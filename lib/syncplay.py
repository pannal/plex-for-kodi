# coding=utf-8
"""Plex Watch Together syncplay session — protocol logic.

No Kodi imports and no sockets: transport is injected. Feed parsed JSON
messages to Session.on_message(); pull outbound messages from
Session.outbound_state() on a steady 1 Hz cadence. Protocol reference:
docs/watch-together.md §5–§6.
"""

from __future__ import absolute_import

import json
import time

VERSION = "1.6.4"
MAX_IDENTITY_BYTES = 149   # relay blind-truncates at 150 (§5.1); stay under
SEEK_BEHIND = -1.75        # §6.2 thresholds
SEEK_AHEAD = 4.0
TEMPO_DIFF = 1.5
TEMPO_RATE = 0.95


def build_identity(device_identifier, device_name, user_id):
    """The double-encoded identity string (§5.1). Compact, under 150 bytes."""
    ident = json.dumps(
        {"deviceIdentifier": device_identifier,
         "deviceName": device_name,
         "userID": str(user_id)},
        separators=(",", ":"))
    if len(ident.encode("utf-8")) > MAX_IDENTITY_BYTES:
        raise ValueError(
            "identity is %d bytes; the relay truncates at 150 and the result "
            "is unparseable — shorten deviceName" % len(ident.encode("utf-8")))
    return ident


def strip_identity(raw):
    """Strip the relay's collision-ladder underscores before parsing (§5.1)."""
    if isinstance(raw, str):
        return raw.rstrip("_")
    return raw


def is_self(set_by, identity):
    """True when setBy resolves to the identity WE sent (§5.5).

    The relay echoes our own State back with setBy filled in; applying it
    makes us fight our own playback. Matched as a subset on str() so it
    survives key reordering, extra fields and int-vs-str ids — full dict
    equality silently stops self-ignoring on any of those.
    """
    if not set_by or not identity:
        return False
    try:
        theirs = json.loads(strip_identity(set_by))
        mine = json.loads(strip_identity(identity))
    except (ValueError, TypeError):
        return False
    if not isinstance(theirs, dict) or not isinstance(mine, dict):
        return False
    return all(k in theirs and str(theirs[k]) == str(v) for k, v in mine.items())


def hello(room, identity, version=VERSION):
    """Hello, sent immediately on connect (§5.2)."""
    return {"Hello": {"room": {"name": room},
                      "username": identity,
                      "version": version}}


def list_request():
    """Roster snapshot request (§5.3)."""
    return {"List": {}}


def set_ready(is_ready, manually_initiated=True):
    """Readiness for the lobby/ready flow — sent only on change (§6.4)."""
    return {"Set": {"ready": {"isReady": bool(is_ready),
                              "manuallyInitiated": bool(manually_initiated)}}}


def set_file(uri, playing=False):
    """Announce what is playing (§5.4). name is double-encoded JSON."""
    inner = json.dumps({"ads": {"playing": bool(playing)}, "uri": uri},
                       separators=(",", ":"))
    return {"Set": {"file": {"name": inner}}}


def ready_member_ids(roster):
    """userIDs (as str) of roster entries with isReady is True."""
    ids = set()
    for identity, entry in roster.items():
        if not (isinstance(entry, dict) and entry.get("isReady") is True):
            continue
        try:
            parsed = json.loads(strip_identity(identity))
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("userID") is not None:
            ids.add(str(parsed["userID"]))
    return ids


def members_ready(member_ids, roster):
    """True only when every member id is present AND ready."""
    return set(map(str, member_ids)) <= ready_member_ids(roster)


class Latency(object):
    """§6.1 latency compensation + forward-delay estimation.

    serverRtt is our own clock skew, not the relay's (§5.5): it is
    relayNow − the epoch latencyCalculation WE sent, so a fresh epoch stamp
    every tick is what keeps it meaningful.
    """

    def __init__(self):
        self.avg_rtt = 0.0
        self.forward_delay = 0.0
        self.client_rtt = 0.0     # last accepted sample (echoed outbound)
        self.server_rtt = 0.0     # last value the relay reported (echoed back)

    def on_state(self, ping, now_mono):
        sr = ping.get("serverRtt")
        if isinstance(sr, (int, float)):
            self.server_rtt = sr
        lc = ping.get("clientLatencyCalculation")
        if not isinstance(lc, (int, float)):
            return
        client_rtt = now_mono - lc
        if client_rtt < 0 or (isinstance(sr, (int, float)) and sr < 0):
            return                      # §6.1: skip negative samples
        self.client_rtt = client_rtt
        if self.avg_rtt == 0:
            self.avg_rtt = sr if isinstance(sr, (int, float)) and sr >= 0 else 0.0
        self.avg_rtt = 0.85 * self.avg_rtt + 0.15 * client_rtt
        self.forward_delay = self.avg_rtt / 2.0
        if isinstance(sr, (int, float)) and sr < client_rtt:
            self.forward_delay += client_rtt - sr   # clock-skew correction


def sync_action(local_position, remote_position, paused, forward_delay):
    """§6.2: decide what the player must do to converge. Pure arithmetic.

    Returns None (stay), ("seek", target) or ("tempo", 0.95). The 0.95 is a
    tempo change (Kodi 21+ only, feature-detected in Phase 2) — callers may
    degrade it to a seek on older Kodi (§9).
    """
    target = remote_position + (0 if paused else forward_delay)
    diff = local_position - target
    if diff >= SEEK_AHEAD or diff <= SEEK_BEHIND:
        return ("seek", target)
    if diff > TEMPO_DIFF:
        return ("tempo", TEMPO_RATE)
    return None


