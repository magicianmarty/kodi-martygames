"""Generate keyboard/joystick/mouse buttonmaps for every controller profile.

Kodi does not translate between controller profiles: each emulated system uses
its own feature names and needs its own <controller> section in a device's
buttonmap. Configuring one by hand in the GUI covers one profile, so a pad that
works on Mega Drive does nothing on Saturn until you map it again.

    ./tools/gen-buttonmaps.py --harvest     # pull profiles + current maps off the box
    ./tools/gen-buttonmaps.py               # regenerate into work/

Outputs go to work/out-{Keyboard,Mouse,Xbox}.xml and are installed with Kodi
STOPPED - it caches buttonmaps in memory and rewrites them on exit:

    systemctl stop kodi
    ... copy application/*.xml and udev/*.xml into
        /storage/.kodi/userdata/addon_data/peripheral.joystick/resources/buttonmaps/xml/ ...
    systemctl start kodi

Note the keyboard sections for gamepad-shaped profiles are inert on Kodi 22:
CAgentKeyboard::ControllerID() always returns game.controller.keyboard and
CDefaultButtonMap::Load() refuses every other profile for a keyboard device, so
a keyboard can only fill a keyboard port. They are generated anyway because
they are the data a patch lifting that limit would need.
"""
import json, os, re, subprocess, sys
from collections import OrderedDict

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "buttonmaps")
HERE = os.path.abspath(HERE)
BOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "box")

HARVEST = r"""
import os, re, glob, json
dirs = ["/usr/share/kodi/addons", "/storage/.kodi/addons"]
prof = {}
for d in dirs:
    for p in glob.glob(os.path.join(d, "game.controller.*")):
        lay = os.path.join(p, "resources", "layout.xml")
        if not os.path.isfile(lay):
            continue
        s = open(lay, errors="replace").read()
        prof[os.path.basename(p)] = [
            [m.group(1), m.group(2)] for m in re.finditer(
                r'<(button|dpad|analogstick|trigger|throttle|wheel|accelerometer|motor|key|relpointer|abspointer|scalar)[^>]*name="([^"]+)"', s)]
cores = {}
for d in dirs:
    for p in glob.glob(os.path.join(d, "game.libretro.*")):
        ax = os.path.join(p, "addon.xml")
        if os.path.isfile(ax):
            cores[os.path.basename(p)] = sorted(set(re.findall(
                r'import addon="(game\.controller\.[^"]+)"', open(ax, errors="replace").read())))
print(json.dumps({"profiles": prof, "cores": cores}))
"""

REFS = {
    "shipped-Keyboard.xml":
        "/usr/share/kodi/addons/peripheral.joystick/resources/buttonmaps/xml/application/Keyboard.xml",
    "user-Xbox.xml":
        "/storage/.kodi/userdata/addon_data/peripheral.joystick/resources/buttonmaps/xml/udev/"
        "Xbox_Wireless_Controller_v045E_p0B20_16b_8a.xml",
}


def harvest():
    os.makedirs(HERE, exist_ok=True)
    out = subprocess.run([BOX, "python3 - <<'PY'\n" + HARVEST + "\nPY"],
                         capture_output=True, text=True, check=True).stdout
    open(os.path.join(HERE, "inputmap.json"), "w").write(out[out.index("{"):].strip() + "\n")
    for name, path in REFS.items():
        r = subprocess.run(
            [BOX, "python3 -c \"import sys;sys.stdout.write(open('%s').read())\"" % path],
            capture_output=True, text=True, check=True)
        open(os.path.join(HERE, name), "w").write(r.stdout)
    print("harvested into", HERE)


if "--harvest" in sys.argv:
    harvest()

inv = json.load(open(os.path.join(HERE, "inputmap.json")))
PROFILES = inv["profiles"]
CORES = inv["cores"]

