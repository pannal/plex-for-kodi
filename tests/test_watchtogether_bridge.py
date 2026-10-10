# coding=utf-8
"""lib/windows/watchtogether.py — the Kodi bridge (spec: phase 2).

Bridge behaviour under test: snapshot shape, the video-only guard (theme
music must never reach the relay), remote apply + echo deadline, leave/gone
teardown, lobby toasts, OSD status property. Fake player/supervisor stand in
for Kodi and the socket."""

from __future__ import absolute_import

import time

from kodienv import ENV

ENV.abort_requested = True
from lib import plexpeople, syncplay, util, watchtogether  # noqa: E402
from lib.windows import watchtogether as wtwin  # noqa: E402
from kodi_six import xbmcgui  # noqa: E402

from .base import KodiTestCase  # noqa: E402

ROOM_JSON = {
    "id": "ca8cfezmke4",
    "title": "A Fazenda – S18 • E20",
    "sourceUri": "server://x/com.plexapp.plugins.library/library/metadata/227117",
    "createdBy": 1000001,
    "startsAt": 1791128438,
    "updatedAt": 1791128438,
    "endsAt": 1791139238,
    "syncplayHost": "pop-fra00.syncplay.plex.services",
    "syncplayPort": 7776,
    "users": [
        {"id": 1000001, "username": "owner", "title": "Owner", "uuid": "u1"},
        {"id": 1000002, "username": "guest", "title": "Guest", "uuid": "u2"},
    ],
}


class FakeLatency(object):
    forward_delay = 0.0


class FakeSession(object):
    latency = FakeLatency()
    remote = {"position": 0.0}
    roster = {}


class FakeSupervisor(object):
    def __init__(self, connected=True):
        self.connected = connected
        self.session = FakeSession()
        self.room = watchtogether.Room(ROOM_JSON)
        self.sent = []
        self.stopped = False
        self.seek_requested = False
        self.ready = None
        self.ready_manual = None
        self.synced = False

    def outbound_state(self, local):
        self.sent.append(local)
        return self.connected

    def request_seek(self):
        self.seek_requested = True

    def send_now(self):
        self.sent_now = getattr(self, "sent_now", 0) + 1

    def mark_synced(self):
        self.synced = True

    def set_ready(self, ready, manually=False):
        self.ready = ready
        self.ready_manual = manually

    def stop(self, timeout=None):
        self.stopped = True


class FakeDialog(object):
    def __init__(self):
        self.seeks = []

    def doSeek(self, offset_ms):
        self.seeks.append(offset_ms)


class FakeHandler(object):
    def __init__(self):
        self.dialog = None


class FakePlayer(object):
    def __init__(self, playing=True, video="227117", position=50.0, paused=False):
        self.playing = playing
        self.video = FakeVideo(video) if video else None
        self.position = position
        self.paused = paused
        self.controls = []
        self.seek_times = []
        self.videos = []
        self.handler = FakeHandler()
        self.wt_broadcast = None
        self.wt_applying_remote = 0.0
        self.pauseAfterPlaybackStarted = False

    def playVideo(self, video, resume=False):
        self.videos.append((video, resume))

    def isPlaying(self):
        return self.playing

    def isPlayingVideo(self):
        return self.video

    def getTime(self):
        return self.position

    def control(self, action):
        self.controls.append(action)

    def seekTime(self, seconds):
        self.seek_times.append(seconds)


class FakeVideo(object):
    def __init__(self, rating_key):
        self.ratingKey = rating_key


class FakeAPI(object):
    def __init__(self, rooms=None, room=ROOM_JSON):
        self.rooms_out = rooms if rooms is not None else []
        self.room_out = room
        self.calls = []
        self.created = []
        self.leaves = []
        self.invites = []
        self.invite_result = None
        self.invite_fail_ids = set()

    def rooms(self):
        self.calls.append("rooms")
        return [watchtogether.Room(r) for r in self.rooms_out]

    def room(self, room_id):
        self.calls.append(("room", room_id))
        return watchtogether.Room(self.room_out)

    def leave(self, room_id):
        self.calls.append(("leave", room_id))
        self.leaves.append(room_id)

    def create(self, source_uri, title, users=None):
        self.created.append({"sourceUri": source_uri, "title": title,
                             "users": users})
        return watchtogether.Room(self.room_out)

    def invite(self, room_id, user_ids):
        self.invites.append((room_id, list(user_ids)))
        if self.invite_result is not None:
            raise self.invite_result
        if user_ids and user_ids[0] in self.invite_fail_ids:
            raise watchtogether.WatchTogetherError("400")
        return watchtogether.Room(self.room_out)


class FakeServer(object):
    def __init__(self, uuid):
        self.uuid = uuid


class FakeItem(object):
    """Minimal PlexObject surface the host flow reads: server.uuid, ratingKey,
    title."""

    def __init__(self, machine="m", rating_key="1", title="T"):
        self.server = FakeServer(machine) if machine is not None else None
        self.ratingKey = rating_key
        self.title = title


class FakeLobby(object):
    def __init__(self):
        self.closed = False

    def doClose(self):
        self.closed = True


class FakeBusyWindow(object):
    """Stand-in for busy.BusyWindow: the xbmcgui stub cannot build a real GUI
    window, but @busy.dialog() only needs create/show/doClose."""

    def show(self):
        pass

    def doClose(self):
        pass

    @classmethod
    def create(cls, show=True, **kwargs):
        return cls()


class FakeRoom(object):
    """Minimal room surface the lobby dialog reads: participants + title."""

    def __init__(self, users=None, title="Room"):
        self.participants = users or []
        self.title = title


class BridgeTestCase(KodiTestCase):
    def setUp(self):
        super(BridgeTestCase, self).setUp()
        self._saved_player = wtwin.player.PLAYER
        self._saved_notification = wtwin.util.showNotification
        self.toasts = []
        wtwin.util.showNotification = self.toasts.append
        util.setSetting("watchtogether.show_osd_status", "true")
        util.setSetting("watchtogether.last_room", "")
        self.bridge = wtwin.WatchTogetherBridge()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.player = FakePlayer()
        wtwin.player.PLAYER = self.player
        ENV.cond_visibility["Player.Paused"] = (
            lambda cond: bool(wtwin.player.PLAYER.paused)
            if wtwin.player.PLAYER else False)

    def tearDown(self):
        wtwin.player.PLAYER = self._saved_player
        wtwin.util.showNotification = self._saved_notification
        util.setSetting("watchtogether.show_osd_status", "true")
        util.setSetting("watchtogether.last_room", "")
        super(BridgeTestCase, self).tearDown()


