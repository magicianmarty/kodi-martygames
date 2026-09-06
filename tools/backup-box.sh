#!/usr/bin/env bash
# Mirror the whole box to this machine.
#
# Three separate things, because they are restored differently:
#
#   flash/    /flash - SYSTEM (the squashfs OS image), kernel, dtb, config.ini.
#             This is what makes a restore possible at all.
#   storage/  /storage - skin, add-ons, keymaps, buttonmaps, savestates,
#             addon_data. Everything we have configured by hand.
#   roms/     the SD card. 15 GB, and re-curating 200 games is a week.
#
# rsync, so a second run only moves what changed. Safe to re-run before any
# risky change - which is the point.
#
#   ./tools/backup-box.sh              # everything
#   ./tools/backup-box.sh flash storage # just those
set -euo pipefail

# Address discovered the same way tools/box does it - the box is on DHCP and
# its lease has already moved once mid-session.
BOX="${MARTYGAMES_BOX:-root@$("$(dirname "$0")/box" --print-ip)}"
DEST="${MARTYGAMES_BACKUP_DIR:-$HOME/dev/kodi-martygames-backups}"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"

RSH='sshpass -e ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR'
RSYNC_OPTS=(-a --info=stats1 --human-readable --delete-after -e "$RSH")

want=("$@")
[ ${#want[@]} -eq 0 ] && want=(flash storage roms)

mkdir -p "$DEST"

# Record what this is a backup *of*: a restore is worthless if you cannot tell
# which image and device it came from.
{
  echo "# backup taken $(date -Is)"
  echo "# from $BOX"
  echo
  $RSH "$BOX" 'cat /etc/os-release; echo; echo "--- df ---"; df -h | grep -vE "tmpfs|devtmpfs"; echo; echo "--- addons ---"; ls /storage/.kodi/addons'
} > "$DEST/MANIFEST.txt" 2>/dev/null || echo "warning: could not write manifest"

has() { local n="$1"; shift; for w in "$@"; do [ "$w" = "$n" ] && return 0; done; return 1; }

if has flash "${want[@]}"; then
  echo "==> /flash (bootable image)"
  mkdir -p "$DEST/flash"
  rsync "${RSYNC_OPTS[@]}" --exclude 'System Volume Information' \
    "$BOX:/flash/" "$DEST/flash/"
fi

if has storage "${want[@]}"; then
  echo "==> /storage (configuration, add-ons, savestates)"
  mkdir -p "$DEST/storage"
  # .cache and temp are regenerated on boot; the SD card is backed up separately
  # and would otherwise be pulled twice through the symlink.
  #
  # .cache/connman is the exception: it holds the network configuration. This
  # box is wired and DHCP, so losing it costs little today - but it is what
  # would carry a static address or Wi-Fi credentials if either is ever set,
  # and it is a few kilobytes. Note that if Wi-Fi is ever configured, this puts
  # the PSK in the backup.
  rsync "${RSYNC_OPTS[@]}" \
    --exclude '/sdcard' --exclude '/roms' \
    --exclude '/.cache/' --exclude '/.kodi/temp/' \
    "$BOX:/storage/" "$DEST/storage/"

  echo "==> network configuration"
  rsync "${RSYNC_OPTS[@]}" --relative \
    "$BOX:/storage/.cache/connman" "$DEST/storage/" 2>/dev/null \
    || echo "    (no connman state - box may be on a stock system)"
fi

if has roms "${want[@]}"; then
  echo "==> ROM library"
  romdir=$($RSH "$BOX" 'readlink -f /storage/sdcard')
  echo "    source: $romdir"
  mkdir -p "$DEST/roms"
  rsync "${RSYNC_OPTS[@]}" "$BOX:$romdir/" "$DEST/roms/"
fi

echo
echo "done -> $DEST"
du -sh "$DEST"/* 2>/dev/null || true
