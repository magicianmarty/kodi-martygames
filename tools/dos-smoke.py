#!/usr/bin/env python3
"""Launch each installed DOS game and check something happened.

dos-install.py proves an installer ran and left a launchable executable
behind. That is not the same as the game working: a half-finished install
leaves the .EXE in place and fails at its own first file read, and the
difference is invisible on disk. Nothing here should reach the box without
being started once.

Each game is run under DOSBox-X for a few seconds and photographed. A game
that never left the DOS prompt, that printed a DOS error, or that drew nothing
at all is reported failed and the screenshots kept.

    dos-smoke.py .cache/dos-installed
    dos-smoke.py ".cache/dos-installed/Descent (1995)" --keep

This is a smoke test, not emulation parity - it runs under DOSBox-X and the
box runs libretro dosbox_pure. It catches broken installs, which is what it is
for; it does not promise the game plays well.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'plugin.program.martygames'))

from resources.lib.scanner import _pick_dos_executable   # noqa: E402

IMAGE = 'localhost/dosinstall:trixie'
SMOKE = os.path.join(HERE, 'dosbox', 'smoke.sh')
RUNNER = os.path.join(HERE, 'dosbox', 'run-dosbox.sh')
DRIVER = os.path.join(HERE, 'dosbox', 'drive-install.py')

# Plenty of DOS games refuse to start until their own configuration program has
# been run once to pick a sound card. Blackthorne says so outright: "An Error
# has occured while running PC Blackthorne - Please run SETUP.EXE".
NEEDS_SETUP = ('run setup', 'reconfigure', 'setup.exe', 'not configured',
               'run install', 'no sound card', 'please configure')
SETUP_NAMES = ('setup', 'config', 'sound', 'install')

# What a failure looks like once the screen is read back as text.
BAD = ('bad command or file name', 'not enough memory', 'insufficient memory',
       'abnormal program termination', 'cannot find', 'file not found',
       'divide overflow', 'runtime error', 'general failure',
       'illegal instruction', 'error opening', 'unable to open')


STAT = os.path.join(HERE, 'chd', 'screenstat.py')


def read_screen(png):
    """(text, distinct colours) for one frame.

    Text alone cannot judge this. The runner presses Return every few seconds
    to get past title screens, which also walks into the game - and a Doom
    level renders as a dark corridor that OCRs as nothing at all, so a working
    install reads exactly like a blank screen. What separates them is how much
    is drawn: a DOS prompt is two or three colours, a game is hundreds.
    """
    r = subprocess.run(
        ['podman', 'run', '--rm', '-v', '%s:/s:ro,z' % os.path.dirname(png),
         '-v', '%s:/screenstat.py:ro,z' % STAT,
         IMAGE, 'python3', '/screenstat.py', '/s/' + os.path.basename(png)],
        capture_output=True, text=True)
    text, colours = '', 0
    for line in r.stdout.splitlines():
        if line.startswith('COLOURS '):
            colours = int(line.split()[1])
        elif line.startswith('TEXT '):
            text = line[5:]
    return text, colours


def verdict(shots):
    """(ok, why) from the last frames of the run."""
    frames = sorted(f for f in os.listdir(shots) if f.startswith('run-'))
    if not frames:
        return False, 'no frames captured'
    best = (False, 'no frames read')
    for name in reversed(frames[-3:]):
        text, colours = read_screen(os.path.join(shots, name))
        bad = next((b for b in BAD if b in text), None)
        if bad:
            return False, 'DOS error on screen: "%s"' % bad
        stripped = text.replace('main cpu video sound dos drive capture help', '').strip()
        if colours <= 4:
            best = (False, 'nothing drawn (%d colours)' % colours)
            continue
        # The autoexec ends at a prompt, so a bare prompt means the game
        # exited immediately or never started. Text mode is a handful of
        # colours; anything richer is the game drawing.
        if colours < 24 and ('c:\\>' in stripped or stripped.endswith('c:\\')):
            best = (False, 'sitting at the DOS prompt')
            continue
        return True, ''
    return best


def find_setup(folder):
    """The game's own configuration program, if it ships one."""
    for root, _dirs, files in os.walk(folder):
        if root[len(folder):].count(os.sep) > 1:
            continue
        for f in sorted(files):
            stem, ext = os.path.splitext(f.lower())
            if ext in ('.exe', '.bat', '.com') and any(
                    stem.startswith(n) for n in SETUP_NAMES):
                return os.path.join(root, f)
    return None


