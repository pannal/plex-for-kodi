"""Bisect the ~6s State stall by starting from a stalling handshake and adding one
real-client behaviour at a time until the stall goes away.

The replay probe proved frame CONTENT is fine (147 verbatim frames, steady 1 Hz for
131s). The probe stalls at ~6s. So the difference is in what happens AROUND the State
frames -- the handshake, or the order things are sent in.

Every case runs concurrently against its own throwaway relay room, so the whole
bisect takes about as long as its slowest case, not the sum of all of them.

Usage: handshakebisect.py [host] [port] [seconds]
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

HOST = sys.argv[1] if len(sys.argv) > 1 else "pop-atl01.syncplay.plex.services"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7777
SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0

FILE_NAME = json.dumps(
    {"ads": {"playing": False},
     "uri": ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
             "com.plexapp.plugins.library/library/metadata/227116")},
    separators=(",", ":"))


def frame(payload, op=0x1):
    """Client->server frame. MASK bit set AND payload XORed with the key."""
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


class Session:
    """One client, one throwaway room, echoing State at 1 Hz."""

    def __init__(self, room):
        self.room = room
        self.ident = json.dumps(
            {"userID": "1000001", "deviceIdentifier": "hb-" + room,
             "deviceName": "Safari"}, separators=(",", ":"))
        raw = socket.create_connection((HOST, PORT), timeout=20)
        self.sock = ssl.create_default_context().wrap_socket(
            raw, server_hostname=HOST)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (HOST, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.sock.settimeout(0.2)
        self.states = []       # (t, parsed State)
        self.rx_times = []     # t of every inbound frame
        self.pongs = 0
        self.dead = False
        self.send({"Hello": {"room": {"name": room}, "username": self.ident,
                             "version": "1.6.4"}})

    def send(self, obj):
        if self.dead:
            return
        try:
            self.sock.sendall(frame(json.dumps(obj, separators=(",", ":"))))
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.dead = True

    def poll(self):
        if self.dead:
            return
        try:
            chunk = self.sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return
        except (ConnectionResetError, BrokenPipeError, OSError, ssl.SSLError):
            self.dead = True
            return
        if not chunk:
            self.dead = True
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
            if op == 0x9:                       # ping -> must pong
                self.pongs += 1
                try:
                    self.sock.sendall(frame(data, 0xA))
                except OSError:
                    self.dead = True
                continue
            if op in (0x8,):
                self.dead = True
                continue
            if op == 0xA:
                continue
            now = time.monotonic()
            self.rx_times.append(now)
            try:
                msg = json.loads(data)
            except ValueError:
                continue
            if "State" in msg:
                self.states.append((now, msg["State"]))

    def echo(self, position, paused=False, do_seek=False, ignore=0):
        self.send({"State": {
            "ping": {"clientLatencyCalculation": time.monotonic(),
                     "clientRtt": 0.18, "latencyCalculation": time.time(),
                     "serverRtt": 0.0},
            "playstate": {"doSeek": do_seek, "paused": paused,
                          "position": int(position), "setBy": None},
            "ignoringOnTheFly": {"client": ignore, "server": 0}}})

    def close(self):
        try:
            self.sock.sendall(frame("", 0x8))
            self.sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------ the cases

def c_baseline(s):
    """What twoclientprobe does today: Hello, file, ready(true, manual), then echo."""
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})


def c_manual_false(s):
    """Real client sends manuallyInitiated: false, not true."""
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_false_first(s):
    """Real client sends isReady:false, then true ~4s later."""
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"ready": {"isReady": False}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_null_ready(s):
    """Real client's first Set.ready has isReady:null (still filling in)."""
    s.send({"Set": {"ready": {"isReady": None, "manuallyInitiated": False}}})
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"ready": {"isReady": False}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_user(s):
    """Real client announces itself with Set.user carrying room + file."""
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"user": {s.ident: {"room": {"name": s.room},
                                        "file": {"name": FILE_NAME}}}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_playlist(s):
    """Real client sends the playlistChange / playlistIndex pair."""
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"playlistChange": {"user": s.ident, "files": []}}})
    s.send({"Set": {"playlistIndex": {"user": s.ident, "index": None}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_full(s):
    """Everything the real client does, in the capture's order."""
    s.send({"Set": {"ready": {"isReady": None, "manuallyInitiated": False}}})
    s.send({"Set": {"playlistChange": {"user": s.ident, "files": []}}})
    s.send({"Set": {"playlistIndex": {"user": s.ident, "index": None}}})
    s.send({"List": {}})
    s.send({"Set": {"file": {"name": FILE_NAME}}})
    s.send({"Set": {"ready": {"isReady": False}}})
    s.send({"Set": {"user": {s.ident: {"room": {"name": s.room},
                                        "file": {"name": FILE_NAME}}}}})
    s.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}})


def c_no_ready(s):
    """Send the file, never claim ready. Does readiness gate the stream?"""
    s.send({"Set": {"file": {"name": FILE_NAME}}})


CASES = [
    ("baseline", c_baseline),
    ("manual:false", c_manual_false),
    ("false-then-true", c_false_first),
    ("null-ready-first", c_null_ready),
    ("+Set.user", c_user),
    ("+playlist pair", c_playlist),
    ("full (capture order)", c_full),
    ("no ready at all", c_no_ready),
]


def run_one(name, fn, results):
    room = "hb" + os.urandom(4).hex()
    try:
        s = Session(room)
    except Exception as exc:
        results[name] = ("CONNECT-FAIL", repr(exc), 0)
        return
    t0 = time.monotonic()
    try:
        fn(s)
        next_tick = time.monotonic() + 1.0
        while time.monotonic() - t0 < SECONDS:
            now = time.monotonic()
            if now >= next_tick:
                s.echo(position=now - t0, paused=False)
                next_tick += 1.0
            s.poll()
            time.sleep(0.05)
        times = [t - t0 for t, _ in s.states]
        last = times[-1] if times else -1.0
        # bucket per 5s so a stall is obvious
        buckets = {}
        for t in times:
            buckets[int(t // 5)] = buckets.get(int(t // 5), 0) + 1
        spread = " ".join(str(buckets.get(i, 0)) for i in range(int(SECONDS // 5)))
        results[name] = ("OK" if last >= SECONDS - 4 else "STALL",
                         "%2d States, last t=%5.1fs, pongs=%d  per5s=[%s]"
                         % (len(times), last, s.pongs, spread),
                         len(times))
    finally:
        s.close()


def main():
    print("bisecting %d handshakes concurrently, %.0fs each" % (len(CASES), SECONDS))
    print("relay %s:%d, each case gets its own throwaway room\n" % (HOST, PORT))
    results = {}
    threads = [threading.Thread(target=run_one, args=(n, f, results), daemon=True)
               for n, f in CASES]
    for t in threads:
        t.start()
    for t in threads:
        t.join(SECONDS + 25)
    print("%-22s %-6s %s" % ("case", "result", "detail"))
    print("-" * 78)
    for name, _ in CASES:
        verdict, detail, _n = results.get(name, ("TIMEOUT", "no result", 0))
        print("%-22s %-6s %s" % (name, verdict, detail))
    ok = [n for n, _ in CASES if results.get(n, ("",))[0] == "OK"]
    print("\nsurvived: %s" % (", ".join(ok) if ok else "NONE"))


if __name__ == "__main__":
    main()