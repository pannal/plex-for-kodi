# coding=utf-8
"""Tests for lib/ws.py — RFC6455 codec (docs/watch-together.md §5)."""

from __future__ import absolute_import

import json
import socket
import threading
import time
import unittest

from lib import ws


def server_frame(payload, opcode=0x1):
    """Build a server->client frame (never masked, per RFC6455)."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    n = len(data)
    if n < 126:
        header = bytes([0x80 | opcode, n])
    elif n < 1 << 16:
        header = bytes([0x80 | opcode, 126]) + __import__("struct").pack(">H", n)
    else:
        header = bytes([0x80 | opcode, 127]) + __import__("struct").pack(">Q", n)
    return header + data


class CodecTest(unittest.TestCase):
    def roundtrip(self, payload, opcode=0x1):
        decoder = ws.FrameDecoder()
        out = decoder.feed(ws.encode_frame(payload, opcode))
        self.assertEqual(out, [(opcode, payload.encode() if isinstance(payload, str) else payload)])

    def test_roundtrip_small_payload(self):
        self.roundtrip('{"Hello":{}}')

    def test_roundtrip_125_bytes(self):
        self.roundtrip("x" * 125)

    def test_roundtrip_126_bytes_needs_extended_length(self):
        self.roundtrip("x" * 126)

    def test_roundtrip_64k_boundary_needs_8byte_length(self):
        self.roundtrip("y" * 65536)

    def test_roundtrip_binary_payload(self):
        decoder = ws.FrameDecoder()
        blob = bytes(range(256)) * 4
        out = decoder.feed(ws.encode_frame(blob, 0x2))
        self.assertEqual(out, [(0x2, blob)])

    def test_partial_feeds_reassemble(self):
        frame = ws.encode_frame('{"List":{}}')
        decoder = ws.FrameDecoder()
        collected = []
        for i in range(len(frame)):
            collected.extend(decoder.feed(frame[i:i + 1]))
        self.assertEqual(collected, [(0x1, b'{"List":{}}')])

    def test_unmasked_server_frame(self):
        decoder = ws.FrameDecoder()
        out = decoder.feed(server_frame('{"State":{}}'))
        self.assertEqual(out, [(0x1, b'{"State":{}}')])

    def test_ping_and_close_opcodes(self):
        decoder = ws.FrameDecoder()
        out = decoder.feed(server_frame(b"pong-me", 0x9))
        out += decoder.feed(server_frame(b"\x03\xe8", 0x8))
        self.assertEqual(out, [(0x9, b"pong-me"), (0x8, b"\x03\xe8")])

    def test_two_frames_in_one_feed(self):
        decoder = ws.FrameDecoder()
        out = decoder.feed(server_frame("one") + server_frame("two"))
        self.assertEqual(out, [(0x1, b"one"), (0x1, b"two")])

    def test_incomplete_frame_yields_nothing_and_stores_it(self):
        decoder = ws.FrameDecoder()
        frame = ws.encode_frame("hello world this is longer than six bytes")
        self.assertEqual(decoder.feed(frame[:3]), [])
        out = decoder.feed(frame[3:])
        self.assertEqual(out, [(0x1, b"hello world this is longer than six bytes")])

    def test_client_frames_are_masked(self):
        raw = ws.encode_frame("abc")
        self.assertTrue(raw[1] & 0x80, "client frames MUST be masked")

    def test_large_length_frames_encode_mask_correctly(self):
        payload = "z" * 70000
        decoder = ws.FrameDecoder()
        out = decoder.feed(ws.encode_frame(payload))
        self.assertEqual(out, [(0x1, payload.encode())])

    def test_oversized_declared_length_raises(self):
        import struct as _struct
        decoder = ws.FrameDecoder()
        header = bytes([0x81, 127]) + _struct.pack(">Q", 1 << 60)
        with self.assertRaises(ws.ProtocolError):
            decoder.feed(header)


class HandshakeTest(unittest.TestCase):
    def test_request_matches_what_the_relay_accepts(self):
        # wsprobe.py handshake, live-verified (docs/watch-together.md §12)
        req = ws.handshake_request("pop-fra00.syncplay.plex.services",
                                   "dGhlIHNhbXBsZSBub25jZQ==")
        text = req.decode()
        self.assertTrue(text.startswith("GET /ws HTTP/1.1\r\n"))
        self.assertIn("Host: pop-fra00.syncplay.plex.services\r\n", text)
        self.assertIn("Upgrade: websocket\r\n", text)
        self.assertIn("Connection: Upgrade\r\n", text)
        self.assertIn("Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n", text)
        self.assertIn("Sec-WebSocket-Version: 13\r\n", text)
        self.assertIn("Origin: https://app.plex.tv\r\n", text)
        self.assertTrue(text.endswith("\r\n\r\n"))

    def test_new_key_is_valid_base64_of_16_bytes(self):
        import base64
        key = ws.new_key()
        self.assertEqual(len(base64.b64decode(key)), 16)

    def test_accepts_101(self):
        head = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
        self.assertEqual(ws.handshake_response_status(head), 101)

    def test_accept_key_matches_the_rfc6455_vector(self):
        # RFC6455 §1.3
        self.assertEqual(ws.accept_key("dGhlIHNhbXBsZSBub25jZQ=="),
                         "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_verifies_the_accept_digest_when_key_given(self):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        head = (b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n")
        self.assertEqual(ws.handshake_response_status(head, key), 101)

    def test_rejects_a_wrong_accept_digest(self):
        head = (b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Sec-WebSocket-Accept: wrong-value\r\n")
        with self.assertRaises(ws.HandshakeError) as ctx:
            ws.handshake_response_status(head, "dGhlIHNhbXBsZSBub25jZQ==")
        self.assertIn("Sec-WebSocket-Accept", str(ctx.exception))

    def test_rejects_non_101(self):
        head = b"HTTP/1.1 400 Bad Request\r\n"
        with self.assertRaises(ws.HandshakeError) as ctx:
            ws.handshake_response_status(head)
        self.assertIn("400", str(ctx.exception))

    def test_rejects_garbage(self):
        with self.assertRaises(ws.HandshakeError):
            ws.handshake_response_status(b"not http at all")


def _accept_from(head):
    """Server-side Sec-WebSocket-Accept for the client's key (RFC6455)."""
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"sec-websocket-key:"):
            key = line.split(b":", 1)[1].strip().decode()
            return ws.accept_key(key).encode()
    return b""


