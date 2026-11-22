# coding=utf-8
"""
plexnet.dvr - watching DVR recordings while they are still being recorded.

Scope is recordings only, not live TV: list what the server is recording right
now, put it on Home as a "Recording now" row, and tell whether a stream is still
growing (an HLS media playlist without EXT-X-ENDLIST).
"""

from __future__ import absolute_import

from xml.etree import ElementTree as ET

from plexnet import dvr

from .base import KodiTestCase, ensure_plex_interface, fixture


GUID = "plex://episode/ad40b8318c9c7212ea805cbf"
TITLE = "River City Kings at Metro Hawks"
OP_ID = "5d445defa82b5d8f2b7090ed64c659bb319aad84"


def scheduled():
    return fixture("plexnet", "subscriptions_scheduled.xml")


def library_lookup():
    return fixture("plexnet", "library_all_guid_recording.xml")


EMPTY = '<MediaContainer size="0"/>'


class FakeServer(object):
    """
    Answers query() from canned responses and records what was asked.
    The scheduled list comes from `xml`; a /library/all guid lookup from `library` (dict guid -> xml),
    defaulting to the real capture for the recording in the fixture.
    """

    def __init__(self, xml=None, error=None, library=None):
        self.xml = xml
        self.error = error
        self.library = {GUID: library_lookup()} if library is None else library
        self.queries = []

    def query(self, path, **kwargs):
        params = kwargs.get("params") or {}
        self.queries.append((path, params.get("guid")) if params else path)
        if self.error:
            raise self.error
        if path == dvr.LIBRARY_LOOKUP_PATH:
            return ET.fromstring(self.library.get(params.get("guid"), EMPTY))
        return ET.fromstring(self.xml) if self.xml is not None else None


def second_recording(root, op_id, guid, title):
    """Copy the fixture's in-progress operation as another game recording at the same time."""
    src = [op for op in root.findall("MediaGrabOperation") if op.get("status") == "inprogress"][0]
    op = ET.fromstring(ET.tostring(src))
    op.set("id", op_id)
    video = op.find("Video")
    video.set("guid", guid)
    video.set("title", title)
    root.append(op)
    return root


