#!/usr/bin/env bash
# Push the add-on to the box.
#
# reuselanguageinvoker is not set in addon.xml, so every invocation is a fresh
# interpreter and changed modules under resources/lib take effect on the next
# click - no Kodi restart. If that ever gets turned on, this needs a restart.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IP="$("$HERE/box" --print-ip)"
SSH_OPTS="-o StrictHostKeyChecking=no -o LogLevel=ERROR"

export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"
sshpass -e rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh $SSH_OPTS" \
  "$HERE/../plugin.program.martygames/" \
  "root@$IP:/storage/.kodi/addons/plugin.program.martygames/"

echo "deployed to $IP"
