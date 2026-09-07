#!/usr/bin/env python3
"""Turn the extracted ScummVM collection into a library the box can launch.

The game id is not guessed. ScummVM itself is asked - `scummvm --detect` over
each game folder - because the collection's folder names describe editions
("Loom (CD - FM Towns)") and the same game can carry a different id per
edition. A wrong id is not a soft failure: the core refuses to start and says
only "Game not found".

Each game gets a `<Title>.scummvm` file holding that id, in its own folder.
That is enough on its own. The core reads the id, finds exactly one game
matching it, and launches with the containing folder as the game path - no
scummvm.ini entry required, which is one less piece of state to keep in sync.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACT = os.path.join(HERE, '..', '.cache', 'svm-extract')
SCUMMVM = ['flatpak', 'run', '--user', 'org.scummvm.ScummVM']
TAGS = re.compile(r'\s*\([^)]*\)\s*$')


def detect(path):
    """Ask ScummVM what this folder is. Returns 'engine:gameid' or None."""
    try:
        out = subprocess.run(SCUMMVM + ['--detect', '--path=' + path],
                             capture_output=True, text=True, timeout=120).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        print("   detect failed for %s: %s" % (os.path.basename(path), exc))
        return None
    ids = []
    for line in out.splitlines():
        m = re.match(r'^(\S+:\S+)\s+\S', line)
        if m:
            ids.append(m.group(1))
    if not ids:
        return None
    # More than one is a real ambiguity, not something to pick blindly from.
    if len(ids) > 1:
        print("   %s: %d candidates %s - skipped" %
              (os.path.basename(path), len(ids), ids[:3]))
        return None
    return ids[0]


def title_of(dirname):
    """'Loom (CD - FM Towns)' -> 'Loom'. Editions collapse; the id keeps them apart."""
    return TAGS.sub('', dirname).strip() or dirname


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--extract', default=EXTRACT)
    ap.add_argument('--limit', type=int)
    args = ap.parse_args()

    dirs = sorted(d for d in os.listdir(args.extract)
                  if os.path.isdir(os.path.join(args.extract, d)))
    if args.limit:
        dirs = dirs[:args.limit]

    ok = skipped = 0
    for d in dirs:
        path = os.path.join(args.extract, d)
        marker = os.path.join(path, title_of(d) + '.scummvm')
        if os.path.exists(marker):
            ok += 1
            continue
        target = detect(path)
        if not target:
            print("   no id: %s" % d)
            skipped += 1
            continue
        with open(marker, 'w', encoding='utf-8') as fh:
            fh.write(target)
        print("   %-52s %s" % (title_of(d)[:52], target))
        ok += 1

    print("\n%d ready, %d without a usable id" % (ok, skipped))


if __name__ == '__main__':
    main()
