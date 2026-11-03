#!/usr/bin/env python3
"""§11.23 — is the join handshake ORDER necessary, or merely what the web client does?

RESULT: it is not. All 11 variants — the full real-client order, no `Set` at all, the
single `Set{ready}{isReady:true, manuallyInitiated:false}`, the playlist pair alone, the
playlist pair moved ahead of ready, the baseline minus its `isReady:false`, one write with
a key the relay does not know, and four permutations of the baseline including a full
reversal and 400 ms spacing — sustain the 1 Hz `State` stream for the full 32 s, past the
~14 s eviction window: 34 inbound `State` frames each, first at ~0.21 s, last at ~33.2 s,
`per5s` identical, 33/34 carrying `setBy` = self, no synthetic `left` against our own key,
`send_err=None`. Reproduced identically twice (22/22 rooms). Liveness is gated on exactly
one thing: mirroring `ignoringOnTheFly.server` back on every outbound `State` (§5.9).
Nothing in the handshake participates.

The writes matter as *values*, but never as *order*. The relay is a plain last-write-wins
store: `List.isReady` is whatever the last `Set{ready}` said, so inverting the pair (P1,
P3) leaves `isReady=False` in the roster and nothing else changes. `playlistChange` /
`playlistIndex` are stored and echoed verbatim whenever they arrive, before or after
ready. An unknown `Set` key is silently dropped, not echoed — V7 is byte-for-byte
indistinguishable from V2. A conforming client therefore needs one frame, not four:
`Set{ready}{isReady:true, manuallyInitiated:false}`.

This supersedes the 8-way `handshakebisect.py` matrix, which is void: it hardcoded
`ignoringOnTheFly.server: 0`, so all 8 variants stalled at the same 1.1–1.4 s and the
handshake looked irrelevant for the wrong reason. The frame codec, send lock, pong
handling and counter mirroring are reused from `twoclientprobe` rather than re-implemented.

Caveat: no variant sends `Set{file}`, so `file` is `{}` in every roster row and the
`maxFilenameLength` interaction is not exercised here.

One client per variant, each in its own throwaway `hso<hex>` room. Never touches a real
room. stdlib only.

Usage: python3 handshakeorder.py [host] [port] [seconds]
"""
import json
import os
import sys
import threading
import time

ARGS = list(sys.argv[1:])
HOST = ARGS[0] if len(ARGS) > 0 else "pop-atl01.syncplay.plex.services"
PORT = int(ARGS[1]) if len(ARGS) > 1 else 7777
SECONDS = float(ARGS[2]) if len(ARGS) > 2 else 32.0
LIST_AT = 20.0          # snapshot the roster well after the handshake has settled
TAIL = 1.5              # grace for the List reply after the window closes

# tcp.Client reads the room from a module global, so concurrent construction would let
# variants collide into one shared room (contaminates both setBy and the List snapshot).
CLONE = threading.Lock()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
import twoclientprobe as tcp   # noqa: E402

tcp.HOST, tcp.PORT = HOST, PORT
ident = tcp.ident


# --------------------------------------------------------------- the write shapes

def ready_false(c):
    return {"Set": {"ready": {"isReady": False}}}


def ready_true(c):
    return {"Set": {"ready": {"isReady": True, "manuallyInitiated": False}}}


def pl_change(c):
    return {"Set": {"playlistChange": {"user": c.identity, "files": []}}}


def pl_index(c):
    return {"Set": {"playlistIndex": {"user": c.identity, "index": None}}}


def nop(c):
    """A key the relay does not know: controls for "does ANY write matter"."""
    return {"Set": {"hsoNop": {"marker": 7}}}


