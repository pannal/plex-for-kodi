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


class FakeServer(object):
    """Answers query() from a canned response and records what was asked."""

    def __init__(self, xml=None, error=None):
        self.xml = xml
        self.error = error
        self.queries = []

    def query(self, path, **kwargs):
        self.queries.append(path)
        if self.error:
            raise self.error
        return ET.fromstring(self.xml) if self.xml is not None else None


def scheduled():
    return fixture("plexnet", "subscriptions_scheduled.xml")


class ActiveRecordingsTest(KodiTestCase):
    def setUp(self):
        super(ActiveRecordingsTest, self).setUp()
        ensure_plex_interface()

    def test_queries_the_scheduled_recordings_endpoint(self):
        server = FakeServer(scheduled())
        dvr.activeRecordings(server)
        self.assertEqual([dvr.SCHEDULED_PATH], server.queries)

    def test_lists_only_recordings_in_progress_with_a_library_item(self):
        recordings = dvr.activeRecordings(FakeServer(scheduled()))
        self.assertEqual(["77"], [r.id for r in recordings])

    def test_every_playable_recording_is_listed_so_one_can_be_picked(self):
        """Two games recording at once -> two cards in the row, in the server's order."""
        root = ET.fromstring(scheduled())
        second = ET.fromstring(ET.tostring(root.find("MediaGrabOperation")))
        second.set("id", "80")
        video = second.find("Video")
        video.set("ratingKey", "5601")
        video.set("key", "/library/metadata/5601")
        video.set("title", "Cowboys at Giants")
        root.append(second)
        recordings = dvr.activeRecordings(FakeServer(ET.tostring(root)))
        self.assertEqual(["Bears at Packers", "Cowboys at Giants"], [r.item.title for r in recordings])
        self.assertEqual(2, dvr.recordingsHub(FakeServer(ET.tostring(root))).size.asInt())

    def test_recording_carries_its_library_item(self):
        rec = dvr.activeRecordings(FakeServer(scheduled()))[0]
        self.assertEqual("episode", rec.item.type)
        self.assertEqual("Bears at Packers", rec.item.title)
        self.assertEqual("/library/metadata/5501", rec.item.key)

    def test_recording_progress_fields(self):
        rec = dvr.activeRecordings(FakeServer(scheduled()))[0]
        self.assertEqual(37.5, rec.percent)
        self.assertEqual(2147483648, rec.currentSize)
        self.assertTrue(rec.isRecording)

    def test_no_dvr_or_empty_response_is_an_empty_list(self):
        self.assertEqual([], dvr.activeRecordings(FakeServer(None)))
        self.assertEqual([], dvr.activeRecordings(FakeServer('<MediaContainer size="0"/>')))

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
        self.assertEqual(["Bears at Packers"], [i.title for i in hub.items])
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
        self.assertEqual(["Bears at Packers"], [i.title for i in hub.extend(0, 10)])


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
