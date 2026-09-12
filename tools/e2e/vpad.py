#!/usr/bin/env python3
"""A uinput gamepad, so tests can actually play rather than just watch.

Kodi 22 cannot drive a game from a keyboard - CAgentKeyboard::ControllerID()
is hardcoded to game.controller.keyboard and CDefaultButtonMap::Load() refuses
every other profile for a keyboard device - so synthetic keys reach the GUI
and never the emulator. A joystick has no such restriction.

Button order matters: SDL and Kodi both walk the evdev key bitmap upward from
BTN_JOYSTICK, so the indices in the generated buttonmap follow the order the
codes are declared here.

    vpad.py --selftest          # create it, hold it open, print what it made
"""

import fcntl
import os
import struct
import sys
import time

UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0

VENDOR, PRODUCT, VERSION = 0xE2E0, 0x0001, 0x0001
NAME = b"e2e virtual pad"

# evdev code order == buttonmap index order
BUTTONS = [
    ("a", 0x130), ("b", 0x131), ("x", 0x133), ("y", 0x134),
    ("leftbumper", 0x136), ("rightbumper", 0x137),
    ("back", 0x13a), ("start", 0x13b), ("guide", 0x13c),
    ("leftthumb", 0x13d), ("rightthumb", 0x13e),
]
ABS_X, ABS_Y, ABS_Z, ABS_RZ, ABS_HAT0X, ABS_HAT0Y = 0, 1, 2, 5, 16, 17
AXES = [ABS_X, ABS_Y, ABS_Z, ABS_RZ, ABS_HAT0X, ABS_HAT0Y]


class VPad:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
        for _name, code in BUTTONS:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        for axis in AXES:
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, axis)

        absmin = [0] * 64
        absmax = [0] * 64
        for axis in (ABS_X, ABS_Y, ABS_Z, ABS_RZ):
            absmin[axis], absmax[axis] = -32768, 32767
        for axis in (ABS_HAT0X, ABS_HAT0Y):
            absmin[axis], absmax[axis] = -1, 1
        setup = struct.pack("80sHHHHi", NAME, 0x03, VENDOR, PRODUCT, VERSION, 0)
        setup += struct.pack("64i", *absmax) + struct.pack("64i", *absmin)
        setup += struct.pack("64i", *([0] * 64)) + struct.pack("64i", *([0] * 64))
        os.write(self.fd, setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        # Kodi has to see the udev add event and load a buttonmap for it.
        time.sleep(2.0)

    def _emit(self, etype, code, value):
        os.write(self.fd, struct.pack("llHHi", 0, 0, etype, code, value))

    def _sync(self):
        self._emit(EV_SYN, SYN_REPORT, 0)

    def tap(self, name, hold=0.12):
        code = dict(BUTTONS)[name]
        self._emit(EV_KEY, code, 1)
        self._sync()
        time.sleep(hold)
        self._emit(EV_KEY, code, 0)
        self._sync()

    def dpad(self, direction, hold=0.2):
        axis, value = {
            "left": (ABS_HAT0X, -1), "right": (ABS_HAT0X, 1),
            "up": (ABS_HAT0Y, -1), "down": (ABS_HAT0Y, 1),
        }[direction]
        self._emit(EV_ABS, axis, value)
        self._sync()
        time.sleep(hold)
        self._emit(EV_ABS, axis, 0)
        self._sync()

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


def other_joysticks():
    """Real pads already attached, which take the low ports ahead of this one.

    Kodi hands ports out in device order, so with a pad already connected the
    virtual one lands on player 2 and a title screen will ignore it - an input
    test would then pass for the wrong reason.
    """
    found = []
    try:
        blocks = open("/proc/bus/input/devices").read().split("\n\n")
    except OSError:
        return found
    for block in blocks:
        if "Handlers=" not in block or "js" not in block:
            continue
        for line in block.splitlines():
            if line.startswith('N: Name="') and NAME.decode() not in line:
                found.append(line[9:].rstrip('"'))
    return found


def buttonmap_filename():
    return "%s_v%04X_p%04X_%db_%da.xml" % (
        NAME.decode().replace(" ", "_"), VENDOR, PRODUCT, len(BUTTONS), len(AXES))


if __name__ == "__main__":
    pad = VPad()
    print("created %r vid=%04X pid=%04X buttons=%d axes=%d"
          % (NAME.decode(), VENDOR, PRODUCT, len(BUTTONS), len(AXES)))
    print("buttonmap should be named:", buttonmap_filename())
    if "--selftest" in sys.argv:
        time.sleep(float(sys.argv[sys.argv.index("--selftest") + 1])
                   if len(sys.argv) > sys.argv.index("--selftest") + 1 else 20)
    pad.close()
    print("destroyed")
