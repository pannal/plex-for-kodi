# coding=utf-8
"""
plexnet.plexobjects - the typed-attribute layer every Plex response goes through.

PlexValue is a str subclass with asInt()/asBool()/asDatetime() helpers, and
missing attributes come back as an empty PlexValue rather than raising. That
"never raises" design is convenient but makes typos silent, so the coercions
and the NA behaviour are worth pinning.
"""

from __future__ import absolute_import

from datetime import datetime
from unittest.mock import patch
from xml.etree import ElementTree as ET

from plexnet import media, plexobjects, plexstream, video

from .base import KodiTestCase, ensure_plex_interface, fixture


def movie():
    ensure_plex_interface()
    root = ET.fromstring(fixture("plexnet", "movie.xml"))
    return video.Movie(root.find("Video"))


class PlexValueTest(KodiTestCase):
    def test_it_is_a_string(self):
        value = plexobjects.PlexValue("42")
        self.assertEqual("42", value)
        self.assertIsInstance(value, str)

    def test_as_int(self):
        self.assertEqual(42, plexobjects.PlexValue("42").asInt())
        self.assertEqual(0, plexobjects.PlexValue("").asInt())
        self.assertEqual(7, plexobjects.PlexValue("").asInt(default=7))

    def test_as_float(self):
        self.assertEqual(2.35, plexobjects.PlexValue("2.35").asFloat())
        self.assertEqual(0.0, plexobjects.PlexValue("").asFloat())

    def test_as_bool_accepts_plex_truthy_spellings(self):
        self.assertTrue(plexobjects.PlexValue("1").asBool())
        self.assertTrue(plexobjects.PlexValue("true").asBool())
        self.assertFalse(plexobjects.PlexValue("0").asBool())
        self.assertFalse(plexobjects.PlexValue("").asBool())

    def test_as_bool_is_strict_about_spelling(self):
        """"True" and "yes" are not Plex spellings and must not read as true."""
        self.assertFalse(plexobjects.PlexValue("True").asBool())
        self.assertFalse(plexobjects.PlexValue("yes").asBool())

    def test_comparison_is_numeric(self):
        self.assertTrue(plexobjects.PlexValue("10") > 9)
        self.assertTrue(plexobjects.PlexValue("9") < 10)

    def test_as_datetime_from_an_epoch(self):
        value = plexobjects.PlexValue("1600000000")
        self.assertEqual(datetime.fromtimestamp(1600000000), value.asDatetime())

    def test_as_datetime_from_an_iso_date(self):
        self.assertEqual("2008-07-18",
                         plexobjects.PlexValue("2008-07-18").asDatetime("%Y-%m-%d"))

    def test_as_datetime_handles_pre_epoch_dates(self):
        """
        There are shows older than 1970-01-02, and time.mktime raises on those;
        the fallback path has to cope rather than losing the date.
        """
        self.assertEqual(datetime(1927, 1, 10),
                         plexobjects.PlexValue("1927-01-10").asDatetime())

    def test_as_datetime_of_nothing_is_none(self):
        self.assertIsNone(plexobjects.PlexValue("").asDatetime())

    def test_calling_a_value_supplies_a_default_when_it_is_na(self):
        present = plexobjects.PlexValue("mkv")
        self.assertEqual("mkv", present("fallback"))

        absent = plexobjects.PlexValue("")
        absent.NA = True
        self.assertEqual("fallback", absent("fallback"))

    def test_a_copy_keeps_the_value(self):
        import copy
        value = plexobjects.PlexValue("42")
        self.assertEqual("42", copy.deepcopy(value))


class PlexObjectAttributeTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.movie = movie()

    def test_attributes_come_back_as_plex_values(self):
        self.assertIsInstance(self.movie.year, plexobjects.PlexValue)
        self.assertEqual(2008, self.movie.year.asInt())

    def test_text_attributes(self):
        self.assertEqual("The Dark Knight", self.movie.title)
        self.assertEqual("Dark Knight", self.movie.titleSort)
        self.assertEqual("movie", self.movie.type)

    def test_a_missing_attribute_is_an_empty_value_not_an_error(self):
        missing = self.movie.definitelyNotAnAttribute
        self.assertEqual("", missing)
        self.assertFalse(missing)
        self.assertEqual(0, missing.asInt())

    def test_get_returns_a_default_for_a_missing_attribute(self):
        self.assertEqual("fallback", self.movie.get("nope", "fallback"))
        self.assertEqual("The Dark Knight", self.movie.get("title", "fallback"))

    def test_the_ratingkey_and_key_are_parsed(self):
        self.assertEqual("1234", self.movie.ratingKey)
        self.assertEqual("/library/metadata/1234", self.movie.key)

    def test_it_is_recognised_as_a_library_video_item(self):
        self.assertTrue(self.movie.isLibraryItem())
        self.assertTrue(self.movie.isVideoOrDirectoryItem())
        self.assertFalse(self.movie.isMusicOrDirectoryItem())
        self.assertFalse(self.movie.isPhotoOrDirectoryItem())


class SubObjectTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.movie = movie()

    def test_media_is_exposed_as_an_item_list(self):
        self.assertIsInstance(self.movie.media, plexobjects.PlexMediaItemList)
        self.assertEqual(1, len(self.movie.media))

    def test_media_attributes(self):
        media = self.movie.media[0]
        self.assertEqual("hevc", media.videoCodec)
        self.assertEqual("truehd", media.audioCodec)
        self.assertEqual("4k", media.videoResolution)
        self.assertEqual(3840, media.width.asInt())
        self.assertEqual(8, media.audioChannels.asInt())

    def test_parts_and_their_file_path(self):
        part = self.movie.media[0].parts[0]
        self.assertEqual("9012", part.id)
        self.assertTrue(part.file.endswith("The Dark Knight (2008) UHD.mkv"))
        self.assertEqual(64424509440, part.size.asInt())

    def test_the_xml_container_attribute_is_renamed_out_of_the_way(self):
        """
        `container` is a PlexObject slot holding the parent MediaContainer, so
        _setData renames any XML container="..." attribute to attrib_container.
        Reading part.container gives you the owning Media object (PlexPart
        reassigns it), never the "mkv" string - a trap when writing new code
        against a Part.
        """
        part = self.movie.media[0].parts[0]
        self.assertEqual("mkv", part.attrib_container)
        self.assertIs(self.movie.media[0], part.container)

    def test_the_media_object_keeps_its_container_the_same_way(self):
        self.assertEqual("mkv", self.movie.media[0].attrib_container)

    def test_every_stream_is_parsed(self):
        streams = self.movie.media[0].parts[0].streams
        self.assertEqual(7, len(streams))
        self.assertEqual(["1", "2", "3", "4", "5", "6", "7"], [s.id for s in streams])

    def test_audio_streams_are_filtered_by_type(self):
        part = self.movie.media[0].parts[0]
        self.assertEqual(["2", "3"], [s.id for s in part.audioStreams])

    def test_get_streams_of_type_filters_video_and_audio(self):
        part = self.movie.media[0].parts[0]
        self.assertEqual(["1"], [s.id for s in
                                 part.getStreamsOfType(plexstream.PlexStream.TYPE_VIDEO)])
        self.assertEqual(["2", "3"], [s.id for s in
                                      part.getStreamsOfType(plexstream.PlexStream.TYPE_AUDIO)])

    def test_guids_are_parsed(self):
        self.assertEqual(["imdb://tt0468569", "tmdb://155", "tvdb://12345"],
                         [g.id for g in self.movie.guids])

    def test_tag_lists_are_parsed(self):
        self.assertEqual(["Action", "Crime"], [g.tag for g in self.movie.genres])
        self.assertEqual(["Christopher Nolan"], [d.tag for d in self.movie.directors])

    def test_roles_carry_the_character_name(self):
        roles = {r.tag: r.role for r in self.movie.roles}
        self.assertEqual("Joker", roles["Heath Ledger"])


