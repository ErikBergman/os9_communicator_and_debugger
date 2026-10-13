#!/usr/bin/env python3
"""Install pinned Ghidra and Apple Silicon JDK archives in .local-tools only."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

REPO = Path(__file__).resolve().parents[2]


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("These pinned JDK downloads are for Apple Silicon macOS.")
    runtimes = json.loads(Path(__file__).with_name("runtime-downloads.json").read_text())
    root = REPO / ".local-tools"
    downloads = root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    for runtime in runtimes:
        if (root / runtime["directory"]).is_dir():
            print("Already present:", runtime["directory"], flush=True)
            continue
        archive = downloads / runtime["archive"]
        if not archive.exists():
            print("Downloading:", runtime["name"], flush=True)
            with urllib.request.urlopen(runtime["url"], timeout=60) as source, archive.open("xb") as target:
                while data := source.read(1024 * 1024):
                    target.write(data)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != runtime["sha256"] or archive.stat().st_size != runtime["download_bytes"]:
            raise SystemExit(f"Archive verification failed: {archive}. Remove the incomplete archive before retrying.")
        print("Checksum verified:", runtime["name"], digest, flush=True)
        if runtime["name"] == "ghidra":
            with zipfile.ZipFile(archive) as packed:
                packed.extractall(root)
                for info in packed.infolist():
                    path = root / info.filename
                    mode = (info.external_attr >> 16) & 0o777
                    if mode and path.is_file():
                        path.chmod(mode)
        else:
            with tarfile.open(archive) as packed:
                packed.extractall(root, filter="data")
        archive.unlink()
        print("Installed:", runtime["directory"], flush=True)
    ghidra = root / "ghidra_12.1.4_PUBLIC"
    native = ghidra / "Ghidra/Features/Decompiler/os/mac_arm_64/decompile"
    if not native.exists():
        cpp = ghidra / "Ghidra/Features/Decompiler/src/decompile/cpp"
        print("Building Apple Silicon native decompiler with Xcode Command Line Tools", flush=True)
        subprocess.run(["make", "clean"], cwd=cpp, check=True)
        subprocess.run(["make", "-j2", "ghidra_opt", "ARCH_TYPE=-arch arm64",
                        "OSDIR=mac_arm_64", "ADDITIONAL_FLAGS=-mmacosx-version-min=11.0 -w"], cwd=cpp, check=True)
        native.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cpp / "ghidra_opt", native)
        native.chmod(0o755)
    print("Run tools/freddi_fisk/decompile_pef.py next; existing runtime directories were not reverified.")


if __name__ == "__main__":
    main()