# ---------------------------------------------------------------- keyboard ---
# Arrows drive the d-pad, WASD the left stick, IJKL the right stick, and the
# action buttons run along the bottom row from Z. Anything without a preference
# takes the next free key, so no two features of one profile share one.
PREFERRED = {
    "up": "up", "down": "down", "left": "left", "right": "right",
    "a": "z", "b": "x", "x": "c", "y": "v",
    "cross": "z", "circle": "x", "square": "c", "triangle": "v",
    "i": "z", "ii": "x", "iii": "c", "iv": "v", "v": "b", "vi": "n",
    "red": "z", "blue": "x", "green": "c", "yellow": "v",
    "button1": "z", "button2": "x", "button3": "c", "button4": "v", "button5": "b",
    "fire": "z", "fire1": "z", "fire2": "x", "trigger": "z", "action": "z",
    "c": "c", "z": "b",
    "start": "enter", "run": "enter", "play": "enter", "return": "enter",
    "select": "rightshift", "back": "rightshift", "pause": "p",
    "mode": "tab", "guide": "tab", "analog": "tab", "menu": "tab",
    "leftbumper": "q", "rightbumper": "e", "l": "q", "r": "e",
    "lefttrigger": "1", "righttrigger": "3", "l2": "1", "r2": "3",
    "l3": "leftctrl", "r3": "leftalt",
    "leftthumb": "leftctrl", "rightthumb": "leftalt",
    "reset": "backspace", "stop": "backspace",
    "rewind": "q", "forward": "e",
    "option": "1", "option1": "1", "option2": "3",
    "space": "space", "escape": "escape", "help": "h", "turbo": "t",
    "color": "c", "bw": "b",
    "cup": "i", "cdown": "k", "cleft": "j", "cright": "l",
    "xup": "up", "xdown": "down", "xleft": "left", "xright": "right",
    "yup": "i", "ydown": "k", "yleft": "j", "yright": "l",
    "star": "kpmultiply", "pound": "kpdivide",
    "offscreen": "o",
    "mode1": "tab", "mode2": "leftbracket",
    "vkbtoggle": "f11", "togglevkbd": "f11", "mousetoggle": "f12",
    "leftdifficulty": "leftbracket", "rightdifficulty": "rightbracket",
    "leftdifficultya": "leftbracket", "leftdifficultyb": "leftbracket",
    "rightdifficultya": "rightbracket", "rightdifficultyb": "rightbracket",
}
for n in range(10):
    PREFERRED["num%d" % n] = "kp%d" % n

STICK_KEYS = {
    "leftstick":   {"up": "w", "down": "s", "left": "a", "right": "d"},
    "analogstick": {"up": "w", "down": "s", "left": "a", "right": "d"},
    "rightstick":  {"up": "i", "down": "k", "left": "j", "right": "l"},
}

FALLBACK = ["z", "x", "c", "v", "b", "n", "m", "a", "s", "d", "f", "g", "h",
            "j", "k", "l", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
            "comma", "period", "slash", "semicolon", "quote",
            "leftbracket", "rightbracket", "backslash", "minus", "equals"]


def valid_keys():
    """The key names a keyboard can actually emit, from the keyboard profile."""
    return {n for t, n in PROFILES.get("game.controller.keyboard", []) if t == "key"}


def gen_keyboard(cid, feats, keys_ok):
    """(list of (name, key), list of (stickname, {dir: key}), list of unmapped)"""
    used, out, sticks, unmapped = set(), [], [], []
    # Deterministic order, and give preferred features first claim on their key
    ordered = sorted(feats, key=lambda f: (f[1] not in PREFERRED, f[1]))
    for ftype, name in ordered:
        if ftype == "analogstick":
            want = STICK_KEYS.get(name)
            if want is None:
                unmapped.append(name)
                continue
            got = {}
            for d, k in want.items():
                if k in used or k not in keys_ok:
                    continue
                used.add(k)
                got[d] = k
            if len(got) == 4:
                sticks.append((name, got))
            else:
                unmapped.append(name)
            continue
        if ftype in ("motor", "relpointer", "key"):
            continue  # rumble/pointer are not keyboard things; keys handled verbatim
        if ftype != "button":
            unmapped.append(name)
            continue
        k = PREFERRED.get(name)
        if k is None or k in used or k not in keys_ok:
            k = next((c for c in FALLBACK if c not in used and c in keys_ok), None)
        if k is None:
            unmapped.append(name)
            continue
        used.add(k)
        out.append((name, k))
    return sorted(out), sticks, unmapped


