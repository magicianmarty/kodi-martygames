#!/usr/bin/env python3
"""Type on the box as a real HID keyboard, via uinput.

Kodi turns EventServer "KB" packets into GUI actions, so they never reach a
game client's keyboard handler - a core that wants a keyboard cannot be tested
that way. A uinput device is indistinguishable from a plugged-in keyboard.

    uikey.py a return
"""
import fcntl, os, struct, sys, time

UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EV_SYN, EV_KEY = 0, 1

KEYS = {'a': 30, 'b': 48, 'c': 46, 'x': 45, 'y': 21, 'z': 44, 'n': 49,
        '1': 2, '2': 3, '3': 4, 'return': 28, 'enter': 28, 'space': 57,
        'escape': 1, 'up': 103, 'down': 108, 'left': 105, 'right': 106}


def emit(fd, etype, code, value):
    os.write(fd, struct.pack('llHHi', 0, 0, etype, code, value))


def main():
    names = sys.argv[1:] or ['a']
    fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for code in set(KEYS.values()):
        fcntl.ioctl(fd, UI_SET_KEYBIT, code)

    # legacy uinput_user_dev: name[80] + input_id + ff_effects_max + 4x abs[64]
    os.write(fd, struct.pack('80sHHHHi', b'claude-virtual-kbd',
                             0x03, 0x1234, 0x5678, 1, 0) + b'\0' * (64 * 4 * 4))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(1.5)          # let Kodi notice the new device

    for name in names:
        code = KEYS.get(name)
        if code is None:
            print('unknown key %s' % name); continue
        for value in (1, 0):
            emit(fd, EV_KEY, code, value)
            emit(fd, EV_SYN, 0, 0)
        print('pressed %s' % name)
        time.sleep(0.4)

    time.sleep(0.5)
    fcntl.ioctl(fd, UI_DEV_DESTROY)
    os.close(fd)


main()
