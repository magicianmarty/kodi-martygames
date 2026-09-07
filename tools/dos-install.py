#!/usr/bin/env python3
"""Install a DOS game from its original install disks, so it can be imported.

Most of the DOS collection is already-installed game folders, which ingest.py
handles directly. A minority are the release's *install media* instead: the
data lives in a proprietary archive that only its own INSTALL.EXE can read, so
importing the folder gives a library entry that cannot launch. ingest.py
detects and skips those.

This is the other half - it produces the installed folder those releases are
missing, and leaves it somewhere ingest.py can take over:

    dos-install.py "Ultima Viii Pagan (1994)(Origin Systems Inc).7z"
    ingest.py .cache/dos-installed --system dos

Two routes, cheapest first. Some install media is a standard archive wearing a
game's extension - ARJ multi-volume behind DEARJ.EXE, LHA behind LHA.EXE - and
a native extractor reads it in a second with no emulation at all. What is left
is genuinely proprietary (PC-Install, Epic's INSTALL.BIN, TTComp), and for
those the only thing that can read the format is the installer itself, so it
gets run under DOSBox-X with its prompts answered by scripted keystrokes.

Both routes are checked the same way: the scanner has to find something
launchable in the result, otherwise the game is reported failed rather than
imported broken. --keep-shots leaves a screenshot every five seconds of the
DOSBox run, which is the only practical way to see which prompt an installer
stopped on.
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

from resources.lib.scanner import _pick_dos_executable   # noqa: E402
from ingest import archive_stem                          # noqa: E402

IMAGE = 'localhost/dosinstall:trixie'
CTX = os.path.join(HERE, 'dosbox')
RUNNER = os.path.join(CTX, 'run-dosbox.sh')
DRIVER = os.path.join(CTX, 'drive-install.py')
PROFILES = os.path.join(HERE, 'dos_installers.json')
DEFAULT_OUT = os.path.join(ROOT, '.cache', 'dos-installed')

INSTALLER_NAMES = ('install', 'instl', 'setup', 'inst')
JUNK = {'dos4gw.exe', 'dos32a.exe', 'pkunzip.exe', 'unzip.exe', 'lha.exe',
        'arj.exe', 'dearj.exe', 'deice.exe'}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def podman(args, mounts, timeout=1800):
    cmd = ['podman', 'run', '--rm']
    for host, dest in mounts:
        cmd += ['-v', '%s:%s:z' % (host, dest)]
    cmd += [IMAGE] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def magic(path):
    return sh(['file', '-b', path]).stdout.strip()


def ensure_image():
    if sh(['podman', 'image', 'exists', IMAGE]).returncode == 0:
        return
    print('.. building %s' % IMAGE)
    subprocess.run(['podman', 'build', '-t', 'dosinstall:trixie', CTX], check=True)


def load_profiles():
    if os.path.exists(PROFILES):
        with open(PROFILES) as fh:
            return json.load(fh)
    return {'default': {'keys': ['enter'] * 30, 'pace': 1.0, 'wait': 5,
                        'seconds': 120}}


def first_volume(src, kinds):
    """The first file in src whose magic matches, in volume order."""
    hits = []
    for entry in sorted(os.listdir(src)):
        path = os.path.join(src, entry)
        if not os.path.isfile(path):
            continue
        m = magic(path)
        if any(m.startswith(k) for k in kinds):
            hits.append((entry.lower(), path))
    return hits[0][1] if hits else None


def find_installer(src):
    """The executable that installs this release, if there is one."""
    cands = []
    for entry in sorted(os.listdir(src)):
        low = entry.lower()
        if not low.endswith(('.exe', '.bat', '.com')):
            continue
        if low in JUNK:
            continue
        stem = os.path.splitext(low)[0]
        if any(stem.startswith(n) for n in INSTALLER_NAMES):
            cands.append(entry)
    # A .bat wrapper knows the arguments the .exe needs, so prefer it.
    cands.sort(key=lambda e: (not e.lower().endswith('.bat'), e))
    return cands[0] if cands else None


def runnable(folder):
    return _pick_dos_executable(folder) is not None


def total_bytes(folder):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(folder) for f in fs)


def flatten(out):
    """Hoist the game up if the extractor wrapped it in one folder of its own."""
    inner = os.listdir(out)
    if len(inner) != 1:
        return
    only = os.path.join(out, inner[0])
    if not os.path.isdir(only):
        return
    # Renamed out of the way first: Ecstatica extracts to ECSTATIC/ECSTATIC,
    # and lifting that straight up collides with the folder being emptied.
    lift = only + '.__lift'
    os.rename(only, lift)
    for e in os.listdir(lift):
        shutil.move(os.path.join(lift, e), os.path.join(out, e))
    os.rmdir(lift)


def looks_complete(out, payload_bytes):
    """Did the extractor actually finish, or stop at a volume boundary?

    Checking for a launchable executable is not enough. A multi-volume set
    whose chain the extractor did not follow still yields the game's .EXE from
    volume one - Lure Of The Temptress came out with LURE.EXE present and
    DISK4.VGA at zero bytes, which imports and then fails at the title screen.
    A truncated member is written empty, and the whole install is necessarily
    larger than the compressed media it came from.
    """
    if not runnable(out):
        return False, 'nothing launchable'
    empty = [f for r, _, fs in os.walk(out) for f in fs
             if os.path.getsize(os.path.join(r, f)) == 0]
    if empty:
        return False, 'truncated (%d empty file(s): %s)' % (
            len(empty), ', '.join(sorted(empty)[:3]))
    got = total_bytes(out)
    if payload_bytes and got < payload_bytes * 0.8:
        return False, 'only %.1f MB out of %.1f MB of media' % (
            got / 1e6, payload_bytes / 1e6)
    return True, ''


RAR_TAIL = re.compile(r'\.(r\d\d|rar)$', re.I)


def normalise_rar_volumes(src, first):
    """Rename a RAR set from .001/.002 to the .rar/.r00 chain extractors follow.

    These releases number their volumes like every other DOS installer, so an
    extractor handed volume one has no way to know volume two exists and stops
    there without complaining.
    """
    if RAR_TAIL.search(first):
        return first
    stem = os.path.splitext(os.path.basename(first))[0]
    vols = sorted(e for e in os.listdir(src)
                  if e.lower().startswith(stem.lower() + '.')
                  and re.fullmatch(r'\d{3}', e.rsplit('.', 1)[-1]))
    if not vols:
        return first
    for i, name in enumerate(vols):
        tail = 'rar' if i == 0 else 'r%02d' % (i - 1)
        os.rename(os.path.join(src, name),
                  os.path.join(src, '%s.%s' % (stem, tail)))
    return os.path.join(src, '%s.rar' % stem)


def clear(folder):
    """Leave nothing half-written for the next route to trip over."""
    for e in os.listdir(folder):
        path = os.path.join(folder, e)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)


def try_sfx(src, out):
    """Media that is one self-extracting archive rather than an installer.

    3D Ball Blaster ships a single INSTALL.EXE that file(1) identifies as an
    "LHa self-extracting archive"; running it under DOSBox means answering a
    German prompt for a destination path, and lhasa reads it directly instead.
    """
    cands = sorted(((os.path.getsize(os.path.join(src, e)), e)
                    for e in os.listdir(src)
                    if e.lower().endswith('.exe')
                    and 'self-extracting' in magic(os.path.join(src, e)).lower()),
                   reverse=True)
    for size, name in cands:
        for cmd in (['lhasa', 'xw=/out', '/src/' + name],
                    ['7z', 'x', '-y', '-o/out', '/src/' + name],
                    ['unar', '-q', '-f', '-o', '/out', '/src/' + name]):
            podman(['sh', '-c', 'cd /out && ' + ' '.join("'%s'" % a for a in cmd)],
                   [(src, '/src'), (out, '/out')], timeout=900)
            flatten(out)
            ok, why = looks_complete(out, size)
            if ok:
                print('  .. self-extracting archive, read with %s' % cmd[0])
                return True
            clear(out)
    return False


SPLIT = re.compile(r'^(.+)\.(\d{1,3})$')


def try_split_sfx(src, out):
    """Media that is one self-extracting archive cut into numbered pieces.

    id Software shipped Doom, Heretic and Hexen as DEICE.EXE plus DOOM1_2R.1
    through .4. file(1) calls the first piece an "LHa self-extracting archive"
    and every extractor reads it and stops, returning nine files and a non-zero
    exit - the rest of the archive is in the other three. They are a split
    file, not volumes, so joining them end to end gives one archive that lhasa
    reads straight through.
    """
    groups = {}
    for e in os.listdir(src):
        m = SPLIT.match(e)
        if m and os.path.isfile(os.path.join(src, e)):
            groups.setdefault(m.group(1), []).append((int(m.group(2)), e))

    for stem, parts in sorted(groups.items()):
        if len(parts) < 2:
            continue
        parts.sort()
        first = os.path.join(src, parts[0][1])
        kind = magic(first).lower()
        if 'self-extracting' not in kind and not kind.startswith('lha'):
            continue
        names = ' '.join("'%s'" % name for _, name in parts)
        payload = sum(os.path.getsize(os.path.join(src, n)) for _, n in parts)
        for tool in ("lhasa xw=/out /tmp/joined.bin",
                     "7z x -y -o/out /tmp/joined.bin",
                     "unar -q -f -o /out /tmp/joined.bin"):
            podman(['sh', '-c',
                    'cd /src && cat %s > /tmp/joined.bin && cd /out && %s'
                    % (names, tool)],
                   [(src, '/src'), (out, '/out')], timeout=900)
            flatten(out)
            ok, why = looks_complete(out, payload)
            if ok:
                print('  .. split archive rejoined (%d parts, %s)'
                      % (len(parts), tool.split()[0]))
                return True
            clear(out)
    return False


def try_native(src, out):
    """Extract install media that is really a standard archive. Cheap, exact."""
    attempts = [
        ('ARJ', ('ARJ archive data',),
         lambda v: ['arj', 'x', '-v', '-y', '/src/' + os.path.basename(v)]),
        ('LHA', ('LHa ', 'LHarc '),
         lambda v: ['lhasa', 'xw=/out', '/src/' + os.path.basename(v)]),
        ('RAR/ARC/ZIP', ('RAR archive data', 'ARC archive data', 'Zip archive'),
         lambda v: ['unar', '-q', '-f', '-o', '/out', '/src/' + os.path.basename(v)]),
    ]
    for label, kinds, build in attempts:
        vol = first_volume(src, kinds)
        if not vol:
            continue
        if label.startswith('RAR'):
            vol = normalise_rar_volumes(src, vol)
        payload = sum(os.path.getsize(os.path.join(src, e))
                      for e in os.listdir(src)
                      if os.path.isfile(os.path.join(src, e))
                      and not e.lower().endswith(('.exe', '.bat', '.com', '.txt')))
        r = podman(['sh', '-c', 'cd /out && ' + ' '.join(
            "'%s'" % a for a in build(vol))],
            [(src, '/src'), (out, '/out')], timeout=900)
        flatten(out)
        ok, why = looks_complete(out, payload)
        if ok:
            print('  .. %s payload extracted natively' % label)
            return True
        print('  .. %s route rejected: %s' % (label, why))
        clear(out)
    return False


def try_dosbox(src, out, installer, profile, shots, keep_shots, title):
    """Run the release's own installer, with drive-install.py answering it."""
    conf = os.path.join(src, '_install.conf')
    stem = os.path.splitext(installer)[0].upper()
    drive = profile.get('drive', 'd')
    with open(conf, 'w') as fh:
        fh.write(
            '[dosbox]\nmemsize=16\n'
            '[cpu]\ncore=dynamic\ncycles=max\n'
            '[dos]\nver=6.22\n'
            '[autoexec]\n'
            'mount c /out\n'
            'mount a /src -t floppy\n'
            'mount d /src -t cdrom\n'
            '%s:\n%s\nc:\nexit\n' % (drive, stem))

    r = podman(['/run-dosbox.sh', '/src/_install.conf',
                str(profile['seconds']), '/shots', '/out', title],
               [(src, '/src'), (out, '/out'), (shots, '/shots'),
                (RUNNER, '/run-dosbox.sh'), (DRIVER, '/drive-install.py')],
               timeout=profile['seconds'] + 180)
    os.remove(conf)
    flatten(out)
    ok, why = looks_complete(out, 0)
    if not ok:
        print('  .. installer result rejected: %s' % why)
    if ok and not keep_shots:
        for e in os.listdir(shots):
            if e.endswith('.png'):
                os.remove(os.path.join(shots, e))
    return ok, r


