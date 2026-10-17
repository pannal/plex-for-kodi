#!/usr/bin/env python3
"""§11.17 — is the relay's idle-eviction threshold a MESSAGE COUNT or a WALL CLOCK?

The doc records "~14 s / 14 messages" and calls it approximate, because in every prior
capture those two numbers moved together: one client echoes at 1 Hz, so 14 messages *is*
14 seconds and the data cannot separate them.

They separate if you change the relay's State rate underneath the victim. The relay does
not generate State on its own — it rebroadcasts whatever the *driver* echoes — so a driver
ticking at 4 Hz pushes 4 State/s at a non-echoing observer, while a driver at 0.5 Hz pushes
one every 2 s. Counted and clocked evictions then predict opposite outcomes:

    count-based (~14 messages)   4 Hz -> evicted in ~3.5 s   0.5 Hz -> ~28 s
    clock-based (~14 s)          4 Hz -> evicted in ~14 s    0.5 Hz -> ~14 s

RESULTS ARE PRINTED AT THE END. Each trial: driver A echoes at RATE for up to LIMIT
seconds, victim B completes Hello and then sends no State at all (it still pongs the
WebSocket pings, as a dead-but-connected client would). We record both the elapsed time and
the number of State frames B saw before the synthetic `left` against B's own key.

Two clients, one throwaway `ev<hex>` room each. Never touches a real room. stdlib only.

Usage: python3 evictprobe.py [host] [port]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
import twoclientprobe as tcp   # noqa: E402

LIMIT = 40.0          # give a clock-based eviction at 0.5 Hz room to happen
RATES = [4.0, 1.0, 0.5]   # driver ticks per second


class Silent(tcp.Client):
    """Sends Hello (in __init__), then never sends a State. Still answers pongs."""

    def keepalive(self):
        while not self.stop.is_set():
            self.stop.wait(1.0)

    def echo(self):
        pass


class Driver(tcp.Client):
    RATE = 1.0

    def keepalive(self):
        while not self.stop.is_set():
            self.echo()
            self.stop.wait(1.0 / self.RATE)


def trial(rate, room, results):
    tcp.ROOM = room
    Driver.RATE = rate
    a = Driver("driver", "111111111", "drv", True)
    time.sleep(0.6)
    b = Silent("victim", "222222222", "vic", False)
    t0 = time.monotonic()
    b.start()
    a.start()
    # the relay may append one "_" per collision (§5.1); match the key as a prefix
    key = b.identity

    left_at = None
    while time.monotonic() - t0 < LIMIT:
        if b.stop.is_set():
            break
        if any(_left_for(m, key) for _, m in b.msgs):
            left_at = time.monotonic() - t0
            break
        time.sleep(0.05)

    elapsed = (left_at if left_at is not None else time.monotonic() - t0)
    frames = len([1 for _, m in b.msgs if "State" in m])
    a.close()
    b.close()
    time.sleep(0.4)
    results.append((rate, left_at is not None, elapsed, frames))
    print("  rate=%-4s Hz  evicted=%-5s  t=%6.2fs  frames=%d"
          % (rate, left_at is not None, elapsed, frames))


def _left_for(m, key):
    """True if this frame is the synthetic `left` against OUR OWN key.

    The event arrives as {"Set": {"user": {...}}}, NOT under "State" -- matching on
    "State" silently returns False for every frame and reports all trials as surviving.
    """
    u = m.get("Set", {}).get("user") if isinstance(m.get("Set"), dict) else None
    if not isinstance(u, dict):
        return False
    for k, v in u.items():
        if isinstance(v, dict) and k.startswith(key) \
                and v.get("event", {}).get("left"):
            return True
    return False


def main():
    print("=== §11.17 idle-eviction: count vs clock ===")
    results = []
    for i, rate in enumerate(RATES):
        room = "ev%06x" % int.from_bytes(os.urandom(3), "big")
        print("trial %d" % (i + 1))
        trial(rate, room, results)

    print()
    print("=== analysis ===")
    ok = [r for r in results if r[1]]
    if not ok:
        print("  no trial evicted within %.0f s -- inconclusive (a conforming observer "
              "survives, or nothing was relayed)" % LIMIT)
        return
    counts = [r[3] for r in ok]
    times = [r[2] for r in ok]
    print("  frame counts at eviction : %s  -> spread %d"
          % (counts, max(counts) - min(counts)))
    print("  elapsed at eviction      : %s  -> spread %.1f s"
          % ([round(t, 1) for t in times], max(times) - min(times)))
    if max(counts) - min(counts) <= 2:
        print("  VERDICT: constant message count, wall clock varies -> COUNT-based")
    elif max(times) - min(times) <= 2.5:
        print("  VERDICT: constant wall clock, frame count varies -> CLOCK-based")
    else:
        print("  VERDICT: neither constant -- neither pure count nor pure clock")


if __name__ == "__main__":
    main()
