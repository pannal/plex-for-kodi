# coding=utf-8
"""Watch Together rooms REST model — https://together.plex.tv (§4).

No Kodi: the plex.tv account token is injected by the caller. Transport is
injectable for tests. Rules baked in from §4: DELETE means "leave" (never
"destroy"); a room you left reads 403 while an expired one reads 404;
never read or log a 401 body — it leaks internal service URLs.
"""

from __future__ import absolute_import

import collections
import threading
import requests

BASE = "https://together.plex.tv"


class WatchTogetherError(Exception):
    pass


class AuthError(WatchTogetherError):
    """401 — message carries method+path only, never the response body."""


class NotMember(WatchTogetherError):
    """403 on GET — you are not (or no longer) in this room."""


class RoomGone(WatchTogetherError):
    """404 — expired (endsAt passed) or never existed. Never retry."""


class Room(object):
    def __init__(self, data):
        self.raw = data
        self.id = data.get("id")
        self.title = data.get("title")
        self.source_uri = data.get("sourceUri") or data.get("source")
        self.created_by = data.get("createdBy")
        self.starts_at = data.get("startsAt", 0)
        # null endsAt = no scheduled end; inf keeps ended() total (0/None
        # would make every comparison True or TypeError)
        self.ends_at = data.get("endsAt") or float("inf")
        self.syncplay_host = data.get("syncplayHost")
        self.syncplay_port = data.get("syncplayPort")
        self.users = data.get("users") or []

    @property
    def user_ids(self):
        # users[] can contain the inviter twice — treat as a set (§4)
        return set(u.get("id") for u in self.users if isinstance(u, dict))

    @property
    def participants(self):
        seen = {}
        for user in self.users:
            if isinstance(user, dict) and user.get("id") is not None:
                seen.setdefault(user["id"], user)
        return list(seen.values())

    def ended(self, now=None):
        import time as _time
        return (now if now is not None else _time.time()) >= self.ends_at


def _http_request(method, path, body=None, token=None):
    headers = {"Accept": "application/json", "X-Plex-Token": token or ""}
    # allow_redirects=False: never follow a 3xx with the account token —
    # requests only strips Authorization, custom headers survive the hop
    kwargs = {"headers": headers, "timeout": 15, "allow_redirects": False}
    if body is not None:
        kwargs["json"] = body
    resp = requests.request(method, BASE + path, **kwargs)
    try:
        payload = resp.json() if resp.content else None
    except ValueError:
        payload = None
    return resp.status_code, payload


class RoomsApi(object):
    """The §4 surface: list, fetch, leave, create, invite."""

    def __init__(self, token, transport=None):
        self.token = token
        self._transport = transport or _http_request

    def _req(self, method, path, body=None):
        try:
            status, payload = self._transport(method, path, body, self.token)
        except requests.RequestException as exc:
            # class name only — str(exc) can embed the URL/token query
            raise WatchTogetherError("%s %s -> %s" % (method, path,
                                                      exc.__class__.__name__))
        if status == 401:
            # §4: body is untrusted and the first 401 leaks an internal URL
            raise AuthError("%s %s -> 401" % (method, path))
        if status == 403:
            raise NotMember("%s %s -> 403" % (method, path))
        if status == 404:
            raise RoomGone("%s %s -> 404" % (method, path))
        if 300 <= status < 400:
            raise WatchTogetherError("%s %s -> HTTP %d redirect" % (method, path,
                                                                    status))
        if status >= 400:
            raise WatchTogetherError("%s %s -> HTTP %d" % (method, path, status))
        return payload

    def rooms(self):
        payload = self._req("GET", "/rooms") or {"rooms": []}
        return [Room(r) for r in payload.get("rooms") or []]

    def room(self, room_id):
        payload = self._req("GET", "/rooms/%s" % room_id)
        if not payload:
            raise WatchTogetherError("GET /rooms/%s -> empty body" % room_id)
        return Room(payload)

    def leave(self, room_id):
        """DELETE is per-participant leave (§4); 404 means already gone."""
        try:
            self._req("DELETE", "/rooms/%s" % room_id)
        except RoomGone:
            pass

    def create(self, source_uri, title, users=None):
        payload = self._req("POST", "/rooms", {"sourceUri": source_uri,
                                               "title": title,
                                               "users": users})
        if not payload:
            # an empty/non-JSON 2xx would make Room(None) an AttributeError,
            # which escapes the caller's WatchTogetherError handling
            raise WatchTogetherError("POST /rooms -> empty body")
        return Room(payload)

    def invite(self, room_id, user_ids):
        # §4: a non-numeric id makes the server leak a Postgres 500 — reject
        # locally before any request goes out. bool is an int subclass: a bool
        # id would serialize as true/false and leak the same 500.
        if not all(isinstance(i, int) and not isinstance(i, bool)
                   for i in user_ids):
            raise ValueError("user ids must be integers")
        payload = self._req("POST", "/rooms/%s/invite" % room_id,
                            {"users": list(user_ids)})
        if not payload:
            raise WatchTogetherError("POST /rooms/%s/invite -> empty body"
                                     % room_id)
        return Room(payload)