class SnapshotTest(BridgeTestCase):
    def test_push_local_shape(self):
        self.bridge.supervisor = FakeSupervisor()
        self.player.position = 12.7
        self.player.paused = True
        self.bridge.push_local()
        self.assertEqual(self.bridge.supervisor.sent,
                         [{"position": 12, "paused": True, "doSeek": False}])

    def test_theme_music_never_reaches_the_relay(self):
        # BGM plays through the same player: audio-only must not push the
        # theme's position, or peers would seek their video to it. We still
        # emit an idle State so the relay does not reap the silent socket.
        self.bridge.supervisor = FakeSupervisor()
        self.player.video = None
        self.player.position = 99.0
        self.bridge.push_local()
        self.assertEqual(self.bridge.supervisor.sent,
                         [{"position": 0, "paused": True, "doSeek": False}])

    def test_no_supervisor_is_inert(self):
        self.bridge.push_local()
        self.assertEqual(self.player.wt_broadcast, None)

    def test_local_change_event_pushes(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_local_change("pause")
        self.assertEqual(len(self.bridge.supervisor.sent), 1)

    def test_local_seek_requests_a_seek_command(self):
        # §5.6: the outbound State must carry doSeek: true, not just position
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_local_change("seek")
        self.assertTrue(sup.seek_requested)

    def test_local_pause_does_not_request_a_seek(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_local_change("pause")
        self.assertFalse(sup.seek_requested)


class ReadinessTest(BridgeTestCase):
    def test_ready_tracks_playback(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.player.video = FakeVideo("227117")
        self.bridge._update_ready(sup)
        self.assertIs(sup.ready, True)
        self.player.video = None
        self.bridge._update_ready(sup)
        self.assertIs(sup.ready, False)

    def test_local_play_reports_manual_readiness(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_local_change("play")
        self.assertIs(sup.ready, True)
        self.assertIs(sup.ready_manual, True)

    def test_local_pause_does_not_report_manual_readiness(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_local_change("pause")
        self.assertIsNone(sup.ready_manual)


class LobbyRowsTest(KodiTestCase):
    """lobby_rows: the lobby's participant list with Ready/Invited status."""

    def room(self, users):
        return watchtogether.Room({"users": users})

    def test_lobby_rows_marks_ready_and_invited(self):
        room = self.room([{"id": 1, "title": "A"}, {"id": 2, "title": "B"}])
        roster = {syncplay.build_identity("d", "n", 1): {"isReady": True}}
        rows = wtwin.lobby_rows(room, roster)
        self.assertEqual([r["status"] for r in rows], ["Ready", "Invited"])
        self.assertEqual([r["title"] for r in rows], ["A", "B"])

    def test_lobby_rows_falls_back_to_username_and_thumb(self):
        room = self.room([{"id": 1, "username": "u1", "thumb": "/t.png"}])
        rows = wtwin.lobby_rows(room, {})
        self.assertEqual(rows, [{"title": "u1", "thumb": "/t.png",
                                 "status": "Invited"}])


class LobbyDialogTest(KodiTestCase):
    """LobbyDialog: host mode offers Start/Cancel/Invite; guest is read-only."""

    def test_lobby_dialog_read_only_hides_start(self):
        d = wtwin.LobbyDialog(room=FakeRoom(users=[]), roster={},
                              host=False)
        self.assertIs(d.is_host, False)   # dialog hides Start/Cancel in guest mode

    def test_lobby_dialog_host_mode(self):
        d = wtwin.LobbyDialog(room=FakeRoom(users=[]), roster={},
                              host=True)
        self.assertIs(d.is_host, True)

    def test_lobby_back_cancels_for_the_host(self):
        calls = []
        saved = wtwin.bridge.cancel_hosting
        wtwin.bridge.cancel_hosting = lambda: calls.append("cancel")
        try:
            d = wtwin.LobbyDialog(room=FakeRoom(users=[]), roster={},
                                  host=True)
            d.onAction(wtwin.xbmcgui.ACTION_NAV_BACK)
        finally:
            wtwin.bridge.cancel_hosting = saved
        self.assertEqual(calls, ["cancel"])

    def test_lobby_back_leaves_for_a_guest(self):
        calls = []
        saved = wtwin.bridge.leave
        wtwin.bridge.leave = lambda: calls.append("leave")
        try:
            d = wtwin.LobbyDialog(room=FakeRoom(users=[]), roster={},
                                  host=False)
            d.onAction(wtwin.xbmcgui.ACTION_NAV_BACK)
        finally:
            wtwin.bridge.leave = saved
        self.assertEqual(calls, ["leave"])

    def test_lobby_dialog_syncs_title_and_status_rows(self):
        room = FakeRoom(users=[{"id": 1, "title": "A"}, {"id": 2, "title": "B"}])

        class FakeList(object):
            def __init__(self):
                self.items = []

            def reset(self):
                self.items = []

            def addItems(self, items):
                self.items += items

        d = wtwin.LobbyDialog(room=room, roster={}, host=True)
        d.peopleList = FakeList()
        d._sync()
        self.assertEqual([i.label for i in d.peopleList.items], ["A", "B"])
        self.assertEqual([i.label2 for i in d.peopleList.items],
                         ["Invited", "Invited"])

    def test_refresh_tracks_bridge_room_membership(self):
        # the 15 s roster poll replaces bridge.room with a fresh Room; the open
        # lobby must re-read it or an invitee never appears (their Invited
        # status would be unreachable)
        class FakeList(object):
            def __init__(self):
                self.items = []

            def reset(self):
                self.items = []

            def addItems(self, items):
                self.items += items

        saved_room = wtwin.bridge.room
        saved_sup = wtwin.bridge.supervisor
        try:
            wtwin.bridge.supervisor = None
            wtwin.bridge.room = watchtogether.Room(
                {"id": "r", "users": [{"id": 1, "title": "A"}]})
            d = wtwin.LobbyDialog(room=watchtogether.Room({"id": "r", "users": []}),
                                  roster={}, host=True)
            d.peopleList = FakeList()
            wtwin.bridge.room = watchtogether.Room(
                {"id": "r", "users": [{"id": 1, "title": "A"},
                                      {"id": 2, "title": "B"}]})
            d.refresh()
        finally:
            wtwin.bridge.room = saved_room
            wtwin.bridge.supervisor = saved_sup
        self.assertEqual([i.label for i in d.peopleList.items], ["A", "B"])

    def test_refresh_repaints_without_any_notification(self):
        # Kodi delivers onNotification to xbmc.Monitor only, never to a window
        # (see Window.h's callback list), so routing the repaint through
        # NotifyAll left the lobby stale and the invite picker empty on a live
        # client. refresh() must paint the list itself.
        class FakeList(object):
            def __init__(self):
                self.items = []

            def reset(self):
                self.items = []

            def addItems(self, items):
                self.items += items

        d = wtwin.LobbyDialog(room=FakeRoom(users=[{"id": 1, "title": "A"}]),
                              roster={}, host=True)
        d.peopleList = FakeList()
        d.refresh()
        self.assertEqual([i.label for i in d.peopleList.items], ["A"],
                         "refresh() must paint the list itself")

    def test_sync_is_a_no_op_once_the_dialog_is_closing(self):
        # a callback still holding a closed dialog must not touch its controls
        class ExplodingList(object):
            def reset(self):
                raise AssertionError("closed dialog's list was repainted")

            def addItems(self, items):
                raise AssertionError("closed dialog's list was repainted")

        d = wtwin.LobbyDialog(room=FakeRoom(users=[{"id": 1, "title": "A"}]),
                              roster={}, host=True)
        d.peopleList = ExplodingList()
        d._closing = True
        d._sync()               # must be a no-op, not a native call


class InviteRowsTest(KodiTestCase):
    """invite_rows: the invite picker's list-item properties."""

    def test_invite_dialog_marks_access_unknown(self):
        rows = wtwin.invite_rows([
            plexpeople.Invitee(1, "a", "", False),
            plexpeople.Invitee(2, "b", "", True),
        ])
        self.assertEqual(rows[1]["access_unknown"], "1")

    def test_invite_rows_carry_id_title_and_thumb(self):
        rows = wtwin.invite_rows([plexpeople.Invitee(7, "b", "/t.png", False)])
        self.assertEqual(rows, [{"id": 7, "title": "b", "thumb": "/t.png",
                                 "access_unknown": ""}])


class InviteDialogTest(KodiTestCase):
    """InviteDialog: multi-select list; OK invites the selected ids."""

    class FakeList(object):
        def __init__(self):
            self.items = []

        def reset(self):
            self.items = []

        def addItems(self, items):
            self.items += items

    def setUp(self):
        super(InviteDialogTest, self).setUp()
        # @busy.dialog() cannot build a real window under the xbmcgui stub
        self._saved_busy_window = wtwin.busy.BusyWindow
        wtwin.busy.BusyWindow = FakeBusyWindow

    def tearDown(self):
        wtwin.busy.BusyWindow = self._saved_busy_window
        super(InviteDialogTest, self).tearDown()

    def dialog(self, room=None):
        d = wtwin.InviteDialog(room=room)
        d.peopleList = self.FakeList()
        return d

    def test_invite_dialog_syncs_rows_and_collects_selection(self):
        d = self.dialog()
        d._invitees = [plexpeople.Invitee(1, "a", "", False),
                       plexpeople.Invitee(2, "b", "", True)]
        d._sync()
        self.assertEqual([i.label for i in d.peopleList.items], ["a", "b"])
        self.assertEqual(d._selected_ids(), [])
        d.peopleList.items[1].setProperty("selected", "1")
        self.assertEqual(d._selected_ids(), [2])

    def test_fetch_paints_the_list_without_any_notification(self):
        # the picker's only paint path used to be a NotifyAll/onNotification
        # hand-off, which Kodi never delivers to a window - so the list stayed
        # empty (0 invitees) on a live client. _fetch must paint it itself.
        saved = wtwin.bridge.invitees
        wtwin.bridge.invitees = lambda room=None: [
            plexpeople.Invitee(1, "a", "", False),
            plexpeople.Invitee(2, "b", "", True)]
        try:
            d = self.dialog()
            d._fetch()
        finally:
            wtwin.bridge.invitees = saved
        self.assertEqual([i.label for i in d.peopleList.items], ["a", "b"])

    def test_fetch_degrades_when_invitees_raises(self):
        # a people lookup failure must not break the picker
        saved = wtwin.bridge.invitees

        def boom(*a, **k):
            raise ValueError("people lookup failed")

        wtwin.bridge.invitees = boom
        try:
            d = self.dialog()
            d._fetch()
        finally:
            wtwin.bridge.invitees = saved
        self.assertEqual(d._invitees, [])
        self.assertEqual(d.peopleList.items, [], "an empty picker, not a crash")

    def test_fetch_uses_the_dialog_room(self):
        # a picker opened from a room tile must query that tile's room, not
        # whatever room the bridge happens to be in
        room = watchtogether.Room({"id": "other", "sourceUri": "", "users": []})
        saved = wtwin.bridge.invitees
        seen = []
        wtwin.bridge.invitees = lambda r=None: seen.append(r) or []
        try:
            d = self.dialog(room=room)
            d._fetch()
        finally:
            wtwin.bridge.invitees = saved
        self.assertEqual(seen, [room])

    def test_send_invites_into_the_dialog_room(self):
        room = watchtogether.Room({"id": "other", "sourceUri": "", "users": []})
        saved = wtwin.bridge.invite
        calls = []
        wtwin.bridge.invite = lambda ids, r=None: calls.append((ids, r)) or []
        try:
            d = self.dialog(room=room)
            d._send([1, 2])
        finally:
            wtwin.bridge.invite = saved
        self.assertEqual(calls, [([1, 2], room)])

    def test_send_toasts_sign_in_on_auth_error(self):
        saved = wtwin.bridge.invite
        saved_notify = wtwin.util.showNotification
        toasts = []
        wtwin.util.showNotification = toasts.append
        wtwin.bridge.invite = lambda ids, r=None: (_ for _ in ()).throw(
            watchtogether.AuthError("POST /rooms/x/invite -> 401"))
        try:
            self.dialog()._send([1])
        finally:
            wtwin.bridge.invite = saved
            wtwin.util.showNotification = saved_notify
        self.assertEqual(toasts, [util.T(35083,
                                        "Sign in again to use Watch Together")])


class InviteeSourceTest(BridgeTestCase):
    """bridge.invitees: eligible invitees, home-only when friends are empty."""

    def test_invitees_fall_back_to_home_users_when_friends_empty(self):
        saved_account = wtwin.plexapp.ACCOUNT
        saved_friends = wtwin.plexpeople.friends

        class Account(object):
            authToken = "tok"
            ID = 9
            homeUsers = [{"id": 5, "title": "Home", "thumb": ""}]

        wtwin.plexapp.ACCOUNT = Account()
        wtwin.plexpeople.friends = lambda *a, **k: []
        try:
            self.bridge.room = watchtogether.Room(dict(
                ROOM_JSON, sourceUri="server://m/com.plexapp.plugins.library/"
                                     "library/metadata/1"))
            out = self.bridge.invitees()
        finally:
            wtwin.plexapp.ACCOUNT = saved_account
            wtwin.plexpeople.friends = saved_friends
        self.assertEqual([i.id for i in out], [5])
        self.assertEqual(out[0].title, "Home")

    def test_home_user_title_falls_back_to_username(self):
        saved_account = wtwin.plexapp.ACCOUNT
        saved_friends = wtwin.plexpeople.friends

        class Account(object):
            authToken = "tok"
            ID = 9
            homeUsers = [{"id": 5, "title": "", "username": "alice", "thumb": ""}]

        wtwin.plexapp.ACCOUNT = Account()
        wtwin.plexpeople.friends = lambda *a, **k: []
        try:
            self.bridge.room = watchtogether.Room(dict(
                ROOM_JSON, sourceUri="server://m/com.plexapp.plugins.library/"
                                     "library/metadata/1"))
            out = self.bridge.invitees()
        finally:
            wtwin.plexapp.ACCOUNT = saved_account
            wtwin.plexpeople.friends = saved_friends
        self.assertEqual(out[0].title, "alice")

    def test_invitees_excludes_self(self):
        # self must never be offered as an invitee (invite self is a 400)
        saved_account = wtwin.plexapp.ACCOUNT
        saved_friends = wtwin.plexpeople.friends

        class Account(object):
            authToken = "tok"
            ID = 9
            homeUsers = [{"id": 9, "title": "Me", "thumb": ""}]

        wtwin.plexapp.ACCOUNT = Account()
        wtwin.plexpeople.friends = lambda *a, **k: [
            {"id": 9, "title": "Me", "thumb": ""},
            {"id": 5, "title": "Friend", "thumb": ""}]
        try:
            self.bridge.room = watchtogether.Room(dict(
                ROOM_JSON, sourceUri="server://m/com.plexapp.plugins.library/"
                                     "library/metadata/1"))
            out = self.bridge.invitees()
        finally:
            wtwin.plexapp.ACCOUNT = saved_account
            wtwin.plexpeople.friends = saved_friends
        self.assertEqual([i.id for i in out], [5])

    def test_invitees_uses_an_explicit_room(self):
        saved_account = wtwin.plexapp.ACCOUNT
        saved_friends = wtwin.plexpeople.friends

        class Account(object):
            authToken = "tok"
            ID = 9
            homeUsers = []

        wtwin.plexapp.ACCOUNT = Account()
        wtwin.plexpeople.friends = lambda *a, **k: [
            {"id": 1, "title": "a", "thumb": ""},
            {"id": 2, "title": "b", "thumb": ""}]
        self.bridge.room = watchtogether.Room(dict(
            ROOM_JSON, users=[{"id": 1, "title": "a"}]))
        other = watchtogether.Room(dict(
            ROOM_JSON, users=[{"id": 2, "title": "b"}]))
        try:
            out = self.bridge.invitees(other)
        finally:
            wtwin.plexapp.ACCOUNT = saved_account
            wtwin.plexpeople.friends = saved_friends
        # the passed room's members are excluded, not the current room's
        self.assertEqual([i.id for i in out], [1])


class AutoStartTest(BridgeTestCase):
    """_maybe_auto_start / _on_ready / start_playback: §6.4 readiness gate."""

    def setUp(self):
        super(AutoStartTest, self).setUp()
        # auto-start is the host's job: only a host drives start_playback
        self.bridge._hosting = True

    def room(self, user_ids):
        return watchtogether.Room({"users": [{"id": i, "title": str(i)}
                                             for i in user_ids]})

    def fire_ready(self, roster):
        """A peer's Set{ready} reached the bridge (Session wrote the roster)."""
        self.bridge.supervisor.session.roster = roster
        self.bridge._on_ready(None, None)

    def test_start_playback_unpauses_and_broadcasts(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.start_playback()
        self.assertEqual(self.player.controls, ["play"])
        self.assertEqual(self.bridge.supervisor.sent_now, 1)

    def test_auto_start_when_all_members_ready(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = self.room([1, 2])
        self.bridge._player_ready = True
        self.fire_ready({
            syncplay.build_identity("d", "n", 1): {"isReady": True},
            syncplay.build_identity("d", "n", 2): {"isReady": True}})
        self.assertIn("play", self.player.controls)
        self.assertEqual(self.bridge.supervisor.sent_now, 1)

    def test_auto_start_holds_when_a_member_missing(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = self.room([1, 2])
        self.bridge._player_ready = True
        self.fire_ready({syncplay.build_identity("d", "n", 1): {"isReady": True}})
        self.assertEqual(self.player.controls, [])
        self.assertEqual(getattr(self.bridge.supervisor, "sent_now", 0), 0)

    def test_host_is_ready_in_the_home_lobby(self):
        # host() waits in the lobby with no video; the 1 s tick's _update_ready
        # must not overwrite the host's readiness with False
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge._started = False
        self.player.video = None
        self.bridge._update_ready(sup)
        self.assertTrue(self.bridge._player_ready)
        self.assertTrue(sup.ready)

    def test_host_auto_start_after_a_readiness_tick(self):
        # the full sequence the review reproduced: tick readiness, then
        # auto-start once every invited member is ready
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge._started = False
        self.bridge.room = self.room([1, 2])
        self.player.video = None
        self.bridge._update_ready(sup)                    # the 1 s tick
        self.fire_ready({
            syncplay.build_identity("d", "n", 1): {"isReady": True},
            syncplay.build_identity("d", "n", 2): {"isReady": True}})
        self.assertIn("play", self.player.controls, "auto-start fires")

    def test_auto_start_holds_until_self_is_ready(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = self.room([1])
        self.bridge._player_ready = False
        self.fire_ready({syncplay.build_identity("d", "n", 1): {"isReady": True}})
        self.assertEqual(self.player.controls, [])

    def test_auto_start_runs_only_once(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = self.room([1])
        self.bridge._player_ready = True
        roster = {syncplay.build_identity("d", "n", 1): {"isReady": True}}
        self.fire_ready(roster)
        self.fire_ready(roster)
        self.assertEqual(self.player.controls, ["play"])
        self.assertEqual(self.bridge.supervisor.sent_now, 1)

    def test_ready_refreshes_the_open_lobby(self):
        class FakeLobby(object):
            refreshed = 0

            def refresh(self):
                self.refreshed += 1

        self.bridge.supervisor = FakeSupervisor()
        lobby = FakeLobby()
        self.bridge.lobby = lobby
        self.fire_ready({})
        self.assertEqual(lobby.refreshed, 1)

    def test_auto_start_does_not_fire_for_a_guest(self):
        # a ready guest must never call start_playback() on the room
        self.bridge._hosting = False
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = self.room([1])
        self.bridge._player_ready = True
        self.fire_ready({syncplay.build_identity("d", "n", 1): {"isReady": True}})
        self.assertEqual(self.player.controls, [])
        self.assertEqual(getattr(self.bridge.supervisor, "sent_now", 0), 0)


class HostFlowTest(BridgeTestCase):
    """host / invite / start / cancel — the host capability (§Flows/Host)."""

    def setUp(self):
        super(HostFlowTest, self).setUp()
        self.api = FakeAPI()
        self.bridge.api = self.api
        self.joined = []
        self.opened = []
        self.lobby_opens = []
        self.start_on_lobby = False       # a test sets True to simulate Start
        # host() joins via the real (network/socket) join and opens the real
        # video window; both are stubbed here to keep the test offline.
        self.bridge.join = self._fake_join
        self.bridge._play_item = self.opened.append
        self.bridge._open_lobby = self._fake_lobby
        # @busy.dialog() around the create/join portion cannot build a real
        # window under the xbmcgui stub
        self._saved_busy_window = wtwin.busy.BusyWindow
        wtwin.busy.BusyWindow = FakeBusyWindow

    def tearDown(self):
        wtwin.busy.BusyWindow = self._saved_busy_window
        super(HostFlowTest, self).tearDown()

    def _fake_lobby(self, host=True):
        # _open_lobby is modal (blocks until Start/Cancel/ESC); stubbed so the
        # test does not need a real window
        self.lobby_opens.append(host)
        if self.start_on_lobby:
            self.bridge._started = True

    def _fake_join(self, room_id, hosting=False):
        if self.bridge.supervisor is not None:
            return self.bridge.supervisor   # mirrors join()'s early return
        self.joined.append(room_id)
        self.bridge._hosting = hosting
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.supervisor = FakeSupervisor()

    def test_host_creates_room_with_item_source_uri(self):
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(len(self.api.created), 1)
        created = self.api.created[0]
        self.assertEqual(
            created["sourceUri"],
            "server://m/com.plexapp.plugins.library/library/metadata/1")
        self.assertEqual(created["title"], "T")

    def test_host_shows_the_lobby_before_the_video(self):
        # the lobby runs over Home; the video opens only once the room starts
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(self.lobby_opens, [True])
        self.assertEqual(self.opened, [], "no video until the room starts")
        self.assertTrue(self.bridge._player_ready,
                        "the host is ready while waiting in the lobby")

    def test_host_opens_the_video_when_the_room_starts(self):
        self.start_on_lobby = True
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(len(self.opened), 1, "Start opens the video")

    def test_host_joins_the_created_room(self):
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(self.joined, ["ca8cfezmke4"])

    def test_host_leaves_the_current_room_first(self):
        # hosting while already joined must switch, not orphan: join()
        # early-returns an existing supervisor, leaving self.room stale
        self.bridge.room = watchtogether.Room(dict(ROOM_JSON, id="oldroom0001"))
        old_sup = FakeSupervisor()
        self.bridge.supervisor = old_sup

        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))

        self.assertEqual(self.api.leaves, ["oldroom0001"],
                         "must leave the current room (DELETE) before joining")
        self.assertTrue(old_sup.stopped)
        self.assertEqual(self.joined, ["ca8cfezmke4"],
                         "must actually join the new room, not no-op")
        self.assertEqual(self.bridge.room.id, "ca8cfezmke4")

    def test_host_skips_without_a_rating_key(self):
        self.bridge.host(FakeItem(machine="m", rating_key=None, title="T"))
        self.assertEqual(self.api.created, [])
        self.assertEqual(self.joined, [])
        self.assertEqual(self.opened, [])

    def test_host_skips_without_a_server_uuid(self):
        # no machine -> an unresolvable sourceUri; do not create a dead room
        self.bridge.host(FakeItem(machine=None, rating_key="1", title="T"))
        self.assertEqual(self.api.created, [])
        self.assertEqual(self.joined, [])
        self.assertEqual(self.opened, [])
        self.assertEqual(self.toasts,
                         [util.T(35084, "This item cannot be hosted")])

    def test_host_leaves_the_created_room_when_join_fails(self):
        # create succeeded but the follow-up join failed: DELETE the orphan
        # and report, instead of leaving a room nobody is in
        def boom(room_id, hosting=False):
            raise watchtogether.RoomGone("gone")
        self.bridge.join = boom
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(self.api.leaves, ["ca8cfezmke4"],
                         "the created room must be left, not orphaned")
        self.assertEqual(self.opened, [], "no playback after a failed join")
        self.assertIsNone(self.bridge.lobby)

    def test_host_dead_token_asks_to_sign_in(self):
        class DeadTokenAPI(FakeAPI):
            def create(self, source_uri, title, users=None):
                raise watchtogether.AuthError("POST /rooms -> 401")
        self.bridge.api = DeadTokenAPI()
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertEqual(self.toasts,
                         [util.T(35083, "Sign in again to use Watch Together")])
        self.assertEqual(self.opened, [])

    def test_host_sets_the_people_client_id(self):
        from lib import plex, plexpeople
        saved = plexpeople.CLIENT_ID
        plexpeople.CLIENT_ID = ""
        try:
            self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
            self.assertEqual(plexpeople.CLIENT_ID, plex.CLIENT_ID)
            self.assertTrue(plexpeople.VERSION)
        finally:
            plexpeople.CLIENT_ID = saved

    def test_invite_reports_failed_targets(self):
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.api.invite_result = watchtogether.WatchTogetherError("400")
        self.assertEqual(self.bridge.invite([1]), [1])

    def test_invite_keeps_the_room_and_invites_the_rest(self):
        # §11.9: a refused target must not block the others
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.api.invite_fail_ids = {1}
        self.assertEqual(self.bridge.invite([1, 2]), [1])
        self.assertEqual(self.api.invites,
                         [("ca8cfezmke4", [1]), ("ca8cfezmke4", [2])],
                         "both ids attempted: the loop must not abort on the "
                         "first failure")

    def test_invite_without_a_room_fails_every_id(self):
        self.bridge.room = None
        self.assertEqual(self.bridge.invite([1, 2]), [1, 2])

    def test_invite_targets_an_explicit_room(self):
        # a picker opened from a room tile must invite into that room, not
        # whatever room the bridge is currently in
        self.bridge.room = watchtogether.Room(dict(ROOM_JSON, id="current"))
        other = watchtogether.Room(dict(ROOM_JSON, id="other"))
        self.assertEqual(self.bridge.invite([1], other), [])
        self.assertEqual(self.api.invites, [("other", [1])])

    def test_start_unpauses(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.start_playback()
        self.assertEqual(self.player.controls, ["play"])

    def test_start_playback_is_idempotent(self):
        # auto-start can race on two threads; the second call must be a no-op
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.start_playback()
        self.bridge.start_playback()
        self.assertEqual(self.player.controls, ["play"])

    def test_invite_refreshes_the_current_room(self):
        # the invited member must show up in the open lobby
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.supervisor = FakeSupervisor()
        refreshes = []
        self.bridge.refresh_room = lambda: refreshes.append(True)
        self.assertEqual(self.bridge.invite([1]), [])
        self.assertEqual(refreshes, [True])

    def test_invite_does_not_refresh_for_another_room(self):
        self.bridge.room = watchtogether.Room(dict(ROOM_JSON, id="current"))
        other = watchtogether.Room(dict(ROOM_JSON, id="other"))
        refreshes = []
        self.bridge.refresh_room = lambda: refreshes.append(True)
        self.assertEqual(self.bridge.invite([1], other), [])
        self.assertEqual(refreshes, [])

    def test_cancel_leaves_without_destroying(self):
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.supervisor = FakeSupervisor()
        lobby = FakeLobby()
        self.bridge.lobby = lobby

        self.bridge.cancel_hosting()

        self.assertEqual(self.api.leaves, ["ca8cfezmke4"])
        self.assertEqual(self.api.calls, [("leave", "ca8cfezmke4")],
                         "cancel must DELETE (leave), never destroy")
        self.assertTrue(lobby.closed)
        self.assertIsNone(self.bridge.lobby)

    def test_guest_lobby_is_not_opened_for_the_host(self):
        # a relay State arriving during join() must not open the guest lobby
        self.bridge._hosting = True
        opened = []
        self.bridge._open_lobby = lambda *a, **k: opened.append(True)
        self.bridge._update_guest_lobby({"paused": True, "position": 0.0})
        self.assertEqual(opened, [])

    def test_host_sets_the_hosting_state(self):
        self.bridge._open_lobby = lambda *a, **k: None
        self.bridge.host(FakeItem(machine="m", rating_key="1", title="T"))
        self.assertTrue(self.bridge._hosting)

    def test_open_lobby_shows_modally(self):
        # the dialog must be shown modally (main thread); setUp's stub bypasses
        # _open_lobby, so restore the real method here
        self.bridge.__dict__.pop("_open_lobby", None)
        made = []

        class FakeDialog(object):
            def __init__(self):
                self.modalled = False
                self.props = {}

            def setBoolProperty(self, key, value):
                self.props[key] = value

            def setProperty(self, key, value):
                self.props[key] = value

            def modal(self):
                self.modalled = True

        class FakeLobbyDialog(object):
            @staticmethod
            def create(**kwargs):
                d = FakeDialog()
                made.append(d)
                return d

        saved = wtwin.LobbyDialog
        wtwin.LobbyDialog = FakeLobbyDialog
        try:
            self.bridge._open_lobby(host=True)
        finally:
            wtwin.LobbyDialog = saved
        self.assertTrue(made[0].modalled, "the lobby must be opened modally")
        self.assertIsNone(self.bridge.lobby, "cleared once the lobby closes")


class GuestLobbyTest(BridgeTestCase):
    """The read-only lobby a guest sees while a joined room is unstarted.

    Heuristic (§Guest lobby visibility): relay State paused with position < 1 s
    means the room has not started; the lobby closes on the first state with
    playback running."""

    def setUp(self):
        super(GuestLobbyTest, self).setUp()
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        # the dialog itself is covered by LobbyDialogTest; here we test the
        # guest-lobby heuristic, so stub the open (a real create()+_onInit
        # needs a Kodi window)
        def open_lobby(host=True):
            lobby = FakeLobby()
            lobby.is_host = host
            self.bridge.lobby = lobby
        self.bridge._open_lobby = open_lobby

    def state(self, position, paused):
        return {"position": position, "paused": paused, "doSeek": False,
                "setBy": "other-identity"}

    def set_remote(self, position, paused):
        self.bridge.supervisor.session.remote = self.state(position, paused)

    def test_room_unstarted_for_paused_at_zero(self):
        self.set_remote(0.0, True)
        self.assertTrue(self.bridge._room_unstarted())

    def test_room_started_when_playing(self):
        self.set_remote(120.0, False)
        self.assertFalse(self.bridge._room_unstarted())

    def test_room_started_when_no_state_yet(self):
        # no relay State yet: do not block the join waiting for a lobby
        self.bridge.supervisor = None
        self.assertFalse(self.bridge._room_unstarted())

    def test_guest_closes_lobby_when_playback_starts(self):
        self.set_remote(0.0, True)
        self.bridge._open_lobby(host=False)
        self.assertIsNotNone(self.bridge.lobby)
        self.bridge.on_state(self.state(1.5, False))
        self.assertIsNone(self.bridge.lobby, "playback started: close the lobby")

    def test_guest_lobby_is_not_closed_for_the_host(self):
        # _update_guest_lobby is a no-op while hosting
        self.bridge._hosting = True
        self.bridge.lobby = FakeLobby()
        self.bridge.on_state(self.state(1.5, False))
        self.assertIsNotNone(self.bridge.lobby)

    def test_guest_lobby_closes_when_the_room_goes_away(self):
        self.set_remote(0.0, True)
        self.bridge._open_lobby(host=False)
        self.assertIsNotNone(self.bridge.lobby)
        self.bridge.on_gone()
        self.assertIsNone(self.bridge.lobby, "room ended: no orphan lobby")


class RemoteApplyTest(BridgeTestCase):
    def remote(self, position, paused):
        return {"position": position, "paused": paused, "doSeek": False,
                "setBy": "other-identity"}

    def test_remote_pause_applies_and_arms_the_deadline(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position, paused=True))
        self.assertEqual(self.player.controls, ["pause"])
        self.assertGreater(self.player.wt_applying_remote, time.monotonic(),
                           "echo deadline must be armed across the apply")

    def test_remote_resume_applies(self):
        self.player.paused = True
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position, paused=False))
        self.assertEqual(self.player.controls, ["play"])

    def test_remote_seek_goes_through_the_seek_dialog(self):
        self.bridge.supervisor = FakeSupervisor()
        dialog = FakeDialog()
        self.player.handler.dialog = dialog
        # 10s behind: sync_action's seek threshold is >1.75s (§6.2)
        self.bridge.on_state(self.remote(self.player.position + 10, paused=False))
        self.assertEqual(dialog.seeks, [int((self.player.position + 10) * 1000)])
        self.assertGreater(self.player.wt_applying_remote, time.monotonic())

    def test_remote_seek_falls_back_to_the_player(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position + 10, paused=False))
        self.assertEqual(self.player.seek_times, [self.player.position + 10])

    def test_drift_inside_the_band_applies_nothing(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position + 0.5, paused=False))
        self.assertEqual(self.player.controls, [])
        self.assertEqual(self.player.seek_times, [])

    def test_remote_doseek_applies_inside_the_band(self):
        # §5.6: an explicit peer seek is a command, applied even when the
        # position is close enough that drift correction would stay put
        self.bridge.supervisor = FakeSupervisor()
        target = self.player.position + 0.5
        self.bridge.on_state({"position": target, "paused": False,
                              "doSeek": True, "setBy": "other-identity"})
        self.assertEqual(self.player.seek_times, [target])

    def test_no_video_playback_is_left_alone(self):
        self.player.video = None
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(0, paused=True))
        self.assertEqual(self.player.controls, [])

    def test_a_raising_callback_never_escapes(self):
        # Session doc: an exception in on_state tears the connection down
        self.bridge.supervisor = FakeSupervisor()
        self.player.handler = object()      # no .dialog, attribute access raises
        self.bridge.on_state(self.remote(0, paused=True))   # must not raise


class LifecycleTest(BridgeTestCase):
    def test_leave_sends_delete_then_stops(self):
        api = FakeAPI()
        self.bridge.api = api
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.player.wt_broadcast = self.bridge.on_local_change
        self.player.wt_applying_remote = float("inf")
        util.setSetting("watchtogether.last_room", "ca8cfezmke4")

        self.bridge.leave()

        self.assertEqual(api.calls, [("leave", "ca8cfezmke4")])
        self.assertTrue(sup.stopped)
        self.assertIsNone(self.bridge.supervisor)
        self.assertIsNone(self.player.wt_broadcast)
        self.assertEqual(self.player.wt_applying_remote, 0.0)
        self.assertEqual(util.getSetting("watchtogether.last_room", ""), "")
        self.assertEqual(util.getGlobalProperty("watchtogether.status", base="{0}"), "")

    def test_gone_stops_without_delete(self):
        api = FakeAPI()
        self.bridge.api = api
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        util.setSetting("watchtogether.last_room", "ca8cfezmke4")

        self.bridge.on_gone()

        self.assertEqual(api.calls, [], "gone must never call leave()")
        self.assertTrue(sup.stopped)
        self.assertIsNone(self.bridge.supervisor)
        self.assertEqual(self.toasts, [util.T(35059, "The Watch Together room has ended")])
        self.assertEqual(util.getSetting("watchtogether.last_room", ""), "")

    def test_gone_after_a_voluntary_leave_does_not_toast(self):
        # our own DELETE makes the next room poll read NotMember; that is our
        # departure, not "the room ended"
        self.bridge.api = FakeAPI()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.leave()
        self.bridge.on_gone()
        self.assertEqual(self.toasts, [])

    def test_disconnect_stops_without_delete_and_keeps_membership(self):
        # stopping playback ends the session but must not DELETE, so the tile
        # can rejoin (the official client's behaviour)
        api = FakeAPI()
        self.bridge.api = api
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        util.setSetting("watchtogether.last_room", "ca8cfezmke4")

        self.bridge.disconnect()

        self.assertEqual(api.calls, [], "disconnect must never DELETE")
        self.assertTrue(sup.stopped)
        self.assertIsNone(self.bridge.supervisor)
        self.assertEqual(util.getSetting("watchtogether.last_room", ""),
                         "ca8cfezmke4", "membership retained for rejoin")

    def test_stale_gone_callback_is_ignored(self):
        # a supervisor we already replaced must not tear down the new one
        current = FakeSupervisor()
        self.bridge.supervisor = current
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.on_gone(FakeSupervisor())
        self.assertIs(self.bridge.supervisor, current)
        self.assertEqual(self.toasts, [])

    def test_leave_releases_the_join_lock_before_blocking_calls(self):
        # api.leave() can block 15s and sup.stop() joins the supervisor thread;
        # holding _join_lock across either stalls a concurrent on_gone()/join().
        bridge = self.bridge
        lock_free = []

        class LockProbeAPI(FakeAPI):
            def leave(self, room_id):
                got = bridge._join_lock.acquire(blocking=False)
                lock_free.append(("api", got))
                if got:
                    bridge._join_lock.release()
                FakeAPI.leave(self, room_id)

        class LockProbeSup(FakeSupervisor):
            def stop(self, timeout=None):
                got = bridge._join_lock.acquire(blocking=False)
                lock_free.append(("stop", got))
                if got:
                    bridge._join_lock.release()
                FakeSupervisor.stop(self, timeout)

        bridge.api = LockProbeAPI()
        bridge.room = watchtogether.Room(ROOM_JSON)
        bridge.supervisor = LockProbeSup()

        bridge.leave()

        self.assertEqual(lock_free, [("api", True), ("stop", True)])

    def test_join_feeds_the_gate_and_status(self):
        class JoinableSup(FakeSupervisor):
            pass

        def fake_join(room_id):
            sup = JoinableSup()
            self.bridge.supervisor = sup
            self.bridge.room = watchtogether.Room(ROOM_JSON)
            return sup

        self.bridge.join = fake_join
        self.bridge.join("ca8cfezmke4")
        # join wires the broadcast callback through on join in the real code;
        # assert the wiring surfaces through on_local_change
        self.bridge.on_local_change("seek")
        self.assertEqual(len(self.bridge.supervisor.sent), 1)


class LobbyTest(BridgeTestCase):
    def test_first_poll_seeds_silently(self):
        self.bridge.api = FakeAPI(rooms=[ROOM_JSON])
        self.bridge._poll_rooms()
        self.assertEqual(self.toasts, [])
        self.assertEqual(len(self.bridge.rooms_cache), 1)

    def test_new_room_toasts_once(self):
        self.bridge.api = FakeAPI(rooms=[ROOM_JSON])
        self.bridge._poll_rooms()
        second = dict(ROOM_JSON, id="otherroom01", title="Other room")
        self.bridge.api = FakeAPI(rooms=[ROOM_JSON, second])
        self.bridge._poll_rooms()
        self.assertEqual(len(self.toasts), 1)
        self.assertIn("Other room", self.toasts[0])
        self.bridge._poll_rooms()        # same rooms again: no repeat toast
        self.assertEqual(len(self.toasts), 1)

    def test_departed_room_is_pruned_then_toasts_again(self):
        self.bridge.api = FakeAPI(rooms=[ROOM_JSON])
        self.bridge._poll_rooms()                 # seed silently
        self.bridge.api = FakeAPI(rooms=[])
        self.bridge._poll_rooms()                 # room gone -> pruned
        self.assertEqual(self.bridge._seen_rooms, set())
        self.bridge.api = FakeAPI(rooms=[ROOM_JSON])
        self.bridge._poll_rooms()                 # back -> toast again
        self.assertEqual(len(self.toasts), 1)

    def test_poll_failure_is_swallowed(self):
        class Boom(object):
            def rooms(self):
                raise watchtogether.WatchTogetherError("500")
        self.bridge.api = Boom()
        self.bridge._poll_rooms()        # must not raise
        self.assertEqual(self.toasts, [])

    def test_poll_survives_a_non_protocol_error(self):
        # a malformed payload (not a WatchTogetherError) must not kill the
        # lobby daemon thread
        class Boom(object):
            def rooms(self):
                raise ValueError("bad payload")
        self.bridge.api = Boom()
        self.bridge._poll_rooms()        # must not raise
        self.assertEqual(self.toasts, [])
        self.assertEqual(self.bridge.rooms_cache, [])

    def test_auto_join_non_protocol_error_is_logged_not_fatal(self):
        def boom(room_id):
            raise ValueError("bad payload")
        self.bridge.join = boom
        util.setSetting("watchtogether.last_room", "ca8cfezmke4")
        self.bridge._auto_join("ca8cfezmke4")     # must not raise
        self.assertEqual(util.getSetting("watchtogether.last_room", ""), "ca8cfezmke4",
                         "a transient error must not forget the room")


class StatusTest(BridgeTestCase):
    def read(self):
        return util.getGlobalProperty("watchtogether.status", base="{0}")

    def test_disconnected_clears_status(self):
        self.bridge.update_status()
        self.assertEqual(self.read(), "")

    def test_connected_shows_count(self):
        self.bridge.supervisor = FakeSupervisor(connected=True)
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.update_status()
        self.assertEqual(self.read(), "2 watching")

    def test_reconnecting_while_socket_is_down(self):
        self.bridge.supervisor = FakeSupervisor(connected=False)
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.update_status()
        self.assertEqual(self.read(), util.T(35055, "Reconnecting…"))

    def test_osd_toggle_silences_the_property(self):
        util.setSetting("watchtogether.show_osd_status", "false")
        self.bridge.supervisor = FakeSupervisor(connected=True)
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.update_status()
        self.assertEqual(self.read(), "")


class PlaybackStartTest(BridgeTestCase):
    """_watch_room / _room_media_item: the guarded guest join-playback (§6.4)."""

    def room(self):
        return watchtogether.Room(ROOM_JSON)

    def test_watch_room_skips_when_a_video_is_already_playing(self):
        self.player.video = FakeVideo("227117")
        self.bridge._watch_room(self.room())   # must not start a new playback
        self.assertEqual(self.player.videos, [])

    def test_watch_room_without_a_source_server_does_nothing(self):
        self.player.video = None
        # SERVERMANAGER is absent in tests: resolve yields nothing, no crash
        self.bridge._watch_room(self.room())
        self.assertEqual(self.player.videos, [])

    def test_room_media_item_returns_none_without_a_source_server(self):
        self.assertIsNone(self.bridge._room_media_item(self.room()))


class LocalChangeGraceTest(BridgeTestCase):
    def test_a_local_change_holds_off_a_peer_state_that_would_revert_it(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_local_change("pause")
        self.assertEqual(sup.sent_now, 1, "a local change is sent immediately")
        self.bridge.on_state({"position": self.player.position + 5,
                              "paused": False, "doSeek": False,
                              "setBy": "other-identity"})
        self.assertEqual(self.player.controls, [], "must not be reverted")

    def test_remote_applies_resume_after_the_grace(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_local_change("pause")
        self.bridge._local_change_at = 0.0     # grace expired
        self.bridge.on_state({"position": self.player.position,
                              "paused": True, "doSeek": False,
                              "setBy": "other-identity"})
        self.assertEqual(self.player.controls, ["pause"])

    def test_position_is_not_published_until_it_matches_the_room(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        # local ~50s, room at 0: far off, must not become the room's position
        self.bridge.on_state({"position": 0.0, "paused": False,
                              "doSeek": False, "setBy": "other-identity"})
        self.assertFalse(sup.synced)
        # now our position matches the room: safe to publish
        self.bridge.on_state({"position": self.player.position, "paused": False,
                              "doSeek": False, "setBy": "other-identity"})
        self.assertTrue(sup.synced)


class TempoTest(BridgeTestCase):
    def tempo_state(self, delta):
        return {"position": self.player.position - delta, "paused": False,
                "doSeek": False, "setBy": "other-identity"}

    def patch_rpc(self, calls, fail=False):
        class RPCPlayer(object):
            def GetActivePlayers(self):
                return [{"playerid": 1, "type": "video"}]

            def SetTempo(self, playerid, tempo):
                calls.append((playerid, tempo))
                if fail:
                    raise RuntimeError("no tempo")

        class RPC(object):
            Player = RPCPlayer()
        return RPC()

    def test_kodi_21_uses_set_tempo(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))       # ~2s ahead
            self.bridge.on_state(self.tempo_state(0.2))       # back in the band
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(calls, [(1, 0.95), (1, 1.0)], "slow then reset")
        self.assertEqual(self.player.seek_times, [], "tempo needs no seek")

    def test_teardown_restores_normal_tempo(self):
        # leaving via the OSD keeps the video running; a catch-up must not
        # leave it slowed after sync has ended
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))   # applies 0.95
            self.assertEqual(self.bridge._tempo, 0.95)
            self.bridge.disconnect()
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertIn((1, 1.0), calls, "normal tempo restored on teardown")
        self.assertEqual(self.bridge._tempo, 1.0)

    def test_old_kodi_degrades_to_a_seek(self):
        saved_major = wtwin.util.KODI_VERSION_MAJOR
        wtwin.util.KODI_VERSION_MAJOR = 20
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR = saved_major
        self.assertEqual(self.player.seek_times, [self.player.position - 2.0])

    def test_set_tempo_failure_degrades_to_a_seek(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc([], fail=True)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(self.player.seek_times, [self.player.position - 2.0])

    def test_set_tempo_failure_backs_off_without_spam(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls, fail=True)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))   # fails -> backs off
            self.bridge.on_state(self.tempo_state(2.0))   # within backoff: no retry
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(len(calls), 1, "must not hammer a failing SetTempo")
        self.assertEqual(len(self.player.seek_times), 2, "still hard-seeks")

    def test_tempo_is_skipped_while_seeking(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        ENV.cond_visibility["Player.Seeking"] = True
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))
        finally:
            ENV.cond_visibility.pop("Player.Seeking", None)
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(calls, [], "no SetTempo while seeking")
        self.assertEqual(self.player.seek_times, [], "and no seek either")

    def test_tempo_applies_once_the_player_is_stable(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        ENV.cond_visibility["Player.Seeking"] = True
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))     # skipped
            ENV.cond_visibility.pop("Player.Seeking", None)
            self.bridge.on_state(self.tempo_state(2.0))     # stable -> tempo
        finally:
            ENV.cond_visibility.pop("Player.Seeking", None)
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(calls, [(1, 0.95)])
        self.assertEqual(self.player.seek_times, [])


