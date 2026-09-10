# systemd drop-ins for the box

Copied to `/storage/.config/system.d/` on the box, which systemd reads directly
and which survives a CoreELEC image update - so these do not need a reflash and
are not lost when the image is rebuilt.

    scp -r system.d/* root@<box>:/storage/.config/system.d/
    ssh root@<box> systemctl daemon-reload

`kodi.service.d/cpu-affinity.conf` keeps Kodi on the A73 cluster. Without it the
scheduler moves emulator threads onto the A53 cores and PSP emulation skips
audio and video together every few seconds.

`kodi-bin-override.service` bind-mounts `/storage/kodi-martyedition/kodi.bin`
over `/usr/lib/kodi/kodi.bin` before Kodi starts. `/` is squashfs and read-only,
so a patched binary cannot replace the image one in place, and reflashing the
whole image to test a Kodi patch costs a build and a boot. Drop the new binary
in and restart Kodi instead.

To go back to the image's own Kodi, `systemctl disable --now
kodi-bin-override.service` and restart Kodi; the unit also no-ops on its own if
`/storage/kodi-martyedition/kodi.bin` is missing.

