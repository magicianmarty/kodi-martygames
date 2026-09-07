#!/usr/bin/env python3
"""Stage Amiga titles out of a TOSEC set, one clean release per game.

TOSEC carries every crack, trainer and alternate dump of every release, split
across disks. Nearly every Amiga file is cracked, so unlike a cartridge set a
[cr] tag cannot be a disqualifier - what we filter is alternates, bad dumps,
trainers and hacks. Disks of one release are then kept together in a folder,
which is what the scanner expects: it starts a multi-disk game on disk 1 and
lets RetroPlayer's disc control swap from there.
"""

import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'plugin.program.martygames'))
sys.path.insert(0, os.path.dirname(__file__))
from resources.lib import scanner            # noqa: E402
from titles import normalise                 # noqa: E402

DISK = re.compile(r'\s*\(Disk (\d+) of (\d+)\)', re.I)
# Cracks are the norm on Amiga; these are the ones that actually hurt.
PENALTY = ('[a', '[b', '[f', '[h', '[m', '[t', '(Demo', '(Preview', '(Beta',
           '(Alpha', '[o', '(Coverdisk')
LANGUAGE = ('(De)', '(Fr)', '(It)', '(Es)', '(Sw)', '(Pl)', '(Cz)', '(Nl)',
            '(Dk)', '(Fi)', '(Gr)')
# Not worth staging at all when it is the best copy there is.
REJECT = ('(Demo)', '(Demo-', '(Preview)', '(Beta)', '(Alpha)', '[b]', '[b ',
          '[data disk]', '[docs]', '[doc]', '[utility]', '(Coverdisk)')
# TOSEC always dates a release. Around 2,400 files here carry no date at all -
# a second, loosely named set mixed into the same folder, mostly duplicates
# under manglings like "a-10tkiller.zip" that normalise to their own title and
# would otherwise import as separate games.
DATED = re.compile(r'\((19|20)\d{2}(-\d{2})*\)')
# "A-10 Tank Killer", "... v1.0" and "... v1.5" are one game, not three.
VERSION = re.compile(r'\s+v\d+(\.\d+)*[a-z]?(?=\s|\.|$)', re.I)


def release_key(name):
    return DISK.sub('', name)


def title_key(name):
    return normalise(VERSION.sub('', name))


def score(name):
    s = 0
    if not DATED.search(name):
        s -= 30
    for flag in PENALTY:
        if flag in name:
            s -= 5
    for flag in LANGUAGE:
        if flag in name:
            s -= 6
    if '(AGA)' in name:
        s -= 1          # plain ECS builds are the safer default under PUAE
    return s - len(name) / 500.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--want', help='file of titles, one per line')
    ap.add_argument('--all', action='store_true',
                    help='stage every title in the set, best release of each')
    ap.add_argument('--out', required=True)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--dated-only', action='store_true',
                    help='skip titles whose only copy carries no TOSEC date')
    args = ap.parse_args()
    if not args.want and not args.all:
        ap.error('give --want or --all')

    by_title = {}
    for name in os.listdir(args.source):
        if name.lower().endswith('.zip'):
            by_title.setdefault(title_key(name), []).append(name)

    os.makedirs(args.out, exist_ok=True)
    if args.all:
        # The set's own titles, rather than a list to look up. Sorted so a run
        # that is cut short can be resumed and lands in the same place.
        wanted = sorted(by_title)
    else:
        wanted = [l.strip() for l in open(args.want, encoding='utf-8')
                  if l.strip() and not l.startswith('#')]
    if args.limit:
        wanted = wanted[:args.limit]

    staged = missing = skipped = 0
    for title in wanted:
        hits = by_title.get(title if args.all else title_key(title), [])
        if not hits:
            print("      not found: %s" % title)
            missing += 1
            continue

        releases = {}
        for name in hits:
            releases.setdefault(release_key(name), []).append(name)
        best = max(releases, key=score)
        # In --all the whole set is walked, so releases arrive that a hand
        # written want list would never have named. If the best copy of a
        # title is still a demo or a known bad dump, there is no good copy.
        if any(f in best for f in REJECT):
            skipped += 1
            continue
        if args.dated_only and not DATED.search(best):
            skipped += 1
            continue
        disks = releases[best]

        def disk_no(name):
            m = DISK.search(name)
            return int(m.group(1)) if m else 1
        disks.sort(key=disk_no)

        clean = scanner.clean_title(title if not args.all else best)
        target = os.path.join(args.out, clean) if len(disks) > 1 else args.out
        os.makedirs(target, exist_ok=True)

        written = []
        for name in disks:
            with zipfile.ZipFile(os.path.join(args.source, name)) as z:
                adfs = [i for i in z.infolist()
                        if i.filename.lower().endswith(('.adf', '.adz', '.dms'))]
                if not adfs:
                    continue
                info = max(adfs, key=lambda i: i.file_size)
                ext = os.path.splitext(info.filename)[1].lower()
                if len(disks) > 1:
                    fname = '%s (Disk %d)%s' % (clean, disk_no(name), ext)
                else:
                    fname = clean + ext
                with z.open(info) as src, \
                        open(os.path.join(target, fname), 'wb') as fh:
                    fh.write(src.read())
                written.append(fname)
        if written:
            # A folder of disks is not a game to the scanner - the playlist
            # beside it is what the library lists and what lets the core swap
            # disks. Without this a multi-disk title stages and then simply
            # does not appear.
            if len(written) > 1:
                with open(os.path.join(args.out, clean + '.m3u'), 'w',
                          encoding='utf-8') as fh:
                    fh.write(''.join('%s/%s\n' % (clean, w) for w in written))
            print("  %-38s %d disk(s)  <- %s" % (clean, len(written), best))
            staged += 1
        else:
            print("      no disk image inside: %s" % title)
            missing += 1

    print("\n  staged %d, missing %d, no good copy %d" % (staged, missing, skipped))


if __name__ == '__main__':
    main()
