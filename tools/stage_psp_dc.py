#!/usr/bin/env python3
"""Stage PSP and Dreamcast titles for the box.

Symlinks rather than copies: the PSP set alone is 99 GB, and rsync -L follows
links, so the rename costs nothing on disk.

Both sources need filtering as well as renaming, but only the PSP set can be
done by rule: its filenames are uniform, so stripping the _PSP suffix and the
underscores is enough.

The Dreamcast pack is picked by hand, because nothing about it is regular. It
is half video (Spider-Man films burned to CDI), it ships games two and three
times over as widescreen, no-music and unpatched variants, its folder names
carry typos ("Quake 3 Area"), and two different Sonic games sit loose in one
folder under names like SA1-FZT-WIDE.cdi. A heuristic over that produces
plausible, wrong titles - "Quake 3 Area (Disc 2)" for a second variant of the
same game. Nine entries are quicker to read than to infer.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.expanduser('~/Downloads/Games')
PSP_SRC = os.path.join(GAMES, 'Sony Playstation Portable--Corekiller')
DC_SRC = os.path.join(
    GAMES,
    '[CONTENT] Sega Dreamcast - Crystal Gems Collection - Volume 1 - '
    '[2023] [WIDESCREEN] [GAMES AND MOVIES] [CDI] (FuZzCasT)')
CACHE = os.path.join(HERE, '..', '.cache')

BRACKETS = re.compile(r'\s*[\[(][^\])]*[\])]')
SPACES = re.compile(r'\s+')


def psp_title(filename):
    stem = os.path.splitext(filename)[0]
    stem = re.sub(r'_PSP$', '', stem, flags=re.I)
    return SPACES.sub(' ', stem.replace('_', ' ')).strip()


def dc_title(dirname):
    name = re.sub(r'^\[GAME\]\s*Sega Dreamcast\s*-\s*', '', dirname)
    return SPACES.sub(' ', BRACKETS.sub('', name)).strip()


def stage(pairs, dest):
    if os.path.isdir(dest):
        for name in os.listdir(dest):
            os.unlink(os.path.join(dest, name))
    else:
        os.makedirs(dest)
    for src, name in pairs:
        os.symlink(src, os.path.join(dest, name))
    return len(pairs)


def collect_psp():
    out, seen = [], set()
    for root, _dirs, files in os.walk(PSP_SRC):
        for f in sorted(files):
            if not f.lower().endswith(('.cso', '.iso')):
                continue
            title = psp_title(f)
            if title.lower() in seen:
                continue
            seen.add(title.lower())
            out.append((os.path.join(root, f),
                        title + os.path.splitext(f)[1].lower()))
    return sorted(out, key=lambda p: p[1].lower())


def collect_dreamcast():
    """The pack's real games, named properly. Missing files are an error.

    A .gdi is an 88-byte index that means nothing without the track files
    beside it, so those titles are staged as their whole directory - which the
    scanner already reads as one game.
    """
    picks = [
        ('Crazy Taxi 2 (Europe)[DCCM][FZT].cdi', 'Crazy Taxi 2.cdi'),
        ('Daytona USA 2001 (Europe)[DCCM][WIDESCREEN][FZT].cdi', 'Daytona USA 2001.cdi'),
        ('Dead or Alive 2 (USA)[RDC][FZT].cdi', 'Dead or Alive 2.cdi'),
        ('Jet Set Radio (Europe)[DCP][WIDESCREEN][FZT].cdi', 'Jet Set Radio.cdi'),
        ('Quake III Arena (Europe)[RDC][WIDESCREEN[FZT].cdi', 'Quake III Arena.cdi'),
        ('Rez (Europe)[RDC[WIDESCREEN][FZT].cdi', 'Rez.cdi'),
        ('SA1-FZT-WIDE.cdi', 'Sonic Adventure.cdi'),
        ('SA2-FZT.cdi', 'Sonic Adventure 2.cdi'),
        ('Sonic Shuffle v1.000 (2001)(Sega)(PAL)(M4)[!].gdi', 'Sonic Shuffle'),
    ]

    found = {}
    for root, _dirs, files in os.walk(DC_SRC):
        for f in files:
            found.setdefault(f, os.path.join(root, f))

    out, missing = [], []
    for source, name in picks:
        path = found.get(source)
        if path is None:
            missing.append(source)
            continue
        # A .gdi needs its tracks, so the directory is the unit.
        out.append((os.path.dirname(path) if source.endswith('.gdi') else path, name))

    if missing:
        raise SystemExit('dreamcast source files not found:\n  ' + '\n  '.join(missing))
    return sorted(out, key=lambda p: p[1].lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true', help='rsync to the box')
    ap.add_argument('--system', choices=['psp', 'dreamcast'], action='append')
    args = ap.parse_args()

    wanted = args.system or ['psp', 'dreamcast']
    plan = {'psp': collect_psp, 'dreamcast': collect_dreamcast}

    for system in wanted:
        pairs = plan[system]()
        dest = os.path.join(CACHE, 'stage-' + system)
        count = stage(pairs, dest)
        size = sum(os.path.getsize(s) for s, _ in pairs)
        print('%s: %d titles, %.1f GB -> %s' % (system, count, size / 2**30, dest))
        for _src, name in pairs[:3]:
            print('   ', name)
        if count > 3:
            print('    ... and %d more' % (count - 3))

        if args.push:
            ip = subprocess.run([os.path.join(HERE, 'box'), '--print-ip'],
                                capture_output=True, text=True, check=True).stdout.strip()
            env = dict(os.environ, SSHPASS=os.environ.get('MARTYGAMES_BOX_PASS', 'coreelec'))
            cmd = ['sshpass', '-e', 'rsync', '-aL', '--partial', '--info=stats1',
                   '-e', 'ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR',
                   dest + '/', 'root@%s:/storage/sdcard/roms/%s/' % (ip, system)]
            print('    pushing to %s ...' % ip)
            rc = subprocess.call(cmd, env=env)
            if rc:
                sys.exit(rc)


if __name__ == '__main__':
    main()
