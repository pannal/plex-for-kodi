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
        self.wt_applied_kind = None
        self.wt_detector_requestid = None
        self.wt_detector_part_index = 0
        self.pauseAfterPlaybackStarted = False

    def wtApplyingRemote(self, kind):
        # mirrors PlexPlayer.wtApplyingRemote: arm the echo deadline and record
        # which kind of change it is the echo of
        self.wt_applying_remote = float("inf")
        self.wt_applied_kind = kind

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
        self.notifications = []
        wtwin.util.showNotification = self._record_notification
        util.setSetting("watchtogether.show_osd_status", "true")
        util.setSetting("watchtogether.last_room", "")
        util.setSetting("watchtogether.pause_catchup", "false")
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
        util.setSetting("watchtogether.pause_catchup", "false")
        super(BridgeTestCase, self).tearDown()

    def _record_notification(self, message, time_ms=3000, icon_path=None,
                             header=None):
        # capture the full call for header/time_ms assertions, but keep
        # self.toasts as bare messages so the existing assertions still hold
        self.toasts.append(message)
        self.notifications.append((message, header, time_ms))


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


class LobbyPreparingTest(KodiTestCase):
    """The lobby's self row shows "Preparing…" while a p3i scan is in flight."""

    class FakeList(object):
        def __init__(self):
            self.items = []

        def reset(self):
            self.items = []

        def addItems(self, items):
            self.items += items

    def setUp(self):
        super(LobbyPreparingTest, self).setUp()
        self._saved = (wtwin.plexapp.ACCOUNT, wtwin.bridge.room,
                       wtwin.bridge._detector_requestid)

    def tearDown(self):
        (wtwin.plexapp.ACCOUNT, wtwin.bridge.room,
         wtwin.bridge._detector_requestid) = self._saved
        super(LobbyPreparingTest, self).tearDown()

    def _sync_rows(self):
        class Account(object):
            ID = 1000001

        wtwin.plexapp.ACCOUNT = Account()
        wtwin.bridge.room = watchtogether.Room(ROOM_JSON)
        d = wtwin.LobbyDialog(room=wtwin.bridge.room, roster={}, host=True)
        d.peopleList = self.FakeList()
        d._sync()
        return [(i.label, i.label2) for i in d.peopleList.items]

    def test_lobby_self_row_shows_preparing(self):
        wtwin.bridge._detector_requestid = "job-1"
        rows = self._sync_rows()
        self.assertEqual([t for t, _ in rows], ["Owner", "Guest"])
        self.assertEqual([s for _, s in rows],
                         [util.T(35088, "Preparing…"), "Invited"])

    def test_lobby_self_row_without_a_job_is_ready_or_invited(self):
        wtwin.bridge._detector_requestid = None
        rows = self._sync_rows()
        self.assertEqual([s for _, s in rows], ["Invited", "Invited"])


