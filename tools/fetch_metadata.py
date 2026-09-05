#!/usr/bin/env python3
"""Build the metadata index the plugin reads for the hero area.

Source is the LaunchBox Games Database dump - one 107 MB zip, no account and no
API key, and it carries the one field libretro-database does not have: an
Overview. libretro-database splits metadata across per-field .dat files
(developer/, publisher/, genre/, releaseyear/...) and has no synopsis at all,
which is exactly what the hero area is mostly made of.

Matching reuses titles.normalise, so this and the artwork fetcher agree on what
counts as the same game.
"""

import argparse
import difflib
import json
import os
import sys
import zipfile
from xml.etree import ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'plugin.program.martygames'))
sys.path.insert(0, os.path.dirname(__file__))
from resources.lib import scanner            # noqa: E402
from resources.lib.systems import BY_KEY     # noqa: E402
from titles import normalise                 # noqa: E402

# Our system key -> the platform name LaunchBox uses.
PLATFORMS = {
    'amiga': ('Commodore Amiga', 'Commodore Amiga CD32'),
    'megadrive': ('Sega Genesis',),
    'psx': ('Sony Playstation',),
    'nes': ('Nintendo Entertainment System',),
    'snes': ('Super Nintendo Entertainment System',),
    'c64': ('Commodore 64',),
    'dos': ('MS-DOS',),
    'doom': ('MS-DOS',),
    'quake': ('MS-DOS',),
    'scummvm': ('MS-DOS',),
    'arcade': ('Arcade',),
}

FIELDS = ('Name', 'Platform', 'Overview', 'Developer', 'Publisher', 'Genres',
          'ReleaseYear', 'ReleaseDate', 'MaxPlayers', 'ReleaseType',
          'CommunityRatingCount')


def read_games(zip_path, wanted_platforms):
    """Stream the 509 MB Metadata.xml out of the zip, one <Game> at a time."""
    with zipfile.ZipFile(zip_path) as z, z.open('Metadata.xml') as handle:
        for _event, elem in ElementTree.iterparse(handle, events=('end',)):
            if elem.tag != 'Game':
                continue
            platform = elem.findtext('Platform')
            if platform in wanted_platforms:
                yield {f: (elem.findtext(f) or '').strip() for f in FIELDS}
            elem.clear()


def score(entry):
    """Prefer the real release, then the entry the most people have rated."""
    released = 1 if entry['ReleaseType'] in ('', 'Released') else 0
    try:
        votes = int(entry['CommunityRatingCount'] or 0)
    except ValueError:
        votes = 0
    return (released, votes)


def condense(entry):
    year = entry['ReleaseYear'] or entry['ReleaseDate'][:4]
    genres = '; '.join(g.strip() for g in entry['Genres'].split(';') if g.strip())
    record = {
        'year': year if year.isdigit() else '',
        'developer': entry['Developer'],
        'publisher': entry['Publisher'],
        'genres': genres,
        'players': entry['MaxPlayers'] if entry['MaxPlayers'].isdigit() else '',
        'overview': ' '.join(entry['Overview'].split()),
    }
    return {k: v for k, v in record.items() if v}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roms', default='.cache/romtree')
    ap.add_argument('--zip', default='.cache/Metadata.zip')
    ap.add_argument('--out', default=os.path.join(
        os.path.dirname(__file__), '..', 'data', 'metadata.json'))
    ap.add_argument('--cutoff', type=float, default=0.86)
    args = ap.parse_args()

    games = scanner.scan_all(args.roms)
    systems = sorted({g['system'] for g in games} & set(PLATFORMS))
    wanted = {p for key in systems for p in PLATFORMS[key]}
    print('  scanning %d games across %s' % (len(games), ', '.join(systems)))

    overrides_path = os.path.join(os.path.dirname(__file__), 'meta_overrides.json')
    overrides = json.load(open(overrides_path)) if os.path.exists(overrides_path) else {}

    # platform -> normalised name -> best entry
    index = {}
    for entry in read_games(args.zip, wanted):
        by_name = index.setdefault(entry['Platform'], {})
        key = normalise(entry['Name'])
        if key and (key not in by_name or score(entry) > score(by_name[key])):
            by_name[key] = entry
    print('  indexed %d platforms: %s' % (
        len(index), ', '.join('%s=%d' % (p, len(v)) for p, v in sorted(index.items()))))

    out = {}
    matched = missed = 0
    for game in sorted(games, key=lambda g: (g['system'], g['title'].lower())):
        key = game['system']
        if key not in PLATFORMS:
            continue
        pool = {}
        for platform in PLATFORMS[key]:
            pool.update(index.get(platform, {}))
        if not pool:
            continue
        manual = overrides.get(key, {}).get(game['title'])
        entry = pool.get(normalise(manual)) if manual else None
        if entry is None:
            norm = normalise(game['title'])
            entry = pool.get(norm)
            if entry is None:
                close = difflib.get_close_matches(norm, list(pool), n=1,
                                                  cutoff=args.cutoff)
                entry = pool[close[0]] if close else None
        if entry is None:
            print('      no match: %-10s %s' % (key, game['title']))
            missed += 1
            continue
        out.setdefault(key, {})[game['title']] = condense(entry)
        matched += 1

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, sort_keys=True, ensure_ascii=False)
    print('\n  matched %d, missed %d -> %s' % (matched, missed, args.out))


if __name__ == '__main__':
    main()
