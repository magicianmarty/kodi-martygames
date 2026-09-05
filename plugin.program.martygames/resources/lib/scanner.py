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
    title_tokens = {t for t in re.split(r'\W+', clean_title(os.path.basename(folder)).lower())
                    if len(t) >= 4}
    best = None

    for root, dirs, files in os.walk(folder):
        depth = root[len(folder):].count(os.sep)
        if depth >= max_depth:
            dirs[:] = []
        parent = os.path.basename(root).lower()
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
            if len(parent) >= 3 and stem.startswith(parent):
                score += 2          # omf/omf21.exe
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
        for wanted in system.prefer:
            chosen = next((p for e, p in files if e == wanted), None)
            if chosen:
                break
        else:
            chosen = sorted(files)[0][1]
        yield {'title': title, 'path': chosen,
               'system': system.key, 'core': system.core}


def scan_all(root):
    """Scan every known system present under root."""
    out = []
    for key in sorted(BY_KEY):
        out.extend(scan_system(root, BY_KEY[key]))
    return out
