#!/usr/bin/env python3
"""Turn a Redump PlayStation set into CHDs the box can play.

The set ships one .7z per game holding a .cue and its .bin tracks. Extracted,
the USA set is roughly 700 GB; the box's PCSX-ReARMed declares
`bin|cue|img|mdf|pbp|toc|cbn|m3u|chd|iso|exe`, so CHD is available and is worth
taking - it is about half the size and one file per disc instead of a cue and
up to thirty track files.

    ps1-chd.py "~/Downloads/Games/[Redump.org] Sony PlayStation (USA) (20130213)/Games"
    ingest.py .cache/ps1-chd --system psx

Conversion is the long pole, so games are done in a deliberate order: the
titles worth having first, then everything else alphabetically. Stopping this
half way then leaves a good library rather than every game beginning with A.

Multi-disc games get an .m3u once all their discs exist, which is what lets the
core swap discs instead of the library showing "(Disc 2)" as its own game.
"""

import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMAGE = 'localhost/chdtools:trixie'
CTX = os.path.join(HERE, 'chd')
DEFAULT_OUT = os.path.join(ROOT, '.cache', 'ps1-chd')

# Done first, in this order. Everything not listed follows alphabetically.
FIRST = [
    'Final Fantasy VII', 'Final Fantasy VIII', 'Final Fantasy IX',
    'Final Fantasy Tactics', 'Metal Gear Solid', 'Castlevania - Symphony',
    'Resident Evil 2', 'Resident Evil 3', 'Resident Evil - Directors',
    'Silent Hill', 'Chrono Cross', 'Xenogears', 'Suikoden', 'Vagrant Story',
    'Legend of Dragoon', 'Parasite Eve', 'Breath of Fire', 'Valkyrie Profile',
    'Tekken 3', 'Tekken 2', 'Soul Blade', 'Street Fighter Alpha 3',
    'Marvel vs. Capcom', 'X-Men vs. Street Fighter', 'Rival Schools',
    'Bushido Blade', 'Gran Turismo', 'Ridge Racer', 'Wipeout', 'Colin McRae',
    'Need for Speed', 'Twisted Metal', 'Driver', 'Crash Bandicoot',
    'Spyro', 'Rayman', 'Oddworld', 'Tomb Raider', 'Medievil', 'MediEvil',
    'Ape Escape', 'Klonoa', 'Tombi', 'Pandemonium', 'Croc',
    'Metal Slug X', 'Castlevania - Chronicles', 'Alundra', 'Brave Fencer',
    'Einhander', 'R-Type Delta', 'Gradius', 'Raiden', 'Strider',
    'Symphony of the Night', 'Tactics Ogre', 'Front Mission 3',
    'Command & Conquer', 'Theme Hospital', 'Worms', 'Bomberman',
    'Point Blank', 'Time Crisis', 'Die Hard Trilogy', 'Syphon Filter',
    'Tony Hawk', 'ISS Pro', 'International Superstar', 'Micro Machines',
    'Grand Theft Auto', 'Duke Nukem', 'Doom', 'Quake', 'Descent',
    'Abe\'s Exoddus', 'Legacy of Kain', 'Soul Reaver', 'Thousand Arms',
    'Star Ocean', 'Wild Arms', 'Lunar', 'Grandia', 'Persona', 'Koudelka',
    'Threads of Fate', 'Chocobo', 'Harvest Moon', 'Monster Rancher',
    'Tenchu', 'Fear Effect', 'Dino Crisis', 'Nuclear Strike', 'Colony Wars',
    'Ace Combat', 'G-Police', 'Jet Moto', 'Rollcage', 'Destruction Derby',
]

DISC = re.compile(r'\s*\(Disc \d+\)', re.I)


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ensure_image():
    if sh(['podman', 'image', 'exists', IMAGE]).returncode != 0:
        subprocess.run(['podman', 'build', '-t', 'chdtools:trixie', CTX], check=True)


