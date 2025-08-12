from __future__ import absolute_import
from . import plexobjects
from . import plexstream
from . import util
from . import exceptions

METADATA_RELATED_TRAILER = 1
METADATA_RELATED_DELETED_SCENE = 2
METADATA_RELATED_INTERVIEW = 3
METADATA_RELATED_MUSIC_VIDEO = 4
METADATA_RELATED_BEHIND_THE_SCENES = 5
METADATA_RELATED_SCENE_OR_SAMPLE = 6
METADATA_RELATED_LIVE_MUSIC_VIDEO = 7
METADATA_RELATED_LYRIC_MUSIC_VIDEO = 8
METADATA_RELATED_CONCERT = 9
METADATA_RELATED_FEATURETTE = 10
METADATA_RELATED_SHORT = 11
METADATA_RELATED_OTHER = 12


class MediaItem(plexobjects.PlexObject):
    def __eq__(self, other):
        return self.ratingKey == other.ratingKey

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.ratingKey)

    def getIdentifier(self):
        identifier = self.get('identifier') or None

        if identifier is None:
            try:
                identifier = self.container.identifier
            except AttributeError:
                util.DEBUG_LOG("Couldn't get media identifier for {}", self)
                pass

        # HACK
        # PMS doesn't return an identifier for playlist items. If we haven't found
        # an identifier and the key looks like a library item, then we pretend like
        # the identifier was set.
        #
        if identifier is None:  # Modified from Roku code which had no check for None with iPhoto - is that right?
            if self.key.startswith('/library/metadata'):
                identifier = "com.plexapp.plugins.library"
            elif self.isIPhoto():
                identifier = "com.plexapp.plugins.iphoto"

        return identifier

    def getQualityType(self, server=None):
        if self.isOnlineItem():
            return util.QUALITY_ONLINE

        if not server:
            server = self.getServer()

        return util.QUALITY_LOCAL if server.isLocalConnection() else util.QUALITY_REMOTE

    def delete(self):
        if not self.ratingKey:
            return

        from . import plexrequest
        req = plexrequest.PlexRequest(self.server, '/library/metadata/{0}'.format(self.ratingKey), method='DELETE')
        req.getToStringWithTimeout(10)
        self.deleted = req.wasOK()
        return self.deleted

    def exists(self, force_full_check=False):
        if (self.deleted or self.deletedAt) and not force_full_check:
            return False

        # force_full_check is imperfect, as it doesn't check for existence of its mediaparts
        try:
            data = self.server.query('/library/metadata/{0}'.format(self.ratingKey))
        except exceptions.BadRequest:
            # item does not exist anymore
            util.DEBUG_LOG("Item {} doesn't exist.", self.ratingKey)
            return False
        return data is not None and data.attrib.get('size') != '0'

    def relatedHubs(self, data, _itemCls, hubIdentifiers=None, _filter=None):
        hubs = data.find("Related")
        if _filter is None and hubIdentifiers is None:
            raise NotImplemented

        _f = lambda x: x
        if _filter is not None:
            _f = _filter
        if hubIdentifiers is not None:
            hubIds = hubIdentifiers
            if not isinstance(hubIds, (list, set, tuple)):
                hubIds = [hubIds]
            _f = lambda x: x.attrib.get("hubIdentifier", None) in hubIds

        results = []
        if hubs is not None:
            for hub in hubs:
                if hub.attrib.get("size", 0) and _f(hub):
                    results += list(plexobjects.PlexItemList(hub, _itemCls, 'Directory', server=self.server,
                                                             container=self))
        return results

    def fixedDuration(self):
        duration = self.duration.asInt()
        if duration < 1000:
            duration *= 60000
        return duration


class Media(plexobjects.PlexObject):
    TYPE = 'Media'

    def __init__(self, data, initpath=None, server=None, video=None):
        plexobjects.PlexObject.__init__(self, data, initpath=initpath, server=server)
        self.video = video
        self.parts = [MediaPart(elem, initpath=self.initpath, server=self.server, media=self) for elem in data]

    def __repr__(self):
        title = self.video.title.replace(' ', '.')[0:20]
        return '<%s:%s>' % (self.__class__.__name__, title.encode('utf8'))


class MediaPart(plexobjects.PlexObject):
    TYPE = 'Part'

    def __init__(self, data, initpath=None, server=None, media=None):
        plexobjects.PlexObject.__init__(self, data, initpath=initpath, server=server)
        self.media = media
        self.streams = [MediaPartStream.parse(e, initpath=self.initpath, server=server, part=self) for e in data if e.tag == 'Stream']

    def __repr__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.id)

    def selectedStream(self, stream_type):
        streams = [x for x in self.streams if stream_type == x.type]
        selected = list([x for x in streams if x.selected is True])
        if len(selected) == 0:
            return None
        return selected[0]


