# Installing the custom image

Phase 1 of `ROADMAP.md`. Written before the first flash, so the steps are
decided while nothing is on fire.

## Read this first: the stick in the box changes what a reboot does

**The recovery stick is already made, verified, and currently plugged in** —
SanDisk Cruzer Blade, `sda1` vfat `COREELEC` + `sda2` ext4 `STORAGE`, holding
stock CoreELEC 22.0-Piers_beta1 (`Generic`) with `dtb.img` set to
`g12b_s922x_ugoos_am6b.dtb` (md5 `b3af99fc…`, identical to `/flash/dtb.img`).
`SYSTEM` and `kernel.img` both match their `.md5`.

That means **the next power-on boots the stick, not the internal install.**
Read from the box's own u-boot environment, not guessed:

```
bootcmd     = ... run bootfromsd; run bootfromusb; run bootfromemmc
bootfromsd  = if mmcinfo; then run cfgloadsd; if fatload mmc 0 ... kernel.img; then ... fi; fi
bootfromusb = usb start 0; run cfgloadusb; if fatload usb 0 ... kernel.img; then ... fi
cfgloadusb  = if fatload usb 0:1 ${loadaddr} cfgload; then ...; autoscr ${loadaddr}; fi
```

SD → USB → internal eMMC, automatically, every power-on. `bootfromnand=0`.
Nothing to press: no toothpick, no reset pinhole, no boot-order setting.

- **SD falls through.** The 119 GB ROM card is `/dev/mmcblk1p1`, **exfat**.
  U-boot's `fatload` cannot read exfat, so both `cfgload` and `kernel.img`
  fail and the stage is skipped. This is why the box boots internally today.
- **USB does not fall through.** `cfgloadusb` finds `cfgload` on `sda1` and
  `autoscr` runs it; that script ends in `fatload kernel.img` + `bootm`, so
  the stick boots. Its kernel gets `boot=LABEL=COREELEC disk=LABEL=STORAGE`,
  which resolves to the stick's own two partitions.

Nothing on the box is at risk from this. The internal filesystems are labelled
`CE_FLASH` and `CE_STORAGE`, so a USB boot cannot even name them, let alone
write to them. It is a live boot of a blank stock system — no games, no skin,
no add-ons — and pulling the stick and rebooting brings the real one straight
back.

**`aml_autoscript` on the stick does not run on a normal boot.** `bootcmd`
never references it; only the Amlogic recovery/upgrade path does. Worth knowing
what it *would* do if that path were ever triggered: `defenv` (reset the u-boot
environment to defaults) then rewrite the boot variables and `saveenv`. It does
not write eMMC, but it does permanently replace the environment printed above.

### The consequence for the flash

The update tar is read from `/storage/.update` **of whatever device booted**.
Copy it to internal storage, reboot with the stick still in, and the box boots
the stick, looks at the *stick's* empty `/storage`, finds no update, and comes
up stock. Nothing breaks, but nothing installs either — and it looks exactly
like a failed flash.

> **The stick must be out of the box for the update to apply.**

Do the confirmation power-cycle first and you get the recovery rehearsal for
free: stick in → stock CoreELEC; stick out → your setup returns. After that,
flash with the stick on the desk and put it back only if something goes wrong.

## Installing

1. **Refresh the backup.** rsync, so it costs seconds:
   ```sh
   ./tools/backup-box.sh
   ```

2. **Capture the before state:**
   ```sh
   ./tools/snapshot-state.sh before
   ```

3. **Pull the recovery stick out of the box.** See above. Not optional.

4. **Copy the image and reboot.** CoreELEC's supported update path — it unpacks
   on boot and replaces `/flash`, leaving `/storage` alone:
   ```sh
   ./tools/box 'mkdir -p /storage/.update'
   scp target/CoreELEC-Amlogic-no.aarch64-*.tar root@192.168.50.113:/storage/.update/
   ./tools/box 'sync; reboot'
   ```
   First boot takes several minutes — it is unpacking a new system. Do not pull
   power.

   The tar's payload is only `target/SYSTEM`, `target/KERNEL` and their md5s —
   **no dtb**, so `/flash/dtb.img` (the AM6B+ device tree) survives untouched.
   `check_is_compatible()` in the init script compares project/arch against
   `Amlogic-no.aarch64`, which is what we built.

   **There are two images. Flash them in order.**

   | | |
   |---|---|
   | **Phase 1** | `CoreELEC-Amlogic-no.aarch64-22.0-Piers_devel_20260906014435.tar` |
   | | sha256 `8f3226e3ec06931f32981e79e9d618cdcf5230d111c71013df7e8d8ce794a515` |
   | | Unmodified CoreELEC. Kodi game ABI 6.0.0 → **8.0.0** |
   | **Phase 4** | `CoreELEC-Amlogic-no.aarch64-22.0-Piers_devel_20260906041600.tar` |
   | | sha256 `03db25bce7a08845abd87e9ad8cbf651ca01fc9132eef1babc81c7a0cadd6684` |
   | | Adds the RetroPlayer FBO patches (1016-1020) |

   Flash the first one, work through step 5 and Phase 2, and confirm all seven
   systems still launch. Only then flash the second. That way a problem on the
   first flash is a toolchain or device problem and nothing else, and a problem
   on the second is our patches — which is a much shorter list to search.

5. **Verify:**
   ```sh
   ./tools/snapshot-state.sh after
   diff -u state-before.txt state-after.txt
   ```
   Expect: `BUILD_ID` changes, Kodi version changes, `kodi.binary.instance.game`
   goes **6.0.0 → 8.0.0**. Expect *no change* to the game counts (215 across 7
   systems), artwork (205/193), metadata (203), keymaps, or emulator settings.

## After it boots: one command

```sh
./tools/post-flash.sh            # check only
./tools/post-flash.sh --apply    # plus the wrapper swap
```

It reports what booted, whether the wrapper is on the right ABI, that all
twelve cores are still there, that the game counts match `state-before.txt`,
that the PS1 settings survived, that the skin still has its rows, and what
RetroPlayer logged. Dry-run against the *current* box it correctly reports one
failure - the ABI-6 wrapper - and passes everything else, so a clean run after
the flash means something.

## Phase 2, immediately after

ABI 8 means the hand-built wrapper is obsolete — the new Kodi sets
`ADDON_INSTANCE_VERSION_GAME_MIN=8.0.0` and will refuse to load it, so this is
not optional cleanup, it is what makes games launch again:

```sh
./tools/box 'rm -rf /storage/.kodi/addons/game.libretro'
# then install game.libretro from the CoreELEC repo in the Kodi UI
```

Re-check the PS1 settings survive — `show_bios_bootlogo=enabled` is a *core*
setting and should carry over, but `gpu_slow_llists` and the interlace fix want
re-testing against a newer wrapper. See `box-config/README.md` for why each is
set.

## If it does not come back

1. Power off, put the recovery stick in, power on. It boots stock CoreELEC
   from USB, as traced above.
2. From there `/flash` and `/storage` are both mountable — follow
   `kodi-martygames-backups/RESTORE.md`.
3. The internal install is untouched by booting from USB; you can also simply
   remove the stick and power-cycle to go back to whatever is on eMMC.

**Do not flash unattended.** The recovery path is only useful if someone can
put the stick in.
