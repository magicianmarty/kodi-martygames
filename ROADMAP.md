# Roadmap: everything in one interface

Three strands of work, in dependency order: a maintained CoreELEC fork that
unlocks the emulators Kodi currently refuses, new shelves on the home screen,
and a game ingest pipeline.

Written 2026-09-06. Every claim in "What we know" was checked against the box or
upstream source on that date; anything unverified is called out as such.

---

## 1. What we know

**It is not a Kodi fork.** CoreELEC builds *stock* Kodi from an xbmc release
tarball and applies 22 numbered patches from
`packages/mediacenter/kodi/patches/` (`1001-add-libreelec.tv-RSS-news.patch`
through `1015-…`). Our changes are additional patch files in that directory,
carried in a fork of **CoreELEC**, not of Kodi. This is the single most
important fact in this document: it turns "maintain a fork of a million-line
media centre" into "maintain a patch series with a numbering convention that
already exists".

**Rebuilding gets us Game ABI 8 for free.**

| Kodi | `ADDON_INSTANCE_VERSION_GAME` |
|---|---|
| 22.0b1-Piers (on the box today) | `6.0.0` |
| 22.0b2-Piers (what `coreelec-22` pins today) | `8.0.0` |
| master | `8.0.0` |

So a build from CoreELEC's current tree **retires the hand-built ABI-6
`game.libretro` wrapper entirely** and lets us install the stock
`game.libretro 22.7.0.x` from the repo. That kills a whole class of problems:
see [[coreelec-game-abi-mismatch]] and the four wrapper bugs catalogued in
`~/dev/coreelec-game.libretro-abi6/`. This is a large win available before any
new feature work.

**Cores are CoreELEC packages.** `packages/emulation/` holds 80 of them
(`libretro-pcsx-rearmed`, `libretro-beetle-saturn`, …). Adding an emulator means
adding a package there in the same shape. `libretro-mupen64plus-nx` **already
exists**; there is no ppsspp, flycast, reicast or redream package.

**The hardware-rendering gap is one class.** Kodi's game-client side is
complete — `CGameClientStreamHwFramebuffer` implements open, close, `GetBuffer`
and the context-reset callback, and `RenderBufferOpenGLES`,
`RenderBufferPoolOpenGLES` and `RenderBufferDMA` all exist. So does our side:
the wrapper already implements `EnableHardwareRendering()`,
`GetHwFramebuffer()`, `RenderHwFrame()` and forwards `get_proc_address`.

What is missing is `CRetroPlayerRendering::OpenStream`, which is a stub:

```cpp
//! @todo
const AVPixelFormat pixelFormat = AV_PIX_FMT_NONE;
const unsigned int width = 640;      // hardcoded
//! @todo: This must be called from the rendering thread
//return m_renderManager.Create(width, height);
return false;
```

…and `CGameClientStreams::EnableHardwareRendering()`, which logs
*"Hardware rendering not implemented"* and returns false. **Still stubbed on
Kodi master** (3 `@todo`s as of today), so this is novel work, not a backport.

**`requires_opengl` in a core's `addon.xml` predicts exactly what is blocked.**
Checked across all 75 cores in the repo: only **`mupen64plus-nx`** and **`vecx`**
declare `true`. Everything else is software-rendered and works today.

**The game-exit crash is ours to fix once we build — but the cause is not what
I first said.** The crash is real and reproducible (exit any game), and the
stack runs `CAgentInput::UpdateConnectedJoysticks` → `CPortInput::RegisterInput`
→ `CAddonInputHandling::Load`, racing `CGameClientInput::CloseJoysticks()`.

I described it as a use-after-free of the `CGameClientJoystick`. **That is
wrong.** Reading 22.0b2:

```cpp
using JoystickMap = std::map<PortAddress, std::shared_ptr<CGameClientJoystick>>;
```

Both owners hold `shared_ptr` — `CGameClientInput::m_joysticks` and
`CAgentInput::m_portMap` — so erasing from one cannot free a joystick the other
still references. `CloseJoystick()` also takes a peripheral event lock *before*
erasing, and that lock blocks until in-flight input is drained.

So the dangling object is something else — most likely reached via
`CAddonInputHandling::Load()`'s `m_peripheral`/`m_addon`, or the frames are
mis-attributed through inlining, which crashlog symbolisation does routinely.

