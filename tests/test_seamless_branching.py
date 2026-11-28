# coding=utf-8
"""
lib/seamless_branching.py - deciding when to engage the LAV workaround.

The consequence of a false negative is audio dropping out mid-film on a
seamless-branching disc rip; a false positive engages LAV where it isn't
needed. Both the curated-list path and the per-folder SB marker path are
covered.
"""

from __future__ import absolute_import

import os

from lib import util
from lib.seamless_branching import SeamlessBranchingManager

from .base import KodiTestCase
from . import REPO_ROOT


class FakeBitrate(object):
    def __init__(self, value):
        self.value = value

    def asInt(self):
        return int(self.value)

    def __bool__(self):
        return bool(self.value)

    __nonzero__ = __bool__


class FakeStream(object):
    def __init__(self, codec, bitrate=None):
        self.codec = codec
        if bitrate is not None:
            self.bitrate = FakeBitrate(bitrate)


class FakeGuid(object):
    def __init__(self, id):
        self.id = id


class FakeVideo(object):
    def __init__(self, guid, guids=()):
        self.guid = guid
        self.guids = list(guids)


class FakeMetadata(object):
    def __init__(self, isMapped=True, streamUrls=()):
        self.isMapped = isMapped
        self.streamUrls = list(streamUrls)


class FakePlayerObject(object):
    def __init__(self, metadata=None):
        if metadata is not None:
            self.metadata = metadata


def manager():
    """A bare manager - no bundled/user file loading, so tests set the list."""
    mgr = SeamlessBranchingManager.__new__(SeamlessBranchingManager)
    mgr.seamless_branching_movies = set()
    return mgr


class BundledDataTest(KodiTestCase):
    def test_the_shipped_movie_list_loads_and_is_not_empty(self):
        mgr = SeamlessBranchingManager()
        self.assertTrue(mgr.seamless_branching_movies,
                        "resources/seamless_branching.json produced no IMDB IDs")

    def test_every_shipped_id_looks_like_an_imdb_id(self):
        mgr = SeamlessBranchingManager()
        bad = sorted(i for i in mgr.seamless_branching_movies
                     if not (i.startswith("tt") and i[2:].isdigit()))
        self.assertEqual([], bad)

    def test_the_shipped_file_is_where_the_manager_looks_for_it(self):
        path = os.path.join(REPO_ROOT, "resources",
                            SeamlessBranchingManager.BUNDLED_DATA_FILE)
        self.assertTrue(os.path.exists(path), path)

    def test_a_user_file_is_merged_on_top_of_the_bundled_one(self):
        user_file = os.path.join(util.translatePath(util.ADDON.getAddonInfo("profile")),
                                 SeamlessBranchingManager.USER_DATA_FILE)
        with open(user_file, "w", encoding="utf-8") as fp:
            fp.write('{"movies": [{"imdb_id": "tt9999999"}]}')
        try:
            mgr = SeamlessBranchingManager()
            self.assertIn("tt9999999", mgr.seamless_branching_movies)
            self.assertGreater(len(mgr.seamless_branching_movies), 1)
        finally:
            os.remove(user_file)

    def test_a_corrupt_user_file_does_not_lose_the_bundled_list(self):
        user_file = os.path.join(util.translatePath(util.ADDON.getAddonInfo("profile")),
                                 SeamlessBranchingManager.USER_DATA_FILE)
        with open(user_file, "w", encoding="utf-8") as fp:
            fp.write("{not json")
        try:
            mgr = SeamlessBranchingManager()
            self.assertTrue(mgr.seamless_branching_movies)
        finally:
            os.remove(user_file)