class SourceUriTest(KodiTestCase):
    """parse_source_uri: the room sourceUri -> (machine, ratingKey) mapping
    used to start the room's content on join (§6.4)."""
    def test_bare_server_uri(self):
        self.assertEqual(
            wtwin.parse_source_uri(
                "server://abc123/com.plexapp.plugins.library/"
                "library/metadata/227117"),
            ("abc123", "227117"))

    def test_provider_prefixed_uri(self):
        self.assertEqual(
            wtwin.parse_source_uri(
                "provider://x/server://abc123/com.plexapp.plugins.library/"
                "library/metadata/42"),
            ("abc123", "42"))

    def test_trailing_segments_are_ignored(self):
        self.assertEqual(
            wtwin.parse_source_uri(
                "server://abc123/com.plexapp.plugins.library/"
                "library/metadata/227117/children"),
            ("abc123", "227117"))

    def test_rejects_non_library_uri(self):
        self.assertEqual(wtwin.parse_source_uri("http://example/x"), (None, None))
        self.assertEqual(wtwin.parse_source_uri("server://abc/other"), (None, None))
        self.assertEqual(wtwin.parse_source_uri(""), (None, None))
        self.assertEqual(wtwin.parse_source_uri(None), (None, None))


class SupervisorGuardTest(BridgeTestCase):
    """A callback from a stopped supervisor must not touch the bridge.

    stop() waits ≤5 s but a room REST can take 15 s, so an old supervisor can
    deliver after another room has been joined."""

    def test_stale_roster_callback_is_ignored(self):
        old, new = FakeSupervisor(), FakeSupervisor()
        self.bridge.supervisor = new
        calls = []
        self.bridge.on_roster = lambda room: calls.append(room)
        self.bridge._sup_guard(old, self.bridge.on_roster,
                               watchtogether.Room({"id": "old"}))
        self.assertEqual(calls, [], "a stale supervisor's roster must not apply")
        self.bridge._sup_guard(new, self.bridge.on_roster,
                               watchtogether.Room({"id": "new"}))
        self.assertEqual(len(calls), 1)

    def test_stale_state_callback_is_ignored(self):
        old, new = FakeSupervisor(), FakeSupervisor()
        self.bridge.supervisor = new
        calls = []
        self.bridge.on_state = lambda remote: calls.append(remote)
        self.bridge._sup_guard(old, self.bridge.on_state, {"position": 1.0})
        self.assertEqual(calls, [])


