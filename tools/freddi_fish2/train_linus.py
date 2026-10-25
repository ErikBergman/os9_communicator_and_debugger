#!/usr/bin/env python3
"""Run or resume the isolated, duration-matched 20-epoch English Linus experiment."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare_linus_dataset import APP_DATA, WORK, prepare

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = "english-linus-freddi2-v2"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def train(runtime, work, threads=2):
    with (work / "linus-training.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("The English Linus training job is already running") from None
        dataset = work / "linus-english-dataset"
        if not (dataset / "manifest.json").is_file():
            prepare(work / "speech", work / "scripts/Freddi2", dataset)
        baseline = runtime / "rvc/assets/weights/swedish-linus-v2.pth"
        baseline_hash = digest(baseline)
        experiment = runtime / "rvc/logs" / EXPERIMENT
        experiment.mkdir(exist_ok=True)
        before = experiment / "swedish-baseline-before.json"
        if before.exists() and json.loads(before.read_text())["model_sha256"] != baseline_hash:
            raise RuntimeError("The Swedish comparison baseline changed")
        before.write_text(json.dumps({"model": str(baseline), "model_sha256": baseline_hash}, indent=2) + "\n")
        snapshot = experiment / "input-files.json"
        if snapshot.is_file():
            identity = {p.name: digest(p) for p in sorted((dataset / "linus/train").glob("*.wav"))}
            if json.loads(snapshot.read_text()) != identity:
                raise RuntimeError("English training inputs changed; old experiment left untouched")
        model = runtime / "rvc/assets/weights" / f"{EXPERIMENT}.pth"
        completed = experiment / "completed-training.json"
        if completed.exists() and model.is_file():
            record = json.loads(completed.read_text())
            if (record["epochs"] == 20 and record["model_sha256"] == digest(model)
                    and list(experiment.glob("added*.index"))):
                print("English Linus already completed 20 epochs; Swedish baseline unchanged", flush=True)
                return
        command = [sys.executable, str(ROOT / "tools/freddi_fisk/rvc_voice.py"), "prepare", "linus",
                   "--runtime-root", str(runtime), "--dataset-root", str(dataset), "--experiment", EXPERIMENT]
        env = os.environ.copy()
        env["RVC_TRAIN_THREADS"] = str(threads)
        if not (experiment / "preparation.json").is_file():
            subprocess.run(command, env=env, check=True)
        command[2] = "train"
        command.extend(["--epochs", "20"])
        subprocess.run(command, env=env, check=True)
        if digest(baseline) != baseline_hash:
            raise RuntimeError("Swedish baseline changed during training")
        record = json.loads(completed.read_text())
        record.update(source_language="en", game="Freddi Fish 2", dataset_sha256=digest(dataset / "manifest.json"),
                      swedish_baseline_unchanged=True)
        completed.write_text(json.dumps(record, indent=2) + "\n")
        print("English Linus trained; Swedish baseline unchanged", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=APP_DATA / "runtime")
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--threads", type=int, choices=(1, 2, 3, 4), default=2)
    args = parser.parse_args()
    train(args.runtime_root.expanduser().resolve(), args.work.expanduser().resolve(), args.threads)


if __name__ == "__main__":
    main()
