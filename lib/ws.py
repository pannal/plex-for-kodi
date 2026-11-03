# coding=utf-8
"""Minimal RFC6455 WebSocket client — generic, no Plex and no Kodi.

Just enough of the spec for the Syncplay relay (docs/watch-together.md §5):
text frames, ping/pong, close, client-side masking. No fragmentation, no
extensions, no compression — the relay uses none of them.
"""

from __future__ import absolute_import

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading


class HandshakeError(Exception):
    pass


class ProtocolError(Exception):
    pass


MAX_FRAME = 1 << 20


def encode_frame(payload, opcode=0x1):
    """Build a client->server frame (always masked, as the RFC requires)."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    n = len(data)
    if n < 126:
        header = bytes([0x80 | opcode, 0x80 | n])
    elif n < 1 << 16:
        header = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
    else:
        header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    return header + mask + bytes(c ^ k for c, k in zip(data, mask * n))


class FrameDecoder(object):
    """Incremental frame decoder: feed() bytes, take (opcode, payload) tuples.

    Handles masked and unmasked frames — we always mask, the relay never does.
    """

    def __init__(self):
        self._buf = b""

    def feed(self, data):
        self._buf += data
        out = []
        while True:
            frame = self._one()
            if frame is None:
                return out
            out.append(frame)

    def _one(self):
        buf = self._buf
        if len(buf) < 2:
            return None
        opcode = buf[0] & 0x0F
        masked = bool(buf[1] & 0x80)
        n = buf[1] & 0x7F
        off = 2
        if n == 126:
            if len(buf) < 4:
                return None
            n = struct.unpack(">H", buf[2:4])[0]
            off = 4
        elif n == 127:
            if len(buf) < 10:
                return None
            n = struct.unpack(">Q", buf[2:10])[0]
            off = 10
            if n > MAX_FRAME:
                raise ProtocolError("declared frame length %d exceeds MAX_FRAME" % n)
        if masked:
            if len(buf) < off + 4:
                return None
            mask = buf[off:off + 4]
            off += 4
        if len(buf) < off + n:
            return None
        data = bytearray(buf[off:off + n])
        if masked:
            for i in range(n):
                data[i] ^= mask[i % 4]
        self._buf = buf[off + n:]
        return opcode, bytes(data)


def new_key():
    return base64.b64encode(os.urandom(16)).decode()


ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(key):
    """RFC6455 §4.2.2: base64(sha1(key + GUID))."""
    digest = hashlib.sha1((key + ACCEPT_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode()


def handshake_request(host, key, origin="https://app.plex.tv"):
    """The exact request wsprobe.py sent — live-verified against the relay."""
    lines = [
        "GET /ws HTTP/1.1",
        "Host: %s" % host,
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Key: %s" % key,
        "Sec-WebSocket-Version: 13",
        "Origin: %s" % origin,
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def handshake_response_status(head_bytes, key=None):
    """Parse the response head; return the status, raise unless it is 101.

    When `key` is given, verify Sec-WebSocket-Accept (§8 transport) — the
    digest is what makes the upgrade ours and not a proxy's.
    """
    first = head_bytes.split(b"\r\n", 1)[0].decode("latin-1")
    parts = first.split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise HandshakeError("unparseable handshake response: %r" % first)
    status = int(parts[1])
    if status != 101:
        raise HandshakeError("handshake rejected: %s" % first)
    if key is not None:
        got = ""
        for line in head_bytes.split(b"\r\n")[1:]:
            name, sep, value = line.partition(b":")
            if sep and name.strip().lower() == b"sec-websocket-accept":
                got = value.strip().decode("latin-1")
                break
        expected = accept_key(key)
        if got != expected:
            raise HandshakeError("bad Sec-WebSocket-Accept: %r != %r"
                                 % (got, expected))
    return status


class WSClient(object):
    """One WebSocket connection with a reader thread.

    on_open()          — after the 101, before any frame (send Hello here)
    on_message(text)   — str payload of every text frame (reader thread)
    on_close(reason)   — when the connection is gone (reader thread)

    An exception raised inside on_open/on_message tears down the connection
    and surfaces as on_close(reason).

    No auto-reconnect: per-user state does not survive a disconnect (§5.8),
    so a reconnect is a fresh session and the caller decides when to start
    a new WSClient.
    """

    def __init__(self, host, port, on_message, on_open=None, on_close=None,
                 use_ssl=True, timeout=15.0):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._sock = None
        self._wlock = threading.Lock()   # sendall() is NOT thread-safe (§5.9)
        self._decoder = FrameDecoder()
        self._stopped = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        reason = "connect failed"
        try:
            self._connect_once()
            reason = "closed by peer"
        except Exception as exc:
            reason = repr(exc)
        finally:
            sock, self._sock = self._sock, None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        if self.on_close:
            self.on_close(reason)

    def _connect_once(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            if self.use_ssl:
                # verification stays ON for *.syncplay.plex.services (§10.2)
                ctx = ssl.create_default_context()
                raw = ctx.wrap_socket(raw, server_hostname=self.host)
            key = new_key()
            raw.sendall(handshake_request(self.host, key))
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = raw.recv(4096)
                if not chunk:
                    raise HandshakeError("connection closed during handshake")
                head += chunk
            head, rest = head.split(b"\r\n\r\n", 1)
            handshake_response_status(head, key)
            # shorten the timeout only after the handshake: a slow PoP must not
            # look like a connect failure and be retried
            raw.settimeout(1.0)
            with self._wlock:
                self._sock = raw
            if self.on_open:
                self.on_open()
            self._read_loop(rest)
        except Exception:
            # _run's finally only closes self._sock, which is still None
            # if the handshake never completed — close the raw fd here.
            try:
                raw.close()
            except OSError:
                pass
            raise

    def _read_loop(self, initial=b""):
        for op, payload in self._decoder.feed(initial):
            self._dispatch(op, payload)
            if self._stopped.is_set():
                return
        while not self._stopped.is_set():
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout:
                continue
            except ssl.SSLWantReadError:
                continue
            if not chunk:
                raise EOFError("server closed TCP")
            for op, payload in self._decoder.feed(chunk):
                self._dispatch(op, payload)
                if self._stopped.is_set():
                    return

    def _dispatch(self, op, payload):
        if op == 0x9:                     # ping -> pong, immediately (§10.2)
            self.send_raw(payload, 0xA)
            return
        if op == 0x8:                     # close
            try:
                self.send_raw(payload, 0x8)   # RFC6455: echo the close frame
            except OSError:
                pass
            self._stopped.set()
            return
        if op in (0x1, 0x2):
            if self.on_message:
                self.on_message(payload.decode("utf-8", "replace"))

    def send(self, obj):
        """Serialise a dict to JSON and send it. Thread-safe."""
        self.send_raw(json.dumps(obj).encode(), 0x1)

    def send_raw(self, payload, opcode=0x1):
        with self._wlock:
            sock = self._sock
            if sock is None:
                raise OSError("not connected")
            frame = encode_frame(payload, opcode)
            try:
                sock.sendall(frame)
            except Exception:
                # a partial frame on the wire corrupts the stream — the
                # connection must be dead, not merely retried
                self._stopped.set()
                try:
                    sock.close()
                except OSError:
                    pass
                raise

    def close(self):
        self._stopped.set()
        try:
            if self._sock is not None:
                self.send_raw(struct.pack(">H", 1000), 0x8)
        except OSError:
            pass
