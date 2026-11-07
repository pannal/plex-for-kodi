#!/usr/bin/env python3
"""Characterise the relay's username padding/disambiguation.

Hypothesis: the relay right-pads (or underscore-suffixes) usernames to a per-room
normalised width, so two sessions with byte-identical identity get distinguishable keys.
"""
import base64, json, os, socket, ssl, struct, threading, time, uuid

HOST, PORT = "pop-fra00.syncplay.plex.services", 7776
ROOM = "wt" + uuid.uuid4().hex[:8]
LOCK = threading.Lock()
T0 = time.time()
log = lambda *a: (LOCK.acquire(), print("[%6.2fs]" % (time.time() - T0), *a, flush=True), LOCK.release())


def frame(p, op=0x1):
    b = p.encode() if isinstance(p, str) else p
    n = len(b)
    h = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else
        bytes([0x80 | 126]) + struct.pack(">H", n) if n < 1 << 16 else
        bytes([0x80 | 127]) + struct.pack(">Q", n))
    m = os.urandom(4)
    return h + m + bytes(c ^ k for c, k in zip(b, m * n))


class Conn:
    def __init__(self, raw_user_json, tag):
        self.tag = tag
        self.s = socket.create_connection((HOST, PORT), timeout=15)
        self.s = ssl.create_default_context().wrap_socket(self.s, server_hostname=HOST)
        self.s.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                        % (HOST, base64.b64encode(os.urandom(16)).decode())).encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.s.recv(4096)
        self.buf = self.buf.split(b"\r\n\r\n", 1)[1]
        self.send({"Hello": {"room": {"name": ROOM}, "username": raw_user_json,
                             "version": "1.6.4"}})
        self.roster = {}
        threading.Thread(target=self._read, daemon=True).start()

    def send(self, o):
        self.s.sendall(frame(json.dumps(o)))

    def _need(self, n):
        while len(self.buf) < n:
            c = self.s.recv(65536)
            if not c:
                raise EOFError
            self.buf += c

    def _read(self):
        try:
            while True:
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
                elif op == 0x8:
                    log("  %s SERVER CLOSE %d %r" % (self.tag, int.from_bytes(d[:2], "big"), d[2:120]))
                    return
                elif op in (0x1, 0x2):
                    m = json.loads(d)
                    if "List" in m:
                        for rname, users in m["List"].items():
                            self.roster = users
                    elif "Hello" in m:
                        self.roster.setdefault("_self_", m["Hello"]["username"])
        except Exception:
            pass

    def close(self):
        try:
            self.s.sendall(frame(b"", 0x8)); self.s.close()
        except Exception:
            pass


def uj(**kw):
    return json.dumps(kw)


log("room =", ROOM)
log("maxUsernameLength advertised by relay = 150")

log("\n=== identities of deliberately different lengths, joined in order ===")
short = uj(deviceIdentifier="a", deviceName="b", userID="1")
mid = uj(deviceIdentifier="m" * 30, deviceName="n" * 30, userID="2")
long = uj(deviceIdentifier="L" * 100, deviceName="M" * 100, userID="3")
for name, raw in (("short", short), ("mid", mid), ("long", long)):
    log("  %-5s sent len=%d" % (name, len(raw)))

conns = [Conn(short, "short"), Conn(mid, "mid"), Conn(long, "long")]
time.sleep(1.0)
for c in conns:
    c.send({"List": {}})
time.sleep(2.0)

conns[0].roster = {}
conns[0].send({"List": {}})
time.sleep(1.5)
print("\n=== full roster as the relay reports it ===")
for k, v in sorted(conns[0].roster.items()):
    stripped = k.rstrip("_")
    print("  key len=%3d  trailing_=%d  stripped len=%3d  %s" % (
        len(k), len(k) - len(stripped), len(stripped), stripped[:70]))
print("\n  matches sent identity exactly after stripping _:")
sent = {short, mid, long}
for k in conns[0].roster:
    print("    %-5s %r" % (k.rstrip("_") in sent, k.rstrip("_")[:60]))
for c in conns:
    c.close()
log("done")