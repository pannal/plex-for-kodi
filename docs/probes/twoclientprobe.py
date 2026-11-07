#!/usr/bin/env python3
"""Two-client Watch Together conformance probe  (v2).

Both clients run a realistic 1 Hz State echo, because that is what keeps the relay
from evicting them (§5.6 — a client that only reads is dropped in ~14 s). One client
is the *driver* (the test mutates its playstate); the other *applies* what it sees and
echoes its applied position, which is what a real client does.

Answers, with two real implementations talking:
  Q1  does anyone ever become controller:true?
  Q2  does the observer see the driver's position, and is it echoed or interpolated?
  Q3  does a pause by the driver propagate?
  Q4  does a seek propagate, and what does doSeek mean / how long does it last?
  Q5  what does ignoringOnTheFly.client:1 do?
  Q6  what happens to the room when the driver disconnects?
  Q7  does setBy transfer to the remaining client?
  Q8  does setBy flip-flop when both clients echo?

Only ever talks to its own throwaway room name. Usage: python3 twoclientprobe2.py [host] [port]
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


def log(*a):
    with LOCK:
        print("[%6.2fs]" % (time.monotonic() - T0), *a, flush=True)


def rule(t):
    with LOCK:
        print("\n" + "=" * 76 + "\n== " + t + "\n" + "=" * 76, flush=True)


def ident(raw):
    """Relay appends '_' per collision; strip or json.loads raises (§5.1)."""
    if not raw:
        return "<none>"
    try:
        return json.loads(raw.rstrip("_")).get("deviceName", "?")
    except ValueError:
        return "<unparseable %r>" % raw[-30:]


def is_self(raw, identity):
    """True when setBy resolves to the identity WE sent (§5.5).

    The relay echoes your own State back with setBy filled in as you, so a client that
    does not drop it applies its own stale echo and fights itself -- the observer in the
    two-account run sat pinned at pos=0 while its driver was at 100+.

    Matched as a subset on str() so it survives a relay that reorders keys, adds fields,
    or round-trips a numeric id as int instead of str. Full dict equality would silently
    stop self-ignoring on any of those.
    """
    if not raw:
        return False
    try:
        theirs, mine = json.loads(raw.rstrip("_")), json.loads(identity)
    except ValueError:
        return False
    if not isinstance(theirs, dict):
        return False
    return all(k in theirs and str(theirs[k]) == str(v) for k, v in mine.items())


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
    def __init__(self, label, user_id, device, driver):
        super().__init__(daemon=True)
        self.label, self.driver = label, driver
        self.identity = json.dumps({"userID": str(user_id), "deviceIdentifier": device,
                                    "deviceName": label}, separators=(",", ":"))
        self.local = {"position": 0.0, "paused": True, "doSeek": False}
        self.applied = {"position": 0.0, "paused": True, "doSeek": False}
        self.ignore = 0
        self.server_rtt = 0.0        # echoed back from the relay
        self.client_rtt = 0.0        # measured, warm after the first reply
        self.relay_ignore = 0        # ignoringOnTheFly.server last sent BY THE RELAY
        self._ping_sent_at = None    # monotonic stamp of the last outbound ping
        self.stop = threading.Event()
        self.wlock = threading.Lock()  # serialises sends; see send()
        self.sent = 0
        self.send_err = None
        self.msgs = []                       # (t, parsed)
        self.raw_setby = []                  # every setBy string seen, in order
        self.self_echo = 0                   # inbound frames we self-ignored (§5.5)
        s = socket.create_connection((HOST, PORT), timeout=20)
        self.sock = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
        self.sock.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                           "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n"
                           % (HOST, base64.b64encode(os.urandom(16)).decode())).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.status = buf.split(b"\r\n\r\n", 1)[0].decode().splitlines()[0]
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.send({"Hello": {"room": {"name": ROOM}, "username": self.identity,
                             "version": VERSION}})

    def send(self, o):
        # sendall() is NOT thread-safe, and two threads write here: the keepalive thread
        # sends State every 1s while the main thread sends announce()/List. Interleaved
        # writes on a TLS socket corrupt the frame stream and the relay silently drops the
        # session -- which showed up as one client receiving zero inbound frames. Observed
        # 2 runs in 5 before this lock, 0 in 5 after.
        with self.wlock:
            try:
                self.sock.sendall(frame(json.dumps(o)))
                self.sent += 1
            except OSError as e:
                self.send_err = repr(e)
                log("  %s SEND ERROR %r" % (self.label, e))
                self.stop.set()

    def announce(self):
        self.send({"Set": {"file": {"name": json.dumps(
            {"ads": {"playing": False}, "uri": SOURCE_URI}, separators=(",", ":"))}}})
        self.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})

    def set_local(self, position=None, paused=None, do_seek=None, ignore=None):
        if position is not None:
            self.local["position"] = position
        if paused is not None:
            self.local["paused"] = paused
        if do_seek is not None:
            self.local["doSeek"] = do_seek
        if ignore is not None:
            self.ignore = ignore

    def echo(self):
        # ONE frame per tick, ~1 Hz.
        #
        # The capture contains two ~equally-frequent State shapes, and the obvious reading
        # -- "clients send both, ~10 ms apart" -- is WRONG. The two shapes are two
        # DIRECTIONS, split cleanly by clientRtt:
        #   relay->you (130 frames): clientRtt absent 130/130, serverRtt 130/130,
        #                             setBy names the driver, position often a float
        #   you->relay (138 frames): clientRtt present, setBy null, position an int
        # Web Inspector WS logs do not tag direction, which is how the two-role reading
        # crept in. Splitting on clientRtt is unambiguous and needs no assumption.
        #
        # position is an INT on the wire -- 116/116 playing and 15/15 paused client-side.
        # The floats are the relay's own extrapolation, not the client's.
        src = self.local if self.driver else self.applied
        now_mono = time.monotonic()
        self._ping_sent_at = now_mono
        self.send({"State": {
            "ping": {"clientLatencyCalculation": now_mono,
                     "clientRtt": self.client_rtt,
                     "latencyCalculation": time.time(),
                     "serverRtt": self.server_rtt},
            "playstate": {"doSeek": src["doSeek"], "paused": src["paused"],
                          "position": int(src["position"]), "setBy": None},
            # server MUST mirror whatever the relay last told us. The relay sets
            # ignoringOnTheFly.server=1 once it has applied our State; a real client
            # echoes that counter back on the next tick. Hardcoding 0 here makes the
            # relay see us talking over a message it already took, and it stops the
            # 1 Hz State stream after ~6s. Verified: mirroring it survives 75s+.
            "ignoringOnTheFly": {"client": self.ignore,
                                 "server": self.relay_ignore}}})

        if not self.driver:
            # a real client re-announces the seek it just applied, then clears the flag
            self.applied["doSeek"] = False

    def keepalive(self):
        while not self.stop.is_set():
            self.echo()
            self.stop.wait(1.0)

    def close(self):
        self.stop.set()
        try:
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
        ka = threading.Thread(target=self.keepalive, daemon=True)
        ka.start()
        while not self.stop.is_set():
            try:
                self._need(2)
            except (socket.timeout, TimeoutError):
                continue
            except (EOFError, OSError):
                self.stop.set()
                log("  %s socket closed by peer" % self.label)
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
                with self.wlock:            # pong shares the socket with send()
                    self.sock.sendall(frame(data, 0xA))
                continue
            if op == 0x8:
                self.stop.set()
                log("  %s got CLOSE %d %r" % (self.label, int.from_bytes(data[:2], "big"),
                                               data[2:120]))
                return
            if op not in (0x1, 0x2):
                continue
            try:
                m = json.loads(data)
            except ValueError:
                continue
            self.msgs.append((time.monotonic(), m))
            if "State" in m:
                ping = m["State"].get("ping", {})
                ig = m["State"].get("ignoringOnTheFly", {}).get("server")
                ps = m["State"].get("playstate", {})
                # mirror the relay's suppression counter straight back at it -- the one
                # field that decides whether the relay keeps relaying to us at all
                if ig:
                    self.relay_ignore = int(ig)
                # echo back whatever serverRtt the relay reported
                if isinstance(ping.get("serverRtt"), (int, float)):
                    self.server_rtt = ping["serverRtt"]
                # measure our own RTT off the round-tripped clientLatencyCalculation
                lc = ping.get("clientLatencyCalculation")
                if isinstance(lc, (int, float)) and self._ping_sent_at is not None:
                    self.client_rtt = round(time.monotonic() - self._ping_sent_at, 6)
                self.raw_setby.append(ps.get("setBy"))
                if is_self(ps.get("setBy"), self.identity):
                    # your own echo: count it, but never apply it (§5.5)
                    self.self_echo += 1
                elif not self.driver:
                    # Apply every non-self frame. This used to be gated on `not ig`,
                    # i.e. dropped while the relay's ignoringOnTheFly.server was set --
                    # which is not a "this is mine" signal, so it silently discarded
                    # legitimate remote frames and left `applied` stale at 0.
                    # Self-identity is the only correct filter; `ig` is for SENDING.
                    for k in ("position", "paused"):
                        if ps.get(k) is not None:
                            self.applied[k] = ps[k]
                    if ps.get("doSeek"):
                        self.applied["doSeek"] = True


def snap(c, since=0.0):
    out = []
    for t, m in c.msgs:
        if t >= since and "State" in m:
            ps = m["State"].get("playstate", {})
            out.append((ps.get("paused"), ps.get("position"), ps.get("doSeek"),
                        ident(ps.get("setBy"))))
    return out


def show(tag, rows):
    if not rows:
        print("   %s: (nothing observed)" % tag)
    for i, (p, pos, ds, sb) in enumerate(rows):
        print("   %s #%-2d paused=%-5s pos=%-10s doSeek=%-5s setBy=%s"
              % (tag, i, p, round(pos, 3) if isinstance(pos, float) else pos, ds, sb))


def roster(c):
    last = None
    for _, m in c.msgs:
        if "List" in m:
            last = m
    if not last:
        return {}
    return {ident(k): v for k, v in last.get("List", {}).get(ROOM, {}).items()}


# ----------------------------------------------------------------- main


def main():
    rule("SETUP")
    print("room    : %s  (throwaway, cloud never told)" % ROOM)
    print("relay   : %s:%d" % (HOST, PORT))
    RUN = uuid.uuid4().hex[:8]
    a = Client("BRAVIA VH1", 1000003, "probeA-" + RUN, driver=True)
    b = Client("Safari", 1000001, "probeB-" + RUN, driver=False)
    for c in (a, b):
        c.start()
    time.sleep(0.8)
    a.announce(); b.announce()
    time.sleep(1.5)
    print("both echoing State at 1 Hz (required — see Q-note below)")

    rule("Q1  controller flag with two live clients")
    time.sleep(2)
    a.send({"List": {}})
    time.sleep(1.2)
    for name, v in roster(a).items():
        print("   %-12s controller=%-5s isReady=%-5s position=%s"
              % (name, v.get("controller"), v.get("isReady"), v.get("position")))

    rule("Q2  A drives 100 -> 104 playing; does B see it?")
    t = time.monotonic()
    for i in range(6):
        a.set_local(position=100.0 + i, paused=False, do_seek=False)
        time.sleep(1.0)
    time.sleep(0.5)
    show("B", snap(b, t))
    print("   roster: %s" % {k: (v.get("controller"), v.get("position"))
                            for k, v in roster(a).items()})

    rule("Q3  A pauses at 106 -> does B see paused:true?")
    t = time.monotonic()
    a.set_local(position=106.0, paused=True)
    time.sleep(2.5)
    show("B", snap(b, t))

    rule("Q4  A SEEKS to 900 with doSeek:true, then clears it")
    t = time.monotonic()
    a.set_local(position=900.0, do_seek=True)
    time.sleep(1.6)
    show("B (seek tick)", snap(b, t))
    t2 = time.monotonic()
    a.set_local(do_seek=False)
    time.sleep(2.0)
    show("B (after doSeek cleared)", snap(b, t2))

    rule("Q5  A sends position 5000 with ignoringOnTheFly.client=1")
    t = time.monotonic()
    a.set_local(position=5000.0, ignore=1)
    time.sleep(2.5)
    rows = snap(b, t)
    show("B", rows)
    print("   verdict: propagated? %s" % ("YES" if rows and rows[-1][1] and rows[-1][1] > 4000
                                          else "NO — relay dropped it"))
    a.set_local(ignore=0)

    rule("Q6  A disconnects")
    t = time.monotonic()
    a.close()
    time.sleep(4)
    show("B", snap(b, t))
    for tt, m in b.msgs:
        if tt >= t and "Set" in m:
            print("   Set after leave: %s" % json.dumps(m["Set"])[:200])

    rule("Q7  B drives alone -> setBy should become B")
    t = time.monotonic()
    b.driver = True
    for i in range(4):
        b.set_local(position=200.0 + i * 2.0, paused=False)
        time.sleep(1.0)
    show("B", snap(b, t))

    rule("RAW TIMELINE")
    for c in (a, b):
        print("\n--- %s inbound (%d) ---" % (c.label, len(c.msgs)))
        t0 = c.msgs[0][0] if c.msgs else 0
        for t, m in c.msgs:
            k = list(m.keys())[0]
            extra = ""
            if k == "State":
                ps = m["State"].get("playstate", {})
                extra = "paused=%s pos=%s doSeek=%s setBy=%s" % (
                    ps.get("paused"), round(ps.get("position", 0), 2) if isinstance(ps.get("position"), float) else ps.get("position"),
                    ps.get("doSeek"), ident(ps.get("setBy")))
            elif k == "Set":
                kk = list(m["Set"].keys())
                v = m["Set"][kk[0]]
                if isinstance(v, dict) and "event" in v:
                    extra = "event=%s key=%s" % (v["event"], ident(list(v.keys())[0]) if len(v) > 1 else "")
                else:
                    extra = json.dumps(v)[:110]
            elif k == "List":
                extra = "%d users" % len(m["List"].get(ROOM, {}))
            print("   t=%6.2f  %-8s %s" % (t - t0, k, extra))

    rule("SUMMARY")
    print("   msgs received: A=%d  B=%d" % (len(a.msgs), len(b.msgs)))
    print("   msgs sent:     A=%d  B=%d" % (a.sent, b.sent))
    print("   send errors:   A=%s  B=%s" % (a.send_err, b.send_err))
    for c in (a, b):
        kinds = {}
        for _, m in c.msgs:
            kinds[list(m.keys())[0]] = kinds.get(list(m.keys())[0], 0) + 1
        print("   %s inbound breakdown: %s   stopped=%s" % (c.label, kinds, c.stop.is_set()))
    print("   distinct setBy values B saw, in order:")
    seq = []
    for s in b.raw_setby:
        n = ident(s)
        if not seq or seq[-1][0] != n:
            seq.append([n, 1])
        else:
            seq[-1][1] += 1
    print("     " + "  ->  ".join("%s x%d" % (n, c) for n, c in seq))
    for c in (a, b):
        print("   %s self-ignored own echo: %d  applied position=%s"
              % (c.label, c.self_echo, c.applied["position"]))
    b.close()
    print("\n   room name: %s" % ROOM)


if __name__ == "__main__":
    main()
