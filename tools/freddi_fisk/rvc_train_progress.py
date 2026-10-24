#!/usr/bin/env python3
"""Display Rich progress from the pinned RVC trainer's live log records."""

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.progress import (BarColumn, Progress, SpinnerColumn, TaskProgressColumn,
                           TextColumn, TimeElapsedColumn, TimeRemainingColumn)


# Match the numbers, rather than translated labels, in RVC's locale files.
BATCH = re.compile(r"(?<!\d)(\d+)\s*\[(\d+(?:\.\d+)?)%\]")
EPOCH = re.compile(r"====>\s*\D+?(\d+)\b")


def parse_progress(line, epochs):
    match = EPOCH.search(line)
    if match:
        epoch = int(match[1])
        return (epoch, 100.0, True) if 1 <= epoch <= epochs else None
    match = BATCH.search(line)
    if match:
        epoch, percent = int(match[1]), float(match[2])
        if 1 <= epoch <= epochs and 0 <= percent <= 100:
            return epoch, percent, False
    return None


class LogTail:
    def __init__(self, path):
        self.path = Path(path)
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        self.pending = b""

    def read(self):
        try:
            with self.path.open("rb") as log:
                if os.fstat(log.fileno()).st_size < self.offset:
                    self.offset, self.pending = 0, b""
                log.seek(self.offset)
                data = log.read()
                self.offset = log.tell()
        except FileNotFoundError:
            return []
        lines = (self.pending + data).split(b"\n")
        self.pending = lines.pop()
        return [line.decode("utf-8", errors="replace") for line in lines]


def stop_training(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except ProcessLookupError:
        pass


def monitor(command, folder, epochs, speaker, console=None, poll_interval=.2):
    console = console or Console()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tail = LogTail(folder / "train.log")
    output = folder / "training-console.log"
    console.print(f"Training {speaker} to {epochs} total epochs", markup=False)
    console.print(f"Trainer output: {output}", markup=False)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    with output.open("ab") as raw:
        invocation_start = raw.tell()
        raw.write(b"\n--- New training invocation ---\n")
        raw.flush()
        process = subprocess.Popen(command, stdout=raw, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=True)
        try:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          BarColumn(), TaskProgressColumn(), TimeElapsedColumn(),
                          TimeRemainingColumn(), console=console,
                          refresh_per_second=4) as progress:
                overall = progress.add_task("Loading models / data", total=None)
                current = progress.add_task("Current epoch", total=100, visible=False)
                started, last_epoch, latest = False, 0, 0.0
                while True:
                    status = process.poll()
                    for line in tail.read():
                        event = parse_progress(line, epochs)
                        if event is None:
                            continue
                        epoch, percent, finished = event
                        completed = epoch - 1 + percent / 100
                        if started and completed < latest:
                            continue
                        if not started:
                            # Starting at a resumed epoch must not inflate speed / ETA.
                            progress.reset(overall, total=epochs, completed=epoch - 1)
                            started = True
                        latest = completed
                        if epoch != last_epoch:
                            progress.reset(current, total=100, completed=0, visible=True)
                            last_epoch = epoch
                        progress.update(overall, completed=completed,
                                        description=f"{speaker} · epoch {epoch}/{epochs}")
                        progress.update(current, completed=percent,
                                        description=f"Epoch {epoch}")
                        if finished:
                            if not console.is_terminal:
                                console.print(f"Epoch {epoch}/{epochs} complete", markup=False)
                            if epoch == epochs:
                                progress.update(overall, description="Epochs complete; saving model")
                    if status is not None:
                        break
                    time.sleep(poll_interval)
        except BaseException:
            stop_training(process)
            raise
    if status:
        console.print(f"Trainer exited with status {status}. Recent output:", style="red", markup=False)
        with output.open("rb") as raw:
            raw.seek(max(invocation_start, output.stat().st_size - 12000))
            console.print(raw.read().decode("utf-8", errors="replace"), markup=False)
    else:
        console.print("Trainer exited; checking exported model…", markup=False)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.epochs < 1:
        parser.error("A trainer command and positive epoch target are required")
    try:
        return monitor([sys.executable, *command], args.folder, args.epochs, args.speaker)
    except KeyboardInterrupt:
        Console().print("Training interrupted. Resume from the latest saved checkpoint.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
