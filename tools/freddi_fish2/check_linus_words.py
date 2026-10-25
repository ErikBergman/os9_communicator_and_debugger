#!/usr/bin/env python3
"""Transcribe the guides and both Linus outputs locally, without a text prompt."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

APP_DATA = Path.home() / "Library/Application Support/FreddiFishVoiceStudio"


def word_errors(expected, observed):
    words = lambda text: re.findall(r"[^\W\d_]+", text.casefold())
    source, target = words(expected), words(observed)
    previous = list(range(len(target) + 1))
    for number, word in enumerate(source, 1):
        current = [number]
        for column, other in enumerate(target, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (word != other)))
        previous = current
    return {"edits": previous[-1], "expected_words": len(source),
            "word_error_rate": previous[-1] / max(1, len(source))}


def check(runtime, comparison):
    import numpy as np
    from faster_whisper import WhisperModel
    installation = json.loads((runtime / "whisper-small-installation.json").read_text())
    model = WhisperModel(str(runtime / "whisper-small"), device="cpu", compute_type="int8",
                         cpu_threads=2, num_workers=1, local_files_only=True)
    results = json.loads((comparison / "results.json").read_text())
    report = {"recognizer": installation, "language": "sv", "initial_prompt": None,
              "interpretation": "Automated transcription only; not a listening assessment of voice similarity or accent",
              "sentences": []}
    for row in results["sentences"]:
        item = {"number": row["number"], "expected": row["text"], "recordings": {}}
        paths = {"guide": comparison / "guides" / f'{row["number"]:02d}-guide-32k.wav',
                 **{label: comparison / voice["file"] for label, voice in row["voices"].items()}}
        for label, path in paths.items():
            # Supply the supported float-array input, using the existing FFmpeg
            # decoder; PyAV 19 removed a keyword used by faster-whisper 1.2.1.
            pcm = subprocess.check_output([shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg",
                "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
                "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"], timeout=30)
            audio = np.frombuffer(pcm, dtype="<f4").copy()
            segments, info = model.transcribe(audio, language="sv", task="transcribe", beam_size=5,
                temperature=0, condition_on_previous_text=False, vad_filter=False)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            item["recordings"][label] = {"file": str(path), "text": text, **word_errors(row["text"], text)}
            print(f'{row["number"]} {label}: {text}', flush=True)
        report["sentences"].append(item)
        (comparison / "transcription-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=APP_DATA / "runtime")
    parser.add_argument("--comparison", type=Path, default=APP_DATA / "comparisons/linus-sv-ff1-vs-en-ff2")
    args = parser.parse_args()
    check(args.runtime_root.expanduser().resolve(), args.comparison.expanduser().resolve())


if __name__ == "__main__":
    main()
