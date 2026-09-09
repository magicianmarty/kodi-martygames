# systemd drop-ins for the box

Copied to `/storage/.config/system.d/` on the box, which systemd reads directly
and which survives a CoreELEC image update - so these do not need a reflash and
are not lost when the image is rebuilt.

    scp -r system.d/* root@<box>:/storage/.config/system.d/
    ssh root@<box> systemctl daemon-reload

`kodi.service.d/cpu-affinity.conf` keeps Kodi on the A73 cluster. Without it the
scheduler moves emulator threads onto the A53 cores and PSP emulation skips
audio and video together every few seconds.
