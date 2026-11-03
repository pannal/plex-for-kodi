#!/usr/bin/env python3
"""Live Watch Together validation for the PM4K protocol library.

Dev-only — NOT part of pytest. Uses the real lib/ws.py + lib/syncplay.py +
lib/watchtogether.py against the real services.

  python3 scripts/watchtogether_soak.py relay [--minutes 2] [--room NAME]
      Two identities in a throwaway relay room (the cloud is never told, so
      there is nothing to clean up). Asserts:
        * no stall: relay States keep arriving for the whole soak (§5.9)
        * roster: both identities appear in List
        * convergence: follower's remote position tracks the driver
        * self-echo: driver drops its own echoed States (§5.5)
      Exit 0 = PASS, 1 = FAIL.

  python3 scripts/watchtogether_soak.py cloud [--token-file PATH] [--leave]
      Read-only RoomsApi check: GET /rooms, then GET /rooms/{id} on the first
      room; asserts syncplayHost/syncplayPort present. With --leave also
      DELETEs (you leave the room — nothing is destroyed, §4).

Exit code 0 = PASS, 1 = FAIL.
"""

from __future__ import absolute_import, print_function

import argparse
import os
import sys
import threading
import time
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from lib.syncplay import Session, build_identity, hello, list_request  # noqa: E402
from lib.watchtogether import RoomsApi, RoomGone, NotMember  # noqa: E402
from lib.ws import WSClient  # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    print("  %-52s %s%s" % (name, "PASS" if ok else "FAIL",
                            (" — " + detail) if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


class Peer(object):
    """One WSClient + Session + 1 Hz echo loop."""

    def __init__(self, label, user_id, device, room, host, port):
        self.label = label
        self.identity = build_identity(device, label, user_id)
        self.session = Session(room, self.identity)
        self.local = {"position": 0.0, "paused": True, "doSeek": False}
        self.inbound_at = []
        self._lock = threading.Lock()
        self.client = WSClient(
            host, port,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close)
        self._stop = threading.Event()
        self.opened = threading.Event()
        self._echo_started = False

    def _on_open(self):
        self.client.send(hello(self.session.room, self.identity))
        self.client.send(list_request())
        self.opened.set()
        # start the echo loop only once, from on_open: sending before the
        # handshake finishes raises OSError("not connected") and the relay
        # silence-evicts a client that never heartbeats (§5.8)
        if not self._echo_started:
            self._echo_started = True
            threading.Thread(target=self._echo_loop, daemon=True).start()

    def _on_message(self, text):
        with self._lock:
            self.inbound_at.append(time.monotonic())
        self.session.on_message(text)

    def _on_close(self, reason):
        self._stop.set()

    def start(self):
        self.client.start()

    def _echo_loop(self):
        # steady 1 Hz: our cadence is everyone else's smoothness (§5.5)
        while not self._stop.is_set():
            msg = self.session.outbound_state(self.local)
            try:
                self.client.send(msg)
            except OSError:
                self._stop.set()
                return
            self._stop.wait(1.0)

    def stop(self):
        self._stop.set()
        self.client.close()