# ------------------------------------------------------------------ joystick -
def parse_controllers(path):
    s = open(path).read()
    out = OrderedDict()
    for m in re.finditer(r'<controller id="([^"]+)">(.*?)</controller>', s, re.S):
        out[m.group(1)] = m.group(2)
    return out, s


def parse_bindings(body):
    """feature name -> raw attribute string, for simple (non-stick) features."""
    b = {}
    for m in re.finditer(r'<feature name="([^"]+)"\s+([a-z]+="[^"]+")\s*/>', body):
        b[m.group(1)] = m.group(2)
    sticks = {}
    for m in re.finditer(r'<feature name="([^"]+)">(.*?)</feature>', body, re.S):
        sticks[m.group(1)] = m.group(2).strip()
    return b, sticks


# Which default-profile feature stands in for a feature on another profile
EQUIV = {
    "a": "a", "b": "b", "x": "x", "y": "y",
    "cross": "a", "circle": "b", "square": "x", "triangle": "y",
    "i": "a", "ii": "b", "iii": "x", "iv": "y", "v": "leftbumper", "vi": "rightbumper",
    "red": "a", "blue": "b", "green": "x", "yellow": "y",
    "button1": "a", "button2": "b", "button3": "x", "button4": "y", "button5": "leftbumper",
    "fire": "a", "fire1": "a", "fire2": "b", "trigger": "a", "action": "a",
    "c": "leftbumper", "z": "rightbumper",
    "start": "start", "run": "start", "play": "start", "return": "start",
    "select": "back", "back": "back", "pause": "start",
    "mode": "guide", "guide": "guide", "analog": "guide", "menu": "guide",
    "leftbumper": "leftbumper", "rightbumper": "rightbumper",
    "l": "leftbumper", "r": "rightbumper",
    "lefttrigger": "lefttrigger", "righttrigger": "righttrigger",
    "l2": "lefttrigger", "r2": "righttrigger",
    "l3": "leftthumb", "r3": "rightthumb",
    "leftthumb": "leftthumb", "rightthumb": "rightthumb",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "rewind": "leftbumper", "forward": "rightbumper",
    "reset": "back", "stop": "back",
    "option": "lefttrigger", "option1": "lefttrigger", "option2": "righttrigger",
    "cup": "y", "cdown": "a", "cleft": "x", "cright": "b",
    "leftstick": "leftstick", "analogstick": "leftstick", "rightstick": "rightstick",
}


# A second d-pad or a C-button cluster is a direction cluster, so it rides the
# right stick rather than eating four face buttons.
RIGHT_CLUSTER = {"cup": "up", "cdown": "down", "cleft": "left", "cright": "right",
                 "yup": "up", "ydown": "down", "yleft": "left", "yright": "right"}
DPAD_CLUSTER = {"xup": "up", "xdown": "down", "xleft": "left", "xright": "right"}

# Order matters: face buttons first, shoulders next, the awkward ones last
JS_POOL = ["a", "b", "x", "y", "leftbumper", "rightbumper",
           "lefttrigger", "righttrigger", "back", "start", "guide",
           "leftthumb", "rightthumb"]


def stick_dirs(body):
    """{direction: attribute} from an analogstick element body."""
    return {m.group(1): m.group(2)
            for m in re.finditer(r'<(up|down|left|right)\s+([a-z]+="[^"]+")\s*/>', body or "")}


