"""Replay a real captured Plex Web outbound frame stream into a throwaway relay room.

Answers one question: was the ~6s State stall caused by the *content* of the frames the
probe sends, or by something else (handshake, cadence, identity)?

If a verbatim replay of 131s of genuine frames survives, the frame content was always
right and the gap is elsewhere. If it dies, the content is wrong and the diff against
the capture says which field.

The capture has no direction marker, so we replay only frames a client could plausibly
have sent: Hello, Set.*, List, and State shapes carrying clientRtt (shape B). Shape A
never carries clientRtt and is the relay's own broadcast -- replaying it would make us
send frames no real client sends. See docs/watch-together.md 5.5.

Usage: replayprobe.py <host> <port> <capture.log> [seconds]
"""
import base64
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "pop-atl01.syncplay.plex.services"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7777
LOG = sys.argv[3] if len(sys.argv) > 3 else "safari-ws.log"
SECONDS = float(sys.argv[4]) if len(sys.argv) > 4 else 140.0

ROOM = "rp" + hashlib.sha1(os.urandom(8)).hexdigest()[:8]
IDENT = json.dumps({"userID": "1000001",
                    "deviceIdentifier": "replay-" + ROOM,
                    "deviceName": "Safari"},
                   separators=(",", ":"))


def load():
    """Return [(t, frame)] for frames a client could have sent."""
    out = []
    with open(LOG) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                msg = json.loads(parts[0])
            except ValueError:
                continue
            if "State" in msg:
                # shape B only: the relay's own broadcast never carries clientRtt
                if "clientRtt" not in msg["State"].get("ping", {}):
                    continue
            if "Hello" in msg:
                # skip the relay's Hello RESPONSE -- it carries realversion/motd/features,
                # which only the server ever sends. Replaying it back is talking to the
                # relay in its own voice.
                h = msg["Hello"]
                if "realversion" in h or "features" in h:
                    continue
            if "Set" in msg:
                # skip relay echoes of our own Set.ready: they carry a username field.
                # A client never sends username in Set.
                for sk, sv in msg["Set"].items():
                    if isinstance(sv, dict) and "username" in sv:
                        msg = None
                        break
                if msg is None:
                    continue
            out.append((float(parts[1]), msg))
    out.sort(key=lambda r: r[0])
    return out


