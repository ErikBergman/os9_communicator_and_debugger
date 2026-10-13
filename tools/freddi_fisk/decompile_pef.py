#!/usr/bin/env python3
"""Run isolated, read-only Ghidra analysis of the preserved PowerPC PEF fork."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=REPO / "analysis/freddi-fisk/mac-forks/22/data.fork")
    parser.add_argument("--output", type=Path, default=REPO / "analysis/freddi-fisk/decompilation")
    parser.add_argument("--ghidra-dir", type=Path, default=REPO / ".local-tools/ghidra_12.1.4_PUBLIC")
    parser.add_argument("--jdk-home", type=Path, default=REPO / ".local-tools/jdk-21.0.12.1+1/Contents/Home")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe-fcb", action="store_true", help="Trace FCB import references instead of exporting pseudocode")
    mode.add_argument("--review-close", action="store_true", help="Review the independently mapped original or patched file-close routine")
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    header = source.open("rb")
    with header:
        observed = header.read(12)
        if observed != b"Joy!peffpwpc":
            parser.error(f"The input must be a PowerPC PEF file; observed header: {observed!r}")
    launcher = args.ghidra_dir.resolve() / "support/analyzeHeadless"
    java = args.jdk_home.resolve() / "bin/java"
    if not launcher.is_file() or not java.is_file():
        parser.error("Ghidra or the JDK is missing; see the tool README")
    output.mkdir(parents=True, exist_ok=True)
    script, report_name = (("InspectFCBAccess.java", "fcb-access.json") if args.probe_fcb else
                          ("ReviewCloseRoutine.java", "ghidra-close.json") if args.review_close else
                          ("ExportPefAnalysis.java", "ghidra-analysis.json"))
    report_path = output / report_name
    if report_path.exists():
        parser.error("The output already has a completed report; choose a fresh --output directory")
    before, info = checksum(source), source.stat()
    env = dict(os.environ)
    env["JAVA_HOME"] = str(args.jdk_home.resolve())
    # Ghidra's shell launcher picks PATH java before JAVA_HOME for bootstrap.
    env["PATH"] = str(args.jdk_home.resolve() / "bin") + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="freddi-ghidra-") as project:
        user_home = Path(project) / "home"
        java_temp = Path(project) / "tmp"
        user_home.mkdir()
        java_temp.mkdir()
        env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "")
            + f" -Duser.home={user_home} -Djava.io.tmpdir={java_temp}").strip()
        command = [str(launcher), project, "FreddiAnalysis", "-import", str(source),
                   "-processor", "PowerPC:BE:32:default", "-cspec", "default",
                   "-readOnly", "-deleteProject", "-analysisTimeoutPerFile", "300",
                   "-max-cpu", "2",
                   "-scriptPath", str(Path(__file__).resolve().parent),
                   "-postScript", script, str(output),
                   "-log", str(output / "ghidra-import.log"),
                   "-scriptlog", str(output / "ghidra-script.log")]
        if args.review_close:
            command.append("-noanalysis")
        result = subprocess.run(command, env=env, check=False)
    after = source.stat()
    after_checksum = checksum(source)
    verification = {"input": str(source), "before_sha256": before, "after_sha256": after_checksum,
                    "before_bytes": info.st_size, "after_bytes": after.st_size,
                    "before_mtime_ns": info.st_mtime_ns, "after_mtime_ns": after.st_mtime_ns}
    (output / "source-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    if after_checksum != before or info.st_mtime_ns != after.st_mtime_ns or info.st_size != after.st_size:
        raise RuntimeError("Source changed during analysis")
    print("Source SHA-256 unchanged:", before, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    if not report_path.is_file():
        raise SystemExit("Ghidra did not produce a completed analysis report; inspect the logs")
    report = json.loads(report_path.read_text())
    if report.get("executable_sha256", "").lower() != before:
        raise SystemExit("The analysis report does not identify the input fork")
    if report.get("language") != "PowerPC:BE:32:default":
        raise SystemExit("The analysis report has an unexpected processor language")
    if (report.get("cancelled") or (args.review_close and not report.get("decompiled")) or
            (not args.probe_fcb and not args.review_close and not report.get("decompiled_function_count"))):
        raise SystemExit("The decompilation was cancelled or produced no functions")


if __name__ == "__main__":
    main()
