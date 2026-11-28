# coding=utf-8
"""
plexnet.plexstream - stream titles and the flags subtitle selection depends on.

`forced_subtitle` and `sdh` drive which subtitle track PM4K auto-picks, and
Plex is inconsistent about whether those are real attributes or just words in
the title - so both routes are covered. `videoCodecRendering` is what labels a
track as DV P8.1 / P7 / HDR10 in the UI.
"""

from __future__ import absolute_import

from xml.etree import ElementTree as ET

from plexnet import plexstream, video
from plexnet.plexstream import NoneStream, PlexStream

from .base import KodiTestCase, ensure_plex_interface, fixture


def stream(**attrs):
    ensure_plex_interface()
    element = ET.Element("Stream", {k: str(v) for k, v in attrs.items()})
    return PlexStream(element)


def movie_part():
    ensure_plex_interface()
    root = ET.fromstring(fixture("plexnet", "movie.xml"))
    return video.Movie(root.find("Video")).media[0].parts[0]


def by_id(part):
    return {s.id: s for s in part.streams}


class StreamTypeTest(KodiTestCase):
    def test_the_type_constants_match_plex(self):
        self.assertEqual(1, PlexStream.TYPE_VIDEO)
        self.assertEqual(2, PlexStream.TYPE_AUDIO)
        self.assertEqual(3, PlexStream.TYPE_SUBTITLE)
        self.assertEqual(4, PlexStream.TYPE_LYRICS)

    def test_repr_names_the_stream_type(self):
        self.assertIn("AudioStream", repr(stream(streamType=2, codec="ac3", channels=6)))
        self.assertIn("SubtitleStream", repr(stream(streamType=3, codec="srt")))


class ForcedSubtitleTest(KodiTestCase):
    def test_the_forced_attribute_is_honoured(self):
        self.assertTrue(stream(streamType=3, forced=1).forced_subtitle)
        self.assertFalse(stream(streamType=3, forced=0).forced_subtitle)

    def test_a_missing_forced_attribute_is_not_forced(self):
        self.assertFalse(stream(streamType=3, codec="srt").forced_subtitle)

    def test_the_word_forced_in_the_title_counts(self):
        """
        Plenty of releases only say "Forced" in the track name, so the title is
        tokenised as a fallback.
        """
        self.assertTrue(stream(streamType=3, title="Forced").forced_subtitle)
        self.assertTrue(stream(streamType=3, displayTitle="English (Forced)").forced_subtitle)
        self.assertTrue(stream(streamType=3,
                              extendedDisplayTitle="English [FORCED] SRT").forced_subtitle)

    def test_separators_around_the_token_are_normalised(self):
        for title in ("English.forced.srt", "English_Forced", "eng-forced",
                      "English (forced)", "English|Forced", "sub;forced"):
            with self.subTest(title=title):
                self.assertTrue(stream(streamType=3, title=title).forced_subtitle)

    def test_forced_as_part_of_a_longer_word_does_not_count(self):
        """
        Tokenised, not substring-matched - otherwise "Reinforced" and
        "unforced" would be treated as forced tracks.
        """
        for title in ("Reinforced", "unforced", "forcedly"):
            with self.subTest(title=title):
                self.assertFalse(stream(streamType=3, title=title).forced_subtitle)

    def test_matching_is_case_insensitive(self):
        self.assertTrue(stream(streamType=3, title="FORCED").forced_subtitle)
        self.assertTrue(stream(streamType=3, title="Forced").forced_subtitle)


class SDHTest(KodiTestCase):
    def test_the_hearing_impaired_attribute_is_honoured(self):
        self.assertTrue(stream(streamType=3, hearingImpaired=1).sdh)

    def test_sdh_in_any_title_counts(self):
        self.assertTrue(stream(streamType=3, title="English SDH").sdh)
        self.assertTrue(stream(streamType=3, displayTitle="English (SDH)").sdh)
        self.assertTrue(stream(streamType=3, extendedDisplayTitle="SDH English").sdh)

    def test_a_plain_track_is_not_sdh(self):
        self.assertFalse(stream(streamType=3, title="English").sdh)