def soak_relay(args):
    host, port_s = args.relay.rsplit(":", 1)
    port = int(port_s)
    room = args.room or ("wt" + uuid.uuid4().hex[:8])
    print("relay  : %s" % args.relay)
    print("room   : %s  (throwaway — cloud never told)" % room)

    driver = Peer("driver", 1000001, "soak-driver", room, host, port)
    follower = Peer("follower", 1000002, "soak-follower", room, host, port)
    driver.start()
    # the relay relays States only from the room's first client — pin order
    # so driver opens before follower races it (proven: first-opener wins)
    if not driver.opened.wait(30):
        check("driver connected within 30s", False, "relay unreachable?")
        driver.stop()
        return not FAILURES
    follower.start()

    # let the handshake + List land
    time.sleep(3.0)
    start = time.monotonic()

    # driver plays: position advances 1 per tick; follower must converge
    driver.local["paused"] = False
    minutes = max(args.minutes, 1.0)
    deadline = start + minutes * 60
    settled = False
    while time.monotonic() < deadline:
        driver.local["position"] += 1.0
        time.sleep(1.0)
        if not settled and time.monotonic() > start + 10:
            gap = abs(follower.session.remote["position"]
                      - driver.local["position"])
            settled = True
            check("follower converges on driver (drift < 6s)", gap < 6.0,
                  "gap=%.2f" % gap)

    elapsed = time.monotonic() - start
    end_gap = abs(follower.session.remote["position"]
                  - driver.local["position"])
    check("follower still converging at end of soak (drift < 6s)",
          end_gap < 6.0, "gap=%.2f" % end_gap)
    driver.stop()
    follower.stop()
    time.sleep(1.0)

    for peer in (driver, follower):
        inbound = [t for t in peer.inbound_at if t >= start]
        expected = elapsed * 0.9        # 1 Hz, allow 10% jitter
        check("%s: no stall — relay kept relaying for %.0fs" % (peer.label, elapsed),
              len(inbound) >= expected,
              "%d frames in %.0fs (want >= %.0f)" % (len(inbound), elapsed, expected))
        if len(inbound) > 2:
            worst_gap = max(b - a for a, b in zip(inbound, inbound[1:]))
            check("%s: worst inter-frame gap < 3s" % peer.label, worst_gap < 3.0,
                  "gap=%.2fs" % worst_gap)

    check("roster contains both identities", len(driver.session.roster) == 2,
          "roster=%d" % len(driver.session.roster))
    check("driver self-echoed and dropped own States (§5.5)",
          driver.session.self_echo > 0, "self_echo=%d" % driver.session.self_echo)
    check("follower self-echoed and dropped own States (§5.5)",
          follower.session.self_echo > 0, "self_echo=%d" % follower.session.self_echo)
    check("follower's remote setBy names the driver",
          follower.session.remote.get("setBy") is not None)
    return not FAILURES


def cloud(args):
    with open(os.path.expanduser(args.token_file), "r") as fp:
        token = fp.read().strip()
    api = RoomsApi(token)
    rooms = api.rooms()
    print("  GET /rooms -> %d room(s)" % len(rooms))
    if not rooms:
        print("  (no rooms you are a member of — create one on plex.tv and "
              "invite this account to test discovery)")
        check("cloud: GET /rooms reachable with valid token", True)
        return not FAILURES
    room = rooms[0]
    fetched = api.room(room.id)
    check("cloud: room fetched and has a relay endpoint",
          bool(fetched.syncplay_host and fetched.syncplay_port),
          "host=%r port=%r" % (fetched.syncplay_host, fetched.syncplay_port))
    check("cloud: room has sourceUri", bool(fetched.source_uri))
    if args.leave:
        api.leave(room.id)
        try:
            api.room(room.id)
            check("cloud: room reads 403/404 after leave", False, "still readable")
        except RoomGone:
            check("cloud: room gone for us after leave", True)
        except NotMember:      # 403 == left (§4)
            check("cloud: left the room (NotMember)", True)
    return not FAILURES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode")
    sub.required = True
    p_relay = sub.add_parser("relay", help="relay soak, throwaway room")
    p_relay.add_argument("--relay", default="pop-atl01.syncplay.plex.services:7777",
                         help="host:port of a syncplay PoP")
    p_relay.add_argument("--room", default=None, help="throwaway room name")
    p_relay.add_argument("--minutes", type=float, default=2.0)
    p_cloud = sub.add_parser("cloud", help="read-only RoomsApi check")
    p_cloud.add_argument("--token-file", default="~/.plex-probe-token-host")
    p_cloud.add_argument("--leave", action="store_true")
    args = parser.parse_args()

    ok = soak_relay(args) if args.mode == "relay" else cloud(args)
    print("\n%s" % ("PASS" if ok and not FAILURES else "FAIL: %s" % FAILURES))
    return 0 if ok and not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
