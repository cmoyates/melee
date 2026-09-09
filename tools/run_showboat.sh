#!/bin/sh
# Dolphin's virtual-disc boot accommodates a DOL larger than its retail slot.
# Stop the previous test session before running this helper again.
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: sh tools/run_showboat.sh /absolute/path/to/US-v1.02.ciso" >&2
  exit 1
fi
DOL="$PWD/build/showboat/GALE01/main.dol"
DISC="$PWD/build/showboat/disc"
[ -f "$DOL" ] || { echo "Run tools/build_showboat.sh first" >&2; exit 1; }
# Read-only, fail-closed check before extraction, DOL replacement or profile seeding.
# Never stop an existing game to make room for a new test session.
if pgrep -ix 'Dolphin|dolphin-emu|dolphin-emu-qt2' >/dev/null; then
  echo "Refusing to launch while Dolphin is running; no DOL copied" >&2
  exit 1
else
  status=$?
  [ "$status" -eq 1 ] || {
    echo "Cannot check for running Dolphin; no DOL copied" >&2; exit 1;
  }
fi
# All extraction/copy destinations are generated files under build/showboat.
[ ! -L "$DISC" ] && [ ! -L "$DISC/sys" ] && [ ! -L "$DISC/sys/main.dol" ] || {
  echo "Refusing a symlinked virtual-disc destination" >&2; exit 1;
}
if [ ! -d "$DISC/files" ]; then
  [ ! -e "$DISC" ] || {
    echo "Incomplete virtual disc at $DISC; move it aside and retry" >&2; exit 1;
  }
  build/tools/dtk disc extract "$1" "$DISC"
fi
.venv/bin/python - "$DISC/sys/boot.bin" <<'PY'
import sys
from pathlib import Path
boot = Path(sys.argv[1]).read_bytes()
if boot[:6] != b"GALE01" or boot[7] != 2:
    raise SystemExit("Expected Melee US v1.02 assets; no DOL copied")
PY
cp "$DOL" "$DISC/sys/main.dol"
USER_DIR="$PWD/build/showboat/dolphin-user"
# Seed only controller mappings on first use; never copy saves or overwrite
# subsequent test-profile changes. The normal profile remains read-only.
PAD_SOURCE="$HOME/Library/Application Support/Dolphin/Config/GCPadNew.ini"
if [ ! -e "$USER_DIR/Config/GCPadNew.ini" ] && [ -f "$PAD_SOURCE" ]; then
  mkdir -p "$USER_DIR/Config"
  cp "$PAD_SOURCE" "$USER_DIR/Config/GCPadNew.ini"
fi
DOLPHIN=${DOLPHIN:-/Applications/Dolphin.app/Contents/MacOS/Dolphin}
set --
if [ -f "$USER_DIR/Config/GCPadNew.ini" ]; then
  set -- --controller-config "$USER_DIR/Config/GCPadNew.ini"
fi
exec .venv/bin/python tools/showboat_capture.py \
  --dol "$DISC/sys/main.dol" --recordings-dir "$PWD/build/showboat/recordings" \
  "$@" -- "$DOLPHIN" --user "$USER_DIR" \
  -C Main.Core.CPUThread=False \
  -C Main.Core.EnableCheats=False \
  -C Logger.Options.WriteToFile=True \
  -C Logger.Options.WriteToConsole=True \
  -C Logger.Options.Verbosity=4 \
  -C Logger.Logs.OSREPORT=True \
  -C Logger.Logs.OSREPORT_HLE=True \
  -C Logger.Logs.BOOT=True \
  --exec "$DISC/sys/main.dol"
