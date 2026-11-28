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
from lib.windows.home import HomeWindow, PinnedTypeSection  # noqa: E402
from plexnet.plexlibrary import CollectionsHub  # noqa: E402
from lib.windows.library import LibrarySettings, realSection  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakeServer(object):
    uuid = "SERVERUUID"
    name = "Tower"


class FakeSection(object):
    """Stands in for a plexnet LibrarySection: attributes plus a query that uses its key."""

    TYPE = "movie"
    type = "movie"
    DEFAULT_SORT = "titleSort"
    DEFAULT_SORT_DESC = False

    def __init__(self, key="3", title="Movies"):
        self.key = key
        self.title = title
        self.server = FakeServer()

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
