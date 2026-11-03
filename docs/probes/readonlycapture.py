#!/usr/bin/env python3
"""READ-ONLY capture of a live Watch Together session.

Sends exactly: one Hello, one List, and pong for every server ping.
NEVER sends Set or State. Safe to point at a real room.
"""
import base64, json, os, socket, ssl, struct, sys, time, uuid

HOST, PORT, ROOM = sys.argv[1], int(sys.argv[2]), sys.argv[3]
USERID = sys.argv[4] if len(sys.argv) > 4 else "0"
DURATION = float(sys.argv[5]) if len(sys.argv) > 5 else 35.0
T0 = time.time()


def frame(p, op=0x1):
    b = p.encode() if isinstance(p, str) else p
    n = len(b)
    h = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else
        bytes([0x80 | 126]) + struct.pack(">H", n) if n < 1 << 16 else
        bytes([0x80 | 127]) + struct.pack(">Q", n))
    m = os.urandom(4)
    return h + m + bytes(c ^ k for c, k in zip(b, m * n))


s = socket.create_connection((HOST, PORT), timeout=20)
s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
print("# TLS", s.version(), s.getpeercert().get("subjectAltName"))
s.sendall(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
           % (HOST, base64.b64encode(os.urandom(16)).decode())).encode())
buf = b""
while b"\r\n\r\n" not in buf:
    buf += s.recv(4096)
hdr, buf = buf.split(b"\r\n\r\n", 1)
print("#", hdr.decode().replace("\r\n", " | "))

# Deliberately NOT impersonating the real clients: distinct probe identity.
me = json.dumps({"deviceIdentifier": "probecapture-" + uuid.uuid4().hex[:12],
                 "deviceName": "probe", "userID": USERID}, separators=(",", ":"))
print("# my identity (%d bytes): %s" % (len(me), me))
s.sendall(frame(json.dumps({"Hello": {"room": {"name": ROOM}, "username": me,
                                       "version": "1.6.4"}})))
sent_list = False
state_count = 0


def need(n):
    global buf
    while len(buf) < n:
        c = s.recv(65536)
        if not c:
            raise EOFError
        buf += c


end = time.time() + DURATION
s.settimeout(2.0)
while time.time() < end:
    try:
        need(2)
    except (socket.timeout, TimeoutError):
        continue
    except EOFError:
        print("# server closed the socket"); break
    b0, b1 = buf[0], buf[1]
    op, masked, ln = b0 & 0xF, b1 & 0x80, b1 & 0x7F
    off = 2
    if ln == 126: need(4); ln = struct.unpack(">H", buf[2:4])[0]; off = 4
    elif ln == 127: need(10); ln = struct.unpack(">Q", buf[2:10])[0]; off = 10
    if masked: need(off + 4); off += 4
    need(off + ln)
    d, buf = buf[off:off + ln], buf[off + ln:]
    if op == 0x9:
        s.sendall(frame(d, 0xA))
        print("[%5.1fs] << PING -> ponged" % (time.time() - T0))
    elif op == 0x8:
        print("[%5.1fs] << CLOSE %d %r" % (time.time() - T0,
              int.from_bytes(d[:2], "big"), d[2:200])); break
    elif op in (0x1, 0x2):
        t = time.time() - T0
        m = json.loads(d)
        for k in m:
            if k == "State":
                state_count += 1
                if state_count <= 4 or state_count % 10 == 0:
                    print("[%5.1fs] << State  %s" % (t, json.dumps(m["State"], sort_keys=True)))
            else:
                print("[%5.1fs] << %s" % (t, json.dumps({k: m[k]}, sort_keys=True)))
        if not sent_list:
            sent_list = True
            s.sendall(frame(json.dumps({"List": {}})))
            print("[%5.1fs] >> List (read-only request)" % t)

try:
    s.sendall(frame(b"", 0x8))
except Exception:
    pass
s.close()
print("# captured %d State messages over %.0fs; closed cleanly" % (state_count, DURATION))