class StreamTitleTest(KodiTestCase):
    def test_a_video_stream_is_titled_by_its_codec(self):
        self.assertEqual("HEVC", stream(streamType=1, codec="hevc").getTitle())

    def test_a_video_stream_without_a_codec_says_unknown(self):
        self.assertEqual("Unknown", stream(streamType=1).getTitle())

    def test_an_audio_stream_shows_language_codec_and_channels(self):
        title = stream(streamType=2, codec="ac3", channels=6, language="English",
                       languageCode="eng").getTitle()
        self.assertIn("English", title)
        self.assertIn("5.1", title)

    def test_channel_counts_are_named(self):
        self.assertEqual("Mono", stream(streamType=2, channels=1).getChannels())
        self.assertEqual("Stereo", stream(streamType=2, channels=2).getChannels())
        self.assertEqual("5.1", stream(streamType=2, channels=6).getChannels())
        self.assertEqual("7.1", stream(streamType=2, channels=8).getChannels())
        self.assertEqual("", stream(streamType=2).getChannels())

    def test_an_unknown_language_falls_back(self):
        self.assertEqual("Unknown", stream(streamType=2).getLanguageName())

    def test_non_latin_languages_use_a_safe_english_name(self):
        """PM4K's fonts can't render every script, so a few get English names."""
        for code, expected in (("jpn", "Japanese"), ("rus", "Russian"),
                               ("chi", "Chinese"), ("ara", "Arabic")):
            with self.subTest(code=code):
                self.assertEqual(expected, stream(streamType=2, languageCode=code,
                                                  language="Nihongo").getLanguageName())

    def test_a_latin_language_keeps_the_plex_supplied_name(self):
        self.assertEqual("Deutsch", stream(streamType=2, languageCode="deu",
                                           language="Deutsch").getLanguageName())

    def test_a_subtitle_title_lists_codec_embedded_and_forced(self):
        title = stream(streamType=3, codec="srt", forced=1, language="English",
                       languageCode="eng").getTitle()
        self.assertIn("SRT", title)
        self.assertIn("Embedded", title)
        self.assertIn("Forced", title)

    def test_a_sidecar_subtitle_is_not_labelled_embedded(self):
        title = stream(streamType=3, codec="srt", key="/library/streams/7",
                       language="German", languageCode="deu").getTitle()
        self.assertNotIn("Embedded", title)

    def test_a_lyrics_stream_is_titled_lyrics(self):
        self.assertEqual("Lyrics", stream(streamType=4).getTitle())
        self.assertEqual("Lyrics (lrc)", stream(streamType=4, format="lrc").getTitle())


class VideoCodecRenderingTest(KodiTestCase):
    def test_dolby_vision_profile_8_variants(self):
        cases = {
            ("8", "1"): "DV P8.1/HDR",
            ("8", "2"): "DV P8.2/SDR",
            ("8", "4"): "DV P8.4/HLG",
        }
        for (profile, compat), expected in sorted(cases.items()):
            with self.subTest(profile=profile, compat=compat):
                self.assertEqual(expected, stream(streamType=1, DOVIProfile=profile,
                                                  DOVIBLCompatID=compat).videoCodecRendering)

    def test_dolby_vision_profile_7_and_5(self):
        self.assertEqual("DV P7/HDR",
                         stream(streamType=1, DOVIProfile="7").videoCodecRendering)
        self.assertEqual("DV P5",
                         stream(streamType=1, DOVIProfile="5").videoCodecRendering)

    def test_an_unrecognised_dv_profile_still_reports_dv(self):
        self.assertEqual("DV P9",
                         stream(streamType=1, DOVIProfile="9").videoCodecRendering)

    def test_hdr10_is_detected_from_the_transfer_function(self):
        self.assertEqual("HDR", stream(streamType=1,
                                       colorTrc="smpte2084").videoCodecRendering)

    def test_hlg_is_detected_from_the_transfer_function(self):
        self.assertEqual("HLG", stream(streamType=1,
                                       colorTrc="arib-std-b67").videoCodecRendering)

    def test_dolby_vision_outranks_the_transfer_function(self):
        """A P8.1 track carries an HDR10 base layer; it must still read as DV."""
        self.assertEqual("DV P8.1/HDR",
                         stream(streamType=1, DOVIProfile="8", DOVIBLCompatID="1",
                                colorTrc="smpte2084").videoCodecRendering)

    def test_plain_video_is_sdr(self):
        self.assertEqual("SDR", stream(streamType=1, codec="h264").videoCodecRendering)


class SelectionTest(KodiTestCase):
    def test_selected_reflects_the_attribute(self):
        self.assertTrue(stream(streamType=2, selected=1).isSelected())
        self.assertFalse(stream(streamType=2).isSelected())

    def test_set_selected_round_trips(self):
        item = stream(streamType=2)
        item.setSelected(True)
        self.assertTrue(item.isSelected())
        item.setSelected(False)
        self.assertFalse(item.isSelected())

    def test_equality_compares_the_identifying_attributes(self):
        first = stream(streamType=2, codec="ac3", channels=6, index=1, language="English")
        same = stream(streamType=2, codec="ac3", channels=6, index=1, language="English")
        other = stream(streamType=2, codec="eac3", channels=6, index=1, language="English")
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)

    def test_a_stream_never_equals_nothing_or_another_class(self):
        item = stream(streamType=2, codec="ac3")
        self.assertNotEqual(item, None)
        self.assertNotEqual(item, NoneStream())


