#!/usr/bin/env bash
# Push the PM4K fork to the box.
#
# The add-on is its own repo (github.com/magicianmarty/plex-for-kodi-martyedition)
# checked out at ~/dev/plex-for-kodi. Copying the files is harmless at any time -
# Python has already imported what it is running - but the change only takes
# effect the next time the add-on starts, so this does NOT restart Kodi. Do that
# yourself, or just exit and re-enter Plex.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${MARTYGAMES_PLEXMOD:-$HERE/../../plex-for-kodi}"
[ -d "$SRC/lib" ] || { echo "no plex-for-kodi checkout at $SRC" >&2; exit 1; }

IP="$("$HERE/box" --print-ip)"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"

# --delete-excluded as well as --delete: without it the excluded __pycache__
# dirs survive on the box, rsync cannot remove the directory holding them, and
# stale .pyc can still be imported for a .py that no longer exists.
sshpass -e rsync -a --delete --delete-excluded \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR" \
  "$SRC/" "root@$IP:/storage/.kodi/addons/script.plexmod/"

echo "deployed to $IP - restart Kodi or re-enter Plex to pick it up"
