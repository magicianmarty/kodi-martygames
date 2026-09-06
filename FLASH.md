# Installing the custom image

Phase 1 of `ROADMAP.md`. Written before the first flash, so the steps are
decided while nothing is on fire.

## Before anything

**The recovery stick is already made and verified** — SanDisk Cruzer Blade,
currently in the box's USB port, holding stock CoreELEC 22.0-Piers_beta1
(`Generic`) with `dtb.img` set to `g12b_s922x_ugoos_am6b.dtb`, md5-identical to
the box's own. `SYSTEM` matches its manifest.

**How this box boots** — read from its u-boot environment, not guessed:

```
bootcmd = ... run bootfromsd; run bootfromusb; run bootfromemmc
```

SD → USB → internal eMMC, automatically, every power-on. `bootfromnand=0`.
Each stage only boots if it finds `kernel.img` on a FAT partition, so
non-bootable media falls straight through — which is why the box boots
internally today despite the 119 GB ROM card in the SD slot.

**Nothing to press.** No toothpick, no reset pinhole, no boot-order setting.

### The one thing to confirm first
`bootfromusb` reads `usb 0` specifically:

```
bootfromusb = usb start 0; run cfgloadusb; if fatload usb 0 ${loadaddr} kernel.img; ...
```

If the stick does not enumerate as USB device 0 it will be skipped and the box
will boot internally as normal — harmless, but it means recovery is not armed.
**Power-cycle with the stick in and confirm stock CoreELEC comes up.** If it
does not, move the stick to the other port and retry before flashing anything.

## Installing

1. **Refresh the backup.** rsync, so it costs seconds:
   ```sh
   ./tools/backup-box.sh
   ```

2. **Capture the before state:**
   ```sh
   ./tools/snapshot-state.sh before
   ```

3. **Copy the image and reboot.** CoreELEC's supported update path — it unpacks
   on boot and replaces `/flash`, leaving `/storage` alone:
   ```sh
   ./tools/box 'mkdir -p /storage/.update'
   scp target/CoreELEC-Amlogic-no.aarch64-*.tar root@192.168.50.113:/storage/.update/
   ./tools/box 'sync; reboot'
   ```
   First boot takes several minutes — it is unpacking a new system. Do not pull
   power.

4. **Verify:**
   ```sh
   ./tools/snapshot-state.sh after
   diff -u state-before.txt state-after.txt
   ```
   Expect: `BUILD_ID` changes, Kodi version changes, `kodi.binary.instance.game`
   goes **6.0.0 → 8.0.0**. Expect *no change* to the game counts (215 across 7
   systems), artwork (205/193), metadata (203), keymaps, or emulator settings.

## Phase 2, immediately after

ABI 8 means the hand-built wrapper is obsolete:

```sh
./tools/box 'rm -rf /storage/.kodi/addons/game.libretro'
# then install game.libretro from the CoreELEC repo in the Kodi UI
```

Re-check the PS1 settings survive — `show_bios_bootlogo=enabled` is a *core*
setting and should carry over, but `gpu_slow_llists` and the interlace fix want
re-testing against a newer wrapper. See `box-config/README.md` for why each is
set.

## If it does not come back

1. Power off, confirm the recovery stick is in, power on. It boots stock
   CoreELEC from USB.
2. From there `/flash` and `/storage` are both mountable — follow
   `kodi-martygames-backups/RESTORE.md`.
3. The internal install is untouched by booting from USB; you can also simply
   remove the stick and power-cycle to go back to whatever is on eMMC.

**Do not flash unattended.** The recovery path is only useful if someone can
put the stick in.