class RelatedCountTest(KodiTestCase):
    def assert_related_count(self, attributes, expected):
        item = movie()
        data = ET.Element("MediaContainer", attributes)
        container = plexobjects.PlexContainer(data, "/similar", address="/similar")
        related = plexobjects.ItemContainer().init(container)
        with patch.object(media.RelatedMixin, "getRelated", return_value=related) as get_related:
            self.assertEqual(expected, int(item.relatedCount))
            self.assertEqual(expected, int(item.relatedCount))
            get_related.assert_called_once_with(0, 0)

    def test_missing_total_size_is_zero(self):
        self.assert_related_count({"size": "28"}, 0)

    def test_empty_total_size_is_zero(self):
        self.assert_related_count({"size": "0", "totalSize": ""}, 0)

    def test_explicit_zero_is_preserved(self):
        self.assert_related_count({"size": "0", "totalSize": "0"}, 0)

    def test_count_only_response_preserves_the_total(self):
        self.assert_related_count({"size": "0", "totalSize": "36"}, 36)

    def test_unavailable_related_response_is_zero(self):
        item = movie()
        with patch.object(media.RelatedMixin, "getRelated", return_value=None) as get_related:
            self.assertEqual(0, int(item.relatedCount))
            self.assertEqual(0, int(item.relatedCount))
            get_related.assert_called_once_with(0, 0)


class ProgressTest(KodiTestCase):
    def test_view_offset_and_duration_are_usable_as_numbers(self):
        item = movie()
        self.assertEqual(1800000, item.viewOffset.asInt())
        self.assertEqual(9120000, item.duration.asInt())
        percent = int(item.viewOffset.asInt() / item.duration.asFloat() * 100)
        self.assertEqual(19, percent)

    def test_search_types_cover_the_item_types_pm4k_browses(self):
        for libtype in ("movie", "show", "season", "episode", "artist", "album",
                        "track", "photo", "collection"):
            with self.subTest(libtype=libtype):
                self.assertEqual(plexobjects.SEARCHTYPES[libtype],
                                 plexobjects.searchType(libtype))

    def test_an_unknown_search_type_raises(self):
        from plexnet import exceptions
        with self.assertRaises(exceptions.NotFound):
            plexobjects.searchType("nonsense")


def episodeWithImages():
    ensure_plex_interface()
    root = ET.fromstring(fixture("plexnet", "episode_images.xml"))
    return video.Episode(root.find("Video"))


class ImagesTest(KodiTestCase):
    """
    The Image children carry the art variants the server picked, clearLogo among them. They only show up in full
    metadata responses, so an item built from a listing simply has none of them.
    """

    def setUp(self):
        super(ImagesTest, self).setUp()
        self.episode = episodeWithImages()

    def test_images_are_parsed(self):
        self.assertEqual(["coverPoster", "snapshot", "background", "clearLogo", "backgroundSquare"],
                         [i.type for i in self.episode.images])

    def test_clear_logo_points_at_the_show(self):
        # the server resolves the parent walk for us; 2101 is the grandparent, 2103 the episode
        self.assertEqual("/library/metadata/2101/clearLogo/1600000000", self.episode.clearLogo)

    def test_clear_logo_is_none_without_images(self):
        self.assertIsNone(movie().clearLogo)

    def test_clear_logo_survives_a_reload(self):
        # _setData rebuilds the lists, so a reloaded item must not keep the old element's images
        item = movie()
        self.assertIsNone(item.clearLogo)
        item._setData(ET.fromstring(fixture("plexnet", "episode_images.xml")).find("Video"))
        self.assertEqual("/library/metadata/2101/clearLogo/1600000000", item.clearLogo)
