# coding=utf-8
"""plex.tv / community people lookups for Watch Together.

Deliberately Kodi-free: the unit tests import this module directly, so it must
not pull in ``xbmc`` or ``lib.kodi_util``. The Kodi layer only wires it in.
"""

from __future__ import absolute_import

import json
import xml.etree.ElementTree as ET
from collections import namedtuple

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:  # Python 2
    from urllib2 import Request, urlopen, HTTPError


GRAPHQL_URL = "https://community.plex.tv/api"
SHARED_SERVERS_URL = "https://plex.tv/api/servers/{machine_id}/shared_servers"

# PM4K identity headers. CLIENT_ID is a module attribute so the Kodi caller can
# set it from plex.CLIENT_ID without this module importing Kodi.
CLIENT_ID = ""
PRODUCT = "PM4K"
PLATFORM = "Kodi"
VERSION = "1.0"

_FRIENDS_QUERY = ("query GetAllFriends { allFriendsV2 { user { avatar displayName "
                  "id idRaw username } createdAt } }")


def _http(method, url, headers, body=None):
    """Minimal stdlib transport. Never raises on HTTP errors: failures come
    back as a ``0`` status so callers can degrade."""
    req = Request(url, data=body, headers=headers)
    if method:
        req.get_method = lambda: method
    try:
        resp = urlopen(req)
    except HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return exc.code, content_type, exc.read()
    except Exception:
        return 0, "", b""
    try:
        return resp.getcode(), resp.headers.get("Content-Type", ""), resp.read()
    finally:
        resp.close()


def _headers(token):
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-plex-token": token,
        "x-plex-client-identifier": CLIENT_ID,
        "x-plex-product": PRODUCT,
        "x-plex-platform": PLATFORM,
        "x-plex-version": VERSION,
    }


def friends(token, http=None):
    """Return ``[{"id": int, "title": str, "thumb": str}]`` for the user's Plex
    friends, or ``[]`` on any failure (the picker then falls back to home
    users). Never logs the token or the response body."""
    http = http or _http
    body = json.dumps({"query": _FRIENDS_QUERY,
                       "operationName": "GetAllFriends"}).encode("utf-8")
    status, _, content = http("POST", GRAPHQL_URL, _headers(token), body)
    if not 200 <= status < 300:
        return []
    try:
        data = json.loads(content.decode("utf-8"))
        payload = data.get("data") if isinstance(data, dict) else None
        edges = payload.get("allFriendsV2") if isinstance(payload, dict) else None
        if not isinstance(edges, list):
            return []
    except (ValueError, AttributeError, TypeError):
        return []

    out = []
    for edge in edges:
        user = edge.get("user") if isinstance(edge, dict) else None
        raw = user.get("idRaw") if isinstance(user, dict) else None
        if raw is None:
            continue
        try:
            # coerce: a string idRaw would never match the int sharee ids, so
            # the friends∩sharees intersection would silently empty
            user_id = int(raw)
        except (TypeError, ValueError):
            continue
        out.append({"id": user_id,
                    "title": user.get("displayName") or user.get("username") or "",
                    "thumb": user.get("avatar", "")})
    return out


def shared_users(token, machine_id, http=None):
    """Return ``[{"id": int, "title": str}]`` for the users a server is shared
    with, or ``[]`` on any failure. Owner-only: a server shared *to* the token
    holder answers 404, which degrades to ``[]``. Never logs the token or the
    response body."""
    http = http or _http
    headers = _headers(token)
    headers["Accept"] = "application/xml"
    status, _, content = http("GET", SHARED_SERVERS_URL.format(machine_id=machine_id),
                              headers)
    if not 200 <= status < 300:
        return []
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError):
        return []

    out = []
    for node in root.iter():
        user_id = node.get("userID")
        if user_id is None:
            continue
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            continue
        out.append({"id": user_id, "title": node.get("username", "")})
    return out


Invitee = namedtuple("Invitee", "id title thumb access_unknown")


def eligible_invitees(token, machine_id, owned, home_users, self_id=None,
                      room_user_ids=(), http=None):
    """People who can be invited to a Watch Together room on this server.

    For a server the token holder *owns*, only friends who are also sharees of
    that server can reach it, so the friend list is intersected with the shared
    users by id. For a server shared *to* the holder, the sharee list cannot be
    enumerated, so every friend is offered and flagged ``access_unknown=True``.
    Home users are always offered. Self and anyone already in the room are
    dropped; ids are deduplicated, friends before home users. Degrades to home
    users alone if the friends lookup fails. Never logs the token or a body.
    """
    exclude = set(room_user_ids)
    if self_id is not None:
        exclude.add(self_id)

    friends_list = friends(token, http=http)
    rows = []
    if owned and friends_list:
        # Only sharees of the server can reach it; skip the lookup when there
        # are no friends to intersect (degrades to home users alone).
        allowed = set(u["id"] for u in shared_users(token, machine_id, http=http))
        rows = [(f, False) for f in friends_list if f["id"] in allowed]
    elif not owned:
        rows = [(f, True) for f in friends_list]
    rows.extend((h, not owned) for h in home_users)

    out = []
    seen = set()
    for user, access_unknown in rows:
        user_id = user["id"]
        if user_id in exclude or user_id in seen:
            continue
        seen.add(user_id)
        out.append(Invitee(user_id, user["title"], user["thumb"], access_unknown))
    return out
