#!/bin/sh
# stream.sh <app> <host> <resolution> <fps> <bitrate-kbps> <codec>
#
# Must run detached from Kodi: it SIGSTOPs kodi.bin for the duration, and the
# add-on that starts it is a thread inside kodi.bin, so anything waiting here
# would stop with it.
set -u

APP="$1"; HOST="$2"; RES="$3"; FPS="$4"; RATE="$5"; CODEC="$6"

LUNA=/storage/.kodi/addons/script.luna
export LD_LIBRARY_PATH="$LUNA/lib:${LD_LIBRARY_PATH:-}"
cd "$LUNA/bin" || exit 1

# The OSD planes keep scanning out the frozen Kodi frame over the video layer
# unless they are blanked.
echo 1 > /sys/class/graphics/fb0/blank
echo 1 > /sys/class/graphics/fb1/blank
echo 0 > /sys/class/video/disable_video

killall -STOP kodi.bin

[ -f stream.log ] && mv stream.log stream.log.old
./moonlight stream -app "$APP" -"$RES" -"$FPS"fps -bitrate "$RATE" \
    -codec "$CODEC" -platform aml "$HOST" >> stream.log 2>&1

killall -CONT kodi.bin

echo 0 > /sys/class/graphics/fb0/blank
echo 0 > /sys/class/graphics/fb1/blank
