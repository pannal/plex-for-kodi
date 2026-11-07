#!/usr/bin/env python3
"""What IS ping.serverRtt?  (docs/watch-together.md §5.5, item 21)

The field is described as "relay-defined, do not compensate on it" because an earlier
reading -- serverRtt == serverNow - clientLatencyCalculation -- was retracted. That
reading named the wrong field. A client sends BOTH:

    ping.clientLatencyCalculation   monotonic seconds   (performance.now()/1000)
    ping.latencyCalculation         unix epoch seconds  (relay's own clock)

Hypothesis H:  serverRtt == relay's latencyCalculation - the latencyCalculation the
CLIENT sent. i.e. it is the relay measuring how stale the frame it just applied was.

Every existing observation fits H:
    real session, client stamps fresh epoch, relay rebroadcast ~0.15s later -> ~0.10-0.25
    verbatim replay of frames captured hours earlier                  -> ~50510 (14h)
    frames before the client ever sent a latencyCalculation           -> 0

If H holds it is load-bearing: §6.1 reads serverRtt for skew compensation, so a client
that sends a stale latencyCalculation would poison it for every peer.

Test: two conforming clients in a throwaway room. A is driven through a sweep of
latencyCalculation values, B is the observer. For each phase we log what BOTH clients
see, which separates "relay stamps it from the frame it applied" (A-derived) from
"relay stamps it from each client's own last frame" (B-derived).

Usage: python3 rttprobe.py [host] [port]
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

# label -> value A puts in ping.latencyCalculation. None means omit the key entirely.
# "mono" means send monotonic instead of epoch.
PHASES = [
    ("fresh-epoch",      "epoch"),
    ("epoch-minus-3600", "epoch-3600"),
    ("epoch-plus-3600",  "epoch+3600"),
    ("monotonic",        "mono"),
    ("zero",             "zero"),
    ("omitted",          None),
    ("fresh-epoch-again", "epoch"),
]

ROWS = []          # (phase, label, t_rel, server_rtt, relay_lc, applied_lc)
SENT = []          # (t_rel, latencyCalculation value actually put on the wire)


def log(*a):
    with LOCK:
        print("[%6.2fs]" % (time.monotonic() - T0), *a, flush=True)


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


class Client(threading.Thread):
    """Minimal conforming client. ONE State per tick, mirrors ignoringOnTheFly.server
    (§5.9 -- hardcoding 0 gets you muted in ~6s), always sends both suppression
    counters, sends setBy null and an int position (§5.5)."""

    def __init__(self, tag, label, user_id, device):
        super().__init__(daemon=True)
        self.tag = tag              # 'A' = the one we manipulate; 'B' = observer
        self.label = label
        self.identity = json.dumps({"userID": str(user_id), "deviceIdentifier": device,
                                    "deviceName": label}, separators=(",", ":"))
        self.position, self.paused = 0.0, True
        self.relay_ignore = 0        # ignoringOnTheFly.server, last set BY THE RELAY
        self.ignore = 0              # our own local-only suppression counter
        self.stop = threading.Event()
        self.wlock = threading.Lock()   # sendall() is not thread-safe (§5.9)
        self.sent = 0
        self.send_err = None
        self._sent_at = None
        self.latency_mode = "epoch"  # what this client puts in ping.latencyCalculation

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
        self.status = buf.split(b"\r\n\r\n", 1)[0].decode().splitlines()[0]
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.send({"Hello": {"room": {"name": ROOM}, "username": self.identity,
                             "version": VERSION}})
        self.send({"Set": {"file": {"name": json.dumps(
            {"ads": {"playing": False}, "uri": SOURCE_URI}, separators=(",", ":"))}}})
        self.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})

    def send(self, o):
        with self.wlock:
            try:
                self.sock.sendall(frame(json.dumps(o)))
                self.sent += 1
            except OSError as e:
                self.send_err = repr(e)
                self.stop.set()

    def echo(self):
        now_mono = time.monotonic()
        self._sent_at = now_mono
        ping = {"clientLatencyCalculation": now_mono, "clientRtt": 0, "serverRtt": 0}
        m = self.latency_mode
        if m == "epoch":
            ping["latencyCalculation"] = time.time()
        elif m == "epoch-3600":
            ping["latencyCalculation"] = time.time() - 3600
        elif m == "epoch+3600":
            ping["latencyCalculation"] = time.time() + 3600
        elif m == "mono":
            ping["latencyCalculation"] = now_mono
        elif m == "zero":
            ping["latencyCalculation"] = 0
        # m is None -> key omitted entirely
        self.send({"State": {"ping": ping,
                             "playstate": {"doSeek": False, "paused": self.paused,
                                           "position": int(self.position), "setBy": None},
                             "ignoringOnTheFly": {"client": self.ignore,
                                                  "server": self.relay_ignore}}})
        if self.tag == "A":
            SENT.append((time.monotonic() - T0, ping.get("latencyCalculation")))

    def keepalive(self):
        while not self.stop.is_set():
            self.echo()
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
            try:
                m = json.loads(data)
            except ValueError:
                continue
            if "State" not in m:
                continue
            st = m["State"]
            ping = st.get("ping", {})
            ig = (st.get("ignoringOnTheFly") or {}).get("server")
            if isinstance(ig, int):
                self.relay_ignore = ig
            ROWS.append({"t": time.monotonic() - T0, "who": self.tag,
                         "serverRtt": ping.get("serverRtt"),
                         "relay_lc": ping.get("latencyCalculation"),
                         "client_lc": ping.get("clientLatencyCalculation"),
                         "pos": st.get("playstate", {}).get("position")})


def main():
    rule("SETUP")
    run = uuid.uuid4().hex[:8]
    a = Client("A", "BRAVIA VH1", 1000003, "probeA-" + run)
    b = Client("B", "Safari", 1000001, "probeB-" + run)
    a.connect(); b.connect()
    a.start(); b.start()
    print("room  : %s  (throwaway, cloud never told)" % ROOM)
    print("relay : %s:%d" % (HOST, PORT))
    a.send({"List": {}})
    time.sleep(1.5)

    for label, mode in PHASES:
        rule("PHASE  A.latencyCalculation = %s" % label)
        a.latency_mode = mode
        t = time.monotonic()
        time.sleep(4.5)
        for r in ROWS:
            if r["t"] < t:
                continue
            sent_v = None
            for st_, sv in SENT:
                if st_ <= r["t"]:
                    sent_v = sv
            delta = None
            if isinstance(r["relay_lc"], (int, float)) and isinstance(sent_v, (int, float)):
                delta = r["relay_lc"] - sent_v
            print("   %s  serverRtt=%-22s relay_lc=%.3f  A_sent=%-12s relay_lc-A_sent=%s"
                  % (r["who"], r["serverRtt"], r["relay_lc"] or 0,
                     ("%.3f" % sent_v) if isinstance(sent_v, (int, float)) else str(sent_v),
                     ("%.3f" % delta) if isinstance(delta, float) else delta))

    rule("VERDICT  (compare: does serverRtt track relay_lc - A_sent ?)")
    print("   If serverRtt ~= relay_lc - A_sent for the whole sweep, serverRtt is the")
    print("   relay's staleness measurement of the frame it applied, and B seeing the")
    print("   same number proves it is A-derived (room-wide poisoning), not per-client.")
    print("   If B's number tracks B's own sends instead, it is per-client.")

    a.close(); b.close()
    print("\n   sent A=%d B=%d   err A=%s B=%s   room=%s"
          % (a.sent, b.sent, a.send_err, b.send_err, ROOM))


if __name__ == "__main__":
    main()