**This is now gated on Phase 1**, not the other way round: diagnosing it needs a
debug build with symbols, which needs the build pipeline. Writing a threading
fix against a disproven theory and flashing it to the only media box in the
house would be worse than leaving the crash alone.

---

## 2. Answering the question directly

> If RetroArch can do PSP, Dreamcast and Saturn, could our fork do this too?

**PSP, Dreamcast and N64: yes**, once hardware rendering lands and the cores are
packaged. There is nothing special about RetroArch here — it simply gives cores
a GL context, which is precisely the thing Kodi declines to do. Same SoC, same
Mali-G52, same cores.

**Saturn: no, and hardware rendering will not help.** `beetle-saturn` and
`yabause` are *already* software renderers — they are not blocked, they are
merely slow. Beetle Saturn is built for accuracy against fast x86; a 2.2 GHz
Cortex-A73 is unlikely to hold full speed no matter what we do to Kodi. The
Saturn question is a CPU question and belongs in Phase 6, not the fork.

**Realistic expectations once it works** (unverified on this SoC — these are the
open questions Phase 4/5 answer):

| System | Core | Expectation |
|---|---|---|
| N64 | mupen64plus-nx + GLideN64 | Good. Note `parallel-rdp` needs Vulkan, which Kodi's GBM/GLES stack does not provide — GLideN64 is the target |
| PSP | ppsspp | Good; PPSSPP is well optimised for ARM Mali |
| Dreamcast | flycast | Playable for much of the library; expect per-game tuning |
| Saturn | beetle-saturn | Probably below full speed regardless |

---

## 3. Phases

Ordered so that each phase delivers something usable on its own, and the
riskiest work happens only after the build pipeline is proven.

### Phase 0 — Recovery first
**Before flashing anything.** A custom image can brick the box, and everything
below depends on being able to get back.

- Confirm the Ugoos boots CoreELEC from SD/USB with the internal install intact
- Take a full backup of `/storage` (skin, plugin, keymaps, buttonmaps, saves,
  ROM tree inventory, `addon_data`)
- Write down the stock-image restore procedure and *test it once*
- Keep a known-good CoreELEC 22.0-Piers_beta1 image on hand

Effort: an evening. Non-negotiable.

### Phase 1 — Reproducible build, no changes
Fork CoreELEC, branch `marty-22` off `coreelec-22`, build an **unmodified**
image for `Amlogic-ng` / the AM6B+ device, install it, confirm the box still
works exactly as now.

This proves the toolchain before any patch exists, and it *already* delivers
Phase 2's ABI-8 win as a side effect.

Effort: a day of wall-clock, mostly build time. Risk: medium (first flash).

### Phase 2 — Retire the hand-built wrapper
On ABI 8, uninstall the hand-built `game.libretro`, install the stock
`game.libretro 22.7.0.x` from the repo, re-verify all eleven working systems.

Expect the four wrapper bugs to disappear, and re-test the PS1 settings — the
black-screen fix is a *core* setting (`show_bios_bootlogo`) and should carry
over, but `gpu_slow_llists` and the interlace fix want re-checking against a
newer wrapper.

Effort: a day. Risk: low. Value: high — this removes the most fragile component
in the whole stack.

### Phase 3 — Fix the game-exit crash
A patch to Kodi's game input teardown. Likely shapes: hold a lock across
`CloseJoysticks()` and the agent's `UpdateConnectedJoysticks()`, or make
`CPortInput` hold a weak reference to `m_gameInput` so a freed
`CGameClientJoystick` cannot be dereferenced by `CAddonInputHandling::Load()`.

**Do this after the flash, not before.** Checked 2026-09-06: the box's Kodi and
the one we built are **1,399 commits apart** on `CoreELEC/xbmc` — the box runs
the pin from 22.0-Piers_beta1 (2026-06-22), ours is 2026-09-04. That range
carries a lot of work in exactly this area, including
`Fix circular reference between CPeripheral and CAgentController` (the agent
controller is what holds game input alive) and a peripheral memory-leak fix,
plus several unrelated crash fixes. None of them names this crash, so this is
not a prediction — but re-testing costs one game launch and a debug build costs
days, so the order matters.

Only if it survives the flash: build a debug Kodi and get a real stack. We have
a reliable repro (exit any game). Do **not** start from the previous theory —
it was disproven, and `CGameClientInput::CloseJoystick()` erasing from
`m_joysticks` cannot free a `CGameClientJoystick` that anything else still
holds, because both sides hold `shared_ptr`.

