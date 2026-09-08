"""Walk the ROM tree and produce one entry per game."""

import json
import os
import re

from .systems import BY_KEY, EXCLUDE_NAMES, DOS_EXE_BLOCKLIST

# DOS layouts defeat any pure heuristic, so allow per-game corrections.
# Paths are relative to the game's own folder.
_OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), 'overrides.json')
try:
    with open(_OVERRIDES_PATH, encoding='utf-8') as fh:
        OVERRIDES = json.load(fh)
except (OSError, ValueError):
    OVERRIDES = {}

# Tags carried by GoodTools / TOSEC / No-Intro names that aren't part of the title.
_TAG = re.compile(r'\s*[\(\[][^\)\]]*[\)\]]')
_DISK = re.compile(r'\s*\(?disk\s*\d+\s*(of\s*\d+)?\)?', re.I)


def clean_title(name):
    """Turn a ROM filename into something presentable.

    'Sonic The Hedgehog 2 (W) (REV01) [!]' -> 'Sonic The Hedgehog 2'
    'Parasol Stars (1992)(Ocean)[cr]'      -> 'Parasol Stars'
    """
    title = os.path.splitext(name)[0]
    title = _DISK.sub('', title)
    title = _TAG.sub('', title)
    title = title.replace('_', ' ').strip(' -.')
    return re.sub(r'\s{2,}', ' ', title) or name


def _pick_dos_executable(folder, max_depth=2):
    """Choose the executable most likely to be the game itself.

    Real libraries nest: Theme Hospital hides HOSPITAL.EXE one folder down next
    to DOS4GW.EXE (a DOS extender), and One Must Fall keeps omf21.exe in omf/
    alongside a tourncmp/ folder full of decoy tools. So search a couple of
    levels deep and score candidates rather than taking the first or largest.
    """
    words = [t for t in re.split(r'\W+', clean_title(os.path.basename(folder)).lower()) if t]
    title_tokens = {t for t in words if len(t) >= 4}
    # DOS names launchers by initials as often as by title: OMF.EXE for One
    # Must Fall, UW.EXE for Ultima Underworld. Without this the pick is decided
    # on size, and One Must Fall ships NETTERM.EXE at twenty times OMF.EXE.
    initials = ''.join(w[0] for w in words if w[0].isalpha())
    best = None

    for root, dirs, files in os.walk(folder):
        depth = root[len(folder):].count(os.sep)
        if depth >= max_depth:
            dirs[:] = []
        parent = os.path.basename(root).lower()
        # Trainers, cheats and manuals ship in their own subfolder, and the
        # executable inside is named nothing like them. Only below the top
        # level: the game's own folder is the parent there, and its name is
        # not ours to veto.
        if depth > 0 and any(b in parent for b in DOS_EXE_BLOCKLIST):
            continue
        for entry in sorted(files):
            low = entry.lower()
            if not low.endswith(('.exe', '.com', '.bat')):
                continue
            if low in EXCLUDE_NAMES or any(b in low for b in DOS_EXE_BLOCKLIST):
                continue
            path = os.path.join(root, entry)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            stem = os.path.splitext(low)[0]
            score = 0
            for tok in title_tokens:
                # match both ways: HOSPITAL.EXE for "Theme Hospital", and
                # civ.exe for "Civilization" (abbreviations are the norm in DOS)
                if tok in stem or (len(stem) >= 3 and tok.startswith(stem)):
                    score += 3
                    break
            if len(initials) >= 2 and stem == initials:
                score += 4
            if len(parent) >= 3 and stem.startswith(parent):
                score += 2          # omf/omf21.exe
            # A subfolder named after the game holds the installed copy; the
            # original disk directories sitting beside it (START0, START1)
            # carry the same executables and must not outrank it. Only below
            # the top level: there the parent is the game's own folder, so
            # every loose executable would score the bonus.
            if depth > 0 and any(tok in parent for tok in title_tokens):
                score += 2
            score -= depth          # prefer shallower
            key = (score, size)
            if best is None or key > best[0]:
                best = (key, path)

    # No score gate: abbreviations are normal in DOS (war2.exe for Warcraft 2,
    # WOLF3D.EXE, C&C.BAT) and would score zero. The blocklist does the real
    # filtering - when everything in a folder is blocked we return None, which
    # correctly identifies un-run installers like SimCity 2000 and Syndicate.
    return best[1] if best else None


