#!/usr/bin/env bash
# Measure the ROM card, the way the box actually uses it.
#
#   ./tools/card-speed.sh
#
# Sequential numbers are what the card is sold on. The one that decides whether
# the library feels quick is the small-file walk: the scanner stats every one of
# ~13,000 files, and 12,804 of those are DOS files averaging under 400 KB.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$HERE/box"
CARD=/storage/sdcard
SIZE_MB="${SIZE_MB:-1024}"

echo "== card"
$BOX "df -h $CARD | tail -1; blkid \$(readlink -f /dev/disk/by-label/MARTYROMS 2>/dev/null || echo /dev/mmcblk1p1) 2>/dev/null | sed 's/^/  /'"

echo
echo "== sequential write (${SIZE_MB} MB, fsync'd so the cache cannot lie)"
$BOX "
  dd if=/dev/zero of=$CARD/.speedtest bs=1M count=$SIZE_MB conv=fsync 2>&1 | tail -1 | sed 's/^/  /'
"

echo
echo "== sequential read (caches dropped first)"
$BOX "
  sync; echo 3 > /proc/sys/vm/drop_caches
  dd if=$CARD/.speedtest of=/dev/null bs=1M 2>&1 | tail -1 | sed 's/^/  /'
  rm -f $CARD/.speedtest
"

echo
echo "== small-file walk (what the library scan actually does)"
$BOX "
  sync; echo 3 > /proc/sys/vm/drop_caches
  start=\$(date +%s%N)
  n=\$(find $CARD/roms -type f -exec stat -c '%s' {} + 2>/dev/null | wc -l)
  end=\$(date +%s%N)
  ms=\$(( (end - start) / 1000000 ))
  echo \"  stat'd \$n files in \${ms} ms\"
  [ \"\$n\" -gt 0 ] && echo \"  \$(( n * 1000 / (ms>0?ms:1) )) files/sec\"
"

echo
echo "== for comparison, the old card was exfat through FUSE"
echo "   (userspace, one context switch per operation - this is the number that changed)"