class ActiveRecordingsTest(KodiTestCase):
    def setUp(self):
        super(ActiveRecordingsTest, self).setUp()
        ensure_plex_interface()

    def test_queries_the_scheduled_list_then_looks_up_the_library_item(self):
        server = FakeServer(scheduled())
        dvr.activeRecordings(server)
        self.assertEqual([dvr.SCHEDULED_PATH, (dvr.LIBRARY_LOOKUP_PATH, GUID)], server.queries)

    def test_lists_only_recordings_in_progress(self):
        """Real capture: one scheduled, one in progress, two complete."""
        recordings = dvr.activeRecordings(FakeServer(scheduled()))
        self.assertEqual([OP_ID], [r.id for r in recordings])

    def test_epg_only_item_gets_its_library_rating_key(self):
        """The grab's Video has an EPG key; the card must point at the library item the guid lookup finds."""
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        self.assertEqual("482133", item.ratingKey)
        self.assertEqual("/library/metadata/482133", item.key)

    def test_card_keeps_the_guide_details(self):
        """Title, artwork, summary and the scheduled length come from the guide data, which the library item lacks."""
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        self.assertEqual("episode", item.type)
        self.assertEqual(TITLE, item.title)
        self.assertEqual("NFL Football", item.grandparentTitle)
        self.assertTrue(item.summary.startswith("The Metro Hawks host"))
        self.assertEqual(10800000, item.duration.asInt())
        self.assertTrue(item.get("art").startswith("https://metadata-static.plex.tv/"))

    def test_card_air_date_reads_like_a_library_date(self):
        """The guide dates items "2026-11-22 06:00:00"; Home formats episode dates from "%Y-%m-%d" and crashed."""
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        self.assertEqual("2026-11-22", item.originallyAvailableAt)
        self.assertEqual("11/22/26", item.originallyAvailableAt.asDatetime("%m/%d/%y"))

    def test_card_drops_guide_parent_keys(self):
        """Show/season keys point at the EPG provider, not the library; opening them would fail."""
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        for attr in ("grandparentKey", "grandparentRatingKey", "parentKey", "parentRatingKey"):
            self.assertFalse(item.get(attr), attr)

    def test_recording_without_a_library_item_yet_is_skipped(self):
        """The server adds the library item a moment after the grab starts; until then nothing is playable."""
        self.assertEqual([], dvr.activeRecordings(FakeServer(scheduled(), library={})))

    def test_library_lookup_error_skips_that_recording(self):
        class Flaky(FakeServer):
            def query(self, path, **kwargs):
                if path == dvr.LIBRARY_LOOKUP_PATH:
                    raise IOError("timeout")
                return FakeServer.query(self, path, **kwargs)
        self.assertEqual([], dvr.activeRecordings(Flaky(scheduled())))

    def test_item_already_in_the_library_needs_no_lookup(self):
        root = ET.fromstring(scheduled())
        op = [o for o in root.findall("MediaGrabOperation") if o.get("status") == "inprogress"][0]
        op.find("Video").set("key", "/library/metadata/5501")
        op.find("Video").set("ratingKey", "5501")
        server = FakeServer(ET.tostring(root), library={})
        rec = dvr.activeRecordings(server)[0]
        self.assertEqual("/library/metadata/5501", rec.item.key)
        self.assertEqual([dvr.SCHEDULED_PATH], server.queries)

    def test_every_playable_recording_is_listed_so_one_can_be_picked(self):
        """Two games recording at once -> two cards in the row, in the server's order."""
        other = "plex://episode/second"
        root = second_recording(ET.fromstring(scheduled()), "80", other, "Cowboys at Giants")
        library = {GUID: library_lookup(),
                   other: library_lookup().replace("482133", "482200").replace(GUID, other)}
        server = FakeServer(ET.tostring(root), library=library)
        recordings = dvr.activeRecordings(server)
        self.assertEqual([TITLE, "Cowboys at Giants"], [r.item.title for r in recordings])
        self.assertEqual(["482133", "482200"], [r.item.ratingKey for r in recordings])
        self.assertEqual(2, dvr.recordingsHub(FakeServer(ET.tostring(root), library=library)).size.asInt())

    def test_recording_progress_fields(self):
        """Real servers report percent=-1 and currentSize=0 for a live grab."""
        rec = dvr.activeRecordings(FakeServer(scheduled()))[0]
        self.assertEqual(-1, rec.percent)
        self.assertEqual(0, rec.currentSize)
        self.assertTrue(rec.isRecording)

    def test_no_dvr_or_empty_response_is_an_empty_list(self):
        self.assertEqual([], dvr.activeRecordings(FakeServer(None)))
        self.assertEqual([], dvr.activeRecordings(FakeServer(EMPTY)))

    def test_server_error_is_an_empty_list_not_a_crash(self):
        """Shared users and servers without a DVR answer with an error; Home must still load."""
        self.assertEqual([], dvr.activeRecordings(FakeServer(error=Exception("401"))))

    def test_operations_without_an_item_are_skipped(self):
        xml = '<MediaContainer size="1"><MediaGrabOperation id="1" status="inprogress"/></MediaContainer>'
        self.assertEqual([], dvr.activeRecordings(FakeServer(xml)))


