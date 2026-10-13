# Mac OS 9 communicator and debugger

Tools for exchanging files with a physical Mac OS 9 iMac and investigating
classic Macintosh games from a modern MacBook.

## Repository layout

```text
tools/
  file_transfer/          Internet Explorer 5 upload/download server
  freddi_fisk/            Freddi Fisk disk-image inspection tools
tests/                   Regression checks
analysis/freddi-fisk/     Inspection reports and inventories
transfer/                Local uploaded files and outgoing downloads
```

Build application-specific tools in `tools/<application>/`, keeping their
scripts, dependency requirements, and usage instructions together. Shared
utilities have their own tool folder, such as `file_transfer`. Keep generated
evidence under `analysis/` and local transfers under `transfer/`; large images
and exported forks are excluded from Git.

## File transfer

Run on the MacBook:

```sh
python3 tools/file_transfer/os9_file_transfer.py
```

Open `http://192.168.77.1:8000/` in Internet Explorer 5 on the iMac. Put outgoing
files in `transfer/to-imac`; uploads arrive in `transfer/from-imac`. These paths
are relative to the repository root, regardless of the terminal's working
directory. See [file-transfer instructions](tools/file_transfer/README.md).

## Freddi Fisk

See [inspection-tool instructions](tools/freddi_fisk/README.md),
[inspection report](analysis/freddi-fisk/INVENTORY.md), and
[complete inventory](analysis/freddi-fisk/inventory.json).

## Checks and handover

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

[HANDOVER.md](HANDOVER.md) records the Ethernet configuration, MacsBug workflow,
and the older communicator implementation that remains in the parent workspace.
