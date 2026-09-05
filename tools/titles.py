"""Reduce a title to something comparable across naming conventions.

Shared by the artwork and metadata fetchers: both match our filenames against a
third-party index whose names follow different conventions, and they must agree
on what counts as the same game or their overrides files drift apart.
"""

import os
import re

_ARTICLES = re.compile(r'^(the|a|an)\s+', re.I)
_TAGS = re.compile(r'[\(\[][^\)\]]*[\)\]]')


def normalise(name):
    s = os.path.splitext(name)[0]
    s = _TAGS.sub(' ', s)                    # (World), [!], (1992)(Ocean)
    # libretro-thumbnails writes '&' as '_' for filesystem safety
    s = s.replace('&', ' and ').replace('_', ' and ')
    s = re.sub(r'[^a-z0-9 ]', ' ', s.lower())
    s = _ARTICLES.sub('', s.strip())
    # trailing ", The" / ", A" as used by TOSEC and No-Intro alike
    s = re.sub(r'\s+(the|a|an)$', '', s)
    return re.sub(r'\s+', ' ', s).strip()
