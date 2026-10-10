# coding=utf-8
"""lib/windows/home.py — Watch Together hub rendering (spec: home hub)."""

from __future__ import absolute_import

from kodienv import ENV

ENV.abort_requested = True
from lib import watchtogether  # noqa: E402
from lib.windows import home  # noqa: E402
from lib.windows import watchtogether as wtwin  # noqa: E402
from lib.windows.home import HomeWindow  # noqa: E402

from .base import KodiTestCase  # noqa: E402

HUB_ID = wtwin.WATCHTOGETHER_HUB_ID


class DisplayFlagsTest(KodiTestCase):
    def win(self):
        return HomeWindow.__new__(HomeWindow)

    def test_display_type_is_ar16x9(self):
        self.assertEqual(self.win().getHubDisplayType(None, HUB_ID), "ar16x9")

    def test_render_flags(self):
        flags = self.win().getHubRenderFlags(None, HUB_ID)
        self.assertTrue(flags["ar16x9"])
        self.assertFalse(flags["with_art"])
        self.assertFalse(flags["with_progress"])


class CreatorTest(KodiTestCase):
    def item(self):
        room = watchtogether.Room({"id": "r1", "title": "Room", "sourceUri": "",
                                  "users": [{"id": 1, "title": "A"}]})
        return wtwin.WatchTogetherRoomItem(room, "http://img/1")

    def test_creator_sets_title_subtitle_thumb(self):
        win = HomeWindow.__new__(HomeWindow)
        mli = win.createWatchTogetherListItem(self.item())
        self.assertEqual(mli.label, "Room")
        self.assertEqual(mli.label2, "A")
        self.assertEqual(mli.thumbnailImage, "http://img/1")
        self.assertEqual(mli.dataSource.type, "watchtogether")

    def test_creator_registered(self):
        self.assertIn("watchtogether", HomeWindow.CREATE_LI_MAP)


class InjectionTest(KodiTestCase):
    def win(self):
        return HomeWindow.__new__(HomeWindow)

    def test_no_hub_returns_original(self):
        class Sec(object):
            key = None
        hubs = home.HubsList([1, 2])
        hubs.identifier = "orig"
        self.assertIs(self.win()._with_watchtogether_hub(hubs, Sec()), hubs)

    def test_hub_is_prepended_and_metadata_preserved(self):
        import lib.windows.watchtogether as wt
        class Sec(object):
            key = None
        sentinel = object()
        saved = wt.bridge.home_hub
        wt.bridge.home_hub = lambda: sentinel
        try:
            hubs = home.HubsList([1, 2])
            hubs.identifier = "orig"
            hubs.lastUpdated = 123
            out = self.win()._with_watchtogether_hub(hubs, Sec())
        finally:
            wt.bridge.home_hub = saved
        self.assertEqual(out[0], sentinel)
        self.assertEqual(list(out[1:]), [1, 2])
        self.assertEqual(out.identifier, "orig")
        self.assertEqual(out.lastUpdated, 123)

    def test_non_home_section_returns_original(self):
        import lib.windows.watchtogether as wt
        class Sec(object):
            key = "1"
        saved = wt.bridge.home_hub
        wt.bridge.home_hub = lambda: object()
        try:
            hubs = home.HubsList([1])
            self.assertIs(self.win()._with_watchtogether_hub(hubs, Sec()), hubs)
        finally:
            wt.bridge.home_hub = saved


class HiddenBypassTest(KodiTestCase):
    def test_watchtogether_hub_is_never_hidden(self):
        win = HomeWindow.__new__(HomeWindow)
        win.isHubHidden = lambda identifier, key: True
        self.assertFalse(win._isHubHiddenFor(wtwin.WATCHTOGETHER_HUB_ID, None, False))

    def test_other_hubs_still_respect_the_hidden_setting(self):
        win = HomeWindow.__new__(HomeWindow)
        win.isHubHidden = lambda identifier, key: True
        class Sec(object):
            key = None
        self.assertTrue(win._isHubHiddenFor("movie.recentlyadded", Sec(), False))

    def test_cross_section_hubs_are_not_hidden_checked(self):
        win = HomeWindow.__new__(HomeWindow)
        win.isHubHidden = lambda identifier, key: (_ for _ in ()).throw(AssertionError("must not check"))
        self.assertFalse(win._isHubHiddenFor("movie.recentlyadded", None, True))


