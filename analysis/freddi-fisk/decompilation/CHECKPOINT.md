# PowerPC decompilation checkpoint

13 October 2026, Europe/Stockholm.

## Outcome

Ghidra 12.1.4 imported the preserved PowerPC PEF executable using the explicit `PowerPC:BE:32:default` language and default compiler specification. It produced C-like pseudocode for all 1,022 functions it recovered, plus inventories of 313 imported symbols and 509 defined strings.

REA 6.4.0 cannot import this file unchanged: its CLI reports `unsupported binary format`. Its shared architecture list and Ghidra adapter support x86, x86_64, ARM, ARM64, and MIPS, with no PowerPC profile. This checkpoint uses unmodified REA for diagnostics and Ghidra directly for the actual decompilation.

## Input identity

- PEF data-fork SHA-256: `aa981103cd36cd9598da22d9ca1e3eca6ad59147dd5a9e7cc449e6a9d665a960`.
- The accepted run recorded identical before-and-after SHA-256 hashes, 368,936-byte lengths, and modification timestamps in `source-verification.json`.
- The fork matches the original preservation manifest. The raw CD image remains untouched.

## Artifacts

- `ghidra-analysis.json`: functions, signatures, callers, imports, strings, and decompiler completion status.
- `functions/<address>.c`: local pseudocode files, excluded from Git.
- `pseudocode-checksums.json`: hashes for those 1,022 local outputs.
- `rea-cli-result.json`, `rea-pef-import.json`, and `rea-compatibility.json`: recorded REA format/profile limitation.
- `toolchain.json`: pinned versions, verified official downloads, and the locally built Apple Silicon native decompiler fingerprint.
- Local import logs retain warnings; they are excluded from Git.

## Quality and limits

- **782 functions** contain warnings in their generated pseudocode. Decompiler completion does not establish accurate types, signatures, control flow, or valid reconstruction.
- Function names are mostly generated `FUN_<address>` labels; the executable entry is named `entry` at `10009664`.
- Optional REA CLI version and provider-doctor probes stalled and were stopped. The direct target-classification and CLI import diagnostics were captured successfully. REA CLI reliability on this host needs further investigation before using it as the primary interface.
- Ghidra's PEF debug analyzer reported an unreadable location at `10054160`. The decompiler also reported an undecodable constructor at `10009774`, in function `10009754`. These are analysis limitations; they do not establish the game's crash location or corrupted media.
- Automatic language selection initially chose `PowerPC:BE:64:VLE-32addr`; that trial was retained separately and excluded from the accepted results. The wrapper now explicitly selects and verifies 32-bit big-endian PowerPC.
- An earlier source check failed; subsequent independent hashing matched the preservation manifest, and the accepted rerun recorded identical hash, size, and timestamp values. No source mutation was established.
- Only the PowerPC executable data fork was analyzed. The separate 68k CODE resources and game-data scripts remain to be decoded. Imports do not include the implementation of Mac OS system libraries.
- No game code was executed or patched. No crash cause has been established.

## Next useful step

Capture a reproducible Freddi Fisk failure in MacsBug and map the runtime address to this static image. The recovered strings include SCUMM error messages and imports include `InterfaceLib::FSRead` and `InterfaceLib::PBReadSync`, which provide starting points for investigation. Runtime addresses must be mapped; they cannot be assumed to equal Ghidra's addresses.

A future REA extension needs PEF header classification and a genuine PowerPC architecture profile. The working Ghidra import/export here is a baseline for testing that integration.

See [tool usage](../../../tools/freddi_fisk/README.md) for repeatable commands.
