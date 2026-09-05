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
    'c64': 'Commodore_-_64',
    'dos': 'DOS',
    'arcade': 'MAME',
}
RAW = 'https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/{path}'
TREE = 'https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/master?recursive=1'

def fetch_index(repo, attempts=3):
    # The DOS repo is large enough that the tree API intermittently 500s.
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(TREE.format(repo=repo),
                                         headers={'User-Agent': 'martygames'})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            if 'tree' not in data:
                raise RuntimeError(data.get('message', 'no tree'))
            return [e['path'] for e in data['tree']
                    if e['path'].startswith(('Named_Boxarts/', 'Named_Snaps/'))
                    and e['path'].endswith('.png')]
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(3 * (n + 1))
    raise last


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
                    hit = by_name.get(norm)
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
                url = RAW.format(repo=REPOS[key],
                                 path=urllib.parse.quote(path))
                try:
                    req = urllib.request.Request(
                        url, headers={'User-Agent': 'martygames'})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        blob = r.read()
                    with open(dest, 'wb') as fh:
                        fh.write(blob)
                    matched += 1
                except Exception as exc:               # noqa: BLE001
                    print("      download failed %s: %s" % (game['title'], exc))
                    missed += 1

    print("\n  matched %d, missed %d" % (matched, missed))


if __name__ == '__main__':
    main()