Effort: a game launch, then a few days only if needed. Risk: medium — it is a
threading fix. Value: very high; it is the single most annoying defect on the
box, and it also trips CoreELEC safe mode after roughly three crashes.

**Strong upstream candidate.** Worth a Kodi PR regardless of whether we ship it
ourselves first.

### Phase 4 — Hardware rendering → N64
The hard one, and the reason this roadmap exists. Scoped against 22.0b2 source
on 2026-09-06, so this is a task list rather than a hope.

**Already done upstream — do not rewrite these:**

| Piece | State |
|---|---|
| `CGameClientStreamHwFramebuffer` | Complete: open, close, `GetBuffer`, context-reset callback |
| `CRPRenderManager::GetCurrentFramebuffer()` | **Complete.** Pulls a buffer from a visible pool and returns its GL framebuffer |
| `CRPStreamManager::GetHwProcedureAddress()` | Complete; delegates to `CRPProcessInfo` |
| Our wrapper | Complete: `EnableHardwareRendering()`, `GetHwFramebuffer()`, `RenderHwFrame()`, `get_proc_address` forwarding |

**What is actually missing** — rescoped 2026-09-06 after finding that Kodi
ships its own notes on this in-tree at
`xbmc/cores/RetroPlayer/OpenGL_Roadmap.md`. They point at
`garbear/xbmc` branch `retro-gl-v3` (lrusak's original work, rebased), which
turns out to sit on **current Kodi 22, not 2022** — the commit dates are author
dates. So the expensive part, the new buffer class, was already written.

Of its ten commits, four are wanted, and the other six are instructive:

| Commit | Verdict |
|---|---|
| `CRenderBufferFBO` + pool + `CRPRendererFBO` | **Ported.** Now patches 1016-1017 |
| `IGameLoopCallback::EndEvent` / `DestroyContext` | **Already merged upstream** in Kodi 22 — applying it duplicated a function |
| `RPRendererOpenGLES: use CRenderBufferFBO` | **Rejected.** Swaps the sysmem pool for the FBO pool, which would break all eleven working systems. Registered as its own factory instead |
| wayland `CRendererFactoryFBO` registration | **Replaced** by the GBM equivalent, patch 1018 |
| `[temp] disable DMA renderer` | **Rejected.** Scaffolding, and CoreELEC needs the DMA renderer for video |
| `[TEMP] use vaos`, `remove global VAO`, `CGLRenderHelper` | Deferred. GL-state hygiene for add-ons; not needed for a first frame |

The ported code needed four fixes before it was worth keeping — an
uninitialised texture name freed in the destructor, a texture left incomplete
by a mipmap filter with no mipmaps (which samples *black*, the failure mode we
have already chased once), no depth or stencil attachment at all, and a buffer
pool that claimed compatibility with every render setting. That last one
matters most: `CRPRenderManager::GetRendererForSettings()` walks the pools and
takes the first compatible one, so the upstream branch's FBO pool captured
software clients too — which is precisely why that branch also had to disable
the DMA renderer. Ours answers `false` until activated, so it is inert.

Separately, `CGameClientStreamHwFramebuffer::GetBuffer()` took the client's
width and height and then requested a `0x0` buffer, which is a request to
allocate a zero-sized texture. Fixed in patch 1019.

**So what is left is the wiring, not the machinery:**

1. **`CRPRenderManager::Create(width, height)`** — `//! @todo return false;`.
   Configure the FBO pool and call `Activate(depth, stencil)` on it.
2. **`CRPRenderManager::RenderFrame()`** — empty. Hand the finished buffer to
   the renderer.
3. **`CRetroPlayerRendering::OpenStream()`** — hardcodes 640×480 and
   `AV_PIX_FMT_NONE`, never calls `Create()`. `HwFramebufferProperties` already
   carries `depth`, `stencil`, `contextType` and the version.
4. **`CRetroPlayerRendering::CloseStream()`** — empty.
5. **`CGameClientStreams::EnableHardwareRendering()`** — already stores the
   properties; it then logs "not implemented" and returns false. **Flip this
   last.** Returning true before 1–4 work would tell a core it has a GL context
   and then fail it — the same defect as flycast's `requires_opengl=false`.
6. **`CRPProcessInfo::GetHwProcedureAddress()`** — a virtual returning
   `nullptr`. Needs a GBM override resolving through `eglGetProcAddress`.
7. **Thread affinity** — the design question is answered by the ported pool:
   it creates an EGL context *sharing object names with the window system's*
   and makes it current on the game loop thread, so the client renders there
   and Kodi's render thread samples the resulting texture. Teardown rides the
   already-merged `EndEvent()` callback, which fires on the game loop thread.
   What is unproven is whether that survives a mid-game resolution change.

Effort: **the remaining items are small, and item 7 is the one that can still
bite.** None of it can be validated until the box runs our image, so it is
gated on Phase 1 rather than on more reading.

**Strong upstream candidate** — a `@todo` Kodi has carried for years, and the
four fixes to the ported code stand on their own regardless of whether the
wiring lands.

### Phase 5 — Package the missing cores → PSP, Dreamcast
Add `packages/emulation/libretro-ppsspp` and `libretro-flycast` following the
existing 80-package pattern, plus the matching `game.libretro.*` addon
definitions so they appear as game clients.

**Verified 2026-09-06 against the live repo index.** `addons.coreelec.org/
Amlogic-no/22.0.10/aarch64` carries **75 game cores and neither of these two**,
so the fork really is the only route to PSP and Dreamcast. Both addon pins are
real and their tarballs hash as pinned (`0.0.1.30-Omega`, `7.0.0.66-Omega`).

**Both depend on Phase 4, including flycast — despite what its addon.xml says.**
`game.libretro.flycast` declares `<requires_opengl>false</requires_opengl>`,
which reads like a software core. It is not. `core/libretro/libretro.cpp` at our
pinned commit negotiates Vulkan, then GLES3, then GLES2, and ends:

```c
if (!foundRenderApi)
   return false;      // retro_load_game fails outright
```

There is no software rasteriser in the libretro build and no `HAVE_OPENGL=0`
switch in its Makefile. The declaration is simply wrong upstream, and it is
worse than a missing feature: `requires_opengl=true` is what makes Kodi *hide*
a core it cannot drive, which is why `mupen64plus-nx` sits inert rather than
failing. With the flag false, Kodi will offer flycast as a game client for every
`.chd`/`.gdi` and then fail at load. Do not ship it before Phase 4.
**Worth an upstream issue against kodi-game.**

Effort: days per core, mostly build plumbing and per-core option wiring. Risk:
low-ish once Phase 4 works — but PPSSPP in particular has a large surface of
renderer options to get right.

### Phase 6 — Saturn reality check
Independent of everything above; can be done today. Install `beetle-saturn`,
supply the BIOS (`sega_101.bin` / `mpr-17933.bin`), measure with the core's own
HUD (`FPS: flip_cnt/vsync_count` — see `box-config/README.md`). If it is too
slow, try `yabause` and accept the compatibility hit.

Effort: an evening, once ROMs and BIOS exist. Needs no fork.

**Confirmed available now.** Both `game.libretro.beetle-saturn 1.29.0.56.1` and
`game.libretro.yabause 0.9.15.68.1` are in the repo for this exact device, and
both declare `requires_opengl=false` — genuinely so, unlike flycast; Mednafen
Saturn is a pure software rasteriser. Only two of the 75 cores in the repo
require GL at all (`mupen64plus-nx` and `vecx`). So Saturn is gated on content,
not on us.

### Phase 7 — Shelves
Independent of the fork; can proceed in parallel.

**The Continue row** is the standout. Kodi already writes a real screenshot
beside every savestate (`/storage/.kodi/saves/<rom>/<timestamp>.jpg`, ~27 KB of
actual gameplay). Nothing uses them. A Continue shelf showing where you left off
rather than box art is mostly plumbing we have already built — the plugin
already reads that directory for last-played ordering.

Then, all driven by metadata we already hold for 203 games (year, genre,
players, developer, publisher, overview) and currently show only in the hero:

- Genre shelves — **done.** Platformers (64), Shooters (63), Strategy (28),
  Racing (14). Counts were checked before placing each row, which is why Puzzle
  (5) and Pinball (3) are absent — too thin to read as a shelf
- **"2 players"** — **done**
- "Never played" — **done**
- Decade shelves — **done**, but "The 1980s" (15), not "1990s": 183 of the 215
  games are from the 90s, so that row would be the library with extra steps.
  Plus "Party Games" (4+ players, 24)
- Snap-on-focus — **done.** The focused poster cross-fades to the in-game snap after 1.1s, gated on `ListItem.Property(marty_info)` so the Plex rows keep their box art
- RetroAchievements — **upstream shipped this.** No longer a wrapper hack: the
  Kodi we built has `xbmc/games/addons/cheevos/`, a `DialogGameAchievements`
  OSD, and real settings (`gamesachievements.username` / `.password` /
  `.token` / `.loggedin`). It landed after the box's build, so it is a
  post-flash login, not development. Needs Marty's RetroAchievements account

### Phase 8 — Ingest pipeline
Replace the current manual dance (copy ROMs → `fetch_artwork.py` →
`fetch_metadata.py` → tar across → remember to overwrite the stale
`metadata.json`, which has already caused one bug) with a single
`tools/ingest.py`:

```
ingest.py <path> [--system X] [--dry-run]
  detect system (extension, or --system)
  unpack archives           (bsdtar / unar / innoextract already installed)
  normalise the name        (No-Intro conventions — this is what makes
                             artwork match; see titles.normalise)
  DOS: resolve the executable through scanner._pick_dos_executable
  copy to the box
  fetch box art + snap + metadata for the new titles only
  merge caches in place
  report: matched / fuzzy-matched / needs a manual override
```

The design question worth getting right: **normalise names at import**, not at
match time. The artwork matcher keys off No-Intro naming, so a strict ingest is
what keeps the hit rate high instead of growing `art_overrides.json` forever.

Effort: a couple of days. Risk: low. Highest day-to-day value of anything here.

---

## 4. Tracking CoreELEC

The fork only survives if picking up upstream is cheap.

**Shape**
- Fork `CoreELEC/CoreELEC`, branch `marty-22` from `coreelec-22`
- Our Kodi changes are patch files `1016-*.patch` onward — the numbering slot
  already exists, and upstream owns `1001`–`1015`
- New core packages are *additions* under `packages/emulation/`, so they never
  conflict
- Rebase rather than merge, so the patch series stays reviewable and each patch
  stays independently upstreamable

**CI** — we have the runner fleet for this ([[ci-runner-fleet-access-and-flake-fix]],
[[runner-fleet-inventory]]): 4 Linux VMs plus COLOSSUS. A CoreELEC image build is
hours, which is exactly what self-hosted runners are for.

1. Watch `coreelec-22` for movement, especially `packages/mediacenter/kodi/package.mk`
   (the `PKG_VERSION` Kodi pin — currently `22.0b2-Piers`)
2. Rebase `marty-22`, fail loudly on patch conflict
3. Build the Amlogic-ng image
4. Smoke test — boot, load a game per system, exit cleanly (the exit path is our
   own regression test after Phase 3)
5. Publish a `.tar` to `/storage/.update/`, which is CoreELEC's supported update
   path

**Open question to resolve in Phase 1:** whether we can iterate faster than a
full image rebuild. The root filesystem is a read-only squashfs, so dropping a
patched `kodi.bin` onto a running box may not be possible. If it is not, every
Kodi patch costs a full image cycle, which materially changes Phase 4's pace.
Worth answering early.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Bricking the box | Phase 0 — tested recovery path before any flash |
| Phase 4 proves intractable | Phases 1–3 stand alone; nothing already delivered is lost |
| Build cycle too slow for iteration | Resolve the squashfs question in Phase 1 |
| Fork drifts from upstream | Patch series + CI rebase on every upstream move |
| Custom image breaks on a CoreELEC release | Pin to a known-good upstream commit; upgrade deliberately |
| Emulators too slow on this SoC | Measure with the core HUD before investing in integration |

## 6. Suggested order

**Do first, independent of everything:** Phase 8 (ingest) and Phase 7's Continue
row. Both are days of work, neither touches the OS, and both get used daily.

**Then the fork:** Phase 0 → 1 → 2 → 3. That sequence ends with a maintained
image, no hand-built wrapper, and no exit crash — a materially better box even
if we stop there.

**Then the ambitious part:** Phase 4 → 5, N64 then PSP and Dreamcast.

Phase 6 (Saturn) can slot in anywhere; it needs ROMs and a BIOS, not code.


---

## 7. Delivery status

Updated 2026-09-06.

| Phase | State |
|---|---|
| 8 — Ingest pipeline | **Done.** `tools/ingest.py`, verified end to end |
| 7 — Continue shelf | **Done.** Live on the box, showing real savestate captures |
| 7 — Metadata shelves | **Route done** (`?action=shelf`); rows not yet placed on Home |
| 0 — Backup | **Done.** Full mirror: `/flash` + `/storage` + ROMs, ~17 GB. SYSTEM md5 matches the box; file counts match. Re-runnable via `tools/backup-box.sh` |
| 0 — Restore procedure | **Documented.** `kodi-martygames-backups/RESTORE.md` |
| 0 — Recovery test | **Needs Marty.** Requires physically booting from SD |
| 1 — Fork skeleton | **Done.** `~/dev/CoreELEC` on branch `marty-22`, with `FORK.md` |
| 1 — Tracking CI | **Done.** `.github/workflows/track-upstream.yml` |
| 1 — Build environment | **Done.** Containerised (`scripts-marty/`); `checkdeps` passes clean |
| 1 — First image build | **DONE.** `[370/370]`, 0 failures. `CoreELEC-Amlogic-no.aarch64-22.0-Piers_devel_20260906014435.tar`, 439 MB, sha256 verified. Built Kodi is **Game ABI 8.0.0** (box runs 6.0.0) |
| 1 — Flash | **Needs Marty.** Bricking risk; do not flash unattended |
| 2 — Retire the wrapper | **Ready, needs the flash.** The new Kodi sets `ADDON_INSTANCE_VERSION_GAME_MIN=8.0.0`, so it will *refuse* the ABI-6 wrapper - installing stock `game.libretro` is required immediately after flashing, not optional tidy-up |
| 3 — Exit crash | **Blocked on a debug build**, and the original theory is disproven (§1) |
| 4 — FBO buffer, pool, renderer | **Ported and building.** Patches 1016-1019 in the fork; Kodi rebuilt clean and the new log strings are present in the stripped `kodi.bin`, so it is linked rather than dead-stripped. Deliberately inert - `EnableHardwareRendering()` still refuses and the pool answers `IsCompatible()` false |
| 4 — Hardware rendering wiring | Not started. `Create()`, `RenderFrame()`, `OpenStream()`, `CloseStream()`, `GetHwProcedureAddress()`. Cannot be validated until the box runs our image |
| 5 — PSP/Dreamcast packages | **Written, never built.** Both addon pins verified real and hash as pinned; the repo carries neither core, so the fork is the only route. Blocked on Phase 4 - flycast needs a GL context whatever its addon.xml claims |
| 6 — Saturn | **Needs ROMs and a BIOS.** No code required; `beetle-saturn` and `yabause` are both in the repo for this device and genuinely software-rendered |

The pattern in what is left: everything outstanding needs either physical access
to the box, or a working build pipeline to iterate against. Neither is something
to fake progress on.

**A build returning 0 is not evidence a patch was tested.** `packages/
mediacenter/kodi` is shadowed for this target by the override at
`projects/Amlogic-ce/packages/mediacenter/kodi`, so nothing in the former's
`patches/` is ever applied - not ours, and not upstream's own 1001-1015. The
first Kodi build of the FBO work succeeded having applied only the two project
patches, and produced an unmodified Kodi. Count `APPLY PATCH` lines in the build
log. `scripts/build` also short-circuits on `.stamps/<pkg>`, so a changed patch
needs `scripts/clean <pkg>` first - `scripts-marty/build-package.sh` does both.
The same wrong assumption had been baked into `track-upstream.yml`, which was
watching the shadowed package for Kodi pin changes.

Six environmental build failures were found and fixed, all committed to the
fork so neither a rebuild nor CI rediscovers them. The pattern worth carrying:
**this network cannot reach several GNU-adjacent hosts** (`ftpmirror.gnu.org`,
`savannah.nongnu.org`, `download.savannah.gnu.org`), and CoreELEC surfaces that
as a silent stall or a bare "Cannot get sources", never as anything resembling
DNS. Two of the six were traps that a plausible fix would have made worse: a
cgit endpoint serving an HTML error page under HTTP 200 with a *stable*
checksum, and a savannah directory listing returning 200 while every actual
file returned 502.

Two further corrections worth carrying forward, both found by checking rather
than assuming:

- The build target is `PROJECT=Amlogic-ce DEVICE=Amlogic-no`, which the box
  reports in `/etc/os-release`. An earlier draft of `FORK.md` said
  `Amlogic/AMLGX` — different hardware, and hours of wasted build.
- The host cannot build CoreELEC: `checkdeps` wants a dozen packages installed
  as root. The build is containerised instead, which also makes it what CI
  runs.