class RecordingsHubTest(KodiTestCase):
    def setUp(self):
        super(RecordingsHubTest, self).setUp()
        ensure_plex_interface()

    def test_hub_lists_the_recordings_items(self):
        hub = dvr.recordingsHub(FakeServer(scheduled()))
        self.assertEqual(dvr.HUB_IDENTIFIER, hub.hubIdentifier)
        self.assertEqual([TITLE], [i.title for i in hub.items])
        self.assertEqual(1, hub.size.asInt())
        self.assertFalse(hub.more)

    def test_no_hub_when_nothing_is_recording(self):
        self.assertIsNone(dvr.recordingsHub(FakeServer('<MediaContainer size="0"/>')))
        self.assertIsNone(dvr.recordingsHub(FakeServer(error=Exception("401"))))

    def test_hub_reload_picks_up_a_finished_recording(self):
        server = FakeServer(scheduled())
        hub = dvr.recordingsHub(server)
        server.xml = '<MediaContainer size="0"/>'
        hub.reload()
        self.assertEqual([], hub.items)

    def test_hub_extend_returns_the_current_items(self):
        hub = dvr.recordingsHub(FakeServer(scheduled()))
        self.assertEqual([TITLE], [i.title for i in hub.extend(0, 10)])


MEDIA_GROWING = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-PLAYLIST-TYPE:EVENT
#EXT-X-TARGETDURATION:2
#EXTINF:2.0,
segment0.ts
#EXTINF:2.0,
segment1.ts
"""

MEDIA_FINISHED = MEDIA_GROWING + "#EXT-X-ENDLIST\n"

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x1080
session/abc/base/index.m3u8
"""


class GrowingPlaylistTest(KodiTestCase):
    def test_media_playlist_without_endlist_is_growing(self):
        self.assertTrue(dvr.isGrowingHlsPlaylist(MEDIA_GROWING))

    def test_media_playlist_with_endlist_is_finished(self):
        self.assertFalse(dvr.isGrowingHlsPlaylist(MEDIA_FINISHED))

    def test_empty_or_non_hls_is_not_growing(self):
        self.assertFalse(dvr.isGrowingHlsPlaylist(""))
        self.assertFalse(dvr.isGrowingHlsPlaylist(None))
        self.assertFalse(dvr.isGrowingHlsPlaylist("<html>error</html>"))

    def test_master_playlist_cannot_tell_on_its_own(self):
        self.assertFalse(dvr.isGrowingHlsPlaylist(MASTER))

    def test_bytes_are_accepted(self):
        self.assertTrue(dvr.isGrowingHlsPlaylist(MEDIA_GROWING.encode("utf8")))

    def test_first_variant_resolves_relative_to_the_master(self):
        self.assertEqual(
            "http://pms:32400/video/:/transcode/universal/session/abc/base/index.m3u8",
            dvr.firstVariantUrl(MASTER, "http://pms:32400/video/:/transcode/universal/start.m3u8?x=1"))

    def test_first_variant_of_a_media_playlist_is_none(self):
        self.assertIsNone(dvr.firstVariantUrl(MEDIA_GROWING, "http://pms/start.m3u8"))

    def test_is_live_hls_follows_the_master_to_its_media_playlist(self):
        fetched = []
        answers = {
            "http://pms/start.m3u8": MASTER,
            "http://pms/session/abc/base/index.m3u8": MEDIA_GROWING,
        }

        def fetch(url):
            fetched.append(url)
            return answers[url]

        self.assertTrue(dvr.isLiveHls("http://pms/start.m3u8", fetch))
        self.assertEqual(["http://pms/start.m3u8", "http://pms/session/abc/base/index.m3u8"], fetched)

    def test_is_live_hls_finished_recording(self):
        self.assertFalse(dvr.isLiveHls("http://pms/index.m3u8", lambda url: MEDIA_FINISHED))

    def test_is_live_hls_fetch_failure_is_not_live(self):
        def fetch(url):
            raise IOError("timeout")
        self.assertFalse(dvr.isLiveHls("http://pms/index.m3u8", fetch))


HOME_HUBS = """<MediaContainer size="1">
  <Hub hubIdentifier="home.continue" title="Continue Watching" type="mixed" key="/hubs/home/continueWatching" size="0"/>
</MediaContainer>"""


