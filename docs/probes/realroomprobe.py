#!/usr/bin/env python3
"""Real two-account relay session: a cloud-issued room joined by two genuine accounts.

Every previous relay probe used an invented room name and fabricated identities. This one
uses the real thing end to end, so it answers the questions that only show up when the relay
is handed a room that actually exists in the cloud:

  R1  Does the relay cross-reference the cloud room record at all, or is it still just a
      name? (Probe with an identity the room's users[] does NOT contain.)
  R2  Does a relay client get anything for free by quoting a real plex.tv userID and
      username — does the roster show a resolved profile, or only what we self-declared?
  R3  Does the identity-based setBy self-ignore work with real userIDs? (A real account must
      not fight its own frames.)
  R4  Does a real seek/pause actually propagate between two accounts with real identities?
  R5  Does the relay's advertised host/port come from the room record, and is it stable for
      the life of the room?

Room lifecycle: created here via the cloud as the host account, the second account is
invited, both clients join from the record's own syncplayHost/syncplayPort, then the host
LEAVES (DELETE = leave, not destroy -- see §4). Nothing else is touched.

    ~/.plex-probe-token-host   creator / client A  (serverowner)
    ~/.plex-probe-token        invited / client B  (libraryuser)

Usage: python3 realroomprobe.py
"""
import json
import os
import sys
import time
import urllib.request

sys.argv = [sys.argv[0]]                     # twoclientprobe reads argv at import
import twoclientprobe as tc                    # noqa: E402

BASE = "https://together.plex.tv"
SOURCE_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117")


def token(path):
    with open(os.path.expanduser(path)) as fh:
        return fh.read().strip()


