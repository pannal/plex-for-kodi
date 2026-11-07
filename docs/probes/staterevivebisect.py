#!/usr/bin/env python3
"""Bisect: what actually keeps the relay's State stream alive?

Matrix of (clients, who echoes, cadence). Measures how long each session keeps
receiving State and whether it gets the synthetic `left` eviction event.
"""
import base64, json, os, socket, ssl, struct, sys, threading, time, uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "pop-atl01.syncplay.plex.services"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7777
LOCK = threading.Lock()


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
    def __init__(self, room, name, echo, interval=1.0, advance=False):
        super().__init__(daemon=True)
        self.name, self.echo_on, self.interval, self.advance = name, echo, interval, advance
        self.identity = json.dumps({"userID": "1", "deviceIdentifier": "bisect-" + uuid.uuid4().hex[:10],
                                    "deviceName": name}, separators=(",", ":"))
        self.states = 0
        self.left_at = None
        self.t0 = time.monotonic()
        self.stop = threading.Event()
        self.pos = 0.0
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
        self.send({"Hello": {"room": {"name": room}, "username": self.identity,
                             "version": "1.6.4"}})
        self.send({"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})

    def send(self, o):
        try:
            self.sock.sendall(frame(json.dumps(o)))
        except OSError:
            self.stop.set()

    def run(self):
        ka = None
        if self.echo_on:
            ka = threading.Thread(target=self._ka, daemon=True)
        self.sock.settimeout(0.5)
        try:
            while not self.stop.is_set():
                try:
                    self._need(2)
                except (socket.timeout, TimeoutError):
                    if ka and not ka.is_alive():
                        ka = threading.Thread(target=self._ka, daemon=True); ka.start()
                    continue
                except (EOFError, OSError):
                    return
                b0, b1 = self.buf[0], self.buf[1]
                op, masked, ln = b0 & 0xF, b1 & 0x80, b1 & 0x7F
                off = 2
                if ln == 126: self._need(4); ln = struct.unpack(">H", self.buf[2:4])[0]; off = 4
                elif ln == 127: self._need(10); ln = struct.unpack(">Q", self.buf[2:10])[0]; off = 10
                if masked: self._need(off + 4); off += 4
                self._need(off + ln)
                d, self.buf = self.buf[off:off + ln], self.buf[off + ln:]
                if op == 0x9:
                    self.sock.sendall(frame(d, 0xA)); continue
                if op == 0x8:
                    self.stop.set(); return
                if op not in (0x1, 0x2):
                    continue
                try:
                    m = json.loads(d)
                except ValueError:
                    continue
                if "State" in m:
                    self.states += 1
                if "Set" in m and "user" in m["Set"]:
                    v = m["Set"]["user"]
                    for k, inner in v.items():
                        if isinstance(inner, dict) and inner.get("event", {}).get("left"):
                            if k.rstrip("_") == self.identity:
                                self.left_at = time.monotonic() - self.t0
        finally:
            self.stop.set()

    def _ka(self):
        while not self.stop.is_set():
            if self.advance:
                self.pos += self.interval
            self.send({"State": {"ping": {"clientLatencyCalculation": time.monotonic(),
                                          "clientRtt": 0.04, "serverRtt": 0.0,
                                          "latencyCalculation": time.time()},
                                 "playstate": {"doSeek": False, "paused": False,
                                               "position": self.pos}}})
            self.stop.wait(self.interval)

    def _need(self, n):
        while len(self.buf) < n:
            c = self.sock.recv(65536)
            if not c:
                raise EOFError
            self.buf += c

    def close(self):
        self.stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def run_case(label, n_clients, who_echoes, interval=1.0, advance=False, seconds=40):
    room = "wt" + uuid.uuid4().hex[:8]
    cs = []
    for i in range(n_clients):
        c = C(room, "c%d" % i, echo=(who_echoes == "all" or (who_echoes == "first" and i == 0)),
              interval=interval, advance=advance)
        c.start()
        cs.append(c)
        time.sleep(0.4)
    time.sleep(seconds)
    with LOCK:
        parts = []
        for i, c in enumerate(cs):
            parts.append("c%d: %3d States%s" % (i, c.states,
                                                ("  LEFT@%.1fs" % c.left_at) if c.left_at else ""))
        print("%-52s %s" % (label, "   ".join(parts)), flush=True)
    for c in cs:
        c.close()
    time.sleep(1.0)


print("each case: fresh throwaway room, %ds, measuring State count + eviction\n" % 40)
run_case("1 client,  echoes @1Hz, position advancing", 1, "all", 1.0, True)
run_case("1 client,  echoes @1Hz, position constant", 1, "all", 1.0, False)
run_case("1 client,  NO echo", 1, "none", 1.0, False)
run_case("2 clients, only c0 echoes @1Hz advancing", 2, "first", 1.0, True)
run_case("2 clients, only c0 echoes @1Hz constant", 2, "first", 1.0, False)
run_case("2 clients, BOTH echo @1Hz advancing", 2, "all", 1.0, True)
run_case("2 clients, BOTH echo @2Hz advancing", 2, "all", 2.0, True)
print("\ndone")