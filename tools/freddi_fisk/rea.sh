#!/bin/sh
# Local REA CLI; leaves Codex configuration unchanged.
set -eu
freddi_repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
freddi_node=${REA_NODE_BIN:-"$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"}
freddi_rea="$freddi_repo/.local-tools/rea/node_modules/rea-agents/scripts/rea.mjs"
if [ ! -x "$freddi_node" ] || [ ! -f "$freddi_rea" ]; then
  echo "Local REA or a compatible Node runtime is missing. See tools/freddi_fisk/README.md." >&2
  exit 1
fi
export GHIDRA_INSTALL_DIR="$freddi_repo/.local-tools/ghidra_12.1.4_PUBLIC"
export JAVA_HOME="$freddi_repo/.local-tools/jdk-21.0.12.1+1/Contents/Home"
exec "$freddi_node" "$freddi_rea" "$@"
