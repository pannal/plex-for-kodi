# coding=utf-8
"""Tests for lib/watchtogether.py — rooms REST model (docs/watch-together.md §4)."""

from __future__ import absolute_import

import json
import time
import unittest

from lib import syncplay, watchtogether

ROOM_JSON = {
    "id": "ca8cfezmke4",
    "title": "A Fazenda – S18 • E20 – Episode 20",
    "type": "watch",
    "sourceUri": "server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
                 "com.plexapp.plugins.library/library/metadata/227117",
    "source": "server://aaaa0000bbbb1111cccc2222dddd3333eeee4444/"
              "com.plexapp.plugins.library/library/metadata/227117",
    "createdBy": 1000003,
    "startsAt": 1791128438,
    "updatedAt": 1791128438,
    "endsAt": 1791139238,
    "syncplayHost": "pop-fra00.syncplay.plex.services",
    "syncplayPort": 7776,
    "users": [
        {"id": 1000003, "username": "otherviewer", "title": "Other Viewer",
         "uuid": "aaaa000000000001", "thumb": "https://plex.tv/users/x/avatar"},
        {"id": 1000001, "username": "serverowner", "title": "Server Owner",
         "uuid": "aaaa000000000002", "thumb": "https://api.plex.tv/users/y/avatar"},
        {"id": 1000003, "username": "otherviewer", "title": "Other Viewer",
         "uuid": "aaaa000000000001", "thumb": "https://plex.tv/users/x/avatar"},
    ],
}


