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


def release_key(name):
    return DISK.sub('', name)


def score(name):
    s = 0
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
    ap.add_argument('--want', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    by_title = {}
    for name in os.listdir(args.source):
        if name.lower().endswith('.zip'):
            by_title.setdefault(normalise(name), []).append(name)

    os.makedirs(args.out, exist_ok=True)
    wanted = [l.strip() for l in open(args.want, encoding='utf-8')
              if l.strip() and not l.startswith('#')]

    staged = missing = 0
    for title in wanted:
        hits = by_title.get(normalise(title), [])
        if not hits:
            print("      not found: %s" % title)
            missing += 1
            continue

        releases = {}
        for name in hits:
            releases.setdefault(release_key(name), []).append(name)
        best = max(releases, key=score)
        disks = releases[best]

        def disk_no(name):
            m = DISK.search(name)
            return int(m.group(1)) if m else 1
        disks.sort(key=disk_no)

        clean = scanner.clean_title(title)
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
            print("  %-38s %d disk(s)  <- %s" % (clean, len(written), best))
            staged += 1
        else:
            print("      no disk image inside: %s" % title)
            missing += 1

    print("\n  staged %d, missing %d" % (staged, missing))


if __name__ == '__main__':
    main()
