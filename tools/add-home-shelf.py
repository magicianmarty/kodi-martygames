#!/usr/bin/env python3
"""Add a games shelf to the home screen.

A shelf is five separate blocks in Home.xml - a fanart backdrop, three hero
labels, a plot textbox and the row itself - all keyed to the row's control id
and all identical apart from that id. Adding one by hand is copy-paste across
600 lines, which is how the first one ended up with the wrong <onup>.

    add-home-shelf.py "Never Played" "?action=shelf&unplayed=1"
    add-home-shelf.py Racing "?action=shelf&genre=Racing" --tile poster

Tiles: poster (box art, default) or wide (screenshots, as Continue uses).
"""

import argparse
import os
import re
import sys

SKIN = os.environ.get('MARTYEDITION',
                      os.path.expanduser('~/dev/skin-martyedition'))
HOME = os.path.join(SKIN, 'xml', 'Home.xml')
PLUGIN = 'plugin://plugin.program.martygames/'


def enclosing_control(text, marker):
    i = text.index(marker)
    start = text.rindex('<control', 0, i)
    depth, j = 0, start
    while True:
        no, nc = text.find('<control', j + 1), text.find('</control>', j + 1)
        if nc == -1:
            raise ValueError('unbalanced <control> around %r' % marker)
        if no != -1 and no < nc:
            depth, j = depth + 1, no
        else:
            if depth == 0:
                return start, nc + len('</control>')
            depth, j = depth - 1, nc


def append_after(text, marker, transform):
    a, b = enclosing_control(text, marker)
    ls = text.rindex('\n', 0, a) + 1
    return text[:b] + '\n' + text[ls:a] + transform(text[a:b]) + text[b:]


def last_row_id(text):
    return max(int(m) for m in re.findall(r'<control type="list" id="(91\d\d)">', text))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('label')
    ap.add_argument('path', help='plugin query, e.g. "?action=shelf&genre=Racing"')
    ap.add_argument('--tile', choices=('poster', 'wide'), default='poster')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = open(HOME, encoding='utf-8').read()
    prev = last_row_id(t)
    new = prev + 1
    if new > 9199:
        raise SystemExit('out of row ids')
    print('adding row %d after %d: %s' % (new, prev, args.label))

    swap = lambda b: b.replace(str(prev), str(new))

    t = append_after(t, '$INFO[Container(%d).ListItem.Art(fanart)]' % prev, swap)
    for prop in ('Label', 'Property(facts_line)', 'Property(people_line)',
                 'Property(plot_line)'):
        t = append_after(t, '$INFO[Container(%d).ListItem.%s]' % (prev, prop), swap)

    # The row lives in a <group> wrapper holding its two title labels.
    a, _ = enclosing_control(t, '<control type="list" id="%d">' % prev)
    gs = t.rindex('<control type="group">', 0, a)
    depth, j = 0, gs
    while True:
        no, nc = t.find('<control', j + 1), t.find('</control>', j + 1)
        if no != -1 and no < nc:
            depth, j = depth + 1, no
        else:
            if depth == 0:
                ge = nc + len('</control>')
                break
            depth, j = depth - 1, nc

    row = swap(t[gs:ge])
    row = re.sub(r'<label>[^<]*</label>',
                 '<label>%s</label>' % args.label, row)
    row = re.sub(r'<content>%s[^<]*</content>' % re.escape(PLUGIN),
                 '<content>%s%s</content>' % (PLUGIN, args.path.replace('&', '&amp;')),
                 row)

    if args.tile == 'poster':
        row = row.replace('<height>254</height>', '<height>338</height>')
        row = row.replace('width="348" height="254"', 'width="244" height="338"')
        row = row.replace('MartyHomeTile', 'MartyPosterTile')
        row = row.replace('center="174,127"', 'center="110,165"')
    else:
        row = row.replace('<height>338</height>', '<height>254</height>')
        row = row.replace('width="244" height="338"', 'width="348" height="254"')
        row = row.replace('MartyPosterTile', 'MartyHomeTile')
        row = row.replace('center="110,165"', 'center="174,127"')

    ls = t.rindex('\n', 0, gs) + 1
    t = t[:ge] + '\n' + t[ls:gs] + row + t[ge:]

    # The previous row now leads down here; this one is last and holds.
    i = t.index('<control type="list" id="%d">' % prev)
    head, tail = t[:i], t[i:]
    tail = tail.replace('<ondown>%d</ondown>' % prev, '<ondown>%d</ondown>' % new, 1)
    t = head + tail
    i = t.index('<control type="list" id="%d">' % new)
    head, tail = t[:i], t[i:]
    tail = re.sub(r'<onup>\d+</onup>', '<onup>%d</onup>' % prev, tail, count=1)
    t = head + tail

    import xml.etree.ElementTree as ET
    ET.fromstring(t)  # refuse to write malformed XML

    if args.dry_run:
        print('dry run: Home.xml unchanged')
        return
    open(HOME, 'w', encoding='utf-8').write(t)
    print('written. Deploy Home.xml and ReloadSkin().')


if __name__ == '__main__':
    main()
