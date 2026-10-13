# Experimental Mac OS 9 FCB compatibility repair

This is a **test candidate**, not yet verified on the physical iMac. It repairs
the direct FCB-table lookup associated with the captured startup error 119.
The original disk image and preservation forks have not been modified.

## Try it on the iMac

1. Reconnect the MacBook's Ethernet adapter and direct iMac cable. At preparation
   time the adapter/interface and `192.168.77.1` address were absent, so a live
   download could not be verified. The existing transfer server still listens
   on `192.168.77.1:8000`.
2. Restart the iMac after the previous crash. In Finder, create a new folder
   such as **Freddi OS9 test** on its hard disk. Copy the game's Mac files from
   the CD/image into it: **Freddi Fisk** and **Freddi Fisk (0)**, **(1)**,
   **(2)** and **(4)**. Copy with the iMac's Finder to preserve resource forks.
3. In IE 5, download [Freddi-Fisk-OS9-test.bin](http://192.168.77.1:8000/download/Freddi-Fisk-OS9-test.bin).
   Open it with StuffIt Expander if the browser does not expand it automatically.
   The extracted application is named **Freddi Fisk**. Put it in the new test
   folder, replacing only the copied application there. Keep the original CD,
   image, application and save files.
4. Launch that extracted application from the test folder. Keep the original
   CD available if the game requests it. Record whether the CD-speed test
   appears, whether startup completes, and whether entering a scene, quitting,
   saving and reopening work. Copying data to the hard disk may change the speed
   test's behavior; successful startup alone would not establish an identical
   CD-backed test.
5. If MacsBug appears again, run `stdlog`, then `es`, restart, and upload the new
   log using the transfer page. Identify the action and confirm that this test
   copy was launched.

The archive is 743,808 bytes (about 744 KB). It contains the original resource
fork, `APPL` type, `HeFF` creator, Finder flags, dates and application filename.
Only its PowerPC data fork is patched. The separate 68k CODE resources are
unchanged; this candidate targets the PowerPC iMac.

## What changed

The PEF text section begins at file offset 152. Its file-close helper occupies
section offsets `0x5b2c..0x5c7f` (340 bytes), represented by Ghidra addresses
`0x10005b2c..0x10005c7f`. These are analysis addresses, not iMac runtime addresses.
The patch changes 252 bytes within this helper and keeps the file length,
section tables, import tables and relocation instructions unchanged.

The original calls the `LMGetFCBSPtr` stub at section offset `0xc78` from `0x5b40`,
adds the file reference number to that pointer, then reads the FCB's volume
pointer, parent ID and filename. It reads the volume signature and reference
number directly from the VCB. This fails on Mac OS 9, which deliberately raises
error 119 for the PowerPC accessor. [Apple TN1184](https://leopard-adc.pepas.com/technotes/tn/tn1184.html)

The replacement obtains the volume reference, parent ID and filename using
the already imported `PBGetFCBInfoSync`. For temporary-file deletion it obtains
the volume signature with the already imported `PBHGetVInfoSync`. It then calls
the existing close, HFS/MFS delete and volume-flush APIs. It retains the original
final `ioResult` return convention. A failed new information query returns its
error before closing/deleting/flushing. This is a new failure path and needs
real-system validation.

The queries use Apple's packed File Manager parameter-block layouts. An FCB
query with index zero selects the supplied file reference. Its name buffer is
separate from the reused volume parameter block, and the parent ID/volume are
saved in nonvolatile registers before that block is reused.
[Apple: File Manager parameter blocks](https://dev.os9.ca/techpubs/mac/Files/Files-301A.html),
[Apple: PBGetFCBInfo](https://leopard-adc.pepas.com/documentation/mac/pdf/Files/File_Manager.pdf)

## Evidence and checks

- `validation.json`: 26 PowerPC emulation cases with mocked File Manager APIs.
  Successful and failed close/delete/flush paths match the original routine's
  file operations and results. New query failures return their errors without
  file mutations. Stack, nonvolatile registers and the game TOC survive hostile
  legal volatile-register clobbers. The old accessor is mocked as error 119 on
  OS 9; the repaired routine never calls it.
- The validator independently unpacks PEF data, parses import names, verifies
  the initial 313-slot import relocation run, checks the remaining relocations
  advance beyond those slots, derives the TOC offset from the main transition
  vector, and maps each called stub to its real import. It finds one direct
  branch to the forbidden stub in the original text section.
- `original-close.asm` / `patched-close.asm`: independent Capstone decoding.
- `ghidra-original/` / `ghidra-patched/`: independent Ghidra decoding and focused
  pseudocode after explicitly defining this routine and naming the verified
  imports. Both report the correct CPU and input checksum. Pseudocode warns
  about an unknown calling convention; machine-code/ABI emulation is the
  stronger check. The prior broad automatic export missed this helper and did
  not resolve all TOC references. It must not be treated as complete coverage.
- MacBinary II header CRC, both decoded forks, type/creator, Finder flags,
  length and padding are checked. macOS `file` independently identifies the
  artifact as a MacBinary II PowerPC PEF application with a resource fork.
  [MacBinary II specification](https://files.stairways.com/other/macbinaryii-standard-info.txt)
- The patcher rejects another edition and an already-patched input. The
  preserved data fork's original checksum, size and modification time remain
  unchanged. `patch-manifest.json` records source/output hashes and scope.

These checks do not emulate Mac OS 9 itself, verify actual File Manager behavior,
prove the captured CD executable has identical bytes, or demonstrate gameplay
on the physical iMac. No global system/ROM patch has been installed.

## Reproduce

From the repository root:

```sh
python3 -m pip install --target /tmp/freddi-patch-deps \
  -r tools/freddi_fisk/patch-requirements.txt
python3 tools/freddi_fisk/patch_os9.py --output /tmp/freddi-os9-build
PYTHONPATH=/tmp/freddi-patch-deps python3 tools/freddi_fisk/validate_os9_patch.py \
  --output /tmp/freddi-os9-validation
python3 tools/freddi_fisk/decompile_pef.py --review-close \
  --input /tmp/freddi-os9-build/patched-data.fork --output /tmp/freddi-os9-review
```

The build directory must be empty. The patcher uses the preserved fork set by
default; `--forks` accepts a different directory holding the same verified
`data.fork`, `resource.fork`, `finder-info.bin` and `metadata.json`.
Copy the resulting `.bin` into `transfer/to-imac` to offer it for download.
The original game bytes and built applications are excluded from Git.

macOS offloaded the repo's toolchain files (`dataless` file flags), causing JAR
reads to stall. The completed focused runs used fresh checksum-verified copies
of the same pinned Ghidra/JDK releases in `/tmp/freddi-fresh-toolchain`, plus the
previously built native decompiler. Supply `--ghidra-dir` and `--jdk-home` for
that runtime if needed; runtime details are in the existing setup tool.