def configure(folder, setup, seconds=90):
    """Run the game's setup once, with the installer driver answering it."""
    shots = tempfile.mkdtemp(prefix='setup-', dir=os.environ.get('TMPDIR', '/tmp'))
    rel = os.path.relpath(setup, folder).replace('/', '\\')
    conf = os.path.join(shots, 'setup.conf')
    with open(conf, 'w') as fh:
        fh.write('[dosbox]\nmemsize=32\n[cpu]\ncore=dynamic\ncycles=max\n'
                 '[dos]\nver=6.22\nxms=true\nems=true\numb=true\n'
                 '[autoexec]\nmount c "/game"\nc:\ncd "%s"\n%s\n'
                 % (os.path.dirname(rel) or '\\', os.path.basename(rel)))
    try:
        subprocess.run(
            ['podman', 'run', '--rm',
             '-v', '%s:/game:z' % os.path.abspath(folder),
             '-v', '%s:/shots:z' % shots,
             '-v', '%s:/run-dosbox.sh:ro,z' % RUNNER,
             '-v', '%s:/drive-install.py:ro,z' % DRIVER,
             IMAGE, '/run-dosbox.sh', '/shots/setup.conf', str(seconds),
             '/shots', '/game', 'setup'],
            capture_output=True, text=True, timeout=seconds + 180)
    except subprocess.TimeoutExpired:
        pass
    finally:
        shutil.rmtree(shots, ignore_errors=True)


def smoke(folder, seconds, keep, fix=False):
    name = os.path.basename(folder.rstrip('/'))
    exe = _pick_dos_executable(folder)
    if not exe:
        print('%-46s SKIP  nothing launchable' % name[:46])
        return 'skipped'

    rel = os.path.relpath(exe, folder).replace('/', '\\')
    shots = tempfile.mkdtemp(prefix='smoke-', dir=os.environ.get('TMPDIR', '/tmp'))
    conf = os.path.join(shots, 'run.conf')
    with open(conf, 'w') as fh:
        # No exit: it fires the moment the game returns, DOSBox closes and
        # every frame after that is black - indistinguishable from a game that
        # never started. Left at the prompt, the two are easy to tell apart.
        fh.write('[dosbox]\nmemsize=32\n[cpu]\ncore=dynamic\ncycles=max\n'
                 '[dos]\nver=6.22\nxms=true\nems=true\numb=true\n'
                 '[autoexec]\nmount c "%s"\nc:\ncd "%s"\n%s\n'
                 % ('/game', os.path.dirname(rel) or '\\', os.path.basename(rel)))
    try:
        subprocess.run(
            ['podman', 'run', '--rm',
             '-v', '%s:/game:z' % os.path.abspath(folder),
             '-v', '%s:/shots:z' % shots,
             '-v', '%s:/smoke.sh:ro,z' % SMOKE,
             IMAGE, '/smoke.sh', '/shots/run.conf', str(seconds), '/shots'],
            capture_output=True, text=True, timeout=seconds + 180)
        ok, why = verdict(shots)
        if not ok and fix and any(w in why for w in ('DOS prompt', 'DOS error')):
            setup = find_setup(folder)
            if setup:
                print('%-46s ..    running %s first'
                      % (name[:46], os.path.basename(setup)))
                configure(folder, setup)
                for f in os.listdir(shots):
                    if f.startswith('run-'):
                        os.remove(os.path.join(shots, f))
                subprocess.run(
                    ['podman', 'run', '--rm',
                     '-v', '%s:/game:z' % os.path.abspath(folder),
                     '-v', '%s:/shots:z' % shots,
                     '-v', '%s:/smoke.sh:ro,z' % SMOKE,
                     IMAGE, '/smoke.sh', '/shots/run.conf', str(seconds), '/shots'],
                    capture_output=True, text=True, timeout=seconds + 180)
                ok, why = verdict(shots)
        print('%-46s %s  %s' % (name[:46], 'ok  ' if ok else 'FAIL', why))
        if not ok or keep:
            hold = os.path.join(ROOT, '.cache', 'smoke', name)
            os.makedirs(os.path.dirname(hold), exist_ok=True)
            shutil.rmtree(hold, ignore_errors=True)
            shutil.copytree(shots, hold)
        return 'ok' if ok else 'failed'
    except subprocess.TimeoutExpired:
        print('%-46s FAIL  timed out' % name[:46])
        return 'failed'
    finally:
        shutil.rmtree(shots, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', help='installed game folder, or a folder of them')
    ap.add_argument('--seconds', type=int, default=25)
    ap.add_argument('--keep', action='store_true', help='keep frames for passes too')
    ap.add_argument('--fix', action='store_true',
                    help="run the game's own setup and retry when it asks for it")
    args = ap.parse_args()

    folders = []
    for p in args.paths:
        p = os.path.expanduser(p.rstrip('/'))
        # A folder of games also looks launchable, because the picker searches
        # two levels down and finds the first game's executable. What settles
        # it is whether the children are games in their own right.
        kids = [os.path.join(p, e) for e in sorted(os.listdir(p))
                if os.path.isdir(os.path.join(p, e)) and not e.startswith('_')] \
            if os.path.isdir(p) else []
        # Two or more, not any: a single game whose files live one folder
        # down - 5th Fleet keeps FLEET.EXE in FLEET/ - has exactly one
        # launchable child and is still one game, not a collection.
        if sum(1 for k in kids if _pick_dos_executable(k)) >= 2:
            folders += kids
        else:
            folders.append(p)

    tally = {}
    for f in folders:
        r = smoke(f, args.seconds, args.keep, args.fix)
        tally[r] = tally.get(r, 0) + 1
    print('\n%s' % ', '.join('%s %d' % (k, v) for k, v in sorted(tally.items())))


if __name__ == '__main__':
    main()
