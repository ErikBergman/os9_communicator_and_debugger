#!/usr/bin/env python3
"""Prepare, train and apply separate Swedish RVC v2 voices using local tools."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "analysis/freddi-fisk/voice-work"
RVC = ROOT / ".local-tools/rvc"
PYTHON = ROOT / ".local-tools/rvc-venv/bin/python"


def run(arguments):
    env = os.environ.copy()
    env.update(PYTHONPATH=str(RVC), RVC_AUDIO_FORCE_CPU="1", OMP_NUM_THREADS="4",
               MPLCONFIGDIR=str(WORK / "cache/matplotlib"),
               NUMBA_CACHE_DIR=str(WORK / "cache/numba"),
               HF_HOME=str(WORK / "cache/huggingface"))
    if not shutil.which("ffmpeg"):
        env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
    print("+", " ".join(map(str, arguments)), flush=True)
    subprocess.run([str(PYTHON), *map(str, arguments)], cwd=RVC, env=env, check=True)


def name_for(speaker, smoke):
    return f"swedish-{speaker}-v2" + ("-smoke" if smoke else "")


def input_files(speaker, smoke):
    files = sorted((WORK / "datasets" / speaker / "train").glob("*.wav"))
    if len(files) < 3:
        raise ValueError("Need at least three training clips; run dataset preparation first")
    if smoke:
        files = files[:3]
        target = WORK / "smoke-input" / speaker
        target.mkdir(parents=True, exist_ok=True)
        for source in files:
            destination = target / source.name
            if not destination.exists():
                shutil.copyfile(source, destination)
        if {p.name for p in target.glob('*.wav')} != {p.name for p in files}:
            raise ValueError("Smoke input contains unexpected files; use a fresh work directory")
        return sorted(target.glob("*.wav"))
    return files


def prepare(speaker, smoke):
    files = input_files(speaker, smoke)
    exp = RVC / "logs" / name_for(speaker, smoke)
    exp.mkdir(parents=True, exist_ok=True)
    identity = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    snapshot = exp / "input-files.json"
    if snapshot.exists() and json.loads(snapshot.read_text()) != identity:
        raise RuntimeError("Training input changed; preserve this experiment and start a new one")
    snapshot.write_text(json.dumps(identity, indent=2) + "\n")
    run(["-m", "train.preprocess", files[0].parent, 32000, 1, exp, "True", "3.0"])
    wavs = sorted((exp / "1_16k_wavs").glob("*.wav"))
    if not wavs:
        raise RuntimeError("Preprocessing produced no audio")
    run(["-m", "train.dataset.extract_f0", "cpu", exp, 1, "rmvpe"])
    run(["-m", "train.dataset.extract_hubert_feature", "cpu", 1, 0, exp, "v2", "False"])
    entries = []
    excluded = []
    for wav in sorted((exp / "0_gt_wavs").glob("*.wav")):
        feature = exp / "3_feature768" / (wav.stem + ".npy")
        coarse = exp / "2a_f0" / (wav.name + ".npy")
        pitch = exp / "2b-f0nsf" / (wav.name + ".npy")
        if all(p.is_file() for p in (feature, coarse, pitch)):
            entries.append("|".join(map(str, (wav, feature, coarse, pitch))) + "|0")
        else:
            excluded.append(wav.name)
    if not entries:
        raise RuntimeError("No complete pitch/content features for training")
    (exp / "filelist.txt").write_text("\n".join(entries) + "\n")
    config = json.loads((RVC / "configs/v2/32k.json").read_text())
    config["train"]["fp16_run"] = False
    config["train"]["log_interval"] = 1 if smoke else 50
    config_file = exp / "config.json"
    if not config_file.exists():
        config_file.write_text(json.dumps(config, indent=2) + "\n")
    report = {"speaker": speaker, "smoke_only": smoke, "input_clips": len(files),
              "complete_training_segments": len(entries), "excluded_segments": excluded,
              "validation_used": False, "sample_rate": 32000, "pitch_method": "rmvpe"}
    (exp / "preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    run(["-m", "train.train_index", exp.name, "v2", RVC / "assets/indices", 1, "single"])
    if not list(exp.glob("added*.index")):
        raise RuntimeError("RVC did not produce a retrieval index")
    print(json.dumps(report, indent=2))


def train(speaker, smoke, epochs):
    name = name_for(speaker, smoke)
    exp = RVC / "logs" / name
    if not (exp / "preparation.json").is_file():
        raise RuntimeError("Run prepare for this speaker/experiment first")
    config_file = exp / "config.json"
    config = json.loads(config_file.read_text())
    # Existing prepared experiments log only every 50 batches. Keep the bar
    # responsive without changing the trainer or logging every single batch.
    config["train"]["log_interval"] = min(config["train"]["log_interval"], 10)
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    (RVC / "assets/weights").mkdir(parents=True, exist_ok=True)
    model = RVC / "assets/weights" / (name + ".pth")
    before = model.stat().st_mtime_ns if model.exists() else None
    run([Path(__file__).with_name("rvc_train_progress.py"), "--folder", exp,
         "--speaker", speaker.title(), "--epochs", epochs, "--",
         "-m", "train.train", "-e", name, "-sr", "32k", "-f0", 1,
         "-bs", 1, "-g", "", "-te", epochs, "-se", min(5, epochs),
         "-pg", "assets/pretrained_v2/f0G32k.pth", "-pd", "assets/pretrained_v2/f0D32k.pth",
         "-l", 1, "-c", 0, "-sw", 0, "-v", "v2"])
    # Upstream can return success even if a child training process failed.
    if not model.exists() or model.stat().st_mtime_ns == before:
        raise RuntimeError("Training did not export a new model; inspect the experiment's train.log")
    print(model)


def convert(speaker, smoke, source, output, pitch):
    if not source or not output:
        raise ValueError("Conversion requires --input and --output")
    name = name_for(speaker, smoke)
    indexes = sorted((RVC / "logs" / name).glob("added*.index"))
    if not indexes:
        raise RuntimeError("Missing retrieval index; run prepare first")
    run([Path(__file__).with_name("rvc_infer_worker.py"), "--model", RVC / "assets/weights" / (name + ".pth"),
         "--input", source.resolve(), "--output", output.resolve(),
         "--index", indexes[-1], "--pitch", pitch])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "train", "convert"))
    parser.add_argument("speaker", choices=("freddi", "linus"))
    parser.add_argument("--smoke", action="store_true", help="Separate three-clip plumbing test; not a usable voice model")
    parser.add_argument("--epochs", type=int, default=20, help="Total target epochs, including earlier runs")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pitch", type=int, default=0)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    if args.action == "prepare":
        prepare(args.speaker, args.smoke)
    elif args.action == "train":
        train(args.speaker, args.smoke, args.epochs)
    else:
        convert(args.speaker, args.smoke, args.input, args.output, args.pitch)


if __name__ == "__main__":
    main()
