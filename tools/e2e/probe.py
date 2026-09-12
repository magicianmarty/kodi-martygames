#!/usr/bin/env python3
"""Run e2e cases on the box and write a JSON report.

Runs ON the box: the window poll needs to be local, an ssh round trip per
sample is slower than the thing being measured.

    probe.py cases.json report.json
"""

import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

RPC = "http://localhost:8080/jsonrpc"
AUTH = "kodi:tkU0nimvSHJV"
LOG = "/storage/.kodi/temp/kodi.log"
SAVES = "/storage/.kodi/saves"
CRASHDIR = "/storage/.kodi/temp"

LAUNCH_TIMEOUT = 45
OBSERVE = 40
TEARDOWN_TIMEOUT = 60
POLL = 0.5

# A game is "playing" in this window; anything else on top is a popup.
PLAYING_WINDOWS = {"Fullscreen game", "Fullscreen video", "Visualisation"}


def rpc(method, params=None, timeout=15):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params or {}}).encode()
    req = urllib.request.Request(RPC, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Basic " + __import__("base64").b64encode(
            AUTH.encode()).decode()})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as exc:
        return {"error": str(exc)}


def players():
    return rpc("Player.GetActivePlayers").get("result") or []


def window():
    r = rpc("GUI.GetProperties", {"properties": ["currentwindow"]})
    try:
        return r["result"]["currentwindow"]["label"]
    except Exception:
        return "?"


def uptime():
    return float(open("/proc/uptime").read().split()[0])


def crashlogs():
    return set(glob.glob(os.path.join(CRASHDIR, "kodi_crashlog_*.log")))


