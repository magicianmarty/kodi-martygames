#!/bin/bash
# Launch an installed game under dosbox-x and photograph it.
#   smoke.sh <conf> <seconds> <shotdir>
set -u
CONF=$1; SECS=$2; SHOTDIR=$3
mkdir -p "$SHOTDIR"

Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
XPID=$!
export DISPLAY=:99
for _ in $(seq 30); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.2; done

timeout -k 5 "${SECS}s" dosbox-x -conf "$CONF" -nolog >"$SHOTDIR/dosbox.log" 2>&1 &
DBX=$!

i=0
while [ $i -lt $((SECS / 5)) ]; do
  sleep 5
  i=$((i + 1))
  import -window root "$SHOTDIR/$(printf 'run-%02d' $i).png" >/dev/null 2>&1
  # Title screens wait for a keypress; a game that never gets one looks
  # identical to a game that hung.
  xdotool key --clearmodifiers Return >/dev/null 2>&1
done

kill -9 $DBX 2>/dev/null
kill -9 $XPID 2>/dev/null
wait 2>/dev/null
exit 0
