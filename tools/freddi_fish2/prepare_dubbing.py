#!/usr/bin/env python3
"""Catalogue every FF2 speech resource and create a Swedish dubbing worksheet."""

import argparse
import collections
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import os
import re
import struct
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path.home() / "Library/Application Support/FreddiFishVoiceStudio/work/freddi-fish-2"
EXPECTED = {
    "Freddi2.HE0": "eb3f740001c0ae08d13149366ee962c4240cb3ed2bc22873aa2917ad2a855e1f",
    "Freddi2.(a)": "c2f6a2e9ec1c2a8a706e1fb8fce5f998f7c71b4588460411b172b939b25f8c69",
    "Freddi2.HE2": "d0ad28713ac4824c24a9f94cfb822b529a990b6410a136cbe8c4079e9ae57b5a",
}
XOR = bytes(n ^ 0x69 for n in range(256))
MARKER = re.compile(rb"\x7fT(\d+),(\d+)\x7f")
SCRIPT_MARKER = re.compile(r'"\x7fT(\d+),(\d+)\x7f([^"\n]*)')
PROFILES = json.loads((HERE.parent / "freddi_fisk/voice-profiles.json").read_text())
FIELDS = ("id", "speech_offset", "rooms", "english", "english_variants", "character",
          "voice_profile", "original_seconds", "swedish", "status", "notes")
EDITABLE = ("character", "voice_profile", "swedish", "status", "notes")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    while start < end:
        if start + 8 > end:
            raise ValueError("Truncated resource header")
        tag, size = struct.unpack_from(">4sI", data, start)
        if size < 8 or start + size > end:
            raise ValueError(f"Invalid resource bounds for {tag!r}")
        yield tag, start, size
        start += size


def room_index(data):
    offsets, names = None, {}
    for tag, pos, size in chunks(data):
        body = data[pos + 8:pos + size]
        if tag == b"DLFL":
            count = int.from_bytes(body[:2], "little")
            if len(body) != 2 + 4 * count:
                raise ValueError("Invalid DLFL room-offset table")
            offsets = struct.unpack_from(f"<{count}I", body, 2)
        elif tag == b"RNAM":
            cursor = 0
            while cursor + 2 <= len(body):
                number = int.from_bytes(body[cursor:cursor + 2], "little")
                cursor += 2
                if number == 0:
                    break
                end = body.find(b"\0", cursor)
                if end < 0 or number in names:
                    raise ValueError("Invalid RNAM room names")
                names[number] = body[cursor:end].decode("ascii")
                cursor = end + 1
    if offsets is None or not names:
        raise ValueError("This index lacks DLFL/RNAM room metadata")
    return {offset: {"id": number, "name": names.get(number, f"room-{number}")}
            for number, offset in enumerate(offsets) if offset}


def clean_text(text):
    prefix = re.match(r"^\(pu\d+\)", text, re.IGNORECASE)
    return (text[prefix.end():], prefix[0]) if prefix else (text, None)


def resource_occurrences(data, base, room, parents=(), start=0, end=None):
    """Walk real chunk boundaries; never treat an arbitrary marker as a script."""
    for tag, pos, size in chunks(data, start, end):
        node = {"tag": tag.decode("ascii"), "offset": base + pos, "bytes": size}
        path = (*parents, node)
        if tag in (b"LFLF", b"RMDA", b"OBCD"):
            yield from resource_occurrences(data, base, room, path, pos + 8, pos + size)
            continue
        for match in MARKER.finditer(data, pos + 8, pos + size):
            if tag not in (b"SCRP", b"LSC2", b"VERB", b"ENCD", b"EXCD"):
                raise ValueError(f"Speech marker in unsupported resource {tag!r}")
            text_end = data.find(b"\0", match.end(), pos + size)
            if text_end < 0:
                raise ValueError("Unterminated dialogue string")
            raw_text = data[match.end():text_end].decode("ascii")
            english, prefix = clean_text(raw_text)
            yield {"speech_offset": int(match[1]), "resource_bytes": int(match[2]),
                   "marker_offset": base + match.start(), "marker_bytes": len(match[0]),
                   "text_offset": base + match.end(), "text_bytes": text_end - match.end(),
                   "raw_text": raw_text, "english": english, "prefix": prefix,
                   "room": room, "resource_path": path}


