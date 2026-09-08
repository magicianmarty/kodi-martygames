"""Reduce a title to something comparable across naming conventions.

Shared by the artwork and metadata fetchers: both match our filenames against a
third-party index whose names follow different conventions, and they must agree
on what counts as the same game or their overrides files drift apart.
"""

import os
import re

_ARTICLES = re.compile(r'^(the|a|an)\s+', re.I)
_TAGS = re.compile(r'[\(\[][^\)\]]*[\)\]]')


# Our filenames spell sequels with digits, the thumbnail repos with roman
# numerals - "X Men Legends 2" against "X-Men Legends II". Folding one to the
# other is what lets those meet at all; without it difflib sees two different
# words and scores the pair below any usable cutoff.
# Single letters are left alone deliberately: "x" is a numeral in "Final
# Fantasy X" and a word in "Mega Man X", and folding it would quietly turn the
# latter into "Mega Man 10" - a real game, and the wrong one.
_ROMAN = {'ii': '2', 'iii': '3', 'iv': '4', 'vi': '6', 'vii': '7',
          'viii': '8', 'ix': '9', 'xi': '11', 'xii': '12', 'xiii': '13'}


def _fold_numerals(s):
    return ' '.join(_ROMAN.get(w, w) for w in s.split())


def normalise(name):
    # splitext() splits at the last dot whatever it is, so it silently cut
    # "Marvel vs. Capcom" down to "marvel vs" - and "Marvel vs. Capcom 2" to
    # the same string, so neither could ever match. Same for Mr./Ms./Dr./St.
    # and any title with initials. Only drop something shaped like a real
    # extension.
    root, ext = os.path.splitext(name)
    s = root if re.fullmatch(r"\.[A-Za-z0-9]{1,5}", ext) else name
    s = _TAGS.sub(' ', s)                    # (World), [!], (1992)(Ocean)
    # libretro-thumbnails writes '&' as '_' for filesystem safety
    s = s.replace('&', ' and ').replace('_', ' and ')
    s = re.sub(r'[^a-z0-9 ]', ' ', s.lower())
    s = _ARTICLES.sub('', s.strip())
    # trailing ", The" / ", A" as used by TOSEC and No-Intro alike
    s = re.sub(r'\s+(the|a|an)$', '', s)
    return _fold_numerals(re.sub(r'\s+', ' ', s).strip())
