#!/usr/bin/env python3
"""Answer a DOS installer's prompts by reading its screen. Runs in the container.

Scripted keystrokes fired on a timer do not survive contact with real
installers. One Must Fall's opens a welcome dialog, then a menu whose first
item is "About this CD", so a sequence of blind Enters walks into the
documentation viewer, and Enter is not what closes it.

So the screen is read instead: grab the framebuffer, OCR it, choose a key, and
inject it into DOSBox as a real X event. Three things decide the key, in order:

1. Phrases the installer puts on screen itself - "press any key", "press ESC
   when done", a yes/no prompt.
2. Aiming at a menu. OCR gives the text and position of every line; the
   selected line is found by colour, because the highlight is the one button
   whose background differs from the others. Knowing both, the right number of
   Up or Down presses is arithmetic. This is what distinguishes "Install One
   Must Fall: 2097" from the "Install Bonus Games" directly below it.
3. Failing both, a ladder of keys indexed by how many times this exact screen
   has been seen before, so a screen that ignores Enter gets Down next time
   rather than Enter forever.

Success is not judged here. This only has to stop; dos-install.py decides
whether what landed in C: is a game.
"""

import hashlib
import os
import re
import subprocess
import sys
import time
from collections import Counter

from PIL import Image

SHOTS, OUT = sys.argv[1], sys.argv[2]
DEADLINE = time.time() + int(sys.argv[3])
TITLE = (sys.argv[4] if len(sys.argv) > 4 else '').lower()

# Escape is last, and only ever reached on a screen that has ignored everything
# else: on a main menu it does not go back, it quits the installer, and DOSBox
# then runs the exit at the end of autoexec and disappears.
LADDER = ['Return', 'Down', 'Return', 'Down', 'Return', 'Down', 'Return',
          'Down', 'Return', 'y', 'space', 'Escape']

WANT = ('install', 'setup', 'hard disk', 'hard drive', 'continue', 'begin')
AVOID = ('bonus', 'read', 'quit', 'exit', 'about', 'manual', 'document',
         'uninstall', 'cancel', 'help', 'order', 'view', 'previous', 'back',
         'catalog', 'demo', 'other', 'more')
STOP_WORDS = {'the', 'of', 'a', 'and', 'to', 'in', 'for', 'cd', 'original'}

BUTTON_TEXT = {}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def grab(path):
    run(['import', '-window', 'root', path])


def key(name):
    run(['xdotool', 'key', '--clearmodifiers', name])


def tree_size(path):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(path) for f in fs)


def longest_run(seq, want):
    """(start, end) of the longest unbroken stretch of want in seq."""
    best, cur = (0, 0, 0), None
    for i, v in enumerate(list(seq) + [None]):
        if v == want and cur is None:
            cur = i
        elif v != want and cur is not None:
            if i - cur > best[0]:
                best = (i - cur, cur, i)
            cur = None
    return best[1], best[2]