def install_one(archive, outdir, profiles, keep_shots, workroot):
    name = archive_stem(archive)
    dest = os.path.join(outdir, name)
    if os.path.exists(dest):
        print('== %s\n  .. already installed, skipping' % name)
        return 'skipped'

    print('== %s' % name)
    work = tempfile.mkdtemp(prefix='dosinstall-', dir=workroot)
    src, out = os.path.join(work, 'src'), os.path.join(work, 'out')
    shots = os.path.join(work, 'shots')
    for d in (src, out, shots):
        os.makedirs(d)
    try:
        r = sh(['bsdtar', '-xf', archive, '-C', src])
        if r.returncode != 0:
            print('  !! could not unpack: %s' % r.stderr.strip()[:120])
            return 'failed'

        # A release packed as one folder puts the install media one level down.
        inner = [os.path.join(src, e) for e in os.listdir(src)]
        if len(inner) == 1 and os.path.isdir(inner[0]):
            src = inner[0]

        if try_native(src, out) or try_sfx(src, out) or try_split_sfx(src, out):
            shutil.move(out, dest)
            return 'installed'

        installer = find_installer(src)
        if not installer:
            print('  !! no installer found and no native route')
            return 'failed'

        key = installer.lower()
        profile = dict(profiles.get('default'))
        profile.update(profiles.get(name, profiles.get(key, {})))
        print('  .. running %s under DOSBox (%ss)' % (installer, profile['seconds']))
        ok, r = try_dosbox(src, out, installer, profile, shots, keep_shots, name)
        if not ok and (r.stdout.strip() or r.stderr.strip()):
            for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
                print('     | %s' % line[:150])
        if ok:
            print('  .. installed, %d files' % sum(len(f) for _, _, f in os.walk(out)))
            shutil.move(out, dest)
            return 'installed'

        got = sum(len(f) for _, _, f in os.walk(out))
        print('  !! installer produced nothing launchable (%d files)' % got)
        # Always, not only under --keep-shots: a failure with no screenshots
        # and no decision log cannot be diagnosed without running it again.
        hold = os.path.join(outdir, '_failed', name)
        os.makedirs(os.path.dirname(hold), exist_ok=True)
        shutil.rmtree(hold, ignore_errors=True)
        shutil.move(shots, hold)
        print('     screenshots: %s' % hold)
        return 'failed'
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help='install-media archive(s), or a folder of them')
    ap.add_argument('--out', default=DEFAULT_OUT, help='where installed games land')
    ap.add_argument('--keep-shots', action='store_true',
                    help='keep DOSBox screenshots (always kept on failure)')
    ap.add_argument('--limit', type=int, help='stop after N archives')
    args = ap.parse_args()

    ensure_image()
    profiles = load_profiles()
    os.makedirs(args.out, exist_ok=True)
    workroot = os.environ.get('TMPDIR', tempfile.gettempdir())

    archives = []
    for p in args.paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            archives += [os.path.join(p, e) for e in sorted(os.listdir(p))
                         if e.lower().endswith(('.7z', '.zip', '.rar'))]
        else:
            archives.append(p)
    if args.limit:
        archives = archives[:args.limit]

    tally = {}
    for a in archives:
        try:
            r = install_one(a, args.out, profiles, args.keep_shots, workroot)
        except subprocess.TimeoutExpired:
            print('  !! timed out')
            r = 'failed'
        tally[r] = tally.get(r, 0) + 1

    print('\n%s' % ', '.join('%s %d' % (k, v) for k, v in sorted(tally.items())))
    print('next: ingest.py %s --system dos' % args.out)


if __name__ == '__main__':
    main()
