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

Needs a debug build and a reliable repro (we have one: exit any game).

Effort: a few days including build cycles. Risk: medium — it is a threading fix.
Value: very high; it is the single most annoying defect on the box, and it also
trips CoreELEC safe mode after roughly three crashes.

**Strong upstream candidate.** Worth a Kodi PR regardless of whether we ship it
ourselves first.

### Phase 4 — Hardware rendering → N64
The hard one, and the reason this roadmap exists.

Implement, on top of the existing scaffolding:
1. `CGameClientStreams::EnableHardwareRendering()` — stop returning false
2. `CRetroPlayerRendering::OpenStream()` — take real dimensions from
   `HwFramebufferProperties` instead of the hardcoded 640×480
3. An FBO + backing texture the core renders into, its GL name returned through
   `GetCurrentFramebuffer`
4. `GetHwProcedureAddress` — resolve GLES symbols for the core
5. Context reset/destroy lifecycle **on the rendering thread** — the existing
   `@todo` explicitly flags this as the constraint
6. `CRetroPlayerRendering::CloseStream()`, currently empty

Then flip `libretro-mupen64plus-nx` on and test with real N64 content.

Effort: **weeks, not days.** This is the phase that can fail. The thread
affinity requirement is the part most likely to bite — Kodi's render thread
owns the GL context, and the game loop runs elsewhere.

Mitigation: Phases 1–3 are independently valuable, so an unsuccessful Phase 4
costs time but loses nothing already delivered.

**Also a strong upstream candidate** — this is a `@todo` the Kodi team have
carried for years.

### Phase 5 — Package the missing cores → PSP, Dreamcast
Add `packages/emulation/libretro-ppsspp` and `libretro-flycast` following the
existing 80-package pattern, plus the matching `game.libretro.*` addon
definitions so they appear as game clients.

Depends on Phase 4. Effort: days per core, mostly build plumbing and per-core
option wiring. Risk: low-ish once Phase 4 works — but PPSSPP in particular has a
large surface of renderer options to get right.

### Phase 6 — Saturn reality check
Independent of everything above; can be done today. Install `beetle-saturn`,
supply the BIOS (`sega_101.bin` / `mpr-17933.bin`), measure with the core's own
HUD (`FPS: flip_cnt/vsync_count` — see `box-config/README.md`). If it is too
slow, try `yabause` and accept the compatibility hit.

Effort: an evening, once ROMs and BIOS exist. Needs no fork.

### Phase 7 — Shelves
Independent of the fork; can proceed in parallel.

**The Continue row** is the standout. Kodi already writes a real screenshot
beside every savestate (`/storage/.kodi/saves/<rom>/<timestamp>.jpg`, ~27 KB of
actual gameplay). Nothing uses them. A Continue shelf showing where you left off
rather than box art is mostly plumbing we have already built — the plugin
already reads that directory for last-played ordering.

Then, all driven by metadata we already hold for 203 games (year, genre,
players, developer, publisher, overview) and currently show only in the hero:

- Genre shelves — "Racing", "Platformers", "Puzzle"
- **"2 players"** — the couch co-op shelf, one property away
- "Never played" — inverse of Recently Played, same savestate trick
- Decade shelves — "1990s"
- Snap-on-focus — swap box art for the in-game snap after a focus delay
- RetroAchievements — the wrapper has cheevos compiled in and unconfigured

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
| 1 — First image build | **Running.** 370 packages; hours |
| 1 — Flash | **Needs Marty.** Bricking risk; do not flash unattended |
| 2 — Retire the wrapper | Blocked on Phase 1 |
| 3 — Exit crash | **Blocked on a debug build**, and the original theory is disproven (§1) |
| 4 — Hardware rendering | Not started. Weeks; the honest gate is Phase 1 |
| 5 — PSP/Dreamcast packages | **Written, never built.** Metadata verified, make flags unproven |
| 6 — Saturn | **Needs ROMs and a BIOS.** No code required |

The pattern in what is left: everything outstanding needs either physical access
to the box, or a working build pipeline to iterate against. Neither is something
to fake progress on.

Two corrections worth carrying forward, both found by checking rather than
assuming:

- The build target is `PROJECT=Amlogic-ce DEVICE=Amlogic-no`, which the box
  reports in `/etc/os-release`. An earlier draft of `FORK.md` said
  `Amlogic/AMLGX` — different hardware, and hours of wasted build.
- The host cannot build CoreELEC: `checkdeps` wants a dozen packages installed
  as root. The build is containerised instead, which also makes it what CI
  runs.