class HostMenuEntryTest(KodiTestCase):
    """The item-menu entry that starts a room, shared by the episodes view, the
    pre-play screen and Home."""

    def test_offered_for_an_eligible_item(self):
        entry = wtwin.host_menu_entry(FakeItem())
        self.assertEqual(entry["key"], "start_watch_together")
        self.assertEqual(entry["display"],
                         util.T(35080, "Start Watch Together"))

    def test_not_offered_without_a_server(self):
        item = FakeItem()
        item.server = None
        self.assertIsNone(wtwin.host_menu_entry(item))

    def test_not_offered_without_a_server_uuid(self):
        # no uuid -> sourceUri cannot resolve, so the room could not be created
        self.assertIsNone(wtwin.host_menu_entry(FakeItem(machine=None)))
        self.assertIsNone(wtwin.host_menu_entry(FakeItem(machine="")))

    def test_not_offered_without_a_rating_key(self):
        self.assertIsNone(wtwin.host_menu_entry(FakeItem(rating_key=None)))

    def test_start_hosting_hosts_straight_away_without_a_room(self):
        saved_host, saved_sup = wtwin.bridge.host, wtwin.bridge.supervisor
        hosted = []
        wtwin.bridge.host = hosted.append
        wtwin.bridge.supervisor = None
        try:
            wtwin.start_hosting(FakeItem())
        finally:
            wtwin.bridge.host, wtwin.bridge.supervisor = saved_host, saved_sup
        self.assertEqual(len(hosted), 1, "nothing joined: no confirm, just host")

    def test_start_hosting_confirms_before_leaving_a_room(self):
        saved = (wtwin.bridge.host, wtwin.bridge.supervisor, wtwin.confirm_host)
        hosted = []
        wtwin.bridge.host = hosted.append
        wtwin.bridge.supervisor = object()
        try:
            wtwin.confirm_host = lambda *a, **k: False
            wtwin.start_hosting(FakeItem())
            self.assertEqual(hosted, [], "declined: must not leave the room")
            wtwin.confirm_host = lambda *a, **k: True
            wtwin.start_hosting(FakeItem())
        finally:
            (wtwin.bridge.host, wtwin.bridge.supervisor,
             wtwin.confirm_host) = saved
        self.assertEqual(len(hosted), 1, "confirmed: host the new room")


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

    def test_invite_applies_the_response_room_at_once(self):
        # the invite response is the updated room, so applying it here is what
        # makes the invited member appear in the open lobby immediately instead
        # of on the next roster push (up to the 15 s poll)
        class FakeLobby(object):
            def __init__(self):
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.supervisor = FakeSupervisor()
        lobby = FakeLobby()
        self.bridge.lobby = lobby
        self.api.room_out = dict(ROOM_JSON, users=ROOM_JSON["users"] + [
            {"id": 9, "username": "new", "title": "New", "uuid": "u9"}])
        self.assertEqual(self.bridge.invite([9]), [])
        self.assertIn(9, self.bridge.room.user_ids,
                      "the response room replaced the stale one")
        self.assertGreaterEqual(lobby.refreshes, 1,
                                "the open lobby was repainted")

    def test_invite_applies_when_a_poll_replaced_the_room_object(self):
        # the 15 s roster poll replaces bridge.room with a fresh Room, so an
        # identity check against the picker's snapshot fails - and then neither
        # the response nor a refresh is applied, leaving the invitee to appear
        # only on the next poll (the reported 15 s delay)
        class FakeLobby(object):
            def __init__(self):
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        self.bridge.supervisor = FakeSupervisor()
        lobby = FakeLobby()
        self.bridge.lobby = lobby
        picker_room = watchtogether.Room(ROOM_JSON)       # snapshot at open
        self.bridge.room = picker_room
        self.bridge.room = watchtogether.Room(ROOM_JSON)  # the poll replaced it
        self.api.room_out = dict(ROOM_JSON, users=ROOM_JSON["users"] + [
            {"id": 9, "username": "new", "title": "New", "uuid": "u9"}])
        self.assertEqual(self.bridge.invite([9], picker_room), [])
        self.assertIn(9, self.bridge.room.user_ids,
                      "the invitee must be applied even though the poll "
                      "replaced the room object")
        self.assertGreaterEqual(lobby.refreshes, 1)

    def test_refresh_room_repaints_the_open_lobby(self):
        # the worker assigned self.room without telling the lobby, so a
        # refreshed room never reached the screen
        class FakeLobby(object):
            def __init__(self):
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        lobby = FakeLobby()
        self.bridge.lobby = lobby
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.api.room_out = dict(ROOM_JSON, users=ROOM_JSON["users"] + [
            {"id": 9, "username": "new", "title": "New", "uuid": "u9"}])
        self.bridge._refresh_room_work(sup)
        self.assertEqual(lobby.refreshes, 1, "the refreshed room must repaint")
        self.assertIn(9, self.bridge.room.user_ids)

    def test_invite_does_not_apply_another_rooms_response(self):
        # inviting into a room that is not the bridge's current one must not
        # repaint this room's lobby
        class FakeLobby(object):
            def __init__(self):
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        self.bridge.room = watchtogether.Room(dict(ROOM_JSON, id="current"))
        other = watchtogether.Room(dict(ROOM_JSON, id="other"))
        lobby = FakeLobby()
        self.bridge.lobby = lobby
        self.assertEqual(self.bridge.invite([1], other), [])
        self.assertEqual(lobby.refreshes, 0)

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

    def test_remote_pause_republishes_the_paused_state(self):
        # the supervisor sends the last snapshot it was fed, so applying a
        # remote pause must feed it now: otherwise its next 1 Hz beat publishes
        # the pre-pause snapshot, the relay adopts it (last-setBy wins) and the
        # peer resumes - seen live as the browser pausing, resuming, pausing
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.on_state(self.remote(self.player.position, paused=True))
        self.assertEqual(sup.sent[-1]["paused"], True,
                         "the applied pause must be published at once")
        self.assertEqual(sup.sent[-1]["doSeek"], False)

    def test_remote_resume_republishes_the_resumed_state(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.player.paused = True
        self.bridge.on_state(self.remote(self.player.position, paused=False))
        self.assertEqual(sup.sent[-1]["paused"], False,
                         "the applied resume must be published at once")

    def test_remote_seek_republishes_the_target_position(self):
        # a stale position in the snapshot would make the peer seek back
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        dialog = FakeDialog()
        self.player.handler.dialog = dialog
        target = self.player.position + 10
        self.bridge.on_state(self.remote(target, paused=False))
        self.assertEqual(dialog.seeks, [int(target * 1000)])
        self.assertEqual(sup.sent[-1]["position"], target,
                         "the applied seek must be published at once")
        self.assertEqual(sup.sent[-1]["doSeek"], False)

    def test_remote_pause_arms_the_pause_echo(self):
        # only the matching kind is the echo: a resume inside the window is a
        # real user action and must still reach the bridge
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position, paused=True))
        self.assertEqual(self.player.wt_applied_kind, "pause")

    def test_remote_resume_arms_the_play_echo(self):
        self.player.paused = True
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.remote(self.player.position, paused=False))
        self.assertEqual(self.player.wt_applied_kind, "play")

    def test_remote_seek_arms_the_seek_echo(self):
        self.bridge.supervisor = FakeSupervisor()
        self.player.handler.dialog = FakeDialog()
        self.bridge.on_state(self.remote(self.player.position + 10, paused=False))
        self.assertEqual(self.player.wt_applied_kind, "seek")

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


