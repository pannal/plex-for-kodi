#!/usr/bin/env python3
"""What does the relay do with each WRITE-path message?  (§5.4, §11 item 14 relay half)

Everything here runs in a throwaway room name that the cloud never learns about, so
nothing real can be disturbed. Two conforming clients so we can tell "the sender sees its
own write echoed" from "the write reached the peer" -- those are different questions and
the doc conflates them in places.

Questions:
  W1  Set{file}: what comes back to the SENDER?  (§5.4 claims Set.file returns as
      Set.user with a file and no event -- verify, and check the payload is verbatim)
  W2  Set{file}: does the PEER see it, and does it land in List.file?  (§5.8 says a
      fresh session's List entry shows file:{} -- but that was a session that never sent one)
  W3  Does the relay validate the file payload at all?  (empty name, garbage JSON,
      missing uri, wrong key order)
  W4  Set{ready}: do false -> true transitions and manuallyInitiated propagate?  And is
      it reflected in List.isReady?
  W5  Set{playlistChange} / Set{playlistIndex}: do the REAL Android client's shapes
      propagate -- files: [] and index: null -- or only non-empty ones?  Do they reach
      the peer and the roster?
  W6  Double-encoding: is the inner JSON echoed byte-for-byte, or re-serialised?

Usage: python3 writepathprobe.py [host] [port]
"""
import base64, json, os, socket, ssl, struct, sys, threading, time, uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "pop-atl01.syncplay.plex.services"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7777
ROOM = "wt" + uuid.uuid4().hex[:8]
SOURCE_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117")
VERSION = "1.6.4"
T0 = time.monotonic()
LOCK = threading.Lock()
MARK = {}


def log(*a):
    with LOCK:
        print("[%6.2fs]" % (time.monotonic() - T0), *a, flush=True)


def rule(t):
    with LOCK:
        print("\n" + "=" * 78 + "\n== " + t + "\n" + "=" * 78, flush=True)


def mark(name):
    with LOCK:
        MARK[name] = time.monotonic() - T0


def since(name):
    return MARK.get(name, 0.0)


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


class Client(threading.Thread):
    def __init__(self, tag, label, user_id, device):
        super().__init__(daemon=True)
        self.tag, self.label = tag, label
        self.identity = json.dumps({"userID": str(user_id), "deviceIdentifier": device,
                                    "deviceName": label}, separators=(",", ":"))
        self.relay_ignore = 0
        self.stop = threading.Event()
        self.wlock = threading.Lock()
        self.sent = 0
        self.send_err = None
        self.msgs = []           # (t, parsed, raw_text)

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
                             "version": VERSION}})

    def send(self, o):
        with self.wlock:
            try:
                self.sock.sendall(frame(json.dumps(o)))
                self.sent += 1
            except OSError as e:
                self.send_err = repr(e)
                self.stop.set()

    def keepalive(self):
        # conforming 1 Hz heartbeat, mirroring the relay's counter (§5.9). Without this
        # we get evicted at ~14s and cannot observe anything.
        while not self.stop.is_set():
            self.send({"State": {
                "ping": {"clientLatencyCalculation": time.monotonic(),
                         "clientRtt": 0, "latencyCalculation": time.time(), "serverRtt": 0},
                "playstate": {"doSeek": False, "paused": True, "position": 0, "setBy": None},
                "ignoringOnTheFly": {"client": 0, "server": self.relay_ignore}}})
            self.stop.wait(1.0)

    def close(self):
        self.stop.set()
        try:
            with self.wlock:
                self.sock.sendall(frame(b"", 0x8))
                self.sock.close()
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
        threading.Thread(target=self.keepalive, daemon=True).start()
        while not self.stop.is_set():
            try:
                self._need(2)
            except (socket.timeout, TimeoutError):
                continue
            except (EOFError, OSError):
                self.stop.set()
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
            txt = data.decode(errors="replace")
            try:
                m = json.loads(txt)
            except ValueError:
                self.msgs.append((time.monotonic() - T0, {"__unparseable": txt}, txt))
                continue
            self.msgs.append((time.monotonic() - T0, m, txt))
            if "State" in m:
                ig = (m["State"].get("ignoringOnTheFly") or {}).get("server")
                if isinstance(ig, int):
                    self.relay_ignore = ig


