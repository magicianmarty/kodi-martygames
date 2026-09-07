#!/usr/bin/env python3
"""Run Kodi builtins on the box over the EventServer (UDP 9777).

JSON-RPC cannot run builtins, and the box's web server is off, so this is the
only remote route to things like ActivateWindow() and ReloadSkin().

    ./tools/es.py 'ReloadSkin()' 'Action(Down)'
    ./tools/es.py --key return --key x        # keystrokes, for cores that
                                              # want a keyboard rather than a pad
"""
import os, socket, struct, sys, time

HOST = os.environ.get('MARTYGAMES_BOX_IP', '192.168.50.113')
PORT, UID = 9777, 0xC0DE1234


def pkt(ptype, payload, seq=1, maxseq=1):
    return (b"XBMC" + bytes([2, 0]) + struct.pack(">H", ptype)
            + struct.pack(">I", seq) + struct.pack(">I", maxseq)
            + struct.pack(">H", len(payload)) + struct.pack(">I", UID)
            + b"\x00" * 10 + payload)


def send(sock, ptype, payload):
    sock.sendto(pkt(ptype, payload), (HOST, PORT))
    time.sleep(0.15)


BTN_USE_NAME, BTN_DOWN, BTN_UP = 0x01, 0x02, 0x04


def button(sock, name, keymap="KB"):
    """A keypress by name, down then up, through Kodi's keyboard map."""
    for updown in (BTN_DOWN, BTN_UP):
        payload = (struct.pack(">HHh", 0, BTN_USE_NAME | updown, 0)
                   + keymap.encode() + b"\x00" + name.encode() + b"\x00")
        send(sock, 0x03, payload)


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send(s, 0x01, b"claude\x00" + bytes([0]) + struct.pack(">H", 0) + struct.pack(">I", 0) * 2)
    args, sent = sys.argv[1:], 0
    while args:
        arg = args.pop(0)
        if arg == "--key":
            button(s, args.pop(0))
        else:
            send(s, 0x0A, bytes([1]) + arg.encode() + b"\x00")   # EXECBUILTIN
        sent += 1
    send(s, 0x02, b"")
    print("sent %d event(s)" % sent)


if __name__ == '__main__':
    main()