class HomeHubsTest(KodiTestCase):
    """plexserver.PlexServer.hubs puts the recordings row first on Home, and only on Home."""

    def setUp(self):
        super(HomeHubsTest, self).setUp()
        ensure_plex_interface()

    def server(self, scheduled_xml):
        from plexnet import plexserver
        server = plexserver.PlexServer.__new__(plexserver.PlexServer)
        server.currentHubs = None
        server.asked = []

        def query(path, **kwargs):
            server.asked.append(path)
            if path == dvr.SCHEDULED_PATH:
                return ET.fromstring(scheduled_xml)
            if path == dvr.LIBRARY_LOOKUP_PATH:
                return ET.fromstring(library_lookup())
            return ET.fromstring(HOME_HUBS)

        server.query = query
        return server

    def test_recording_row_comes_first_on_home(self):
        hubs = self.server(scheduled()).hubs()
        self.assertEqual([dvr.HUB_IDENTIFIER, "home.continue"], [h.hubIdentifier for h in hubs])

    def test_no_row_when_nothing_is_recording(self):
        hubs = self.server('<MediaContainer size="0"/>').hubs()
        self.assertEqual(["home.continue"], [h.hubIdentifier for h in hubs])

    def test_sections_and_search_do_not_ask_for_recordings(self):
        server = self.server(scheduled())
        server.hubs(section="4")
        server.hubs(search_query="bears")
        self.assertNotIn(dvr.SCHEDULED_PATH, server.asked)


class OpenRecordingTest(KodiTestCase):
    """
    Opening a "Recording Now" card goes to the item's Play screen. An episode normally opens its show's episode
    list, but a recording in progress has no show in the library yet ("No data - deleted or server disconnected").
    """

    def setUp(self):
        super(OpenRecordingTest, self).setUp()
        ensure_plex_interface()
        from lib.windows import opener
        self.opener = opener
        self.opened = []
        self._orig = (opener.playableClicked, opener.episodeClicked)
        opener.playableClicked = lambda obj, **kw: self.opened.append(("play screen", obj)) or ""
        opener.episodeClicked = lambda obj, **kw: self.opened.append(("episode list", obj)) or ""

    def tearDown(self):
        self.opener.playableClicked, self.opener.episodeClicked = self._orig
        super(OpenRecordingTest, self).tearDown()

    def test_recording_items_are_marked(self):
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        self.assertTrue(dvr.isInProgressRecording(item))

    def test_recording_opens_the_play_screen(self):
        item = dvr.activeRecordings(FakeServer(scheduled()))[0].item
        self.opener.open(item)
        self.assertEqual([("play screen", item)], self.opened)

    def test_ordinary_episode_still_opens_the_episode_list(self):
        from plexnet import plexobjects
        elem = ET.fromstring('<Video type="episode" ratingKey="1" key="/library/metadata/1" title="Pilot"/>')
        episode = plexobjects.buildItem(None, elem, "/library/metadata/1")
        self.assertFalse(dvr.isInProgressRecording(episode))
        self.opener.open(episode)
        self.assertEqual([("episode list", episode)], self.opened)