class ClickRouteTest(KodiTestCase):
    def test_wt_item_routes_to_room_clicked(self):
        import lib.windows.watchtogether as wt
        clicked = []
        saved = wt.bridge.room_clicked
        wt.bridge.room_clicked = clicked.append
        try:
            room = watchtogether.Room({"id": "r", "title": "t", "sourceUri": "",
                                       "users": []})
            item = wt.WatchTogetherRoomItem(room)

            class MLI(object):
                dataSource = item

            class Control(object):
                def getSelectedItem(self):
                    return MLI()

            win = HomeWindow.__new__(HomeWindow)
            win.hubControls = (Control(),)
            win.hubItemClicked(400)
        finally:
            wt.bridge.room_clicked = saved
        self.assertEqual(clicked, [item.room])


class IsWtItemTest(KodiTestCase):
    def test_true_for_room_item(self):
        win = HomeWindow.__new__(HomeWindow)
        room = watchtogether.Room({"id": "r", "title": "t", "sourceUri": "",
                                   "users": []})
        self.assertTrue(win._isWatchTogetherItem(wtwin.WatchTogetherRoomItem(room)))

    def test_false_for_other(self):
        win = HomeWindow.__new__(HomeWindow)
        self.assertFalse(win._isWatchTogetherItem(object()))


class PositionTrackingTest(KodiTestCase):
    def test_wt_item_ratingKey_does_not_break_positions(self):
        room = watchtogether.Room({"id": "r1", "title": "t", "sourceUri": "",
                                   "users": [{"id": 1, "title": "A"}]})
        item = wtwin.WatchTogetherRoomItem(room)
        self.assertEqual(item.ratingKey, "r1")
        self.assertIsNone(item.art)
        self.assertIsNone(item.thumb)

        hub = wtwin.WatchTogetherRoomsHub(lambda: [item])

        class Item(object):
            dataSource = item

        class HubControl(object):
            dataSource = hub

            def getSelectedPos(self):
                return 0

            def getItemByPos(self, pos):
                return Item()

        win = HomeWindow.__new__(HomeWindow)
        win.hubControls = (HubControl(),)
        positions = win.getCurrentHubsPositions(None)   # is_home
        self.assertEqual(positions.get(HUB_ID), ("r1", 0))


class RefreshTest(KodiTestCase):
    def win(self):
        win = HomeWindow.__new__(HomeWindow)
        win._wtRoomsVersion = None
        win._shown = []
        win.showHubs = lambda *a, **k: win._shown.append((a, k))
        win.getCurrentHubsPositions = lambda section: {"p": 1}
        return win

    def test_no_change_no_redraw(self):
        import lib.windows.watchtogether as wt
        saved = wt.bridge.rooms_version
        wt.bridge.rooms_version = 5
        try:
            win = self.win()
            win._wtRoomsVersion = 5
            self.assertFalse(win.checkWatchTogetherHub())
            self.assertEqual(win._shown, [])
        finally:
            wt.bridge.rooms_version = saved

    def test_change_redraws_home(self):
        import lib.windows.watchtogether as wt
        saved = wt.bridge.rooms_version
        wt.bridge.rooms_version = 6
        try:
            win = self.win()
            win._wtRoomsVersion = 5
            self.assertTrue(win.checkWatchTogetherHub())
            self.assertEqual(len(win._shown), 1)
        finally:
            wt.bridge.rooms_version = saved


