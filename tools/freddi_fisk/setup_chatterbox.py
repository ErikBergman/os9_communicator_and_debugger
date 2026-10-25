#!/usr/bin/env python3
"""Install isolated Chatterbox tools and original Swedish reference clips."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_RUNTIME = Path.home() / "Library/Application Support/FreddiFishVoiceStudio/runtime"
VERSIONS = json.loads((HERE / "chatterbox-versions.json").read_text())


def run(arguments, **kwargs):
    print("+", " ".join(map(str, arguments)), flush=True)
    subprocess.run(list(map(str, arguments)), check=True, **kwargs)


def choose_reference(dataset, speaker):
    manifest = json.loads((dataset / "manifest.json").read_text())
    candidates = [row for row in manifest["clips"]
                  if row["speaker"] == speaker and row["split"] == "train"
                  and 3 <= row["duration_seconds"] <= 10]
    if not candidates:
        raise ValueError(f"No 3–10 second training reference for {speaker}")
    row = min(candidates, key=lambda item: (abs(item["duration_seconds"] - 8), item["file"]))
    return dataset / row["file"]


def install_references(runtime, overrides=None, dataset=None):
    dataset = dataset or ROOT / "analysis/freddi-fisk/voice-work/datasets"
    destination = runtime / "chatterbox/references"
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for speaker in ("freddi", "linus"):
        target = destination / f"{speaker}.wav"
        source = (overrides or {}).get(speaker)
        if source is None and target.is_file():
            print(f"Keeping existing reference: {target}", flush=True)
            continue
        source = source or choose_reference(dataset, speaker)
        with wave.open(str(source), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or not 3 <= duration <= 10:
                raise ValueError(f"Reference must be a 3–10 second mono WAV: {source}")
        temporary = target.with_suffix(".installing")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        metadata[speaker] = {"source": str(source), "duration_seconds": duration,
                             "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        print(f"Reference for {speaker}: {source.name} ({duration:.1f}s)", flush=True)
    manifest = destination / "references.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    manifest.write_text(json.dumps({**previous, **metadata}, indent=2) + "\n")


def verify_models(runtime):
    folder = runtime / "chatterbox/models"
    for name, spec in VERSIONS["models"].items():
        model = folder / name
        if not model.is_file() or model.stat().st_size != spec["size"]:
            raise RuntimeError(f"Missing or incomplete Chatterbox model: {model}")
        if "sha256" in spec:
            with model.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != spec["sha256"]:
                raise RuntimeError(f"Chatterbox model checksum mismatch: {model}")


def install(runtime, overrides):
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Run setup with Python 3.12, as used for the existing RVC runtime")
    runtime.mkdir(parents=True, exist_ok=True)
    missing = sum(spec["size"] for name, spec in VERSIONS["models"].items()
                  if not (runtime / "chatterbox/models" / name).exists())
    if shutil.disk_usage(runtime).free < missing + 2 * 1024**3:
        raise RuntimeError("Not enough free disk space for Chatterbox models and Python tools")
    install_references(runtime, overrides)
    (runtime / "chatterbox/installed.json").unlink(missing_ok=True)
    environment = runtime / "chatterbox-venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    run([python, "-m", "pip", "install", "--no-cache-dir", "--timeout", "120",
         "--retries", "5", "--index-url",
         "https://pypi.org/simple", "-r", HERE / "chatterbox-requirements.txt"])
    env = os.environ.copy()
    env.update(HF_HOME=str(runtime / "chatterbox/cache"), HF_HUB_DISABLE_XET="1",
               HF_HUB_DOWNLOAD_TIMEOUT="120", PKUSEG_HOME=str(runtime / "chatterbox/cache/pkuseg"))
    print("Downloading pinned multilingual model files (about 3.2 GB on first setup)…", flush=True)
    run([python, "-c",
         "import json,sys; from huggingface_hub import snapshot_download; "
         "v=json.load(open(sys.argv[1])); "
         "snapshot_download(v['model_repository'],revision=v['model_revision'],"
         "allow_patterns=list(v['models']),local_dir=sys.argv[2])",
         HERE / "chatterbox-versions.json", runtime / "chatterbox/models"], env=env)
    verify_models(runtime)
    # Upstream initializes the Chinese tokenizer even for Swedish. Prepare its
    # caches here, rather than permitting network downloads during synthesis.
    run([python, "-c",
         "import json,sys; from huggingface_hub import hf_hub_download; "
         "from pathlib import Path; from chatterbox.models.tokenizers import MTLTokenizer; "
         "from chatterbox.mtl_tts import ChatterboxMultilingualTTS; "
         "from perth import PerthImplicitWatermarker; "
         "v=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); "
         "mapping=hf_hub_download(v['model_repository'],filename='Cangjie5_TC.json'); "
         "assert Path(mapping).read_bytes()==(root/'Cangjie5_TC.json').read_bytes(); "
         "MTLTokenizer(str(root/'grapheme_mtl_merged_expanded_v1.json')); "
         "assert 'sv' in ChatterboxMultilingualTTS.get_supported_languages(); "
         "PerthImplicitWatermarker()",
         HERE / "chatterbox-versions.json", runtime / "chatterbox/models"], env=env)
    installed = subprocess.check_output([str(python), "-m", "pip", "freeze"], text=True)
    (runtime / "chatterbox/installed-requirements.txt").write_text(installed)
    (runtime / "chatterbox/installed.json").write_text(json.dumps(VERSIONS, indent=2) + "\n")
    print("Chatterbox is installed. Restart Voice Studio to use Chatterbox + RVC.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "references", "check"))
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    for speaker in ("freddi", "linus"):
        parser.add_argument(f"--reference-{speaker}", type=Path)
    args = parser.parse_args()
    runtime = args.runtime_root.expanduser().resolve()
    overrides = {speaker: getattr(args, "reference_" + speaker)
                 for speaker in ("freddi", "linus")}
    if args.action == "install":
        install(runtime, overrides)
    elif args.action == "references":
        install_references(runtime, overrides)
    else:
        verify_models(runtime)
        print("Chatterbox model sizes and checksums verified.")


if __name__ == "__main__":
    main()
