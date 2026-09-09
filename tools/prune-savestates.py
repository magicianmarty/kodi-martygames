#!/usr/bin/env python3
"""Delete old autosaves, keeping the newest few per game. Manual saves never go.

Kodi opens a new autosave slot every time you launch a game and never removes
the old ones - there is no pruning, cap or rotation anywhere in its savestate
code. God of War serialises 128 MB, so twenty sessions had left 2.6 GB behind.

Kodi patch 1050 caps this going forward by naming new autosaves "auto_*", but
savestates written before that keep timestamped names whose type cannot be told
apart from a manual save without opening them. This reads the type out of each
file to sort them safely.

    ./tools/prune-savestates.py            # dry run: show what would go
    ./tools/prune-savestates.py --delete   # actually delete
    ./tools/prune-savestates.py --keep 5   # keep more per game

Run it on the box, or over ssh:  ./tools/box "python3 - < tools/prune-savestates.py"
"""
import argparse
import glob
import os
import struct
import sys

SAVES = "/storage/.kodi/saves"
TYPES = {0: "Unknown", 1: "Auto", 2: "Manual"}


def savestate_type(path):
    """Read the FlatBuffer 'type' field without loading the file.

    savestate.fbs declares `type:SaveType (id: 1)`, so it sits in vtable slot 1
    (offset 4 + 2*1). Two small seeks beat reading 128 MB per file.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) < 8:
                return "short"
            root = struct.unpack_from("<I", head, 0)[0]
            size = os.path.getsize(path)
            if root + 4 > size:
                return "badroot"
            f.seek(root)
            vtable = root - struct.unpack("<i", f.read(4))[0]
            if vtable < 0 or vtable + 8 > size:
                return "badvtable"
            f.seek(vtable)
            vtable_size = struct.unpack("<HH", f.read(4))[0]
            if vtable_size < 8:
                return "novtable"          # field absent, so it defaults
            f.seek(vtable + 6)
            offset = struct.unpack("<H", f.read(2))[0]
            if offset == 0:
                return "default"
            f.seek(root + offset)
            return TYPES.get(f.read(1)[0], "?")
    except Exception as exc:  # noqa: BLE001 - a bad file must not stop the sweep
        return "error:%s" % exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=3)
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--saves", default=SAVES)
    args = ap.parse_args()

    if not os.path.isdir(args.saves):
        sys.exit("no savestate folder at %s" % args.saves)

    doomed, kept_bytes, freed, preserved = [], 0, 0, []
    for game in sorted(os.listdir(args.saves)):
        folder = os.path.join(args.saves, game)
        if not os.path.isdir(folder):
            continue
        autos = []
        for path in glob.glob(os.path.join(folder, "*.sav")):
            kind = savestate_type(path)
            if kind == "Auto":
                autos.append(path)
            else:
                # Manual, or a type we could not read: keep it either way
                preserved.append((kind, path))
                kept_bytes += os.path.getsize(path)
        autos.sort(key=os.path.getmtime, reverse=True)
        for path in autos[:args.keep]:
            kept_bytes += os.path.getsize(path)
        for path in autos[args.keep:]:
            freed += os.path.getsize(path)
            doomed.append(path)

    print("keeping the newest %d autosaves per game; never touching manual saves" % args.keep)
    print("preserved outright : %d files" % len(preserved))
    for kind, path in preserved:
        if kind != "Manual":
            print("   %-10s %s  (unreadable type, kept)" % (kind, path[len(args.saves) + 1:]))
    print("would delete       : %d files, %.2f GB" % (len(doomed), freed / 1e9))
    print("would keep         : %.2f GB" % (kept_bytes / 1e9))

    if not args.delete:
        print("\ndry run; pass --delete to apply")
        return

    n = thumbs = 0
    for path in doomed:
        if not os.path.isfile(path):
            continue
        os.remove(path)
        n += 1
        thumb = path[:-4] + ".jpg"
        if os.path.isfile(thumb):
            os.remove(thumb)
            thumbs += 1
    print("\ndeleted %d savestates and %d thumbnails" % (n, thumbs))


main()
