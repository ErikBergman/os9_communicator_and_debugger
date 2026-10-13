#!/usr/bin/env python3
"""Execute original/repaired PowerPC close routines with mocked Classic Mac APIs.

This validates machine code, ABI and File Manager arguments, not real OS 9.
Dependencies: capstone==5.0.7, unicorn==2.1.4 (install into an isolated directory).
"""
import argparse
import binascii
import io
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn import ppc_const as regs

import patch_os9 as patch

API = {0xC78: "LMGetFCBSPtr", 0xDC8: "PBGetFCBInfoSync", 0x1938: "PBHGetVInfoSync",
       0xBB8: "PBGetFInfoSync", 0xC90: "PBCloseSync", 0xBD0: "PBDeleteSync",
       0xCA8: "PBHDeleteSync", 0xCC0: "PBFlushVolSync", 0x66E8: "memcpy"}
STACK, SP, OBJ, FCB, VCB = 0x30000000, 0x30010000, 0x31000000, 0x32000000, 0x33000000
RETURN = 0x10058000
TOC, REF, VREF, PARENT = 0x20008000, 0x1BE, -2, 0x12345678
# A non-ASCII Pascal filename exercises byte preservation.
NAME = bytes((len(b"Speed\x8etest.tmp"),)) + b"Speed\x8etest.tmp"


def execute(data, *, temporary=False, signature=0x4244, errors=None, os9=False):
    errors = errors or {}
    uc = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
    uc.mem_map(patch.BASE, 0x60000)
    uc.mem_write(patch.BASE, data[patch.TEXT_OFFSET:patch.TEXT_OFFSET + 344416])
    for address, size in ((STACK, 0x20000), (OBJ, 0x10000), (FCB, 0x10000), (VCB, 0x10000)):
        uc.mem_map(address, size)
        uc.mem_write(address, bytes((0xA5,)) * size)

    def read(address, fmt):
        return struct.unpack(fmt, bytes(uc.mem_read(address, struct.calcsize(fmt))))[0]

    def write(address, fmt, value):
        uc.mem_write(address, struct.pack(fmt, value))

    def reg(n):
        return uc.reg_read(getattr(regs, f"UC_PPC_REG_{n}"))

    def setreg(n, value):
        uc.reg_write(getattr(regs, f"UC_PPC_REG_{n}"), value & 0xFFFFFFFF)

    write(OBJ, ">I", 0x01000000 if temporary else 0)
    write(OBJ + 6, ">h", REF)
    write(FCB + REF + 20, ">I", VCB)
    write(FCB + REF + 58, ">I", PARENT)
    uc.mem_write(FCB + REF + 62, NAME)
    write(VCB + 8, ">H", signature)
    write(VCB + 78, ">h", VREF)
    for n in range(32):
        setreg(n, 0x50000000 + n * 0x100)
    setreg(1, SP)
    setreg(2, TOC)
    setreg(3, OBJ)
    uc.reg_write(regs.UC_PPC_REG_LR, RETURN)
    saved = {n: reg(n) for n in range(13, 32)}
    calls, mutation_calls, failure = [], [], None

    def hook(emu, address, size, unused):
        nonlocal failure
        offset = address - patch.BASE
        if offset not in API:
            return
        name = API[offset]
        calls.append(name)
        pb = reg(3)
        if name == "LMGetFCBSPtr":
            if os9:
                failure = "dsMustUseFCBAccessors:119"
                emu.emu_stop()
                return
            result = FCB
        elif name == "memcpy":
            emu.mem_write(pb, bytes(emu.mem_read(reg(4), reg(5))))
            emu.reg_write(regs.UC_PPC_REG_PC, emu.reg_read(regs.UC_PPC_REG_LR))
            return
        else:
            result = errors.get(name, 0)
            if name == "PBGetFCBInfoSync":
                assert read(pb + 24, ">h") == REF
                assert read(pb + 28, ">h") == 0
                assert read(pb + 12, ">I") == 0
                if not result:
                    write(pb + 52, ">h", VREF)
                    write(pb + 58, ">I", PARENT)
                    emu.mem_write(read(pb + 18, ">I"), NAME)
            elif name == "PBHGetVInfoSync":
                assert read(pb + 22, ">h") == VREF
                assert read(pb + 28, ">h") == 0
                assert read(pb + 18, ">I") == 0
                # Volume output overlaps FCB output. Filename/parent must survive separately.
                emu.mem_write(pb + 30, bytes((0x5A,)) * 92)
                write(pb + 64, ">H", signature)
            elif name == "PBGetFInfoSync":
                assert read(pb + 22, ">h") == VREF
                write(pb + 24, ">h", REF)
                emu.mem_write(read(pb + 18, ">I"), NAME)
            elif name == "PBCloseSync":
                assert read(pb + 24, ">h") == REF
                mutation_calls.append({"api": name, "ref": REF})
            elif name in ("PBDeleteSync", "PBHDeleteSync"):
                name_ptr = read(pb + 18, ">I")
                length = read(name_ptr, ">B")
                filename = bytes(emu.mem_read(name_ptr, length + 1))
                assert filename == NAME
                assert read(pb + 22, ">h") == VREF
                assert read(pb + 26, ">B") == 0
                item = {"api": name, "volume": VREF, "name_hex": filename.hex()}
                if name == "PBHDeleteSync":
                    assert read(pb + 48, ">I") == PARENT
                    item["parent"] = PARENT
                mutation_calls.append(item)
            elif name == "PBFlushVolSync":
                assert read(pb + 22, ">h") == VREF
                assert read(pb + 18, ">I") == 0
                mutation_calls.append({"api": name, "volume": VREF})
            write(pb + 16, ">h", result)
        # Model the CFM import glue and hostile legal clobbers of volatile registers.
        write(reg(1) + 20, ">I", reg(2))
        for n in (0, *range(2, 13)):
            setreg(n, 0x60000000 + n * 0x100)
        setreg(3, result)
        emu.reg_write(regs.UC_PPC_REG_PC, emu.reg_read(regs.UC_PPC_REG_LR))

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(patch.BASE + patch.START, RETURN, count=2000)
    if failure:
        return {"failure": failure, "calls": calls}
    assert uc.reg_read(regs.UC_PPC_REG_PC) == RETURN, "Routine did not return"
    assert reg(1) == SP, "Stack pointer changed"
    assert reg(2) == TOC, "Game TOC was not restored"
    assert {n: reg(n) for n in saved} == saved, "Nonvolatile register corrupted"
    result = reg(3)
    if result & 0x80000000:
        result -= 1 << 32
    return {"result": result, "calls": calls, "mutations": mutation_calls, "abi_preserved": True}