class FakeRelay(threading.Thread):
    """In-process plain-TCP relay double for WSClient tests (no TLS)."""

    def __init__(self):
        super(FakeRelay, self).__init__(daemon=True)
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self.handshake = b""
        self.texts = []
        self.pongs = []
        self.error = None

    def run(self):
        try:
            conn, _ = self._srv.accept()
        except OSError as exc:
            self.error = exc
            return
        with conn:
            conn.settimeout(5)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                head += chunk
            self.handshake = head
            conn.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: " + _accept_from(head) + b"\r\n\r\n")
            decoder = ws.FrameDecoder()
            # 1. expect the client's first text frame
            text1 = self._next_text(conn, decoder)
            if text1 is not None:
                self.texts.append(text1)
            # 2. send a text frame and a ping
            conn.sendall(server_frame("ready"))
            conn.sendall(server_frame(b"ping-payload", 0x9))
            # 3. expect the client's pong
            self._next_pong(conn, decoder)
            # 4. send another text, then hang up
            conn.sendall(server_frame("bye"))
            time.sleep(0.2)

    def _next_text(self, conn, decoder, deadline=5.0):
        end = time.time() + deadline
        while time.time() < end:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                return None
            for op, payload in decoder.feed(chunk):
                if op == 0x1:
                    return payload.decode()
        return None

    def _next_pong(self, conn, decoder, deadline=5.0):
        end = time.time() + deadline
        while time.time() < end:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                return
            for op, payload in decoder.feed(chunk):
                if op == 0xA:
                    self.pongs.append(payload)
                    return