def archive_occurrences(path, rooms):
    """Read one room at a time to keep memory and CPU use low during training."""
    with path.open("rb") as stream:
        header = stream.read(8).translate(XOR)
        if header[:4] != b"LECF" or int.from_bytes(header[4:8], "big") != path.stat().st_size:
            raise ValueError("Expected the verified XOR-encoded HE99 LECF archive")
        while stream.tell() < path.stat().st_size:
            base = stream.tell()
            header = stream.read(8).translate(XOR)
            size = int.from_bytes(header[4:8], "big")
            if len(header) != 8 or header[:4] != b"LFLF" or size < 8 or base + size > path.stat().st_size:
                raise ValueError("Invalid LFLF room bounds")
            room = rooms.get(base + 8)
            if room is None:
                raise ValueError("Room boundary disagrees with the DLFL index")
            data = header + stream.read(size - 8).translate(XOR)
            yield from resource_occurrences(data, base, room)


def script_evidence(scripts):
    refs, hashes = collections.defaultdict(list), {}
    for source in sorted(scripts.glob("*.scu")):
        raw = source.read_bytes()
        hashes[source.name] = hashlib.sha256(raw).hexdigest()
        lines = raw.decode("utf-8").replace(r"\x7F", "\x7f").replace(r"\x7f", "\x7f").splitlines()
        i = 0
        while i < len(lines):
            first = i
            block = [lines[i]]
            command = re.match(r"\s*say-line(?: (\S+))?\s*\\$", lines[i])
            actor_command = re.match(r"\s*actor (\S+)\s*\\$", lines[i])
            while lines[i].rstrip().endswith("\\") and i + 1 < len(lines) and lines[i + 1].strip():
                i += 1
                block.append(lines[i])
            actor = (command[1] or "ego") if command else actor_command[1] if actor_command else None
            color = None
            for number, line in enumerate(block, first + 1):
                match = re.match(r"\s*(?:talk-color|color) (\d+)\b", line)
                if match:
                    color = match[1]
                for match in SCRIPT_MARKER.finditer(line):
                    # The pinned decompiler prints printEgo/talkEgo without an
                    # actor argument. Require Freddi's explicit colour as well.
                    # Actors in animation talkie tables may change characters.
                    speaker = {("2", "232"): "linus", ("s_selectedActor", "228"): "freddi",
                               ("ego", "228"): "freddi"}.get((actor, color)) if command else None
                    refs[int(match[1])].append({"file": source.name, "line": number,
                        "resource_bytes": int(match[2]), "speaker": speaker,
                        "command": "say-line" if command else "actor" if actor_command else "other",
                        "actor": actor, "color": int(color) if color else None})
            i += 1
    return refs, hashes


def verify_audio(path, row):
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (
                1, 1, row["sample_rate"], row["frames"]):
            raise ValueError(f"Original audio format changed: {path.name}")
        if hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest() != row["pcm_sha256"]:
            raise ValueError(f"Original audio checksum changed: {path.name}")


def worksheet_row(row):
    return {"id": row["id"], "speech_offset": str(row["speech_offset"]),
            "rooms": "; ".join(row["rooms"]), "english": row["english_variants"][0],
            "english_variants": json.dumps(row["english_variants"], ensure_ascii=False),
            "character": row["suggested_character"], "voice_profile": row["suggested_character"],
            "original_seconds": f"{row['original_seconds']:.6f}",
            "swedish": "", "status": "pending", "notes": "; ".join(row["flags"])}


