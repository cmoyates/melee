#!/bin/sh
# Build this mod branch separately, retaining stock code-generation settings.
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python configure.py \
  --build-dir build/cstick \
  --wrapper build/tools/wibo-1.0.3 \
  --dtk build/tools/dtk \
  --objdiff build/tools/objdiff-cli \
  --sjiswrap build/tools/sjiswrap.exe \
  --compilers build/compilers \
  --binutils build/binutils \
  --no-always-apply
# Intentionally target only the modded DOL, not the retail SHA-1 check/progress.
# Keep MUST_MATCH code paths so unrelated game code stays identical to stock.
ninja -j 8 build/cstick/GALE01/main.dol
