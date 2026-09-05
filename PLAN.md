# Games experience for skin.martyedition

A cohesive games section for the Ugoos AM6B+ / CoreELEC box, matching how Movies and
TV Shows already look and behave in the skin.

**This project is unrelated to fyai work.** It lives at `~/dev/kodi-martygames`.

---

## 1. The constraint that shapes everything

**Kodi 22 has no games library.** Verified directly against the running binary:

| Symbol | Present in `kodi.bin` |
|---|---|
| `MyGamesNav` | ✗ |
| `games://` | ✗ |
| `CGameDatabase` | ✗ |
| `gameinfo` | ✗ |
| `MyGames.xml` (the window itself) | ✓ |

The Games window is a **plain file browser** — the log shows
`CGUIMediaWindow::GetDirectory(/storage/roms/c64/)`. There is no scanning, no metadata,
no artwork association, and no play-count/last-played tracking.

There is also **no general games scraper** in the configured repos. The only game-adjacent
program addon is `plugin.program.AML` (Advanced MAME Launcher), which is MAME-only.

**Conclusion:** cover art and a movies-like browse experience must be *built*, not configured.

## 2. Prior art — evaluated, not adopted wholesale

| | Advanced Kodi Launcher (AKL) | Rom Collection Browser (RCB) |
|---|---|---|
| Repo | `chrisism/plugin.program.akl` | `maloep/romcollectionbrowser` |
| Licence | GPL-2.0 | GPL-2.0 |
| Last push | 2026-01-19 (active) | 2021-07-15 (5 years stale) |
| Scrapers | ScreenScraper, TheGamesDB, MobyGames, ArcadeDB, GameFAQs, SteamGridDB | built-in |
| Launcher | `AppLauncher` — external executables / RetroArch | external emulator |
| Python 3.14 risk | low | **high** (targets the Kodi 17 era) |

**Neither works off the shelf**, for one decisive reason: both launch *external* emulators.
On CoreELEC there is no RetroArch — our emulators **are** Kodi game clients
(`game.libretro.*`) driven by RetroPlayer. AKL's default launcher is a 140-line
`AppLauncher` that shells out to a binary.

**Decision:** build a focused plugin (below), and treat AKL as a reference implementation for
scraper interfaces rather than a base to fork. Revisit forking only if metadata scraping
becomes the dominant cost — AKL's scrapers are its genuinely valuable part, and its component
plugins (`script.akl.screenscraper`, `script.akl.tgdbscraper`) have a documented interface we
could implement against later.

## 3. What is already in our favour

The skin is **already plugin-driven**, which makes native-looking integration cheap:

- Home rows consume plugin directories directly:
  `<content>plugin://script.plexmod/hubs?hub=…</content>`
- `Variables.xml` → `MartyTilePoster` resolves art in this order:
  `ListItem.Art(poster)` → `ListItem.Art(thumb)` → `ListItem.Art(landscape)`

So **any plugin that sets `poster` art inherits `MartyPosterTile` verbatim** — the same
rounded-corner mask, drop shadow, focus glow and flag strip as Movies. No new tile design.

## 4. Architecture

A single Kodi plugin, `plugin.program.martygames`:

```
ROM tree (SD card)  ──scan──>  SQLite index  ──serve──>  plugin:// directories
                                    ^                          |
                              artwork cache                    v
                          (libretro-thumbnails /        skin widgets + Games window
                           ScreenScraper)                (MartyPosterTile, unchanged)
```

Virtual directories served: `All Games`, `By System`, `Recently Played`, `Random`,
`Favourites`.

## 5. Phases

### Phase 1 — Index and launch (no artwork)
- Walk `/storage/sdcard/roms`, one row per game in SQLite.
- Collapse multi-disk sets (Amiga `.m3u` files already exist); skip BIOS and side files.
- **Launch with the core pinned per system**, e.g.
  `PlayMedia(<path>, gameclient=game.libretro.genplus)`.
  This deliberately fixes two problems already hit in practice:
  - the emulator **select dialog** appearing on every launch;
  - Kodi's **savestate pinning a game to the wrong core** (a `.cue` opened once with PUAE
    kept resuming under PUAE even after that core was disabled).
- *Deliverable:* a Games row that launches reliably, every time, with no dialogs.

### Phase 2 — Artwork
- Primary: **libretro-thumbnails** — free, no API key, per-system repos with
  `Named_Boxarts` / `Named_Snaps` / `Named_Titles`.
- Fallback: **ScreenScraper** — needs a free account, but far better Amiga / C64 / DOS coverage.
- Cache to `/storage/sdcard/artwork/<system>/<id>.png`.

⚠️ **The name-matching problem is the main cost of this project.** Filenames span three
conventions plus bare names:

```
GoodTools    Sonic The Hedgehog 2 (W) (REV01) [!].zip
TOSEC        Parasol Stars (1992)(Ocean)[cr].adf
bare         Bubble Bobble.adf
DOS folder   Sid Meiers Civilization (1991)
```

Approach: normalise (strip region/dump/revision/cracker tags, punctuation, leading articles)
→ fuzzy match → hand-maintained `overrides.json` for the tail. Budget for ~80% automatic.

### Phase 3 — Metadata
Year, publisher, genre, player count, description — enabling sort, filter and an info pane.

### Phase 4 — Skin integration
- Home: one to three rows (Recently Played / By System / Random), created by copying an
  existing row block and swapping `<content>`.
- A dedicated Games category page — the skin ships an as-yet-unused `Includes_Games.xml`
  to build on, reachable from the Games menu button already added to `Home.xml`.

### Phase 5 — Polish
Fanart behind the carousel, system logos, play counts, and a "Continue" row driven by the
savestates Kodi writes to `special://home/saves/<rom>/`.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Artwork matching is the dominant time cost | Ship Phase 1 first; hand-place ~6 posters to prove the look before building the matcher |
| DOS games are *folders*, not files | Per-folder executable selection (already a known wrinkle — several titles ship multiple `.exe`) |
| Skin edits are overwritten by a skin update | Fold `Home.xml` changes into the skin source repo |
| Plugin must be maintained alongside the skin | Keep it standalone; depend only on documented Kodi APIs |
| CoreELEC beta1 missing modules (xpadneo, joydev) | Already worked around; unrelated to this plugin |

## 7. Environment facts (verified)

- Box: Ugoos AM6B+, CoreELEC 22.0-Piers_beta1, Kodi 22, aarch64, `xbmc.python` 3.0.2
- Games source: single entry `Games` → `/storage/sdcard/roms/`
  (`/storage/roms` is a symlink to it, so legacy paths still resolve)
- Library: amiga 32 · dos 29 · megadrive 17 · doom 2 · psx 2 · c64 2 · nes 1
- 11 game clients installed; `game.libretro` 22.5.0 is a **hand-built ABI-6 wrapper**
  (the repo ships ABI-8, which this Kodi cannot load)
- Input: Xbox Wireless Controller (BLE), MX Master 3S, MX KEYS S — all paired and trusted
