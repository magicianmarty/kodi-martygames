#!/usr/bin/env bash
# Push the skin to the box and reload it.
#
# Kodi caches skin XML for the life of the process. Disabling and re-enabling
# the add-on over JSON-RPC does not reload it; only a restart does.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IP="$("$HERE/box" --print-ip)"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"

# The skin is its own repo (github.com/magicianmarty/skin-martyedition),
# checked out beside this one rather than inside it.
SKIN="${MARTYGAMES_SKIN:-$HERE/../../skin-martyedition}"
[ -d "$SKIN/xml" ] || { echo "no skin checkout at $SKIN" >&2; exit 1; }

sshpass -e rsync -a --delete --exclude '.git' \
  -e "ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR" \
  "$SKIN/" \
  "root@$IP:/storage/.kodi/addons/skin.martyedition/"

"$HERE/box" 'systemctl restart kodi'
echo "deployed to $IP and restarted kodi"
