# coding=utf-8
"""
plexnet.mediadecisionengine - direct play vs transcode, and how subtitles ride along.

The subtitle decision decides whether a track can be handed to Kodi as a soft
subtitle or has to be burned into a transcode, and the choice sort decides
which Media version of a title gets played at all.
"""

from __future__ import absolute_import

from kodienv import ENV

from plexnet import mediachoice, plexstream
from plexnet.mediadecisionengine import MediaDecisionEngine

from .base import KodiTestCase, ensure_plex_interface


class FakeSorts(object):
    def __init__(self, **kwargs):
        self.directPlay = kwargs.get("directPlay", 0)
        self.videoDS = kwargs.get("videoDS", 0)
        self.audioDS = kwargs.get("audioDS", 0)
        self.resolution = kwargs.get("resolution", 0)
        self.bitrate = kwargs.get("bitrate", 0)


class FakeServer(object):
    def __init__(self, local=True, transcoding=True, remuxOnly=False):
        self.supportsVideoTranscoding = transcoding
        self.supportsVideoRemuxOnly = remuxOnly
        self._local = local

    def isLocalConnection(self):
        return self._local


class FakeMedia(object):
    def __init__(self, server=None, proxyType=None):
        self._server = server or FakeServer()
        self.proxyType = proxyType

    def getServer(self):
        return self._server


class FakeChoice(object):
    """Enough of a MediaChoice for the sort helpers."""

    def __init__(self, name="choice", media=None, **sorts):
        self.name = name
        self.media = media
        self.sorts = FakeSorts(**sorts)
        self.bitrate = sorts.get("bitrate", 0)
        self.audioChannels = sorts.get("audioChannels", 0)
        self.audioDS = sorts.get("audioDS", 0)
        self.resolution = sorts.get("resolution", 0)
        self.videoDS = sorts.get("videoDS", 0)
        self.isDirectPlayable = sorts.get("isDirectPlayable", 0)

    def __repr__(self):
        return "<FakeChoice {0}>".format(self.name)


class FakeStream(object):
    def __init__(self, key=None, codec="srt", languageCode="eng"):
        self.key = key
        self.codec = codec
        self.languageCode = languageCode


class SubtitleDecisionTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        self.mde = MediaDecisionEngine()

    def test_an_embedded_subtitle_can_only_be_direct_played(self):
        """No key means the track lives inside the file."""
        ENV.settings["burn_subtitles"] = "auto"
        self.assertEqual(mediachoice.MediaChoice.SUBTITLES_SOFT_DP,
                         self.mde.evaluateSubtitles(FakeStream(key=None)))

    def test_a_sidecar_subtitle_works_with_a_transcode_too(self):
        ENV.settings["burn_subtitles"] = "auto"
        self.assertEqual(mediachoice.MediaChoice.SUBTITLES_SOFT_ANY,
                         self.mde.evaluateSubtitles(FakeStream(key="/library/streams/7")))

    def test_the_burn_preference_overrides_everything(self):
        ENV.settings["burn_subtitles"] = "always"
        for stream in (FakeStream(key=None), FakeStream(key="/library/streams/7")):
            with self.subTest(key=stream.key):
                self.assertEqual(mediachoice.MediaChoice.SUBTITLES_BURN,
                                 self.mde.evaluateSubtitles(stream))

    def test_the_decision_constants_are_distinct(self):
        constants = (mediachoice.MediaChoice.SUBTITLES_DEFAULT,
                     mediachoice.MediaChoice.SUBTITLES_BURN,
                     mediachoice.MediaChoice.SUBTITLES_SOFT_DP,
                     mediachoice.MediaChoice.SUBTITLES_SOFT_ANY)
        self.assertEqual(len(constants), len(set(constants)))


class SortTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        self.mde = MediaDecisionEngine()

    def names(self, choices):
        return [c.name for c in choices]

    def test_sorting_by_an_attribute_name(self):
        choices = [FakeChoice("high", bitrate=20000), FakeChoice("low", bitrate=2000)]
        self.mde.sort(choices, "bitrate")
        self.assertEqual(["low", "high"], self.names(choices))

    def test_sorting_by_a_callable(self):
        choices = [FakeChoice("b"), FakeChoice("a")]
        self.mde.sort(choices, lambda c: c.name)
        self.assertEqual(["a", "b"], self.names(choices))

    def test_sorting_a_non_list_is_a_no_op(self):
        self.mde.sort("not a list", "bitrate")
        self.mde.sort(None, "bitrate")

    def test_sort_choices_tolerates_none(self):
        self.assertEqual([], self.mde.sortChoices(None))

    def test_sort_choices_leaves_a_single_choice_alone(self):
        only = [FakeChoice("only", media=FakeMedia())]
        self.assertEqual(only, self.mde.sortChoices(only))

    def test_sort_choices_puts_the_best_option_last(self):
        """
        The chain of stable sorts ends up with the preferred choice at the end
        of the list; chooseMedia takes the last one.
        """
        low = FakeChoice("low", media=FakeMedia(), bitrate=2000, resolution=720,
                         isDirectPlayable=0)
        high = FakeChoice("high", media=FakeMedia(), bitrate=20000, resolution=2160,
                          isDirectPlayable=1)
        ordered = self.mde.sortChoices([low, high])
        self.assertEqual("high", ordered[-1].name)

    def test_a_direct_playable_choice_outranks_a_higher_bitrate_transcode(self):
        transcode = FakeChoice("transcode", media=FakeMedia(), bitrate=30000,
                               isDirectPlayable=0)
        direct = FakeChoice("direct", media=FakeMedia(), bitrate=10000,
                            isDirectPlayable=1)
        ordered = self.mde.sortChoices([direct, transcode])
        self.assertEqual("direct", ordered[-1].name)


class HigherResIfCapableTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        self.mde = MediaDecisionEngine()

    def test_a_transcoding_server_lets_a_direct_playable_choice_keep_its_resolution(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(transcoding=True)),
                            directPlay=1, resolution=2160)
        self.assertEqual(2160, self.mde.higherResIfCapable(choice))

    def test_a_remux_only_server_does_not_get_the_boost(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(transcoding=True, remuxOnly=True)),
                            directPlay=1, resolution=2160)
        self.assertEqual(0, self.mde.higherResIfCapable(choice))

    def test_a_server_without_transcoding_does_not_get_the_boost(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(transcoding=False)),
                            directPlay=1, resolution=2160)
        self.assertEqual(0, self.mde.higherResIfCapable(choice))

    def test_a_choice_that_is_neither_direct_play_nor_direct_stream(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(transcoding=True)),
                            directPlay=0, videoDS=0, resolution=2160)
        self.assertEqual(0, self.mde.higherResIfCapable(choice))

    def test_direct_streaming_also_qualifies(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(transcoding=True)),
                            directPlay=0, videoDS=1, resolution=2160)
        self.assertEqual(2160, self.mde.higherResIfCapable(choice))

    def test_a_choice_without_media(self):
        self.assertEqual(0, self.mde.higherResIfCapable(FakeChoice(media=None)))


class CloudIfRemoteTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        self.mde = MediaDecisionEngine()

    def test_a_local_non_cloud_media_is_preferred(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(local=True), proxyType=None))
        self.assertEqual(1, self.mde.cloudIfRemote(choice))

    def test_a_remote_media_is_not_boosted(self):
        choice = FakeChoice(media=FakeMedia(FakeServer(local=False), proxyType=None))
        self.assertEqual(0, self.mde.cloudIfRemote(choice))

    def test_a_local_cloud_proxied_media_is_not_boosted(self):
        mde = self.mde
        choice = FakeChoice(media=FakeMedia(FakeServer(local=True),
                                            proxyType=mde.proxyTypes.CLOUD))
        self.assertEqual(0, mde.cloudIfRemote(choice))

    def test_a_choice_without_media(self):
        self.assertEqual(0, self.mde.cloudIfRemote(FakeChoice(media=None)))


class Supported4kTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.interface = ensure_plex_interface()
        self.mde = MediaDecisionEngine()

    def test_4k_is_supported_when_the_feature_is_advertised(self):
        self.assertIn("allow_4k", self.interface.getPlaybackFeatures())
        self.assertTrue(self.mde.isSupported4k(FakeMedia(), FakeStream()))

    def test_no_video_stream_means_no_4k(self):
        self.assertFalse(self.mde.isSupported4k(FakeMedia(), None))

    def test_without_the_feature_4k_is_refused(self):
        original = self.interface.getPlaybackFeatures
        try:
            self.interface.getPlaybackFeatures = lambda: ["playback_directplay"]
            self.assertFalse(self.mde.isSupported4k(FakeMedia(), FakeStream()))
        finally:
            self.interface.getPlaybackFeatures = original


class StreamTypeConstantsTest(KodiTestCase):
    def test_the_engine_and_the_stream_class_agree_on_types(self):
        """
        evaluateMediaVideo indexes streams by these numbers; a drift between
        the two would silently mis-classify every track.
        """
        self.assertEqual(1, plexstream.PlexStream.TYPE_VIDEO)
        self.assertEqual(2, plexstream.PlexStream.TYPE_AUDIO)
        self.assertEqual(3, plexstream.PlexStream.TYPE_SUBTITLE)
