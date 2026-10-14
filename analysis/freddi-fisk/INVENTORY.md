# Freddi Fisk disk-image inspection

Inspected 13 October 2026, Europe/Stockholm.

For the subsequent application modification, see the
[plain-language compatibility repair explanation](COMPATIBILITY-REPAIR.md).

## Original image

- Source: `/Users/erikbergman/Documents/Programmering/MacOS9/os9_communicator_and_debugger/transfer/from-imac/20261013-122508-0bdf521f70bd-Freddi Fisk.img`
- Size: **265,768,944 bytes**.
- SHA-256: `29f8319c86cfbfe22c3cd8658b1ac7a1c0aa61bea9b3a26b9c794c744027d77c`.
- Opened only for reading; never mounted. Its hash, byte length, and modification time matched after inspection.

## Disc layout

- Raw CD-ROM Mode 1, **112,997 sectors**, 2352 bytes per sector.
- Every sector has the expected sync sequence and Mode 1 header. EDC/ECC were not validated.
- A separate derivative contains the 2048-byte payload from each sector, preserving the embedded filesystems and their forks. It is not a replacement for the raw preservation image.
- Derivative: `freddi-mode1-payload.iso`, 231,417,856 bytes; SHA-256 `4342015307d097d8a8930faf126e49ab4a02e69e736843de1760d5930ce88ac3`.
- Hybrid disc: classic HFS Macintosh volume **Freddi** plus ISO 9660 Windows volume **FREDDI**.
- HFS: **12 files, 1 folder** (excluding the root). Catalog counts match the master directory block.
- ISO 9660: **259 files, 9 folders**. The ISO logical volume ends before the HFS partition; trailing-data warnings from ISO-only tools do not establish corruption.

## Macintosh inventory

| File | Type / creator | Data fork (bytes) | Resource fork (bytes) |
| --- | --- | ---: | ---: |
| `Apple System Software/QuickTime™` | `INIT` / `ånd6` | 245,206 | 827,409 |
| `Apple System Software/Sound` | `cdev` / `soun` | 0 | 54,212 |
| `Apple System Software/Sound Manager` | `INIT` / `sad ` | 20,250 | 212,010 |
| `Desktop DB` | `BTFL` / `DMGR` | 16,384 | 0 |
| `Desktop DF` | `DTFL` / `DMGR` | 14,210 | 0 |
| `Freddi Fisk` | `APPL` / `HeFF` | 368,936 | 374,616 |
| `Freddi Fisk (0)` | `HeHe` / `HeFF` | 26,402 | 0 |
| `Freddi Fisk (1)` | `HeHe` / `HeFF` | 54,552,096 | 0 |
| `Freddi Fisk (2)` | `HeHe` / `HeFF` | 29,957,769 | 0 |
| `Freddi Fisk (4)` | `HeHe` / `HeFF` | 25,623,197 | 0 |
| `Icon\r` | `\0\0\0\0` / `\0\0\0\0` | 0 | 2,670 |
| `Viktigt` | `ttro` / `ttxt` | 9,474 | 332 |

## Executable and preservation findings

- **Freddi Fisk** is an APPL file with creator HeFF. Its 368,936-byte data fork starts with `Joy!peffpwpc`: PowerPC PEF code.
- Its 374,616-byte resource fork includes a PowerPC `cfrg`, 13 `CODE` resources containing 68k code/jump-table material, and 2 `vers` resources reporting version 1.0. The Swedish readme specifies System 7.0 or later and a 25 MHz or faster 68040 or PowerPC Macintosh.
- The four Macintosh data files are `Freddi Fisk (0)`, `(1)`, `(2)`, and `(4)`. Their numbering alone is not evidence of a missing file.
- The Windows side has `FREDDI.HE0` through `.HE4`. Only Mac `(4)` and Windows `.HE4` have identical SHA-256 hashes; the other compared data files differ and must not be substituted as interchangeable copies.
- Every HFS file has exact data and resource fork copies under `mac-forks/<catalog ID>/`, plus the complete 32-byte Finder info and original catalog record. Each written artifact was hashed and checked against the bytes read from HFS.
- `inventory.json` records all Mac file/fork hashes, raw names as path components, catalog IDs, Finder metadata, resource inventories, and the complete Windows file inventory with hashes.
- Desktop DB and Desktop DF are included. The high-level machfs reader omits these; the catalog-based inventory retains them.
- Separate parser paths agree on both forks for the 10 files exposed by the high-level machfs reader.

## Files for subsequent analysis

- `mac-forks/22/data.fork`: the game's PowerPC PEF executable for static analysis.
- `mac-forks/22/resource.fork`: the original complete application resource fork.
- `mac-forks/22/finder-info.bin` and `catalog-record.bin`: original Finder info and catalog entry.
- These are separate preservation artifacts, not native dual-fork Mac files. Recombine with a fork-aware tool or package as MacBinary/AppleDouble before transferring an executable back to OS 9.

## Limits

The original read-only inspection did not execute or modify game code or
diagnose the crash. The subsequent repair of a separate application copy is
documented separately. No EDC/ECC verification or comparison against a known-good
image was performed. Readable files and matching copies do not prove that the
image is undamaged.

## Reproduce

Python 3.11+ is required. Install the pinned requirements into a temporary directory, then run:

```sh
python3 -m pip install --target /tmp/os9-freddi-analysis-deps -r tools/freddi_fisk/requirements.txt
PYTHONPATH=/tmp/os9-freddi-analysis-deps python3 tools/freddi_fisk/inspect_freddi_image.py \
  "transfer/from-imac/20261013-122508-0bdf521f70bd-Freddi Fisk.img" analysis/freddi-fisk
```

Run from the `os9_communicator_and_debugger` repository. The original is always opened with `rb`; existing derivatives are checked before reuse.

Readers: [machfs 1.3](https://github.com/elliotnunn/machfs) and [macresources 1.2](https://github.com/elliotnunn/macresources). B-tree decoding uses machfs; the catalog traversal explicitly preserves entries hidden by its high-level Volume reader.
