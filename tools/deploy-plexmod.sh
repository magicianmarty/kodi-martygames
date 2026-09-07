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
# Default to the worktree holding feat/plex-hubs, not the main checkout: that
# one is usually parked on whatever branch was last worked on.
SRC="${MARTYGAMES_PLEXMOD:-$HERE/../../wt-p4k-scan}"
[ -d "$SRC/lib" ] || SRC="$HERE/../../plex-for-kodi"
[ -d "$SRC/lib" ] || { echo "no plex-for-kodi checkout at $SRC" >&2; exit 1; }

IP="$("$HERE/box" --print-ip)"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"

echo "deploying from $SRC ($(git -C "$SRC" branch --show-current 2>/dev/null || echo "not a git checkout"))"

# Deliberately NOT --delete.
#
# It was, once. A --delete deploy of an unrelated subtitle change wiped
# plugin.py, the Plex hubs, badges.py and the whole downloads subsystem off
# the box, emptying the skin's home rows.
#
# The work was committed and pushed the whole time - on feat/plex-hubs, which
# is checked out in a worktree, not in the checkout this script defaults to.
# There are eight worktrees on that repo; SRC pointing at the main one says
# nothing about which branch is in it. So --delete asked the box to match a
# tree that was simply a different branch.
#
# Stale files left behind are a far smaller problem than deleted ones. If you
# do want --delete, check the branch printed below is the one you mean and
# dry-run it first.
sshpass -e rsync -a \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR" \
  "$SRC/" "root@$IP:/storage/.kodi/addons/script.plexmod/"

echo "deployed to $IP - restart Kodi or re-enter Plex to pick it up"
echo "note: files removed from the checkout are left on the box; clean those by hand"