class ImdbIdTest(KodiTestCase):
    def test_legacy_imdb_agent_guid(self):
        video = FakeVideo("com.plexapp.agents.imdb://tt0468569?lang=en")
        self.assertEqual("tt0468569", manager().get_imdb_id(video))

    def test_legacy_guid_without_a_language_suffix(self):
        video = FakeVideo("com.plexapp.agents.imdb://tt0468569")
        self.assertEqual("tt0468569", manager().get_imdb_id(video))

    def test_new_plex_agent_reads_the_guids_array(self):
        video = FakeVideo("plex://movie/5d776831961905001eb90a12",
                          guids=[FakeGuid("tmdb://155"), FakeGuid("imdb://tt0468569")])
        self.assertEqual("tt0468569", manager().get_imdb_id(video))

    def test_new_plex_agent_without_an_imdb_guid(self):
        video = FakeVideo("plex://movie/x", guids=[FakeGuid("tmdb://155")])
        self.assertIsNone(manager().get_imdb_id(video))

    def test_an_unrecognised_agent_yields_nothing(self):
        self.assertIsNone(manager().get_imdb_id(FakeVideo("com.plexapp.agents.thetvdb://1")))


class AudioDetectionTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = manager()

    def test_truehd_always_counts(self):
        self.assertTrue(self.mgr._is_truehd_or_tms(FakeStream("truehd")))
        self.assertTrue(self.mgr._is_truehd_or_tms(FakeStream("TrueHD")))

    def test_high_bitrate_eac3_counts_as_tms(self):
        self.assertTrue(self.mgr._is_truehd_or_tms(FakeStream("eac3", bitrate=768)))

    def test_the_threshold_is_inclusive(self):
        threshold = SeamlessBranchingManager.TMS_EAC3_MIN_BITRATE
        self.assertTrue(self.mgr._is_truehd_or_tms(FakeStream("eac3", bitrate=threshold)))
        self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream("eac3", bitrate=threshold - 1)))

    def test_ordinary_eac3_does_not_count(self):
        self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream("eac3", bitrate=640)))

    def test_eac3_without_a_bitrate_does_not_count(self):
        self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream("eac3")))

    def test_other_codecs_never_count(self):
        for codec in ("ac3", "dca", "flac", "aac", "dts"):
            with self.subTest(codec=codec):
                self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream(codec, bitrate=3000)))

    def test_missing_stream_or_codec(self):
        self.assertFalse(self.mgr._is_truehd_or_tms(None))
        self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream("")))
        self.assertFalse(self.mgr._is_truehd_or_tms(FakeStream(None)))


class DetectionTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = manager()
        self.mgr.seamless_branching_movies = {"tt0468569"}
        self.truehd = FakeStream("truehd")

    def test_needs_both_a_listed_movie_and_affected_audio(self):
        self.assertTrue(self.mgr.is_seamless_branching_movie("tt0468569", self.truehd,
                                                             force_detection=True))

    def test_an_unlisted_movie_is_never_engaged(self):
        self.assertFalse(self.mgr.is_seamless_branching_movie("tt0000001", self.truehd,
                                                              force_detection=True))

    def test_a_listed_movie_with_unaffected_audio_is_not_engaged(self):
        self.assertFalse(self.mgr.is_seamless_branching_movie(
            "tt0468569", FakeStream("ac3"), force_detection=True))

    def test_no_imdb_id_at_all(self):
        self.assertFalse(self.mgr.is_seamless_branching_movie(None, self.truehd,
                                                              force_detection=True))

    def test_without_platform_support_detection_is_skipped(self):
        """
        util.CE_SB_LAV_SWITCH is what says "this build can flip LAV at all".
        Without it, detection short-circuits unless forced.
        """
        orig = util.CE_SB_LAV_SWITCH
        try:
            util.CE_SB_LAV_SWITCH = False
            self.assertFalse(self.mgr.is_seamless_branching_movie("tt0468569", self.truehd))
            util.CE_SB_LAV_SWITCH = True
            self.assertTrue(self.mgr.is_seamless_branching_movie("tt0468569", self.truehd))
        finally:
            util.CE_SB_LAV_SWITCH = orig

    def test_needs_lav_switch_only_for_the_non_lav_modes(self):
        mgr = self.mgr
        self.assertFalse(mgr.needs_lav_switch(mgr.LAV_MODE_LAV_FULL))
        self.assertFalse(mgr.needs_lav_switch(mgr.LAV_MODE_LAV_SB))
        for mode in (mgr.LAV_MODE_OFF, mgr.LAV_MODE_SEEK_SYNC, mgr.LAV_MODE_DEBUG):
            with self.subTest(mode=mode):
                self.assertTrue(mgr.needs_lav_switch(mode))


class SBMarkerTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = manager()
        self.folder = self.mktemp()
        self.movie = os.path.join(self.folder, "Movie (2008).mkv")
        with open(self.movie, "w", encoding="utf-8") as fp:
            fp.write("x")

    def write_marker(self, content, name="SB"):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(content)
        return path

    def player(self, isMapped=True, url=None):
        return FakePlayerObject(FakeMetadata(isMapped=isMapped,
                                            streamUrls=[url or self.movie]))

    def test_no_marker_means_no_engage(self):
        self.assertFalse(self.mgr.has_sb_marker(self.player()))

    def test_an_empty_marker_engages_the_whole_folder(self):
        self.write_marker("")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_a_whitespace_only_marker_engages_the_whole_folder(self):
        self.write_marker("  \n\n\t\n")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_a_comments_only_marker_engages_the_whole_folder(self):
        self.write_marker("# nothing here\n; nor here\n")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_an_exact_filename_entry_matches(self):
        self.write_marker("Movie (2008).mkv\n")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_a_glob_entry_matches(self):
        self.write_marker("Movie*.mkv\n")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_a_non_matching_entry_does_not_engage(self):
        self.write_marker("Other.mkv\n")
        self.assertFalse(self.mgr.has_sb_marker(self.player()))

    def test_matching_is_case_sensitive(self):
        """fnmatchcase, so a lowercase entry must not match a capitalised file."""
        self.write_marker("movie (2008).mkv\n")
        self.assertFalse(self.mgr.has_sb_marker(self.player()))

    def test_comments_and_blanks_are_ignored_between_entries(self):
        self.write_marker("# the imax cut\n\nOther.mkv\nMovie*.mkv\n; done\n")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_the_alternate_marker_filename_works(self):
        self.write_marker("Movie*.mkv\n", name="SB.txt")
        self.assertTrue(self.mgr.has_sb_marker(self.player()))

    def test_an_unmapped_part_is_never_checked(self):
        self.write_marker("")
        self.assertFalse(self.mgr.has_sb_marker(self.player(isMapped=False)))

    def test_a_player_without_metadata(self):
        self.assertFalse(self.mgr.has_sb_marker(FakePlayerObject()))
        self.assertFalse(self.mgr.has_sb_marker(FakePlayerObject(None)))

    def test_a_player_without_stream_urls(self):
        self.write_marker("")
        obj = FakePlayerObject(FakeMetadata(isMapped=True, streamUrls=[]))
        self.assertFalse(self.mgr.has_sb_marker(obj))

    def test_an_empty_stream_url(self):
        self.write_marker("")
        obj = FakePlayerObject(FakeMetadata(isMapped=True, streamUrls=[""]))
        self.assertFalse(self.mgr.has_sb_marker(obj))

    def test_read_marker_patterns_strips_and_filters(self):
        path = self.write_marker("  a.mkv  \n# c\n\n;d\nb*.mkv\n")
        self.assertEqual(["a.mkv", "b*.mkv"], self.mgr._read_marker_patterns(path))

    def test_read_marker_patterns_of_an_empty_file_is_none(self):
        self.assertIsNone(self.mgr._read_marker_patterns(self.write_marker("")))

    def test_read_marker_patterns_of_a_missing_file_is_none(self):
        self.assertIsNone(self.mgr._read_marker_patterns(
            os.path.join(self.folder, "absent")))
