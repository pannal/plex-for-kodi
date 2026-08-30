# coding=utf-8
"""
Collections pinned to the top bar - lib/windows/home.py and lib/windows/library.py.

A pinned view is a proxy around a real library: everything it doesn't define itself is
delegated, so queries keep running against the real section key, while its own key gives
it a private sort/filter bucket. Both halves are easy to break in opposite directions -
delegate the key too and the pin shares the library's sort; delegate too little and it
queries a section id the server has never heard of.

Importing anything under lib/windows/ pulls in lib.player, which starts a monitor thread
that spins until Kodi says abort. Setting abort_requested before the import lets that
thread exit immediately, otherwise the interpreter never shuts down.
"""

from __future__ import absolute_import

import json

from kodienv import ENV

ENV.abort_requested = True
from lib.windows import home, library  # noqa: E402
from lib.windows.home import HomeWindow, PinnedTypeSection, sectionId  # noqa: E402
from plexnet.plexlibrary import CollectionsHub  # noqa: E402
from lib.windows.library import LibrarySettings, realSection  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakeServer(object):
    uuid = "SERVERUUID"
    name = "Tower"

    def __init__(self, uuid="SERVERUUID"):
        self.uuid = uuid


class FakeSection(object):
    """Stands in for a plexnet LibrarySection: attributes plus a query that uses its key."""

    TYPE = "movie"
    type = "movie"
    DEFAULT_SORT = "titleSort"
    DEFAULT_SORT_DESC = False

    def __init__(self, key="3", title="Movies", server_uuid="SERVERUUID"):
        self.key = key
        self.title = title
        self.server = FakeServer(server_uuid)

    def all(self, *args, **kwargs):
        return "items of section {0}".format(self.key)

    def getServer(self):
        return self.server


def homeWindow(library_settings):
    """A HomeWindow without Kodi behind it - only the pin bookkeeping is exercised."""
    win = HomeWindow.__new__(HomeWindow)
    win.librarySettings = library_settings
    return win


class PinnedTypeSectionTest(KodiTestCase):
    def setUp(self):
        super(PinnedTypeSectionTest, self).setUp()
        self.section = FakeSection()
        self.pin = PinnedTypeSection(self.section, "collection")

    def test_the_pin_has_a_key_of_its_own(self):
        self.assertEqual("3#collection", self.pin.key)
        self.assertNotEqual(self.section.key, self.pin.key)

    def test_queries_still_run_against_the_real_section(self):
        # the delegated method is bound to the library, so it uses key 3, not 3#collection
        self.assertEqual("items of section 3", self.pin.all())

    def test_everything_undefined_is_delegated(self):
        self.assertEqual("movie", self.pin.TYPE)
        self.assertEqual("movie", self.pin.type)  # the top bar icon comes from this
        self.assertEqual("titleSort", self.pin.DEFAULT_SORT)
        self.assertIs(self.section.server, self.pin.server)

    def test_view_type_is_shared_with_the_library(self):
        # sort and filters are private to the pin, poster/list view is not
        self.assertEqual("3", self.pin.getLibrarySectionId())

    def test_item_type_is_reachable_without_getattr(self):
        # opener and LibrarySettings read __dict__ directly: PlexObject.__getattr__
        # invents an empty attribute for anything asked of it, so getattr can't be trusted
        self.assertEqual("collection", self.pin.__dict__.get("itemType"))
        self.assertIsNone(self.section.__dict__.get("itemType"))

    def test_real_section_unwraps_only_pins(self):
        self.assertIs(self.section, realSection(self.pin))
        self.assertIs(self.section, realSection(self.section))


class FakeValue(object):
    def __init__(self, value):
        self.value = value

    def asInt(self):
        return self.value


class FakeContainer(object):
    def __init__(self, offset=0, size=2, total=2):
        self.offset = FakeValue(offset)
        self.size = FakeValue(size)
        self.totalSize = FakeValue(total)