class Session(object):
    """Protocol session for one connection. Transport-agnostic (no sockets).

    on_state(remote)  — a remote (non-self) State was applied, per frame
    on_roster(roster) — a List snapshot arrived
    on_event(kind, key) — "left"/"joined" for a roster identity (§5.8)
    on_ready(key, is_ready) — a Set{ready} updated an entry's readiness

    An exception in a callback propagates to the transport loop and tears
    down the connection (surfaced as WSClient's on_close reason) — callbacks
    must not raise.

    Drive outbound_state() at a steady 1 Hz: your echo cadence is every
    peer's smoothness (§5.5).
    """

    def __init__(self, room, identity, on_state=None, on_roster=None,
                 on_event=None, on_ready=None):
        self.room = room
        self.identity = identity
        self.on_state = on_state
        self.on_roster = on_roster
        self.on_event = on_event
        self.on_ready = on_ready
        self.relay_ignore = 0       # ignoringOnTheFly.server, live from wire (§5.9)
        # ignoringOnTheFly.client: 1 means "apply to me but do not rebroadcast".
        # v1 emits no local drift nudge, so this stays 0 (deferred with tempo).
        self.local_ignore = 0
        self.latency = Latency()
        self.remote = {"position": 0.0, "paused": True, "doSeek": False,
                       "setBy": None}
        self.roster = {}            # raw identity -> List entry
        self.relay_hello = None
        self.file = None            # parsed {ads, uri} of what's playing
        self.self_echo = 0

    def on_message(self, msg, now_mono=None):
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except ValueError:
                return
        if not isinstance(msg, dict):
            return
        if "Hello" in msg:
            self.relay_hello = msg["Hello"]
        elif "List" in msg:
            entries = msg["List"].get(self.room) or {}
            self.roster = dict(entries)
            # §5.4a/§5.8: a mid-session joiner learns the room's current file
            # from a peer's List entry — the relay stores no playlist
            for entry in entries.values():
                if isinstance(entry, dict):
                    self._take_file(entry.get("file"))
            if self.on_roster:
                self.on_roster(dict(self.roster))
        elif "Set" in msg:
            self._on_set(msg["Set"])
        elif "State" in msg:
            self._on_state(msg["State"], now_mono)

    def _on_set(self, sub):
        if not isinstance(sub, dict):
            return
        ready = sub.get("ready")
        if isinstance(ready, dict):
            key = ready.get("username")
            if key:
                entry = self.roster.setdefault(key, {})
                entry["isReady"] = ready.get("isReady")
                if self.on_ready:
                    self.on_ready(key, ready.get("isReady"))
        user = sub.get("user")
        if isinstance(user, dict):
            for key, entry in user.items():
                if not isinstance(entry, dict):
                    continue
                event = entry.get("event") or {}
                if "left" in event or "joined" in event:
                    kind = "left" if event.get("left") else "joined"
                    if kind == "left" and is_self(key, self.identity):
                        # §5.8: left against our own key is advisory — it is
                        # also how the relay reaps a live-but-silent socket, so
                        # it must not be read as a peer departure or a reconnect
                        pass
                    else:
                        if kind == "left":
                            self.roster.pop(key, None)
                        if self.on_event:
                            self.on_event(kind, key)
                self._take_file(entry.get("file"))
        self._take_file(sub.get("file"))

    def _take_file(self, file_obj):
        if not (isinstance(file_obj, dict) and isinstance(file_obj.get("name"), str)):
            return
        try:
            parsed = json.loads(file_obj["name"])
        except ValueError:
            return
        # §5.4a: the relay validates nothing. Only a well-formed object replaces
        # the current file — one truncated peer frame must not wipe it.
        if isinstance(parsed, dict):
            self.file = parsed

    def _on_state(self, state, now_mono=None):
        ig = state.get("ignoringOnTheFly") or {}
        if "server" in ig:
            try:
                self.relay_ignore = int(ig["server"])
            except (TypeError, ValueError):
                pass
        ping = state.get("ping") or {}
        self.latency.on_state(ping,
                              time.monotonic() if now_mono is None else now_mono)
        ps = state.get("playstate") or {}
        if is_self(ps.get("setBy"), self.identity):
            self.self_echo += 1     # §5.5: our own echo — count, never apply
            return
        for key in ("position", "paused", "doSeek"):
            if ps.get(key) is not None:
                value = ps[key]
                if key == "position":
                    try:
                        value = float(value)   # §5.5: never truncate the float
                    except (TypeError, ValueError):
                        return   # unparseable frame: applying a stale position
                                 # would seek every peer to it — drop the frame
                self.remote[key] = value
        self.remote["setBy"] = ps.get("setBy")
        if self.on_state:
            self.on_state(dict(self.remote))

    def outbound_state(self, local, now_mono=None, now_epoch=None):
        """One heartbeat frame (§5.5). Caller drives this at 1 Hz."""
        mono = time.monotonic() if now_mono is None else now_mono
        epoch = time.time() if now_epoch is None else now_epoch
        return {"State": {
            "ping": {"clientLatencyCalculation": mono,
                     "clientRtt": self.latency.client_rtt,
                     "serverRtt": self.latency.server_rtt,
                     "latencyCalculation": epoch},
            "playstate": {"doSeek": bool(local.get("doSeek", False)),
                          "paused": bool(local.get("paused", True)),
                          "position": int(local.get("position") or 0),
                          "setBy": None},
            "ignoringOnTheFly": {"client": self.local_ignore,
                                 "server": self.relay_ignore}}}
