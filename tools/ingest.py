#!/usr/bin/env python3
"""Take new games from anywhere and land them on the box, enriched.

Replaces the hand-run sequence of copy -> fetch_artwork -> fetch_metadata ->
tar across, which had to be done in the right order and silently produced a
stale metadata.json when it was not.

The important design decision is that names are normalised at import rather
than at match time. Both enrichment sources key off No-Intro conventions, so a
strict ingest is what keeps the artwork hit rate high; the alternative is
growing art_overrides.json forever.

    ingest.py ~/Downloads/roms --dry-run
    ingest.py "~/Downloads/Sonic 3.zip" --system megadrive
    ingest.py ~/Downloads/games --no-push        # stage and enrich only
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'plugin.program.martygames'))
sys.path.insert(0, HERE)

from resources.lib import scanner            # noqa: E402
from resources.lib.systems import BY_KEY, SYSTEMS  # noqa: E402
from titles import normalise                 # noqa: E402

BOX = os.environ.get('MARTYGAMES_BOX', 'root@192.168.50.113')
BOX_ROMS = '/storage/sdcard/roms'
BOX_ARTWORK = '/storage/sdcard/artwork'
CACHE = os.path.join(ROOT, '.cache')
ARTWORK_CACHE = os.path.join(CACHE, 'artwork')
METADATA = os.path.join(ROOT, 'data', 'metadata.json')

ARCHIVES = ('.zip', '.7z', '.rar', '.tar', '.tar.gz', '.tgz', '.lha')

# Extension -> system key, from the same table the plugin scans with, so a new
# emulator only has to be declared in one place.
EXT_SYSTEM = {}
for _s in SYSTEMS:
    if _s.folder_games:
        continue
    for _e in _s.exts:
        EXT_SYSTEM.setdefault(_e, _s.key)

# Ambiguous extensions: several systems claim them, so they need --system.
for _e in ('.bin', '.cue', '.chd', '.zip', '.iso'):
    EXT_SYSTEM.pop(_e, None)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def have(tool):
    return shutil.which(tool) is not None


def unpack(path, dest):
    """Expand an archive into dest. Returns True if it was one."""
    low = path.lower()
    if not low.endswith(ARCHIVES):
        return False
    os.makedirs(dest, exist_ok=True)
    for cmd in (['bsdtar', '-xf', path, '-C', dest],
                ['7z', 'x', '-y', '-o' + dest, path],
                ['unar', '-q', '-o', dest, path]):
        if not have(cmd[0]):
            continue
        try:
            run(cmd)
            return True
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError('no extractor could open %s '
                       '(need bsdtar, 7z or unar on PATH)' % path)


def detect_system(path, override=None):
    if override:
        if override not in BY_KEY:
            raise SystemExit('unknown system %r (know: %s)'
                             % (override, ', '.join(sorted(BY_KEY))))
        return override
    if os.path.isdir(path):
        return 'dos'
    return EXT_SYSTEM.get(os.path.splitext(path)[1].lower())


def collect(src):
    """Yield every candidate game file or folder under src."""
    if os.path.isfile(src):
        yield src
        return
    for entry in sorted(os.listdir(src)):
        yield os.path.join(src, entry)


def staged_name(path, system):
    """The filename to store under, keeping multi-disc sets together.

    Only whitespace and separators are tidied. Region and dump tags are
    deliberately preserved: the scanner strips them for display and the
    enrichment matchers normalise them away, but they are what distinguishes
    two dumps of the same game on disk.
    """
    base = os.path.basename(path.rstrip('/'))
    base = re.sub(r'\s+', ' ', base.replace('_', ' ')).strip()
    return base


def existing_titles(system):
    """Titles already on the box for this system, as the plugin sees them."""
    tree = os.path.join(CACHE, 'romtree')
    if not os.path.isdir(os.path.join(tree, system)):
        return set()
    return {g['title'] for g in scanner.scan_system(tree, BY_KEY[system])}


def refresh_inventory():
    """Mirror the box's ROM tree locally as empty files, for scanning.

    The scanner needs a filesystem, not a listing, and the enrichment matchers
    only ever look at names - so an inventory of empty files is enough and
    avoids copying gigabytes back.
    """
    tree = os.path.join(CACHE, 'romtree')
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree, exist_ok=True)
    listing = ssh("cd %s && find . -type d | sed 's|^|D |'; "
                  "cd %s && find . -type f | sed 's|^|F |'" % (BOX_ROMS, BOX_ROMS))
    for line in listing.splitlines():
        kind, _, rel = line.partition(' ')
        rel = rel.lstrip('./')
        if not rel:
            continue
        target = os.path.join(tree, rel)
        if kind == 'D':
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            open(target, 'a').close()
    return tree


def ssh(command):
    env = dict(os.environ, SSHPASS=os.environ.get('MARTYGAMES_BOX_PASS', 'coreelec'))
    return subprocess.run(
        ['sshpass', '-e', 'ssh', '-o', 'StrictHostKeyChecking=no',
         '-o', 'LogLevel=ERROR', BOX, command],
        check=True, capture_output=True, text=True, env=env).stdout


def scp(src, dest):
    env = dict(os.environ, SSHPASS=os.environ.get('MARTYGAMES_BOX_PASS', 'coreelec'))
    subprocess.run(
        ['sshpass', '-e', 'scp', '-r', '-o', 'StrictHostKeyChecking=no',
         '-o', 'LogLevel=ERROR', src, dest],
        check=True, capture_output=True, text=True, env=env)


def stage(sources, system_override, staging):
    """Unpack, name and lay out everything under a per-system staging tree."""
    staged = []
    for src in sources:
        work = None
        path = src
        if os.path.isfile(src) and src.lower().endswith(ARCHIVES):
            work = tempfile.mkdtemp(prefix='ingest-')
            unpack(src, work)
            inner = [os.path.join(work, e) for e in sorted(os.listdir(work))]
            # A one-folder archive is the game; anything else is a bundle.
            if len(inner) == 1 and os.path.isdir(inner[0]):
                path = inner[0]
            else:
                for item in inner:
                    staged += stage([item], system_override, staging)
                continue
        system = detect_system(path, system_override)
        if system is None:
            print('  ?? unknown system, skipping: %s' % os.path.basename(path))
            continue
        dest_dir = os.path.join(staging, system)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, staged_name(path, system))
        if os.path.isdir(path):
            shutil.copytree(path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(path, dest)
        staged.append((system, dest))
        if work:
            shutil.rmtree(work, ignore_errors=True)
    return staged


def enrich(staging, systems):
    """Fetch art and metadata for the staged tree only, then merge."""
    art_out = os.path.join(CACHE, 'artwork-new')
    meta_out = os.path.join(CACHE, 'metadata-new.json')
    shutil.rmtree(art_out, ignore_errors=True)

    subprocess.run([sys.executable, os.path.join(HERE, 'fetch_artwork.py'),
                    '--roms', staging, '--out', art_out,
                    '--systems', ','.join(sorted(systems))], check=False)

    zip_path = os.path.join(CACHE, 'Metadata.zip')
    if os.path.exists(zip_path):
        subprocess.run([sys.executable, os.path.join(HERE, 'fetch_metadata.py'),
                        '--roms', staging, '--zip', zip_path,
                        '--out', meta_out], check=False)
    else:
        print('  !! %s missing - skipping metadata (download it to enable)'
              % zip_path)

    merged_art = 0
    if os.path.isdir(art_out):
        for root, _dirs, files in os.walk(art_out):
            rel = os.path.relpath(root, art_out)
            target = os.path.join(ARTWORK_CACHE, rel)
            os.makedirs(target, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(target, f))
                merged_art += 1

    merged_meta = 0
    if os.path.exists(meta_out):
        base = {}
        if os.path.exists(METADATA):
            with open(METADATA, encoding='utf-8') as fh:
                base = json.load(fh)
        with open(meta_out, encoding='utf-8') as fh:
            new = json.load(fh)
        for system, games in new.items():
            merged_meta += len(games)
            base.setdefault(system, {}).update(games)
        with open(METADATA, 'w', encoding='utf-8') as fh:
            json.dump(base, fh, indent=1, sort_keys=True, ensure_ascii=False)
    return merged_art, merged_meta


def push(staging, systems):
    for system in sorted(systems):
        src = os.path.join(staging, system)
        if os.path.isdir(src):
            ssh('mkdir -p %s/%s' % (BOX_ROMS, system))
            for entry in sorted(os.listdir(src)):
                scp(os.path.join(src, entry), '%s:%s/%s/' % (BOX, BOX_ROMS, system))
    ssh('mkdir -p %s' % BOX_ARTWORK)
    if os.path.isdir(ARTWORK_CACHE):
        for entry in sorted(os.listdir(ARTWORK_CACHE)):
            scp(os.path.join(ARTWORK_CACHE, entry), '%s:%s/' % (BOX, BOX_ARTWORK))
    # The plugin reads metadata.json from beside the artwork, and an artwork
    # push used to overwrite it with a stale copy - so it goes last, always.
    if os.path.exists(METADATA):
        scp(METADATA, '%s:%s/metadata.json' % (BOX, BOX_ARTWORK))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', help='file, folder or archive to ingest')
    ap.add_argument('--system', help='force a system key (needed for .bin/.cue/.zip)')
    ap.add_argument('--dry-run', action='store_true', help='stage and report only')
    ap.add_argument('--no-push', action='store_true', help='skip copying to the box')
    args = ap.parse_args()

    src = os.path.expanduser(args.path)
    if not os.path.exists(src):
        raise SystemExit('no such path: %s' % src)

    staging = os.path.join(CACHE, 'ingest')
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    print('staging from %s' % src)
    staged = stage(list(collect(src)), args.system, staging)
    if not staged:
        raise SystemExit('nothing to ingest')

    systems = sorted({s for s, _ in staged})
    print('\nstaged %d item(s) across %s:' % (len(staged), ', '.join(systems)))

    known = {}
    if not args.dry_run:
        try:
            refresh_inventory()
            known = {s: existing_titles(s) for s in systems}
        except Exception as exc:                            # noqa: BLE001
            print('  !! could not read the box inventory (%s); '
                  'duplicate detection skipped' % exc)

    for system in systems:
        for game in scanner.scan_system(staging, BY_KEY[system]):
            dupe = ' [already on the box]' if game['title'] in known.get(system, ()) else ''
            print('  %-10s %-44s %s%s' % (system, game['title'][:44],
                                          os.path.basename(game['path']), dupe))

    if args.dry_run:
        print('\ndry run: nothing copied, nothing fetched')
        return

    print('\nenriching...')
    art, meta = enrich(staging, systems)
    print('  %d artwork file(s), %d metadata record(s) merged' % (art, meta))

    if args.no_push:
        print('\n--no-push: staged at %s' % staging)
        return

    print('\npushing to %s...' % BOX)
    push(staging, systems)
    print('done. Restart Kodi or re-enter the games window to see them.')


if __name__ == '__main__':
    main()
