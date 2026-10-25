#!/usr/bin/env python3
"""Train the Swedish FF1 cast sequentially; Ctrl+C pauses after a saved epoch."""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from prepare_cast_datasets import PROFILES, WORK, digest, prepare, verify
from setup_chatterbox import DEFAULT_RUNTIME, install_references

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAUSED = 75


def atomic_json(path, value):
    temporary = path.with_suffix(".installing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def experiment(runtime, speaker):
    return runtime / "rvc/logs" / f"swedish-{speaker}-v2"


def model_path(runtime, speaker):
    return runtime / "rvc/assets/weights" / f"swedish-{speaker}-v2.pth"


def completed_epochs(runtime, speaker):
    folder = experiment(runtime, speaker)
    record = folder / "completed-training.json"
    model = model_path(runtime, speaker)
    if not record.is_file() or not model.is_file():
        return 0
    metadata = json.loads(record.read_text())
    if not any(p.stat().st_size for p in folder.glob("added*.index")):
        raise RuntimeError(f"Completed {speaker} model is missing its retrieval index")
    if metadata["model_sha256"] != digest(model):
        raise RuntimeError(f"Completed {speaker} model changed; left untouched")
    return metadata["epochs"]


def import_legacy_fish(runtime):
    """Read the epoch count embedded in this user's original, local RVC exports."""
    for speaker in ("freddi", "linus"):
        folder = experiment(runtime, speaker)
        model = model_path(runtime, speaker)
        if (folder / "completed-training.json").exists() or not model.is_file():
            continue
        if not list(folder.glob("added*.index")):
            raise RuntimeError(f"Existing {speaker} model has no retrieval index")
        # These are the user's own previously trained weights, not downloaded
        # arbitrary pickle files. Load in a separate process to release Torch RAM.
        info = subprocess.check_output([
            str(runtime / "rvc-venv/bin/python"), "-c",
            "import torch,sys; m=torch.load(sys.argv[1],map_location='cpu',weights_only=False); "
            "print(m.get('info',''))", str(model)], text=True).strip()
        match = re.fullmatch(r"(\d+)epoch", info)
        if not match:
            raise RuntimeError(f"Cannot verify the epoch count of existing {speaker} model")
        atomic_json(folder / "completed-training.json", {
            "epochs": int(match[1]), "model_sha256": digest(model),
            "provenance": "Epoch metadata embedded in existing Swedish FF1 model"})


def prepared(folder):
    required = ("preparation.json", "config.json", "filelist.txt", "input-files.json")
    if not all((folder / name).is_file() for name in required):
        return False
    if not any(p.stat().st_size for p in folder.glob("added*.index")):
        return False
    lines = (folder / "filelist.txt").read_text().splitlines()
    return bool(lines) and all(len(line.split("|")) == 5 and
                               all(Path(p).is_file() for p in line.split("|")[:4])
                               for line in lines)


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


def compact_finished(runtime, speaker):
    """Discard only this batch's finished secondary-role optimizer checkpoints."""
    if PROFILES[speaker]["group"] != "cast" or not completed_epochs(runtime, speaker):
        return
    for checkpoint in experiment(runtime, speaker).glob("*.pth"):
        if re.fullmatch(r"[GD]_\d+\.pth", checkpoint.name):
            checkpoint.unlink()


class Runner:
    def __init__(self, runtime):
        self.pause_file = runtime / "cast-pause.request"
        self.active = None
        self.training = False
        self.interruptions = 0

    def request_pause(self, signum, frame):
        self.interruptions += 1
        self.pause_file.touch()
        if self.active is None:
            print("\nPause requested; stopping between stages.", flush=True)
        elif self.training and self.interruptions == 1:
            print("\nPause requested: waiting for the next saved epoch. Keep this terminal open."
                  "\nCtrl+C again stops immediately and loses progress since the last checkpoint.", flush=True)
        else:
            print("\nStopping the active stage…", flush=True)
            try:
                os.killpg(self.active.pid, signal.SIGINT)
            except ProcessLookupError:
                pass

    def run(self, command, env, training=False):
        if self.pause_file.exists():
            return PAUSED
        self.training = training
        # Isolate the workers from terminal Ctrl+C. First interrupt requests a
        # checkpoint pause; it must not kill a worker halfway through saving.
        self.active = subprocess.Popen(command, env=env, start_new_session=True)
        try:
            status = self.active.wait()
        finally:
            self.active = None
            self.training = False
        if self.pause_file.exists():
            return PAUSED
        if status:
            raise subprocess.CalledProcessError(status, command)
        return 0


def show_status(runtime, speakers):
    dataset = runtime / "cast-datasets"
    report = json.loads((dataset / "manifest.json").read_text()) if (dataset / "manifest.json").exists() else None
    for speaker in speakers:
        count = completed_epochs(runtime, speaker)
        state = f"ready ({count} epochs)" if count else "not finished"
        if not count and list(experiment(runtime, speaker).glob("G_*.pth")):
            state = "checkpoint saved; will resume"
        source = report["summary"][speaker]["train"] if report else None
        detail = f" · {source['clips']} clips, {source['seconds']:.1f}s original speech" if source else ""
        print(f"{speaker:18} {state}{detail}", flush=True)


def train_all(runtime, epochs, threads, speakers, prepare_only=False, compact=False):
    if not (runtime / "rvc-venv/bin/python").is_file():
        raise RuntimeError("The existing Voice Studio RVC runtime is required")
    with (runtime / "cast-training.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Cast training is already running. Use 'pause' or return to its terminal.") from None
        runner = Runner(runtime)
        runner.pause_file.unlink(missing_ok=True)
        handlers = {sig: signal.signal(sig, runner.request_pause) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            print(f"Swedish FF1 cast · {epochs} total epochs per voice · {threads} CPU threads", flush=True)
            print("Ctrl+C: pause after the next saved epoch. Run the same command to continue.\n", flush=True)
            import_legacy_fish(runtime)
            dataset = runtime / "cast-datasets"
            report = verify(dataset) if dataset.exists() else prepare(WORK / "speech", WORK / "scripts/Freddi", dataset)
            show_status(runtime, speakers)
            if runner.pause_file.exists():
                return PAUSED
            copy_pretrained(runtime)
            install_references(runtime, dataset=dataset, speakers=speakers,
                               overrides={s: dataset / report["references"][s]["file"]
                                          for s in speakers if not (runtime / "chatterbox/references" / f"{s}.wav").exists()})
            if prepare_only:
                print(f"\nDatasets and Chatterbox references are ready: {dataset}", flush=True)
                return 0
            env = os.environ.copy()
            env["RVC_TRAIN_THREADS"] = str(threads)
            for number, speaker in enumerate(speakers, 1):
                if runner.pause_file.exists():
                    return PAUSED
                completed = completed_epochs(runtime, speaker)
                if completed >= epochs:
                    if compact:
                        compact_finished(runtime, speaker)
                    print(f"[{number}/{len(speakers)}] {speaker}: keeping completed model", flush=True)
                    continue
                folder = experiment(runtime, speaker)
                if completed and not (list(folder.glob("G_*.pth")) and list(folder.glob("D_*.pth"))):
                    raise RuntimeError(f"{speaker}: existing model has {completed} epochs but training checkpoints"
                                       " are absent. Keep --epochs 20 or restore its original G/D checkpoints.")
                minimum_free = (2 if compact else 4) * 1024**3
                if shutil.disk_usage(runtime).free < minimum_free:
                    raise RuntimeError("Not enough free disk space for the next voice; free space and run the same command to continue")
                source = report["summary"][speaker]["train"]
                warning = " · VERY LIMITED SOURCE AUDIO" if source["seconds"] < 30 else ""
                print(f"\n[{number}/{len(speakers)}] {PROFILES[speaker]['name']}: {source['seconds']:.1f}s source{warning}", flush=True)
                if speaker in report["notes"]:
                    print(report["notes"][speaker], flush=True)
                command = [sys.executable, str(HERE / "rvc_voice.py"), "prepare", speaker,
                           "--runtime-root", str(runtime), "--dataset-root", str(dataset),
                           "--allow-small-dataset"]
                if not prepared(folder) and runner.run(command, env) == PAUSED:
                    return PAUSED
                # Validate the exact input identity even when feature preparation
                # was completed during an earlier invocation.
                identity = {p.name: digest(p) for p in sorted((dataset / speaker / "train").glob("*.wav"))}
                if json.loads((folder / "input-files.json").read_text()) != identity:
                    raise RuntimeError(f"{speaker}: prepared features belong to different recordings")
                command[2] = "train"
                command.extend(["--epochs", str(epochs), "--save-every", "1",
                                "--pause-file", str(runner.pause_file)])
                if runner.run(command, env, training=True) == PAUSED:
                    return PAUSED
                if completed_epochs(runtime, speaker) < epochs:
                    raise RuntimeError(f"{speaker}: training did not produce a verified completed model")
                if compact:
                    compact_finished(runtime, speaker)
                print(f"{speaker}: ready in Voice Studio", flush=True)
            print("\nCast training finished. Refresh Voice Studio to select the new voices.", flush=True)
            return 0
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="run", choices=("run", "prepare", "pause", "status"))
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--epochs", type=int, default=20, help="Total target, including previously saved epochs")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--compact", action="store_true", help="Discard optimizer checkpoints only AFTER a secondary voice finishes; interrupted voices remain resumable")
    parser.add_argument("--speakers", nargs="+", choices=tuple(PROFILES), default=list(PROFILES))
    args = parser.parse_args()
    if args.epochs < 1 or not 1 <= args.threads <= 4:
        parser.error("Use positive epochs and one to four CPU threads")
    runtime = args.runtime_root.expanduser().resolve()
    if args.action == "pause":
        (runtime / "cast-pause.request").touch()
        print("Pause requested. The active voice will stop after its next saved epoch.")
        return 0
    if args.action == "status":
        show_status(runtime, args.speakers)
        return 0
    try:
        status = train_all(runtime, args.epochs, args.threads, list(dict.fromkeys(args.speakers)),
                           prepare_only=args.action == "prepare", compact=args.compact)
        if status == PAUSED:
            print("\nPaused. You can close the terminal now. Run the same command to continue.")
        return 0 if status == PAUSED else status
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nStopped: {error}\nCompleted voices and saved checkpoints are kept. Run the same command to retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
