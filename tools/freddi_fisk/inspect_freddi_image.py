#!/usr/bin/env python3
"""Read a raw Mode 1 hybrid CD; inventory and preserve HFS forks separately.

Requires machfs==1.3 and macresources==1.2. Never mounts or writes the source.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct



def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mac_date(seconds):
    return datetime.fromtimestamp(seconds - 2082844800, timezone.utc).isoformat() if seconds else None


def hfs_inventory(volume, output):
    from machfs import btree
    from macresources import parse_file

    if volume[1024:1026] != b"BD":
        raise ValueError("Expected an HFS master directory block")
    fields = struct.unpack_from(">2sLLHHHHHLLHLH28pLHLLLHLL32sHHHL12sL12s", volume, 1024)
    (_, created, modified, attributes, _, _, _, alloc_count, alloc_size, _, alloc_start,
     _, free_blocks, name, _, _, _, _, _, _, file_count, dir_count, finder,
     _, _, _, ext_size, ext_first, cat_size, cat_first) = fields
    volume_name, volume_finder = name.decode("mac_roman"), finder.hex()
    overflow = {}

    def fork(size, first, cnid, kind):
        extents = btree.unpack_extent_record(first)
        blocks = sum(count for _, count in extents)
        while blocks * alloc_size < size:
            extra = btree.unpack_extent_record(overflow[cnid, kind, blocks])
            if not extra:
                raise ValueError("Empty overflow extent")
            extents += extra
            blocks += sum(count for _, count in extra)
        pieces = []
        for start, count in extents:
            if start + count > alloc_count:
                raise ValueError("Extent outside HFS allocation area")
            offset = 512 * alloc_start + alloc_size * start
            part = volume[offset:offset + alloc_size * count]
            if len(part) != alloc_size * count:
                raise ValueError("Truncated HFS extent")
            pieces.append(part)
        data = b"".join(pieces)[:size]
        if len(data) != size:
            raise ValueError("Fork shorter than its catalog length")
        return data

    for rec in btree.dump_btree(fork(ext_size, ext_first, 3, "data")):
        if rec[0] == 7:
            flag, cnid, start, extents = struct.unpack_from(">xBLH12s", rec)
            overflow[cnid, "rsrc" if flag == 255 else "data", start] = extents
    catalog = fork(cat_size, cat_first, 4, "data")
    (output / "hfs-catalog.bin").write_bytes(catalog)
    (output / "hfs-master-directory-block.bin").write_bytes(volume[1024:1536])
    directories = {}
    records = []
    for rec in btree.dump_btree(catalog):
        key_size = rec[0]
        if not key_size:
            continue
        key = rec[2:1 + key_size]
        value = rec[(1 + key_size + 1) & ~1:]
        parent, name_len = struct.unpack_from(">LB", key)
        name = key[5:5 + name_len].decode("mac_roman")
        kind, data = value[0], value[2:]
        if kind == 1:
            _, _, cnid, cr, md, bk, user, find = struct.unpack_from(">HHLLLL16s16s", data)
            directories[cnid] = {"cnid": cnid, "parent_cnid": parent, "name": name,
                                 "finder_info_hex": (user + find).hex(), "raw_catalog_record_hex": rec.hex()}
        elif kind == 2:
            fields = struct.unpack_from(">BB16sLHLLHLLLLL16sH12s12sxxxx", data)
            (flags, _, user, cnid, _, data_len, _, _, rsrc_len, _, cr, md, bk,
             find, _, data_ext, rsrc_ext) = fields
            records.append((name, parent, cnid, flags, user, find, cr, md, bk,
                            fork(data_len, data_ext, cnid, "data"),
                            fork(rsrc_len, rsrc_ext, cnid, "rsrc"), rec))

    def parent_path(cnid):
        if cnid == 2:
            return []
        directory = directories[cnid]
        return parent_path(directory["parent_cnid"]) + [directory["name"]]

    files = []
    for name, parent, cnid, flags, user, finder, cr, md, bk, data, rsrc, rec in records:
        path = parent_path(parent) + [name]
        folder = output / "mac-forks" / str(cnid)
        folder.mkdir(parents=True, exist_ok=True)
        for filename, payload in (("data.fork", data), ("resource.fork", rsrc),
                                  ("finder-info.bin", user + finder), ("catalog-record.bin", rec)):
            target = folder / filename
            target.write_bytes(payload)
            if file_sha(target) != sha(payload):
                raise ValueError("Preservation copy verification failed")
        resources = [{"type": r.type.decode("mac_roman"), "id": r.id, "name": r.name,
                      "attributes": r.attribs, "bytes": len(r.data), "sha256": sha(r.data)}
                     for r in parse_file(rsrc)]
        entry = {"path_components": path, "display_path": "/".join(path), "cnid": cnid,
                 "type": user[:4].decode("mac_roman"), "creator": user[4:8].decode("mac_roman"),
                 "type_hex": user[:4].hex(), "creator_hex": user[4:8].hex(),
                 "finder_info_hex": (user + finder).hex(), "catalog_flags": flags,
                 "created_utc": mac_date(cr), "modified_utc": mac_date(md), "backup_utc": mac_date(bk),
                 "data_bytes": len(data), "resource_bytes": len(rsrc),
                 "data_sha256": sha(data), "resource_sha256": sha(rsrc),
                 "data_header_hex": data[:40].hex(),
                 "pef_architecture": data[8:12].decode("ascii") if data.startswith(b"Joy!peff") else None,
                 "resource_type_counts": dict(sorted(Counter(r["type"] for r in resources).items())),
                 "resources": resources, "preserved_forks_directory": str(folder.relative_to(output))}
        json_write(folder / "metadata.json", entry)
        files.append(entry)
    if len(files) != file_count or len(directories) - 1 != dir_count:
        raise ValueError("Inventory count does not match the HFS master directory block")
    return {"name": volume_name, "created_utc": mac_date(created),
            "modified_utc": mac_date(modified), "attributes_hex": f"{attributes:04x}",
            "allocation_block_bytes": alloc_size, "allocation_blocks": alloc_count,
            "free_allocation_blocks": free_blocks, "finder_info_hex": volume_finder,
            "file_count": file_count, "directory_count_excluding_root": dir_count,
            "directories": list(directories.values()), "files": sorted(files, key=lambda x: x["display_path"])}


def iso_inventory(image):
    descriptor = image[16 * 2048:17 * 2048]
    if descriptor[:7] != b"\x01CD001\x01":
        raise ValueError("Expected ISO 9660 primary volume descriptor")
    block_size = int.from_bytes(descriptor[128:130], "little")
    entries, visited = [], set()

    def record(buf):
        return (int.from_bytes(buf[2:6], "little"), int.from_bytes(buf[10:14], "little"),
                buf[25], buf[33:33 + buf[32]])

    def visit(block, length, prefix):
        if block in visited:
            raise ValueError("Repeated ISO directory extent")
        visited.add(block)
        data = image[block * block_size:block * block_size + length]
        offset = 0
        while offset < len(data):
            size = data[offset]
            if not size:
                offset = (offset // block_size + 1) * block_size
                continue
            child = data[offset:offset + size]
            extent, size_bytes, flags, raw_name = record(child)
            offset += size
            if raw_name in (b"\0", b"\1"):
                continue
            if flags & 128:
                raise ValueError("ISO multi-extent file requires additional handling")
            name = raw_name.decode("ascii").split(";")[0]
            path = prefix + [name]
            content = image[extent * block_size:extent * block_size + size_bytes]
            if len(content) != size_bytes:
                raise ValueError("ISO extent outside image")
            directory = bool(flags & 2)
            entries.append({"path": "/".join(path), "kind": "directory" if directory else "file",
                            "bytes": size_bytes, "extent_block": extent,
                            "sha256": None if directory else sha(content)})
            if directory:
                visit(extent, size_bytes, path)
    block, length, _, _ = record(descriptor[156:])
    visit(block, length, [])
    return {"volume_name": descriptor[40:72].decode("ascii").strip(),
            "logical_block_bytes": block_size,
            "declared_volume_bytes": int.from_bytes(descriptor[80:84], "little") * block_size,
            "publisher": descriptor[318:446].decode("ascii").strip(),
            "entries": sorted(entries, key=lambda e: e["path"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, output = args.image.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    raw_hash, payload_hash = hashlib.sha256(), hashlib.sha256()
    payload = bytearray()
    sectors = 0
    with source.open("rb") as stream:
        while block := stream.read(2352):
            if len(block) != 2352 or block[:12] != b"\0" + b"\xff" * 10 + b"\0" or block[15] != 1:
                raise ValueError(f"Invalid Mode 1 sector {sectors}")
            raw_hash.update(block)
            data = block[16:2064]
            payload_hash.update(data)
            payload.extend(data)
            sectors += 1
    payload = bytes(payload)
    cooked = output / "freddi-mode1-payload.iso"
    if cooked.exists():
        if file_sha(cooked) != payload_hash.hexdigest():
            raise ValueError("Existing derivative does not match sector payloads")
    else:
        cooked.write_bytes(payload)
    partitions = []
    count = int.from_bytes(payload[516:520], "big")
    for i in range(1, count + 1):
        entry = payload[512 * i:512 * (i + 1)]
        if entry[:2] != b"PM":
            raise ValueError("Invalid Apple partition entry")
        start, blocks = struct.unpack_from(">LL", entry, 8)
        partitions.append({"start_block_512": start, "blocks_512": blocks,
                           "name": entry[16:48].split(b"\0")[0].decode("mac_roman"),
                           "type": entry[48:80].split(b"\0")[0].decode("ascii")})
    part = next(p for p in partitions if p["type"] == "Apple_HFS")
    start, size = part["start_block_512"] * 512, part["blocks_512"] * 512
    hfs = hfs_inventory(payload[start:start + size], output)
    iso = iso_inventory(payload)
    after_hash = file_sha(source)
    after = source.stat()
    unchanged = raw_hash.hexdigest() == after_hash and before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
    if not unchanged:
        raise ValueError("Source image changed during inspection")
    report = {"inspected_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"path": str(source), "bytes": before.st_size, "sha256": after_hash,
                         "unchanged_after_inspection": unchanged, "opened_read_only": True},
              "format": "Raw CD-ROM Mode 1: 2352-byte sectors with 2048-byte payloads",
              "sector_count": sectors, "all_sector_sync_and_mode_headers_valid": True,
              "derivative": {"path": cooked.name, "bytes": len(payload), "sha256": payload_hash.hexdigest(),
                             "omits": "Per-sector sync/header/EDC/ECC; original retained intact"},
              "apple_partitions": partitions, "hfs": hfs, "iso9660": iso,
              "limitations": ["No EDC/ECC validation or comparison with another known-good disc",
                              "No filesystem repair, game execution, or crash diagnosis performed",
                              "Exported data.fork/resource.fork pairs are preservation artifacts, not native Mac files"]}
    json_write(output / "inventory.json", report)
    (output / "checksums.sha256").write_text(f"{after_hash}  {source}\n{payload_hash.hexdigest()}  {cooked.name}\n", encoding="utf-8")
    print(f"Original unchanged: {unchanged}; SHA-256: {after_hash}")
    print(f"HFS volume {hfs['name']}: {len(hfs['files'])} files")
    print(f"ISO 9660: {sum(e['kind'] == 'file' for e in iso['entries'])} files")
    for file in hfs["files"]:
        print(repr(file["display_path"]), file["type"], file["data_bytes"], file["resource_bytes"], file["pef_architecture"], file["resource_type_counts"])


if __name__ == "__main__":
    main()
