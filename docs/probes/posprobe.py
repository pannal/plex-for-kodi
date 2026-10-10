#!/usr/bin/env python3
"""§11.2 — what does the relay do to `playstate.position`?

The doc records that "a relative position came back as an epoch-scale number" and reads it
as a clock base that could not be reconstructed, then tells clients never to emulate
relay-side arithmetic. That is the last unwieldy claim in §5.7: it was inferred from one
unexpected value rather than from a sweep.

This sweeps it directly. One driver, one throwaway room, paused and playing:

    * position P sent  ->  what the relay broadcasts back, before and after our own
                           rebroadcast arrives
    * P = 0, 1, 60, 1800, 3151, 3600, 86400, 1e6   (integers, incl. epoch-ish magnitudes)
    * paused=True (expect store-and-return) and paused=False (expect extrapolation)

Questions settled:
    1. Is it "store the client's value" (paused) -- exact round-trip?
    2. Playing: does the relay add elapsed wall time, and from which base?
    3. Does a small "relative" value ever come back epoch-scale? That is the specific
       claim under test. If P=1 comes back as ~1.7e9 while P=1800 comes back as 1800,
       the clock-base reading survives; if everything round-trips, it was a bug in the
       probe that produced the number, not in the relay.

Read-only with respect to the cloud; spins its own `pos<hex>` room on the relay. stdlib
only.

Usage: python3 posprobe.py [host] [port]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
import twoclientprobe as tcp   # noqa: E402

LIMIT = 4.0
POSITIONS = [0, 1, 60, 1800, 3151, 3600, 86400, 1000000]


def inbound_states(c, since=0.0):
    return [(t, m["State"]) for t, m in c.msgs
            if t >= since and isinstance(m.get("State"), dict)
            and "playstate" in m["State"]]


def trial(position, paused):
    tcp.ROOM = "pos%06x" % int.from_bytes(os.urandom(3), "big")
    c = tcp.Client("pos", "777777777", "pos", True)
    c.set_local(position=position, paused=paused, do_seek=False)
    t0 = time.monotonic()
    c.start()
    time.sleep(LIMIT)
    c.close()
    time.sleep(0.3)

    rows = inbound_states(c, t0)
    if not rows:
        return position, paused, None, None, 0
    own = [p for _, p in rows
           if p.get("playstate", {}).get("setBy") is None]
    # our own frames come back with setBy set by the relay to our identity
    mine = [p.get("playstate", {}).get("position") for _, p in rows
            if p.get("playstate", {}).get("setBy") and "777777777" in
            str(p.get("playstate", {}).get("setBy"))]
    returned = [p.get("playstate", {}).get("position") for _, p in rows]
    return position, paused, returned, mine, len(rows)


def main():
    print("=== §11.2 position arithmetic ===")
    print("%-10s %-7s %-9s %s" % ("sent", "paused", "frames", "positions seen back"))
    for paused in (True, False):
        for pos in POSITIONS:
            _, _, returned, mine, n = trial(pos, paused)
            if returned is None:
                print("%-10s %-7s %-9s %s" % (pos, paused, 0, "(no State)"))
                continue
            seen = [round(v, 3) if isinstance(v, float) else v for v in returned]
            print("%-10s %-7s %-9d %s" % (pos, paused, n, seen))
        print()

    print("=== analysis ===")
    print("  paused rows should round-trip exactly; playing rows should drift upward")
    print("  by elapsed wall time. Anything epoch-scale on a small input would confirm")
    print("  the clock-base reading.")


if __name__ == "__main__":
    main()
