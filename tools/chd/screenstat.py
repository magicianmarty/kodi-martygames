#!/usr/bin/env python3
"""Report what is on a captured screen: OCR text and how much is drawn."""
import subprocess
import sys

from PIL import Image

path = sys.argv[1]
img = Image.open(path).convert('RGB')
box = img.getbbox()
if box:
    img = img.crop(box)
colours = img.getcolors(maxcolors=200000) or []
text = subprocess.run(['tesseract', path, 'stdout', '--psm', '6'],
                      capture_output=True).stdout.decode(errors='replace')
print('COLOURS %d' % len(colours))
print('TEXT %s' % ' '.join(text.lower().split()))
