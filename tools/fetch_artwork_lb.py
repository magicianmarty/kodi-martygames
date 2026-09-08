#!/usr/bin/env python3
"""Second-pass box art from the LaunchBox Games Database dump.

libretro-thumbnails is the first source and is excellent for console sets that
follow No-Intro or Redump naming. It is thin exactly where our library is
thickest: it holds 3,325 Amiga boxarts against LaunchBox's 9,187, and our Amiga
set is 2,891 games of cracked and TOSEC-named releases. Measured against the
gap libretro left, LaunchBox covers 855 more Amiga games, 373 DOS and 44 PSP.

Same dump fetch_metadata.py already uses - no account, no API key - and the
same titles.normalise, so all three tools agree on what counts as one game.

    fetch_artwork_lb.py --roms .cache/romtree-all --out .cache/artwork-lb \
                        --systems amiga,dos,psp --have box-art.txt

Images come from images.launchbox-app.com through curl: it sits behind
Cloudflare, which answers python-urllib with a 1010 fingerprint block.
"""

import argparse
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'plugin.program.martygames'))
sys.path.insert(0, os.path.dirname(__file__))
from resources.lib import scanner            # noqa: E402
from resources.lib.systems import BY_KEY     # noqa: E402
from titles import normalise                 # noqa: E402

CDN = 'https://images.launchbox-app.com/%s'

# our key -> the platform string LaunchBox uses
PLATFORMS = {
    'amiga': ('Commodore Amiga',), 'dos': ('MS-DOS',), 'psp': ('Sony PSP',),
    'psx': ('Sony Playstation',), 'n64': ('Nintendo 64',),
    'megadrive': ('Sega Genesis',), 'nes': ('Nintendo Entertainment System',),
    'c64': ('Commodore 64',), 'saturn': ('Sega Saturn',),
    'dreamcast': ('Sega Dreamcast',), 'tg16': ('NEC TurboGrafx-16',),
    'scummvm': ('MS-DOS',), 'doom': ('MS-DOS',), 'quake': ('MS-DOS',),
}

# Best first. A box shot beats a 3D render; a screenshot is the snap.
COVER_TYPES = ('Box - Front', 'Fanart - Box - Front', 'Box - 3D')
SNAP_TYPES = ('Screenshot - Gameplay', 'Screenshot - Game Title')
REGIONS = ('North America', 'United States', 'World', 'Europe', '')


def stream(zip_path, chunk=16 * 1024 * 1024):
    with zipfile.ZipFile(zip_path) as z, z.open('Metadata.xml') as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                return
            yield data


def index_games(zip_path, wanted):
    """(system, normalised name) -> DatabaseID, for the platforms we care about."""
    plat = {p: k for k, ps in PLATFORMS.items() if k in wanted for p in ps}
    out, buf = {}, b''
    for data in stream(zip_path):
        buf += data
        for m in re.finditer(rb'<Game>(.*?)</Game>', buf, re.S):
            g = m.group(1).decode('utf-8', 'replace')
            p = re.search(r'<Platform>([^<]*)</Platform>', g)
            n = re.search(r'<Name>([^<]*)</Name>', g)
            i = re.search(r'<DatabaseID>(\d+)</DatabaseID>', g)
            if p and n and i and p.group(1) in plat:
                out.setdefault((plat[p.group(1)], normalise(n.group(1))), i.group(1))
        buf = buf[-40000:]
        if b'<GameImage>' in data:
            break
    return out


def index_images(zip_path, ids):
    """DatabaseID -> {kind: filename}, keeping only the ids we asked for."""
    best, buf = {}, b''
    rec = re.compile(rb'<GameImage>\s*<DatabaseID>(\d+)</DatabaseID>\s*'
                     rb'<FileName>([^<]+)</FileName>\s*<Type>([^<]*)</Type>'
                     rb'(?:\s*<Region>([^<]*)</Region>)?')
    for data in stream(zip_path):
        buf += data
        for m in rec.finditer(buf):
            dbid = m.group(1).decode()
            if dbid not in ids:
                continue
            fn = m.group(2).decode('utf-8', 'replace')
            kind = m.group(3).decode('utf-8', 'replace')
            region = (m.group(4) or b'').decode('utf-8', 'replace')
            for group, types in (('cover', COVER_TYPES), ('snap', SNAP_TYPES)):
                if kind not in types:
                    continue
                rank = (types.index(kind),
                        REGIONS.index(region) if region in REGIONS else len(REGIONS))
                slot = best.setdefault(dbid, {})
                if group not in slot or rank < slot[group][0]:
                    slot[group] = (rank, fn)
        buf = buf[-4000:]
    return best


def download(filename, dest):
    """curl, not urllib: the CDN is behind Cloudflare."""
    tmp = dest + '.part'
    r = subprocess.run(['curl', '-sfL', '-m', '90', '-o', tmp, CDN % filename],
                       capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, dest)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roms', default='.cache/romtree-all')
    ap.add_argument('--out', required=True)
    ap.add_argument('--zip', default='.cache/Metadata.zip')
    ap.add_argument('--systems', required=True)
    ap.add_argument('--have', help='listing of artwork already on the box, so a '
                                   'second pass only fetches what is still missing')
    args = ap.parse_args()

    wanted = [s for s in args.systems.split(',') if s]
    have = set()
    if args.have and os.path.exists(args.have):
        have = set(open(args.have, encoding='utf-8', errors='replace').read().splitlines())

    print('indexing games...', flush=True)
    games_ix = index_games(args.zip, wanted)
    print('  %d LaunchBox titles across %s' % (len(games_ix), ','.join(wanted)))

    todo = []
    for key in wanted:
        for g in scanner.scan_system(args.roms, BY_KEY[key]):
            for group, sub in (('cover', key), ('snap', 'snaps/' + key)):
                rel = '%s/%s.png' % (sub, g['title'])
                if rel in have or os.path.exists(os.path.join(args.out, rel)):
                    continue
                dbid = games_ix.get((key, normalise(g['title'])))
                if dbid:
                    todo.append((dbid, group, os.path.join(args.out, rel)))
    print('  %d image(s) to look up' % len(todo))
    if not todo:
        return

    print('indexing images...', flush=True)
    images = index_images(args.zip, {d for d, _, _ in todo})
    print('  %d titles have artwork' % len(images))

    got = missed = 0
    for dbid, group, dest in todo:
        slot = images.get(dbid, {}).get(group)
        if not slot:
            missed += 1
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if download(slot[1], dest):
            got += 1
            if got % 100 == 0:
                print('  %d downloaded' % got, flush=True)
        else:
            missed += 1
    print('\nfetched %d, missed %d' % (got, missed))


if __name__ == '__main__':
    main()
