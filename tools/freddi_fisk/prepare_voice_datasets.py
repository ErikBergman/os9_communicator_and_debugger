#!/usr/bin/env python3
"""Select Freddi/Linus speech using explicit dialogue-position cues in SCU scripts."""

import argparse
import array
import collections
import hashlib
import html
import json
import re
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "analysis/freddi-fisk/voice-work"
SAY = re.compile(
    r'^[ \t]*say-line[^\n]*\\\n(?:[ \t]+[^\n]*\\\n)*'
    r'[ \t]+"@T(\d+),(\d+)@([^"\n]*)', re.MULTILINE)


def dialogue_refs(script_dir):
    refs = collections.defaultdict(list)
    for path in sorted(Path(script_dir).glob("*.scu")):
        text = path.read_text(encoding="utf-8", errors="strict")
        for match in SAY.finditer(text):
            # Deliberately exclude bare ego/actor IDs and animation talkie tables:
            # a single actor may play several characters in a cutscene/minigame.
            freddi = "at V.270,V.271" in match[0]
            linus = "at V.272,V.273" in match[0]
            if freddi == linus:
                continue
            refs[int(match[1])].append({
                "speaker": "freddi" if freddi else "linus",
                "resource_bytes": int(match[2]), "original_script_text": match[3],
                "script": path.name, "line": text.count("\n", 0, match.start()) + 1,
            })
    return refs


def signed16(pcm):
    samples = array.array("h", ((value - 128) * 256 for value in pcm))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def prepare(speech_dir, scripts, output):
    speech_dir, output = Path(speech_dir), Path(output)
    manifest = json.loads((speech_dir / "manifest.json").read_text())
    refs = dialogue_refs(scripts)
    if not refs:
        raise ValueError("No explicit Freddi/Linus dialogue-position cues found")
    selected, skipped, seen = [], collections.Counter(), set()
    known = {row["offset"]: row for row in manifest["clips"]}
    if set(refs) - set(known):
        raise ValueError("Script references speech offsets missing from this archive")
    for row in manifest["clips"]:
        matches = refs.get(row["offset"], [])
        if not matches:
            skipped["no_explicit_speaker_cue"] += 1
            continue
        labels = {m["speaker"] for m in matches}
        if len(labels) != 1:
            skipped["conflicting_speaker_cues"] += 1
            continue
        if any(m["resource_bytes"] != row["resource_bytes"] for m in matches):
            raise ValueError(f"Script/archive resource size mismatch at {row['offset']}")
        if not 1 <= row["duration_seconds"] <= 10:
            skipped["outside_1_to_10_seconds"] += 1
            continue
        # Deduplicate by original PCM, including across different offsets/speakers.
        if row["pcm_sha256"] in seen:
            skipped["duplicate_pcm"] += 1
            continue
        seen.add(row["pcm_sha256"])
        speaker = next(iter(labels))
        # All byte-identical recordings stay in one split, independent of filenames.
        split = "validation" if int(row["pcm_sha256"][:8], 16) % 10 == 0 else "train"
        selected.append({**row, "speaker": speaker, "split": split,
                         "evidence": matches, "file": f"{speaker}/{split}/{row['file']}"})
    if not {"freddi", "linus"} <= {r["speaker"] for r in selected}:
        raise ValueError("Both characters must have selected recordings")
    output.mkdir(parents=True, exist_ok=False)
    for row in selected:
        source = speech_dir / Path(row["file"]).name
        with wave.open(str(source), "rb") as wav:
            if (wav.getsampwidth(), wav.getnchannels(), wav.getframerate()) != (1, 1, row["sample_rate"]):
                raise ValueError(f"Unexpected WAV format: {source}")
            pcm = wav.readframes(wav.getnframes())
        if hashlib.sha256(pcm).hexdigest() != row["pcm_sha256"]:
            raise ValueError(f"PCM hash mismatch: {source}")
        target = output / row["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(row["sample_rate"])
            wav.writeframes(signed16(pcm))
    summary = {}
    for speaker in ("freddi", "linus"):
        summary[speaker] = {}
        for split in ("train", "validation"):
            group = [r for r in selected if (r["speaker"], r["split"]) == (speaker, split)]
            summary[speaker][split] = {"clips": len(group), "seconds": sum(r["duration_seconds"] for r in group)}
    report = {"speech_source_sha256": manifest["source_sha256"],
              "selection": "Explicit at V.270,V.271 (Freddi) / V.272,V.273 (Linus); script cues, not a listening audit",
              "format": "16-bit mono PCM at original rate; no added bandwidth or denoising",
              "summary": summary, "skipped": dict(skipped), "clips": selected}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    cards = []
    for row in selected:
        label = html.escape(row["evidence"][0]["original_script_text"])
        cards.append(f'<tr><td>{row["speaker"]}</td><td>{row["split"]}</td><td>{row["offset"]}</td>'
                     f'<td>{label}</td><td><audio controls preload="none" src="{row["file"]}"></audio></td></tr>')
    (output / "listen.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Freddi/Linus dataset review</title>'
        '<style>body{font:16px system-ui;max-width:1400px;margin:2em auto}td{padding:.5em}tr:nth-child(even){background:#eee}</style>'
        '<h1>Freddi / Linus source recordings</h1><p>Labels use script dialogue positions. '
        'Descriptions are the retained English script text; recordings are Swedish. '
        'Listen for wrong speakers, effects, silence and damaged audio.</p>'
        '<table><tr><th>Speaker</th><th>Split</th><th>Offset</th><th>Original script text</th><th>Recording</th></tr>'
        + "\n".join(cards) + '</table>', encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", type=Path, default=WORK / "speech")
    parser.add_argument("--scripts", type=Path, default=WORK / "scripts/Freddi")
    parser.add_argument("--output", type=Path, default=WORK / "datasets")
    args = parser.parse_args()
    print(json.dumps(prepare(args.speech, args.scripts, args.output)["summary"], indent=2))


if __name__ == "__main__":
    main()