def logsize():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def logtail(since):
    """Everything appended to kodi.log since byte offset `since`."""
    try:
        with open(LOG, "rb") as fh:
            fh.seek(since)
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def dirsize(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def alsa_stream():
    """(path, hw_ptr, rate) of the running playback stream, if there is one."""
    for status in glob.glob("/proc/asound/card*/pcm*p/sub0/status"):
        try:
            txt = open(status).read()
        except OSError:
            continue
        if "state: RUNNING" not in txt:
            continue
        m = re.search(r"hw_ptr\s*:\s*(\d+)", txt)
        if not m:
            continue
        rate = None
        try:
            hw = open(status.replace("/status", "/hw_params")).read()
            rm = re.search(r"^rate:\s*(\d+)", hw, re.M)
            if rm:
                rate = int(rm.group(1))
        except OSError:
            pass
        return status, int(m.group(1)), rate
    return None, None, None


def cpu_of_threads(pid):
    out = {}
    base = "/proc/%d/task" % pid
    try:
        tids = os.listdir(base)
    except OSError:
        return out
    for tid in tids:
        try:
            raw = open(os.path.join(base, tid, "stat")).read()
            fields = raw[raw.rindex(")") + 2:].split()
            name = raw[raw.index("(") + 1:raw.rindex(")")]
            out[tid] = (int(fields[11]) + int(fields[12]), name)
        except Exception:
            pass
    return out


def kodi_pid():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if "kodi.bin" in open("/proc/%s/cmdline" % pid).read():
                return int(pid)
        except OSError:
            pass
    return None


def stop_everything():
    for pid in (0, 1, 2):
        rpc("Player.Stop", {"playerid": pid}, timeout=8)


def settle_to_home(deadline):
    while time.time() < deadline:
        if not players():
            rpc("GUI.ActivateWindow", {"window": "home"}, timeout=8)
            time.sleep(1)
            return True
        time.sleep(0.5)
    return False


def run_case(case):
    name = case["title"]
    result = {"title": name, "system": case.get("system"),
              "core": case.get("core"), "path": case.get("path"),
              "checks": {}, "notes": []}

    if players():
        result["checks"]["box_idle_before"] = False
        result["notes"].append("something was already playing; skipped")
        return result
    result["checks"]["box_idle_before"] = True

    pid = kodi_pid()
    base = {
        "uptime": uptime(),
        "crashlogs": crashlogs(),
        "logpos": logsize(),
        "saves": dirsize(SAVES),
        "cpu": cpu_of_threads(pid) if pid else {},
        "t": time.time(),
    }

    params = {"action": "play", "path": case["path"], "core": case["core"]}
    if case.get("action") == "stream":
        params = {"action": "stream", "app": case["app"]}
    rpc("Addons.ExecuteAddon",
        {"addonid": "plugin.program.martygames", "params": params}, timeout=25)

    t0 = time.time()
    launched = False
    while time.time() - t0 < LAUNCH_TIMEOUT:
        if players():
            launched = True
            break
        time.sleep(POLL)
    result["checks"]["launched"] = launched
    result["launch_seconds"] = round(time.time() - t0, 1)
    if not launched:
        result["notes"].append("no active player within %ds" % LAUNCH_TIMEOUT)
        stop_everything()
        settle_to_home(time.time() + TEARDOWN_TIMEOUT)
        result["log"] = logtail(base["logpos"])[-6000:]
        return result

    windows, popups, gone = [], 0, 0
    prev = None
    a_path = a_ptr0 = a_t0 = a_rate = None
    obs_end = time.time() + OBSERVE
    while time.time() < obs_end:
        w = window()
        if w != prev:
            windows.append(w)
            if prev in PLAYING_WINDOWS and w not in PLAYING_WINDOWS:
                popups += 1
            prev = w
        if not players():
            gone += 1
        if a_ptr0 is None:
            a_path, p, a_rate = alsa_stream()
            if p is not None:
                a_ptr0, a_t0 = p, time.time()
        time.sleep(POLL)

    # hw_ptr runs at the sink's rate, so this measures whether audio kept
    # flowing - not how fast the emulator ran. A restarted substream resets the
    # pointer, which would read as a slowdown that never happened.
    path1, a_ptr1, _ = alsa_stream()
    a_t1 = time.time()
    if (a_ptr0 is not None and a_ptr1 is not None and path1 == a_path
            and a_ptr1 > a_ptr0):
        rate = round((a_ptr1 - a_ptr0) / (a_t1 - a_t0))
        result["audio_frames_per_sec"] = rate
        result["audio_sink_rate"] = a_rate
        if a_rate:
            result["checks"]["audio_kept_up"] = rate > a_rate * 0.95
    else:
        result["audio_frames_per_sec"] = None
        result["notes"].append("audio stream restarted or absent mid-run")

    result["windows_seen"] = windows
    result["checks"]["stayed_in_game"] = (gone == 0)
    result["checks"]["no_popups"] = (popups == 0)
    result["popups"] = popups

    cpu_now = cpu_of_threads(pid) if pid else {}
    hz = os.sysconf("SC_CLK_TCK")
    elapsed = time.time() - base["t"]
    busiest = []
    for tid, (ticks, nm) in cpu_now.items():
        if tid in base["cpu"]:
            pct = (ticks - base["cpu"][tid][0]) / hz / elapsed * 100
            if pct > 5:
                busiest.append([round(pct, 1), nm])
    busiest.sort(reverse=True)
    result["busiest_threads"] = busiest[:5]
    # A pegged GameLoop is the only speed signal a libretro core gives us;
    # nothing logs emulated fps.
    result["checks"]["not_cpu_saturated"] = not any(
        p >= 95 and n.startswith("GameLoop") for p, n in busiest)

    t_stop = time.time()
    stop_everything()
    clean = settle_to_home(t_stop + TEARDOWN_TIMEOUT)
    result["teardown_seconds"] = round(time.time() - t_stop, 1)
    result["checks"]["clean_exit"] = clean

    time.sleep(2)
    tail = logtail(base["logpos"])
    result["checks"]["no_crash"] = (crashlogs() == base["crashlogs"])
    result["checks"]["no_reboot"] = (uptime() > base["uptime"])
    result["checks"]["core_loaded"] = (
        "Loaded DLL for %s" % case["core"] in tail) if case.get("core") else True

    reconfigures = tail.count("Configuring format")
    result["reconfigures"] = reconfigures
    # yabasanshiro managed 5412 in 107s by reopening the stream every frame
    result["checks"]["no_reconfigure_storm"] = reconfigures < 30

    errors = len(re.findall(r"\berror\s+<", tail))
    result["errors"] = errors
    result["checks"]["no_error_spam"] = errors < 25

    result["saves_growth_mb"] = round((dirsize(SAVES) - base["saves"]) / 1e6, 1)
    result["checks"]["no_savestate_explosion"] = result["saves_growth_mb"] < 400

    result["error_lines"] = [l[:200] for l in tail.splitlines()
                             if re.search(r"\berror\s+<", l)][:12]
    result["failed"] = [k for k, v in result["checks"].items() if not v]
    return result


def main():
    cases = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    results = []
    for i, case in enumerate(cases, 1):
        print("[%d/%d] %s (%s)" % (i, len(cases), case["title"],
                                   case.get("system")), flush=True)
        try:
            r = run_case(case)
        except Exception as exc:
            r = {"title": case["title"], "system": case.get("system"),
                 "checks": {"harness_ok": False}, "failed": ["harness_ok"],
                 "notes": ["probe raised: %r" % (exc,)]}
        results.append(r)
        print("     %s" % ("PASS" if not r.get("failed") else
                           "FAIL " + ",".join(r["failed"])), flush=True)
        json.dump(results, open(out, "w"), indent=1)
        # A reboot or a dead Kodi invalidates everything after it, and
        # repeated restarts trip CoreELEC's safe mode at 5 in 900s.
        if "no_reboot" in r.get("failed", []) or not rpc("JSONRPC.Ping").get("result"):
            print("!! box unhealthy, stopping early", flush=True)
            break
        time.sleep(3)
    json.dump(results, open(out, "w"), indent=1)
    print("wrote %s (%d cases)" % (out, len(results)))


main()