def build(work, output, expected=EXPECTED):
    if output.exists():
        raise FileExistsError(f"Dubbing folder already exists; translations left untouched: {output}")
    for name, checksum in expected.items():
        if digest(work / "game" / name) != checksum:
            raise ValueError(f"Edition/source checksum mismatch: {name}")
    speech = json.loads((work / "speech/manifest.json").read_text())
    if speech["source_sha256"] != expected["Freddi2.HE2"]:
        raise ValueError("Speech manifest belongs to a different archive")
    known = {row["offset"]: row for row in speech["clips"]}
    if len(known) != len(speech["clips"]):
        raise ValueError("Duplicate speech resource offsets")
    rooms = room_index((work / "game/Freddi2.HE0").read_bytes().translate(XOR))
    references = collections.defaultdict(list)
    for occurrence in archive_occurrences(work / "game/Freddi2.(a)", rooms):
        offset = occurrence["speech_offset"]
        if offset not in known or occurrence["resource_bytes"] != known[offset]["resource_bytes"]:
            raise ValueError(f"Script/speech resource mismatch at {offset}")
        references[offset].append(occurrence)
    if set(known) != set(references):
        raise ValueError("At least one speech clip lacks a matching archive text reference")
    script_refs, script_hashes = script_evidence(work / "scripts/Freddi2")
    for offset, entries in script_refs.items():
        if offset not in known or any(e["resource_bytes"] != known[offset]["resource_bytes"] for e in entries):
            raise ValueError("Decompiler/source resource mismatch")
    rows = []
    for offset, audio in sorted(known.items()):
        if audio["file"] != f"speech{offset}.wav":
            raise ValueError("Unexpected speech filename")
        verify_audio(work / "speech" / audio["file"], audio)
        occurrences = references[offset]
        variants = list(dict.fromkeys(e["english"] for e in occurrences))
        evidence = script_refs.get(offset, [])
        candidates = {e["speaker"] for e in evidence if e["speaker"]}
        speaker = next(iter(candidates)) if len(candidates) == 1 else ""
        flags = []
        if not speaker:
            flags.append("speaker_needs_review")
        if len(variants) > 1:
            flags.append("multiple_english_texts_share_audio")
        rows.append({"id": f"ff2-{offset:08d}", "speech_offset": offset,
                     "resource_bytes": audio["resource_bytes"], "sample_rate": audio["sample_rate"],
                     "frames": audio["frames"], "pcm_sha256": audio["pcm_sha256"],
                     "audio_file": str((work / "speech" / audio["file"]).resolve()),
                     "original_seconds": audio["duration_seconds"], "english_variants": variants,
                     "rooms": sorted({f"{e['room']['id']:02d} {e['room']['name']}" for e in occurrences}),
                     "suggested_character": speaker,
                     "speaker_evidence": "explicit_actor_and_colour" if speaker else "unresolved",
                     "script_evidence": evidence, "occurrences": occurrences, "flags": flags})
    summary = {"clips": len(rows), "minutes": sum(r["original_seconds"] for r in rows) / 60,
               "archive_references": sum(len(r["occurrences"]) for r in rows),
               "decompiled_clips": len(script_refs),
               "decompiled_references": sum(map(len, script_refs.values())),
               "speaker_hints": dict(collections.Counter(r["suggested_character"] or "unresolved" for r in rows)),
               "shared_audio_text_variants": sum(len(r["english_variants"]) > 1 for r in rows)}
    catalogue = {"schema": 1, "edition": "English HE99 Updated; Swedish FF1 voices chosen for dubbing",
                 "source_language": "en", "target_language": "sv", "source_sha256": expected,
                 "script_sha256": script_hashes, "summary": summary, "clips": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dubbing-build-", dir=output.parent) as tmp:
        staging = Path(tmp) / "dubbing"
        staging.mkdir()
        (staging / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n")
        sheet = [worksheet_row(row) for row in rows]
        pilot = json.loads((HERE / "pilot-swedish.json").read_text())
        for row in sheet:
            draft = pilot.get(row["id"])
            if draft:
                if row["english"] != draft["english"] or row["character"] != draft["character"]:
                    raise ValueError("Pilot draft does not match this edition's dialogue")
                row.update(swedish=draft["swedish"], status="draft",
                           notes="Pilot draft; wording, delivery and timing need review")
        with (staging / "translations.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sheet)
        write_review(catalogue, sheet, staging / "review", link_root=output / "review")
        staging.replace(output)
    return catalogue


def read_sheet(catalogue, path):
    originals = {row["id"]: worksheet_row(row) for row in catalogue["clips"]}
    errors, seen, rows = [], set(), []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Worksheet columns changed")
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                errors.append(f"Row {number}: missing or extra CSV fields")
                continue
            identifier = row.get("id")
            if identifier in seen or identifier not in originals:
                errors.append(f"Row {number}: duplicate or unknown line ID")
                continue
            seen.add(identifier)
            for field in set(FIELDS) - set(EDITABLE):
                unchanged = row[field] == originals[identifier][field]
                if field == "original_seconds":
                    try:
                        unchanged = Decimal(row[field]) == Decimal(originals[identifier][field])
                    except InvalidOperation:
                        unchanged = False
                if not unchanged:
                    errors.append(f"{identifier}: source field {field} changed")
            if row["status"] not in ("pending", "draft", "approved"):
                errors.append(f"{identifier}: invalid status")
            if row["voice_profile"] and row["voice_profile"] not in PROFILES:
                errors.append(f"{identifier}: unknown Swedish FF1 voice profile")
            if row["status"] == "approved" and not all(row[k].strip() for k in ("swedish", "character", "voice_profile")):
                errors.append(f"{identifier}: approval requires Swedish text, character and voice")
            if any(ord(c) < 32 for c in row["swedish"]):
                errors.append(f"{identifier}: Swedish text must be one plain sentence/line")
            rows.append(row)
    if seen != set(originals):
        errors.append("Worksheet is missing original line IDs")
    if errors:
        raise ValueError("\n".join(errors))
    return rows


def write_review(catalogue, sheet, output, link_root=None):
    output.mkdir(parents=True, exist_ok=True)
    edits = {row["id"]: row for row in sheet}
    pages = collections.defaultdict(list)
    escape = lambda value: html.escape(str(value), quote=True)
    style = '<meta charset="utf-8"><style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:1em}article{border-top:1px solid #ccc;padding:1em 0}small{color:#555}audio{display:block;margin:.5em 0}li{margin:.5em 0}</style>'
    for row in catalogue["clips"]:
        for room in row["rooms"]:
            pages[room].append(row)
    links = []
    for room, clips in sorted(pages.items()):
        filename = f"room-{room.split()[0]}.html"
        links.append(f'<li><a href="{filename}">{escape(room)}</a> · {len(clips)} clips</li>')
        cards = []
        for row in clips:
            edit = edits[row["id"]]
            audio = os.path.relpath(row["audio_file"], (link_root or output).resolve())
            cards.append(f'<article><strong>{escape(row["id"])} · {escape(edit["character"] or "Speaker unresolved")}</strong>'
                f'<small> · {row["original_seconds"]:.2f}s · {escape(edit["status"])}</small>'
                f'<p>{escape(" / ".join(row["english_variants"]))}</p>'
                f'<p lang="sv">{escape(edit["swedish"] or "Swedish translation pending")}</p>'
                f'<audio controls preload="none" src="{escape(audio)}"></audio>'
                f'<small>Swedish voice: {escape(edit["voice_profile"] or "not cast")} · {escape(edit["notes"])}</small></article>')
        (output / filename).write_text('<!doctype html>' + style + '<a href="index.html">All rooms</a>'
            f'<h1>{escape(room)}</h1>' + "".join(cards), encoding="utf-8")
    (output / "index.html").write_text('<!doctype html>' + style + '<title>Freddi Fish 2 dubbing review</title>'
        '<h1>Freddi Fish 2 · Swedish dubbing preparation</h1>'
        '<p>Original English recordings; Swedish text is a draft until approved in translations.csv. '
        'Rooms are archive storage locations, not guaranteed playback order. Speaker hints still need review.</p>'
        f'<p>{catalogue["summary"]["clips"]} clips · {catalogue["summary"]["minutes"]:.2f} minutes. '
        'This work does not modify game files or use the voice trainer.</p><ul>' + "".join(links) + '</ul>', encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("build", "validate", "review"), default="build")
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    work = args.work.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else work / "dubbing"
    try:
        if args.action == "build":
            catalogue = build(work, output)
        else:
            catalogue = json.loads((output / "catalogue.json").read_text())
            rows = read_sheet(catalogue, output / "translations.csv")
            if args.action == "review":
                write_review(catalogue, rows, output / "review")
            print(json.dumps({"translation_status": dict(collections.Counter(row["status"] for row in rows))}, indent=2))
        print(json.dumps(catalogue["summary"], indent=2))
        print(f"Worksheet: {output / 'translations.csv'}\nListening review: {output / 'review/index.html'}")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Dubbing preparation stopped: {error}\n")


if __name__ == "__main__":
    main()
