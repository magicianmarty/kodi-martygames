#!/usr/bin/env python3
"""Render an e2e report.json as markdown."""

import json
import sys

CHECKS = ["launched", "core_loaded", "stayed_in_game", "no_popups",
          "no_reconfigure_storm", "no_error_spam", "audio_kept_up",
          "not_cpu_saturated", "no_crash", "no_reboot", "clean_exit",
          "no_savestate_explosion"]
SHORT = {"launched": "launch", "core_loaded": "core", "stayed_in_game": "stays",
         "no_popups": "popup", "no_reconfigure_storm": "recfg",
         "no_error_spam": "errs", "no_crash": "crash", "no_reboot": "reboot",
         "clean_exit": "exit", "no_savestate_explosion": "saves", "audio_kept_up": "audio",
         "not_cpu_saturated": "cpu"}


def main():
    results = json.load(open(sys.argv[1]))
    passed = [r for r in results if not r.get("failed")]

    print("# e2e sweep\n")
    print("%d cases, %d pass, %d fail\n" % (
        len(results), len(passed), len(results) - len(passed)))

    print("| game | system | " + " | ".join(SHORT[c] for c in CHECKS) + " |")
    print("|---|---|" + "---|" * len(CHECKS))
    for r in results:
        cells = []
        for c in CHECKS:
            v = r.get("checks", {}).get(c)
            cells.append("·" if v is None else ("ok" if v else "**X**"))
        print("| %s | %s | %s |" % (r["title"][:34], r.get("system", "?"),
                                    " | ".join(cells)))

    print("\n## failures\n")
    any_fail = False
    for r in results:
        if not r.get("failed"):
            continue
        any_fail = True
        print("### %s  (%s / %s)" % (r["title"], r.get("system"), r.get("core")))
        print("- failed: %s" % ", ".join(r["failed"]))
        for k in ("launch_seconds", "teardown_seconds", "reconfigures",
                  "errors", "popups", "audio_frames_per_sec",
                  "saves_growth_mb"):
            if r.get(k) not in (None, 0):
                print("- %s: %s" % (k, r[k]))
        if r.get("windows_seen"):
            print("- windows: %s" % " -> ".join(r["windows_seen"][:10]))
        if r.get("busiest_threads"):
            print("- cpu: %s" % ", ".join(
                "%s %s%%" % (n, p) for p, n in r["busiest_threads"]))
        for n in r.get("notes", []):
            print("- note: %s" % n)
        for line in r.get("error_lines", [])[:6]:
            print("      %s" % line)
        print()
    if not any_fail:
        print("none\n")

    print("## timings\n")
    print("| game | launch s | teardown s | audio fps | reconfigs | errors |")
    print("|---|---|---|---|---|---|")
    for r in results:
        print("| %s | %s | %s | %s | %s | %s |" % (
            r["title"][:34], r.get("launch_seconds", "-"),
            r.get("teardown_seconds", "-"), r.get("audio_frames_per_sec", "-"),
            r.get("reconfigures", "-"), r.get("errors", "-")))


main()
