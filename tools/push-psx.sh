#!/usr/bin/env bash
# Copy converted PS1 CHDs to the box as they appear.
#
# Conversion runs for hours and the network is the slower half, so this is run
# repeatedly alongside it rather than once at the end - rsync skips what is
# already there. ps1-chd.py renames each finished file into place, so a file
# visible here is complete.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$HERE/../.cache/ps1-chd}"
IP="$("$HERE/box" --print-ip)"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"
sshpass -e ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR "root@$IP" \
  'mkdir -p /storage/sdcard/roms/psx'
sshpass -e rsync -a --info=stats1 --partial \
  -e 'ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR' \
  "$SRC/" "root@$IP:/storage/sdcard/roms/psx/"
