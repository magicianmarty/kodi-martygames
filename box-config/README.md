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
