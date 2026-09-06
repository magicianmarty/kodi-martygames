#!/usr/bin/env bash
# Set up a new ROM card and restore onto it from the verified backup.
#
#   ./tools/swap-card.sh            # checks and capacity test only
#   ./tools/swap-card.sh --apply    # partition, format, mount, restore
#
# Why this exists rather than typing mkfs at a live box: the SD slot is
# /dev/mmcblk1 and the eMMC holding /flash and /storage is /dev/mmcblk0. One
# transposed digit destroys the install. Every guard below is about that.
#
# It also fixes the reason a card swap breaks the library at all. /storage/sdcard
# is a symlink to /var/media/mmcblk1p1-mmc-<serial>, so a new card dangles it.
# This replaces the symlink with a real mount by LABEL, which no future swap can
# break as long as the label matches.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$HERE/box"
BACKUP="${MARTYGAMES_BACKUP:-$HERE/../../kodi-martygames-backups/roms}"
DEV=/dev/mmcblk1
PART=${DEV}p1
LABEL=MARTYROMS
MOUNT=/storage/sdcard
APPLY="${1:-}"

die() { printf '\nREFUSING: %s\n' "$*" >&2; exit 1; }
say() { printf '\n== %s\n' "$*"; }

say "target check"
$BOX "test -b $DEV" || die "$DEV is not a block device - is the card seated?"

# Compared by device major:minor, not by name. /flash and /storage are
# udev-named nodes (/dev/CE_FLASH, /dev/CE_STORAGE) that no amount of string
# matching relates to /dev/mmcblk0, and busybox has no findmnt. An earlier
# version of this check compared empty strings and passed vacuously.
TARGET_IDS=$($BOX "for d in /sys/block/$(basename $DEV)/dev /sys/block/$(basename $DEV)/*/dev; do
                     [ -r \"\$d\" ] && cat \"\$d\"; done" | tr '\n' ' ')
[ -n "$TARGET_IDS" ] || die "cannot read the device ids of $DEV"
echo "   $DEV and its partitions are devices: $TARGET_IDS"

for critical in / /flash /storage; do
  src=$($BOX "df '$critical' 2>/dev/null | tail -1 | cut -d' ' -f1")
  [ -n "$src" ] || die "cannot determine which device holds $critical"
  id=$($BOX "stat -L -c '%t:%T' '$src' 2>/dev/null" | awk -F: '{printf "%d:%d", strtonum("0x"$1), strtonum("0x"$2)}')
  [ -n "$id" ] && [ "$id" != ":" ] || die "cannot determine the device id of $src (holding $critical)"
  case " $TARGET_IDS " in
    *" $id "*) die "$critical is on $src (device $id), which is part of $DEV" ;;
  esac
  echo "   $critical is on $src (device $id), clear of $DEV"
done

SIZE=$($BOX "cat /sys/block/$(basename $DEV)/size")
BYTES=$(( SIZE * 512 ))
GB=$(( BYTES / 1000000000 ))
echo "   $DEV reports ${GB} GB"
[ "$GB" -gt 500 ] || die "${GB} GB is not the new 1 TB card - refusing to touch the wrong device"

say "capacity test (catches counterfeit cards, which report 1 TB and wrap)"
# Write a distinct marker near the start, middle and end, then read all three
# back. A fake card wraps writes onto earlier blocks, so the earlier markers
# come back holding the later marker's content.
if ! $BOX "
  set -e
  fail=0
  for frac in 1 25 50 75 99; do
    off=\$(( $SIZE / 100 * frac ))
    printf 'MARTY-%03d-CAPACITY-PROBE' \$frac | dd of=$DEV bs=512 seek=\$off count=1 conv=notrunc 2>/dev/null
  done
  sync; echo 3 > /proc/sys/vm/drop_caches
  for frac in 1 25 50 75 99; do
    off=\$(( $SIZE / 100 * frac ))
    got=\$(dd if=$DEV bs=512 skip=\$off count=1 2>/dev/null | head -c 24)
    want=\$(printf 'MARTY-%03d-CAPACITY-PROBE' \$frac)
    if [ \"\$got\" != \"\$want\" ]; then echo \"  block \$frac%: wanted '\$want' got '\$got'\"; fail=1; fi
  done
  exit \$fail
"; then
  die "the card does not hold what is written across its full span - it is not really ${GB} GB"
fi
echo "   markers at 1/25/50/75/99% all read back correctly"

say "backup to restore from"
[ -d "$BACKUP" ] || die "no backup at $BACKUP"
FILES=$(find "$BACKUP" -type f | wc -l)
BYTES_B=$(find "$BACKUP" -type f -printf '%s\n' | awk '{s+=$1} END {print s}')
echo "   $FILES files, $BYTES_B bytes"
[ "$FILES" -gt 13000 ] || die "only $FILES files in the backup - that is not the full ROM tree"

if [ "$APPLY" != "--apply" ]; then
  echo
  echo "checks passed. Re-run with --apply to partition, format and restore."
  exit 0
fi

say "partitioning and formatting $DEV as ext4"
$BOX "
  set -e
  umount ${PART} 2>/dev/null || true
  umount /var/media/mmcblk1p1* 2>/dev/null || true
  echo -e 'o\nn\np\n1\n\n\nw' | fdisk $DEV >/dev/null 2>&1 || true
  sleep 2
  mkfs.ext4 -F -L $LABEL -m 0 ${PART}
  blkid ${PART}
"

say "mounting by label, so a future card swap cannot break the path again"
$BOX "
  set -e
  systemctl stop storage-sdcard.mount 2>/dev/null || true
  rm -f $MOUNT
  mkdir -p $MOUNT /storage/.config/system.d
  cat > /storage/.config/system.d/storage-sdcard.mount <<UNIT
[Unit]
Description=ROM card
Requires=blockdev@dev-disk-by\\\\x2dlabel-$LABEL.target
After=blockdev@dev-disk-by\\\\x2dlabel-$LABEL.target

[Mount]
What=/dev/disk/by-label/$LABEL
Where=$MOUNT
Type=ext4
Options=rw,noatime

[Install]
WantedBy=local-fs.target
UNIT
  systemctl daemon-reload
  systemctl enable --now storage-sdcard.mount
  findmnt -no SOURCE,TARGET,FSTYPE $MOUNT
"

say "restoring $BYTES_B bytes"
export SSHPASS="${MARTYGAMES_BOX_PASS:-coreelec}"
sshpass -e rsync -a --info=progress2 -e "ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR" \
  "$BACKUP"/ "${MARTYGAMES_BOX:-root@192.168.50.113}:$MOUNT/"

say "verifying every file back on the card"
$BOX "cd $MOUNT && find . -type f -exec stat -c '%s %n' {} + 2>/dev/null | sort" > /tmp/card-after.$$
find "$BACKUP" -type f -printf '%s ./%P\n' | sort > /tmp/card-want.$$
if diff -q /tmp/card-after.$$ /tmp/card-want.$$ >/dev/null; then
  echo "   all $FILES files match by path and size"
else
  echo "   MISMATCH:"; diff /tmp/card-after.$$ /tmp/card-want.$$ | head -20
  rm -f /tmp/card-after.$$ /tmp/card-want.$$
  exit 1
fi
rm -f /tmp/card-after.$$ /tmp/card-want.$$

say "re-baselining the pre-flash snapshot against the new card"
"$HERE/snapshot-state.sh" before >/dev/null && echo "   state-before.txt rewritten"

echo
echo "done. The card is ext4, labelled $LABEL, mounted at $MOUNT by label."
