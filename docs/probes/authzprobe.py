#!/usr/bin/env python3
"""Cloud authorisation matrix: what can a non-host account do to a room? (§11 item 14)

The last open question in the doc. Everything else in the REST surface was verified with a
single token, which can prove "an anonymous caller is refused" but can never prove "only
the host may do this" -- that needs a second *valid* account.

Tokens are read from files, never arguments, so they stay out of shell history and out of
this file. The relay needs no token at all (see §7); this is purely the cloud layer.

    ~/.plex-probe-token-host   the account that CREATES the room
    ~/.plex-probe-token        the second, non-host account

Ordering matters and is not cosmetic:
  * PATCH and invite-permission checks run BEFORE the DELETE probe, because a successful
    DELETE destroys the room and there would be nothing left to test against.
  * The host always deletes at the end, so a run leaves no room behind even if a probe
    surprises us.

Read-only against anything but throwaway rooms the run creates itself.

Usage: python3 authzprobe.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://together.plex.tv"
SOURCE_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117")
HOST_TOKEN_FILE = os.path.expanduser("~/.plex-probe-token-host")
PEER_TOKEN_FILE = os.path.expanduser("~/.plex-probe-token")


def read_token(path):
    with open(path) as fh:
        return fh.read().strip()


def call(method, path, token, body=None):
    """Return (status, parsed_or_text). Never raises for HTTP errors."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Plex-Token", token)
    req.add_header("X-Plex-Product", "PM4K")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:                                    # noqa: BLE001
        return 0, "%s: %s" % (type(e).__name__, e)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def whoami(token):
    req = urllib.request.Request("https://plex.tv/api/v2/user")
    req.add_header("X-Plex-Token", token)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:                                    # noqa: BLE001
        return {"error": repr(e)}


def rule(t):
    print("\n" + "=" * 74 + "\n== " + t + "\n" + "=" * 74, flush=True)


def show(label, status, body, keep=90):
    text = body if isinstance(body, str) else json.dumps(body)
    print("   %-46s HTTP %-3s %s" % (label, status, text[:keep].replace("\n", " ")))


def main():
    if not (os.path.exists(HOST_TOKEN_FILE) and os.path.exists(PEER_TOKEN_FILE)):
        sys.exit("need both token files: %s and %s" % (HOST_TOKEN_FILE, PEER_TOKEN_FILE))
    host = read_token(HOST_TOKEN_FILE)
    peer = read_token(PEER_TOKEN_FILE)
    if host == peer:
        sys.exit("the two token files are identical -- that tests nothing")

    rule("ACCOUNTS")
    h, p = whoami(host), whoami(peer)
    print("   host : %s (id %s)" % (h.get("username"), h.get("id")))
    print("   peer : %s (id %s)" % (p.get("username"), p.get("id")))
    for who, acct in (("host", h), ("peer", p)):
        sub = acct.get("subscription") or {}
        wt = [f for f in sub.get("features", []) if "watch-together" in f]
        print("   %s pass=%-8s WT flags=%s"
              % (who, sub.get("status") or "none", wt or "NONE"))
    if h.get("id") == p.get("id"):
        sys.exit("both tokens are the same account")

    peer_id = p["id"]

    rule("0  PEER baseline -- what can it see with no room of its own?")
    s, b = call("GET", "/rooms", peer)
    show("GET /rooms as peer", s, b)

    # A non-host can only act on a room it has been invited to, so everything below is
    # scoped to a room the HOST creates and the PEER is invited into.
    rule("1  HOST creates a throwaway room")
    s, room = call("POST", "/rooms", host, {"sourceUri": SOURCE_URI,
                                            "title": "pm4k-authz-probe", "users": None})
    show("POST /rooms as host", s, room)
    if s not in (200, 201) or not isinstance(room, dict) or "id" not in room:
        sys.exit("host could not create a room; aborting without touching anything")
    rid = room["id"]
    print("   room id: %s   relay: %s:%s" % (rid, room.get("syncplayHost"),
                                             room.get("syncplayPort")))

    rule("2  PEER tries to touch a room it was NOT invited to")
    show("GET /rooms/{id} as peer (no invite)", *call("GET", "/rooms/%s" % rid, peer))
    show("PATCH title as peer (no invite)",
         *call("PATCH", "/rooms/%s?title=peergotcha" % rid, peer))
    show("DELETE as peer (no invite)", *call("DELETE", "/rooms/%s" % rid, peer))
    show("GET /rooms/{id} as host (still alive?)", *call("GET", "/rooms/%s" % rid, host))

    rule("3  HOST invites the PEER")
    s, b = call("POST", "/rooms/%s/invite" % rid, host, {"users": [peer_id]})
    show("POST invite as host", s, b, keep=60)
    if isinstance(b, dict):
        print("   users now: %s" % [u.get("username") for u in b.get("users", [])])

    rule("4  PEER's view AFTER being invited")
    show("GET /rooms/{id} as peer", *call("GET", "/rooms/%s" % rid, peer))
    s, b = call("GET", "/rooms", peer)
    listed = [r.get("id") for r in b.get("rooms", [])] if isinstance(b, dict) else []
    print("   GET /rooms as peer -> HTTP %s lists %s  (our room listed: %s)"
          % (s, listed, rid in listed))

    rule("5  PEER, now a legitimate participant: what is it allowed to do?")
    # These run BEFORE the delete probe on purpose.
    show("PATCH title as peer", *call("PATCH", "/rooms/%s?title=peer-renamed" % rid, peer))
    s, b = call("GET", "/rooms/%s" % rid, host)
    print("   host sees title now: %r" % (b.get("title") if isinstance(b, dict) else b))
    # An absent (clearly non-existent) user id is the only third-party target this probe
    # may use; a participant trying it returns 400. That used to be misread as "invite is
    # host-gated" -- see inviteprobe.py Q6 for the correction: a participant CAN invite a
    # user it is related to, and the 400 here is the relationship/validity gate, not role.
    show("invite absent user id as peer", *call("POST", "/rooms/%s/invite" % rid, peer,
                                                {"users": [999999999]}))
    show("DELETE as PEER (invited, non-host)  <-- THE QUESTION",
         *call("DELETE", "/rooms/%s" % rid, peer))

    rule("6  Who actually killed it?")
    show("GET /rooms/{id} as host", *call("GET", "/rooms/%s" % rid, host))
    show("GET /rooms/{id} as peer", *call("GET", "/rooms/%s" % rid, peer))
    s, b = call("GET", "/rooms", host)
    print("   host GET /rooms -> %s" % ([r.get("id") for r in b.get("rooms", [])]
                                        if isinstance(b, dict) else b))

    rule("7  CLEANUP -- host deletes whatever is left")
    show("DELETE as host (cleanup)", *call("DELETE", "/rooms/%s" % rid, host))
    show("GET /rooms/{id} after cleanup", *call("GET", "/rooms/%s" % rid, host))
    show("GET /rooms as host", *call("GET", "/rooms", host))

    rule("VERDICT")
    print("   Read step 5. If 'DELETE as PEER' returned 204, ANY invited participant can")
    print("   destroy the room for everyone and host-only is a fiction. If it returned")
    print("   403/404 while the host's DELETE returned 204, authorisation is enforced.")


if __name__ == "__main__":
    main()
