#!/usr/bin/env python3
"""Build isolated, auditable Swedish FF1 voice datasets, including brief cameos."""

import collections
import hashlib
import html
import json
import re
import tempfile
import wave
from pathlib import Path

from prepare_voice_datasets import WORK, dialogue_refs as fish_refs, signed16
from prepare_shark_datasets import dialogue_refs as shark_refs

HERE = Path(__file__).resolve().parent
CUE_FILE = HERE / "cast-speaker-cues.json"
PROFILES = json.loads((HERE / "voice-profiles.json").read_text())


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def cast_refs(scripts, cues):
    refs = collections.defaultdict(list, fish_refs(scripts))
    for offset, entries in shark_refs(scripts).items():
        refs[offset].extend(entries)
    for name, expected in cues["script_sha256"].items():
        if digest(scripts / name) != expected:
            raise ValueError(f"Script checksum mismatch: {name}")
    for name, specification in cues["rooms"].items():
        lines = (scripts / name).read_text().splitlines()
        i, script = 0, None
        while i < len(lines):
            match = re.match(r"\s*script (\d+)\b", lines[i])
            if match:
                script = match[1]
            if script in specification.get("exclude_scripts", []):
                i += 1
                continue
            if not re.match(r"\s*(actor \S+|say-line)\b", lines[i]):
                i += 1
                continue
            block = [(i + 1, lines[i])]
            while lines[i].rstrip().endswith("\\") and i + 1 < len(lines) and lines[i + 1].strip():
                i += 1
                block.append((i + 1, lines[i]))
            color = None
            for number, line in block:
                match = re.match(r"\s*(?:talk-color|color) (\d+)\b", line)
                if match:
                    color = match[1]
                match = re.search(r'"@T(\d+),(\d+)@([^"\n]*)', line)
                speaker = specification["colors"].get(color)
                if match and speaker:
                    refs[int(match[1])].append({
                        "speaker": speaker, "resource_bytes": int(match[2]),
                        "original_script_text": match[3], "script": name,
                        "script_sha256": specification["sha256"],
                        "dialogue_color": int(color), "line": number})
            i += 1
    return refs


def write_wav(target, pcm, rate):
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)


def read_wav(source):
    with wave.open(str(source), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth()) != (1, 2):
            raise ValueError(f"Expected mono signed 16-bit WAV: {source}")
        return wav.readframes(wav.getnframes()), wav.getframerate()


def make_reference(dataset, speaker, rows):
    """Use only training clips. Short references repeat original audio, never TTS."""
    rows = sorted((r for r in rows if r["split"] == "train"),
                  key=lambda r: (abs(r["duration_seconds"] - 6), r["file"]))
    chunks, origins, rate, seconds = [], [], None, 0
    while seconds < 3:
        for row in rows:
            pcm, current_rate = read_wav(dataset / row["file"])
            # References use each original take once before any necessary
            # looping, rather than inheriting RVC's padded short segments.
            pcm = pcm[:round(row["duration_seconds"] * current_rate) * 2]
            if rate is not None and rate != current_rate:
                raise ValueError("Mixed source sample rates in character reference")
            rate = current_rate
            chunks.append(pcm)
            origins.append(row["offset"])
            seconds += len(pcm) / (rate * 2)
            if seconds >= 3:
                break
            chunks.append(b"\0\0" * int(rate * .12))
            seconds += .12
    target = dataset / "references" / f"{speaker}.wav"
    write_wav(target, b"".join(chunks)[:rate * 2 * 10], rate)
    return {"file": str(target.relative_to(dataset)), "offsets": origins,
            "repeated": len(origins) != len(set(origins)), "sha256": digest(target)}