def check_archive(archive, expected_data, expected_resource, finder):
    header = archive[:128]
    assert binascii.crc_hqx(header[:124], 0) == struct.unpack_from(">H", header, 124)[0]
    assert header[0] == header[74] == header[82] == 0
    assert header[122:124] == b"\x81\x81"
    assert header[2:2 + header[1]] == b"Freddi Fisk"
    assert header[65:73] == finder[:8] == b"APPLHeFF"
    assert bytes((header[73], header[101])) == finder[8:10]
    data_size, rsrc_size = struct.unpack_from(">II", header, 83)
    assert data_size == len(expected_data) and rsrc_size == len(expected_resource)
    resource_start = 128 + ((data_size + 127) // 128) * 128
    assert archive[128:128 + data_size] == expected_data
    assert archive[resource_start:resource_start + rsrc_size] == expected_resource
    assert len(archive) == resource_start + ((rsrc_size + 127) // 128) * 128


def verify_import_mapping(original):
    """Independently map the edition's packed data, import run and TOC stubs."""
    assert original[:12] == b"Joy!peffpwpc"
    text = struct.unpack_from(">6I4B", original, 40)
    data = struct.unpack_from(">6I4B", original, 68)
    loader_section = struct.unpack_from(">6I4B", original, 96)
    assert text[5] == patch.TEXT_OFFSET and text[2] == 344416 and text[6] == 0
    assert data[6] == 2 and data[2] == data[3] == 149608
    packed = io.BytesIO(original[data[5]:data[5] + data[4]])
    unpacked = bytearray()

    def count():
        value = 0
        for _ in range(5):
            byte = packed.read(1)
            assert byte, "Truncated packed data"
            value = value * 128 + (byte[0] & 127)
            if not byte[0] & 128:
                return value
        raise AssertionError("Overlong packed-data count")

    while packed.tell() < data[4]:
        instruction = packed.read(1)[0]
        opcode, length = instruction >> 5, instruction & 31
        length = length or count()
        if opcode == 0:
            unpacked += bytes(length)
        elif opcode == 1:
            unpacked += packed.read(length)
        elif opcode == 2:
            repeat = count()
            unpacked += packed.read(length) * (repeat + 1)
        elif opcode in (3, 4):
            custom, repeat = count(), count()
            common = packed.read(length) if opcode == 3 else bytes(length)
            for _ in range(repeat):
                unpacked += common + packed.read(custom)
            unpacked += common
        else:
            raise AssertionError("Unknown packed-data opcode")
        assert len(unpacked) <= data[3]
    assert len(unpacked) == data[3]
    loader = original[loader_section[5]:loader_section[5] + loader_section[4]]
    header = struct.unpack_from(">14I", loader)
    assert header[0] == 1 and header[6:9] == (2, 313, 1)
    imported = []
    for index in range(header[7]):
        entry = struct.unpack_from(">I", loader, 56 + header[6] * 24 + index * 4)[0]
        start = header[10] + (entry & 0xFFFFFF)
        imported.append(loader[start:loader.index(0, start)].decode("ascii"))
    relocation_header = struct.unpack_from(">HHII", loader, 56 + header[6] * 24 + header[7] * 4)
    assert relocation_header[:2] == (1, 0)
    relocations = struct.unpack_from(">" + "H" * relocation_header[2], loader,
                                   header[9] + relocation_header[3])
    assert relocations[0] == 0x4B38  # import run: 313 slots at data offset 0
    assert unpacked[:313 * 4] == bytes(313 * 4)
    # Verify every later relocation advances, so it cannot replace an import slot.
    position = 313 * 4
    for instruction in relocations[1:]:
        if instruction >> 13 == 2:
            kind = (instruction >> 9) & 15
            assert kind in (0, 1, 2, 3, 4)
            position += ((instruction & 511) + 1) * (4, 4, 12, 8, 8)[kind]
        elif instruction >> 12 == 8:
            position += (instruction & 4095) + 1
        elif instruction >> 14 == 0:
            position += (((instruction >> 6) & 255) + (instruction & 63)) * 4
        else:
            raise AssertionError("Unexpected relocation command")
        assert position <= data[2]
    main_entry, main_toc = struct.unpack_from(">II", unpacked, header[1])
    relative_toc = main_toc - data[1]
    assert main_entry == 0x9664 and relative_toc == 0x8000
    mapping = {}
    code = original[patch.TEXT_OFFSET:patch.TEXT_OFFSET + text[2]]
    stub_suffix = bytes.fromhex("90410014800c0000804c00047c0903a64e800420")
    for offset, expected in API.items():
        if expected == "memcpy":
            continue
        load = struct.unpack_from(">I", code, offset)[0]
        assert load >> 16 == 0x8182 and code[offset + 4:offset + 24] == stub_suffix
        displacement = struct.unpack(">h", struct.pack(">H", load & 65535))[0]
        index = (relative_toc + displacement) // 4
        assert imported[index] == expected
        mapping[expected] = {"index": index, "stub_offset": hex(offset), "toc_slot": hex(index * 4)}
    callers = []
    for offset in range(0, len(code), 4):
        word = struct.unpack_from(">I", code, offset)[0]
        if word >> 26 == 18 and word & 3 == 1:
            distance = word & 0x3FFFFFC
            if distance & 0x2000000:
                distance -= 0x4000000
            if offset + distance == 0xC78:
                callers.append(hex(offset))
    assert callers == ["0x5b40"]
    return {"imports": mapping, "toc_section_offset": hex(relative_toc),
            "LMGetFCBSPtr_direct_call_offsets": callers, "import_slots": 313}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forks", type=Path, default=patch.REPO / "analysis/freddi-fisk/mac-forks/22")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = (args.forks / "data.fork").read_bytes()
    import_mapping = verify_import_mapping(original)
    repaired = patch.patch_data(original)
    cases = []
    for temporary in (False, True):
        for signature in (0x4244, 0xD2D7, 0x1234):
            for errors in ({}, {"PBCloseSync": -36}, {"PBFlushVolSync": -34},
                           {"PBHDeleteSync": -45, "PBDeleteSync": -45}):
                old = execute(original, temporary=temporary, signature=signature, errors=errors)
                new = execute(repaired, temporary=temporary, signature=signature, errors=errors, os9=True)
                assert old["result"] == new["result"], (old, new)
                assert old["mutations"] == new["mutations"], (old, new)
                assert "LMGetFCBSPtr" not in new["calls"]
                cases.append({"temporary": temporary, "signature": hex(signature), "errors": errors,
                              "result": new["result"], "mutations": new["mutations"], "abi_preserved": True})
    for api in ("PBGetFCBInfoSync", "PBHGetVInfoSync"):
        new = execute(repaired, temporary=True, errors={api: -51}, os9=True)
        assert new["result"] == -51 and not new["mutations"]
        cases.append({"query_failure": api, **new})
    old_os9 = execute(original, os9=True)
    assert old_os9["failure"] == "dsMustUseFCBAccessors:119"
    for bad in (bytes((original[0] ^ 1,)) + original[1:], repaired):
        try:
            patch.patch_data(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Patcher accepted a different/already-patched executable")
    resource = (args.forks / "resource.fork").read_bytes()
    finder = (args.forks / "finder-info.bin").read_bytes()
    metadata = json.loads((args.forks / "metadata.json").read_text())
    archive = patch.macbinary(repaired, resource, finder, metadata)
    check_archive(archive, repaired, resource, finder)
    disassembler = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (("original", original), ("patched", repaired)):
        code = data[patch.TEXT_OFFSET + patch.START:patch.TEXT_OFFSET + patch.END]
        instructions = list(disassembler.disasm(code, patch.BASE + patch.START))
        assert sum(i.size for i in instructions) == len(code)
        (args.output / f"{name}-close.asm").write_text("\n".join(
            f"{i.address:08x}  {i.bytes.hex()}  {i.mnemonic} {i.op_str}".rstrip() for i in instructions) + "\n")
    report = {"status": "passed; real Mac OS 9 still untested", "emulation_cases": len(cases),
              "original_os9_mock_failure": old_os9, "cases": cases,
              "archive_forks_type_creator_flags_crc": "passed", "checksum_guard": "passed",
              "patched_data_sha256": patch.sha256(repaired), "archive_sha256": patch.sha256(archive),
              "verified_pef_import_mapping": import_mapping,
              "capstone_version": "5.0.7", "unicorn_version": "2.1.4"}
    (args.output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Passed {len(cases)} PowerPC emulation cases, ABI checks, archive checks and checksum guard")


if __name__ == "__main__":
    main()
