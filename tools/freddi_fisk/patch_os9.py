#!/usr/bin/env python3
"""Build an experimental, fork-preserving OS 9 repair for this exact Freddi edition."""
import argparse
import binascii
import datetime
import hashlib
import json
from pathlib import Path
import struct

REPO = Path(__file__).resolve().parents[2]
DATA_SHA256 = "aa981103cd36cd9598da22d9ca1e3eca6ad59147dd5a9e7cc449e6a9d665a960"
RESOURCE_SHA256 = "11afcc615d7d3287a9dc9d65b42581c121f854c2ca4106d59792c315b14dcbf2"
FINDER_SHA256 = "14893f3c718482f98aa0b19afbd0f3e54e22c365a3031512bca89e6309c0f25a"
TEXT_OFFSET = 152
START = 0x5B2C
END = 0x5C80
BASE = 0x10000000


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class PowerPC:
    """Small checked encoder for the instructions used in the replacement only."""
    def __init__(self):
        self.words, self.labels, self.fixups = [], {}, []

    def emit(self, word):
        self.words.append(word)

    def d(self, opcode, reg, base, immediate):
        if not -32768 <= immediate <= 65535:
            raise ValueError("D-form immediate out of range")
        self.emit(opcode << 26 | reg << 21 | base << 16 | (immediate & 0xFFFF))

    def label(self, name):
        self.labels[name] = START + 4 * len(self.words)

    def branch(self, target, *, link=False, condition=None):
        offset = len(self.words)
        self.fixups.append((offset, target, link, condition))
        self.emit(0)

    def finish(self):
        for index, target, link, condition in self.fixups:
            target = self.labels[target] if isinstance(target, str) else target
            displacement = target - (START + index * 4)
            if displacement % 4:
                raise ValueError("Unaligned branch")
            if condition is None:
                if not -(1 << 25) <= displacement < (1 << 25):
                    raise ValueError("Branch out of range")
                self.words[index] = 0x48000000 | (displacement & 0x3FFFFFC) | int(link)
            else:
                if not -32768 <= displacement <= 32764:
                    raise ValueError("Conditional branch out of range")
                bo, bi = {"eq": (12, 2), "ne": (4, 2), "dnz": (16, 0)}[condition]
                self.words[index] = 0x40000000 | bo << 21 | bi << 16 | (displacement & 0xFFFC)
        code = b"".join(struct.pack(">I", w) for w in self.words)
        if len(code) > END - START:
            raise ValueError("Replacement exceeds the original routine")
        return code + struct.pack(">I", 0x60000000) * ((END - START - len(code)) // 4)


def replacement():
    p = PowerPC()
    # Original ABI/frame: r28-r31 saved; 0x198-byte frame; caller TOC at sp+20.
    # PB at sp+0x38. FCBPBRec is 62 bytes, packed to 2-byte alignment:
    # ioRefNum +24, ioFCBIndx +28, ioFCBVRefNum +52, ioFCBParID +58.
    # Filename buffer at sp+0xb8 is separate from the 122-byte HVolumeParam.
    p.emit(0x7C0802A6)                  # mflr r0
    p.d(47, 28, 1, -16)                # stmw r28,-16(sp)
    p.d(36, 0, 1, 8)                   # stw r0,8(sp)
    p.d(14, 29, 3, 0)                  # mr r29,r3 (file object)
    p.d(37, 1, 1, -0x198)              # stwu sp,-0x198(sp)
    p.d(14, 0, 0, 0)
    p.d(14, 4, 1, 0x38)
    p.d(14, 5, 0, 16)
    p.emit(0x7CA903A6)                  # mtctr r5
    p.label("clear_pb")
    p.d(36, 0, 4, 0)
    p.d(14, 4, 4, 4)
    p.branch("clear_pb", condition="dnz")
    p.d(14, 3, 1, 0xB8)
    p.d(36, 3, 1, 0x4A)                # ioNamePtr
    p.d(42, 3, 29, 6)                  # file object's refNum
    p.d(44, 3, 1, 0x50)                # ioRefNum
    p.d(14, 3, 1, 0x38)
    p.branch(0xDC8, link=True)          # PBGetFCBInfoSync; ioFCBIndx=0
    p.d(32, 2, 1, 20)                  # restore game TOC after CFM call
    p.d(11, 0, 3, 0)                   # cmpwi r3,0
    p.branch("done", condition="ne")
    p.d(42, 28, 1, 0x6C)               # ioFCBVRefNum (PB+52)
    p.d(32, 31, 1, 0x72)               # ioFCBParID (PB+58)
    p.d(14, 30, 0, 0)                  # 0=close only, 1=MFS delete, 2=HFS delete
    p.d(14, 0, 0, 0)
    p.d(36, 0, 1, 0x4A)                # no name for volume lookup
    p.d(44, 28, 1, 0x4E)               # ioVRefNum
    p.d(34, 3, 29, 0)                  # file object's high flags byte
    p.d(28, 3, 3, 1)                   # andi. r3,r3,1 (temporary file)
    p.branch("close", condition="eq")
    p.d(44, 0, 1, 0x54)                # ioVolIndex=0: query specified volume
    p.d(14, 3, 1, 0x38)
    p.branch(0x1938, link=True)         # PBHGetVInfoSync
    p.d(32, 2, 1, 20)
    p.d(11, 0, 3, 0)
    p.branch("done", condition="ne")
    p.d(40, 3, 1, 0x78)                # HVolumeParam.ioVSigWord (PB+64)
    p.d(10, 0, 3, 0x4244)              # HFS signature ('BD'; also HFS+ via this API)
    p.branch("hfs", condition="eq")
    p.d(10, 0, 3, 0xD2D7)              # MFS signature
    p.branch("close", condition="ne")
    p.d(14, 30, 0, 1)
    p.branch("delete_name")
    p.label("hfs")
    p.d(14, 30, 0, 2)
    p.label("delete_name")
    p.d(14, 3, 1, 0xB8)
    p.d(36, 3, 1, 0x4A)
    p.d(36, 31, 1, 0x68)               # HFileParam.ioDirID (PB+48)
    p.d(14, 0, 0, 0)
    p.d(38, 0, 1, 0x52)                # ioVersNum=0
    p.label("close")
    p.d(44, 28, 1, 0x4E)
    p.d(42, 3, 29, 6)
    p.d(44, 3, 1, 0x50)
    p.d(14, 3, 1, 0x38)
    p.branch(0xC90, link=True)          # PBCloseSync
    p.d(32, 2, 1, 20)
    p.d(11, 0, 3, 0)
    p.branch("done", condition="ne")
    p.d(11, 0, 30, 0)
    p.branch("flush", condition="eq")
    p.d(11, 0, 30, 1)
    p.branch("hdelete", condition="ne")
    p.d(14, 3, 1, 0x38)
    p.branch(0xBD0, link=True)          # PBDeleteSync (MFS)
    p.d(32, 2, 1, 20)
    p.branch("flush")
    p.label("hdelete")
    p.d(14, 3, 1, 0x38)
    p.branch(0xCA8, link=True)          # PBHDeleteSync (HFS)
    p.d(32, 2, 1, 20)
    p.label("flush")
    p.d(14, 0, 0, 0)
    p.d(36, 0, 1, 0x4A)                # flush by volume ref, not by filename
    p.d(14, 3, 1, 0x38)
    p.branch(0xCC0, link=True)          # PBFlushVolSync
    p.d(32, 2, 1, 20)
    p.label("done")
    p.d(42, 3, 1, 0x48)                # propagate final ioResult, as original
    p.d(14, 1, 1, 0x198)
    p.d(46, 28, 1, -16)                # lmw r28,-16(sp)
    p.d(32, 0, 1, 8)
    p.emit(0x7C0803A6)                  # mtlr r0
    p.emit(0x4E800020)                  # blr
    return p.finish()


def patch_data(data):
    if sha256(data) != DATA_SHA256:
        raise ValueError("Executable checksum differs from the inspected edition; refusing to patch")
    code = replacement()
    result = data[:TEXT_OFFSET + START] + code + data[TEXT_OFFSET + END:]
    assert len(result) == len(data)
    assert result[:TEXT_OFFSET + START] == data[:TEXT_OFFSET + START]
    assert result[TEXT_OFFSET + END:] == data[TEXT_OFFSET + END:]
    return result


def macbinary(data, resource, finder, metadata):
    """MacBinary II: two independently padded forks, type/creator and header CRC."""
    header = bytearray(128)
    name = b"Freddi Fisk"             # keep the name expected by the game
    header[1] = len(name)
    header[2:2 + len(name)] = name
    header[65:73] = finder[:8]
    header[73] = finder[8]
    header[101] = finder[9]
    header[75:81] = finder[10:16]
    struct.pack_into(">II", header, 83, len(data), len(resource))
    epoch = datetime.datetime(1904, 1, 1, tzinfo=datetime.timezone.utc)
    for offset, key in ((91, "created_utc"), (95, "modified_utc")):
        value = datetime.datetime.fromisoformat(metadata[key])
        struct.pack_into(">I", header, offset, int((value - epoch).total_seconds()))
    header[122:124] = bytes((129, 129))
    struct.pack_into(">H", header, 124, binascii.crc_hqx(header[:124], 0))
    return bytes(header) + data + bytes(-len(data) % 128) + resource + bytes(-len(resource) % 128)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forks", type=Path, default=REPO / "analysis/freddi-fisk/mac-forks/22")
    parser.add_argument("--output", type=Path, default=REPO / "analysis/freddi-fisk/patches/os9-fcb-v1")
    args = parser.parse_args()
    source = args.forks.resolve()
    files = {name: (source / name).read_bytes() for name in
             ("data.fork", "resource.fork", "finder-info.bin", "metadata.json")}
    for name, expected in (("data.fork", DATA_SHA256), ("resource.fork", RESOURCE_SHA256),
                           ("finder-info.bin", FINDER_SHA256)):
        if sha256(files[name]) != expected:
            parser.error(f"{name} does not match the preserved edition")
    metadata = json.loads(files["metadata.json"])
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory is not empty; choose a new directory")
    patched = patch_data(files["data.fork"])
    archive = macbinary(patched, files["resource.fork"], files["finder-info.bin"], metadata)
    output.mkdir(parents=True, exist_ok=True)
    (output / "patched-data.fork").write_bytes(patched)
    (output / "Freddi-Fisk-OS9-test.bin").write_bytes(archive)
    report = {
        "status": "experimental; physical Mac OS 9 validation required",
        "original_data_sha256": DATA_SHA256,
        "patched_data_sha256": sha256(patched),
        "resource_sha256": RESOURCE_SHA256,
        "finder_info_sha256": FINDER_SHA256,
        "archive_sha256": sha256(archive), "archive_bytes": len(archive),
        "text_section_file_offset": TEXT_OFFSET,
        "routine_section_offset": f"0x{START:x}", "routine_bytes": END - START,
        "ghidra_address": f"0x{BASE + START:x}",
        "changed_bytes": sum(a != b for a, b in zip(files["data.fork"], patched)),
        "source_files_unchanged": all((source / n).read_bytes() == v for n, v in files.items()),
        "resource_fork_unchanged": True,
        "imports_and_relocations_unchanged": True,
        "cpu": "PowerPC only; 68k CODE resources unchanged",
    }
    if not report["source_files_unchanged"]:
        raise RuntimeError("Source changed while building")
    (output / "patch-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
