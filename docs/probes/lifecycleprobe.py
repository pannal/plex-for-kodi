#!/usr/bin/env python3
"""Two spec questions, in a throwaway room:

Q1. Two simultaneous connections sharing the SAME username — does the relay
    evict one, refuse the second, or allow both?
Q2. Does per-user state (ready / file / position) survive a disconnect+reconnect?
"""
import base64, json, os, socket, ssl, struct, sys, threading, time, uuid

HOST, PORT = "pop-fra00.syncplay.plex.services", 7776
ROOM = "wt" + uuid.uuid4().hex[:8]
LOCK = threading.Lock()


def log(*a):
    with LOCK:
        print("[%6.2fs]" % (time.time() - T0), *a, flush=True)


def frame(p, op=0x1):
    b = p.encode() if isinstance(p, str) else p
    n = len(b)
    h = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else
        bytes([0x80 | 126]) + struct.pack(">H", n) if n < 1 << 16 else
        bytes([0x80 | 127]) + struct.pack(">Q", n))
    m = os.urandom(4)
    return h + m + bytes(c ^ k for c, k in zip(b, m * n))


class Conn:
    def __init__(self, user, tag):
        self.tag, self.user = tag, user
        self.alive = True
        s = socket.create_connection((HOST, PORT), timeout=15)
        self.s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
        self.s.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                        % (HOST, base64.b64encode(os.urandom(16)).decode())).encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.s.recv(4096)
        self.buf = self.buf.split(b"\r\n\r\n", 1)[1]
        self.send({"Hello": {"room": {"name": ROOM},
                             "username": json.dumps(user), "version": "1.6.4"}})
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _need(self, n):
        while len(self.buf) < n:
            c = self.s.recv(65536)
            if not c:
                raise EOFError
            self.buf += c

    def send(self, o):
        self.s.sendall(frame(json.dumps(o)))

    def _read(self):
        try:
            while self.alive:
                self._need(2)
                b0, b1 = self.buf[0], self.buf[1]
                op, masked, ln = b0 & 0xF, b1 & 0x80, b1 & 0x7F
                off = 2
                if ln == 126: self._need(4); ln = struct.unpack(">H", self.buf[2:4])[0]; off = 4
                elif ln == 127: self._need(10); ln = struct.unpack(">Q", self.buf[2:10])[0]; off = 10
                if masked: self._need(off + 4); off += 4
                self._need(off + ln)
                d = self.buf[off:off + ln]
                self.buf = self.buf[off + ln:]
                if op == 0x9:
                    self.s.sendall(frame(d, 0xA))
                    log("  %s got ping" % self.tag)
                elif op == 0x8:
                    log("  %s SERVER CLOSE code=%d reason=%r" % (
                        self.tag, int.from_bytes(d[:2], "big"), d[2:160]))
                    self.alive = False
                    return
                elif op in (0x1, 0x2):
                    t = d.decode(errors="replace")
                    if '"State"' in t or '"playlist' in t:
                        continue
                    log("  %s <<< %s" % (self.tag, t[:300]))
        except Exception as e:
            log("  %s READ-END %r" % (self.tag, e))
            self.alive = False

    def close(self):
        self.alive = False
        try:
            self.s.sendall(frame(b"", 0x8))
            self.s.close()
        except Exception:
            pass


T0 = time.time()
U = {"deviceIdentifier": "dup-device", "deviceName": "dup", "userID": "1000001"}
log("room =", ROOM)

log("=== Q1: two connections, IDENTICAL username ===")
a = Conn(U, "A")
time.sleep(1.5)
b = Conn(U, "B")
time.sleep(2.5)
log("A alive=%s   B alive=%s" % (a.alive, b.alive))

log("=== Q2a: B sets ready+file, then disconnects; A observes ===")
b.send({"Set": {"ready": {"isReady": True}}})
b.send({"Set": {"file": {"name": json.dumps(
    {"ads": {"playing": False}, "uri": "server://x/library/metadata/1"})}}})
time.sleep(1.5)
b.close()
time.sleep(2.0)

log("=== Q2b: reconnect with same username — did A see 'left'? did state survive? ===")
c = Conn(U, "C")
time.sleep(1.5)
c.send({"List": {}})
time.sleep(2.0)
log("A alive=%s   C alive=%s" % (a.alive, c.alive))
c.close(); a.close()
log("done")