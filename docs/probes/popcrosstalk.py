#!/usr/bin/env python3
"""Are the Syncplay relay PoPs interchangeable?  (docs/watch-together.md §3, §11.22)

The relay is described as a dumb pub/sub bus with no room table (§7), which predicts
that a room name is purely a string the relay fans out on and that therefore ANY PoP
would accept ANY name -- making PoPs fungible failover targets. Measured answer: the
handshake half of that is true (every PoP accepts every name with 101), the routing
half is false. A room name is scoped to one relay INSTANCE -- one host:port pair.
Two clients on the same PoP but different ports, or on different PoPs, each get a
101 and each see only themselves in List. So syncplayHost AND syncplayPort from the
room record are both load-bearing, and a client that gets either wrong silently
syncs to an empty room of its own instead of erroring.

Run it with two clients on the SAME host:port as a control first: that case must
show both identities in both rosters, otherwise "they did not see each other"
proves nothing.

    python3 docs/probes/popcrosstalk.py [room] [host:port ...]
"""
import base64
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
import uuid

# Usage: popcrosstalk.py [room] [host:port ...]   (defaults: one client per known PoP)
ROOM = sys.argv[1] if len(sys.argv) > 1 else "popx" + uuid.uuid4().hex[:10]
POPS = []
for arg in sys.argv[2:]:
    h, _, p = arg.partition(":")
    POPS.append((h, int(p or 7777)))
if not POPS:
    POPS = [("pop-fra01.syncplay.plex.services", 7777),
            ("pop-atl01.syncplay.plex.services", 7777),
            ("pop-fra00.syncplay.plex.services", 7776)]
VERSION = "1.6.4"
T0 = time.monotonic()
LOCK = threading.Lock()


def log(*a):
    with LOCK:
        print("[%6.2fs]" % (time.monotonic() - T0), *a, flush=True)


def frame(p, op=0x1):
    b = p.encode() if isinstance(p, str) else p
    n = len(b)
    h = bytes([0x80 | op])
    if n < 126:
        h += bytes([0x80 | n])
    elif n < 1 << 16:
        h += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        h += bytes([0x80 | 127]) + struct.pack(">Q", n)
    m = os.urandom(4)
    return h + m + bytes(c ^ k for c, k in zip(b, m * n))


class Client(threading.Thread):
    def __init__(self, label, host, port):
        super().__init__(daemon=True)
        self.label, self.host, self.port = label, host, port
        self.identity = json.dumps(
            {"userID": "0", "deviceIdentifier": "xpop-" + label,
             "deviceName": label}, separators=(",", ":"))
        self.server_rtt = 0.0
        self.relay_ignore = 0
        self.stop = threading.Event()
        self.wlock = threading.Lock()
        self.lists = []
        self.state_seen = 0
        self.hello = None
        self.status = None
        self.tls = None
        s = socket.create_connection((host, port), timeout=20)
        c = ssl.create_default_context().wrap_socket(s, server_hostname=host)
        self.tls = (c.version(), c.cipher()[0])
        c.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                   "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                   "Sec-WebSocket-Version: 13\r\nOrigin: https://app.plex.tv\r\n"
                   "Sec-WebSocket-Protocol: plex.syncplay\r\n\r\n"
                   % (host, base64.b64encode(os.urandom(16)).decode())).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += c.recv(1)
        head, rest = head.split(b"\r\n\r\n", 1)
        self.status = head.decode().splitlines()[0]
        self.headers = head.decode()
        self.sock = c
        self.buf = rest
        self.send({"Hello": {"room": {"name": ROOM}, "username": self.identity,
                             "version": VERSION}})

    def send(self, o):
        with self.wlock:
            try:
                self.sock.sendall(frame(json.dumps(o)))
            except OSError as e:
                log("%s SEND ERROR %r" % (self.label, e))
                self.stop.set()

    def _need(self, n):
        while len(self.buf) < n:
            ch = self.sock.recv(65536)
            if not ch:
                raise EOFError
            self.buf += ch

    def keepalive(self):
        while not self.stop.is_set():
            self.send({"State": {
                "ping": {"clientLatencyCalculation": time.monotonic(),
                         "clientRtt": 0.0, "latencyCalculation": time.time(),
                         "serverRtt": self.server_rtt},
                "playstate": {"doSeek": False, "paused": True, "position": 0,
                              "setBy": None},
                "ignoringOnTheFly": {"client": 0, "server": self.relay_ignore}}})
            self.stop.wait(1.0)

    def run(self):
        self.sock.settimeout(0.5)
        threading.Thread(target=self.keepalive, daemon=True).start()
        while not self.stop.is_set():
            try:
                self._need(2)
            except (socket.timeout, TimeoutError):
                continue
            except (EOFError, OSError):
                log("%s socket closed" % self.label)
                return
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
            data, self.buf = self.buf[off:off + ln], self.buf[off + ln:]
            if op == 0x9:
                with self.wlock:
                    self.sock.sendall(frame(data, 0xA))
                continue
            if op == 0x8:
                self.stop.set()
                return
            if op not in (0x1, 0x2):
                continue
            try:
                m = json.loads(data)
            except ValueError:
                continue
            if "Hello" in m:
                self.hello = m["Hello"]
            elif "List" in m:
                self.lists.append(m["List"])
            elif "State" in m:
                self.state_seen += 1
                ig = m["State"].get("ignoringOnTheFly", {}).get("server")
                if ig:
                    self.relay_ignore = int(ig)
                rtt = m["State"].get("ping", {}).get("serverRtt")
                if isinstance(rtt, (int, float)):
                    self.server_rtt = rtt

    def close(self):
        self.stop.set()
        try:
            self.sock.sendall(frame(b"", 0x8))
            self.sock.close()
        except OSError:
            pass


