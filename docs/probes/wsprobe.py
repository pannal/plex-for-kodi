#!/usr/bin/env python3
"""Minimal RFC6455 client to probe the Plex Syncplay relay.

Read-only. Pongs every ping immediately. Logs every frame with a timestamp.
Sends no Set/State, so it cannot alter anyone else's playback.
"""
import base64
import json
import os
import socket
import ssl
import struct
import sys
import time

ROOM = sys.argv[1]
HOST = sys.argv[2]
PORT = int(sys.argv[3])
USER_ID = sys.argv[4]
DEVICE_ID = sys.argv[5] if len(sys.argv) > 5 else "probe-plexfor-kodi"
DEVICE_NAME = sys.argv[6] if len(sys.argv) > 6 else "probe"
VERSION = sys.argv[7] if len(sys.argv) > 7 else "1.6.4"
LISTEN = float(sys.argv[8]) if len(sys.argv) > 8 else 25.0

USER = {"deviceIdentifier": DEVICE_ID, "deviceName": DEVICE_NAME, "userID": str(USER_ID)}
T0 = time.time()


def log(*a):
    print("[%6.2fs]" % (time.time() - T0), *a, flush=True)


def frame(payload, opcode=0x1):
    b = payload.encode() if isinstance(payload, str) else payload
    n = len(b)
    h = bytes([0x80 | opcode])
    if n < 126:
        h += bytes([0x80 | n])
    elif n < 1 << 16:
        h += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        h += bytes([0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    return h + mask + bytes(c ^ k for c, k in zip(b, mask * n))


class Reader:
    def __init__(self, sock):
        self.s = sock
        self.buf = b""

    def _need(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("server closed TCP")
            self.buf += chunk

    def frame(self):
        self._need(2)
        b0, b1 = self.buf[0], self.buf[1]
        op, masked, ln = b0 & 0xF, b1 & 0x80, b1 & 0x7F
        off = 2
        if ln == 126:
            self._need(4); ln = struct.unpack(">H", self.buf[2:4])[0]; off = 4
        elif ln == 127:
            self._need(10); ln = struct.unpack(">Q", self.buf[2:10])[0]; off = 10
        if masked:
            self._need(off + 4); off += 4
        self._need(off + ln)
        data = self.buf[off:off + ln]
        self.buf = self.buf[off + ln:]
        return op, data


key = base64.b64encode(os.urandom(16)).decode()
req = ["GET /ws HTTP/1.1", "Host: %s" % HOST, "Upgrade: websocket",
       "Connection: Upgrade", "Sec-WebSocket-Key: %s" % key,
       "Sec-WebSocket-Version: 13", "Origin: https://app.plex.tv",
       "X-Plex-Product: PM4K"]

sock = ctx = None
try:
    sock = socket.create_connection((HOST, PORT), timeout=15)
    ctx = ssl.create_default_context()
    sock = ctx.wrap_socket(sock, server_hostname=HOST)
    cert = sock.getpeercert().get("subject")
    log("TLS %s  cn=%s" % (sock.version(), dict(x[0] for x in cert).get("commonName")))
    sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())

    r = Reader(sock)
    head = b""
    while b"\r\n\r\n" not in head:
        c = sock.recv(1)
        if not c:
            break
        head += c
    log("handshake:", head.decode(errors="replace").strip().replace("\r\n", " | "))
    if b" 101 " not in head.split(b"\r\n")[0]:
        sys.exit("no 101")

    sock.sendall(frame(json.dumps({"Hello": {"room": {"name": ROOM},
                                            "username": json.dumps(USER),
                                            "version": VERSION}})))
    log(">>> Hello  user=%s device=%r version=%s" % (USER_ID, DEVICE_ID, VERSION))

    end = time.time() + LISTEN
    sent_list = False
    while time.time() < end:
        if not sent_list and time.time() - T0 > 1.0:
            sock.sendall(frame(json.dumps({"List": {}})))
            log(">>> List")
            sent_list = True
        sock.settimeout(max(1.0, end - time.time()))
        try:
            op, data = r.frame()
        except (socket.timeout, ssl.SSLWantReadError):
            break
        except Exception as e:
            log("read stopped: %r" % (e,))
            break
        if op == 0x9:
            sock.sendall(frame(data, 0xA))
            log("<<< ping %dB  (ponged)" % len(data))
        elif op == 0xA:
            log("<<< pong %r" % data[:60])
        elif op == 0x8:
            log("<<< CLOSE  code=%d reason=%r" % (int.from_bytes(data[:2], "big"), data[2:200]))
            break
        elif op in (0x1, 0x2):
            txt = data.decode(errors="replace")
            try:
                txt = json.dumps(json.loads(txt))
            except Exception:
                pass
            log("<<<", txt[:900])
            if not sent_list and "List" in txt:
                sock.sendall(frame(json.dumps({"List": {}})))
                log(">>> List")
                sent_list = True
        else:
            log("<<< op=0x%x %r" % (op, data[:120]))
except Exception as e:
    log("FATAL %r" % (e,))
finally:
    if sock is not None:
        try:
            sock.sendall(frame(b"", 0x8))
            sock.close()
        except Exception:
            pass
    log("done")