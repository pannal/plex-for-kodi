# coding=utf-8
"""
Hub display for Home and library sections - lib/windows/home.py.

Plex tells same-type sections' hubs apart only by numeric suffixes on the
hubIdentifier ("home.movies.recent.3.1" vs "home.movies.recent.7.1"), and
getCleanHubIdentifier strips exactly those suffixes to build catalog ids. Two
consequences worth pinning down:

- getCombinedHubsForSection must not dedup on the collapsed catalog id, or the
  second movie-type library's "Recently Added" row silently disappears (the
  "Other Videos" bug).
- A hub rendered outside its source section must always name its source. A
  substring test is not enough to skip the suffix: a library named "Movies"
  also matches "Recently Released Movies", leaving foreign hubs unattributed.

Importing anything under lib/windows/ pulls in lib.player, which starts a
monitor thread that spins until Kodi says abort. Setting abort_requested before
the import lets that thread exit immediately.
"""

from __future__ import absolute_import

from kodienv import ENV

ENV.abort_requested = True
from lib.windows.home import HomeWindow, HubsList  # noqa: E402
from plexnet import plexlibrary  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakeHub(object):
    """A hub with the real identifier cleaning, without a PlexObject behind it."""

    # borrow the actual implementation so the suffix stripping under test is the
    # shipped one, not a re-implementation
    getCleanHubIdentifier = plexlibrary.BaseHub.getCleanHubIdentifier

    def __init__(self, hubIdentifier, title):
        self.hubIdentifier = hubIdentifier
        self.title = title
        self._identifier = None


class FakeSection(object):
    def __init__(self, key, title):
        self.key = key
        self.title = title


HOME = FakeSection(None, "Home")


def homeWindow(section_hubs=None, hub_settings=None, all_sections=None):
    """A HomeWindow without Kodi behind it - only hub bookkeeping is exercised."""
    win = HomeWindow.__new__(HomeWindow)
    win.sectionHubs = section_hubs or {}
    win.hubSettings = hub_settings or {}
    win.allSections = all_sections or {}
    return win


class CombinedHubsDedupTest(KodiTestCase):
    """Two same-type libraries' home hubs share a catalog id but are distinct hubs."""

    def setUp(self):
        super(CombinedHubsDedupTest, self).setUp()
        self.movies_hub = FakeHub("home.movies.recent.3.1", "Recently Added in Movies")
        self.other_hub = FakeHub("home.movies.recent.7.1", "Recently Added in Other Videos")
        native = HubsList([self.movies_hub, self.other_hub]).init()
        self.win = homeWindow(
            section_hubs={None: native},
            hub_settings={None: {"custom": True, "hubs": [
                {"catalog_id": "home.movies.recent", "order": 0},
            ]}},
        )

    def test_both_libraries_keep_their_row(self):
        combined = self.win.getCombinedHubsForSection(HOME)
        self.assertEqual(
            ["Recently Added in Movies", "Recently Added in Other Videos"],
            [h.title for h in combined],
        )

    def test_the_shared_catalog_id_enables_both_rows(self):
        combined = self.win.getCombinedHubsForSection(HOME)
        self.assertEqual(["home.movies.recent"] * 2,
                         [h._catalogId for h in combined])

    def test_a_disabled_catalog_id_still_hides_its_rows(self):
        self.win.hubSettings[None]["hubs"] = [{"catalog_id": "home.continue", "order": 0}]
        combined = self.win.getCombinedHubsForSection(HOME)
        self.assertEqual([], list(combined))

    def test_the_same_hub_listed_twice_is_still_deduped(self):
        self.win.sectionHubs[None].append(self.movies_hub)
        combined = self.win.getCombinedHubsForSection(HOME)
        self.assertEqual(2, len(combined))


class CrossSectionAttributionTest(KodiTestCase):
    """attributeCrossSectionHub appends the source library to foreign hubs."""

    def setUp(self):
        super(CrossSectionAttributionTest, self).setUp()
        self.movies = FakeSection("3", "Movies")
        self.other = FakeSection("7", "Other Videos")
        self.win = homeWindow(all_sections={"3": self.movies, "7": self.other})

    @staticmethod
    def crossHub(title, source_key, identifier="movie.recentlyreleased.3.1"):
        hub = FakeHub(identifier, title)
        hub._crossSectionSource = source_key
        return hub

    def displayTitle(self, hub, section, is_home=False):
        self.win.attributeCrossSectionHub(hub, section, is_home)
        return hub.__dict__.get("_displayTitle")

    def test_foreign_hub_is_attributed_even_if_the_library_name_is_a_substring(self):
        # the "Recently Released Movies" inside "Other Videos" bug
        hub = self.crossHub("Recently Released Movies", "3")
        self.assertEqual("Recently Released Movies — Movies",
                         self.displayTitle(hub, self.other))

    def test_foreign_hub_with_an_unrelated_name_is_attributed(self):
        hub = self.crossHub("Top Rated", "3")
        self.assertEqual("Top Rated — Movies", self.displayTitle(hub, self.other))

    def test_a_hub_in_its_own_section_stays_bare(self):
        hub = self.crossHub("Recently Released Movies", "3")
        self.assertIsNone(self.displayTitle(hub, self.movies))

    def test_a_title_identical_to_the_library_name_stays_bare(self):
        hub = self.crossHub("Movies", "3")
        self.assertIsNone(self.displayTitle(hub, self.other))

    def test_home_sourced_hub_in_a_library_is_attributed_to_home(self):
        hub = self.crossHub("Continue Watching", None, identifier="home.continue")
        self.assertEqual("Continue Watching — Home",
                         self.displayTitle(hub, self.movies))

    def test_home_sourced_hub_on_home_stays_bare(self):
        hub = self.crossHub("Continue Watching", None, identifier="home.continue")
        self.assertIsNone(self.displayTitle(hub, HOME, is_home=True))

    def test_native_hub_without_cross_section_marker_stays_bare(self):
        hub = FakeHub("home.movies.recent.3.1", "Recently Added in Movies")
        self.assertIsNone(self.displayTitle(hub, HOME, is_home=True))
