#!/usr/bin/env python3
"""Extract separate Swedish shark datasets from verified cutscene dialogue cues."""

import argparse
import collections
import hashlib
import html
import json
import re
import wave
from pathlib import Path

from prepare_voice_datasets import signed16

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1] / "analysis/freddi-fisk/voice-work"
CUES = json.loads((HERE / "shark-speaker-cues.json").read_text())
SHARKS = ("boss", "spongehead")


def dialogue_refs(script_dir, cues=CUES):
    refs = collections.defaultdict(list)
    for name, specification in cues.items():
        source = Path(script_dir) / name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != specification["sha256"]:
            raise ValueError(f"Unverified cutscene script: {source}")
        lines = source.read_text(encoding="utf-8").splitlines()
        script, i = None, 0
        while i < len(lines):
            match = re.match(r"\s*script (\d+)\b", lines[i])
            if match:
                script = match[1]
            colors = specification["scripts"].get(script, {})
            if not colors or not re.match(r"\s*(actor \S+|say-line)\b", lines[i]):
                i += 1
                continue
            block = [(i + 1, lines[i])]
            while lines[i].rstrip().endswith("\\") and i + 1 < len(lines) and lines[i + 1].strip():
                i += 1
                block.append((i + 1, lines[i]))
            # Actors are shared across characters; only explicit colours within
            # these audited scripts identify a speaker. Never inherit a colour
            # from an earlier actor command or another cutscene.
            color = None
            for line_number, line in block:
                match = re.match(r"\s*(?:talk-color|color) (\d+)\b", line)
                if match:
                    color = match[1]
                match = re.search(r'"@T(\d+),(\d+)@([^"\n]*)', line)
                if match and color in colors:
                    refs[int(match[1])].append({
                        "speaker": colors[color], "resource_bytes": int(match[2]),
                        "original_script_text": match[3], "script": name,
                        "script_sha256": digest, "script_id": script,
                        "dialogue_color": int(color), "line": line_number,
                    })
            i += 1
    return refs


def prepare(speech, scripts, output):
    speech, output = Path(speech), Path(output)
    if output.exists():
        raise FileExistsError(f"Dataset directory already exists; left untouched: {output}")
    source = json.loads((speech / "manifest.json").read_text())
    refs = dialogue_refs(scripts)
    known = {row["offset"] for row in source["clips"]}
    if set(refs) - known:
        raise ValueError("Cutscene cues reference absent speech resources")
    selected, seen, skipped = [], set(), collections.Counter()
    for row in source["clips"]:
        evidence = refs.get(row["offset"], [])
        if not evidence:
            continue
        speakers = {entry["speaker"] for entry in evidence}
        if len(speakers) != 1:
            skipped["conflicting_speakers"] += 1
            continue
        if any(entry["resource_bytes"] != row["resource_bytes"] for entry in evidence):
            raise ValueError(f"Archive resource size mismatch: {row['offset']}")
        if not 1 <= row["duration_seconds"] <= 10:
            skipped["outside_1_to_10_seconds"] += 1
            continue
        if row["pcm_sha256"] in seen:
            skipped["duplicate_pcm"] += 1
            continue
        seen.add(row["pcm_sha256"])
        speaker = speakers.pop()
        split = "validation" if int(row["pcm_sha256"][:8], 16) % 10 == 0 else "train"
        selected.append({**row, "speaker": speaker, "split": split, "evidence": evidence,
                         "file": f"{speaker}/{split}/{Path(row['file']).name}"})
    for speaker in SHARKS:
        if sum(row["speaker"] == speaker and row["split"] == "train" for row in selected) < 3:
            raise ValueError(f"Insufficient verified training recordings for {speaker}")
    output.mkdir(parents=True)
    for row in selected:
        original = speech / Path(row["file"]).name
        with wave.open(str(original), "rb") as wav:
            if (wav.getsampwidth(), wav.getnchannels(), wav.getframerate()) != (1, 1, row["sample_rate"]):
                raise ValueError(f"Unexpected original speech format: {original}")
            pcm = wav.readframes(wav.getnframes())
        if hashlib.sha256(pcm).hexdigest() != row["pcm_sha256"]:
            raise ValueError(f"Original PCM checksum mismatch: {original}")
        target = output / row["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as wav:
            wav.setparams((1, 2, row["sample_rate"], 0, "NONE", "not compressed"))
            wav.writeframes(signed16(pcm))
    summary = {}
    for speaker in SHARKS:
        summary[speaker] = {}
        for split in ("train", "validation"):
            group = [row for row in selected if row["speaker"] == speaker and row["split"] == split]
            summary[speaker][split] = {"clips": len(group),
                                       "seconds": sum(row["duration_seconds"] for row in group)}
    report = {"speech_source_sha256": source["source_sha256"], "summary": summary,
              "cues_sha256": hashlib.sha256((HERE / "shark-speaker-cues.json").read_bytes()).hexdigest(),
              "selection": "Explicit dialogue colours in checksum-verified shark cutscenes; not a listening audit",
              "skipped": dict(skipped), "clips": selected}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    rows = [f'<tr><td>{row["speaker"]}</td><td>{row["split"]}</td>'
            f'<td>{html.escape(row["evidence"][0]["original_script_text"])}</td>'
            f'<td><audio controls preload="none" src="{row["file"]}"></audio></td></tr>' for row in selected]
    (output / "listen.html").write_text('<!doctype html><meta charset="utf-8"><title>Shark voice references</title>'
                                       '<h1>Boss / Spongehead source recordings</h1><table>' + "".join(rows) + '</table>')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", type=Path, default=WORK / "speech")
    parser.add_argument("--scripts", type=Path, default=WORK / "scripts/Freddi")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.speech, args.scripts, args.output)["summary"], indent=2))


if __name__ == "__main__":
    main()