def priority(name):
    base = os.path.splitext(os.path.basename(name))[0]
    for i, want in enumerate(FIRST):
        if want.lower() in base.lower():
            return (0, i, base.lower())
    return (1, 0, base.lower())


def convert(archive, outdir, workroot):
    name = os.path.splitext(os.path.basename(archive))[0]
    dest = os.path.join(outdir, name + '.chd')
    if os.path.exists(dest):
        return name, 'skipped', ''

    work = tempfile.mkdtemp(prefix='ps1-', dir=workroot)
    try:
        r = sh(['bsdtar', '-xf', archive, '-C', work])
        if r.returncode != 0:
            return name, 'failed', 'unpack: ' + r.stderr.strip()[:80]

        # Redump packs the cue beside its tracks, sometimes one folder down.
        cues = [os.path.join(d, f) for d, _, fs in os.walk(work)
                for f in fs if f.lower().endswith(('.cue', '.gdi'))]
        if not cues:
            return name, 'failed', 'no cue sheet'
        cue = sorted(cues)[0]

        r = subprocess.run(
            ['podman', 'run', '--rm', '-v', '%s:/w:z' % work, '-w', '/w',
             IMAGE, 'chdman', 'createcd', '-f',
             '-i', os.path.relpath(cue, work), '-o', 'out.chd'],
            capture_output=True, text=True, timeout=3600)
        made = os.path.join(work, 'out.chd')
        if r.returncode != 0 or not os.path.exists(made):
            return name, 'failed', (r.stderr or r.stdout).strip().splitlines()[-1][:90]

        v = subprocess.run(
            ['podman', 'run', '--rm', '-v', '%s:/w:z' % work, '-w', '/w',
             IMAGE, 'chdman', 'info', '-i', 'out.chd'],
            capture_output=True, text=True, timeout=300)
        if v.returncode != 0:
            return name, 'failed', 'chd did not verify'

        os.makedirs(outdir, exist_ok=True)
        shutil.move(made, dest)
        return name, 'converted', '%.0f MB' % (os.path.getsize(dest) / 1e6)
    except subprocess.TimeoutExpired:
        return name, 'failed', 'timed out'
    finally:
        shutil.rmtree(work, ignore_errors=True)


def write_m3u(outdir):
    """One playlist per multi-disc game, so the core can swap discs."""
    sets = {}
    for f in sorted(os.listdir(outdir)):
        if not f.lower().endswith('.chd') or '(disc' not in f.lower():
            continue
        sets.setdefault(DISC.sub('', os.path.splitext(f)[0]), []).append(f)
    made = 0
    for title, discs in sets.items():
        if len(discs) < 2:
            continue
        path = os.path.join(outdir, title + '.m3u')
        body = ''.join(d + '\n' for d in sorted(discs))
        if not os.path.exists(path) or open(path).read() != body:
            open(path, 'w').write(body)
            made += 1
    return made


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='folder of Redump .7z archives')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--limit', type=int)
    args = ap.parse_args()

    ensure_image()
    src = os.path.expanduser(args.src)
    archives = sorted((os.path.join(src, e) for e in os.listdir(src)
                       if e.lower().endswith(('.7z', '.zip'))), key=priority)
    if args.limit:
        archives = archives[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    workroot = os.environ.get('TMPDIR', tempfile.gettempdir())

    tally = {}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(convert, a, args.out, workroot) for a in archives]
        for fut in concurrent.futures.as_completed(futures):
            name, how, note = fut.result()
            tally[how] = tally.get(how, 0) + 1
            done += 1
            if how != 'skipped':
                print('%5d/%d %-9s %-58s %s'
                      % (done, len(archives), how, name[:58], note), flush=True)

    print('\n%s' % ', '.join('%s %d' % (k, v) for k, v in sorted(tally.items())))
    print('playlists written: %d' % write_m3u(args.out))
    print('next: ingest.py %s --system psx' % args.out)


if __name__ == '__main__':
    main()