def prepare(speech, scripts, output):
    speech, scripts, output = Path(speech), Path(scripts), Path(output)
    if output.exists():
        raise FileExistsError(f"Dataset already exists: {output}")
    cues = json.loads(CUE_FILE.read_text())
    source = json.loads((speech / "manifest.json").read_text())
    refs = cast_refs(scripts, cues)
    known = {row["offset"]: row for row in source["clips"]}
    if set(refs) - set(known):
        raise ValueError("Script refers to missing speech resources")
    candidates, skipped = [], collections.Counter()
    for offset, entries in refs.items():
        row = known[offset]
        if len({e["speaker"] for e in entries}) != 1:
            skipped["conflicting_speaker_cues"] += 1
            continue
        if any(e["resource_bytes"] != row["resource_bytes"] for e in entries):
            raise ValueError(f"Archive resource size mismatch at {offset}")
        speaker = entries[0]["speaker"]
        # Preserve the original four datasets' selection and held-out split.
        minimum = 1 if speaker in ("freddi", "linus", "boss", "spongehead") else .2
        if not minimum <= row["duration_seconds"] <= 10:
            skipped["duration"] += 1
            continue
        candidates.append({**row, "speaker": speaker, "evidence": entries})
    owners = collections.defaultdict(set)
    for row in candidates:
        owners[row["pcm_sha256"]].add(row["speaker"])
    selected, seen = [], set()
    counts = collections.Counter(r["speaker"] for r in candidates)
    for row in sorted(candidates, key=lambda r: r["offset"]):
        pcm_hash, speaker = row["pcm_sha256"], row["speaker"]
        if len(owners[pcm_hash]) != 1 or pcm_hash in seen:
            skipped["duplicate_or_shared_pcm"] += 1
            continue
        seen.add(pcm_hash)
        hold_out = speaker in ("freddi", "linus", "boss", "spongehead") or counts[speaker] >= 10
        split = "validation" if hold_out and int(pcm_hash[:8], 16) % 10 == 0 else "train"
        selected.append({**row, "split": split,
                         "file": f"{speaker}/{split}/{Path(row['file']).name}"})
    if set(PROFILES) - {r["speaker"] for r in selected if r["split"] == "train"}:
        raise ValueError("At least one cast role has no unambiguous training audio")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cast-building-", dir=output.parent) as tmp:
        staging = Path(tmp) / "dataset"
        staging.mkdir()
        for row in selected:
            original = speech / Path(row["file"]).name
            with wave.open(str(original), "rb") as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 1, row["sample_rate"]):
                    raise ValueError(f"Unexpected original WAV format: {original}")
                raw = wav.readframes(wav.getnframes())
            if hashlib.sha256(raw).hexdigest() != row["pcm_sha256"]:
                raise ValueError(f"Original PCM checksum mismatch: {original}")
            pcm = signed16(raw)
            # The RVC bucket sampler discards sub-second segments. Only a tiny
            # cameo needs repetition to meet that mechanical minimum; record it.
            repeats = 1
            if row["speaker"] not in ("freddi", "linus", "boss", "spongehead") and len(pcm) < row["sample_rate"] * 2 * 1.5:
                repeats = int(1.5 / row["duration_seconds"]) + 1
                pcm *= repeats
            row["training_repetitions"] = repeats
            target = staging / row["file"]
            write_wav(target, pcm, row["sample_rate"])
            row["wav_sha256"] = digest(target)
        references, summary = {}, {}
        for speaker in PROFILES:
            rows = [r for r in selected if r["speaker"] == speaker]
            references[speaker] = make_reference(staging, speaker, rows)
            summary[speaker] = {split: {
                "clips": sum(r["split"] == split for r in rows),
                "seconds": round(sum(r["duration_seconds"] for r in rows if r["split"] == split), 3)}
                for split in ("train", "validation")}
        report = {"schema": 1, "cues_sha256": digest(CUE_FILE),
                  "speech_source_sha256": source["source_sha256"], "summary": summary,
                  "notes": cues["notes"], "references": references,
                  "selection": cues["selection"], "skipped": dict(skipped), "clips": selected}
        (staging / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        cards = []
        for row in selected:
            cards.append(f'<tr><td>{html.escape(PROFILES[row["speaker"]]["name"])}</td>'
                         f'<td>{row["split"]}</td><td>{row["duration_seconds"]:.2f}s</td>'
                         f'<td>{html.escape(row["evidence"][0]["original_script_text"])}</td>'
                         f'<td><audio controls preload="none" src="{row["file"]}"></audio></td></tr>')
        (staging / "listen.html").write_text('<!doctype html><meta charset="utf-8">'
            '<title>Swedish FF1 cast recordings</title><h1>Swedish FF1 cast</h1>'
            '<p>Script-based labels; retained English descriptions, Swedish audio. '
            'Very short clips may repeat for RVC compatibility; repetition adds no new voice data.</p>'
            '<table>' + "".join(cards) + '</table>')
        staging.replace(output)
    return report


def verify(dataset):
    report = json.loads((dataset / "manifest.json").read_text())
    if report["cues_sha256"] != digest(CUE_FILE):
        raise ValueError("Speaker cues changed; preserve this dataset and use a new runtime")
    for row in report["clips"]:
        if digest(dataset / row["file"]) != row["wav_sha256"]:
            raise ValueError(f"Dataset WAV changed: {row['file']}")
    for reference in report["references"].values():
        if digest(dataset / reference["file"]) != reference["sha256"]:
            raise ValueError("Dataset reference changed")
    return report