class FakeTransport(object):
    """Stands in for _http_request: (method, path, body, token) -> (status, obj)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, body=None, token=None):
        self.calls.append((method, path, body, token))
        return self.responses.pop(0)


class RoomModelTest(unittest.TestCase):
    def test_parses_room_fields(self):
        room = watchtogether.Room(ROOM_JSON)
        self.assertEqual(room.id, "ca8cfezmke4")
        self.assertEqual(room.syncplay_host, "pop-fra00.syncplay.plex.services")
        self.assertEqual(room.syncplay_port, 7776)
        self.assertEqual(room.created_by, 1000003)
        self.assertEqual(room.title, ROOM_JSON["title"])

    def test_source_uri_falls_back_to_source(self):
        data = dict(ROOM_JSON)
        del data["sourceUri"]
        room = watchtogether.Room(data)
        self.assertIn("metadata/227117", room.source_uri)

    def test_users_are_a_set_even_when_inviter_duplicated(self):
        # §4: users[] can contain the same id twice — treat as a set
        room = watchtogether.Room(ROOM_JSON)
        self.assertEqual(room.user_ids, {1000003, 1000001})

    def test_participants_dedup(self):
        room = watchtogether.Room(ROOM_JSON)
        self.assertEqual(len(room.participants), 2)

    def test_ended_uses_ends_at(self):
        room = watchtogether.Room(ROOM_JSON)
        self.assertFalse(room.ended(now=ROOM_JSON["endsAt"] - 1))
        self.assertTrue(room.ended(now=ROOM_JSON["endsAt"]))

    def test_explicit_null_ends_at_does_not_crash(self):
        room = watchtogether.Room(dict(ROOM_JSON, endsAt=None))
        self.assertFalse(room.ended(now=1))


class RoomsApiTest(unittest.TestCase):
    def api(self, *responses):
        transport = FakeTransport(list(responses))
        return watchtogether.RoomsApi(token="tok", transport=transport), transport

    def test_rooms_parses_list(self):
        api, transport = self.api((200, {"rooms": [ROOM_JSON]}))
        rooms = api.rooms()
        self.assertEqual([r.id for r in rooms], ["ca8cfezmke4"])
        self.assertEqual(transport.calls[0][:2], ("GET", "/rooms"))
        self.assertEqual(transport.calls[0][3], "tok")

    def test_rooms_empty_is_empty_list_not_error(self):
        # §4: GET /rooms with no active rooms -> 200 {"rooms":[]}
        api, _ = self.api((200, {"rooms": []}))
        self.assertEqual(api.rooms(), [])

    def test_room_fetch(self):
        api, transport = self.api((200, ROOM_JSON))
        room = api.room("ca8cfezmke4")
        self.assertEqual(room.id, "ca8cfezmke4")
        self.assertEqual(transport.calls[0][:2], ("GET", "/rooms/ca8cfezmke4"))

    def test_403_maps_to_not_member(self):
        api, _ = self.api((403, "you do not have access to that room"))
        with self.assertRaises(watchtogether.NotMember):
            api.room("ca8cfezmke4")

    def test_404_maps_to_room_gone(self):
        api, _ = self.api((404, "room not found not found!"))
        with self.assertRaises(watchtogether.RoomGone):
            api.room("ca8cfezmke4")

    def test_401_maps_to_auth_error_and_never_carries_the_body(self):
        # §4: never log/read a 401 body — the first one leaks an internal URL
        api, _ = self.api((401, "Request failed with status code 401 "
                                "(Unauthorized): GET http://my-plex-api"
                                ".plex-tv.svc.cluster.local:8080/..."))
        with self.assertRaises(watchtogether.AuthError) as ctx:
            api.rooms()
        self.assertNotIn("cluster.local", str(ctx.exception))
        self.assertNotIn("http", str(ctx.exception))
        self.assertEqual(ctx.exception.args, ("GET /rooms -> 401",))

    def test_3xx_is_an_error_not_a_success(self):
        api, _ = self.api((302, {"Location": "http://evil"}))
        with self.assertRaises(watchtogether.WatchTogetherError):
            api.room("x")

    def test_network_failure_maps_to_watchtogether_error(self):
        def boom(method, path, body=None, token=None):
            raise watchtogether.requests.ConnectionError("boom")

        api = watchtogether.RoomsApi(token="tok", transport=boom)
        with self.assertRaises(watchtogether.WatchTogetherError) as ctx:
            api.rooms()
        self.assertIn("ConnectionError", str(ctx.exception))
        self.assertNotIn("boom", str(ctx.exception))

    def test_room_empty_body_is_error(self):
        api, _ = self.api((200, None))
        with self.assertRaises(watchtogether.WatchTogetherError):
            api.room("x")

    def test_leave_sends_delete(self):
        api, transport = self.api((204, None))
        api.leave("ca8cfezmke4")
        self.assertEqual(transport.calls[0][:2], ("DELETE", "/rooms/ca8cfezmke4"))

    def test_leave_swallows_404(self):
        # second DELETE / leave of an expired room -> 404; still "gone = done"
        api, _ = self.api((404, "room not found not found!"))
        api.leave("ca8cfezmke4")

class RoomsWriteTest(unittest.TestCase):
    """Host capability: POST /rooms and POST /rooms/<id>/invite (v2, task 1)."""

    def api_with(self, status, payload):
        transport = FakeTransport([(status, payload)])
        api = watchtogether.RoomsApi(token="tok", transport=transport)
        return api, transport.calls

    def test_create_posts_source_uri_and_title(self):
        api, calls = self.api_with(201, {"id": "r1", "title": "T"})
        room = api.create("server://m/com.plexapp.plugins.library/library/metadata/1", "T")
        self.assertEqual(room.id, "r1")
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/rooms")
        self.assertTrue(calls[0][2]["sourceUri"].startswith("server://"))

    def test_invite_posts_user_ids(self):
        api, calls = self.api_with(200, {"id": "r1", "users": []})
        api.invite("r1", [1000002, 1000003])
        self.assertEqual(calls[0][1], "/rooms/r1/invite")
        self.assertEqual(calls[0][2], {"users": [1000002, 1000003]})

    def test_invite_rejects_non_numeric_ids_without_requesting(self):
        api, calls = self.api_with(200, {"id": "r1"})
        with self.assertRaises(ValueError):
            api.invite("r1", ["NaN"])
        self.assertEqual(calls, [])          # never reaches the 500-leaking path

    def test_invite_rejects_bool_ids(self):
        # bool is an int subclass but serializes as true/false -> the same 500
        api, calls = self.api_with(200, {"id": "r1"})
        with self.assertRaises(ValueError):
            api.invite("r1", [True])
        self.assertEqual(calls, [])

    def test_create_empty_body_is_error(self):
        api, _ = self.api_with(201, None)
        with self.assertRaises(watchtogether.WatchTogetherError):
            api.create("server://x", "T")

    def test_invite_empty_body_is_error(self):
        api, _ = self.api_with(200, None)
        with self.assertRaises(watchtogether.WatchTogetherError):
            api.invite("r1", [1000002])

    def test_create_401_raises_auth_error(self):
        api, _ = self.api_with(401, None)
        with self.assertRaises(watchtogether.AuthError):
            api.create("server://x", "T")


class StubTransport(object):
    """RoomsApi transport that always answers from ROOM_JSON (or a status)."""

    def __init__(self, data=ROOM_JSON, status=200):
        self.data = data
        self.status = status
        self.calls = []

    def __call__(self, method, path, body=None, token=None):
        self.calls.append((method, path, token))
        if method == "DELETE":
            return 200, None
        if self.status != 200:
            return self.status, None
        if path == "/rooms":
            return 200, {"rooms": [self.data]}
        return 200, self.data


class FakeClient(object):
    """Stands in for ws.WSClient: start() emulates connect, send() records."""

    def __init__(self, factory, host, port, on_open, on_message, on_close, opens):
        self.factory = factory
        self.host = host
        self.port = port
        self.on_open = on_open
        self.on_message = on_message
        self.on_close = on_close
        self.opens = opens
        self.opened = False
        self.closed = None
        self.sent = []

    def start(self):
        if self.opens:
            self.opened = True
            self.on_open()
        else:
            self.closed = "refused"
            self.on_close("refused")

    def send(self, obj):
        if not self.opened or self.closed is not None:
            raise RuntimeError("not connected")
        self.sent.append(obj)

    def close(self):
        if self.opened and self.closed is None:
            self.closed = "closed"
            self.on_close("closed")

    def drop(self):
        """Remote hangup: socket dies without us calling close()."""
        if self.closed is None:
            self.closed = "dropped"
            self.on_close("dropped")

    def states(self):
        return [m for m in self.sent if "State" in m]


class FakeWSFactory(object):
    def __init__(self, opens=True):
        self.opens = opens
        self.clients = []
        self.times = []

    def __call__(self, host, port, on_open, on_message, on_close):
        self.times.append(time.monotonic())
        client = FakeClient(self, host, port, on_open, on_message, on_close,
                            opens=self.opens)
        self.clients.append(client)
        return client


def wait_for(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class SessionSupervisorTest(unittest.TestCase):
    """Offline tests for lib/watchtogether.SessionSupervisor (spec: phase 2)."""

    def setUp(self):
        self._saved = (watchtogether.POLL, watchtogether.BACKOFF, watchtogether.TICK)
        watchtogether.POLL = 0.2       # exercised inside a couple of seconds
        watchtogether.BACKOFF = (0.02, 0.04, 0.08)
        watchtogether.TICK = 0.01
        self.sup = None

    def tearDown(self):
        (watchtogether.POLL, watchtogether.BACKOFF, watchtogether.TICK) = self._saved
        if self.sup:
            self.sup.stop(timeout=3.0)

    def make(self, transport=None, factory=None):
        self.transport = transport if transport is not None else StubTransport()
        self.factory = factory if factory is not None else FakeWSFactory()
        self.sup = watchtogether.SessionSupervisor(
            watchtogether.Room(ROOM_JSON), "me-identity", "token",
            self.factory, transport=self.transport)
        return self.sup

    def open_client(self):
        self.assertTrue(wait_for(lambda: self.factory.clients and self.factory.clients[0].opened),
                        "supervisor never opened a socket")
        return self.factory.clients[0]

    def test_on_open_sends_hello_list_ready(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.assertTrue(wait_for(lambda: len(client.sent) >= 3))
        self.assertEqual(client.sent[0], syncplay.hello(ROOM_JSON["id"], "me-identity"))
        self.assertEqual(client.sent[1], syncplay.list_request())
        self.assertEqual(client.sent[2],
                         syncplay.set_ready(False, manually_initiated=False))

    def test_set_ready_is_sent_only_on_change(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.assertTrue(wait_for(lambda: syncplay.set_ready(
            False, manually_initiated=False) in client.sent))

        def ready_frames():
            return sum(1 for m in client.sent
                       if "Set" in m and "ready" in m["Set"])

        before = ready_frames()
        sup.set_ready(False)                 # unchanged: nothing on the wire
        self.assertEqual(ready_frames(), before)
        sup.set_ready(True)
        self.assertTrue(wait_for(lambda: syncplay.set_ready(
            True, manually_initiated=False) in client.sent))

    def test_manual_ready_always_goes_out(self):
        # a user-pressed play must reach the relay even if isReady already
        # matched (manuallyInitiated is the signal)
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.assertTrue(wait_for(lambda: syncplay.set_ready(
            False, manually_initiated=False) in client.sent))
        sup.set_ready(False, manually=True)
        self.assertTrue(wait_for(lambda: syncplay.set_ready(
            False, manually_initiated=True) in client.sent))

    def test_on_open_announces_the_rooms_file(self):
        # §5.8: state is per-connection — the file must be re-announced on
        # every (re)connect, not just the first join
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.assertTrue(wait_for(lambda: syncplay.set_file(ROOM_JSON["sourceUri"])
                                 in client.sent))

    def test_request_seek_marks_exactly_one_outbound_state(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        sup.mark_synced()
        sup.request_seek()
        self.assertTrue(wait_for(lambda: any(
            m["State"]["playstate"]["doSeek"] for m in client.states())))
        marked = [m for m in client.states() if m["State"]["playstate"]["doSeek"]]
        self.assertEqual(len(marked), 1, "doSeek is true for exactly one tick (§5.6)")

    def test_outbound_state_before_connect_only_stores(self):
        sup = self.make()
        self.assertFalse(sup.outbound_state({"position": 1, "paused": True}))
        self.assertEqual(sup._local["position"], 1)

    def test_outbound_state_sends_while_connected(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        sup.mark_synced()
        self.assertTrue(sup.outbound_state(
            {"position": 42, "paused": False, "doSeek": False}))
        # the supervisor's 1 Hz loop is the single sender (§5.5)
        self.assertTrue(wait_for(lambda: any(
            m["State"]["playstate"]["position"] == 42 for m in client.states())))
        state = client.states()[-1]
        self.assertEqual(state["State"]["playstate"]["paused"], False)

    def test_states_are_held_until_synced(self):
        # a pre-sync position must never be published: it would become the
        # room's position and drag everyone to the start (§5.5)
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.assertFalse(client.states(), "no State before the room is applied")
        sup.mark_synced()
        self.assertTrue(wait_for(lambda: client.states()),
                        "States flow once the room position is applied")

    def test_outbound_state_only_stores_never_sends(self):
        # the 1 Hz heartbeat is the single sender (§5.5)
        sup = self.make()
        sup.start()
        client = self.open_client()
        sup.outbound_state({"position": 7, "paused": True})
        self.assertFalse(any(m["State"]["playstate"]["position"] == 7
                             for m in client.states()),
                         "outbound_state must not put a frame on the wire")

    def test_outbound_state_after_drop_is_inert(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        client.drop()
        self.assertTrue(wait_for(lambda: not sup.connected))
        self.assertFalse(sup.outbound_state({"position": 5, "paused": True}))

    def test_failed_connects_back_off(self):
        factory = FakeWSFactory(opens=False)
        self.make(factory=factory)
        self.sup.start()
        self.assertTrue(wait_for(lambda: len(factory.clients) >= 4, timeout=5.0),
                        "supervisor stopped re-dialing")
        gaps = [b - a for a, b in zip(factory.times, factory.times[1:])]
        # BACKOFF = (0.02, 0.04, 0.08): each gap is wider than the one before
        self.assertGreaterEqual(gaps[1], gaps[0] + 0.005)
        self.assertGreaterEqual(gaps[2], gaps[1] + 0.005)

    def test_quick_drops_do_not_reset_the_backoff_ladder(self):
        # a socket that opens then drops immediately is not "healthy": the
        # ladder must keep escalating instead of hammering at the base delay
        watchtogether.BACKOFF = (0.05, 0.1, 0.2, 0.4)
        factory = FakeWSFactory()
        self.make(factory=factory)
        self.sup.start()
        for n in range(4):
            self.assertTrue(wait_for(lambda n=n: len(factory.clients) > n
                                     and factory.clients[n].opened))
            factory.clients[n].drop()
        gaps = [b - a for a, b in zip(factory.times, factory.times[1:])]
        self.assertGreaterEqual(gaps[2], gaps[0] + 0.005)

    def test_drop_fires_on_disconnected_then_redials(self):
        factory = FakeWSFactory()
        sup = self.make(factory=factory)
        events = []
        sup.on_disconnected = lambda: events.append("disc")
        sup.start()
        client = self.open_client()
        client.drop()
        self.assertTrue(wait_for(lambda: "disc" in events))
        self.assertTrue(wait_for(lambda: len(factory.clients) >= 2))
        self.assertTrue(wait_for(lambda: factory.clients[1].opened))

    def test_session_is_fresh_per_attempt(self):
        factory = FakeWSFactory()
        sup = self.make(factory=factory)
        sup.start()
        client = self.open_client()
        first = sup.session
        self.assertIsNotNone(first)
        client.drop()
        self.assertTrue(wait_for(lambda: len(factory.clients) >= 2
                                 and factory.clients[1].opened))
        self.assertIsNot(sup.session, first, "a reconnect must be a fresh session (§5.8)")

    def test_file_is_re_announced_on_reconnect(self):
        factory = FakeWSFactory()
        sup = self.make(factory=factory)
        sup.start()
        self.open_client().drop()
        self.assertTrue(wait_for(lambda: len(factory.clients) >= 2
                                 and factory.clients[1].opened))
        self.assertTrue(wait_for(lambda: syncplay.set_file(ROOM_JSON["sourceUri"])
                                 in factory.clients[1].sent))

    def test_seek_pending_does_not_survive_reconnect(self):
        factory = FakeWSFactory()
        sup = self.make(factory=factory)
        sup.start()
        self.open_client()
        sup.request_seek()
        self.factory.clients[0].drop()
        self.assertTrue(wait_for(lambda: len(factory.clients) >= 2
                                 and factory.clients[1].opened))
        self.assertFalse(any(m["State"]["playstate"]["doSeek"]
                             for m in factory.clients[1].states()),
                         "doSeek is per-connection state (§5.8)")

    def test_poll_delivers_rest_room(self):
        sup = self.make()
        rooms = []
        sup.on_roster = rooms.append
        sup.start()
        self.assertTrue(wait_for(lambda: rooms))
        self.assertEqual(rooms[0].id, ROOM_JSON["id"])
        self.assertEqual(sup.room.syncplay_host, ROOM_JSON["syncplayHost"])

    def test_relay_state_reaches_on_state(self):
        sup = self.make()
        states = []
        sup.on_state = states.append
        sup.start()
        client = self.open_client()
        client.on_message(json.dumps({"State": {"playstate": {
            "position": 7.5, "paused": True, "doSeek": False,
            "setBy": "someone-else"}}}))
        self.assertTrue(wait_for(lambda: states))
        self.assertEqual(states[0]["position"], 7.5)

    def test_relay_ready_reaches_on_ready(self):
        # §6.4: the bridge learns a peer readied up through the supervisor's
        # on_ready, not by reading the session directly
        sup = self.make()
        seen = []
        sup.on_ready = lambda key, is_ready: seen.append((key, is_ready))
        sup.start()
        client = self.open_client()
        identity = syncplay.build_identity("d", "n", 1)
        client.on_message(json.dumps({"Set": {"ready": {
            "username": identity, "isReady": True}}}))
        self.assertTrue(wait_for(lambda: seen))
        self.assertEqual(seen[0], (identity, True))

    def test_gone_room_fires_on_gone_once_and_never_leaves(self):
        transport = StubTransport(status=404)
        self.make(transport=transport)
        gones = []
        self.sup.on_gone = lambda: gones.append(1)
        self.sup.start()
        self.assertTrue(wait_for(lambda: not self.sup._thread.is_alive()))
        self.assertEqual(gones, [1])
        self.assertEqual(len(self.factory.clients), 0, "must not dial a gone room")
        self.assertFalse(any(c[0] == "DELETE" for c in transport.calls),
                         "on_gone never calls leave() (§4)")

    def test_not_member_is_gone_too(self):
        self.make(transport=StubTransport(status=403))
        gones = []
        self.sup.on_gone = lambda: gones.append(1)
        self.sup.start()
        self.assertTrue(wait_for(lambda: gones == [1]))
        self.assertTrue(wait_for(lambda: not self.sup._thread.is_alive()))

    def test_dead_token_is_gone_never_retried(self):
        self.make(transport=StubTransport(status=401))
        gones = []
        self.sup.on_gone = lambda: gones.append(1)
        self.sup.start()
        self.assertTrue(wait_for(lambda: gones == [1]))
        self.assertTrue(wait_for(lambda: not self.sup._thread.is_alive()))

    def test_transient_poll_failure_keeps_the_socket(self):
        sup = self.make()
        sup.start()
        client = self.open_client()
        self.transport.status = 500          # REST blip mid-session
        self.assertTrue(wait_for(lambda: self.transport.calls.count(("GET", "/rooms/ca8cfezmke4", "token")) >= 2))
        self.assertTrue(sup.connected)
        self.assertEqual(len(self.factory.clients), 1)

    def test_stop_interrupts_backoff(self):
        watchtogether.BACKOFF = (5.0,)
        self.make(factory=FakeWSFactory(opens=False))
        self.sup.start()
        self.assertTrue(wait_for(lambda: len(self.factory.clients) == 1))
        started = time.monotonic()
        self.sup.stop(timeout=3.0)
        self.assertLess(time.monotonic() - started, 2.0,
                        "stop() must not sit behind a backoff sleep")
        self.assertIsNone(self.sup._thread)

    def test_stop_is_idempotent(self):
        self.make()
        self.sup.stop()
        self.sup.stop()
        self.assertIsNone(self.sup._thread)