class SubtitlePathTest(KodiTestCase):
    def test_the_query_asks_for_utf8(self):
        item = stream(streamType=3, codec="srt", key="/library/streams/7")
        self.assertEqual("/library/streams/7?encoding=utf-8", item.getSubtitlePath())

    def test_smi_is_converted_to_srt(self):
        """Kodi can't render SMI, so the server is asked to convert."""
        item = stream(streamType=3, codec="smi", key="/library/streams/7")
        self.assertIn("&format=srt", item.getSubtitlePath())

    def test_an_embedded_stream_has_no_server_path(self):
        item = stream(streamType=3, codec="srt")
        self.assertIsNone(item.getSubtitleServerPath())
        self.assertTrue(item.embedded)

    def test_auto_sync_is_only_requested_when_the_stream_wants_it(self):
        item = stream(streamType=3, codec="srt", key="/library/streams/7")
        self.assertNotIn("autoAdjustSubtitle", item.getSubtitlePath())
        item.should_auto_sync = True
        self.assertIn("autoAdjustSubtitle=1", item.getSubtitlePath())

    def test_auto_sync_can_be_declined_explicitly(self):
        item = stream(streamType=3, codec="srt", key="/library/streams/7")
        item.should_auto_sync = True
        self.assertNotIn("autoAdjustSubtitle", item.getSubtitlePath(auto_sync=False))


class NoneStreamTest(KodiTestCase):
    def test_it_is_the_zero_id_synthetic_stream(self):
        ensure_plex_interface()
        self.assertEqual("0", NoneStream().id)

    def test_subtitle_lists_get_a_none_option_prepended(self):
        part = movie_part()
        subtitles = part.getStreamsOfType(PlexStream.TYPE_SUBTITLE)
        self.assertIsInstance(subtitles[0], NoneStream)
        self.assertEqual(["0", "4", "5", "6", "7"], [s.id for s in subtitles])

    def test_none_is_selected_when_no_subtitle_track_is(self):
        part = movie_part()
        subtitles = part.getStreamsOfType(PlexStream.TYPE_SUBTITLE)
        self.assertTrue(subtitles[0].isSelected())

    def test_none_is_not_selected_when_a_track_already_is(self):
        part = movie_part()
        by_id(part)["5"].setSelected(True)
        subtitles = part.getStreamsOfType(PlexStream.TYPE_SUBTITLE)
        self.assertFalse(subtitles[0].isSelected())
        self.assertTrue(by_id(part)["5"].isSelected())

    def test_audio_lists_get_no_none_option(self):
        part = movie_part()
        audio = part.getStreamsOfType(PlexStream.TYPE_AUDIO)
        self.assertFalse(any(isinstance(s, NoneStream) for s in audio))


class FixtureStreamTest(KodiTestCase):
    """End-to-end over the recorded MediaContainer, the way a real title arrives."""

    def setUp(self):
        KodiTestCase.setUp(self)
        self.streams = by_id(movie_part())

    def test_the_video_stream_is_dolby_vision_profile_8_1(self):
        self.assertEqual("DV P8.1/HDR", self.streams["1"].videoCodecRendering)

    def test_the_truehd_track_is_selected(self):
        self.assertTrue(self.streams["2"].isSelected())
        self.assertEqual("truehd", self.streams["2"].codec)
        self.assertEqual(8, self.streams["2"].channels.asInt())

    def test_the_forced_track_is_detected_from_its_attribute(self):
        self.assertTrue(self.streams["5"].forced_subtitle)

    def test_the_sdh_track_is_detected_from_its_attribute(self):
        self.assertTrue(self.streams["6"].sdh)

    def test_the_plain_pgs_track_is_neither_forced_nor_sdh(self):
        self.assertFalse(self.streams["4"].forced_subtitle)
        self.assertFalse(self.streams["4"].sdh)

    def test_the_german_track_is_the_only_sidecar_one(self):
        """
        A stream `key` is what distinguishes a sidecar subtitle from an
        embedded one. (The `embedded` property answers the same question but
        routes through getSubtitleServerPath(), so it needs a live server -
        see SubtitlePathTest for that path.)
        """
        keys = {sid: bool(s.key) for sid, s in self.streams.items()
                if s.streamType.asInt() == plexstream.PlexStream.TYPE_SUBTITLE}
        self.assertEqual({"4": False, "5": False, "6": False, "7": True}, keys)
