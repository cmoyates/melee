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
DOLPHIN=${DOLPHIN:-/Applications/Dolphin.app/Contents/MacOS/Dolphin}
exec "$DOLPHIN" --user "$PWD/build/showboat/dolphin-user" \
  -C Main.Core.CPUThread=False \
  -C Main.Core.EnableCheats=False \
  -C Logger.Options.WriteToFile=True \
  -C Logger.Options.WriteToConsole=True \
  -C Logger.Options.Verbosity=4 \
  -C Logger.Logs.OSREPORT=True \
  -C Logger.Logs.OSREPORT_HLE=True \
  -C Logger.Logs.BOOT=True \
  --exec "$DISC/sys/main.dol"
