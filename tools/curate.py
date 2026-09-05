#!/usr/bin/env python3
"""Pick the best copy of each wanted title out of a full romset.

A complete TOSEC or GoodTools set carries a dozen files per game - cracks,
trainers, alternate dumps, every region and language. This scores the candidates
so the box gets one clean copy of each: the verified dump, in a language we can
read, and disk 1 of a multi-disk set rather than a random middle disk.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from titles import normalise                 # noqa: E402

# GoodTools/TOSEC flags, best first. Anything unlisted scores zero.
GOOD = ('[!]',)
BAD = ('[a', '[b', '[o', '[t', '[f', '[h', '[cr', '[tr', '(Beta', '(Proto',
       '(Demo', '(Sample', '(Alpha', '(Pirate', '(Unl', '[m')
REGION = (('(U)', 6), ('(UE)', 6), ('(USA)', 6), ('(E)', 5), ('(EU)', 5),
          ('(Europe)', 5), ('(W)', 5), ('(En)', 4), ('(JU)', 2), ('(J)', 1))
_DISK = re.compile(r'\(Disk (\d+) of (\d+)\)', re.I)


def score(name):
    s = 0
    for flag in GOOD:
        if flag in name:
            s += 10
    for flag in BAD:
        if flag in name:
            s -= 8
    for token, weight in REGION:
        if token in name:
            s += weight
            break
    else:
        # TOSEC names often carry no region at all; that is not a defect.
        s += 3
    m = _DISK.search(name)
    if m:
        # Only ever start a set on disk 1, but do not punish single-disk games.
        s += 4 if m.group(1) == '1' else -20
    return s


def index(source):
    by_title = {}
    for root, _dirs, files in os.walk(source):
        for name in files:
            if name.startswith('.'):
                continue
            key = normalise(name)
            if key:
                by_title.setdefault(key, []).append(os.path.join(root, name))
    return by_title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--want', required=True, help='file of titles, one per line')
    ap.add_argument('--out', required=True, help='file to write chosen paths to')
    args = ap.parse_args()

    by_title = index(args.source)
    wanted = [l.strip() for l in open(args.want, encoding='utf-8')
              if l.strip() and not l.startswith('#')]

    chosen, missing = [], []
    for title in wanted:
        hits = by_title.get(normalise(title), [])
        if not hits:
            missing.append(title)
            continue
        best = max(hits, key=lambda p: (score(os.path.basename(p)),
                                        -len(os.path.basename(p))))
        chosen.append((title, best))

    with open(args.out, 'w', encoding='utf-8') as fh:
        for _title, path in chosen:
            fh.write(path + '\n')

    for title, path in chosen:
        print("  %-42s %s" % (title, os.path.basename(path)))
    if missing:
        print("\n  not found (%d):" % len(missing))
        for title in missing:
            print("      %s" % title)
    print("\n  chose %d, missing %d" % (len(chosen), len(missing)))


if __name__ == '__main__':
    main()
