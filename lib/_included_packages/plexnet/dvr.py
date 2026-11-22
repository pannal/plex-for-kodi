# coding=utf-8
"""
DVR recordings that are still being recorded.

Recordings only, not live TV: the server's scheduled-recordings list says which
grabs are in progress, each wrapping the item being recorded. On a real server
that item only carries EPG keys (/tv.plex.providers.epg.cloud.../metadata/...).
The library item for the growing recording is found by looking the item's guid
up in /library/all; the card keeps the guide's title, artwork, summary and
scheduled length, but points at the library item so it can be played.

isLiveHls finishes the stub plexplayer.PlexPlayer.isLiveHls carried over from
the Roku client: an HLS media playlist without EXT-X-ENDLIST is still growing.
"""
from __future__ import absolute_import

import time
from xml.etree import ElementTree

from six.moves.urllib.parse import quote, urljoin

from . import exceptions
from . import plexlibrary
from . import plexobjects
from . import util

SCHEDULED_PATH = '/media/subscriptions/scheduled'
HUB_IDENTIFIER = 'home.VIRTUAL.recordings.inprogress'
HUB_TITLE = 'Recording Now'

STATUS_IN_PROGRESS = 'inprogress'
LIBRARY_KEY_PREFIX = '/library/metadata/'
LIBRARY_LOOKUP_PATH = '/library/all'
LIVE_SESSIONS_PATH = '/livetv/sessions'

# Show/season links in the guide data point at the EPG provider, not the library.
GUIDE_PARENT_ATTRS = ('grandparentKey', 'grandparentRatingKey', 'parentKey', 'parentRatingKey')


IN_PROGRESS_FLAG = 'dvrInProgress'


def isInProgressRecording(item):
    """
    Was this item built for "Recording Now"? Read from __dict__: PlexObject.__getattr__ invents an empty value for
    any attribute asked of it, and the flag must survive the reload the Play screen does.
    """
    return bool(item is not None and item.__dict__.get(IN_PROGRESS_FLAG))


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


def _libraryRatingKey(server, guid):
    """The library ratingKey of the item the server is recording under this guid, or None."""
    if not guid:
        return None
    try:
        data = server.query(LIBRARY_LOOKUP_PATH, params={'guid': guid})
    except Exception as e:
        util.DEBUG_LOG('DVR: library lookup for {0} failed: {1}', guid, e)
        return None
    if data is None:
        return None
    for elem in data:
        if elem.attrib.get('ratingKey'):
            return elem.attrib['ratingKey']
    return None


def _liveSessionRatingKey(server, channelIdentifier):
    """
    The library ratingKey of the live session recording this channel. Past its scheduled slot (recording padding)
    the session's item takes the next program's guid, so the guid lookup no longer finds it.
    """
    if not channelIdentifier:
        return None
    try:
        data = server.query(LIVE_SESSIONS_PATH)
    except Exception as e:
        util.DEBUG_LOG('DVR: live sessions lookup failed: {0}', e)
        return None
    if data is None:
        return None
    for video in data.iter('Video'):
        media = video.find('Media')
        if media is not None and media.attrib.get('channelIdentifier') == channelIdentifier:
            return video.attrib.get('ratingKey')
    return None


def _toLibraryElem(server, op, elem):
    """
    The grab's item as a library element, or None when the library has no item for it yet.
    Guide details stay; ratingKey/key point at the library, and EPG show/season links are dropped.
    """
    if elem.attrib.get('key', '').startswith(LIBRARY_KEY_PREFIX):
        return elem

    ratingKey = _libraryRatingKey(server, elem.attrib.get('guid'))
    if not ratingKey:
        media = elem.find('Media')
        ratingKey = _liveSessionRatingKey(server, media.attrib.get('channelIdentifier') if media is not None else None)
    if not ratingKey:
        util.DEBUG_LOG('DVR: recording {0} has no library item yet ({1})', op.attrib.get('id'),
                       elem.attrib.get('guid'))
        return None

    elem.set('ratingKey', ratingKey)
    elem.set('key', LIBRARY_KEY_PREFIX + ratingKey)
    for attr in GUIDE_PARENT_ATTRS:
        elem.attrib.pop(attr, None)
    # The guide dates items "YYYY-MM-DD HH:MM:SS"; library code parses "YYYY-MM-DD".
    aired = elem.attrib.get('originallyAvailableAt')
    if aired:
        elem.set('originallyAvailableAt', aired.split(' ')[0])
    return elem


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

        elem = _toLibraryElem(server, op, elem)
        if elem is None:
            continue

        try:
            item = plexobjects.buildItem(server, elem, SCHEDULED_PATH, container=container, tag_fallback=True,
                                         not_cachable=True)
        except exceptions.UnknownType:
            continue

        item.__dict__[IN_PROGRESS_FLAG] = True
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


