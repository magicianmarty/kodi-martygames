#!/usr/bin/env bash
# Everything that has to happen after the box boots a new image, in one run.
#
#   ./tools/post-flash.sh            # check only, changes nothing
#   ./tools/post-flash.sh --apply    # do the wrapper swap too
#
# Phase 2 of ROADMAP.md is not optional tidy-up: the new Kodi sets
# ADDON_INSTANCE_VERSION_GAME_MIN=8.0.0 and will refuse the hand-built ABI-6
# game.libretro, so games stop launching until it is replaced. The 13 core
# add-ons are ABI-agnostic - game.libretro.pcsx-rearmed.so exports only retro_*,
# no ADDON_Create - so they carry over untouched and are left alone here.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$HERE/box"
APPLY="${1:-}"

say() { printf '\n== %s\n' "$*"; }
ok()  { printf '   ok    %s\n' "$*"; }
bad() { printf '   FAIL  %s\n' "$*"; FAILED=1; }
FAILED=0

say "what booted"
$BOX 'grep -E "^(VERSION|BUILD_ID)=" /etc/os-release'

say "game ABI the new Kodi wants"
MIN=$($BOX 'grep -roE "ADDON_INSTANCE_VERSION_GAME_MIN[^0-9]*[0-9.]+" /usr/include/kodi 2>/dev/null | head -1' || true)
[ -n "$MIN" ] && echo "   $MIN"
WRAPPER=$($BOX 'grep -oE "instance.game\" minversion=\"[0-9.]+\"" /storage/.kodi/addons/game.libretro/addon.xml 2>/dev/null | head -1' || true)
echo "   installed wrapper: ${WRAPPER:-none}"

case "$WRAPPER" in
  *6.0.0*)
    if [ "$APPLY" = "--apply" ]; then
      say "retiring the hand-built ABI-6 wrapper"
      $BOX 'rm -rf /storage/.kodi/addons/game.libretro && echo removed'
      echo "   now install game.libretro from the CoreELEC repo in the Kodi UI,"
      echo "   then re-run this script without --apply"
    else
      bad "ABI-6 wrapper still installed - re-run with --apply"
    fi
    ;;
  *8.0.0*)
    ok "wrapper declares ABI 8"
    # addon.xml alone is not enough. Kodi's updater replaces the whole add-on,
    # but a Kodi already running holds the *old* library path in its add-on
    # database - it logged "Could not locate game.libretro.so.22.5.0" while the
    # directory contained 22.7.0, and every game refused to launch.
    LIB=$($BOX 'grep -oE "library_linux=\"[^\"]+\"" /storage/.kodi/addons/game.libretro/addon.xml | cut -d\" -f2')
    if [ -n "$LIB" ] && $BOX "test -f /storage/.kodi/addons/game.libretro/$LIB"; then
      ok "library $LIB is present"
    else
      bad "addon.xml names $LIB but that file is not there"
    fi
    if $BOX 'grep -q "Could not locate game.libretro" /storage/.kodi/temp/kodi.log 2>/dev/null'; then
      bad "Kodi is still looking for the old library - restart it: systemctl restart kodi"
    fi
    ;;
  "")      bad "no game.libretro installed - install it from the repo" ;;
  *)       bad "unexpected wrapper ABI: $WRAPPER" ;;
esac

say "cores still present"
$BOX 'n=$(ls -d /storage/.kodi/addons/game.libretro.* 2>/dev/null | wc -l); echo "   $n core add-ons"'

say "library still scans"
"$HERE/snapshot-state.sh" after >/dev/null
if [ -f "$HERE/../state-before.txt" ]; then
  if diff -q <(grep -A12 "games per system" "$HERE/../state-before.txt") \
             <(grep -A12 "games per system" "$HERE/../state-after.txt") >/dev/null; then
    ok "game counts unchanged"
  else
    bad "game counts changed:"
    diff -u <(grep -A12 "games per system" "$HERE/../state-before.txt") \
            <(grep -A12 "games per system" "$HERE/../state-after.txt") | sed 's/^/      /' || true
  fi
else
  bad "no state-before.txt to compare against"
fi

say "PS1 settings survived"
$BOX 'cat /storage/.kodi/userdata/addon_data/game.libretro.pcsx-rearmed/settings.xml 2>/dev/null | sed "s/^/   /"'
echo "   show_bios_bootlogo=enabled is the black-screen fix - see box-config/README.md"

say "skin"
$BOX 'echo "   home rows: $(grep -cE "<control type=\"list\" id=\"91[0-9][0-9]\">" /storage/.kodi/addons/skin.martyedition/xml/Home.xml)"'

say "hardware rendering (only meaningful on the Phase 4 image)"
$BOX 'if grep -q "Hardware rendering not implemented" /storage/.kodi/temp/kodi.log 2>/dev/null; then
        echo "   still refused - this is the stock image"
      else
        grep -E "RetroPlayer\[REND(ER|ERING)\]" /storage/.kodi/temp/kodi.log 2>/dev/null | tail -5 | sed "s/^/   /" || echo "   nothing logged yet - launch a game"
      fi'

say "audio smoothing (1036, 1037)"
$BOX 'log=/storage/.kodi/temp/kodi.log
      flushes=$(grep -c "RetroPlayer\[AUDIO\]: Flushing" $log 2>/dev/null || echo 0)
      echo "   flushes this session: $flushes  (was 2 per 90s before 1036)"
      grep -E "RetroPlayer\[AUDIO\]: Buffer .* ms, rate" $log 2>/dev/null | tail -4 | sed "s/^/   /" \
        || echo "   no rate-control lines yet - launch a game and give it 10s"'

say "run-ahead (1038)"
$BOX 'log=/storage/.kodi/temp/kodi.log
      grep -E "RetroPlayer\[RUNAHEAD\]" $log 2>/dev/null | tail -5 | sed "s/^/   /" \
        || echo "   nothing logged - run-ahead is off unless a game sets it"'

say "per-game settings reach RetroPlayer (1039)"
# The three properties only exist in a patched build; their absence means the
# image is older than the patches, not that nothing has set them.
$BOX 'if strings /usr/lib/kodi/kodi.bin 2>/dev/null | grep -q "retroplayer.videofilter"; then
        echo "   ok    kodi.bin carries the launch-override properties"
      else
        echo "   FAIL  kodi.bin has no retroplayer.* properties - pre-1039 image"
      fi'

echo
if [ "$FAILED" = 0 ]; then
  echo "all checks passed"
else
  echo "something needs attention - see FAIL lines above"
  exit 1
fi