BACKOFF = (1.0, 2.0, 4.0, 8.0, 30.0)
TICK = 0.1
POLL = 15.0
HEARTBEAT = 1.0   # §5.5: one State per second, the relay's liveness gate
STABLE = 10.0     # a connection up this long counts as healthy: reset backoff
SYNC_HOLD = 10.0  # hold outbound States until synced (well under the 13s reap)


class SessionSupervisor(object):
    def __init__(self, room, identity, token, ws_factory, transport=None,
                 clock=None, abort=None, log=None):
        from . import syncplay
        self.room = room
        self.identity = identity
        self.api = RoomsApi(token, transport=transport)
        self.ws_factory = ws_factory
        if clock is None:
            import time

            class _Clock(object):
                def time(self):
                    return time.time()

                def monotonic(self):
                    return time.monotonic()

            clock = _Clock()
        self.clock = clock
        if abort is None:
            def abort():
                return False
        self.abort = abort
        if log is None:
            def log(msg):
                pass
        self.log = log

        self.on_state = None
        self.on_roster = None
        self.on_disconnected = None
        self.on_gone = None
        self.on_event = None
        self.on_ready = None

        self.session = None
        self.connected = False
        self._local = None
        self._gone = False
        self._stop = threading.Event()
        self._thread = None
        self._client = None
        self._heartbeat = None
        self._hb_stop = None
        # inbound frames are queued by the WS reader thread and processed on
        # the supervisor thread: a remote apply (seek) can block for seconds
        # and must not stall frame reads (§5.8)
        self._inbox = collections.deque()
        self._inbox_lock = threading.Lock()
        self._inbox_event = threading.Event()
        self._seek_pending = False
        self._ready = False         # §6.4 readiness; re-announced per connection
        self._ready_sent = None
        self._synced = False        # hold States until the first room State is applied
        self._opened_at = None

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="wt-supervisor")
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        """Idempotent; safe to call from the supervisor thread itself (no join)."""
        self._stop.set()
        client, self._client = self._client, None
        if client:
            try:
                client.close()
            except Exception:
                pass
        self._stop_heartbeat()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        self._thread = None
        self._client = None

    def _stopping(self):
        return self._stop.is_set() or self.abort()

    def outbound_state(self, local):
        """Store the latest local snapshot. The 1 Hz loop on the supervisor
        thread is the single State sender (§5.5) — sending here too, with a
        bridge that also ticks at 1 Hz, would double the frame rate."""
        self._local = local
        return self.connected

    def request_seek(self):
        """Flag the next outbound State as a seek command (§5.6). The bridge
        calls this on a local seek; exactly one tick carries doSeek: true."""
        self._seek_pending = True

    def send_now(self):
        """Send the current snapshot immediately. A local play/pause/seek must
        reach the relay before the next 1 Hz beat, or a peer's in-flight State
        reverts it (last-setBy wins, but only once ours lands). Thread-safe."""
        self._send_state()

    def mark_synced(self):
        """The bridge has applied the room's position: our own position is now
        meaningful and may be published."""
        self._synced = True

    def set_ready(self, ready, manually=False):
        """Report readiness, but only when it changes (§6.4). `manually` marks
        a user-pressed play, which always goes out even if the value matches."""
        ready = bool(ready)
        if not manually and ready == self._ready_sent:
            return
        from . import syncplay
        self._ready = ready
        self._ready_sent = ready
        self._send(syncplay.set_ready(ready, manually_initiated=manually))

    def _inbox_push(self, text):
        with self._inbox_lock:
            # stamp at receive: a blocking apply ahead of it must not inflate
            # this frame's client_rtt (§6.1)
            self._inbox.append((text, self.clock.monotonic()))
            if len(self._inbox) > 512:
                self._inbox.popleft()
                self.log("Watch Together: inbound backlog dropped a frame")
        self._inbox_event.set()

    def _inbox_drain(self):
        session = self.session
        while True:
            with self._inbox_lock:
                if not self._inbox:
                    self._inbox_event.clear()
                    return
                text, mono = self._inbox.popleft()
            if session is None:
                continue
            try:
                session.on_message(text, mono)
            except Exception:
                pass

    def _loop(self):
        started = False
        failures = 0
        while not self._stopping() and not self._gone:
            if started:
                delay = BACKOFF[min(max(failures - 1, 0), len(BACKOFF) - 1)]
                if not self._sleep(delay):
                    break
            started = True
            if self._poll_room() is False:
                break
            if self._attempt():
                failures = 0
            else:
                failures += 1

    def _sleep(self, delay):
        if delay <= 0:
            return True
        end = self.clock.monotonic() + delay
        # if clock jumped past end (fake clock advanced), wake immediately
        if self.clock.monotonic() >= end:
            return True
        while self.clock.monotonic() < end:
            if self._stopping():
                return False
            rem = end - self.clock.monotonic()
            if rem <= 0:
                return True
            w = min(0.1, rem)
            self._stop.wait(w)
        return True

    def _mark_gone(self):
        if self._gone:
            return
        self._gone = True
        if self.on_gone:
            try:
                self.on_gone()
            except Exception:
                pass

    def _poll_room(self):
        try:
            fresh = self.api.room(self.room.id)
        except (RoomGone, NotMember, AuthError) as exc:
            self.log("Watch Together: room unavailable ({0})".format(exc.__class__.__name__))
            self._mark_gone()
            return False
        except WatchTogetherError as exc:
            self.log("Watch Together: room refresh failed ({0})".format(exc.__class__.__name__))
            return True
        self.room = fresh
        if self.on_roster:
            try:
                self.on_roster(fresh)
            except Exception:
                pass
        return True

    def _attempt(self):
        state = {"open": False, "ever": False, "closed": False, "opened_at": None}

        def on_open():
            state["open"] = state["ever"] = True
            state["opened_at"] = self.clock.monotonic()
            self._opened_at = state["opened_at"]
            self._synced = False
            self.connected = True
            from . import syncplay
            self._send(syncplay.hello(self.room.id, self.identity))
            self._send(syncplay.list_request())
            # §5.8/§6.4: state is per-connection — re-announce readiness and
            # the file on every (re)connect, not just the first join
            self._ready_sent = None
            self.set_ready(self._ready, manually=False)
            if self.room.source_uri:
                self._send(syncplay.set_file(self.room.source_uri))
            self._start_heartbeat()

        def on_message(text):
            # reader thread: queue only. Processing (and the remote apply it
            # triggers) runs on the supervisor thread, so a blocking seek
            # cannot stall frame reads and get us reaped (§5.8).
            self._inbox_push(text)

        def on_close(reason):
            state["open"] = False
            state["closed"] = True
            self.connected = False
            self._stop_heartbeat()

        from . import syncplay
        with self._inbox_lock:
            self._inbox.clear()
        self._inbox_event.clear()
        self._seek_pending = False      # state is per-connection (§5.8)
        self.session = syncplay.Session(self.room.id, self.identity,
                                        on_state=self.on_state,
                                        on_event=self.on_event,
                                        on_ready=self.on_ready)
        client = self.ws_factory(self.room.syncplay_host, self.room.syncplay_port,
                                 on_open, on_message, on_close)
        self._client = client
        opened = self._pump(client, state)
        try:
            client.close()
        except Exception:
            pass
        self._stop_heartbeat()
        self._client = None
        self.connected = False
        self.session = None
        if opened and not self._stopping() and not self._gone and self.on_disconnected:
            try:
                self.on_disconnected()
            except Exception:
                pass
        # only a connection that stayed up counts as healthy: an accept-then-
        # immediate-drop loop must escalate the backoff, not hammer at 1 s
        stable = bool(state["ever"] and state["opened_at"] is not None
                      and self.clock.monotonic() - state["opened_at"] >= STABLE)
        return stable

    def _pump(self, client, state):
        client.start()
        last_poll = self.clock.monotonic()
        while not self._stopping():
            if state["closed"]:
                break
            if state["open"] and self.clock.monotonic() - last_poll >= POLL:
                last_poll = self.clock.monotonic()
                if self._poll_room() is False:
                    break
            self._inbox_event.wait(TICK)
            self._inbox_drain()
        return state["ever"]

    def _start_heartbeat(self):
        self._stop_heartbeat()
        ev = threading.Event()
        self._hb_stop = ev
        thread = threading.Thread(target=self._heartbeat_loop, args=(ev,),
                                  name="wt-heartbeat")
        thread.daemon = True
        thread.start()
        self._heartbeat = thread

    def _stop_heartbeat(self):
        thread, self._heartbeat = self._heartbeat, None
        ev, self._hb_stop = self._hb_stop, None
        if ev:
            ev.set()
        if (thread is not None and thread is not threading.current_thread()
                and thread.is_alive()):
            thread.join(HEARTBEAT + 1.0)

    def _heartbeat_loop(self, ev):
        # A dedicated thread, NOT the poll loop: a slow REST poll (up to 15 s)
        # must never stall the 1 Hz State — the relay reaps a ~13 s gap (§5.8).
        # This is the single State sender; the bridge only stores the snapshot.
        while not self._stopping() and not ev.is_set():
            if ev.wait(HEARTBEAT):
                return
            if self.connected:
                self._send_state()

    def _send_state(self):
        session = self.session
        client = self._client
        if session is None or client is None or not self.connected:
            return
        # Hold the first States: publishing our pre-sync position (a freshly
        # started video at ~0) would make it the room's position and drag
        # everyone to the start. Release once the bridge has applied the room's
        # position, or after SYNC_HOLD so a session that never starts playing
        # still stays alive.
        if not self._synced:
            if (self._opened_at is not None
                    and self.clock.monotonic() - self._opened_at < SYNC_HOLD):
                return
        # seed a lobby snapshot if the bridge has not fed one yet: an empty
        # _local must never mean "send nothing" (that is the 13 s reap)
        local = dict(self._local or {"position": 0, "paused": True, "doSeek": False})
        if self._seek_pending:
            # §5.6: doSeek is a command for exactly one tick, then back to a
            # plain position report
            local["doSeek"] = True
            self._seek_pending = False
        try:
            client.send(session.outbound_state(local, self.clock.monotonic(),
                                               self.clock.time()))
        except Exception as exc:
            self.log("Watch Together: state send failed ({0})".format(exc.__class__.__name__))

    def _send(self, obj):
        client = self._client
        if client is None or not self.connected:
            return False
        try:
            client.send(obj)
            return True
        except Exception as exc:
            self.log("Watch Together: send failed ({0})".format(exc.__class__.__name__))
            return False