class CountingRelay(threading.Thread):
    """Minimal relay double: handshake, then count text frames until 100 or deadline."""

    def __init__(self, expect=100, deadline=5.0):
        super(CountingRelay, self).__init__(daemon=True)
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self.expect = expect
        self.deadline = deadline
        self.frames = []
        self.error = None

    def run(self):
        try:
            conn, _ = self._srv.accept()
        except OSError as exc:
            self.error = exc
            return
        finally:
            self._srv.close()
        with conn:
            conn.settimeout(5)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                head += chunk
            conn.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: " + _accept_from(head) + b"\r\n\r\n")
            decoder = ws.FrameDecoder()
            end = time.time() + self.deadline
            try:
                while time.time() < end and len(self.frames) < self.expect:
                    try:
                        chunk = conn.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        return
                    for op, payload in decoder.feed(chunk):
                        if op == 0x1:
                            self.frames.append(payload)
            except ws.ProtocolError as exc:
                self.error = exc
            except OSError as exc:
                self.error = exc


class WSClientTest(unittest.TestCase):
    def test_full_connection_lifecycle(self):
        relay = FakeRelay()
        relay.start()

        opened = []
        messages = []
        closed = []
        client = ws.WSClient(
            "127.0.0.1", relay.port, use_ssl=False,
            on_open=lambda: (opened.append(True), client.send({"hello": 1})),
            on_message=messages.append,
            on_close=lambda reason: closed.append(reason))
        client.start()
        deadline = time.time() + 6
        while time.time() < deadline and (len(messages) < 2 or not relay.pongs):
            time.sleep(0.05)
        client.close()

        self.assertEqual(opened, [True], "on_open must fire after the 101")
        self.assertEqual(messages, ["ready", "bye"], "text frames in order")
        self.assertEqual(relay.pongs, [b"ping-payload"], "ping answered with pong")
        self.assertEqual(len(relay.texts), 1)
        self.assertEqual(json.loads(relay.texts[0]), {"hello": 1})
        self.assertIn(b"Sec-WebSocket-Key:", relay.handshake)
        deadline = time.time() + 6
        while time.time() < deadline and not closed:
            time.sleep(0.05)
        self.assertEqual(len(closed), 1, "on_close fires once")

    def test_concurrent_sends_are_serialised(self):
        relay = CountingRelay()
        relay.start()
        connected = threading.Event()
        client = ws.WSClient(
            "127.0.0.1", relay.port, use_ssl=False,
            on_open=connected.set, on_message=lambda text: None)
        client.start()
        self.assertTrue(connected.wait(5), "client never connected")

        send_errors = []

        def worker(tag):
            try:
                for i in range(50):
                    client.send({"t": tag, "i": i})
            except Exception as exc:
                send_errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,), daemon=True)
                   for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(6)
        self.assertFalse(any(t.is_alive() for t in threads),
                         "send threads did not finish in time")

        deadline = time.time() + 6
        while time.time() < deadline and len(relay.frames) < relay.expect:
            time.sleep(0.05)
        client.close()
        self.assertEqual(send_errors, [], "no send may fail on a live connection")
        self.assertIsNone(relay.error, "relay decoded garbage")
        self.assertEqual(len(relay.frames), 100,
                         "exactly 100 complete frames, no interleaving")
        for payload in relay.frames:
            json.loads(payload)

    def test_close_frame_is_echoed_and_stops(self):
        client = ws.WSClient("127.0.0.1", 1, on_message=lambda t: None)
        sent = []
        client.send_raw = lambda payload, opcode=0x1: sent.append((payload, opcode))
        client._dispatch(0x8, b"\x03\xe8")
        self.assertEqual(sent, [(b"\x03\xe8", 0x8)])
        self.assertTrue(client._stopped.is_set())

    def test_read_loop_stops_at_a_close_before_later_frames(self):
        client = ws.WSClient("127.0.0.1", 1, on_message=lambda t: None)
        sent = []
        client.send_raw = lambda payload, opcode=0x1: sent.append((payload, opcode))
        chunk = ws.encode_frame(b"", 0x8) + ws.encode_frame(b"ignored", 0x1)

        class OneChunk(object):
            def __init__(self, data):
                self.data = data

            def recv(self, n):
                data, self.data = self.data, b""
                return data

        client._sock = OneChunk(chunk)
        client._read_loop()
        self.assertTrue(client._stopped.is_set())
        self.assertEqual(sent, [(b"", 0x8)], "only the close is echoed")


if __name__ == "__main__":
    unittest.main()