class BufferingPeerTest(BridgeTestCase):
    """The drift-seek gate: a slow or silent peer must not drag the host
    backwards (2026-10-23 live session — the host was seeked back ~10 s on
    every drift while the peer buffered)."""

    def slow_peer(self, position, anchor_pos=0.0, anchor_age=9.0, do_seek=False):
        """Fake a peer whose position advanced < 0.9x realtime over the anchor
        window, so peer_slow() reports True."""
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge._peer_probe = (anchor_pos, time.monotonic() - anchor_age)
        sup.session.remote = {"position": position, "paused": False,
                              "doSeek": do_seek}

    def state(self, position, do_seek=False):
        return {"position": position, "paused": False, "doSeek": do_seek,
                "setBy": syncplay.build_identity("d", "n", 1000002)}

    def test_stale_peer_is_not_chased_backwards(self):
        # a peer that has gone quiet must not drag the host back. The gate no
        # longer consults peer_stale() (it is refreshed before the branch, so it
        # is never true there); this stays as a regression guard for the rule.
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.peer_stale = lambda: True
        self.player.position = 50.0
        self.bridge.on_state(self.state(40.0))
        self.assertEqual(self.player.seek_times, [])

    def test_a_healthy_peer_is_not_chased_backwards_either(self):
        # 2026-10-23: peer_slow() flickers while a stuck peer wobbles by a
        # second, and each "not slow" beat used to yank the host back 10-27 s.
        # Nothing moves us backwards for drift now.
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge.peer_slow = lambda: False
        self.bridge.peer_stale = lambda: False
        self.player.position = 50.0
        self.bridge.on_state(self.state(20.0))          # 30 s behind us
        self.assertEqual(self.player.seek_times, [])

    def test_slow_peer_is_not_chased_backwards(self):
        self.slow_peer(1.0)          # peer frozen near 0 while the host runs
        self.player.position = 50.0
        self.bridge.on_state(self.state(1.0))
        self.assertEqual(self.player.seek_times, [])

    def test_slow_peer_with_a_forward_target_still_seeks(self):
        # a peer ahead of us that is only advancing slowly: converging forward
        # is legitimate and must not be gated
        self.slow_peer(60.0, anchor_pos=55.0)   # 60 - 55 = 5 < 0.9 * 9: slow
        self.player.position = 50.0
        self.bridge.on_state(self.state(60.0))
        self.assertEqual(self.player.seek_times, [60.0])

    def test_slow_peer_doseek_still_seeks(self):
        # §5.6: an explicit seek command is applied regardless of the peer's
        # buffering — the doSeek branch is not gated
        self.slow_peer(40.0, do_seek=True)
        self.player.position = 50.0
        self.bridge.on_state(self.state(40.0, do_seek=True))
        self.assertEqual(self.player.seek_times, [40.0])

    def test_gated_seek_leaves_drift_alone_on_the_next_beat(self):
        # the live jolt was one seek per beat; a gated seek must not accumulate
        self.slow_peer(1.0)
        self.player.position = 50.0
        self.bridge.on_state(self.state(1.0))
        self.bridge.on_state(self.state(1.0))
        self.assertEqual(self.player.seek_times, [])

    def test_applied_drift_seek_toasts_once_then_dedupes(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.player.position = 50.0
        remote = self.state(250.0)          # forward: the gate leaves it alone
        self.bridge.on_state(remote)
        self.assertEqual(self.toasts,
                         [util.T(35095, "{} jumped to {}").format("Guest", "4:10")])
        # a second correction inside 4 s: expire the seek cooldown so the seek
        # applies, then assert the toast dedupe (not the cooldown) holds
        self.bridge._remote_seek_at = 0.0
        self.bridge.on_state(remote)
        self.assertEqual(self.toasts,
                         [util.T(35095, "{} jumped to {}").format("Guest", "4:10")])


class ToastTest(BridgeTestCase):
    """Event toasts: pause/resume/jump and join/leave, deduped per identity.

    Toasts are always on (no setting). One toast per (identity, kind) per 4 s,
    and nothing for a nameless/unparseable identity."""

    def peer(self, user_id=1000002):
        return syncplay.build_identity("d", "n", user_id)

    def state(self, position=None, paused=False, do_seek=False, set_by=None):
        return {"position": self.player.position if position is None
                else position,
                "paused": paused, "doSeek": do_seek,
                "setBy": set_by if set_by is not None else self.peer()}

    def test_pause_transition_toasts_once(self):
        self.bridge.supervisor = FakeSupervisor()
        remote = self.state(paused=True)
        self.bridge.on_state(remote)
        self.bridge.on_state(remote)   # a repeated identical state: no repeat
        self.assertEqual(self.toasts, [util.T(35093, "{} paused").format("Guest")])

    def test_resume_toasts(self):
        self.player.paused = True
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.state(paused=False))
        self.assertEqual(self.toasts, [util.T(35094, "{} resumed").format("Guest")])

    def test_doseek_toasts_with_the_formatted_time(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.state(position=250.0, do_seek=True))
        self.assertEqual(self.toasts, [
            util.T(35095, "{} jumped to {}").format("Guest", "4:10")])

    def test_join_and_leave_toast_with_the_peer_name(self):
        self.bridge.supervisor = FakeSupervisor()
        key = self.peer()
        self.bridge.on_event("joined", key)
        self.bridge.on_event("left", key)
        self.assertEqual(self.toasts, [
            util.T(35096, "{} joined the room").format("Guest"),
            util.T(35097, "{} left the room").format("Guest")])

    def test_our_own_events_never_toast(self):
        # Self is filtered upstream in syncplay (is_self -> self_echo, on_state
        # never fires; self "left" is advisory, on_event never fires), not in
        # the bridge. Wire the bridge's real callbacks to a Session and feed
        # self frames: nothing may toast.
        ident = syncplay.build_identity("dev", "Me", 1000001)
        self.bridge.supervisor = FakeSupervisor()
        sess = syncplay.Session(room="r", identity=ident,
                                on_state=self.bridge.on_state,
                                on_event=self.bridge.on_event)
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.1},
            "playstate": {"position": 50.0, "paused": True, "doSeek": False,
                          "setBy": ident + "_"}}})
        sess.on_message({"Set": {"user": {ident: {
            "room": {"name": "r"}, "event": {"left": True}}}}})
        self.assertEqual(self.toasts, [])

    def test_unparseable_identity_toasts_nothing(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.state(paused=True, set_by="not json"))
        self.bridge.on_event("joined", "not json")
        self.assertEqual(self.toasts, [])

    def test_flapping_peer_toasts_once_within_4s_then_again_after(self):
        self.bridge.supervisor = FakeSupervisor()
        remote = self.state(paused=True)
        self.bridge.on_state(remote)
        self.assertEqual(len(self.toasts), 1)
        self.bridge.on_state(remote)          # still inside the 4 s window
        self.assertEqual(len(self.toasts), 1)
        # back-date the stored stamp past the 4 s dedupe window
        self.bridge._toasted[(wtwin.identity_user_id(self.peer()), "paused")] = \
            time.monotonic() - 5.0
        self.bridge.on_state(remote)
        self.assertEqual(len(self.toasts), 2)

    def test_toast_header_is_the_watch_together_title(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge.on_state(self.state(paused=True))
        self.assertEqual(self.notifications[0][1],
                         util.T(35053, "Watch Together"))


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


class DetectorBridgeTest(BridgeTestCase):
    """_start_scan/_poll_detector/_cancel_detector: the host pre-scan gate.

    The scan path resolution is best-effort and covered elsewhere; here we
    patch p3i_detector (start/status/cancel) to drive the prepared-state
    machine that gates host readiness until the job completes or fails open."""

    def setUp(self):
        super(DetectorBridgeTest, self).setUp()
        self.bridge._hosting = True
        self.bridge._detector_scan_path = lambda item: "/media/movie.mkv"
        self._saved_start = wtwin.p3i_detector.start
        self._saved_status = wtwin.p3i_detector.status
        self._saved_cancel = wtwin.p3i_detector.cancel
        self.start_calls = []
        self.status_calls = []
        self.cancel_calls = []
        self.start_result = "job-1"
        self.status_result = {"status": "completed"}
        wtwin.p3i_detector.start = self._start
        wtwin.p3i_detector.status = self._status
        wtwin.p3i_detector.cancel = self._cancel

    def tearDown(self):
        wtwin.p3i_detector.start = self._saved_start
        wtwin.p3i_detector.status = self._saved_status
        wtwin.p3i_detector.cancel = self._saved_cancel
        super(DetectorBridgeTest, self).tearDown()

    def _start(self, path):
        self.start_calls.append(path)
        return self.start_result

    def _status(self, requestid):
        self.status_calls.append(requestid)
        return self.status_result

    def _cancel(self, requestid):
        self.cancel_calls.append(("Cancel", {"requestid": requestid}))

    def room(self, user_ids):
        return watchtogether.Room({"users": [{"id": i, "title": str(i)}
                                             for i in user_ids]})

    def fire_ready(self, roster):
        self.bridge.supervisor.session.roster = roster
        self.bridge._on_ready(None, None)

    def test_host_ready_held_until_scan_completes(self):
        self.bridge._start_scan(object(), gate=True)
        sup = FakeSupervisor()
        self.bridge._update_ready(sup)
        self.assertIs(sup.ready, False)
        self.assertIs(self.bridge._player_ready, False)
        self.status_result = {"status": "completed"}
        self.bridge._poll_detector()
        self.bridge._update_ready(sup)
        self.assertIs(sup.ready, True)

    def test_auto_start_does_not_fire_while_prepared_false(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge._start_scan(object(), gate=True)
        self.bridge._update_ready(sup)
        self.bridge.room = self.room([1])
        self.fire_ready({syncplay.build_identity("d", "n", 1): {"isReady": True}})
        self.assertEqual(self.player.controls, [])

    def test_scan_timeout_fails_open(self):
        self.bridge._start_scan(object(), gate=True)
        self.bridge._detector_deadline = time.monotonic() - 1
        self.status_result = {"status": "running"}
        self.bridge._poll_detector()
        self.assertTrue(self.bridge._prepared)
        self.assertIsNone(self.bridge._detector_requestid)
        # the zombie scan is cancelled, not just forgotten: otherwise it holds
        # the shared p3i scanner reservation until the server reaps it
        self.assertIn(("Cancel", {"requestid": "job-1"}), self.cancel_calls)

    def test_non_completed_terminal_status_fails_open(self):
        self.bridge._start_scan(object(), gate=True)
        self.status_result = {"status": "failed"}
        self.bridge._poll_detector()
        self.assertTrue(self.bridge._prepared)
        self.assertIsNone(self.bridge._detector_requestid)

    def test_completed_scan_stores_requestid_on_player(self):
        self.bridge._start_scan(object(), gate=True)
        self.status_result = {"status": "completed"}
        self.bridge._poll_detector()
        self.assertEqual(self.player.wt_detector_requestid, "job-1")

    def test_late_result_after_leave_is_ignored(self):
        self.bridge._start_scan(object(), gate=True)
        self.bridge._detector_requestid = None
        self.status_result = {"status": "completed"}
        self.bridge._poll_detector()
        self.assertIsNone(self.player.wt_detector_requestid)

    def test_leave_cancels_the_job(self):
        self.bridge._start_scan(object(), gate=True)
        self.bridge.leave()
        self.assertIn(("Cancel", {"requestid": "job-1"}), self.cancel_calls)
        self.assertTrue(self.bridge._prepared)

    def test_disconnect_cancels_the_job(self):
        self.bridge._start_scan(object(), gate=True)
        self.bridge.disconnect()
        self.assertIn(("Cancel", {"requestid": "job-1"}), self.cancel_calls)
        self.assertIsNone(self.bridge._detector_requestid)
        self.assertTrue(self.bridge._prepared)

    def test_teardown_clears_the_detector_job_on_the_player(self):
        self.player.wt_detector_requestid = "job-1"
        self.player.wt_detector_part_index = 0
        self.bridge.disconnect()
        self.assertIsNone(self.player.wt_detector_requestid)
        self.assertEqual(self.player.wt_detector_part_index, 0)


class FakePart(object):
    """Part surface _detector_scan_path reads: getPathMappedUrl/getAbsolutePath."""

    def __init__(self, mapped=None, key="1"):
        self._mapped = mapped
        self._key = key

    def getPathMappedUrl(self):
        return self._mapped

    def getAbsolutePath(self, kind):
        assert kind == "key"
        return "/library/parts/{0}".format(self._key)

    def getSelectedStreamOfType(self, *args, **kwargs):
        return None

    def isAccessible(self):
        return True


class FakeMedia(object):
    """Media surface plexnet.MediaChoice reads: parts + indirectHeaders."""

    def __init__(self, part):
        self.parts = [part]
        self.indirectHeaders = {}


class FakeChoice(object):
    """A mediaChoice stand-in: only .part is read by the resolver."""

    def __init__(self, part):
        self.part = part


class ScanServer(object):
    def __init__(self):
        self.builds = []

    def buildUrl(self, path, includeToken=False):
        self.builds.append((path, includeToken))
        return "https://plex.test" + path


class ScanItem(object):
    """Item surface _detector_scan_path reads: mediaChoice, media(), getServer()."""

    def __init__(self, media_choice=None, media_list=None, server=None):
        self.mediaChoice = media_choice
        self._media = media_list or []
        self._server = server

    def media(self):
        return self._media

    def getServer(self):
        return self._server


class DetectorScanPathTest(BridgeTestCase):
    """_detector_scan_path: the sole Direct Play URI resolver for the pre-scan.

    Stubbed in every bridge test above, so its branches need direct coverage:
    a regression returning None would silently disable the whole feature."""

    def test_mapped_path_wins(self):
        part = FakePart(mapped="/media/movie.mkv")
        item = ScanItem(media_choice=FakeChoice(part), server=ScanServer())
        self.assertEqual(self.bridge._detector_scan_path(item), "/media/movie.mkv")

    def test_falls_back_to_the_server_key_url(self):
        part = FakePart(mapped=None)
        server = ScanServer()
        item = ScanItem(media_choice=FakeChoice(part), server=server)
        self.assertEqual(self.bridge._detector_scan_path(item),
                         "https://plex.test/library/parts/1")
        self.assertEqual(server.builds, [("/library/parts/1", True)],
                         "buildUrl must be called with the part's key and the token")

    def test_media_choice_none_falls_back_to_part_0(self):
        part = FakePart(mapped="/media/movie.mkv")
        media = FakeMedia(part)
        item = ScanItem(media_choice=None, media_list=[media], server=ScanServer())
        self.assertEqual(self.bridge._detector_scan_path(item), "/media/movie.mkv")

    def test_empty_path_is_none(self):
        # buildUrl returning "" must not slip _start_scan's `path is None` guard
        part = FakePart(mapped=None)
        server = ScanServer()
        server.buildUrl = lambda path, includeToken=False: ""
        item = ScanItem(media_choice=FakeChoice(part), server=server)
        self.assertIsNone(self.bridge._detector_scan_path(item))

    def test_raising_part_is_none(self):
        class BoomPart(object):
            def getPathMappedUrl(self):
                raise RuntimeError("boom")
        item = ScanItem(media_choice=FakeChoice(BoomPart()), server=ScanServer())
        self.assertIsNone(self.bridge._detector_scan_path(item))


class GuestScanTest(BridgeTestCase):
    """room_clicked's guest branch: a best-effort pre-scan that never gates
    readiness (gate=False), never blocks the join, and is abandoned if the room
    starts first (nothing binds to the player)."""

    def setUp(self):
        super(GuestScanTest, self).setUp()
        self.bridge._detector_scan_path = lambda item: "/media/movie.mkv"
        self._saved_start = wtwin.p3i_detector.start
        self._saved_status = wtwin.p3i_detector.status
        self.start_calls = []
        self.status_calls = []
        self.start_result = "job-1"
        self.status_result = {"status": "running"}
        wtwin.p3i_detector.start = self._start
        wtwin.p3i_detector.status = self._status

    def tearDown(self):
        wtwin.p3i_detector.start = self._saved_start
        wtwin.p3i_detector.status = self._saved_status
        super(GuestScanTest, self).tearDown()

    def _start(self, path):
        self.start_calls.append(path)
        getattr(self, "events", []).append("scan")
        return self.start_result

    def _status(self, requestid):
        self.status_calls.append(requestid)
        return self.status_result

    def _click(self, item):
        """Run room_clicked down the guest branch: a guest not yet in the room
        clicks an unstarted room tile. The join/takeover steps are side-stepped
        (not the behaviour under test)."""
        self.events = []
        self.bridge._room_media_item = lambda room: self.events.append("media") or item
        self.bridge._open_lobby = lambda host=False: self.events.append(("lobby", host))
        self.bridge._watch_room = lambda room: self.events.append("watch")
        self.bridge._join_or_switch = lambda room_id, leave_first: self.events.append("join")
        self.bridge.supervisor = None
        self.bridge._room_unstarted = lambda: True
        self.player.video = None          # nothing playing -> no takeover prompt
        self.bridge.room_clicked(watchtogether.Room(ROOM_JSON))
        return self.events

    def test_guest_resolves_item_before_lobby_and_scans(self):
        events = self._click(FakeItem())
        self.assertTrue(self.start_calls, "the guest scan must start")
        self.assertIs(self.bridge._prepared, True,
                      "guest scan never gates readiness")
        self.assertLess(events.index("media"), events.index("scan"),
                        "resolve the item before scanning")
        self.assertLess(events.index("scan"), events.index(("lobby", False)),
                        "scan before opening the lobby")
        self.assertEqual(events, ["join", "media", "scan", ("lobby", False),
                                  "watch"])

    def test_guest_scan_abandons_on_start(self):
        # the guest's best-effort scan is still running when the room starts:
        # nothing completed, so nothing binds to the player (no bind => no block)
        self._click(FakeItem())
        self.assertTrue(self.start_calls, "the guest scan must have started")
        self.bridge._poll_detector()          # the tick, mid-scan
        self.assertIsNone(self.player.wt_detector_requestid)
        self.assertIs(self.bridge._prepared, True,
                      "an abandoned scan still leaves readiness un-gated")


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

    def test_old_kodi_widens_the_tolerance(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 20
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))    # 2s ahead: no seek
            self.assertEqual(self.player.seek_times, [], "2s drift must not seek")
            self.bridge.on_state(self.tempo_state(-10.0))  # 10s behind: wide enough
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(self.player.seek_times, [self.player.position + 10.0])
        self.assertEqual(calls, [], "no SetTempo RPC on old Kodi")

    def test_set_tempo_failure_does_not_seek(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc([], fail=True)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(self.player.seek_times, [],
                         "a tempo failure must not degrade into a seek")

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
        self.assertEqual(self.player.seek_times, [], "a tempo failure must not seek")

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

    def test_two_failures_mark_tempo_unavailable(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls, fail=True)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))   # failure 1
            self.bridge._tempo_retry_at = 0.0             # expire the backoff
            self.bridge.on_state(self.tempo_state(2.0))   # failure 2 -> unavailable
            self.assertTrue(self.bridge._tempo_unavailable,
                            "two failures must mark tempo unavailable")
            self.bridge.on_state(self.tempo_state(5.0))   # 5s drift: no seek
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(self.player.seek_times, [],
                         "a 5s drift must not seek once tempo is unavailable")

    def test_first_refusal_already_widens_the_tolerance(self):
        # a player that refuses SetTempo must not get seeks for a 4-10s drift
        # while the second probe is still 60s away (2026-10-23 seek burst)
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls, fail=True)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge.on_state(self.tempo_state(2.0))   # failure 1 only
            self.bridge.on_state(self.tempo_state(5.0))   # 5s drift: no seek
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertFalse(self.bridge._tempo_unavailable, "still only one failure")
        self.assertEqual(self.player.seek_times, [],
                         "one refusal must already widen the tolerance")
        self.assertEqual(len(calls), 1, "the backoff still holds the retry")

    def test_no_seek_while_seeking_or_caching(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            ENV.cond_visibility["Player.Seeking"] = True
            self.bridge.on_state(self.tempo_state(5.0))   # would seek
            self.assertEqual(self.player.seek_times, [])
            ENV.cond_visibility.pop("Player.Seeking", None)
            ENV.cond_visibility["Player.Caching"] = True
            self.bridge.on_state(self.tempo_state(5.0))   # would seek
            self.assertEqual(self.player.seek_times, [])
        finally:
            ENV.cond_visibility.pop("Player.Seeking", None)
            ENV.cond_visibility.pop("Player.Caching", None)
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc

    def test_remote_seek_is_rate_limited(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge._remote_seek_at = time.monotonic()  # a seek just happened
            self.bridge.on_state(self.tempo_state(-5.0))    # forward: we are behind
            self.assertEqual(self.player.seek_times, [],
                             "cooldown must suppress the next seek")
            self.bridge._remote_seek_at = time.monotonic() - wtwin.WT_SEEK_COOLDOWN
            self.bridge.on_state(self.tempo_state(-5.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(self.player.seek_times, [self.player.position + 5.0])

    def test_seek_apply_publishes_the_target(self):
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        sup = FakeSupervisor()
        try:
            self.bridge.supervisor = sup
            self.bridge.on_state(self.tempo_state(-5.0))  # forward drift -> seek
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(sup.sent,
                         [{"position": self.player.position + 5.0,
                           "paused": False, "doSeek": False}])

    def test_pause_is_published_even_when_the_seek_is_blocked(self):
        sup = FakeSupervisor()
        try:
            self.bridge.supervisor = sup
            ENV.cond_visibility["Player.Seeking"] = True
            self.bridge.on_state({
                "position": self.player.position,
                "paused": True,          # pause transition: player is not paused
                "doSeek": True,          # and the room asks for a seek (blocked)
                "setBy": "other-identity",
            })
        finally:
            ENV.cond_visibility.pop("Player.Seeking", None)
        self.assertEqual(self.player.controls, ["pause"],
                         "the pause must still be applied")
        self.assertEqual(self.player.seek_times, [],
                         "the blocked seek must not fire")
        self.assertEqual(sup.sent,
                         [{"position": self.player.position,
                           "paused": True, "doSeek": False}],
                         "the applied pause must still be published")


class PauseCatchupTest(BridgeTestCase):
    """Optional pause-based catch-up for players without tempo (§6.2 alt).

    Only reached once _tempo_unavailable is True (Kodi < 21 or SetTempo
    refused twice); the freeze is local and must never be broadcast."""

    def state(self, delta, paused=False):
        return {"position": self.player.position - delta, "paused": paused,
                "doSeek": False, "setBy": "other-identity"}

    def test_setting_off_leaves_the_drift_alone(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge._tempo_unavailable = True
        self.player.position = 52.0        # 2 s ahead of the room at 50
        self.bridge.on_state(self.state(2.0))
        self.assertEqual(self.player.controls, [],
                         "the setting is off: no pause must be applied")
        self.assertEqual(self.bridge._catchup_until, 0.0)

    def test_two_seconds_ahead_pauses_without_broadcasting(self):
        util.setSetting("watchtogether.pause_catchup", "true")
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge._tempo_unavailable = True
        self.player.position = 52.0
        self.bridge.on_state(self.state(2.0))
        self.assertEqual(self.player.controls, ["pause"])
        self.assertEqual(self.player.wt_applied_kind, "pause")
        self.assertGreater(self.bridge._catchup_until, 0.0,
                           "the freeze deadline is armed")
        self.assertEqual(sup.sent, [], "the local freeze must not be broadcast")

    def test_beat_inside_the_window_is_inert(self):
        util.setSetting("watchtogether.pause_catchup", "true")
        self.bridge.supervisor = FakeSupervisor()
        self.bridge._tempo_unavailable = True
        self.player.position = 52.0
        self.bridge.on_state(self.state(2.0))       # arms the freeze
        self.player.controls = []
        self.bridge.on_state(self.state(2.0))       # still inside the window
        self.assertEqual(self.player.controls, [],
                         "no control while the catch-up pause is pending")

    def test_deadline_resume_plays_with_the_echo_gate(self):
        util.setSetting("watchtogether.pause_catchup", "true")
        self.bridge.supervisor = FakeSupervisor()
        self.bridge._tempo_unavailable = True
        self.bridge._catchup_until = time.monotonic() - 1.0   # deadline passed
        self.player.position = 50.0                           # now caught up
        self.bridge.on_state(self.state(0.0))
        self.assertIn("play", self.player.controls)
        self.assertEqual(self.player.wt_applied_kind, "play")
        self.assertEqual(self.bridge._catchup_until, 0.0,
                         "the deadline is cleared once it passes")

    def test_pending_freeze_cleared_when_playback_stops(self):
        util.setSetting("watchtogether.pause_catchup", "true")
        self.bridge.supervisor = FakeSupervisor()
        self.bridge._tempo_unavailable = True
        # expired, not future: without the fix the next playing beat would see
        # it in the past, resume, and issue a spurious play on the new video
        self.bridge._catchup_until = time.monotonic() - 1.0
        # a beat while no video is playing: the freeze must be cleared
        self.player.video = None
        self.bridge.on_state(self.state(0.0))
        self.assertEqual(self.bridge._catchup_until, 0.0,
                         "stopping playback clears a pending catch-up pause")
        self.assertEqual(self.player.controls, [],
                         "no resume is issued while there is no video")
        # a fresh video, room paused: no stale play must leak onto it
        self.player.video = FakeVideo("227117")
        self.bridge.on_state({"position": 50.0, "paused": True,
                              "doSeek": False, "setBy": "other-identity"})
        self.assertNotIn("play", self.player.controls,
                         "a cleared freeze must not resume the next video")

    def patch_rpc(self, calls):
        class RPCPlayer(object):
            def GetActivePlayers(self):
                return [{"playerid": 1, "type": "video"}]

            def SetTempo(self, playerid, tempo):
                calls.append((playerid, tempo))

        class RPC(object):
            Player = RPCPlayer()
        return RPC()

    def test_tempo_band_drift_is_a_no_op_without_tempo(self):
        # a tempo-band drift on a tempo-less player must neither SetTempo nor
        # seek (the band is "leave it", and the per-beat log reports action=None)
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge._tempo_unavailable = True
            self.player.position = 52.0        # 2 s ahead of the room at 50
            self.bridge.on_state(self.state(2.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(calls, [], "no SetTempo when tempo is unavailable")
        self.assertEqual(self.player.seek_times, [], "and no seek either")
        self.assertEqual(self.player.controls, [],
                         "setting off: the drift is left alone")

    def test_tempo_band_drift_still_runs_the_catchup_pause(self):
        util.setSetting("watchtogether.pause_catchup", "true")
        saved_major, saved_rpc = wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc
        calls = []
        wtwin.util.KODI_VERSION_MAJOR = 21
        wtwin.util.rpc = self.patch_rpc(calls)
        try:
            self.bridge.supervisor = FakeSupervisor()
            self.bridge._tempo_unavailable = True
            self.player.position = 52.0
            self.bridge.on_state(self.state(2.0))
        finally:
            wtwin.util.KODI_VERSION_MAJOR, wtwin.util.rpc = saved_major, saved_rpc
        self.assertEqual(calls, [], "no SetTempo when tempo is unavailable")
        self.assertEqual(self.player.seek_times, [], "and no seek either")
        self.assertEqual(self.player.controls, ["pause"],
                         "the opt-in catch-up pause is still applied")


class DisplayNameTest(BridgeTestCase):
    def test_resolves_through_participants_title(self):
        key = syncplay.build_identity("d", "n", 1000001)
        self.assertEqual(self.bridge.display_name(key), "Owner")

    def test_falls_back_to_username(self):
        self.bridge.room = watchtogether.Room(dict(
            ROOM_JSON, users=[{"id": 1000001, "username": "owner"}]))
        key = syncplay.build_identity("d", "n", 1000001)
        self.assertEqual(self.bridge.display_name(key), "owner")

    def test_falls_back_to_device_name_when_no_participant_matches(self):
        key = syncplay.build_identity("d", "Bedroom Kodi", 999)
        self.assertEqual(self.bridge.display_name(key), "Bedroom Kodi")

    def test_returns_empty_when_neither_exists(self):
        self.assertEqual(self.bridge.display_name(None), "")
        key = syncplay.build_identity("d", "", 999)   # no participant, no name
        self.assertEqual(self.bridge.display_name(key), "")


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


class MemberStateTest(KodiTestCase):
    """member_state: the participant status truth table (Task 2)."""

    def test_truth_table(self):
        self.assertEqual(wtwin.member_state(False, True), wtwin.STATUS_INVITED)
        self.assertEqual(wtwin.member_state(False, None), wtwin.STATUS_INVITED)
        self.assertEqual(wtwin.member_state(False, False), wtwin.STATUS_INVITED)
        self.assertEqual(wtwin.member_state(True, None), wtwin.STATUS_JOINING)
        self.assertEqual(wtwin.member_state(True, False), wtwin.STATUS_BUFFERING)
        self.assertEqual(wtwin.member_state(True, True, stale=True),
                         wtwin.STATUS_BUFFERING)
        self.assertEqual(wtwin.member_state(True, True, slow=True),
                         wtwin.STATUS_BUFFERING)
        self.assertEqual(wtwin.member_state(True, True), wtwin.STATUS_WATCHING)

    def test_state_label(self):
        self.assertEqual(wtwin.state_label(wtwin.STATUS_INVITED, "R"),
                         util.T(35076, "Invited"))
        self.assertEqual(wtwin.state_label(wtwin.STATUS_JOINING, "R"),
                         util.T(35092, "Joining"))
        self.assertEqual(wtwin.state_label(wtwin.STATUS_BUFFERING, "R"),
                         util.T(35091, "Buffering"))
        self.assertEqual(wtwin.state_label(wtwin.STATUS_WATCHING, "R"), "R")


class LobbyRowsStatusTest(KodiTestCase):
    """lobby_rows with state_for: the richer status set."""

    def room(self, users):
        return watchtogether.Room({"users": users})

    def roster(self):
        return {
            syncplay.build_identity("d", "n", 1): {"isReady": True},
            syncplay.build_identity("d", "n", 2): {"isReady": None},
            syncplay.build_identity("d", "n", 3): {"isReady": False},
            # id 4 is absent: invited (not on the roster)
        }

    def test_full_status_set(self):
        room = self.room([{"id": 1, "title": "A"}, {"id": 2, "title": "B"},
                          {"id": 3, "title": "C"}, {"id": 4, "title": "D"}])
        rows = wtwin.lobby_rows(room, self.roster(),
                                state_for=lambda uid: (False, False))
        self.assertEqual([r["status"] for r in rows],
                         [util.T(35075, "Ready"), util.T(35092, "Joining"),
                          util.T(35091, "Buffering"), util.T(35076, "Invited")])

    def test_stale_peer_shows_buffering(self):
        room = self.room([{"id": 1, "title": "A"}])
        rows = wtwin.lobby_rows(room, self.roster(),
                                state_for=lambda uid: (True, False))
        self.assertEqual([r["status"] for r in rows],
                         [util.T(35091, "Buffering")])

    def test_no_state_for_keeps_old_behaviour(self):
        room = self.room([{"id": 1, "title": "A"}, {"id": 4, "title": "D"}])
        rows = wtwin.lobby_rows(room, self.roster())
        self.assertEqual([r["status"] for r in rows],
                         [util.T(35075, "Ready"), util.T(35076, "Invited")])


class PeerHeuristicsTest(BridgeTestCase):
    """peer_stale/peer_slow: the staleness heuristics (Task 2)."""

    def test_peer_stale_after_five_seconds(self):
        self.assertFalse(self.bridge.peer_stale())
        self.bridge._last_remote_state_at = time.monotonic()
        self.assertFalse(self.bridge.peer_stale())
        self.bridge._last_remote_state_at = time.monotonic() - 6.0
        self.assertTrue(self.bridge.peer_stale())

    def test_apply_remote_records_the_state_heartbeat(self):
        self.bridge.supervisor = FakeSupervisor()
        self.player.video = None      # early return, but past the checks
        self.bridge.on_state({"position": 0.0, "paused": True,
                              "doSeek": False, "setBy": "other-identity"})
        self.assertGreater(self.bridge._last_remote_state_at, 0.0)
        self.assertFalse(self.bridge.peer_stale())

    def test_peer_slow_only_for_two_participants(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)   # 2 users
        sup.session.remote = {"position": 1.0, "paused": False}
        self.bridge._peer_probe = (0.0, time.monotonic() - 9.0)
        self.assertTrue(self.bridge.peer_slow())
        self.bridge.room = watchtogether.Room(dict(
            ROOM_JSON, users=ROOM_JSON["users"] + [{"id": 3, "username": "x"}]))
        self.assertFalse(self.bridge.peer_slow())
        self.assertIsNone(self.bridge._peer_probe,
                          "a member join/leave must drop the anchor")

    def test_backward_jump_is_not_slow(self):
        # a peer's 30 s rewind drops the remote position; without re-anchoring
        # the fixed anchor keeps pos-anchor below 0.9x elapsed for ~10x the jump
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup.session.remote = {"position": 100.0, "paused": False, "doSeek": False}
        self.bridge._peer_probe = (100.0, time.monotonic() - 9.0)
        sup.session.remote = {"position": 70.0, "paused": False, "doSeek": False}
        self.assertFalse(self.bridge.peer_slow())
        self.assertEqual(self.bridge._peer_probe[0], 70.0)

    def test_do_seek_is_not_slow(self):
        # an explicit seek command (even to the same position) re-anchors the
        # probe so the seek is not read as buffering
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup.session.remote = {"position": 100.0, "paused": False, "doSeek": False}
        self.bridge._peer_probe = (100.0, time.monotonic() - 9.0)
        sup.session.remote = {"position": 100.0, "paused": False, "doSeek": True}
        self.assertFalse(self.bridge.peer_slow())

    def test_advancing_position_is_not_slow(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup.session.remote = {"position": 9.0, "paused": False}
        self.bridge._peer_probe = (0.0, time.monotonic() - 9.0)
        self.assertFalse(self.bridge.peer_slow())   # 9.0 >= 0.9 * 9.0

    def test_peer_slow_requires_eight_seconds(self):
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        sup.session.remote = {"position": 1.0, "paused": False}
        self.bridge._peer_probe = (0.0, time.monotonic() - 7.0)
        self.assertFalse(self.bridge.peer_slow())

    def test_paused_room_is_not_slow(self):
        # a paused room freezes position; that is the normal non-slow state,
        # not buffering — even after the slow window has elapsed
        sup = FakeSupervisor()
        self.bridge.supervisor = sup
        self.bridge.room = watchtogether.Room(ROOM_JSON)   # 2 participants
        sup.session.remote = {"position": 5.0, "paused": True}
        self.bridge._peer_probe = (0.0, time.monotonic() - 9.0)   # window gone
        self.assertFalse(self.bridge.peer_slow(),
                         "a paused room must not read as buffering")
        self.assertIsNone(self.bridge._peer_probe,
                          "the anchor resets so a resume is not flagged slow")

    def test_peer_state_reset_on_disconnect(self):
        self.bridge.supervisor = FakeSupervisor()
        self.bridge._last_remote_state_at = time.monotonic()
        self.bridge._peer_probe = (0.0, time.monotonic())
        self.bridge.disconnect()
        self.assertEqual(self.bridge._last_remote_state_at, 0.0)
        self.assertIsNone(self.bridge._peer_probe)

    def _as_account(self, account_id):
        """Point plexapp.ACCOUNT at a minimal account with the given id."""
        saved = wtwin.plexapp.ACCOUNT
        class Account(object):
            ID = account_id
        wtwin.plexapp.ACCOUNT = Account()
        self.addCleanup(setattr, wtwin.plexapp, "ACCOUNT", saved)
        return saved

    def test_own_row_has_no_special_case(self):
        # the peer-only heuristics return (False, False) for our own user id,
        # even when the peer is stale, and still apply to the peer's row
        self._as_account(1000001)
        self.bridge.room = watchtogether.Room(ROOM_JSON)   # self 1000001 + peer
        self.bridge._last_remote_state_at = time.monotonic() - 6.0   # peer stale
        self.assertEqual(self.bridge._participant_state("1000001"),
                         (False, False))
        self.assertEqual(self.bridge._participant_state("1000002"),
                         (True, False))

    def test_peer_stale_keeps_own_row_watching(self):
        # two-member room, peer stalled: our own row stays "Watching", the
        # peer's shows "Buffering"
        self._as_account(1000001)
        self.bridge.room = watchtogether.Room(ROOM_JSON)
        self.bridge._last_remote_state_at = time.monotonic() - 6.0   # peer stale
        roster = {
            syncplay.build_identity("d", "n", 1000001): {"isReady": True},
            syncplay.build_identity("d", "n", 1000002): {"isReady": True},
        }
        watching = util.T(35090, "Watching")
        self.assertEqual(
            wtwin.member_state_label("1000001", roster,
                                     self.bridge._participant_state, watching),
            watching)
        self.assertEqual(
            wtwin.member_state_label("1000002", roster,
                                     self.bridge._participant_state, watching),
            util.T(35091, "Buffering"))


class ParticipantsDialogStatusTest(KodiTestCase):
    """ParticipantsDialog: label2 becomes the status label (Task 2)."""

    class FakeList(object):
        def __init__(self):
            self.items = []

        def reset(self):
            self.items = []

        def addItems(self, items):
            self.items += items

    def setUp(self):
        super(ParticipantsDialogStatusTest, self).setUp()
        self._saved_room = wtwin.bridge.room
        self._saved_sup = wtwin.bridge.supervisor

    def tearDown(self):
        wtwin.bridge.room = self._saved_room
        wtwin.bridge.supervisor = self._saved_sup
        super(ParticipantsDialogStatusTest, self).tearDown()

    def test_sync_shows_status_labels(self):
        wtwin.bridge.room = watchtogether.Room({
            "users": [{"id": 1000001, "username": "owner", "title": "Owner"},
                      {"id": 1000002, "username": "guest", "title": "Guest"}]})
        sup = FakeSupervisor()
        sup.session.roster = {
            syncplay.build_identity("d", "n", 1000001): {"isReady": True},
            syncplay.build_identity("d", "n", 1000002): {"isReady": False},
        }
        wtwin.bridge.supervisor = sup
        d = wtwin.ParticipantsDialog()
        d.peopleList = self.FakeList()
        d._key = None
        d._sync()
        self.assertEqual([i.label for i in d.peopleList.items],
                         ["Owner", "Guest"])
        self.assertEqual([i.label2 for i in d.peopleList.items],
                         [util.T(35090, "Watching"),
                          util.T(35091, "Buffering")])


class RoomInfoDialogStatusTest(KodiTestCase):
    """RoomInfoDialog: no supervisor -> old username rows, not "Invited"."""

    class FakeList(object):
        def __init__(self):
            self.items = []

        def reset(self):
            self.items = []

        def addItems(self, items):
            self.items += items

    def setUp(self):
        super(RoomInfoDialogStatusTest, self).setUp()
        self._saved_sup = wtwin.bridge.supervisor

    def tearDown(self):
        wtwin.bridge.supervisor = self._saved_sup
        super(RoomInfoDialogStatusTest, self).tearDown()

    def test_no_supervisor_keeps_username(self):
        wtwin.bridge.supervisor = None
        room = watchtogether.Room({
            "id": "r",
            "users": [{"id": 1, "username": "otherviewer",
                       "title": "Other Viewer"}],
        })
        d = wtwin.RoomInfoDialog(room=room, item=None)
        d.peopleList = self.FakeList()
        d._sync()
        self.assertEqual([i.label for i in d.peopleList.items],
                         ["Other Viewer"])
        self.assertEqual([i.label2 for i in d.peopleList.items],
                         ["otherviewer"])   # the username, not "Invited"
