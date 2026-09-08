#!/bin/sh
# Boot the rebuilt DOL with original assets mounted read-only by Dolphin.
# A separate profile avoids touching the user's normal saves/settings.
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: sh tools/run_showboat.sh /absolute/path/to/US-v1.02.ciso" >&2
  exit 1
fi
DISC=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
DOL="$PWD/build/showboat/GALE01/main.dol"
[ -f "$DOL" ] || { echo "Run tools/build_showboat.sh first" >&2; exit 1; }
DOLPHIN=${DOLPHIN:-/Applications/Dolphin.app/Contents/MacOS/Dolphin}
exec "$DOLPHIN" --user "$PWD/build/showboat/dolphin-user" \
  -C Main.Core.CPUThread=False \
  -C Main.Core.EnableCheats=False \
  -C "Main.Core.DefaultISO=$DISC" \
  -C Logger.Options.WriteToFile=True \
  -C Logger.Options.WriteToConsole=True \
  -C Logger.Options.Verbosity=4 \
  -C Logger.Logs.OSREPORT=True \
  -C Logger.Logs.OSREPORT_HLE=True \
  -C Logger.Logs.BOOT=True \
  --exec "$DOL"