def gen_joystick(cid, feats, dflt_simple, dflt_sticks):
    out, sticks, unmapped = [], [], []
    used = set()
    right = stick_dirs(dflt_sticks.get("rightstick"))
    names = {n for _, n in feats}
    ordered = sorted(feats, key=lambda f: (f[1] not in EQUIV, f[1]))
    for ftype, name in ordered:
        if ftype in ("motor", "relpointer", "key"):
            continue
        if ftype == "analogstick":
            body = dflt_sticks.get(EQUIV.get(name, ""))
            if body and name not in ("rightstick",) or (body and not (names & set(RIGHT_CLUSTER))):
                sticks.append((name, body))
            elif body:
                sticks.append((name, body))
            else:
                unmapped.append(name)
            continue
        # direction clusters
        cl = RIGHT_CLUSTER.get(name)
        if cl and right.get(cl):
            attr = right[cl]
            if attr not in used:
                used.add(attr)
                out.append((name, attr))
                continue
        cl = DPAD_CLUSTER.get(name)
        if cl and dflt_simple.get(cl):
            attr = dflt_simple[cl]
            if attr not in used:
                used.add(attr)
                out.append((name, attr))
                continue
        src = EQUIV.get(name)
        attr = dflt_simple.get(src) if src else None
        if attr is None or attr in used:
            attr = next((dflt_simple[c] for c in JS_POOL
                         if c in dflt_simple and dflt_simple[c] not in used), None)
        if attr is None:
            unmapped.append(name)
            continue
        used.add(attr)
        out.append((name, attr))
    return sorted(out), sticks, unmapped


# --------------------------------------------------------------------- mouse -
MOUSE_BTN = {
    "left": "left", "right": "right", "middle": "middle",
    "button4": "button4", "button5": "button5",
    "wheelup": "wheelup", "wheeldown": "wheeldown",
    "horizwheelleft": "horizwheelleft", "horizwheelright": "horizwheelright",
    # lightguns and console mice: the trigger is the left button
    "trigger": "left", "a": "left", "b": "right", "c": "middle",
    "fire": "left", "start": "middle", "select": "button4",
    "offscreen": "right", "reload": "right", "aux": "button4",
    "pause": "button5",
}
POINTER_BODY = ('<up axis="-y"/>\n                <down axis="+y"/>\n'
                '                <right axis="+x"/>\n                <left axis="-x"/>')


MOUSE_POOL = ["left", "right", "middle", "button4", "button5", "wheelup", "wheeldown"]


def gen_mouse(cid, feats):
    out, pointers, unmapped = [], [], []
    used = set()
    prio = {"trigger": 0, "fire": 0, "left": 0, "pointer": 0}
    for ftype, name in sorted(feats, key=lambda f: (prio.get(f[1], 1), f[1])):
        if ftype == "relpointer":
            pointers.append(name)
            continue
        if ftype in ("motor", "key", "analogstick"):
            continue
        m = MOUSE_BTN.get(name)
        if m is None or m in used:
            m = next((c for c in MOUSE_POOL if c not in used), None)
        if m is None:
            unmapped.append(name)
            continue
        used.add(m)
        out.append((name, m))
    return sorted(out), pointers, unmapped


# ---------------------------------------------------------------- rendering --
def render(device_attrs, sections, config=""):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<buttonmap>",
             "    <device %s>" % device_attrs]
    if config:
        lines.append(config)
    for cid, body in sections:
        lines.append('        <controller id="%s">' % cid)
        lines.append(body.rstrip())
        lines.append("        </controller>")
    lines += ["    </device>", "</buttonmap>", ""]
    return "\n".join(lines)


