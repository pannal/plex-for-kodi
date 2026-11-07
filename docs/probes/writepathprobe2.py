#!/usr/bin/env python3
"""Follow-up: exact bytes back for the surprising write-path results.

Three things writepathprobe.py flagged but truncated:
  1. oversized uri -- features.maxFilenameLength is 250. Does the relay truncate the
     file payload, and if so where?
  2. Set{ready} -- is manuallyInitiated preserved, or normalised?
  3. Set{playlistChange}/{playlistIndex} -- the reply looked like {"user": "<identity>"}
     rather than an echo of the playlist. If so the playlist messages are write-only:
     the relay acknowledges by naming the user and keeps no playlist state.

Usage: python3 writepathprobe2.py [host] [port]
"""
import base64, json, os, socket, ssl, struct, sys, threading, time, uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "pop-atl01.syncplay.plex.services"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7777
ROOM = "wt" + uuid.uuid4().hex[:8]
SOURCE_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117")
T0, LOCK = time.monotonic(), threading.Lock()
MARK = {}


def mark(n):
    MARK[n] = time.monotonic() - T0


def since(n):
    return MARK.get(n, 0.0)


def rule(t):
    with LOCK:
        print("\n" + "=" * 78 + "\n== " + t + "\n" + "=" * 78, flush=True)


def frame(p, op=0x1):
    b = p.encode() if isinstance(p, str) else p
    n = len(b)
    if n < 126:
        h = bytes([0x80 | op, 0x80 | n])
    elif n < 1 << 16:
        h = bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
    else:
        h = bytes([0x80 | op, 0x80 | 127]) + struct.pack(">Q", n)
    m = os.urandom(4)
    return h + m + bytes(c ^ k for c, k in zip(b, m * n))


class C(threading.Thread):
    def __init__(self, tag, label, uid, dev):
        super().__init__(daemon=True)
        self.tag, self.label = tag, label
        self.identity = json.dumps({"userID": str(uid), "deviceIdentifier": dev,
                                    "deviceName": label}, separators=(",", ":"))
        self.relay_ignore = 0
        self.stop = threading.Event()
        self.wlock = threading.Lock()
        self.msgs = []
        self.err = None

    def connect(self):
        s = socket.create_connection((HOST, PORT), timeout=20)
        self.sock = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
        self.sock.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                           "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n"
                           % (HOST, base64.b64encode(os.urandom(16)).decode())).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.send({"Hello": {"room": {"name": ROOM}, "username": self.identity,
                             "version": "1.6.4"}})

    def send(self, o):
        with self.wlock:
            try:
                self.sock.sendall(frame(json.dumps(o)))
            except OSError as e:
                self.err = repr(e); self.stop.set()

    def ka(self):
        while not self.stop.is_set():
            self.send({"State": {
                "ping": {"clientLatencyCalculation": time.monotonic(), "clientRtt": 0,
                         "latencyCalculation": time.time(), "serverRtt": 0},
                "playstate": {"doSeek": False, "paused": True, "position": 0, "setBy": None},
                "ignoringOnTheFly": {"client": 0, "server": self.relay_ignore}}})
            self.stop.wait(1.0)

    def close(self):
        self.stop.set()
        try:
            with self.wlock:
                self.sock.sendall(frame(b"", 0x8)); self.sock.close()
        except OSError:
            pass

    def _need(self, n):
        while len(self.buf) < n:
            c = self.sock.recv(65536)
            if not c:
                raise EOFError
            self.buf += c

    def run(self):
        self.sock.settimeout(0.5)
        threading.Thread(target=self.ka, daemon=True).start()
        while not self.stop.is_set():
            try:
                self._need(2)
            except (socket.timeout, TimeoutError):
                continue
            except (EOFError, OSError):
                self.stop.set(); return
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
                self.stop.set(); return
            if op not in (0x1, 0x2):
                continue
            try:
                m = json.loads(data.decode(errors="replace"))
            except ValueError:
                self.msgs.append((time.monotonic() - T0, {"__bad": data.decode(errors="replace")}))
                continue
            self.msgs.append((time.monotonic() - T0, m))
            if "State" in m:
                ig = (m["State"].get("ignoringOnTheFly") or {}).get("server")
                if isinstance(ig, int):
                    self.relay_ignore = ig

    def since_msg(self, n, key):
        out = []
        for t, m in self.msgs:
            if t < since(n):
                continue
            if key in m:
                out.append((t - since(n), m[key]))
        return out


