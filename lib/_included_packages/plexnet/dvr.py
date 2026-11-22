# coding=utf-8
"""
DVR recordings that are still being recorded.

Recordings only, not live TV: the server's scheduled-recordings list says which
grabs are in progress, each wrapping the item being recorded. An item that is
already in the library (a /library/metadata/ key) can be played from the start
while the recording keeps growing; one that still only has an EPG key cannot.

isLiveHls finishes the stub plexplayer.PlexPlayer.isLiveHls carried over from
the Roku client: an HLS media playlist without EXT-X-ENDLIST is still growing.
"""
from __future__ import absolute_import

from xml.etree import ElementTree

from six.moves.urllib.parse import urljoin

from . import exceptions
from . import plexlibrary
from . import plexobjects
from . import util

SCHEDULED_PATH = '/media/subscriptions/scheduled'
HUB_IDENTIFIER = 'home.VIRTUAL.recordings.inprogress'
HUB_TITLE = 'Recording Now'

STATUS_IN_PROGRESS = 'inprogress'
LIBRARY_KEY_PREFIX = '/library/metadata/'


class ActiveRecording(object):
    """One grab operation the server is recording right now, and its library item."""

    def __init__(self, elem, item):
        attrib = elem.attrib
        self.id = attrib.get('id')
        self.status = attrib.get('status')
        self.subscriptionId = attrib.get('mediaSubscriptionID')
        self.percent = plexobjects.PlexValue(attrib.get('percent', '')).asFloat()
        self.currentSize = plexobjects.PlexValue(attrib.get('currentSize', '')).asInt()
        self.item = item

    @property
    def isRecording(self):
        return self.status == STATUS_IN_PROGRESS

    def __repr__(self):
        return '<ActiveRecording:{0}:{1}>'.format(self.id, self.item and self.item.title)


def _query(server):
    try:
        return server.query(SCHEDULED_PATH)
    except Exception as e:
        # No DVR, not the owner, or the server is unreachable: Home must load anyway.
        util.DEBUG_LOG('DVR: no scheduled recordings from {0}: {1}', server, e)
        return None


def _parse(server, data):
    recordings = []
    if data is None:
        return recordings

    container = plexobjects.PlexContainer(data, SCHEDULED_PATH, server, SCHEDULED_PATH)
    for op in data.findall('MediaGrabOperation'):
        if op.attrib.get('status') != STATUS_IN_PROGRESS:
            continue

        elem = next(iter(op), None)
        if elem is None:
            continue

        if not elem.attrib.get('key', '').startswith(LIBRARY_KEY_PREFIX):
            util.DEBUG_LOG('DVR: recording {0} has no library item yet ({1})', op.attrib.get('id'),
                           elem.attrib.get('key'))
            continue

        try:
            item = plexobjects.buildItem(server, elem, SCHEDULED_PATH, container=container, tag_fallback=True,
                                         not_cachable=True)
        except exceptions.UnknownType:
            continue

        recordings.append(ActiveRecording(op, item))
    return recordings


def activeRecordings(server):
    """What the server is recording right now and can already be played, newest grab first as the server orders them."""
    return _parse(server, _query(server))


class RecordingsHub(plexlibrary.Hub):
    """The "Recording now" row on Home. Rebuilt from the scheduled list rather than a /hubs key."""

    def __init__(self, server, recordings):
        elem = ElementTree.Element('Hub', {
            'hubIdentifier': HUB_IDENTIFIER,
            'title': HUB_TITLE,
            'type': 'mixed',
            'key': SCHEDULED_PATH,
        })
        super(RecordingsHub, self).__init__(elem, server=server)
        self._fill(recordings)

    def _fill(self, recordings):
        self.items = [r.item for r in recordings]
        self._totalSize = len(self.items)
        self.set('size', len(self.items))
        self.set('offset', 0)
        self.set('more', '')

    def reload(self, **kwargs):
        self._fill(activeRecordings(self.server))

    def extend(self, start=None, size=None, **kwargs):
        self.reload()
        return self.items

    @property
    def totalSize(self):
        return self._totalSize


def recordingsHub(server):
    """A RecordingsHub when something playable is recording, else None (no empty row on Home)."""
    recordings = activeRecordings(server)
    if not recordings:
        return None
    return RecordingsHub(server, recordings)


def _text(body):
    if isinstance(body, bytes):
        return body.decode('utf8', 'replace')
    return body or ''


def isGrowingHlsPlaylist(body):
    """A media playlist still being appended to: HLS, has segments, no EXT-X-ENDLIST. A master playlist cannot say."""
    text = _text(body).strip()
    if not text.startswith('#EXTM3U'):
        return False
    if '#EXT-X-STREAM-INF' in text:
        return False
    return '#EXT-X-ENDLIST' not in text


def firstVariantUrl(body, base_url):
    """The first media playlist a master playlist points to, resolved against the master's URL."""
    lines = _text(body).splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXT-X-STREAM-INF'):
            for uri in lines[i + 1:]:
                uri = uri.strip()
                if uri and not uri.startswith('#'):
                    return urljoin(base_url, uri)
    return None


def isLiveHls(url, fetch):
    """
    Is the HLS stream at url still growing? fetch(url) returns the playlist text.
    A master playlist is followed to its first variant. Any failure reads as not live, so playback falls back to the
    normal fixed-length behaviour.
    """
    try:
        body = fetch(url)
        variant = firstVariantUrl(body, url)
        if variant:
            body = fetch(variant)
        return isGrowingHlsPlaylist(body)
    except Exception as e:
        util.DEBUG_LOG('DVR: could not inspect HLS playlist {0}: {1}', util.cleanToken(url), e)
        return False
