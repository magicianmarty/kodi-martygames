#!/usr/bin/env bash
# Capture what the box looks like, so a flash can be proved not to have broken it.
#
# Phase 2 retires the hand-built ABI-6 wrapper for the stock one. The failure
# mode is not a crash - it is a system quietly no longer launching, or artwork
# and metadata silently unresolving. Both are invisible unless you compared.
#
# Deliberately launches nothing: exiting a game crashes Kodi, and three crashes
# trips CoreELEC safe mode. Everything here is static inspection.
#
#   ./tools/snapshot-state.sh before      # now, on the working box
#   ./tools/snapshot-state.sh after       # once the new image is up
#   diff -u state-before.txt state-after.txt
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$HERE/box"
LABEL="${1:-snapshot}"
OUT="$HERE/../state-$LABEL.txt"

{
  echo "# state snapshot: $LABEL"
  echo "# taken $(date -Is)"
  echo

  echo "== os =="
  $BOX 'grep -E "^(VERSION|BUILD_ID|DISTRO_)" /etc/os-release'
  echo

  echo "== kodi + game ABI =="
  $BOX 'grep -oE "Starting Kodi \([^)]*\)" /storage/.kodi/temp/kodi.log 2>/dev/null | head -1'
  $BOX 'grep -oE "kodi.binary.instance.game\" [a-z]*version=\"[0-9.]+\"" /storage/.kodi/addons/game.libretro/addon.xml 2>/dev/null | head -2'
  echo

  echo "== game clients installed =="
  $BOX 'for d in /storage/.kodi/addons/game.libretro*; do
          [ -d "$d" ] || continue
          v=$(grep -oE "version=\"[0-9][0-9.]*\"" "$d/addon.xml" 2>/dev/null | head -1)
          printf "%-42s %s\n" "$(basename $d)" "$v"
        done'
  echo

  echo "== library: games per system =="
  $BOX 'python3 - <<PY
import sys
sys.path.insert(0, "/storage/.kodi/addons/plugin.program.martygames")
from resources.lib import scanner
from resources.lib.systems import BY_KEY
tot = 0
for key in sorted(BY_KEY):
    games = list(scanner.scan_system("/storage/sdcard/roms", BY_KEY[key]))
    if games:
        print("%-12s %3d" % (key, len(games)))
        tot += len(games)
print("%-12s %3d" % ("TOTAL", tot))
PY'
  echo

  echo "== artwork and metadata coverage =="
  $BOX 'echo "boxart:   $(find /storage/sdcard/artwork -maxdepth 2 -name "*.png" -not -path "*/snaps/*" 2>/dev/null | wc -l)"
        echo "snaps:    $(find /storage/sdcard/artwork/snaps -name "*.png" 2>/dev/null | wc -l)"
        echo "metadata: $(python3 -c "import json;d=json.load(open(\"/storage/sdcard/artwork/metadata.json\"));print(sum(len(v) for v in d.values()))" 2>/dev/null)"'
  echo

  echo "== emulator settings that matter =="
  $BOX 'cat /storage/.kodi/userdata/addon_data/game.libretro.pcsx-rearmed/settings.xml 2>/dev/null'
  echo

  echo "== keymaps and buttonmaps =="
  $BOX 'ls /storage/.kodi/userdata/keymaps/ 2>/dev/null
        ls /storage/.kodi/userdata/addon_data/peripheral.joystick/resources/buttonmaps/xml/udev/ 2>/dev/null'
  echo

  echo "== skin =="
  $BOX 'grep -oE "<version>[^<]*" /storage/.kodi/addons/skin.martyedition/addon.xml 2>/dev/null | head -1
        echo "home rows: $(grep -cE "<control type=\"list\" id=\"91[0-9][0-9]\">" /storage/.kodi/addons/skin.martyedition/xml/Home.xml)"'
} > "$OUT" 2>&1

echo "wrote $OUT ($(wc -l < "$OUT") lines)"