def sets_since(c, name, skip_state=True):
    """All non-State messages c received after mark `name`."""
    out = []
    for t, m, txt in c.msgs:
        if t < since(name):
            continue
        if skip_state and "State" in m:
            continue
        out.append((t - since(name), m, txt))
    return out


def dump(tag, rows):
    if not rows:
        print("   %s: (nothing)" % tag)
    for dt, m, txt in rows:
        k = list(m.keys())[0]
        body = json.dumps(m[k])
        print("   %s  t+%5.2fs  %-6s %s" % (tag, dt, k, body[:190]))


def roster(c):
    last = None
    for _, m, _ in c.msgs:
        if "List" in m:
            last = m
    if not last:
        return {}
    out = {}
    for raw, v in last.get("List", {}).get(ROOM, {}).items():
        try:
            n = json.loads(raw.rstrip("_")).get("deviceName", "?")
        except ValueError:
            n = "<unparseable>"
        out[n] = v
    return out


def inner_name(v):
    """Pull the double-encoded {ads,uri} payload out of a Set message, if present."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, vv in x.items():
                if k == "name" and isinstance(vv, str) and vv.startswith("{"):
                    found.append(vv)
                walk(vv)
        elif isinstance(x, list):
            for vv in x:
                walk(vv)
    walk(v)
    return found


def main():
    rule("SETUP")
    run = uuid.uuid4().hex[:8]
    a = Client("A", "BRAVIA VH1", 1000003, "probeA-" + run)
    b = Client("B", "Safari", 1000001, "probeB-" + run)
    a.connect(); b.connect()
    a.start(); b.start()
    print("room  : %s  (throwaway, cloud never told)" % ROOM)
    print("relay : %s:%d" % (HOST, PORT))
    time.sleep(1.0)

    # -- W1/W2: Set{file} --------------------------------------------------
    rule("W1/W2  A sends Set{file}  (ads-first, compact -- the doc's shape)")
    mark("file1")
    payload1 = json.dumps({"ads": {"playing": False}, "uri": SOURCE_URI},
                          separators=(",", ":"))
    a.send({"Set": {"file": {"name": payload1}}})
    time.sleep(2.5)
    dump("A(send)", sets_since(a, "file1"))
    dump("B(peer)", sets_since(b, "file1"))
    names = inner_name([m for _, m, _ in sets_since(b, "file1")])
    print("   W6  peer payload verbatim? %s" % (names and names[0] == payload1))
    print("       sent  : %s" % payload1[:120])
    print("       peer  : %s" % (names[0][:120] if names else "(none)"))

    # -- W2b: does file show up in the roster? ------------------------------
    rule("W2b  A asks for List -- is file now in the roster?")
    mark("list1")
    a.send({"List": {}})
    time.sleep(1.5)
    for n, v in roster(a).items():
        f = v.get("file")
        print("   %-12s isReady=%-5s file=%s" % (n, v.get("isReady"),
                                                  (f or {}).get("name", f) if f else f))

    # -- W3: is the payload validated at all? -------------------------------
    rule("W3  does the relay validate the file payload?")
    for label, payload in [
        ("empty-string", ""),
        ("not-json", "hello world"),
        ("truncated-json", '{"uri":"server://x"'),
        ("missing-uri", json.dumps({"ads": {"playing": False}})),
        ("uri-first (Android order)", json.dumps({"uri": SOURCE_URI,
                                                  "ads": {"playing": False}},
                                                 separators=(",", ":"))),
        ("spaced-separators", json.dumps({"ads": {"playing": False},
                                          "uri": SOURCE_URI})),
        ("bogus-uri", json.dumps({"ads": {"playing": False}, "uri": "not-a-uri"})),
        ("oversized-uri", json.dumps({"ads": {"playing": False},
                                      "uri": "x" * 400})),
    ]:
        mark("v_" + label)
        a.send({"Set": {"file": {"name": payload}}})
        time.sleep(1.6)
        ra, rb = sets_since(a, "v_" + label), sets_since(b, "v_" + label)
        got_a = [n for _, m, _ in ra for n in inner_name(m)]
        got_b = [n for _, m, _ in rb for n in inner_name(m)]
        print("   %-26s -> sender echo: %-38s peer: %s"
              % (label, (got_a[0][:34] if got_a else "(none)"),
                 (got_b[0][:34] if got_b else "(none)")))

    # -- W4: Set{ready} ----------------------------------------------------
    rule("W4  Set{ready} transitions")
    for label, body in [
        ("isReady false, manual false", {"isReady": False, "manuallyInitiated": False}),
        ("isReady true,  manual false", {"isReady": True, "manuallyInitiated": False}),
        ("isReady true,  manual TRUE", {"isReady": True, "manuallyInitiated": True}),
        ("isReady null", {"isReady": None, "manuallyInitiated": False}),
        ("no manuallyInitiated key", {"isReady": True}),
    ]:
        mark("r_" + label)
        a.send({"Set": {"ready": body}})
        time.sleep(1.6)
        ra, rb = sets_since(a, "r_" + label), sets_since(b, "r_" + label)
        ja = [json.dumps(m["Set"]) for _, m, _ in ra if "ready" in m.get("Set", {})]
        jb = [json.dumps(m["Set"]) for _, m, _ in rb if "ready" in m.get("Set", {})]
        print("   %-32s -> sender: %-58s peer: %s"
              % (label, ja[0][:56] if ja else "(none)", jb[0][:56] if jb else "(none)"))

    mark("list2")
    a.send({"List": {}})
    time.sleep(1.5)
    print("   roster after ready sweep:")
    for n, v in roster(a).items():
        print("      %-12s isReady=%-5s file=%s"
              % (n, v.get("isReady"), bool(v.get("file"))))

    # -- W5: playlist messages ---------------------------------------------
    rule("W5  Set{playlistChange} / Set{playlistIndex} -- real Android shapes")
    for label, msg in [
        ("playlistChange files:[]", {"Set": {"playlistChange": {"user": None, "files": []}}}),
        ("playlistIndex index:null", {"Set": {"playlistIndex": {"user": None, "index": None}}}),
        ("playlistChange user:null files:[{name:'x'}]",
         {"Set": {"playlistChange": {"user": None,
                                     "files": [{"name": json.dumps(
                                         {"ads": {"playing": False}, "uri": SOURCE_URI},
                                         separators=(",", ":"))}]}}}),
        ("playlistIndex index:0", {"Set": {"playlistIndex": {"user": None, "index": 0}}}),
        ("playlistIndex index:1", {"Set": {"playlistIndex": {"user": None, "index": 1}}}),
    ]:
        mark("p_" + label)
        a.send(msg)
        time.sleep(1.8)
        ra, rb = sets_since(a, "p_" + label), sets_since(b, "p_" + label)
        key = list(msg["Set"].keys())[0]
        ja = [json.dumps(m["Set"][key]) for _, m, _ in ra if key in m.get("Set", {})]
        jb = [json.dumps(m["Set"][key]) for _, m, _ in rb if key in m.get("Set", {})]
        print("   %-40s -> sender: %-30s peer: %s"
              % (label, ja[0][:28] if ja else "(none)", jb[0][:28] if jb else "(none)"))

    mark("list3")
    a.send({"List": {}})
    time.sleep(1.5)
    print("   final roster:")
    for n, v in roster(a).items():
        print("      %-12s isReady=%-5s controller=%-5s position=%s features=%s"
              % (n, v.get("isReady"), v.get("controller"), v.get("position"),
                 json.dumps(v.get("features"))))

    rule("SUMMARY")
    print("   sent A=%d B=%d   errors A=%s B=%s" % (a.sent, b.sent, a.send_err, b.send_err))
    for c in (a, b):
        kinds = {}
        for _, m, _ in c.msgs:
            k = list(m.keys())[0]
            kinds[k] = kinds.get(k, 0) + 1
        print("   %s inbound: %s stopped=%s" % (c.tag, kinds, c.stop.is_set()))
    print("   room: %s" % ROOM)
    a.close(); b.close()


if __name__ == "__main__":
    main()