#!/usr/bin/env python3
"""Select English Luther/Linus lines for a duration-matched Swedish comparison."""

import argparse
import collections
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import wave

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "freddi_fisk"))
from prepare_voice_datasets import signed16

APP_DATA = Path.home() / "Library/Application Support/FreddiFishVoiceStudio"
WORK = APP_DATA / "work/freddi-fish-2"
SPEECH_SHA256 = "d0ad28713ac4824c24a9f94cfb822b529a990b6410a136cbe8c4079e9ae57b5a"
BASELINE_SECONDS = 190.77877551020407
SAY = re.compile(r'^[ \t]*say-line 2[ \t]*\\\n(?:[ \t]+[^\n]*\\\n)*'
                 r'[ \t]+"\x7fT(\d+),(\d+)\x7f([^"\n]*)', re.MULTILINE)


def dialogue_refs(scripts):
    refs = collections.defaultdict(list)
    hashes = {}
    for path in sorted(Path(scripts).glob("*.scu")):
        original = path.read_bytes()
        hashes[path.name] = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8").replace(r"\x7F", "\x7f").replace(r"\x7f", "\x7f")
        for match in SAY.finditer(text):
            if not re.search(r'^\s*color 232\s*\\$', match[0], re.MULTILINE):
                continue
            refs[int(match[1])].append({"script": path.name,
                "script_sha256": hashes[path.name], "line": text.count("\n", 0, match.start()) + 1,
                "actor": 2, "dialogue_color": 232, "resource_bytes": int(match[2]),
                "original_script_text": match[3]})
    return refs, hashes


def prepare(speech, scripts, output, budget=BASELINE_SECONDS):
    speech, output = Path(speech), Path(output)
    if output.exists():
        raise FileExistsError(f"Dataset already exists; left untouched: {output}")
    manifest = json.loads((speech / "manifest.json").read_text())
    if manifest["source_sha256"] != SPEECH_SHA256:
        raise ValueError("Expected the verified English Freddi Fish 2 speech archive")
    refs, scripts_sha256 = dialogue_refs(scripts)
    known = {row["offset"] for row in manifest["clips"]}
    if set(refs) - known:
        raise ValueError("Dialogue references are absent from the speech archive")
    rows, seen = [], set()
    for original in manifest["clips"]:
        evidence = refs.get(original["offset"])
        if not evidence or not 1 <= original["duration_seconds"] <= 10:
            continue
        if any(item["resource_bytes"] != original["resource_bytes"] for item in evidence):
            raise ValueError("Script/archive resource size mismatch")
        if original["pcm_sha256"] in seen:
            continue
        seen.add(original["pcm_sha256"])
        split = "validation" if int(original["pcm_sha256"][:8], 16) % 10 == 0 else "reserve"
        rows.append({**original, "speaker": "linus", "source_language": "en",
                     "split": split, "evidence": evidence})
    remaining = budget
    for row in sorted(rows, key=lambda item: item["pcm_sha256"]):
        if row["split"] == "reserve" and row["duration_seconds"] <= remaining:
            row["split"] = "train"
            remaining -= row["duration_seconds"]
    training = [row for row in rows if row["split"] == "train"]
    if len(training) < 3 or remaining > budget * .05:
        raise ValueError("Insufficient English Linus material for the matched experiment")
    output.mkdir(parents=True)
    for row in rows:
        source = speech / Path(row["file"]).name
        with wave.open(str(source), "rb") as wav:
            if (wav.getsampwidth(), wav.getnchannels(), wav.getframerate()) != (1, 1, row["sample_rate"]):
                raise ValueError(f"Unexpected original WAV format: {source}")
            pcm = wav.readframes(wav.getnframes())
        if hashlib.sha256(pcm).hexdigest() != row["pcm_sha256"]:
            raise ValueError(f"Original PCM checksum mismatch: {source}")
        row["file"] = f"linus/{row['split']}/{source.name}"
        target = output / row["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as wav:
            wav.setparams((1, 2, row["sample_rate"], 0, "NONE", "not compressed"))
            wav.writeframes(signed16(pcm))
    summary = {split: {"clips": sum(row["split"] == split for row in rows),
                       "seconds": sum(row["duration_seconds"] for row in rows if row["split"] == split)}
               for split in ("train", "validation", "reserve")}
    report = {"speech_source_sha256": SPEECH_SHA256, "baseline_training_seconds": budget,
              "selection": "Explicit say-line actor 2 AND colour 232; script cues, not a complete listening audit",
              "balance": "Deterministic PCM-hash order; match Swedish FF1 training duration; reserve unused clips",
              "scripts_sha256": scripts_sha256, "summary": summary, "clips": rows}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    cards = [f'<tr><td>{row["split"]}</td><td>{html.escape(row["evidence"][0]["original_script_text"])}</td>'
             f'<td><audio controls preload="none" src="{row["file"]}"></audio></td></tr>' for row in rows]
    (output / "listen.html").write_text('<!doctype html><meta charset="utf-8"><title>English Linus sources</title>'
        '<h1>English Linus / Luther source recordings</h1><table>' + "".join(cards) + '</table>')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--output", type=Path, default=WORK / "linus-english-dataset")
    args = parser.parse_args()
    report = prepare(args.work / "speech", args.work / "scripts/Freddi2", args.output)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