def frame(payload, op=0x1):
    """Client->server frame. The payload MUST be masked with the 4-byte key."""
    b = payload.encode() if isinstance(payload, str) else payload
    n = len(b)
    if n < 126:
        hdr = bytes([0x80 | op, 0x80 | n])
    elif n < 1 << 16:
        hdr = bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
    else:
        hdr = bytes([0x80 | op, 0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    return hdr + mask + bytes(c ^ k for c, k in zip(b, mask * n))


class Replay:
    def __init__(self, host, port):
        raw = socket.create_connection((host, port), timeout=20)
        self.sock = ssl.create_default_context().wrap_socket(
            raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (host, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b"101" not in buf.split(b"\r\n")[0]:
            raise SystemExit("upgrade refused: %r" % buf.split(b"\r\n")[0])
        self.sock.settimeout(0.5)
        self.buf = b""
        self.rx = []           # (t, parsed) inbound
        self.rx_raw = []       # (t, frame) inbound, undecoded
        self.states = []       # (t, parsed) inbound State only
        self.dead = False      # relay hung up; stop touching the socket
        self.death = None      # (t, reason)
        self.pongs = 0         # WS pings we had to answer

    def send(self, obj):
        self.sock.sendall(frame(json.dumps(obj, separators=(",", ":"))))

    dead = False          # relay hung up; stop touching the socket

    def poll(self):
        if self.dead:
            return
        try:
            chunk = self.sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return
        except (ConnectionResetError, BrokenPipeError, OSError, ssl.SSLError) as exc:
            self.dead = True
            self.death = (time.monotonic(), "%s: %s" % (type(exc).__name__, exc))
            return
        if not chunk:
            self.dead = True
            self.death = (time.monotonic(), "relay sent EOF")
            return
        self.buf += chunk
        while len(self.buf) >= 2:
            b0, b1 = self.buf[0], self.buf[1]
            ln, off = b1 & 0x7F, 2
            if ln == 126:
                if len(self.buf) < 4:
                    return
                ln, off = struct.unpack("!H", self.buf[2:4])[0], 4
            elif ln == 127:
                if len(self.buf) < 10:
                    return
                ln, off = struct.unpack("!Q", self.buf[2:10])[0], 10
            if len(self.buf) < off + ln:
                return
            data, self.buf = self.buf[off:off + ln], self.buf[off + ln:]
            op = b0 & 0x0F
            if op == 0x9:
                # WS ping. A real client MUST answer with a pong or the relay drops us.
                self.pongs += 1
                try:
                    self.sock.sendall(frame(data, 0xA))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    self.dead = True
                    self.death = (time.monotonic(), "could not pong")
                return
            if op == 0x8:
                self.dead = True
                self.death = (time.monotonic(), "relay sent close frame")
                return
            if op in (0xA,):        # pong from the relay, nothing to do
                continue
            self.rx_raw.append((time.monotonic(), data))
            try:
                self.rx.append((time.monotonic(), json.loads(data)))
            except ValueError:
                continue
            if "State" in self.rx[-1][1]:
                self.states.append(self.rx[-1])

    def close(self):
        try:
            self.sock.sendall(frame("", 0x8))
            self.sock.close()
        except OSError:
            pass


def rewrite(msg):
    """Point the captured frames at our throwaway room and identity."""
    out = {}
    for k, v in msg.items():
        if k == "Hello":
            out[k] = {"room": {"name": ROOM}, "username": IDENT,
                      "version": v.get("version", "1.6.4")}
            continue
        if k == "Set":
            nv = {}
            for sk, sv in v.items():
                if sk in ("file", "user"):
                    nv[sk] = sv          # keep verbatim; content is irrelevant
                elif sk == "ready":
                    nv[sk] = {"isReady": sv.get("isReady"),
                              "manuallyInitiated": sv.get("manuallyInitiated")}
                elif sk in ("playlistChange", "playlistIndex"):
                    nv[sk] = sv
                else:
                    nv[sk] = sv
            out[k] = nv
            continue
        if k == "State":
            nv = {"ping": dict(v.get("ping", {})),
                  "playstate": dict(v.get("playstate", {})),
                  "ignoringOnTheFly": dict(v.get("ignoringOnTheFly",
                                                 {"client": 0, "server": 0}))}
            nv["playstate"]["setBy"] = None   # clients never set this
            out[k] = nv
            continue
        if k == "List":
            out[k] = {}
            continue
        out[k] = v
    return out


def main():
    seq = load()
    span = seq[-1][0] - seq[0][0] if seq else 0
    print("capture : %s" % LOG)
    print("replaying %d client-plausible frames spanning %.1fs" % (len(seq), span))
    print("room    : %s  (throwaway, cloud never told)" % ROOM)
    print("relay   : %s:%d\n" % (HOST, PORT))

    c = Replay(HOST, PORT)
    t0 = time.monotonic()
    base = seq[0][0]
    sent = 0
    try:
        for when, msg in seq:
            target = t0 + (when - base)
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            if time.monotonic() - t0 > SECONDS:
                print("\nstopping at %.0fs (capture exhausted)" % SECONDS)
                break
            try:
                c.send(rewrite(msg))
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                # The relay hung up on us. That is a result, not a crash: report how far
                # the replay got and what we last heard, then stop.
                print("\n!! relay closed the connection after %.1fs / %d frames sent"
                      % (time.monotonic() - t0, sent))
                print("   %s: %s" % (type(exc).__name__, exc))
                c.dead = True
                c.death = (time.monotonic(), "%s: %s" % (type(exc).__name__, exc))
                break
            sent += 1
            c.poll()
            if c.dead:
                print("\n!! relay hung up at t=%.1fs (%s) after %d frames sent"
                      % (c.death[0] - t0, c.death[1], sent))
                break
        # stay connected to the end so we can see whether State flow survived
        while time.monotonic() - t0 < SECONDS + 5 and not c.dead:
            c.poll()
            time.sleep(0.1)
    finally:
        c.close()

    print("\nsent %d frames over %.0fs" % (sent, time.monotonic() - t0))
    verdict(c, t0)


SPAN = 131.2   # real-client capture length; the bar a conforming client clears


def verdict(c, t0):
    times = [t - t0 for t, _ in c.states]
    print("inbound States: %d" % len(times))
    if not times:
        print("VERDICT: relay sent NO State at all -- rejected or never registered")
    else:
        last = times[-1]
        print("first t=%.1f  last t=%.1f  span=%.1f" % (times[0], last, last - times[0]))
        buckets = {}
        for t in times:
            buckets[int(t // 10)] = buckets.get(int(t // 10), 0) + 1
        print("States per 10s bucket:")
        for k in sorted(buckets):
            print("   %3ds-%3ds  %2d %s" % (k * 10, k * 10 + 9, buckets[k],
                                            "#" * buckets[k]))
        if last >= SPAN - 5:
            print("\nVERDICT: SURVIVED the full %.0fs." % SPAN)
            print("  => frame CONTENT was never the problem. The gap is the")
            print("     handshake, the cadence, or the identity -- not the State.")
        else:
            print("\nVERDICT: STALLED at t=%.1fs (real clients run %.0fs+)."
                  % (last, SPAN))
            print("  => frame CONTENT is wrong. Diff against the capture:")
            print("     docs/probes/framediff.py")
    print("WS pings answered: %d" % c.pongs)
    if c.death:
        print("\nconnection died at t=%.1fs: %s" % (c.death[0] - t0, c.death[1]))
    if c.rx_raw:
        print("\nlast 3 inbound frames verbatim:")
        for t, data in c.rx_raw[-3:]:
            print("   t=%6.1f %s" % (t - t0, data[:190]))


if __name__ == "__main__":
    main()