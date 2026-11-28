# coding=utf-8
"""
plexnet.playqueue and plexnet.videosession helpers.

AudioUsage is the skip limiter Plex mixes impose (a rolling hour window), and
PlayQueueFactory.getContentType is what decides whether a click starts the
video, music or photo player at all.
"""

from __future__ import absolute_import

from plexnet import playqueue, util as pnUtil, videosession
from plexnet.playqueue import AudioUsage, PlayOptions, PlayQueueFactory

from .base import KodiTestCase, ensure_plex_interface


class FakeItem(object):
    def __init__(self, type):
        self.type = type

    def isMusicOrDirectoryItem(self):
        return self.type in ("artist", "album", "track")

    def isVideoOrDirectoryItem(self):
        return self.type in ("movie", "show", "episode")

    def isPhotoOrDirectoryItem(self):
        return self.type == "photoalbum"


class AudioUsageTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        self._orig_now = pnUtil.now
        self.clock = {"t": 1_000_000}
        pnUtil.now = lambda: self.clock["t"]

    def tearDown(self):
        pnUtil.now = self._orig_now
        KodiTestCase.tearDown(self)

    def test_a_negative_limit_means_unlimited(self):
        usage = AudioUsage(-1, "pq1")
        for _ in range(50):
            usage.registerSkip()
        self.assertTrue(usage.allowSkip())
        self.assertIsNone(usage.allowSkipMessage())

    def test_skips_are_allowed_up_to_the_limit(self):
        usage = AudioUsage(3, "pq1")
        for expected in range(3):
            with self.subTest(skips=expected):
                self.assertTrue(usage.allowSkip())
                usage.registerSkip()
        self.assertFalse(usage.allowSkip())

    def test_exceeding_the_limit_produces_a_message(self):
        usage = AudioUsage(2, "pq1")
        usage.registerSkip()
        usage.registerSkip()
        message = usage.allowSkipMessage()
        self.assertIsNotNone(message)
        self.assertIn("2", message)

    def test_the_window_is_a_rolling_hour(self):
        usage = AudioUsage(2, "pq1")
        usage.registerSkip()
        usage.registerSkip()
        self.assertFalse(usage.allowSkip())

        # an hour and a second later the old skips have aged out
        self.clock["t"] += usage.HOUR + 1
        self.assertTrue(usage.allowSkip())
        self.assertEqual([], usage.skips)

    def test_a_partially_expired_window_only_drops_the_old_skips(self):
        usage = AudioUsage(3, "pq1")
        usage.registerSkip()
        self.clock["t"] += usage.HOUR - 10
        usage.registerSkip()
        usage.registerSkip()
        self.assertFalse(usage.allowSkip())

        # 20 more seconds: the first skip is now over an hour old, the others are not
        self.clock["t"] += 20
        self.assertTrue(usage.allowSkip())
        self.assertEqual(2, len(usage.skips))

    def test_reset_clears_the_history(self):
        usage = AudioUsage(1, "pq1")
        usage.registerSkip()
        usage.updateSkips(reset=True)
        self.assertEqual([], usage.skips)
        self.assertTrue(usage.allowSkip())

    def test_a_zero_limit_allows_nothing(self):
        self.assertFalse(AudioUsage(0, "pq1").allowSkip())

    def test_the_usage_remembers_its_queue(self):
        self.assertEqual("pq1", AudioUsage(3, "pq1").playQueueId)


class PlayOptionsTest(KodiTestCase):
    def test_context_defaults_to_auto(self):
        options = PlayOptions()
        self.assertEqual(options.CONTEXT_AUTO, options.context)

    def test_the_context_constants_are_distinct(self):
        options = PlayOptions()
        constants = (options.CONTEXT_AUTO, options.CONTEXT_SELF,
                     options.CONTEXT_PARENT, options.CONTEXT_CONTAINER)
        self.assertEqual(len(constants), len(set(constants)))

    def test_it_behaves_as_an_attribute_dict(self):
        options = PlayOptions({"key": "/library/metadata/1", "shuffle": True})
        self.assertEqual("/library/metadata/1", options.key)
        self.assertTrue(options.shuffle)

    def test_attributes_can_be_assigned(self):
        options = PlayOptions()
        options.unwatched = True
        self.assertTrue(options.unwatched)
        self.assertTrue(options["unwatched"])


class ContentTypeTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.factory = PlayQueueFactory()

    def test_music_items(self):
        for libtype in ("artist", "album", "track"):
            with self.subTest(type=libtype):
                self.assertEqual("audio", self.factory.getContentType(FakeItem(libtype)))

    def test_video_items(self):
        for libtype in ("movie", "show", "episode"):
            with self.subTest(type=libtype):
                self.assertEqual("video", self.factory.getContentType(FakeItem(libtype)))

    def test_photo_albums(self):
        self.assertEqual("photo", self.factory.getContentType(FakeItem("photoalbum")))

    def test_an_unplayable_type_has_no_content_type(self):
        self.assertIsNone(self.factory.getContentType(FakeItem("collection")))

    def test_an_artist_requires_a_remote_play_queue(self):
        """Artist radio is generated server-side, so it cannot be a local PQ."""
        factory = PlayQueueFactory()
        factory.item = FakeItem("artist")
        self.assertTrue(factory.itemRequiresRemotePlayQueue())

        factory.item = FakeItem("movie")
        self.assertFalse(factory.itemRequiresRemotePlayQueue())


class NormResTest(KodiTestCase):
    def test_a_bare_number_gets_a_p_suffix(self):
        self.assertEqual("1080p", videosession.normRes("1080"))
        self.assertEqual("720p", videosession.normRes("720"))

    def test_an_already_named_resolution_is_left_alone(self):
        self.assertEqual("4k", videosession.normRes("4k"))
        self.assertEqual("sd", videosession.normRes("sd"))

    def test_an_already_suffixed_resolution_is_not_double_suffixed(self):
        self.assertEqual("1080p", videosession.normRes("1080p"))

    def test_an_empty_resolution(self):
        self.assertEqual("", videosession.normRes(""))


class ModuleShapeTest(KodiTestCase):
    """
    Cheap guards that the module still exposes what the windows import; a
    rename here shows up as an AttributeError deep inside playback otherwise.
    """

    def test_playqueue_exposes_its_public_helpers(self):
        for name in ("AudioUsage", "UsageFactory", "PlayOptions", "PlayQueue",
                     "PlayQueueFactory", "createPlayQueueForItem"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(playqueue, name), name)

    def test_videosession_exposes_its_media_detail_types(self):
        for name in ("MediaDetails", "MediaDetailsIncomplete", "MediaDetailsHolder",
                     "normRes"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(videosession, name), name)