LIVE_SESSION_PREFIX = '/livetv/sessions/'
DVRS_PATH = '/livetv/dvrs'
TUNE_PATH = '/livetv/dvrs/{0}/channels/{1}/tune'
# The Generic client profile gets "Neither direct play nor conversion is available" for a live session; allow HLS.
# Seeking stops this far before the end of what is recorded so far.
LIVE_EDGE_MARGIN = 30


def now():
    return int(time.time())


class TunedRecording(object):
    """What tuning a recording in progress tells: its live session, scheduled length (ms) and start (epoch s)."""

    def __init__(self, key, duration, beginsAt, available=None):
        self.key = key
        self.duration = duration
        self.beginsAt = beginsAt
        self.available = available  # seconds recorded, as the server reported at tune time

    def recordedSeconds(self, now=None):
        """How much is recorded so far: what the server reports, else the clock (capped at the scheduled length)."""
        if self.available is not None:
            return int(self.available)
        if not self.beginsAt:
            return None
        elapsed = max(0, (now if now is not None else globals()['now']()) - self.beginsAt)
        if self.duration:
            elapsed = min(elapsed, self.duration // 1000)
        return elapsed

    def seekableOffset(self, offset, now=None):
        """offset (s) capped LIVE_EDGE_MARGIN before the recorded edge."""
        recorded = self.recordedSeconds(now)
        if recorded is None:
            return offset
        return max(0, min(offset, recorded - LIVE_EDGE_MARGIN))


LIVE_HLS_TARGET = ('add-transcode-target(type=videoProfile&context=streaming&protocol=hls&container=mpegts&'
                   'videoCodec=h264&audioCodec=aac,ac3)')


def isLiveRecording(item):
    """A library item still being recorded: keyed by its live session (live="1") instead of a file."""
    if item is None:
        return False
    # key is an attribute of the object, not in its attribs (item.get('key') is empty)
    return item.get('live') == '1' and str(getattr(item, 'key', '') or '').startswith(LIVE_SESSION_PREFIX)


def dvrIdForChannel(server, channelIdentifier):
    """The DVR whose lineup carries this channel; the only DVR when no mapping matches."""
    data = server.query(DVRS_PATH)
    if data is None:
        return None
    dvrs = data.findall('Dvr')
    for d in dvrs:
        for mapping in d.iter('ChannelMapping'):
            if mapping.attrib.get('channelKey') == channelIdentifier:
                return d.attrib.get('key')
    if len(dvrs) == 1:
        return dvrs[0].attrib.get('key')
    return None


def tune(server, channelIdentifier, sessionIdentifier):
    """
    Join the live session a recording in progress is filling, as this playback session (what Plex Web does before
    asking for the stream). Creates this viewer's consumer on the session; without it the transcoder's input 404s.
    Returns a TunedRecording, or None.
    """
    if not channelIdentifier:
        return None
    try:
        dvrId = dvrIdForChannel(server, channelIdentifier)
        if not dvrId:
            util.WARN_LOG('DVR: no DVR carries channel {0}', channelIdentifier)
            return None
        data = server.query(TUNE_PATH.format(dvrId, quote(channelIdentifier, safe='')), method='post',
                            params={'X-Plex-Session-Identifier': sessionIdentifier})
    except Exception as e:
        util.WARN_LOG('DVR: tuning channel {0} failed: {1}', channelIdentifier, e)
        return None
    if data is None:
        return None
    for video in data.iter('Video'):
        key = video.attrib.get('key', '')
        if key.startswith(LIVE_SESSION_PREFIX):
            media = video.find('Media')
            attrs = media.attrib if media is not None else {}
            duration = plexobjects.PlexValue(video.attrib.get('duration') or attrs.get('duration', '')).asInt()
            beginsAt = plexobjects.PlexValue(attrs.get('beginsAt', '')).asInt()
            return TunedRecording(key, duration, beginsAt, available=recordedAvailable(server, key))
    return None


def recordedAvailable(server, liveKey):
    """Seconds recorded so far: the live session's maxOffsetAvailable (counted from the recording's start)."""
    try:
        data = server.query(liveKey)
    except Exception as e:
        util.DEBUG_LOG('DVR: could not read live session {0}: {1}', liveKey, e)
        return None
    if data is None:
        return None
    for ts in data.iter('TranscodeSession'):
        value = ts.attrib.get('maxOffsetAvailable')
        if value:
            try:
                return float(value)
            except ValueError:
                return None
    return None


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