def main():
    run = uuid.uuid4().hex[:8]
    a, b = C("A", "BRAVIA VH1", 1000003, "pA" + run), C("B", "Safari", 1000001, "pB" + run)
    a.connect(); b.connect(); a.start(); b.start()
    rule("SETUP   room=%s relay=%s:%d" % (ROOM, HOST, PORT))
    time.sleep(1.0)

    rule("1  file payload length vs features.maxFilenameLength (250)")
    for n in (100, 200, 240, 245, 248, 249, 250, 251, 260, 400, 800):
        uri = "server://" + ("x" * (n - 10))
        payload = json.dumps({"ads": {"playing": False}, "uri": uri},
                             separators=(",", ":"))
        k = "len%d" % n
        mark(k)
        a.send({"Set": {"file": {"name": payload}}})
        time.sleep(1.5)
        got = None
        for t, m in b.msgs:
            if t < since(k) or "Set" not in m:
                continue
            # Set{user: {<identity>: {room, file}}} -- m["Set"]["user"] is keyed BY the
            # sender's identity string, and the file sits inside that. Two levels down.
            for outer in m["Set"].values():
                if not isinstance(outer, dict):
                    continue
                for inner in outer.values():
                    if isinstance(inner, dict) and isinstance(inner.get("file"), dict):
                        got = inner["file"].get("name")
        if got is None:
            print("   sent inner=%-4d bytes -> (nothing echoed)" % len(payload))
        else:
            print("   sent inner=%-4d bytes -> got inner=%-4d bytes  uri_len=%-4d %s"
                  % (len(payload), len(got), len(got) - len('{"uri":"","ads":{"playing":false}}')
                     if got.startswith('{"uri"') else -1,
                     "TRUNCATED" if len(got) < len(payload) else "verbatim"))

    rule("2  Set{ready} -- is manuallyInitiated preserved?")
    for label, body in [
        ("false/false", {"isReady": False, "manuallyInitiated": False}),
        ("true/false", {"isReady": True, "manuallyInitiated": False}),
        ("true/TRUE", {"isReady": True, "manuallyInitiated": True}),
        ("null/false", {"isReady": None, "manuallyInitiated": False}),
        ("true only", {"isReady": True}),
        ("extra key", {"isReady": True, "manuallyInitiated": False, "bogusKey": 42}),
    ]:
        k = "r" + label
        mark(k)
        a.send({"Set": {"ready": body}})
        time.sleep(1.6)
        ga = a.since_msg(k, "Set")
        gb = b.since_msg(k, "Set")
        print("   sent   %-58s" % json.dumps(body))
        print("     sender <- %s" % (json.dumps(ga[0][1]["ready"]) if ga and "ready" in ga[0][1]
                                     else "(none)"))
        print("     peer   <- %s" % (json.dumps(gb[0][1]["ready"]) if gb and "ready" in gb[0][1]
                                     else "(none)"))

    rule("3  playlist messages -- is any playlist state kept, or just an ack?")
    f1 = json.dumps({"ads": {"playing": False}, "uri": SOURCE_URI}, separators=(",", ":"))
    for label, msg in [
        ("playlistChange files:[1 file]", {"Set": {"playlistChange": {
            "user": None, "files": [{"name": f1}]}}}),
        ("playlistIndex index:0", {"Set": {"playlistIndex": {"user": None, "index": 0}}}),
        ("playlistIndex index:1", {"Set": {"playlistIndex": {"user": None, "index": 1}}}),
        ("playlistChange files:[]", {"Set": {"playlistChange": {"user": None, "files": []}}}),
        ("playlistIndex index:null", {"Set": {"playlistIndex": {"user": None, "index": None}}}),
    ]:
        k = "p" + label
        key = list(msg["Set"].keys())[0]
        mark(k)
        a.send(msg)
        time.sleep(1.7)
        print("   -> %s" % label)
        for c in (a, b):
            rows = c.since_msg(k, "Set")
            print("      %s <- %s" % (c.tag, json.dumps(rows[0][1]) if rows else "(none)"))

    mark("final")
    a.send({"List": {}})
    time.sleep(1.5)
    last = None
    for t, m in a.msgs:
        if "List" in m:
            last = m
    rule("FINAL ROSTER (does it know about playlists at all?)")
    if last:
        for raw, v in last.get("List", {}).get(ROOM, {}).items():
            print("   %s" % json.dumps(v, sort_keys=True))
    a.close(); b.close()
    print("\n   errors A=%s B=%s" % (a.err, b.err))


if __name__ == "__main__":
    main()