def dialog_box(img):
    """The bounding box of the panel the installer is drawing in, if any.

    Cropping to it before OCR is not cosmetic. One Must Fall animates an "Epic
    MegaGames" wallpaper either side of its dialog, and tesseract reads across
    the whole width, so every menu line comes back as the button text spliced
    into the wallpaper - "epic negaganes is tcu es gaganes epic" is Install.

    The panel is the widest unbroken block of one colour. Black is discounted
    because the wallpaper sits on it and would otherwise win every row, and the
    extent is measured as a run rather than as min/max because the wallpaper
    lettering is drawn in the panel's own colour.
    """
    w, h = img.size
    votes, rows = Counter(), {}
    for y in range(0, h, 3):
        row = Counter(img.getpixel((x, y)) for x in range(0, w, 4))
        row.pop((0, 0, 0), None)
        if not row:
            continue
        col, n = row.most_common(1)[0]
        if n < (w / 4) * 0.25:
            continue
        votes[col] += 1
        rows.setdefault(col, []).append(y)
    if not votes:
        return None

    col = votes.most_common(1)[0][0]
    ys = rows[col]
    runs, cur = [], [ys[0]]
    for a, b in zip(ys, ys[1:]):
        (cur.append(b) if b - a <= 36 else (runs.append(cur), cur := [b]))
    runs.append(cur)
    band = max(runs, key=len)

    mid = band[len(band) // 2]
    x0, x1 = longest_run([img.getpixel((x, mid)) for x in range(w)], col)
    if x1 - x0 < 200 or band[-1] - band[0] < 60:
        return None
    return (x0, band[0], x1, band[-1])


def screen(path):
    """(image, lines) for the installer's panel, cropped away from the rest."""
    img = Image.open(path).convert('RGB')
    box = dialog_box(img)
    if box:
        img = img.crop((max(0, box[0] - 4), max(0, box[1] - 4),
                        box[2] + 5, box[3] + 5))
        img.save(path + '.crop.png')
        return img, read_lines(path + '.crop.png')
    return img, read_lines(path)


def _ocr(path):
    """[(text, top, bottom, left, right)] for one image, one line per entry."""
    r = run(['tesseract', path, 'stdout', '--psm', '6', 'tsv'])
    groups = {}
    for c in (l.split('\t') for l in r.stdout.splitlines()[1:]):
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            left, top, w, h = (int(c[6]), int(c[7]), int(c[8]), int(c[9]))
        except ValueError:
            continue
        groups.setdefault((c[2], c[3], c[4]), []).append(
            (left, top, left + w, top + h, c[11]))
    return [(' '.join(w[4] for w in ws).lower(),
             min(w[1] for w in ws), max(w[3] for w in ws),
             min(w[0] for w in ws), max(w[2] for w in ws))
            for ws in groups.values()]


def read_lines(path):
    """OCR the screen, reading both polarities.

    A DOS installer draws its dialog light-on-dark and its buttons dark-on-
    light in the same frame. tesseract binarises for one of the two and loses
    the other completely - on One Must Fall's main menu the four buttons, which
    are the only lines worth reading, come back empty. Both passes are run and
    merged, keeping whichever read more characters for a given line.
    """
    lines = _ocr(path)
    inv = path + '.inv.png'
    if run(['magick', path, '-negate', inv]).returncode != 0:
        run(['convert', path, '-negate', inv])
    if os.path.exists(inv):
        lines += _ocr(inv)

    lines.sort(key=lambda l: (l[1], -len(l[0])))
    kept = []
    for line in lines:
        mid = (line[1] + line[2]) / 2
        if any(k[1] <= mid <= k[2] for k in kept):
            continue
        kept.append(line)
    kept.sort(key=lambda l: l[1])
    return kept


def text_quality(t):
    """How much this OCR reading looks like words rather than noise.

    Length alone picks the wrong reading: a misbinarised button comes back as
    "me 8=-sti<"-i-i-s-sts-sscccc'rr@keh", which is longer than "read this!"
    and would win.
    """
    good = sum(c.isalnum() or c.isspace() for c in t)
    return good - 2 * (len(t) - good)


def ocr_band(img, y0, y1, tag):
    """Read one menu button, trying each way of binarising it."""
    crop = img.crop((0, max(0, y0 - 2), img.size[0], y1 + 3))
    if crop.size[1] < 6:
        return ''
    path = '/tmp/band%s.png' % tag
    crop.resize((crop.size[0] * 2, crop.size[1] * 2)).save(path)
    best = ''
    for i, args in enumerate(([], ['-negate'],
                              ['-colorspace', 'Gray', '-normalize'],
                              ['-colorspace', 'Gray', '-normalize', '-negate'])):
        use = path
        if args:
            use = '/tmp/band%s-%d.png' % (tag, i)
            if run(['magick', path] + args + [use]).returncode != 0:
                run(['convert', path] + args + [use])
            if not os.path.exists(use):
                continue
        r = run(['tesseract', use, 'stdout', '--psm', '7'])
        got = ' '.join(r.stdout.lower().split())
        if text_quality(got) > text_quality(best):
            best = got
    return best


def find_buttons(img):
    """Menu buttons located by colour, then read one at a time.

    Finding them in the full-screen OCR does not work: a button drawn dark-on-
    light inside a light-on-dark dialog is dropped by tesseract, and the
    highlighted one - which is the single most important line on the screen,
    because it is where the cursor is - has a third contrast again and is
    dropped even from the inverted pass. Their position is unambiguous in
    colour though, so they are found there and each read in isolation.

    Returns [(text, colour)] top to bottom.
    """
    w, h = img.size
    page = Counter(img.getpixel((x, y))
                   for y in range(0, h, 2) for x in range(0, w, 4)
                   ).most_common(1)[0][0]
    bands, cur = [], None
    for y in range(h):
        row = Counter(img.getpixel((x, y)) for x in range(0, w, 3))
        col, n = row.most_common(1)[0]
        solid = col != page and n > (w / 3) * 0.55
        if solid and cur and cur[2] == col:
            cur[1] = y
        elif solid:
            if cur:
                bands.append(cur)
            cur = [y, y, col]
        elif cur:
            bands.append(cur)
            cur = None
    if cur:
        bands.append(cur)

    bands = [b for b in bands if b[1] - b[0] >= 8]
    if len(bands) < 2:
        return []

    # The highlighted button is the one that cannot be read - white on the
    # highlight colour is a third contrast again - and it is also the one whose
    # text decides whether to press Enter or keep moving. It was readable in
    # the frame before the cursor arrived on it, so readings are kept per
    # position and the best one so far wins. Menus are keyed on their button
    # geometry, which is what distinguishes one screen's menu from another's.
    key = tuple(b[0] for b in bands)
    cache = BUTTON_TEXT.setdefault(key, {})
    out = []
    for i, b in enumerate(bands):
        got = ocr_band(img, b[0], b[1], i)
        if i not in cache or text_quality(got) > text_quality(cache[i]):
            cache[i] = got
        out.append((cache[i], b[2]))
    return out


def menu(img):
    """(buttons, index of the selected one), or (None, None) if not a menu.

    The selected button is the one whose colour no other button shares.
    """
    buttons = find_buttons(img)
    if len(buttons) < 2:
        return None, None
    tally = Counter(c for _, c in buttons)
    odd = [c for c, n in tally.items() if n == 1]
    if len(tally) != 2 or len(odd) != 1:
        return None, None
    return buttons, [i for i, (_, c) in enumerate(buttons) if c == odd[0]][0]


def score(text):
    """How much this menu line looks like the option that installs the game."""
    if not any(w in text for w in WANT):
        return -99
    s = 10
    if any(w in text for w in AVOID):
        s -= 12
    words = {w for w in re.findall(r'[a-z0-9]+', TITLE) if w not in STOP_WORDS
             and len(w) > 2}
    s += 3 * sum(1 for w in words if w in text)
    return s


def aim(img, log):
    """Key that moves toward, or activates, the install option."""
    buttons, sel = menu(img)
    if buttons is None:
        return None
    log.append('menu: ' + ' | '.join(
        '%s%s(%d)' % ('*' if i == sel else '', b[0][:22], score(b[0]))
        for i, b in enumerate(buttons)))
    scored = [(score(b[0]), i) for i, b in enumerate(buttons)]
    best, idx = max(scored)
    if best < 0:
        return None
    if idx == sel:
        return 'Return'
    return 'Down' if idx > sel else 'Up'


# ESC leaves a document viewer, but on a prompt it aborts the install: the
# screen asking "Drive to install to: C:" also says "press ESC to abort", so
# anything looser than this walks out of the installer one step from finishing.
ESC_MEANS_DONE = re.compile(
    r'esc\w*\s+(key\s+)?(when|to)\s+(done|finish|exit|return|continue|resume)')
ESC_MEANS_QUIT = ('abort', 'cancel', 'quit', 'without installing')


def phrase(text):
    if ESC_MEANS_DONE.search(text) and not any(w in text for w in ESC_MEANS_QUIT):
        return 'Escape'
    if 'press any key' in text:
        return 'space'
    if '(y/n)' in text or ' y/n' in text:
        return 'y'
    return None


def main():
    shot = os.path.join(SHOTS, 'cur.png')
    # Screens are remembered by content, not just compared with the last one.
    # An installer that loops menu -> submenu -> menu never repeats two frames
    # in a row, so "has the screen stopped changing" never fires and the same
    # wrong key gets pressed forever. Counting visits per screen escalates on
    # the cycle instead of on the freeze.
    seen = {}
    last, step, quiet, blank = None, 0, 0, 0
    size = tree_size(OUT)

    while time.time() < DEADLINE:
        time.sleep(1.2)
        step += 1
        grab(shot)
        img, lines = screen(shot)
        text = ' '.join(l[0] for l in lines)

        if len(text) < 8:
            # Nothing on screen: the installer quit and took DOSBox with it.
            blank += 1
            if blank > 2:
                print('screen went empty, installer is gone')
                break
            continue
        blank = 0

        digest = hashlib.sha1(text.encode()).hexdigest()
        visits = seen.get(digest, 0)
        seen[digest] = visits + 1
        if digest != last:
            run(['cp', shot, os.path.join(SHOTS, 'shot-%03d.png' % step)])
        last = digest

        if visits > len(LADDER):
            print('exhausted every key on the same screen, giving up')
            break

        now = tree_size(OUT)
        if now != size:
            size, quiet = now, 0
        elif size:
            # Files stopped arriving. The installer is on its closing screen,
            # so keep answering it, but do not wait out the whole deadline.
            quiet += 1
            if quiet > 12:
                print('install quiet for ~15s at %d bytes, stopping' % size)
                break

        note = []
        k = phrase(text)
        if k is None and visits < 3:
            k = aim(img, note)
        if k is None:
            k = LADDER[min(visits, len(LADDER) - 1)]
        key(k)
        with open(os.path.join(SHOTS, 'decisions.log'), 'a') as fh:
            fh.write('%03d v%d key=%-7s %s | %s\n'
                     % (step, visits, k, '; '.join(note), text[:110]))

    grab(os.path.join(SHOTS, 'shot-999-final.png'))


if __name__ == '__main__':
    main()