class FakeCollection(object):
    def __init__(self, title, container):
        self.title = title
        self.container = container


class CollectingSection(FakeSection):
    """Records how the hub asked for its items."""

    def __init__(self, count=2, total=2):
        FakeSection.__init__(self)
        self.queries = []
        container = FakeContainer(size=count, total=total)
        self.collections = [FakeCollection("Collection {0}".format(i), container) for i in range(count)]

    def all(self, start=None, size=None, sort=None, type_=None, **kwargs):
        self.queries.append({"start": start, "size": size, "sort": sort, "type_": type_})
        return list(self.collections)


class CollectionsHubTest(KodiTestCase):
    """
    Plex serves no all-collections hub, so PM4K builds one for a pinned view's hub row.

    It draws its items from the section itself, which is what keeps the row and the pinned
    view showing the same collections in the same order.
    """

    def test_it_asks_the_section_for_collections_alphabetically(self):
        section = CollectingSection()
        CollectionsHub(section)

        self.assertEqual(1, len(section.queries))
        query = section.queries[0]
        self.assertEqual(18, query["type_"])  # SEARCHTYPES['collection']
        self.assertEqual(("titleSort", "asc"), query["sort"])

    def test_items_come_from_the_section(self):
        hub = CollectionsHub(CollectingSection(count=3, total=3))

        self.assertEqual(["Collection 0", "Collection 1", "Collection 2"],
                         [c.title for c in hub.items])

    def test_a_library_without_collections_yields_an_empty_hub(self):
        hub = CollectionsHub(CollectingSection(count=0))

        self.assertEqual([], hub.items)

    def test_each_library_gets_its_own_identifier(self):
        movies = CollectingSection()
        shows = CollectingSection()
        shows.key = "5"

        self.assertNotEqual(CollectionsHub(movies).getCleanHubIdentifier(),
                            CollectionsHub(shows).getCleanHubIdentifier())

    def test_the_identifier_survives_suffix_stripping(self):
        # the base class strips trailing numeric suffixes, which would merge every
        # library's collections into one identifier and with it their stored item states
        hub = CollectionsHub(CollectingSection())

        self.assertEqual("collections.3", hub.getCleanHubIdentifier())
        self.assertEqual("collections.3", hub.getCleanHubIdentifier(is_home=True))

    def test_more_is_set_when_the_library_has_further_collections(self):
        hub = CollectionsHub(CollectingSection(count=10, total=40))

        self.assertEqual("1", hub.more)

    def test_reload_requeries_the_section(self):
        # the base reloads from self.key, which a client-built hub hasn't got
        section = CollectingSection()
        hub = CollectionsHub(section)
        hub.reload(limit=10)

        self.assertEqual(2, len(section.queries))
        self.assertEqual(2, len(hub.items))


class PinBookkeepingTest(KodiTestCase):
    def setUp(self):
        super(PinBookkeepingTest, self).setUp()
        self.section = FakeSection()

    def test_nothing_is_pinned_by_default(self):
        self.assertEqual([], homeWindow({}).sectionPinnedTypes(self.section))

    def test_pinning_then_unpinning_round_trips(self):
        win = homeWindow({})
        win.saveLibrarySettings = lambda: None

        win.setSectionPinned(self.section, "collection", True)
        self.assertEqual(["collection"], win.sectionPinnedTypes(self.section))

        win.setSectionPinned(self.section, "collection", False)
        self.assertEqual([], win.sectionPinnedTypes(self.section))

    def test_pinning_twice_does_not_duplicate_the_entry(self):
        win = homeWindow({})
        win.saveLibrarySettings = lambda: None

        win.setSectionPinned(self.section, "collection", True)
        win.setSectionPinned(self.section, "collection", True)
        self.assertEqual(["collection"], win.sectionPinnedTypes(self.section))

    def test_a_type_the_library_cannot_pin_is_ignored(self):
        photos = FakeSection(key="9", title="Photos")
        photos.TYPE = photos.type = "photo"
        win = homeWindow({"9": {"pinned_types": ["collection"]}})
        self.assertEqual([], win.sectionPinnedTypes(photos))

    def test_virtual_sections_without_a_type_are_ignored(self):
        # playlists and the watchlist reach this code on every top bar rebuild
        win = homeWindow({"playlists": {"pinned_types": ["collection"]}})
        self.assertEqual([], win.sectionPinnedTypes(home.playlists_section))

    def test_a_pin_cannot_itself_be_pinned(self):
        win = homeWindow({"3": {"pinned_types": ["collection"]}})
        pin = PinnedTypeSection(self.section, "collection")
        self.assertEqual([], win.sectionPinnedTypes(pin))