VARIANTS = [
    ("V1", "full real order: rf, rt, plC, plI",       [ready_false, ready_true, pl_change, pl_index], 0.0),
    ("V2", "no Set at all (Hello + State only)",       [],                                             0.0),
    ("V3", "ready only: rt",                           [ready_true],                                  0.0),
    ("V4", "playlist pair only: plC, plI",             [pl_change, pl_index],                         0.0),
    ("V5", "V1 with playlist pair BEFORE ready pair",  [pl_change, pl_index, ready_false, ready_true], 0.0),
    ("V6", "V1 minus the isReady:false",              [ready_true, pl_change, pl_index],              0.0),
    ("V7", "one no-op Set (unknown key)",             [nop],                                          0.0),
    ("P1", "ready-true BEFORE ready-false",            [ready_true, ready_false, pl_change, pl_index], 0.0),
    ("P2", "playlist pair reversed (plI, plC)",        [ready_false, ready_true, pl_index, pl_change], 0.0),
    ("P3", "full reverse: plI, plC, rt, rf",          [pl_index, pl_change, ready_true, ready_false], 0.0),
    ("P4", "V1 but spaced 400ms apart",                [ready_false, ready_true, pl_change, pl_index], 0.4),
]


# --------------------------------------------------------------------- one variant

def own_entry(c, room):
    """Our own row in the most recent roster snapshot."""
    last = None
    for _, m in list(c.msgs):
        if "List" in m:
            last = m
    if not last:
        return None, "<no List reply>"
    for k, v in (last.get("List") or {}).get(room, {}).items():
        if ident(k) == c.label:
            return v, ""
    return None, "<no row for self: relay answered for %s>" % list(
        (last.get("List") or {}).keys())


def describe(msg):
    """One-line shape label for an inbound Set, so rebroadcasts are attributable."""
    s = msg.get("Set")
    if not isinstance(s, dict):
        return None
    out = []
    for k, v in s.items():
        if k == "user" and isinstance(v, dict):
            for _, vv in v.items():
                if isinstance(vv, dict) and "event" in vv:
                    out.append("user:%s" % ",".join(sorted(vv["event"])))
                else:
                    out.append("user:state")
        elif k == "ready":
            out.append("ready(isReady=%s)" % v.get("isReady") if isinstance(v, dict)
                       else "ready")
        elif k == "playlistChange":
            out.append("playlistChange(n=%s)" % (len(v.get("files") or [])
                                                 if isinstance(v, dict) else "?"))
        elif k == "playlistIndex":
            out.append("playlistIndex(%s)" % (v.get("index") if isinstance(v, dict) else "?"))
        else:
            out.append(k)
    return ",".join(out)