def scan_system(root, system):
    """Yield {'title','path','system','core'} for one system directory."""
    base = os.path.join(root, system.key)
    if not os.path.isdir(base):
        return

    if system.folder_games:
        overrides = OVERRIDES.get(system.key, {})
        for entry in sorted(os.listdir(base)):
            folder = os.path.join(base, entry)
            if not os.path.isdir(folder):
                continue
            title = clean_title(entry)
            manual = overrides.get(title)
            if manual:
                candidate = os.path.join(folder, manual)
                exe = candidate if os.path.exists(candidate) else None
            else:
                exe = _pick_dos_executable(folder)
            if exe:
                yield {'title': clean_title(entry), 'path': exe,
                       'system': system.key, 'core': system.core}
        return

    # Group by cleaned title so multi-disk sets collapse to one entry, then
    # pick the best file for each (an .m3u playlist beats a bare disk image).
    groups = {}
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if entry.lower() in EXCLUDE_NAMES or ext in system.skip_exts:
            continue
        if ext not in system.exts:
            continue
        groups.setdefault(clean_title(entry), []).append((ext, path))

    # Multi-disk sets live in a subfolder of their own (Amiga). Treat each
    # folder as one game and start it on disk 1 - RetroPlayer's disc control
    # handles swapping from there.
    for entry in sorted(os.listdir(base)):
        folder = os.path.join(base, entry)
        if not os.path.isdir(folder):
            continue
        disks = sorted(f for f in os.listdir(folder)
                       if os.path.splitext(f)[1].lower() in system.exts)
        if not disks:
            continue
        first = next((d for d in disks if re.search(r'disk\s*0*1\b', d, re.I)), disks[0])
        groups.setdefault(clean_title(entry), []).append(
            (os.path.splitext(first)[1].lower(), os.path.join(folder, first)))

    for title, files in sorted(groups.items()):
        files = sorted(files, key=lambda ep: (_region_rank(ep[1]), ep[1]))
        for wanted in system.prefer:
            chosen = next((p for e, p in files if e == wanted), None)
            if chosen:
                break
        else:
            chosen = files[0][1]
        yield {'title': title, 'path': chosen,
               'system': system.key, 'core': system.core}


# Regions we can actually read, best first. Anything unlisted sorts last.
_REGIONS = ('usa', 'world', 'europe', 'australia', 'uk', 'canada')
_REGION_RE = re.compile(r'[(\[]([^)\]]*)[)\]]')


def _region_rank(path):
    """Rank a file by how readable its release is.

    Titles collapse by name, so "Fighting Vipers (Korea)" and
    "Fighting Vipers (USA)" are one game and something has to choose. That was
    a plain alphabetical sort, which put Korea first and quietly handed over
    the Korean build of eight games we hold in English.
    """
    tags = ' '.join(_REGION_RE.findall(os.path.basename(path))).lower()
    for i, region in enumerate(_REGIONS):
        if region in tags:
            return i
    return len(_REGIONS)


def _cache_path():
    try:
        import xbmcaddon
        import xbmcvfs
        profile = xbmcvfs.translatePath(
            xbmcaddon.Addon().getAddonInfo('profile'))
        return os.path.join(profile, 'library.json')
    except Exception:                                  # noqa: BLE001
        return None


def _stamp(root):
    """A cheap fingerprint of the ROM tree: each system directory's mtime.

    Adding, removing or renaming a ROM changes the mtime of the directory it
    is in, which is all this needs to notice. Editing a file in place does not,
    but nothing here cares about a ROM's contents.
    """
    out = {}
    for key in sorted(BY_KEY):
        base = os.path.join(root, key)
        try:
            out[key] = os.path.getmtime(base)
        except OSError:
            pass
    return out


def scan_all(root, use_cache=True):
    """Scan every known system present under root.

    Cached to disk because the home screen is built from about a dozen
    separate add-on invocations - each shelf, plus Recently Played and
    Continue - and every one of them was walking the whole tree. At 242 games
    that was free; at 8,000 it is nearly three seconds each, the screen takes
    a minute to fill, and the box never drops below 75% CPU. It was enough
    contention to stop an N64 game reaching its first frame of audio.

    Each invocation is a fresh interpreter, so the cache has to be on disk.
    """
    path = _cache_path() if use_cache else None
    stamp = _stamp(root)

    if path:
        try:
            with open(path, encoding='utf-8') as fh:
                cached = json.load(fh)
            if cached.get('stamp') == stamp and cached.get('root') == root:
                return cached['games']
        except (OSError, ValueError, KeyError):
            pass

    out = []
    for key in sorted(BY_KEY):
        out.extend(scan_system(root, BY_KEY[key]))

    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'root': root, 'stamp': stamp, 'games': out}, fh)
            os.replace(tmp, path)
        except OSError:
            pass                                       # a slow library beats none

    return out
