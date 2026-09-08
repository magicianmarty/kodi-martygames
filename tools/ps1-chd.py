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
PSX_FIRST = [
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


DREAMCAST_FIRST = [
    'Shenmue', 'Sonic Adventure', 'Jet Grind Radio', 'Jet Set Radio',
    'Crazy Taxi', 'Soul Calibur', 'Power Stone', 'Skies of Arcadia',
    'Grandia II', 'Resident Evil', 'Code - Veronica', 'Marvel vs. Capcom',
    'Street Fighter III', 'Virtua Tennis', 'Dead or Alive 2', 'Rez',
    'Space Channel 5', 'Samba de Amigo', 'ChuChu Rocket', 'Phantasy Star',
    'Metropolis Street Racer', 'Test Drive Le Mans', 'Daytona',
    'Sega Rally', 'Hydro Thunder', 'San Francisco Rush', 'Quake III',
    'Unreal Tournament', 'Half-Life', 'Toy Commander', 'Ecco the Dolphin',
    'MDK2', 'Bangai-O', 'Ikaruga', 'Under Defeat', 'Border Down',
    'Guilty Gear', 'Capcom vs. SNK', 'Garou', 'King of Fighters',
    'NFL 2K', 'NBA 2K', 'Tony Hawk', 'Legacy of Kain', 'Headhunter',
    'Shadow Man', 'Silver', 'Evolution', 'Time Stalkers', 'Illbleed',
]

SATURN_FIRST = [
    'Panzer Dragoon', 'Nights into Dreams', 'Guardian Heroes', 'Radiant',
    'Shining Force III', 'Shining the Holy Ark', 'Dragon Force', 'Albert Odyssey',
    'Burning Rangers', 'Virtua Fighter', 'Fighters Megamix', 'Fighting Vipers',
    'Last Bronx', 'Virtua Cop', 'House of the Dead', 'Daytona', 'Sega Rally',
    'Sonic R', 'Sonic Jam', 'Sonic 3D', 'Astal', 'Clockwork Knight',
    'Bug!', 'Croc', 'Tomb Raider', 'Duke Nukem', 'Quake', 'Exhumed',
    'Powerslave', 'Alien Trilogy', 'Resident Evil', 'D', 'Enemy Zero',
    'Grandia', 'Magic Knight', 'Street Fighter', 'X-Men', 'Marvel Super Heroes',
    'Darkstalkers', 'Vampire Savior', 'King of Fighters', 'Samurai Shodown',
    'Metal Slug', 'Galactic Attack', 'Layer Section', 'Thunder Force',
    'Battle Garegga', 'Saturn Bomberman', 'Worms', 'Command & Conquer',
    'Wipeout', 'Manx TT', 'Sky Target', 'Die Hard Arcade', 'Christmas Nights',
]

FIRST_BY_SYSTEM = {'psx': PSX_FIRST, 'dreamcast': DREAMCAST_FIRST,
                   'saturn': SATURN_FIRST}

# names already sitting on the remote, so a resumed run does not redo them
ALREADY_REMOTE = set()


def priority(name, first=()):
    base = os.path.splitext(os.path.basename(name))[0]
    for i, want in enumerate(first):
        if want.lower() in base.lower():
            return (0, i, base.lower())
    return (1, 0, base.lower())


def push_away(path, remote):
    """Send one finished disc to the remote and drop the local copy.

    A full set is far larger than the scratch disk - Saturn is 250 GB against
    105 GB free - so the output cannot simply pile up until the end.
    """
    r = sh(['rsync', '-a', '--partial', path, remote + '/'])
    if r.returncode != 0:
        return 'push failed: ' + r.stderr.strip()[:70]
    os.remove(path)
    return None


def convert(archive, outdir, workroot, remote=None):
    name = os.path.splitext(os.path.basename(archive))[0]
    dest = os.path.join(outdir, name + '.chd')
    if os.path.exists(dest) or name in ALREADY_REMOTE:
        return name, 'skipped', ''

    work = tempfile.mkdtemp(prefix='ps1-', dir=workroot)
    try:
        r = sh(['bsdtar', '-xf', archive, '-C', work])
        if r.returncode != 0:
            return name, 'failed', 'unpack: ' + r.stderr.strip()[:80]

        # A .cdi is already one self-contained file and chdman will not read
        # one, but flycast plays it directly - so pass it through rather than
        # calling the disc a failure. Same for a bare .iso.
        loose = [os.path.join(d, f) for d, _, fs in os.walk(work)
                 for f in fs if f.lower().endswith(('.cdi', '.iso'))]
        if loose and not any(f.lower().endswith(('.cue', '.gdi', '.ccd'))
                             for _, _, fs in os.walk(work) for f in fs):
            src = sorted(loose)[0]
            out = os.path.join(outdir, name + os.path.splitext(src)[1].lower())
            if not os.path.exists(out):
                shutil.move(src, out)
            size = os.path.getsize(out) >> 20
            if remote:
                err = push_away(out, remote)
                if err:
                    return name, 'failed', err
            return name, 'copied', '%d MB' % size

        # Redump packs the cue beside its tracks, sometimes one folder down.
        # .ccd is CloneCD, which chdman reads as well - three Dreamcast discs
        # ship that way and were being discarded as "no cue sheet".
        cues = [os.path.join(d, f) for d, _, fs in os.walk(work)
                for f in fs if f.lower().endswith(('.cue', '.gdi', '.ccd'))]
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
        size = os.path.getsize(dest) / 1e6
        if remote:
            err = push_away(dest, remote)
            if err:
                return name, 'failed', err
        return name, 'converted', '%.0f MB' % size
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


def write_m3u_remote(remote, workdir):
    """Playlists for a pushed set, built from the remote listing.

    The discs are no longer on this machine, so write_m3u() has nothing to
    read; ask the remote what it holds instead, then send the playlists back.
    """
    host, _, rpath = remote.partition(':')
    listing = sh(['ssh', '-o', 'StrictHostKeyChecking=no', host,
                  'ls -1 %s 2>/dev/null' % rpath])
    sets = {}
    for f in sorted(listing.stdout.splitlines()):
        if not f.lower().endswith('.chd') or '(disc' not in f.lower():
            continue
        sets.setdefault(DISC.sub('', os.path.splitext(f)[0]), []).append(f)
    made = 0
    os.makedirs(workdir, exist_ok=True)
    for title, discs in sets.items():
        if len(discs) < 2:
            continue
        path = os.path.join(workdir, title + '.m3u')
        with open(path, 'w') as fh:
            fh.write(''.join(d + '\n' for d in sorted(discs)))
        if sh(['rsync', '-a', path, remote + '/']).returncode == 0:
            os.remove(path)
            made += 1
    return made


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='folder of Redump .7z archives')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--system', default='psx',
                    help='picks the title order and the ingest hint')
    ap.add_argument('--push-to', metavar='USER@HOST:/PATH',
                    help='rsync each finished disc there and delete it locally, '
                         'for a set larger than the scratch disk')
    ap.add_argument('--exclude', action='append', default=[], metavar='TEXT',
                    help='skip archives whose name contains TEXT '
                         '(case-insensitive); repeatable, e.g. --exclude "(Japan)"')
    args = ap.parse_args()

    ensure_image()
    if args.push_to:
        host, _, rpath = args.push_to.partition(':')
        listing = sh(['ssh', '-o', 'StrictHostKeyChecking=no', host,
                      'ls -1 %s 2>/dev/null' % rpath])
        ALREADY_REMOTE.update(os.path.splitext(l)[0]
                              for l in listing.stdout.splitlines() if l.strip())
        print('already on the remote: %d' % len(ALREADY_REMOTE))
    src = os.path.expanduser(args.src)
    skip = [t.lower() for t in args.exclude]
    names = [e for e in os.listdir(src) if e.lower().endswith(('.7z', '.zip'))]
    kept = [e for e in names if not any(t in e.lower() for t in skip)]
    if skip:
        print('excluding %d of %d archives (%s)'
              % (len(names) - len(kept), len(names), ', '.join(args.exclude)))
    first = FIRST_BY_SYSTEM.get(args.system, ())
    archives = sorted((os.path.join(src, e) for e in kept),
                      key=lambda n: priority(n, first))
    if args.limit:
        archives = archives[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    workroot = os.environ.get('TMPDIR', tempfile.gettempdir())

    tally = {}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(convert, a, args.out, workroot, args.push_to)
                   for a in archives]
        for fut in concurrent.futures.as_completed(futures):
            name, how, note = fut.result()
            tally[how] = tally.get(how, 0) + 1
            done += 1
            if how != 'skipped':
                print('%5d/%d %-9s %-58s %s'
                      % (done, len(archives), how, name[:58], note), flush=True)

    print('\n%s' % ', '.join('%s %d' % (k, v) for k, v in sorted(tally.items())))
    if args.push_to:
        print('playlists written: %d' % write_m3u_remote(args.push_to, args.out))
    else:
        print('playlists written: %d' % write_m3u(args.out))
    print('next: ingest.py %s --system %s' % (args.out, args.system))


if __name__ == '__main__':
    main()