def run_variant(tag, desc, plan, gap, out):
    room = "hso" + os.urandom(4).hex()
    t0 = time.monotonic()
    try:
        with CLONE:
            tcp.ROOM = room
            c = tcp.Client(tag, 1000001, "hso-" + room, driver=True)
        c.room = room
        t0 = time.monotonic()
        for fn in plan:
            c.send(fn(c))
            if gap:
                time.sleep(gap)
        c.start()

        listed = False
        while time.monotonic() - t0 < SECONDS:
            if not listed and time.monotonic() - t0 >= LIST_AT:
                c.send({"List": {}})
                listed = True
            time.sleep(0.2)
        time.sleep(TAIL)

        msgs = list(c.msgs)
        st = [t - t0 for t, m in msgs if "State" in m]
        buckets = [0] * int(SECONDS // 5)
        for t in st:
            buckets[min(int(t // 5), len(buckets) - 1)] += 1
        kinds, shapes, ready_seq = {}, {}, []
        for t, m in msgs:
            k = list(m.keys())[0]
            kinds[k] = kinds.get(k, 0) + 1
            d = describe(m)
            if d:
                shapes[d] = shapes.get(d, 0) + 1
                if d.startswith("ready("):
                    ready_seq.append(d)

        setby = []
        for _, m in msgs:
            if "State" in m:
                n = ident(m["State"].get("playstate", {}).get("setBy"))
                if not setby or setby[-1][0] != n:
                    setby.append([n, 1])
                else:
                    setby[-1][1] += 1

        closed = False
        for _, m in msgs:
            s = m.get("Set", {}).get("user", {})
            for k, v in s.items():
                if ident(k) == tag and isinstance(v, dict) and (v.get("event") or {}).get("left"):
                    closed = True

        entry, why = own_entry(c, room)
        listtxt = why or "isReady=%-5s file=%-4s controller=%-5s position=%s" % (
            entry.get("isReady"), json.dumps(entry.get("file"))[:4],
            entry.get("controller"), entry.get("position"))

        last = st[-1] if st else -1.0
        alive = last >= SECONDS - 4 and not c.stop.is_set() and c.send_err is None
        realver = ""
        for _, m in msgs:
            if "Hello" in m:
                realver = m["Hello"].get("realversion", "?")
                break

        out[tag] = {"desc": desc, "room": room, "verdict": "OK" if alive else "STALL",
                    "status": "%s  realversion=%s" % (c.status, realver),
                    "states": len(st), "first": st[0] if st else None, "last": last,
                    "buckets": buckets, "setby": setby,
                    "self_echo": sum(n for name, n in setby if name == tag),
                    "kinds": sorted(kinds.items()), "shapes": shapes,
                    "ready_seq": ready_seq, "list": listtxt, "survived": alive,
                    "closed": closed, "send_err": c.send_err, "tb": ""}
        c.close()
    except Exception:
        import traceback
        out[tag] = {"desc": desc, "room": room, "verdict": "CRASH",
                    "status": traceback.format_exc().strip().splitlines()[-1],
                    "tb": traceback.format_exc(), "states": 0, "first": None,
                    "last": -1.0, "buckets": [], "setby": [], "self_echo": 0,
                    "kinds": [], "shapes": {}, "ready_seq": [], "list": "-",
                    "survived": False, "closed": False, "send_err": None}


def main():
    print("%d handshake variants, %.0fs each (eviction window is ~14s), concurrent"
          % (len(VARIANTS), SECONDS))
    print("relay %s:%d, every variant gets its own throwaway hso<hex> room" % (HOST, PORT))
    print("all clients echo State at 1 Hz WITH ignoringOnTheFly.server mirrored "
          "(twoclientprobe.Client)\n")
    out = {}
    threads = [threading.Thread(target=run_variant, args=(t, d, p, g, out), daemon=True)
               for t, d, p, g in VARIANTS]
    for th in threads:
        th.start()
    for th in threads:
        th.join(SECONDS + 40)

    print("=" * 118)
    print("%-4s %-42s %-6s %6s %7s %7s  %s" % ("var", "plan", "verdict", "states",
                                               "first", "last", "per5s"))
    print("-" * 118)
    for tag, _, _, _ in VARIANTS:
        r = out.get(tag)
        if not r:
            print("%-4s %-42s %s" % (tag, "", "NO RESULT"))
            continue
        print("%-4s %-42s %-6s %6d %6s %6.1f  %s" % (
            tag, r["desc"], r["verdict"], r["states"],
            "%.2f" % r["first"] if r["first"] is not None else "-",
            r["last"], r["buckets"]))
    print("=" * 118)

    for tag, desc, _, _ in VARIANTS:
        r = out.get(tag)
        if not r:
            continue
        print("\n--- %s  %s" % (tag, desc))
        print("   room          : %s" % r["room"])
        print("   handshake     : %s" % r["status"])
        print("   States in     : %d   first=%s  last=%.2fs"
              % (r["states"], "%.2f" % r["first"] if r["first"] is not None else "-", r["last"]))
        print("   inbound kinds : %s" % (r["kinds"],))
        print("   Set shapes in : %s" % (r["shapes"],))
        if r["ready_seq"]:
            print("   ready echoes  : %s" % " ".join(r["ready_seq"][:8]))
        print("   setBy sequence: %s" % ("  ->  ".join("%s x%d" % (n, k) for n, k in r["setby"]),))
        print("   self-echoes   : %d" % r["self_echo"])
        print("   List self row : %s" % r["list"])
        print("   survived %.0fs : %s   synthetic left(self)=%s   send_err=%s"
              % (SECONDS, r["survived"], r["closed"], r["send_err"]))
        if r["tb"]:
            print(r["tb"])

    ok = [t for t, _, _, _ in VARIANTS if out.get(t, {}).get("survived")]
    print("\nsurvived %.0fs: %s" % (SECONDS, ", ".join(ok) if ok else "NONE"))
    print("rooms used: %s" % ", ".join("%s=%s" % (t, out[t]["room"]) for t, _, _, _ in VARIANTS
                                      if t in out))


if __name__ == "__main__":
    main()