class EpisodeWithoutShowTest(KodiTestCase):
    """
    The Play screen asks an episode for related shows, genres and cast, all of which go through its show. A recording
    in progress has no show in the library yet; it must come back empty instead of crashing the screen
    (IndexError in Episode.show).
    """

    def setUp(self):
        super(EpisodeWithoutShowTest, self).setUp()
        ensure_plex_interface()
        from plexnet import plexobjects

        class NoShowServer(FakeServer):
            def query(self, path, **kwargs):
                raise AssertionError("asked the server for {0}".format(path))

        # what /library/metadata/<ratingKey> returns for the recording: no grandparentKey
        elem = ET.fromstring(library_lookup()).find("Video")
        self.episode = plexobjects.buildItem(NoShowServer(), elem, "/library/metadata/482133")

    def test_no_show(self):
        self.assertIsNone(self.episode.show())

    def test_no_related_items(self):
        self.assertEqual(0, self.episode.relatedCount)

    def test_no_genres_or_cast(self):
        self.assertEqual([], list(self.episode.genres()))
        self.assertEqual([], list(self.episode.roles()))

    def test_playback_settings_without_a_show(self):
        """The player's seek bar reads binge/auto-skip settings from the show; with none it crashed on start."""
        from plexnet import util as pnUtil
        asked = []
        original = pnUtil.INTERFACE.playbackManager
        pnUtil.INTERFACE.playbackManager = lambda obj, **kw: asked.append(obj) or "item settings"
        try:
            self.assertEqual("item settings", self.episode.playbackSettings)
        finally:
            pnUtil.INTERFACE.playbackManager = original
        self.assertEqual([self.episode], asked)

    def test_live_item_is_a_full_object(self):
        """
        Its key is the live session, not the /library/metadata/ path it was loaded from, so it never counted as a
        full object: directors/writers stayed unset and the Play screen crashed calling directors().
        """
        self.assertNotEqual(self.episode.initpath, self.episode.key)
        self.assertEqual([], list(self.episode.directors()))
        self.assertEqual([], list(self.episode.writers()))


DVRS = """<MediaContainer size="2">
  <Dvr key="7" uuid="a"><Device key="1"><ChannelMapping channelKey="lineup-other" enabled="1"/></Device></Dvr>
  <Dvr key="14" uuid="b"><Device key="13"><ChannelMapping channelKey="lineup-fox" enabled="1"/></Device></Dvr>
</MediaContainer>"""

TUNED = """<MediaContainer size="1"><MediaSubscription key="1812"><MediaGrabOperation status="inprogress">
  <Video ratingKey="482133" key="/livetv/sessions/00000000-0000-4000-8000-000000000001" type="episode"/>
</MediaGrabOperation></MediaSubscription></MediaContainer>"""


class TuneServer(object):
    """Answers the DVR list and the tune POST; records (method, path, params)."""

    def __init__(self, dvrs=DVRS, tuned=TUNED, error=None):
        self.dvrs, self.tuned, self.error = dvrs, tuned, error
        self.calls = []

    def query(self, path, method=None, **kwargs):
        self.calls.append((method or "get", path, kwargs.get("params")))
        if self.error:
            raise self.error
        if path == "/livetv/dvrs":
            return ET.fromstring(self.dvrs)
        return ET.fromstring(self.tuned)


class TuneTest(KodiTestCase):
    """
    Plex Web tunes the recording's channel before asking for the stream: the tune creates this viewer's consumer
    on the live session the recording fills. Without it the transcoder's input 404s and the session never starts.
    """

    def test_dvr_is_the_one_carrying_the_channel(self):
        self.assertEqual("14", dvr.dvrIdForChannel(TuneServer(), "lineup-fox"))

    def test_single_dvr_is_used_when_no_mapping_matches(self):
        one = '<MediaContainer size="1"><Dvr key="3"/></MediaContainer>'
        self.assertEqual("3", dvr.dvrIdForChannel(TuneServer(dvrs=one), "lineup-unknown"))

    def test_tune_posts_with_the_session_identifier(self):
        server = TuneServer()
        key = dvr.tune(server, "lineup-fox", "sess-1")
        self.assertEqual(("post", "/livetv/dvrs/14/channels/lineup-fox/tune", {"X-Plex-Session-Identifier": "sess-1"}),
                         server.calls[-1])
        self.assertEqual("/livetv/sessions/00000000-0000-4000-8000-000000000001", key)

    def test_tune_failure_is_none_not_a_crash(self):
        self.assertIsNone(dvr.tune(TuneServer(error=IOError("timeout")), "lineup-fox", "sess-1"))
        self.assertIsNone(dvr.tune(TuneServer(), "", "sess-1"))