def main():
    needed = set()
    for core, imports in CORES.items():
        needed.update(imports)
    needed = {c for c in needed if c in PROFILES}
    keys_ok = valid_keys()

    # ---- keyboard
    kb_sections, kb_report = [], []
    shipped, _ = parse_controllers(os.path.join(HERE, "shipped-Keyboard.xml"))
    verbatim = {"game.controller.keyboard", "game.controller.amstrad.keyboard",
                "game.controller.elektronika.bk", "game.controller.msx.keyboard"}
    for cid in sorted(needed | (set(shipped) & verbatim)):
        if cid in shipped and cid in verbatim:
            kb_sections.append((cid, shipped[cid].rstrip("\n")))
            kb_report.append((cid, len(re.findall(r"<feature ", shipped[cid])), 0, "shipped verbatim"))
            continue
        feats = PROFILES.get(cid, [])
        if not feats or cid in verbatim:
            continue
        if any(t == "relpointer" for t, _ in feats):
            continue  # needs a pointer; see Mouse.xml
        simple, sticks, un = gen_keyboard(cid, feats, keys_ok)
        if not simple and not sticks:
            continue
        body = []
        for n, k in simple:
            body.append('            <feature name="%s" key="%s"/>' % (n, k))
        for n, dirs in sticks:
            body.append('            <feature name="%s">' % n)
            for d in ("up", "down", "left", "right"):
                body.append('                <%s key="%s"/>' % (d, dirs[d]))
            body.append("            </feature>")
        kb_sections.append((cid, "\n".join(body)))
        kb_report.append((cid, len(simple) + len(sticks), len(un), ",".join(un)))
    open(os.path.join(HERE, "out-Keyboard.xml"), "w").write(
        render('name="Keyboard" provider="application"', kb_sections,
               "        <configuration/>"))

    # ---- joystick (extend the existing pad map)
    seed = os.environ.get("BUTTONMAP_SEED", os.path.join(HERE, "user-Xbox.xml"))
    xbox, xsrc = parse_controllers(seed)
    dflt_simple, dflt_sticks = parse_bindings(xbox["game.controller.default"])
    js_sections, js_report = [], []
    for cid in sorted(set(xbox) | needed):
        if cid in xbox:
            js_sections.append((cid, xbox[cid].rstrip("\n")))
            js_report.append((cid, len(re.findall(r"<feature ", xbox[cid])), 0, "existing"))
            continue
        feats = PROFILES.get(cid, [])
        if not feats:
            continue
        if any(t == "relpointer" for t, _ in feats):
            continue  # needs a pointer; see Mouse.xml
        simple, sticks, un = gen_joystick(cid, feats, dflt_simple, dflt_sticks)
        if not simple and not sticks:
            continue
        body = []
        for n, attr in simple:
            body.append('            <feature name="%s" %s/>' % (n, attr))
        for n, sbody in sticks:
            body.append('            <feature name="%s">' % n)
            for ln in sbody.splitlines():
                body.append("                " + ln.strip())
            body.append("            </feature>")
        js_sections.append((cid, "\n".join(body)))
        js_report.append((cid, len(simple) + len(sticks), len(un), ",".join(un)))
    dev = re.search(r"<device ([^>]+)>", xsrc).group(1)
    cfg = re.search(r"(\s*<configuration>.*?</configuration>)", xsrc, re.S)
    open(os.path.join(HERE, os.environ.get("BUTTONMAP_OUT", "out-Xbox.xml")), "w").write(
        render(dev, js_sections, cfg.group(1).rstrip("\n") if cfg else ""))

    # ---- mouse
    ms_sections, ms_report = [], []
    for cid in sorted(needed):
        feats = PROFILES.get(cid, [])
        if not any(t == "relpointer" for t, _ in feats):
            continue
        simple, pointers, un = gen_mouse(cid, feats)
        body = []
        for n, m in simple:
            body.append('            <feature name="%s" mouse="%s"/>' % (n, m))
        for n in pointers:
            body.append('            <feature name="%s">' % n)
            body.append("                " + POINTER_BODY)
            body.append("            </feature>")
        ms_sections.append((cid, "\n".join(body)))
        ms_report.append((cid, len(simple) + len(pointers), len(un), ",".join(un)))
    open(os.path.join(HERE, "out-Mouse.xml"), "w").write(
        render('name="Mouse" provider="application"', ms_sections))

    for title, rep in (("KEYBOARD", kb_report), ("JOYSTICK (Xbox)", js_report),
                       ("MOUSE", ms_report)):
        print("=== %s: %d profiles ===" % (title, len(rep)))
        for cid, n, nun, note in rep:
            flag = "  unmapped: " + note if nun else ""
            print("   %-40s %3d features%s" % (cid.replace("game.controller.", ""), n, flag))
        print()


main()
