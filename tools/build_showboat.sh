#!/bin/sh
# Separate shifted, source-built personality mod; keep stock and C-stick DOLs.
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python configure.py \
  --build-dir build/showboat \
  --wrapper build/tools/wibo-1.0.3 \
  --dtk build/tools/dtk \
  --objdiff build/tools/objdiff-cli \
  --sjiswrap build/tools/sjiswrap.exe \
  --compilers build/compilers \
  --binutils build/binutils \
  --no-always-apply --map --showboat-ai --showboat-ai-debug --showboat-ai-hud \
  --showboat-unlock-all "$@"
# A modified executable intentionally fails retail SHA-1 matching.
ninja -j 8 build/showboat/GALE01/main.dol
