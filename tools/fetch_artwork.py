#!/usr/bin/env python3
"""Fetch box art from libretro-thumbnails and match it to the local library.

Runs on the dev machine, writes into a staging directory, which is then copied
to the box. libretro-thumbnails is free and needs no API key, but its names
follow No-Intro conventions while our filenames span GoodTools, TOSEC, bare
names and DOS folder names - so matching is normalise-then-fuzzy, with a
manual overrides file for the tail.
"""

import argparse
import difflib
import json
import os
import posixpath
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'plugin.program.martygames'))
from resources.lib import scanner            # noqa: E402
from resources.lib.systems import BY_KEY     # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from titles import normalise                # noqa: E402

REPOS = {
    'megadrive': 'Sega_-_Mega_Drive_-_Genesis',
    'nes': 'Nintendo_-_Nintendo_Entertainment_System',
    'snes': 'Nintendo_-_Super_Nintendo_Entertainment_System',
    'amiga': 'Commodore_-_Amiga',
    'psx': 'Sony_-_PlayStation',
    'psp': 'Sony_-_PlayStation_Portable',
    'dreamcast': 'Sega_-_Dreamcast',
    'saturn': 'Sega_-_Saturn',
    'n64': 'Nintendo_-_Nintendo_64',
    'c64': 'Commodore_-_64',
    'dos': 'DOS',
    'scummvm': 'ScummVM',
    'arcade': 'MAME',
    'tg16': 'NEC_-_PC_Engine_-_TurboGrafx_16',
}
RAW = 'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/{path}'
TREE = 'https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/master?recursive=1'

SUBDIR_TREE = 'https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/master:{sub}'


def _tree(url, attempts=3):
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'martygames'})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            if 'tree' not in data:
                raise RuntimeError(data.get('message', 'no tree'))
            return data
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(3 * (n + 1))
    raise last


def fetch_index(repo):
    """List the boxart and snap filenames in a thumbnails repo.

    The recursive tree endpoint is the cheap way to do this, and for the DOS
    repo GitHub answers it with a flat 500 - it is simply too big. Asking for
    each subdirectory by path costs one extra request and works: 4,481 boxarts
    and 7,731 snaps come back untruncated where the recursive form returns
    nothing at all. That silently cost every DOS import its artwork.
    """
    try:
        data = _tree(TREE.format(repo=repo), attempts=2)
        if not data.get('truncated'):
            return [e['path'] for e in data['tree']
                    if e['path'].startswith(('Named_Boxarts/', 'Named_Snaps/'))
                    and e['path'].endswith('.png')]
    except Exception:                                  # noqa: BLE001
        pass

    paths = []
    for sub in ('Named_Boxarts', 'Named_Snaps'):
        data = _tree(SUBDIR_TREE.format(repo=repo, sub=sub))
        paths += ['%s/%s' % (sub, e['path']) for e in data['tree']
                  if e['path'].endswith('.png')]
    return paths


PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _download(repo, path, hops=3):
    """Fetch one thumbnail, following the repo's symlinks.

    libretro-thumbnails stores regional duplicates as git symlinks, and the raw
    endpoint serves a symlink as its target filename in plain text. Written
    straight to disk that produces a 26-byte "PNG" - which Kodi cannot draw, so
    the game shows a placeholder and nothing anywhere reports an error. 78 of
    2,831 covers were this.
    """
    for _ in range(hops):
        url = RAW.format(repo=repo, path=urllib.parse.quote(path))
        req = urllib.request.Request(url, headers={'User-Agent': 'martygames'})
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read()
        if blob.startswith(PNG_MAGIC):
            return blob
        target = blob.decode('utf-8', 'replace').strip()
        if not target.lower().endswith('.png') or '\n' in target:
            raise RuntimeError('not a PNG and not a symlink (%d bytes)' % len(blob))
        path = posixpath.join(posixpath.dirname(path), target)
    raise RuntimeError('symlink chain too deep')


def _subtitle_match(norm, keys, by_name):
    """Our name against a repo name that carries a subtitle we do not have.

    "Tomb Raider Anniversary" is the whole title on the card and
    "Tomb Raider - Anniversary" in the repo; "X Men Legends 2" is
    "X-Men Legends II - Rise of Apocalypse". Fuzzy matching cannot bridge the
    second, because the extra words dominate the ratio.

    Only accepted when exactly one repo title extends ours, and only for names
    long enough to be specific - otherwise "Warhammer" would claim whichever of
    its half-dozen sequels happened to sort first.
    """
    if len(norm) < 12 or len(norm.split()) < 2:
        return None
    prefix = norm + ' '
    hits = [k for k in keys if k.startswith(prefix)]
    return by_name[hits[0]] if len(hits) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roms', default='/tmp/romtree')
    ap.add_argument('--out', required=True)
    ap.add_argument('--cutoff', type=float, default=0.86)
    ap.add_argument('--systems', default='')
    args = ap.parse_args()

    wanted = set(args.systems.split(',')) if args.systems else set(REPOS)
    overrides_path = os.path.join(os.path.dirname(__file__), 'art_overrides.json')
    overrides = json.load(open(overrides_path)) if os.path.exists(overrides_path) else {}

    matched = missed = 0
    for key in sorted(wanted):
        system = BY_KEY.get(key)
        if not system or key not in REPOS:
            continue
        games = list(scanner.scan_system(args.roms, system))
        if not games:
            continue
        try:
            index = fetch_index(REPOS[key])
        except Exception as exc:                       # noqa: BLE001
            print("  %-10s index failed: %s" % (key, exc))
            continue

        lookup = {}
        for path in index:
            folder = path.split('/', 1)[0]
            lookup.setdefault(folder, {}).setdefault(
                normalise(os.path.basename(path)), path)
        print("  %s: %d games vs %d boxarts, %d snaps" % (
            key, len(games), len(lookup.get('Named_Boxarts', {})),
            len(lookup.get('Named_Snaps', {}))))

        for folder, subdir in (('Named_Boxarts', key),
                               ('Named_Snaps', os.path.join('snaps', key))):
            by_name = lookup.get(folder, {})
            keys = list(by_name)
            outdir = os.path.join(args.out, subdir)
            os.makedirs(outdir, exist_ok=True)
            for game in games:
                dest = os.path.join(outdir, game['title'] + '.png')
                if os.path.exists(dest):
                    matched += 1
                    continue
                manual = overrides.get(key, {}).get(game['title'])
                if manual:
                    path = '%s/%s.png' % (folder, manual)
                else:
                    norm = normalise(game['title'])
                    hit = by_name.get(norm) or _subtitle_match(norm, keys, by_name)
                    if not hit:
                        close = difflib.get_close_matches(norm, keys, n=1,
                                                          cutoff=args.cutoff)
                        hit = by_name[close[0]] if close else None
                    path = hit
                if not path:
                    if folder == 'Named_Boxarts':
                        print("      no match: %s" % game['title'])
                    missed += 1
                    continue
                try:
                    blob = _download(REPOS[key], path)
                    with open(dest, 'wb') as fh:
                        fh.write(blob)
                    matched += 1
                except Exception as exc:               # noqa: BLE001
                    print("      download failed %s: %s" % (game['title'], exc))
                    missed += 1

    print("\n  matched %d, missed %d" % (matched, missed))


if __name__ == '__main__':
    main()