class PlaybackOwnershipTest(BridgeTestCase):
    """The sync gates: only the room's own item may be synced.

    isPlayingVideo() is true for any video; with auto-join the bridge is
    connected before room playback, so an unrelated movie must not be
    paused/seeked by room States nor have its position published."""

    def remote(self, position=100.0, paused=True):
        return {"position": position, "paused": paused, "doSeek": False,
                "setBy": "other-identity"}

    def test_unrelated_video_is_not_controlled_by_room_states(self):
        self.bridge.supervisor = FakeSupervisor()
        self.player.video = FakeVideo("999")     # not the room's item
        self.bridge.on_state(self.remote())
        self.assertEqual(self.player.controls, [], "no pause/play applied")
        self.assertEqual(self.player.seek_times, [], "no seek applied")

    def test_unrelated_video_position_is_not_published(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.player.video = FakeVideo("999")
        self.player.position = 12.0
        self.bridge.push_local()
        self.assertEqual(sup.sent[-1]["position"],
                         int(sup.session.remote.get("position", 0)),
                         "echoes the room position, not the unrelated video")

    def test_room_item_is_synced(self):
        self.bridge.supervisor = FakeSupervisor()
        self.player.video = FakeVideo("227117")
        self.bridge.on_state(self.remote(position=50.0))
        self.assertEqual(self.player.controls, ["pause"])

    def test_ready_requires_the_room_item(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.player.video = FakeVideo("999")
        self.bridge._update_ready(sup)
        self.assertFalse(self.bridge._player_ready)
        self.player.video = FakeVideo("227117")
        self.bridge._update_ready(sup)
        self.assertTrue(self.bridge._player_ready)


class TakeoverConfirmTest(BridgeTestCase):
    """Confirm before a join takes over a different item already playing."""

    def room(self):
        return watchtogether.Room(dict(
            ROOM_JSON,
            sourceUri="server://abc/com.plexapp.plugins.library/"
                      "library/metadata/227117"))

    def test_unknown_playing_item_prompts(self):
        # playing but unidentifiable (external player): cannot prove it is the
        # room's content, so prompt
        self.assertTrue(wtwin.needs_takeover_confirm(self.room(), ""))

    def test_same_item_no_prompt(self):
        self.assertFalse(wtwin.needs_takeover_confirm(self.room(), "227117"))

    def test_different_item_prompts(self):
        self.assertTrue(wtwin.needs_takeover_confirm(self.room(), "999"))

    def test_unknown_room_content_prompts(self):
        room = watchtogether.Room(dict(ROOM_JSON, sourceUri="not-a-uri"))
        self.assertTrue(wtwin.needs_takeover_confirm(room, "999"))

    def test_dialog_is_used_when_prompting(self):
        self.player.video = FakeVideo("999")
        ENV.dialog_answers.clear()
        ENV.dialog_answers.append(False)
        self.assertFalse(wtwin.confirm_takeover(self.room()))
        self.assertEqual(ENV.dialog_calls[-1][0], "yesno")

    def test_same_item_skips_the_dialog(self):
        self.player.video = FakeVideo("227117")
        ENV.dialog_answers.clear()
        ENV.dialog_calls.clear()
        self.assertTrue(wtwin.confirm_takeover(self.room()))
        self.assertEqual(ENV.dialog_calls, [])
