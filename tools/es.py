#!/usr/bin/env python3
"""Run Kodi builtins on the box over the EventServer (UDP 9777).

JSON-RPC cannot run builtins, and the box's web server is off, so this is the
only remote route to things like ActivateWindow() and ReloadSkin().

    ./tools/es.py 'ReloadSkin()' 'Action(Down)'
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


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send(s, 0x01, b"claude\x00" + bytes([0]) + struct.pack(">H", 0) + struct.pack(">I", 0) * 2)
    for arg in sys.argv[1:]:
        send(s, 0x0A, bytes([1]) + arg.encode() + b"\x00")   # EXECBUILTIN
    send(s, 0x02, b"")
    print("sent %d builtin(s)" % (len(sys.argv) - 1))


if __name__ == '__main__':
    main()
