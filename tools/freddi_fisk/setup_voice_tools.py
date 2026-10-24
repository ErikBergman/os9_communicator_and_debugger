#!/usr/bin/env python3
"""Install pinned voice tools into this repository's ignored .local-tools folder."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCAL = ROOT / ".local-tools"
WORK = ROOT / "analysis/freddi-fisk/voice-work"
VERSIONS = json.loads((HERE / "voice-tool-versions.json").read_text())


def run(args, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def checkout(name, url):
    target = LOCAL / name
    revision = VERSIONS[name]
    if not target.exists():
        run(["git", "clone", "--no-checkout", "--filter=blob:none", url, target])
        run(["git", "-C", target, "checkout", "--detach", revision])
    actual = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if actual != revision:
        raise RuntimeError(f"Existing {name} is at {actual}, expected {revision}; left untouched")
    return target


def environment(name):
    target = LOCAL / (name + "-venv")
    if not target.exists():
        venv.EnvBuilder(with_pip=True).create(target)
    return target / "bin/python"


def setup():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Run setup with Python 3.12 (the bundled Codex Python is suitable)")
    LOCAL.mkdir(exist_ok=True)
    rvc = checkout("rvc", "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git")
    nut = checkout("nutcracker", "https://github.com/BLooperZ/nutcracker.git")
    python = environment("rvc")
    run([python, "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "-r", HERE / "rvc-requirements.txt"])
    run([environment("nutcracker"), "-m", "pip", "install", "--index-url", "https://pypi.org/simple", nut, "click==8.1.8"])
    env = os.environ.copy()
    env.update(HF_HOME=str(WORK / "cache/huggingface"), HF_HUB_DISABLE_XET="1")
    run([python, "-c",
         "import json,sys; from huggingface_hub import snapshot_download; "
         "v=json.load(open(sys.argv[1])); "
         "snapshot_download(v['model_repository'],revision=v['model_revision'],"
         "allow_patterns=list(v['models']),local_dir=sys.argv[2])",
         HERE / "voice-tool-versions.json", rvc / "assets"], env=env)
    for name, expected in VERSIONS["models"].items():
        data = (rvc / "assets" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Model checksum mismatch: {name}")
    pitch = rvc / "assets/rmvpe/rmvpe.pt"
    pitch.parent.mkdir(exist_ok=True)
    shutil.copyfile(rvc / "assets/rmvpe.pt", pitch)
    WORK.mkdir(parents=True, exist_ok=True)
    installed = subprocess.check_output([str(python), "-m", "pip", "freeze"], text=True)
    (WORK / "installed-rvc-requirements.txt").write_text(installed)
    print("Voice tools installed; model checksums verified.")


def scripts():
    """Give NUTCracker correctly named copies; never edit the preserved forks."""
    game = WORK / "game"
    game.mkdir(parents=True, exist_ok=True)
    for catalog_id, suffix in ((23, 0), (24, 1), (25, 2), (26, 4)):
        source = ROOT / f"analysis/freddi-fisk/mac-forks/{catalog_id}/data.fork"
        target = game / f"Freddi.he{suffix}"
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError(f"Existing game copy differs: {target}")
        else:
            shutil.copyfile(source, target)
    if (WORK / "scripts").exists():
        raise FileExistsError("Decompiled scripts already exist; left untouched")
    run([LOCAL / "nutcracker-venv/bin/python", "-c",
         "from pathlib import Path; from nutcracker.sputm.windex.runner import decompile,Version; "
         "decompile(Path('game/Freddi.he0'),gver=Version.he73,verbose=False,chiper_key='69',skip_transform=False)"], cwd=WORK)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "scripts"))
    args = parser.parse_args()
    setup() if args.action == "install" else scripts()
