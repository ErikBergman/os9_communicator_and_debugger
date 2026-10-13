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
