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
