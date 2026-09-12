#!/usr/bin/env python3
"""Choose e2e cases from the library the plugin actually scanned.

Reads library.json off the box so a case launches exactly what a tile would,
rather than a path this script guessed at.

    pick-cases.py --per-system 1 > cases.json
    pick-cases.py --system amiga --per-system 5 > cases.json
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOX = os.path.join(HERE, "..", "box")
LIBRARY = "/storage/.kodi/userdata/addon_data/plugin.program.martygames/library.json"


def fetch_library():
    out = subprocess.run(
        [BOX, "python3 -c \"import sys;sys.stdout.write(open('%s').read())\"" % LIBRARY],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out[out.index("{"):])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-system", type=int, default=1)
    ap.add_argument("--system", action="append", default=[])
    ap.add_argument("--pc", action="store_true", help="include streamed PC games")
    args = ap.parse_args()

    lib = fetch_library()
    by_system = {}
    for game in lib.get("games", []):
        by_system.setdefault(game["system"], []).append(game)

    wanted = args.system or sorted(by_system)
    cases = []
    for system in wanted:
        games = sorted(by_system.get(system, []), key=lambda g: g["title"])
        if not games:
            print("no games for %s" % system, file=sys.stderr)
            continue
        # Spread the picks across the alphabet instead of taking the first few,
        # which on most systems are numeric-titled oddities.
        step = max(1, len(games) // (args.per_system + 1))
        seen = set()
        for i in range(args.per_system):
            g = games[min((i + 1) * step, len(games) - 1)]
            if g["path"] in seen:
                continue
            seen.add(g["path"])
            cases.append({"title": g["title"], "path": g["path"],
                          "core": g["core"], "system": system})

    if args.pc:
        pc = json.load(open(os.path.join(
            HERE, "..", "..", "plugin.program.martygames", "resources", "pc.json")))
        for g in pc.get("games", []):
            cases.append({"title": g["title"], "app": g["app"],
                          "system": "pc", "action": "stream", "core": None})

    json.dump(cases, sys.stdout, indent=1)


main()
