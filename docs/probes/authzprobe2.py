#!/usr/bin/env python3
"""Follow-up: exact DELETE semantics, and what PATCH actually edits.

authzprobe.py showed DELETE returning 204 for an invited non-host while the room SURVIVED
for the creator -- so DELETE is overloaded, not "destroy". It also showed PATCH failing
with a Node internal error naming `req.body.sourceUri`, which implies PATCH wants a full
room body rather than the query params the doc claims. Both need pinning down.

Questions:
  A  Does a creator's DELETE destroy the room for the other participant too, or only strip
     the creator's own access? (authzprobe's creator-delete case had no peer left in it)
  B  Is the post-delete response 403 or 404, and does it settle? The first throwaway room
     answered 403 three times; the second answered 404. A client has to know which.
  C  Can the creator re-invite someone who left via DELETE? i.e. is leaving reversible?
  D  Which fields does PATCH actually write, and does it need a body?
  E  Is PATCH host-gated, the way invite is?

Tokens from ~/.plex-probe-token-host and ~/.plex-probe-token. Throwaway rooms only; the
host deletes every room it creates before exiting.

Usage: python3 authzprobe2.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://together.plex.tv"
SOURCE_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117")
ALT_URI = ("server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
           "com.plexapp.plugins.library/library/metadata/99999999")
HOST_TOKEN = os.path.expanduser("~/.plex-probe-token-host")
PEER_TOKEN = os.path.expanduser("~/.plex-probe-token")


def tok(p):
    with open(p) as fh:
        return fh.read().strip()


def call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("X-Plex-Token", token)
    req.add_header("X-Plex-Product", "PM4K")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:                                       # noqa: BLE001
        return 0, "%s: %s" % (type(e).__name__, e)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def mkroom(host, title):
    s, r = call("POST", "/rooms", host, {"sourceUri": SOURCE_URI, "title": title,
                                         "users": None})
    return (s, r.get("id")) if isinstance(r, dict) and r.get("id") else (s, None)


def rule(t):
    print("\n" + "=" * 74 + "\n== " + t + "\n" + "=" * 74, flush=True)


def show(label, status, body, keep=80):
    text = body if isinstance(body, str) else json.dumps(body)
    print("   %-48s HTTP %-3s %s" % (label, status, text[:keep].replace("\n", " ")))


def main():
    host, peer = tok(HOST_TOKEN), tok(PEER_TOKEN)
    s, me = call("GET", "/rooms", peer)          # cheap liveness + confirms peer token
    print("   peer token sanity: GET /rooms -> %s" % s)
    peer_id = json.loads(urllib.request.urlopen(
        urllib.request.Request("https://plex.tv/api/v2/user",
                               headers={"X-Plex-Token": peer,
                                        "Accept": "application/json"}),
        timeout=20).read().decode())["id"]
    print("   peer account id: %s" % peer_id)

    # ---------------------------------------------------------------- A
    rule("A  creator DELETE while a participant is still in the room")
    s1, r1 = mkroom(host, "pm4k-authz2-A")
    print("   room A: %s (HTTP %s)" % (r1, s1))
    call("POST", "/rooms/%s/invite" % r1, host, {"users": [peer_id]})
    show("host sees room before delete", *call("GET", "/rooms/%s" % r1, host))
    show("peer sees room before delete", *call("GET", "/rooms/%s" % r1, peer))
    show("DELETE by CREATOR", *call("DELETE", "/rooms/%s" % r1, host))
    show("host after creator delete", *call("GET", "/rooms/%s" % r1, host))
    show("PEER after creator delete  <-- did it kill them too?", *call("GET", "/rooms/%s" % r1, peer))
    s, b = call("GET", "/rooms", peer)
    print("   peer GET /rooms -> %s" % ([r.get("id") for r in b.get("rooms", [])]
                                        if isinstance(b, dict) else b))

    # ---------------------------------------------------------------- B
    rule("B  is the post-delete state 403 or 404, and does it settle?")
    s2, r2 = mkroom(host, "pm4k-authz2-B")
    call("POST", "/rooms/%s/invite" % r2, host, {"users": [peer_id]})
    call("DELETE", "/rooms/%s" % r2, host)
    for i in (1, 2, 3):
        show("host GET /rooms/%s  (attempt %d)" % (r2, i), *call("GET", "/rooms/%s" % r2, host))
        show("peer GET /rooms/%s  (attempt %d)" % (r2, i), *call("GET", "/rooms/%s" % r2, peer))
        time.sleep(2)
    call("DELETE", "/rooms/%s" % r2, host)     # idempotency of a second delete
    show("second DELETE by host", *call("DELETE", "/rooms/%s" % r2, host))

    # ---------------------------------------------------------------- C
    rule("C  can a participant who left be re-invited? (is leaving reversible)")
    s3, r3 = mkroom(host, "pm4k-authz2-C")
    call("POST", "/rooms/%s/invite" % r3, host, {"users": [peer_id]})
    show("peer in room", *call("GET", "/rooms/%s" % r3, peer))
    show("peer DELETE (= leave)", *call("DELETE", "/rooms/%s" % r3, peer))
    show("peer after leaving", *call("GET", "/rooms/%s" % r3, peer))
    show("host room survived the leave", *call("GET", "/rooms/%s" % r3, host))
    show("host re-invites peer", *call("POST", "/rooms/%s/invite" % r3, host,
                                       {"users": [peer_id]}))
    show("peer after re-invite", *call("GET", "/rooms/%s" % r3, peer))

    # ---------------------------------------------------------------- D/E
    rule("D  PATCH -- which fields does it write, and does it need a body?")
    show("PATCH no body at all", *call("PATCH", "/rooms/%s" % r3, host))
    show("PATCH query param only", *call("PATCH", "/rooms/%s?title=qparam" % r3, host))
    show("PATCH body {title}", *call("PATCH", "/rooms/%s" % r3, host, {"title": "body-title"}))
    show("PATCH body {sourceUri, title}", *call("PATCH", "/rooms/%s" % r3, host,
                                                 {"sourceUri": SOURCE_URI,
                                                  "title": "full-body-title"}))
    s, b = call("GET", "/rooms/%s" % r3, host)
    if isinstance(b, dict):
        print("   host now sees: title=%r  sourceUri=%s"
              % (b.get("title"), str(b.get("sourceUri"))[-30:]))
    show("PATCH repoints sourceUri", *call("PATCH", "/rooms/%s" % r3, host,
                                           {"sourceUri": ALT_URI, "title": "repointed"}))
    s, b = call("GET", "/rooms/%s" % r3, host)
    if isinstance(b, dict):
        print("   host now sees: title=%r  sourceUri=%s"
              % (b.get("title"), str(b.get("sourceUri"))[-30:]))

    rule("E  is PATCH host-gated, the way invite is?")
    # An ABSENT user id is the only allowed non-self, non-peer target. A participant
    # inviting it gets 400 -- but that is the relationship/validity gate (§11.9), NOT
    # host-gating. inviteprobe Q6 shows a participant CAN invite an account it is
    # related to (got 200), so invite is not host-gated either.
    show("invite absent user id as PEER", *call("POST", "/rooms/%s/invite" % r3, peer,
                                                {"users": [999999999]}))
    show("PATCH as PEER, full body", *call("PATCH", "/rooms/%s" % r3, peer,
                                           {"sourceUri": SOURCE_URI, "title": "peer-was-here"}))
    s, b = call("GET", "/rooms/%s" % r3, host)
    print("   host sees title: %r  <-- unchanged means host-gated"
          % (b.get("title") if isinstance(b, dict) else b))

    rule("CLEANUP -- every member must leave; DELETE removes only the caller")
    # DELETEs are 404 for a caller no longer in the room (already left during the probe),
    # so this is best-effort double-removal. Both members must leave or the room survives.
    for r in (r1, r2, r3):
        show("DELETE %s by peer" % r, *call("DELETE", "/rooms/%s" % r, peer))
        show("DELETE %s by host" % r, *call("DELETE", "/rooms/%s" % r, host))
    s, b = call("GET", "/rooms", host)
    print("   host rooms remaining: %s" % ([r.get("id") for r in b.get("rooms", [])]
                                           if isinstance(b, dict) else b))
    s, b = call("GET", "/rooms", peer)
    print("   peer rooms remaining: %s" % ([r.get("id") for r in b.get("rooms", [])]
                                           if isinstance(b, dict) else b))


if __name__ == "__main__":
    main()