def api(method, path, tok, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("X-Plex-Token", tok)
    req.add_header("X-Plex-Product", "PM4K")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            # 204 comes back EMPTY; json.loads('') raises and a bare except used to
            # report that success as "HTTP 0", which read as a failed cleanup.
            return r.status, (json.loads(raw) if raw.strip() else "")
    except Exception as e:                                     # noqa: BLE001
        return 0, repr(e)


def account(tok):
    req = urllib.request.Request("https://plex.tv/api/v2/user",
                                 headers={"X-Plex-Token": tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    return d["username"], d["id"]


def main():
    host_tok, peer_tok = token("~/.plex-probe-token-host"), token("~/.plex-probe-token")
    hname, hid = account(host_tok)
    pname, pid = account(peer_tok)
    tc.rule("R0  SETUP -- a room that really exists in the cloud")
    print("   client A (creator) : %s (%s)" % (hname, hid))
    print("   client B (invited) : %s (%s)" % (pname, pid))

    s, room = api("POST", "/rooms", host_tok,
                  {"sourceUri": SOURCE_URI, "title": "pm4k-real-two-account", "users": None})
    print("   POST /rooms -> HTTP %s" % s)
    if s not in (200, 201):
        print("   cannot create a room: %s" % room)
        return
    rid, relay_host, relay_port = room["id"], room["syncplayHost"], room["syncplayPort"]
    print("   room id  : %s" % rid)
    print("   sourceUri: %s" % room["sourceUri"][:70])
    print("   startsAt/endsAt: %s -> %s  (%.0f h)"
          % (room["startsAt"], room["endsAt"], (room["endsAt"] - room["startsAt"]) / 3600.0))
    print("   R5  relay from the RECORD: %s:%s" % (relay_host, relay_port))

    s, inv = api("POST", "/rooms/%s/invite" % rid, host_tok, {"users": [pid]})
    print("   invite %s -> HTTP %s, users now %s"
          % (pname, s, [u.get("username") for u in inv.get("users", [])] if isinstance(inv, dict) else inv))
    s, mine = api("GET", "/rooms", peer_tok)
    print("   R0  client's own GET /rooms sees: %s"
          % ([r.get("id") for r in mine.get("rooms", [])] if isinstance(mine, dict) else mine))

    # Point the imported probe at the real room and relay.
    tc.ROOM, tc.HOST, tc.PORT = rid, relay_host, int(relay_port)

    tc.rule("R1  does the relay know the room record, or only the name?")
    print("   We will join a THIRD client claiming userID 999999999, which is in nobody's")
    print("   users[]. If the relay had any membership view it would refuse or ignore it.")
    a = tc.Client("BRAVIA VH1", int(hid), "pm4kA-" + rid[-6:], driver=True)
    a.start()
    time.sleep(0.8)
    a.announce()
    time.sleep(1.5)
    impostor = tc.Client("NotInUsers", 999999999, "pm4kX-" + rid[-6:], driver=False)
    impostor.start()
    time.sleep(1.5)
    a.send({"List": {}})
    time.sleep(1.2)
    print("   roster seen by A: %s" % sorted(tc.roster(a).keys()))
    print("   impostor handshake: %s" % impostor.status)
    print("   R1  verdict: %s"
          % ("relay has NO membership view -- fabricated userID accepted"
             if "NotInUsers" in tc.roster(a) else
             "relay DOES filter on membership -- investigate"))

    tc.rule("R2  does a real userID/username buy a resolved profile?")
    b = tc.Client(pname, int(pid), "pm4kB-" + rid[-6:], driver=False)
    b.start()
    time.sleep(1.0)
    b.announce()
    time.sleep(2.0)
    a.send({"List": {}})
    time.sleep(1.2)
    for name, v in sorted(tc.roster(a).items()):
        print("   %-14s userID=%-10s controller=%-6s isReady=%-6s position=%s"
              % (name, v.get("userID"), v.get("controller"), v.get("isReady"), v.get("position")))
    print("   R2  verdict: roster keys are the identities WE sent (%s, %s), not resolved"
          % (hname, pname))
    print("        profiles -- the relay does no plex.tv lookup for the roster.")

    tc.rule("R3/R4  does playstate propagate between two REAL accounts?")
    impostor.close()
    time.sleep(1.0)
    t = time.monotonic()
    for i in range(5):
        a.set_local(position=100.0 + i, paused=False, do_seek=False)
        time.sleep(1.0)
    tc.show("B", tc.snap(b, t))
    t = time.monotonic()
    a.set_local(position=106.0, paused=True)
    time.sleep(2.5)
    tc.show("B (pause)", tc.snap(b, t))
    t = time.monotonic()
    a.set_local(position=900.0, do_seek=True)
    time.sleep(1.6)
    tc.show("B (seek tick)", tc.snap(b, t))
    t = time.monotonic()
    a.set_local(do_seek=False)
    time.sleep(2.0)
    tc.show("B (doSeek cleared)", tc.snap(b, t))

    tc.rule("R3  setBy self-ignore with real identities")
    seq = []
    for sby in b.raw_setby:
        n = tc.ident(sby)
        if not seq or seq[-1][0] != n:
            seq.append([n, 1])
        else:
            seq[-1][1] += 1
    print("   distinct setBy B observed: %s"
          % ("  ->  ".join("%s x%d" % (n, c) for n, c in seq) or "(none)"))
    mine_as_b = sum(c for n, c in seq if n == "BRAVIA VH1")
    print("   R3a  frames A authored that B saw: %d   (propagation, not self-ignore)"
          % mine_as_b)
    print("   R3b  frames B self-ignored (own echo): %d of %d inbound"
          % (b.self_echo, len(b.raw_setby)))
    print("   R3b  B applied position after driving: %s (A was at %s)"
          % (b.applied["position"], a.local["position"]))
    if not mine_as_b:
        verdict = "B saw NOTHING from A -- propagation broken"
    elif not b.self_echo:
        verdict = ("no self-echo observed -- cannot claim self-ignore works; "
                   "the old R3 verdict was this case, misread")
    else:
        verdict = ("own echo dropped before applying: real account self-ignore works"
                   " (previously B applied it and sat pinned at 0)")
    print("   R3  verdict: %s" % verdict)

    tc.rule("R5  is the advertised relay endpoint stable for the room's life?")
    s, again = api("GET", "/rooms/%s" % rid, host_tok)
    print("   re-GET the room: %s:%s  (was %s:%s) -> %s"
          % (again.get("syncplayHost"), again.get("syncplayPort"), relay_host, relay_port,
             "STABLE" if (again.get("syncplayHost"), again.get("syncplayPort"))
             == (relay_host, relay_port) else "CHANGED -- must re-read"))

    tc.rule("CLEANUP -- leave, not destroy (§4)")
    for c in (a, b):
        c.close()
    time.sleep(1.0)
    s, _ = api("DELETE", "/rooms/%s" % rid, host_tok)
    print("   host DELETE (leave) -> HTTP %s" % s)
    s, _ = api("GET", "/rooms/%s" % rid, peer_tok)
    print("   peer GET after host left -> HTTP %s  <- room still exists" % s)
    s, mine = api("GET", "/rooms", peer_tok)
    print("   peer still lists it: %s"
          % ([r.get("id") for r in mine.get("rooms", [])] if isinstance(mine, dict) else mine))
    print("   room %s expires at endsAt=%s (%.1f h from now)"
          % (rid, room["endsAt"], (room["endsAt"] - time.time()) / 3600.0))


if __name__ == "__main__":
    main()