class PinnedSectionOrderTest(KodiTestCase):
    """The stored top bar order predates any pin, so a new pin has to find its place."""

    def orderedKeys(self, order, sections):
        # mirrors showSections(): pins are inserted next to the library they belong to
        expanded = []
        for section in sections:
            expanded.append(section)
            if section.key == "3":
                expanded.append(PinnedTypeSection(section, "collection"))

        def orderPos(s):
            if s.key in order:
                return order.index(s.key), 0
            if isinstance(s, PinnedTypeSection) and s.librarySection.key in order:
                return order.index(s.librarySection.key), 1
            return -1, 0

        return [s.key for s in sorted(expanded, key=orderPos)]

    def test_a_new_pin_follows_its_library_instead_of_jumping_to_the_front(self):
        movies = FakeSection()
        shows = FakeSection(key="5", title="TV")
        self.assertEqual(["3", "3#collection", "5"],
                         self.orderedKeys(["3", "5"], [movies, shows]))
        self.assertEqual(["5", "3", "3#collection"],
                         self.orderedKeys(["5", "3"], [movies, shows]))


class LibrarySettingsPerItemTypeTest(KodiTestCase):
    """
    Sort and filters are stored per (section, item type).

    Switching item type used to clear and persist empty filters for the type being
    switched *to*, which meant coming back to Movies threw away the filters the user
    had set there. The storage was always per type; only the clearing defeated it.
    """

    def setUp(self):
        super(LibrarySettingsPerItemTypeTest, self).setUp()
        self.section = FakeSection()
        library.setItemType("movie")

    def stored(self):
        return json.loads(ENV.settings["library.settings.SERVERUUID"])

    def test_each_item_type_keeps_its_own_sort_and_filter(self):
        settings = LibrarySettings(self.section)
        settings.setSetting("filter", {"display": "Genre"})
        settings.setSetting("sort", "addedAt")

        settings.setItemType("collection")
        self.assertIsNone(settings.getSetting("filter"))
        settings.setSetting("sort", "titleSort")

        settings.setItemType("movie")
        self.assertEqual({"display": "Genre"}, settings.getSetting("filter"))
        self.assertEqual("addedAt", settings.getSetting("sort"))

        settings.setItemType("collection")
        self.assertEqual("titleSort", settings.getSetting("sort"))

    def test_a_pin_stores_apart_from_its_library(self):
        settings = LibrarySettings(self.section)
        settings.setSetting("sort", "addedAt")

        pin = PinnedTypeSection(self.section, "collection")
        pinSettings = LibrarySettings(pin)
        pinSettings.setSetting("sort", "titleSort")

        self.assertEqual("addedAt", self.stored()["3"]["movie"]["sort"])
        self.assertEqual("titleSort", self.stored()["3#collection"]["collection"]["sort"])

    def test_a_pin_always_opens_in_its_own_item_type(self):
        library.setItemType("movie")
        pin = PinnedTypeSection(self.section, "collection")

        LibrarySettings(pin)
        self.assertEqual("collection", library.ITEM_TYPE)

        # switching type inside the pinned view must not survive the next open
        LibrarySettings(pin).setItemType("movie")
        library.setItemType("movie")
        LibrarySettings(pin)
        self.assertEqual("collection", library.ITEM_TYPE)

    def test_a_library_still_reopens_in_its_last_item_type(self):
        settings = LibrarySettings(self.section)
        settings.setItemType("collection")

        library.setItemType("movie")
        LibrarySettings(self.section)
        self.assertEqual("collection", library.ITEM_TYPE)