class HubMenuTest(KodiTestCase):
    def setUp(self):
        super(HubMenuTest, self).setUp()
        self.room = watchtogether.Room({"id": "r", "title": "Room",
                                        "sourceUri": "", "users": []})
        self._saved_dropdown = home.dropdown.showDropdown
        self._saved_clicked = wtwin.bridge.room_clicked
        self._saved_remove = wtwin.bridge.remove_room
        self._saved_info = wtwin.show_room_info
        self._saved_confirm = HomeWindow._confirm_remove_room

    def tearDown(self):
        home.dropdown.showDropdown = self._saved_dropdown
        wtwin.bridge.room_clicked = self._saved_clicked
        wtwin.bridge.remove_room = self._saved_remove
        wtwin.show_room_info = self._saved_info
        HomeWindow._confirm_remove_room = self._saved_confirm
        super(HubMenuTest, self).tearDown()

    def run_menu(self, key, confirm=True):
        win = HomeWindow.__new__(HomeWindow)
        win.hubControls = ()
        home.dropdown.showDropdown = lambda *a, **k: ({"key": key} if key else None)
        HomeWindow._confirm_remove_room = lambda self, room: confirm
        win._watchtogether_hub_menu(self.room)

    def test_join_calls_room_clicked(self):
        calls = []
        wtwin.bridge.room_clicked = calls.append
        self.run_menu("wt_join")
        self.assertEqual(calls, [self.room])

    def test_remove_confirmed_removes(self):
        removed = []
        wtwin.bridge.remove_room = removed.append
        self.run_menu("wt_remove", confirm=True)
        self.assertEqual(removed, [self.room])

    def test_remove_declined_does_nothing(self):
        removed = []
        wtwin.bridge.remove_room = removed.append
        self.run_menu("wt_remove", confirm=False)
        self.assertEqual(removed, [])

    def test_info_opens_the_dialog(self):
        opened = []
        wtwin.show_room_info = opened.append
        self.run_menu("wt_info")
        self.assertEqual(opened, [self.room])

    def test_cancel_does_nothing(self):
        calls = []
        wtwin.bridge.room_clicked = calls.append
        self.run_menu(None)
        self.assertEqual(calls, [])


class _Server(object):
    def __init__(self, uuid):
        self.uuid = uuid


class _Count(object):
    def __init__(self, value):
        self._value = value

    def asInt(self, default=0):
        return self._value


class Movie(object):
    """Minimal PlexObject surface hubMenu reads for a movie/episode item."""

    def __init__(self, machine="m", rating_key="1", type_="movie"):
        self.server = _Server(machine) if machine is not None else None
        self.ratingKey = rating_key
        self.TYPE = type_
        self.title = "T"
        self.isFullyWatched = False
        self.isWatched = False
        self.viewedLeafCount = _Count(0)
        self.in_progress = False


class _Hub(object):
    def __init__(self):
        self.hubIdentifier = "movie.recentlyadded"
        self.title = "Movies"
        self.__dict__["_crossSectionSource"] = None
        self.__dict__["_displayTitle"] = None

    def getCleanHubIdentifier(self, is_home=False):
        return "movie.recentlyadded"


class _Section(object):
    key = None


class _MLI(object):
    def __init__(self, ds):
        self.dataSource = ds

    def getProperty(self, key):
        return None


class _Control(object):
    def __init__(self, mli, hub):
        self._mli = mli
        self.dataSource = hub

    def getSelectedItem(self):
        return self._mli


