# Freddi Fisk inspection tools

`inspect_freddi_image.py` reads raw Mode 1 hybrid CD images without mounting or
writing the source. It inventories HFS and ISO 9660 files, saves exact HFS data
and resource fork copies with Finder metadata, and verifies the original hash
and modification time afterward. It requires Python 3.11+.

Run from the repository root:

```sh
python3 -m pip install --target /tmp/os9-freddi-analysis-deps \
  -r tools/freddi_fisk/requirements.txt
PYTHONPATH=/tmp/os9-freddi-analysis-deps python3 tools/freddi_fisk/inspect_freddi_image.py \
  "transfer/from-imac/20261013-122508-0bdf521f70bd-Freddi Fisk.img" \
  analysis/freddi-fisk
```

The pinned dependencies install in a temporary folder. Change the image path and
output directory for another copy; the reader expects 2352-byte Mode 1 sectors
and a hybrid image with a classic HFS partition and ISO 9660 volume.

Outputs include `inventory.json`, `checksums.sha256`, a separate payload-only
ISO derivative, and `mac-forks/<catalog ID>/` preservation artifacts. The fork
pairs are not native dual-fork Macintosh files; they require a fork-aware tool
or packaging before use on Mac OS 9. The script does not validate CD EDC/ECC,
repair filesystems, execute game code, or diagnose crashes.

See [the completed inspection report](../../analysis/freddi-fisk/INVENTORY.md).

## PowerPC decompilation

The tested release, REA 6.4.0, rejects this PEF file as an unsupported binary
format. Its provider-neutral CPU list and Ghidra adapter exclude PowerPC.
Ghidra itself can import it. `decompile_pef.py` therefore uses Ghidra directly;
`rea.sh` provides the unmodified local REA CLI for compatibility checks.

Install the pinned Ghidra 12.1.4 and Temurin JDK 21 archives on Apple Silicon
macOS, then run the analysis (Python 3.12+ and Xcode Command Line Tools):

```sh
python3 tools/freddi_fisk/setup_decompiler.py
python3 tools/freddi_fisk/decompile_pef.py
```

The installer verifies the downloaded archive sizes and SHA-256 checksums in
`runtime-downloads.json`. It uses the ignored `.local-tools/` directory and
builds the missing native Apple Silicon decompiler from Ghidra's bundled source.
It skips existing runtime directories without reverifying their installed
contents. It does not alter Java or Node installations outside the repository.

The analysis forces `PowerPC:BE:32:default`, because automatic PEF language
selection chose an unsuitable VLE/64-bit profile in our initial trial. It uses
a temporary, read-only project and isolated Java user settings. The input fork's
SHA-256, size, and modification time are checked after analysis and written to
`source-verification.json`. A completed output directory is never overwritten;
use `--output /path/to/new-output` for a subsequent run.

Outputs in `analysis/freddi-fisk/decompilation/`:

- `ghidra-analysis.json`: recovered functions, imports, defined strings, and
  per-function diagnostics.
- `functions/<address>.c`: C-like pseudocode for each recovered function.
- `source-verification.json`: before-and-after input identity checks.
- Local logs: import and analysis warnings. Pseudocode and logs are excluded
  from Git; they remain available on this MacBook.

Pseudocode is an interpretation of the native executable. It does not recover
the original source project, cover the separate 68k resources or game-data
scripts, or establish the cause of a crash.

## Local REA CLI

REA also requires a compatible Node runtime (22.19+, 24.11+, or 26+). This
MacBook has a compatible bundled Codex Node runtime. The local installation used:

```sh
"$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node" \
  /usr/local/lib/node_modules/npm/bin/npm-cli.js install \
  --prefix .local-tools/rea --ignore-scripts --no-audit --no-fund rea-agents@6.4.0
tools/freddi_fisk/rea.sh inspect analysis/freddi-fisk/mac-forks/22/data.fork \
  --provider ghidra --format json --full-output
```

`rea.sh` sets the local Ghidra and JDK paths. Set `REA_NODE_BIN` to another
compatible Node executable when the bundled runtime is unavailable. These CLI
checks do not register an MCP server or change Codex settings. Supporting this
game in REA would require genuine PEF classification and PowerPC profiles;
labeling the executable as another CPU architecture would be incorrect.

See [the decompilation checkpoint](../../analysis/freddi-fisk/decompilation/CHECKPOINT.md)
for the verified output counts, source checks, and observed analysis limitations.
Optional REA version and provider-doctor probes stalled on this host and were
stopped; the direct Ghidra analysis is the verified working path.

`--probe-fcb --output /path/to/fresh-output` selects the focused FCB-reference
script, `InspectFCBAccess.java`. The initial run stalled loading a framework JAR;
a rerun using verified runtime copies in `/tmp` now completes. It resolves the
external symbols to data slots but does not automatically resolve every TOC
instruction. The launcher puts the chosen
JDK first on PATH as well as setting JAVA_HOME, because Ghidra's bootstrap prefers
PATH's Java executable.

## Experimental OS 9 compatibility patch

`patch_os9.py` replaces this edition's incompatible file-close helper and builds
a MacBinary II application with the original resource fork and Finder metadata.
It requires the exact preserved checksums and writes a separate output. It never
updates the source disk image or forks.

`validate_os9_patch.py` independently maps the PEF imports and runs original and
patched PowerPC machine code under Unicorn, with mocked OS calls, ABI and fork
checks. Dependencies are pinned in `patch-requirements.txt`. Ghidra's
`--review-close` mode explicitly defines the verified routine and import stubs
to export focused disassembly/pseudocode; the broad automatic export missed it.

See [the patch instructions](../../analysis/freddi-fisk/patches/os9-fcb-v1/README.md)
for reproduction commands, iMac installation, checksums and remaining limits.
The candidate passes static/emulated validation; physical OS 9 testing remains.