class MediaPartStream(plexstream.PlexStream):
    TYPE = None
    STREAMTYPE = None

    def __init__(self, data, initpath=None, server=None, part=None):
        plexobjects.PlexObject.__init__(self, data, initpath, server)
        self.part = part

    @staticmethod
    def parse(data, initpath=None, server=None, part=None):
        STREAMCLS = {
            1: VideoStream,
            2: AudioStream,
            3: SubtitleStream
        }
        stype = int(data.attrib.get('streamType'))
        cls = STREAMCLS.get(stype, MediaPartStream)
        return cls(data, initpath=initpath, server=server, part=part)

    @staticmethod
    def rebuild(s):
        return MediaPartStream.parse(s.data, initpath=s.initpath, server=s.server, part=s.part)

    def __repr__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.id)


class VideoStream(MediaPartStream):
    TYPE = 'videostream'
    STREAMTYPE = plexstream.PlexStream.TYPE_VIDEO


class AudioStream(MediaPartStream):
    TYPE = 'audiostream'
    STREAMTYPE = plexstream.PlexStream.TYPE_AUDIO


class SubtitleStream(MediaPartStream):
    TYPE = 'subtitlestream'
    STREAMTYPE = plexstream.PlexStream.TYPE_SUBTITLE

    def __init__(self, data, initpath=None, server=None, part=None):
        super(MediaPartStream, self).__init__(data, initpath=initpath, server=server, part=part)
        self._should_auto_sync = self.canAutoSync.asBool() and util.INTERFACE.getPreference('auto_sync', True)

    @property
    def should_auto_sync(self):
        return self._should_auto_sync

    @should_auto_sync.setter
    def should_auto_sync(self, value):
        self._should_auto_sync = value


class TranscodeSession(plexobjects.PlexObject):
    TYPE = 'TranscodeSession'


class MediaTag(plexobjects.PlexObject):
    TYPE = None
    ID = 'None'
    virtual = False

    def __repr__(self):
        tag = self.tag.replace(' ', '.')[0:20]
        return '<%s:%s:%s:%s>' % (self.__class__.__name__, self.id, tag, self.virtual)

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False

        return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)


class Collection(MediaTag):
    TYPE = 'Collection'
    FILTER = 'collection'


class Location(MediaTag):
    TYPE = 'Location'
    FILTER = 'location'


class Country(MediaTag):
    TYPE = 'Country'
    FILTER = 'country'


class Genre(MediaTag):
    TYPE = 'Genre'
    FILTER = 'genre'
    ID = '1'


class Mood(MediaTag):
    TYPE = 'Mood'
    FILTER = 'mood'



class Role(MediaTag):
    TYPE = 'Role'
    FILTER = 'actor'
    ID = '6'
    translated_role = ''

    def sectionRoles(self):
        hubs = self.server.hubs(count=10, search_query=self.tag)
        for hub in hubs:
            if hub.type == self.FILTER:
                break
        else:
            return None

        roles = []

        for actor in hub.items:
            if actor.id == self.id:
                roles.append(actor)

        return roles or None


class Similar(MediaTag):
    TYPE = 'Similar'
    FILTER = 'similar'


class Director(Role):
    TYPE = 'Director'
    FILTER = 'director'
    ID = '4'
    translated_role = 'Director'


class Producer(Role):
    TYPE = 'Producer'
    FILTER = 'producer'
    translated_role = 'Producer'


class Writer(Role):
    TYPE = 'Writer'
    FILTER = 'writer'
    translated_role = 'Writer'


class Guid(MediaTag):
    TYPE = 'Guid'
    FILTER = 'guid'


class Chapter(MediaTag):
    TYPE = 'Chapter'
    
    def startTime(self):
        return self.get('startTimeOffset', -1).asInt()


class Bandwidth(plexobjects.PlexObject):
    TYPE = 'Bandwidth'


class Marker(MediaTag):
    TYPE = 'Marker'
    FILTER = 'Marker'

    def __repr__(self):
        return '<%s:%s:%s:%s>' % (self.__class__.__name__, self.id, self.type, self.final and "final" or "")


class Review(MediaTag):
    TYPE = 'Review'
    FILTER = 'Review'

    def ratingImage(self):
        # only rottentomatoes currently supported
        img = str(self.image)
        if not img or not img.startswith("rottentomatoes://"):
            return ''

        return img.split('rottentomatoes://')[1]


class Studio(MediaTag):
    TYPE = 'Studio'
    FILTER = 'Studio'


class RelatedMixin(object):
    _relatedCount = None
    related_source = "similar"

    @property
    def relatedCount(self):
        if self._relatedCount is None:
            related = self.getRelated(0, 0 if self.related_source == "similar" else 36)
            if related is not None:
                self._relatedCount = related.totalSize
            else:
                self._relatedCount = 0

        return self._relatedCount

    @property
    def related(self):
        return self.getRelated(0, 8)

    def getRelated(self, offset=None, limit=None, _max=36):
        path = '/library/metadata/{}/{}'.format(self.ratingKey, self.related_source)
        try:
            return plexobjects.listItems(self.server, path, offset=offset, limit=limit, params={"count": _max},
                                         cachable=self.cachable, cache_ref=self.cacheRef, not_cachable=self._not_cachable)
        except exceptions.BadRequest:
            util.DEBUG_LOG("Invalid related items response returned for {}", self)
            return None