class EntryMenuTest(KodiTestCase):
    """The Start Watch Together / Invite entries (Review Focus 4: hidden when
    the item has no resolvable source)."""

    def setUp(self):
        super(EntryMenuTest, self).setUp()
        self.room = watchtogether.Room({"id": "r", "title": "Room",
                                        "sourceUri": "", "users": []})
        self._saved_dropdown = home.dropdown.showDropdown
        self._saved_host = wtwin.bridge.host
        self._saved_supervisor = wtwin.bridge.supervisor
        self._saved_room = wtwin.bridge.room
        self._saved_open = wtwin.InviteDialog.open
        self._saved_confirm = HomeWindow._confirm_start_watch_together
        # hubMenu reads cache_requests via util.getSetting; the harness has no
        # registered default, so give it a JSON list (it is a JSON setting) to
        # keep 'items' in <setting> from raising on None.
        ENV.settings["cache_requests"] = "[]"

    def tearDown(self):
        home.dropdown.showDropdown = self._saved_dropdown
        wtwin.bridge.host = self._saved_host
        wtwin.bridge.supervisor = self._saved_supervisor
        wtwin.bridge.room = self._saved_room
        wtwin.InviteDialog.open = self._saved_open
        HomeWindow._confirm_start_watch_together = self._saved_confirm
        super(EntryMenuTest, self).tearDown()

    def _capture(self, choice=None):
        captured = []

        def show(options, **kwargs):
            captured.extend(options)
            return {"key": choice} if choice else None

        home.dropdown.showDropdown = show
        return captured

    def menu_options(self, ds, choice=None):
        captured = self._capture(choice)
        win = HomeWindow.__new__(HomeWindow)
        win.hubControls = (_Control(_MLI(ds), _Hub()),)
        win.lastSection = _Section()
        win.hubSettings = None
        ENV.window_props[-1]["hub.focus"] = "0"   # currentHub reads this
        win.hubMenu(400)
        return [o for o in captured if o]

    def room_menu(self, choice=None):
        captured = self._capture(choice)
        win = HomeWindow.__new__(HomeWindow)
        win.hubControls = ()
        win._watchtogether_hub_menu(self.room)
        return [o for o in captured if o]

    def test_start_watch_together_shown_for_movie(self):
        opts = self.menu_options(ds=Movie(machine="m", rating_key="1"))
        assert any(o["key"] == "start_watch_together" for o in opts)

    def test_start_watch_together_hidden_without_source(self):
        opts = self.menu_options(ds=Movie(machine=None, rating_key=None))
        assert not any(o["key"] == "start_watch_together" for o in opts)

    def test_start_watch_together_hidden_without_server_uuid(self):
        # a server object without a uuid still yields an unresolvable sourceUri
        ds = Movie(machine="m", rating_key="1")
        ds.server = _Server(None)
        opts = self.menu_options(ds=ds)
        assert not any(o["key"] == "start_watch_together" for o in opts)

    def test_room_tile_menu_has_invite(self):
        wtwin.bridge.room = self.room
        opts = self.room_menu()
        assert any(o["key"] == "invite" for o in opts)

    def test_room_tile_menu_hides_invite_for_another_room(self):
        # invite is scoped to the current room; do not offer it on other tiles
        wtwin.bridge.room = watchtogether.Room({"id": "other", "title": "O",
                                                "sourceUri": "", "users": []})
        opts = self.room_menu()
        assert not any(o["key"] == "invite" for o in opts)

    def test_room_tile_menu_hides_invite_when_not_in_a_room(self):
        wtwin.bridge.room = None
        opts = self.room_menu()
        assert not any(o["key"] == "invite" for o in opts)

    def test_start_calls_host_when_not_in_a_room(self):
        hosted = []
        wtwin.bridge.host = hosted.append
        wtwin.bridge.supervisor = None
        HomeWindow._confirm_start_watch_together = lambda self: (_ for _ in ()).throw(
            AssertionError("must not confirm when not in a room"))
        ds = Movie()
        self.menu_options(ds=ds, choice="start_watch_together")
        self.assertEqual(hosted, [ds])

    def test_start_confirms_before_leaving_a_room(self):
        hosted = []
        wtwin.bridge.host = hosted.append
        wtwin.bridge.supervisor = object()      # already connected to a room
        ds = Movie()
        HomeWindow._confirm_start_watch_together = lambda self: False
        self.menu_options(ds=ds, choice="start_watch_together")
        self.assertEqual(hosted, [])
        HomeWindow._confirm_start_watch_together = lambda self: True
        self.menu_options(ds=ds, choice="start_watch_together")
        self.assertEqual(hosted, [ds])

    def test_invite_opens_the_dialog(self):
        wtwin.bridge.room = self.room
        opened = []
        wtwin.InviteDialog.open = lambda *a, **k: opened.append(k.get("room"))
        self.room_menu(choice="invite")
        self.assertEqual(opened, [self.room])
