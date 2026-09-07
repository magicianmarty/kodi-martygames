#!/usr/bin/env python3
"""Remove ROMs of an unwanted region from the box, and only their artwork.

    purge-region.py --tag "(J)" --tag "(Japan)"          # what would go
    purge-region.py --tag "(J)" --tag "(Japan)" --apply

Artwork is keyed on the *normalised* title, so "Donkey Kong 64 (J)" and
"Donkey Kong 64 (U)" name the same file. Deleting the Japanese ROM's artwork
therefore blanks the American one too, which is exactly what happened the first
time this was done by hand: three surviving games lost their covers. Artwork is
only removed once no remaining ROM in that system still resolves to the title.

Multi-region tags are deliberately not matched by "(J)": (JU) and (JUE) are the
American release as well, so they stay.
"""

import argparse
import re
import subprocess
import sys

ROMS = '/storage/sdcard/roms'
ART = '/storage/sdcard/artwork'
TAGS = re.compile(r'\s*[(\[][^)\]]*[)\]]')


def box(cmd):
    out = subprocess.run(['./tools/box', cmd], capture_output=True, text=True)
    return out.stdout.splitlines()


def title_of(filename):
    base = filename.rsplit('.', 1)[0]
    return TAGS.sub('', base).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', action='append', required=True,
                    help='region tag to remove, e.g. "(J)"; repeatable')
    ap.add_argument('--system', action='append',
                    help='limit to these systems (default: all)')
    ap.add_argument('--apply', action='store_true', help='actually delete')
    args = ap.parse_args()

    systems = args.system or [d.rstrip('/') for d in box('ls %s' % ROMS)]
    tags = [t.lower() for t in args.tag]
    doomed, kept_art = [], []

    for system in systems:
        names = box('ls "%s/%s" 2>/dev/null' % (ROMS, system))
        if not names:
            continue
        hits = [n for n in names if any(t in n.lower() for t in tags)]
        survivors = {title_of(n) for n in names if n not in hits}
        for name in hits:
            title = title_of(name)
            shared = title in survivors
            doomed.append((system, name, title, shared))
            if shared:
                kept_art.append('%s/%s' % (system, title))

    if not doomed:
        print('nothing matches %s' % ', '.join(args.tag))
        return

    for system, name, title, shared in doomed:
        print('  %-10s %-58s %s' % (system, name[:58],
                                    'ART SHARED - keeping' if shared else ''))
    print('\n%d rom(s); artwork kept for %d title(s) still present in another region'
          % (len(doomed), len(kept_art)))

    if not args.apply:
        print('\ndry run - pass --apply to delete')
        return

    for system, name, title, shared in doomed:
        box('rm -f "%s/%s/%s"' % (ROMS, system, name.replace('"', '\\"')))
        if not shared:
            for path in ('%s/%s/%s.png' % (ART, system, title),
                         '%s/snaps/%s/%s.png' % (ART, system, title)):
                box('rm -f "%s"' % path.replace('"', '\\"'))
    print('\ndeleted %d rom(s)' % len(doomed))


if __name__ == '__main__':
    main()