class LiveRecordingDetectionTest(KodiTestCase):
    def setUp(self):
        super(LiveRecordingDetectionTest, self).setUp()
        ensure_plex_interface()

    def build(self, attrs):
        from plexnet import plexobjects
        elem = ET.Element("Video", dict(type="episode", ratingKey="1", **attrs))
        return plexobjects.buildItem(None, elem, "/library/metadata/1")

    def test_library_item_of_a_recording_in_progress(self):
        self.assertTrue(dvr.isLiveRecording(self.build({"key": "/livetv/sessions/x", "live": "1"})))

    def test_ordinary_episode_is_not(self):
        self.assertFalse(dvr.isLiveRecording(self.build({"key": "/library/metadata/1"})))
        self.assertFalse(dvr.isLiveRecording(None))


class LiveRecordingStreamTest(KodiTestCase):
    """PlexPlayer.buildTranscode for a recording in progress mirrors Plex Web: tune, relative live path, HLS, offset 0."""

    def setUp(self):
        super(LiveRecordingStreamTest, self).setUp()
        ensure_plex_interface()
        from plexnet import plexplayer, util as pnUtil
        from six.moves.urllib.parse import urlsplit, parse_qs
        self.split = lambda url: (urlsplit(url).path, {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()})

        server = TuneServer()
        server.TYPE = "PLEXSERVER"
        server.supportsFeature = lambda name: True
        server.isLocalConnection = lambda: True
        server.buildUrl = lambda path, includeToken=False: "http://pms:32400" + path
        self.server = server

        class Settings(object):
            maxVerticalDPRes = 1080

            def getPreference(self, name, default=None):
                return default

            def getGlobal(self, name, default=None):
                return {"clientIdentifier": "client-1", "transcodeVideoBitrates": ["20000"],
                        "transcodeVideoResolutions": [(1920, 1080)], "supports1080p60": True}.get(name, default)

            def getQualityIndex(self, qualityType):
                return 0

            def supportsAudioStream(self, codec, channels):
                return False

        class Item(object):
            settings = Settings()
            key = "/livetv/sessions/00000000-0000-4000-8000-000000000001"

            def get(self, name, default=""):
                return {"live": "1", "key": self.key}.get(name, default)

            def getServer(self):
                return server

            def getAbsolutePath(self, attr):
                return "http://pms:32400" + self.key

            def getQualityType(self, server):
                return 0

        class Part(object):
            duration = pnUtil.AttributeDict(asInt=lambda: 0)

        class Media(object):
            mediaIndex = None
            parts = [Part()]
            channelIdentifier = "lineup-fox"

        class Choice(object):
            SUBTITLES_SOFT_ANY = 1
            subtitleDecision = 1
            subtitleStream = None

        self.player = plexplayer.PlexPlayer.__new__(plexplayer.PlexPlayer)
        self.player.item, self.player.media, self.player.choice = Item(), Media(), Choice()
        self.player.seekValue, self.player.sessionID = 0, "sess-1"
        self.obj = self.player.buildTranscode(server, pnUtil.AttributeDict(), 0, True, True, features=[])

    def test_tunes_the_channel_with_the_playback_session(self):
        self.assertIn(("post", "/livetv/dvrs/14/channels/lineup-fox/tune", {"X-Plex-Session-Identifier": "sess-1"}),
                      self.server.calls)

    def test_streams_hls_from_the_start_of_the_live_session(self):
        path, q = self.split(self.obj.streamUrls[0])
        self.assertEqual("/video/:/transcode/universal/start.m3u8", path)
        self.assertEqual("hls", q["protocol"])
        self.assertEqual("/livetv/sessions/00000000-0000-4000-8000-000000000001", q["path"])
        self.assertEqual("0", q["offset"])
        self.assertEqual("sess-1", q["X-Plex-Session-Identifier"])
        self.assertEqual("hls", self.obj.streamFormat)

    def test_profile_allows_an_hls_conversion(self):
        """The add-on's Generic profile alone gets "Neither direct play nor conversion is available" for a live session."""
        path, q = self.split(self.obj.streamUrls[0])
        self.assertIn(dvr.LIVE_HLS_TARGET, q["X-Plex-Client-Profile-Extra"])
