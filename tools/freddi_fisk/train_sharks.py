#!/usr/bin/env python3
"""Prepare and train both shark voices, then publish them to the local studio."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_shark_datasets import CUES, SHARKS, WORK, dialogue_refs, prepare
from setup_chatterbox import DEFAULT_RUNTIME, install_references

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def copy_pretrained(runtime):
    versions = json.loads((HERE / "voice-tool-versions.json").read_text())
    for name, expected in versions["models"].items():
        if not name.startswith("pretrained_v2/"):
            continue
        target = runtime / "rvc/assets" / name
        if target.is_file() and digest(target) == expected:
            continue
        source = ROOT / ".local-tools/rvc/assets" / name
        if not source.is_file() or digest(source) != expected:
            raise RuntimeError(f"Missing verified pretrained weights: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".installing")
        shutil.copyfile(source, temporary)
        temporary.replace(target)


def train_all(runtime, epochs, threads):
    if not (runtime / "rvc-venv/bin/python").is_file():
        raise RuntimeError("Install the existing RVC studio runtime first")
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "shark-training.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A shark training job is already running; resume its terminal instead") from None
        dataset = runtime / "shark-datasets"
        if (dataset / "manifest.json").is_file():
            report = json.loads((dataset / "manifest.json").read_text())
            if report.get("cues_sha256") != digest(HERE / "shark-speaker-cues.json"):
                raise RuntimeError("Existing shark dataset uses different speaker cues; left untouched")
            dialogue_refs(WORK / "scripts/Freddi", CUES)
        else:
            report = prepare(WORK / "speech", WORK / "scripts/Freddi", dataset)
        print(json.dumps(report["summary"], indent=2), flush=True)
        copy_pretrained(runtime)
        install_references(runtime, dataset=dataset, speakers=SHARKS)
        env = os.environ.copy()
        env["RVC_TRAIN_THREADS"] = str(threads)
        for speaker in SHARKS:
            experiment = runtime / "rvc/logs" / f"swedish-{speaker}-v2"
            model = runtime / "rvc/assets/weights" / f"swedish-{speaker}-v2.pth"
            completed = experiment / "completed-training.json"
            if completed.exists() and model.is_file():
                metadata = json.loads(completed.read_text())
                if metadata["epochs"] >= epochs and metadata["model_sha256"] == digest(model):
                    print(f"{speaker}: already trained to {metadata['epochs']} epochs", flush=True)
                    continue
            command = [sys.executable, str(HERE / "rvc_voice.py"), "prepare", speaker,
                       "--runtime-root", str(runtime), "--dataset-root", str(dataset)]
            if not (experiment / "preparation.json").exists():
                subprocess.run(command, env=env, check=True)
            command[2] = "train"
            command.extend(["--epochs", str(epochs)])
            print(f"Training {speaker} to {epochs} total epochs", flush=True)
            subprocess.run(command, env=env, check=True)
            if not model.is_file() or not list(experiment.glob("added*.index")):
                raise RuntimeError(f"No completed model/index pair for {speaker}")
            completed.write_text(json.dumps({"epochs": epochs, "model_sha256": digest(model),
                                           "dataset_sha256": digest(dataset / "manifest.json")}, indent=2) + "\n")
            print(f"{speaker}: trained model is available in Voice Studio", flush=True)
        print("Both shark models are ready. Restart or refresh Voice Studio.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.epochs < 1 or not 1 <= args.threads <= 4:
        parser.error("Use positive epochs and between one and four CPU threads")
    train_all(args.runtime_root.expanduser().resolve(), args.epochs, args.threads)


if __name__ == "__main__":
    main()