def who(raw):
    try:
        return json.loads(raw.rstrip("_")).get("deviceIdentifier", "?")
    except ValueError:
        return "<unparseable>"


def roster(c):
    if not c.lists:
        return None
    last = c.lists[-1]
    if ROOM not in last:
        return {"<room key absent>": sorted(last)}
    return {who(k): {"controller": v.get("controller"), "position": v.get("position")}
            for k, v in last[ROOM].items()}


def main():
    print("room    : %s   (throwaway, cloud never told)" % ROOM)
    clients = []
    for i, (host, port) in enumerate(POPS):
        # the index is in the label so two clients on the SAME host:port still get
        # distinct identities -- otherwise the relay de-dupes them into one roster key
        # and the control case ("can co-located clients see each other?") reads as a
        # failure to observe.
        c = Client("%s:%d#%d" % (host.split(".")[0], port, i), host, port)
        c.start()
        clients.append(c)
        log("%-10s %s:%d  %s  %s" % (c.label, host, port, c.tls, c.status))
        time.sleep(1.5)

    print()
    print("staggered join: each PoP joined while the earlier ones were already present.")
    time.sleep(4)

    for c in clients:
        c.send({"List": {}})
    time.sleep(2)
    for c in clients:
        c.send({"List": {}})
    time.sleep(2)

    print()
    print("%-10s %-38s %-6s %-8s %s" % ("PoP", "handshake", "State", "List?", "roster seen"))
    for c in clients:
        r = roster(c)
        print("%-10s %-38s %-6d %-8s %s"
              % (c.label, c.status, c.state_seen,
                 "yes" if c.lists else "NO", sorted(r) if r else r))

    print()
    print("per-PoP detail:")
    for c in clients:
        print("   %-26s %s  state=%d  hello=%s"
              % (c.label, c.status, c.state_seen,
                 (c.hello or {}).get("realversion")))
        for line in c.headers.splitlines()[1:]:
            print("        %s" % line)
    print()
    print("room key present in every List?  %s"
          % all(ROOM in (c.lists[-1] if c.lists else {}) for c in clients))
    print("did every client see ALL THREE identities?  %s"
          % all(roster(c) and len(roster(c)) == len(clients) for c in clients))
    for c in clients:
        c.close()
    time.sleep(0.5)
    print("room name: %s" % ROOM)


if __name__ == "__main__":
    main()