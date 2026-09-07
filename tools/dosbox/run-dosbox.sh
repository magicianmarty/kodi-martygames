#!/bin/bash
# Run an installer under dosbox-x on a virtual display, with drive-install.py
# watching the screen and answering it.
#   run-dosbox.sh <conf> <seconds> <shotdir> <outdir> <title>
#
# dosbox-x ignores SIGTERM once a DOS program has the CPU, so the time limit is
# enforced by timeout(1) with a SIGKILL follow-up rather than by waiting on it.
set -u
CONF=$1; SECS=$2; SHOTDIR=$3; OUTDIR=$4; TITLE=${5:-}
mkdir -p "$SHOTDIR"

Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >/dev/null 2>&1 &
XPID=$!
export DISPLAY=:99
for _ in $(seq 30); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.2; done

timeout -k 5 "${SECS}s" dosbox-x -conf "$CONF" -nolog >"$SHOTDIR/dosbox.log" 2>&1 &
DBX=$!

sleep 3
python3 /drive-install.py "$SHOTDIR" "$OUTDIR" "$((SECS - 5))" "$TITLE"

kill -9 $DBX 2>/dev/null
kill -9 $XPID 2>/dev/null
wait 2>/dev/null
rm -f "$SHOTDIR/cur.png"
exit 0