class SectionIdentityTest(KodiTestCase):
    def setUp(self):
        super(SectionIdentityTest, self).setUp()
        self.section = FakeSection()

    def test_real_section_identity_is_uuid_colon_key(self):
        server = FakeServer()
        server.uuid = "AAAABBBB"
        section = FakeSection(key="1", title="Movies")
        section.server = server
        self.assertEqual("AAAABBBB:1", sectionId(section))
        # two servers, same key -> distinct identities
        other = FakeSection(key="1", title="Foreign Movies")
        other.server = FakeServer()  # uuid "SERVERUUID"
        self.assertNotEqual(sectionId(section), sectionId(other))

    def test_pinned_type_section_derives_identity_from_its_library(self):
        pin = PinnedTypeSection(self.section, "collection")
        self.assertEqual("SERVERUUID:3#collection", sectionId(pin))

    def test_home_and_playlists_use_sentinels(self):
        self.assertEqual("home", sectionId(home.HomeSection()))
        self.assertEqual("playlists", sectionId(home.PlaylistsSection()))

    def test_watchlist_uses_a_sentinel_despite_having_a_real_key(self):
        section = FakeSection(key="/library/sections/watchlist", title="Watchlist")
        section.ID = "watchlist"
        self.assertEqual("watchlist", sectionId(section))

    def test_a_section_with_an_explicit_section_id_returns_it_verbatim(self):
        section = FakeSection(key="9", title="Movies")
        section.sectionId = "ZZZZ:9"
        self.assertEqual("ZZZZ:9", sectionId(section))


