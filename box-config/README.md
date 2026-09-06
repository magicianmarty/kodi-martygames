# Box configuration

Files that live on the CoreELEC box but are worth version-controlling, since
they are hand-built and a Kodi/addon update can lose them.

## keymaps/ -> `/storage/.kodi/userdata/keymaps/`

- **game-buttons.xml** — Kodi's global joystick keymap binds `b=Back`,
  `x=ContextMenu`, `y=FullScreen`. In a game those must reach the emulator.
  The actions here are **empty**, which *removes* the inherited binding.
  Using `noop` instead would *consume* the press and the game would never see
  it — that exact mistake made B/X/Y dead in every emulator.
  Exit a game with **hold Back/View + Start/Menu**.
- **game-osd.xml** — Kodi's `joystick.xml` defines no section for any of the
  in-game dialogs (`GameOSD`, `GameSaves`, `GameControllers`...), so they fall
  back to `<global>` — which does give them up/down/left/right/a/b. What it
  also gives them is `guide` and `back` mapped to `ActivateWindow(Home)`, which
  drops out of the game entirely; this rebinds both to Back so the button that
  opens the OSD closes it.

  **Do not bind directions under `<FullscreenGame>`.** While a game is loaded
  `CPortInput::RegisterInput` puts its own keymap handler *in front of* the
  emulator's, and that handler hard-codes its window to `FullscreenGame`
  (`CPortInput::GetWindowID`). Anything bound there is consumed before the game
  sees it, so `<down>Down</down>` would kill the d-pad in every emulator. It is
  also unnecessary: the OSD pauses the game, the emulator's handler then stops
  accepting input, and the press falls through to the peripheral's own keymap,
  which uses the real window id.
- **mouse-wheel.xml** — vertical wheel moves between rows rather than
  scrolling a horizontal carousel sideways. Horizontal wheel is not mappable:
  the parser accepts only leftclick/rightclick/middleclick/doubleclick/
  longclick/wheelup/wheeldown/mousedrag*/mousemove/mouserdrag*.

## buttonmaps/ -> `/storage/.kodi/userdata/addon_data/peripheral.joystick/resources/buttonmaps/xml/udev/`

**Xbox_Wireless_Controller_v045E_p0B20_16b_8a.xml** — hand-written. Kodi ships
`Xbox_Wireless_Controller_15b_9a.xml`, but the firmware-updated pad enumerates
as 16 buttons / 8 axes over BLE with pid 0B20, so nothing matched and the pad
did nothing. Matching is by provider + name + vid/pid + exact counts.

Covers 11 controller profiles, because Kodi does **not** translate between
them — each emulated system uses its own feature names and needs its own
`<controller>` section:

| Core | Profile required |
|---|---|
| mame2003_plus, prboom, tyrquake, scummvm, vice_x64 | default |
| genplus | genesis.3button, genesis.6button |
| pcsx-rearmed | ps.gamepad, ps.dualshock, ps.dualanalog |
| nestopia | nes |
| uae | amiga.pro.joystick, amiga.cd32 |
| dosbox-pure | gravis.gamepad |

Button indices were decoded from the evdev bitmaps (ascending code order):
`0=KEY_RECORD 1=A 2=B 4=BTN_NORTH 5=BTN_WEST 7=LB 8=RB 11=View 12=Menu
13=Guide 14=L3 15=R3`; axes `0/1=Lstick 2/3=Rstick 4=GAS 5=BRAKE 6/7=d-pad`.

## ports/ -> `/storage/.kodi/userdata/addon_data/<core>/ports.xml`

Overrides which controller a core's port gets. Without it Kodi binds the
**first** profile the core's topology accepts — and uae lists `amiga.cd32`
before `amiga.pro.joystick`, so every Amiga game got a CD32 pad.

Neither removing the profile from the buttonmap nor disabling the
`game.controller.amiga.cd32` addon changes the binding; only `ports.xml` does.

Schema (undocumented, determined by testing against the loader's own errors —
`<accepts>` is rejected with *"Inside \<port\> tag: Ignoring \<accepts\> tag"*):

```xml
<ports>
  <port type="controller" id="1">
    <controller id="game.controller.amiga.pro.joystick"/>
  </port>
</ports>
```

## addon_data/ -> `/storage/.kodi/userdata/addon_data/<addon>/settings.xml`

**game.libretro.pcsx-rearmed** — four non-default settings, each fixing a
symptom that took a long time to trace. None are cosmetic.

| Setting | Why |
|---|---|
| `show_bios_bootlogo=enabled` | **Every PS1 game rendered a black screen without this.** It is the only option that sets `Config.SlowBoot`; the default fast-boots straight into the game executable and skips the BIOS, so the GPU is never initialised, `vout_set_mode()` is never called again and every frame handed to Kodi is blank. Costs a few seconds of real BIOS boot. |
| `gpu_slow_llists=disabled` | Games rendered 26 of 60 frames. This is a compatibility hack that deliberately slows the emulated GPU; off, Tekken 3 holds a solid 60/60. **Suspect this first if a game glitches** — put it back to `auto`. |
| `gpu_thread_rendering=enabled` | Moves the software rasteriser to its own core. Changed at the same time as the above, so its individual contribution is unverified. |
| `neon_interlace_enable_v2=disabled` | Fight scenes run 368x480 interlaced and the NEON GPU renders alternating fields by default, which shreds moving objects into displaced horizontal bands. Full-frame rendering fixes it. A CRT shader hides the artefact, which is why it only became obvious with the shader off. |

Diagnosing these: `display_fps_v2=extra` draws the core's own HUD, and the
string is `FPS: <flip_cnt>/<psx_vsync_count>` — **left is the game's own render
rate, right is emulation speed**. `30/60` on Driver is that game being 30fps by
design, not a fault. `DRC: n` in the same HUD proves the dynarec is live.

## Game video filter: leave it empty

`guisettings.xml` → `<defaultgamesettings><videofilter>` was set to
`game.shader.presets/resources/glsl/xbrz/4xbrz-linear.glslp`. 4x xBRZ is a
per-pixel upscaling filter and the Mali G52 in this box cannot run it at 60 Hz,
so RetroPlayer paces the emulator down to whatever the GPU manages. Measured on
Sonic (Genesis Plus GX), GameLoop CPU over 5 s:

| | GameLoop |
|---|---|
| 4xbrz-linear.glslp | **8 %** |
| no filter | **21 %** |

2.6x more emulation getting done with it off, and it applied to *every* system,
which is why Mega Drive of all things was crawling.

It only started biting after the ABI-8 flash. The hand-built ABI-6
`game.libretro` almost certainly ignored shader presets, so the setting sat
there inert; the stock 22.7.0.2 wrapper implements them, so the same setting
suddenly cost real frames. Worth remembering before blaming a build: **a setting
that was harmless under the old wrapper is not necessarily harmless now.**

If you want a filter, try a cheap one and measure the same way - the
`GameLoop` thread's CPU over five seconds is a good proxy for frames actually
emulated.
