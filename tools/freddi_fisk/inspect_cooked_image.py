#!/usr/bin/env python3
"""Inventory a 2048-byte-sector ISO/hybrid CD without mounting or modifying it."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import struct

from inspect_freddi_image import file_sha, hfs_inventory, iso_inventory, json_write, sha


def partitions(image):
    if image[512:514] != b"PM":
        return []
    count = int.from_bytes(image[516:520], "big")
    if not 1 <= count <= min(4096, len(image) // 512 - 1):
        raise ValueError("Invalid Apple partition count")
    result = []
    for number in range(1, count + 1):
        entry = image[number * 512:(number + 1) * 512]
        if entry[:2] != b"PM" or int.from_bytes(entry[4:8], "big") != count:
            raise ValueError("Invalid Apple partition entry")
        start, blocks = struct.unpack_from(">LL", entry, 8)
        if (start + blocks) * 512 > len(image):
            raise ValueError("Apple partition extends beyond the image")
        result.append({"start_block_512": start, "blocks_512": blocks,
                       "name": entry[16:48].split(b"\0")[0].decode("mac_roman"),
                       "type": entry[48:80].split(b"\0")[0].decode("ascii")})
    return result


def inspect(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Inspection output already exists; left untouched: {output}")
    before = source.stat()
    image = source.read_bytes()
    if len(image) % 2048:
        raise ValueError("Expected complete 2048-byte sectors")
    iso = iso_inventory(image)
    apple_partitions = partitions(image)
    hfs_partitions = [part for part in apple_partitions if part["type"] == "Apple_HFS"]
    if len(hfs_partitions) > 1:
        raise ValueError("Multiple HFS partitions require explicit selection")
    output.mkdir(parents=True)
    hfs = None
    if hfs_partitions:
        part = hfs_partitions[0]
        start, size = part["start_block_512"] * 512, part["blocks_512"] * 512
        hfs = hfs_inventory(image[start:start + size], output)
    after = source.stat()
    checksum = sha(image)
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or file_sha(source) != checksum):
        raise RuntimeError("Source image changed during inspection")
    report = {"inspected_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"path": str(source), "bytes": before.st_size, "sha256": checksum,
                         "unchanged_after_inspection": True, "opened_read_only": True},
              "format": "ISO 9660, 2048-byte sectors; optional Apple HFS partition",
              "apple_partitions": apple_partitions, "hfs": hfs, "iso9660": iso,
              "limitations": ["No filesystem repair or game execution performed",
                              "Preserved fork pairs are not native dual-fork Macintosh files"]}
    json_write(output / "inventory.json", report)
    (output / "checksums.sha256").write_text(f"{checksum}  {source}\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = inspect(args.image, args.output)
    print(f"Original unchanged: True; SHA-256: {report['source']['sha256']}")
    print(f"ISO 9660 volume: {report['iso9660']['volume_name']}")
    for entry in report["iso9660"]["entries"]:
        if entry["kind"] == "file":
            print(entry["path"], entry["bytes"])
    if report["hfs"]:
        print(f"HFS volume: {report['hfs']['name']}")
        for entry in report["hfs"]["files"]:
            print(entry["display_path"], entry["data_bytes"], entry["resource_bytes"])


if __name__ == "__main__":
    main()