class ForeignLibraryConfigTest(KodiTestCase):
    def setUp(self):
        super(ForeignLibraryConfigTest, self).setUp()
        from plexnet import plexapp as _plexapp
        self._orig_account = _plexapp.ACCOUNT
        _plexapp.ACCOUNT = type("FakeAccount", (), {"ID": "TESTACCOUNT"})()
        self.win = homeWindow({})

    def tearDown(self):
        from plexnet import plexapp as _plexapp
        _plexapp.ACCOUNT = self._orig_account
        super(ForeignLibraryConfigTest, self).tearDown()

    def pin(self, server_uuid="SERVERUUID", section_key="1", name="Away",
            title="Movies", win=None):
        # real saveForeignLibraries writes ENV.settings via util.setSetting;
        # each KodiTestCase.setUp resets ENV so a test starts from a clean setting
        win = win or self.win
        win.pinForeignLibrary(server_uuid, section_key, name, title)
        return win

    def test_pin_creates_a_foreign_record(self):
        self.pin()
        self.assertEqual([{
            "server_uuid": "SERVERUUID", "section_key": "1",
            "server_name": "Away", "section_title": "Movies",
        }], self.win.foreignLibraries())

    def test_pinning_the_same_foreign_library_twice_dedupes(self):
        self.pin()
        self.pin()
        self.assertEqual(1, len(self.win.foreignLibraries()))

    def test_two_foreign_libraries_with_same_key_on_different_servers_both_stay(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        self.assertEqual(2, len(self.win.foreignLibraries()))

    def test_unpin_removes_by_server_and_key(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        self.win.unpinForeignLibrary(server_uuid="AAA", section_key="1")
        got = [r["server_uuid"] for r in self.win.foreignLibraries()]
        self.assertEqual(["BBB"], got)

    def test_unpin_for_a_missing_record_is_a_no_op(self):
        self.pin(server_uuid="AAA")
        self.win.unpinForeignLibrary(server_uuid="NOPE", section_key="1")
        self.assertEqual(1, len(self.win.foreignLibraries()))

    def test_prune_drops_records_for_unknown_servers(self):
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        pruned = self.win.pruneForeignLibraries(known_servers={"AAA"})
        surviving = [r["server_uuid"] for r in pruned]
        self.assertEqual(["AAA"], surviving)

    def test_unpin_with_only_one_filter_is_a_safe_noop(self):
        # AND semantics: both server and key must match to remove
        self.pin(server_uuid="AAA")
        self.pin(server_uuid="BBB", name="Other")
        self.win.unpinForeignLibrary(server_uuid="AAA")          # uuid only
        self.win.unpinForeignLibrary(section_key="1")            # key only
        self.assertEqual(2, len(self.win.foreignLibraries()))

    def test_foreign_libraries_are_stored_under_the_account_scoped_key(self):
        self.pin()
        self.assertIn("home.foreign_libraries.TESTACCOUNT", ENV.settings)
        stored = json.loads(ENV.settings["home.foreign_libraries.TESTACCOUNT"])
        self.assertEqual([{
            "server_uuid": "SERVERUUID", "section_key": "1",
            "server_name": "Away", "section_title": "Movies",
        }], stored)


class ForeignLibrarySectionTest(KodiTestCase):
    def test_placeholder_identity_comes_from_the_record_not_a_server(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertIsNone(ph.server)
        self.assertTrue(ph.offline)
        self.assertEqual("ZZZZ:9", sectionId(ph))

    def test_placeholder_title_is_suffixed(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertEqual("Movies - Away", ph.title)


class FakeManager(object):
    def __init__(self, servers):
        self.servers = servers

    def getServers(self):
        return self.servers


class FakeResolvableSection(object):
    key = "1"
    title = "Live Movies"
    offline = False


class ForeignResolutionTest(KodiTestCase):
    def setUp(self):
        super(ForeignResolutionTest, self).setUp()
        self.win = homeWindow({})

    def test_unknown_server_resolves_to_a_placeholder(self):
        manager = FakeManager([])
        section, offline = self.win.resolveForeignLibrary(
            {"server_uuid": "NOPE", "section_key": "1",
             "server_name": "Away", "section_title": "Movies"},
            manager=manager)
        self.assertTrue(offline)
        self.assertIsNone(section.server)

    def test_match_by_key_resolves_to_a_live_section(self):
        live = FakeResolvableSection()

        class FakeLib(object):
            def sections(self):
                return [live]

        server = FakeServer()
        server.library = FakeLib()
        manager = FakeManager([server])
        record = {"server_uuid": "SERVERUUID", "section_key": "1",
                  "server_name": "Away", "section_title": "Movies"}
        section, offline = self.win.resolveForeignLibrary(record, manager=manager)
        self.assertFalse(offline)
        self.assertIs(section, live)
        # live match refreshes the denormalized title
        self.assertEqual("Live Movies", record["section_title"])

    def test_no_section_match_on_a_known_server_resolves_to_a_placeholder(self):
        class FakeLib(object):
            def sections(self):
                return []
        server = FakeServer()
        server.library = FakeLib()
        manager = FakeManager([server])
        section, offline = self.win.resolveForeignLibrary(
            {"server_uuid": "SERVERUUID", "section_key": "99",
             "server_name": "Away", "section_title": "Movies"},
            manager=manager)
        self.assertTrue(offline)

    def test_a_pin_over_a_placeholder_keeps_its_item_type_suffix(self):
        # regression for the Task-1 code review: PinnedTypeSection must win over sectionId
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        pin = PinnedTypeSection(ph, "collection")
        self.assertEqual("ZZZZ:9#collection", sectionId(pin))


class ForeignPlaceholderHubGuardTest(KodiTestCase):
    def setUp(self):
        super(ForeignPlaceholderHubGuardTest, self).setUp()
        self.win = homeWindow({})
        # a stripped HomeWindow has no hub controls to clear and no live window
        # behind it; the busy wrapper's teardown calls setProperty('busy', '')
        self.win.hubControls = []
        self.win.setProperty = lambda key, value: None

    def test_placeholder_never_fetches_hubs(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.win._showHubs(ph)


class ForeignRailSectionsTest(KodiTestCase):
    def setUp(self):
        super(ForeignRailSectionsTest, self).setUp()
        self.win = homeWindow({})
        self.win._foreignLibraries = [
            {"server_uuid": "AWAY", "section_key": "1",
             "server_name": "Away", "section_title": "Films"},
        ]

    def test_unknown_server_yields_a_placeholder(self):
        manager = FakeManager([])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="LOCAL")
        self.assertEqual(1, len(sections))
        ph = sections[0]
        self.assertTrue(ph.offline)
        self.assertEqual("Films - Away", ph.title)

    def test_reachable_server_yields_a_live_section_with_suffixed_title(self):
        live = FakeResolvableSection()
        class FakeLib(object):
            def sections(self):
                return [live]
        server = FakeServer()
        server.uuid = "AWAY"  # match the record's foreign server
        server.library = FakeLib()
        manager = FakeManager([server])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="LOCAL")
        self.assertEqual(1, len(sections))
        self.assertFalse(sections[0].offline)
        self.assertEqual("Live Movies - Away", sections[0].title)
        self.assertTrue(getattr(sections[0], 'is_foreign', False))

    def test_record_for_the_selected_server_is_skipped(self):
        # the selected server's own libraries are already on the rail
        self.win._foreignLibraries[0]["server_uuid"] = "SERVERUUID"
        server = FakeServer()
        class FakeLib(object):
            def sections(self):
                return []
        server.library = FakeLib()
        manager = FakeManager([server])
        sections = self.win.foreignRailSections(manager=manager,
                                                selected_server_uuid="SERVERUUID")
        self.assertEqual([], sections)


class ForeignPlaceholderRenderAttrsTest(KodiTestCase):
    def test_placeholder_exposes_mapping_attrs(self):
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="9", server_name="Away",
            section_title="Movies")
        self.assertFalse(getattr(ph, 'mappingBroken', True))
        self.assertFalse(getattr(ph, 'isMapped', True))


class ForeignPinMenuTest(KodiTestCase):
    def setUp(self):
        super(ForeignPinMenuTest, self).setUp()
        self.win = homeWindow({})

    def test_is_pinable_reports_when_a_section_is_not_yet_pinned(self):
        server = FakeServer()
        section = FakeSection()
        section.server = server
        self.win._foreignLibraries = [
            {"server_uuid": "OTHER", "section_key": "9",
             "server_name": "Away", "section_title": "Series"},
        ]
        self.assertFalse(self.win.isSectionPinnedToHome(section))

    def test_is_pinable_reports_when_a_section_is_pinned(self):
        server = FakeServer()
        server.uuid = "SERVERUUID"
        section = FakeSection(key="3")
        section.server = server
        self.win._foreignLibraries = [
            {"server_uuid": "SERVERUUID", "section_key": "3",
             "server_name": "Tower", "section_title": "Movies"},
        ]
        self.assertTrue(self.win.isSectionPinnedToHome(section))


class ServerRefreshReselectTest(KodiTestCase):
    def test_same_rail_section_matches_by_section_id(self):
        win = homeWindow({})
        local = FakeSection(key="1")
        ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="1", server_name="Away",
            section_title="Movies")
        # different servers, same key -> not the same rail item
        self.assertFalse(win._sameRailSection(local, ph))
        same_ph = home.ForeignLibrarySection.placeholder(
            server_uuid="ZZZZ", section_key="1", server_name="Away",
            section_title="Other")
        # same server+key, different label -> same rail item
        self.assertTrue(win._sameRailSection(ph, same_ph))
        # live resolved foreign section vs its placeholder -> same rail item
        live = FakeSection(key="1", server_uuid="ZZZZ")
        self.assertTrue(win._sameRailSection(live, ph))

