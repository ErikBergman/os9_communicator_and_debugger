#!/usr/bin/env python3
"""Losslessly extract this edition's HE TALK/SDAT speech (Python stdlib only)."""

import argparse
import hashlib
import json
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "analysis/freddi-fisk/mac-forks/25/data.fork"
DEFAULT_OUTPUT = ROOT / "analysis/freddi-fisk/voice-work/speech"
XOR_TABLE = bytes(i ^ 0x69 for i in range(256))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def chunks(data, start, end):
    """HE lengths are big endian and include the eight-byte chunk header."""
    pos = start
    while pos < end:
        if end - pos < 8:
            raise ValueError(f"Truncated chunk header at {pos}")
        tag, size = struct.unpack_from(">4sI", data, pos)
        if size < 8 or pos + size > end:
            raise ValueError(f"Invalid {tag!r} chunk size {size} at {pos}")
        yield tag, pos, size
        pos += size


def decode_archive(raw):
    if raw[:4] == b"TLKB":
        return raw, 0
    decoded = raw.translate(XOR_TABLE)
    if decoded[:4] != b"TLKB":
        raise ValueError("Expected a TLKB speech archive (plain or XOR 0x69)")
    return decoded, 0x69


def speech_records(raw):
    data, _ = decode_archive(raw)
    if len(data) < 8 or struct.unpack_from(">I", data, 4)[0] != len(data):
        raise ValueError("TLKB length does not match the archive size")
    for tag, offset, size in chunks(data, 8, len(data)):
        if tag != b"TALK":
            raise ValueError(f"Unsupported speech resource {tag!r} at {offset}")
        parts = {}
        for child_tag, pos, child_size in chunks(data, offset + 8, offset + size):
            if child_tag in parts:
                raise ValueError(f"Duplicate {child_tag!r} in TALK at {offset}")
            parts[child_tag] = data[pos + 8:pos + child_size]
        header = parts.get(b"HSHD", b"")
        if len(header) != 16 or b"SDAT" not in parts:
            raise ValueError(f"Missing/unsupported HSHD or SDAT at {offset}")
        # ScummVM HE <95 reads frequency at resource byte 22, unsigned 8-bit mono.
        rate = struct.unpack_from("<H", header, 6)[0]
        if rate not in (11000, 11025):
            raise ValueError(f"Unexpected source rate {rate} at {offset}")
        pcm = parts[b"SDAT"]
        if not pcm:
            raise ValueError(f"Empty SDAT at {offset}")
        yield {
            "offset": offset, "resource_bytes": size, "sample_rate": rate,
            "frames": len(pcm), "duration_seconds": len(pcm) / rate,
            "pcm_sha256": sha256(pcm),
        }, pcm


def extract(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    before = source.stat()
    raw = source.read_bytes()
    # Validate the whole archive before writing any outputs.
    records = list(speech_records(raw))
    _, xor_key = decode_archive(raw)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for row, pcm in records:
        name = f"speech{row['offset']}.wav"
        with wave.open(str(output / name), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(1)
            wav.setframerate(row["sample_rate"])
            wav.writeframes(pcm)
        rows.append({**row, "file": name})
    after = source.stat()
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or sha256(source.read_bytes()) != sha256(raw)):
        raise RuntimeError("Source identity changed during extraction")
    manifest = {
        "source": str(source), "source_sha256": sha256(raw),
        "source_bytes": len(raw), "source_mtime_ns": before.st_mtime_ns,
        "source_unchanged": True, "xor_key": xor_key,
        "count": len(rows),
        "total_seconds": sum(r["duration_seconds"] for r in rows),
        "format": "unsigned 8-bit PCM, mono; original samples, no resampling",
        "clips": rows,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = extract(args.source, args.output)
    print(f"Extracted {report['count']} clips, {report['total_seconds']/60:.2f} minutes")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
