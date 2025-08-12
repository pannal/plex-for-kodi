from __future__ import absolute_import
from datetime import datetime

from . import exceptions
from . import util
import json
import six
import time

# Search Types - Plex uses these to filter specific media types when searching.
SEARCHTYPES = {
    'movie': 1,
    'show': 2,
    'season': 3,
    'episode': 4,
    'artist': 8,
    'album': 9,
    'track': 10,
    'collection': 18,
    'movies_shows': 99,
}

LIBRARY_TYPES = {}


def registerLibType(cls):
    LIBRARY_TYPES[cls.TYPE] = cls
    return cls


def registerLibFactory(ftype):
    def wrap(func):
        LIBRARY_TYPES[ftype] = func
        return func
    return wrap


class PlexValue(six.text_type):
    __slots__ = ("parent", "NA")

    def __new__(cls, value, parent=None):
        self = super(PlexValue, cls).__new__(cls, value)
        self.parent = parent
        self.NA = False
        return self

    def __call__(self, default):
        return not self.NA and self or PlexValue(default, self.parent)

    def __copy__(self):
        return self.__deepcopy__()

    def __deepcopy__(self, memodict=None):
        return self.__class__(self)

    def __gt__(self, other):
        return self.asInt() > other

    def __lt__(self, other):
        return self.asInt() < other

    def asBool(self):
        return self == '1' or self == 'true'

    def asInt(self, default=0):
        return int(self or default)

    def asFloat(self, default=0):
        return float(self or default)

    def asDatetime(self, format_=None):
        if not self:
            return None

        if self.isdigit():
            dt = datetime.fromtimestamp(int(self))
        else:
            # dt = datetime.strptime(self, '%Y-%m-%d')
            # Avoid datetime.strptime to avoid
            # https://github.com/python/cpython/issues/71587
            try:
                dt = datetime.fromtimestamp(time.mktime(time.strptime(self, '%Y-%m-%d')))
            except OverflowError:
                # special case for dates before 1970-01-02 (yes, there are shows that old), mktime fails on those
                year, month, day = (int(p) for p in str(self).split("-"))
                dt = datetime(year=year, month=month, day=day)

        if not format_:
            return dt

        return dt.strftime(format_)

    def asURL(self, includeToken=False):
        return self.parent.server.buildUrl(self, includeToken)

    def asTranscodedImageURL(self, w, h, **extras):
        return self.parent.server.getImageTranscodeURL(self, w, h, **extras)


class JEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return json.JSONEncoder.default(self, o)
        except:
            return None


def asFullObject(func):
    def wrap(self, *args, **kwargs):
        if not self.isFullObject():
            self.reload()
        return func(self, *args, **kwargs)

    return wrap


class Checks(object):
    def isLibraryItem(self):
        return "/library/metadata" in self.get('key', '') or ("/playlists/" in self.get('key', '') and self.get("type", "") == "playlist")

    def isVideoItem(self):
        return False

    def isMusicItem(self):
        return False

    def isOnlineItem(self):
        return self.isChannelItem() or self.isMyPlexItem() or self.isVevoItem() or self.isIvaItem()

    def isMyPlexItem(self):
        try:
            return self.container.server.TYPE == 'MYPLEXSERVER' or self.container.identifier == 'com.plexapp.plugins.myplex'
        except AttributeError:
            return

    def isChannelItem(self):
        identifier = self.getIdentifier() or "com.plexapp.plugins.library"
        return not self.isLibraryItem() and not self.isMyPlexItem() and identifier != "com.plexapp.plugins.library"

    def isVevoItem(self):
        return 'vevo://' in self.get('guid')

    def isIvaItem(self):
        return 'iva://' in self.get('guid')

    def isGracenoteCollection(self):
        return False

    def isIPhoto(self):
        return (self.title == "iPhoto" or self.container.title == "iPhoto" or (self.mediaType == "Image" or self.mediaType == "Movie"))

    def isDirectory(self):
        return self.name == "Directory" or self.name == "Playlist"

    def isPhotoOrDirectoryItem(self):
        return self.type == "photoalbum"  # or self.isPhotoItem()

    def isMusicOrDirectoryItem(self):
        return self.type in ('artist', 'album', 'track')

    def isVideoOrDirectoryItem(self):
        return self.type in ('movie', 'show', 'episode')

    def isSettings(self):
        return False


class PlexObject(Checks):
    __slots__ = ("initpath", "key", "server", "container", "mediaChoice", "titleSort", "deleted", "_reloaded", "data",
                 "_not_cachable")
    TYPE = None
    cachable = False
    is_watchlist = False

    def __init__(self, data, initpath=None, server=None, container=None, **kwargs):
        self.initpath = initpath
        self.key = None
        self.server = server
        self.container = container
        self.mediaChoice = None
        self.titleSort = PlexValue('')
        self.deleted = False
        self._reloaded = False

        # items initialized by containers that shouldn't be cached get this special attribute set, which overrides
        # cachable
        self._not_cachable = kwargs.get('not_cachable', False)
        self.data = data

        if data is None:
            return

        self._setData(data)

        self.init(data)

    def _setData(self, data):
        if data is False:
            return

        self.name = data.tag
        for k, v in data.attrib.items():
            if k in ("container",):
                k = "attrib_%s" % k

            setattr(self, k, PlexValue(v, self))

    def __getattr__(self, attr):
        a = PlexValue('', self)
        a.NA = True

        try:
            setattr(self, attr, a)
        except AttributeError:
            util.LOG('Failed to set attribute: {0} ({1})', attr, self.__class__)

        return a

    def exists(self, *args, **kwargs):
        # Used for media items - for others we just return True
        return True

    def get(self, attr, default=''):
        ret = self.__dict__.get(attr, getattr(self, attr) if attr in self.__slots__ else None)
        return ret is not None and ret or PlexValue(default, self)

    def set(self, attr, value):
        setattr(self, attr, PlexValue(six.text_type(value), self))

    def init(self, data):
        pass

    @property
    def cacheRef(self):
        return self.getCacheRef()

    def getCacheRef(self, always_return=False):
        if (hasattr(self, "TYPE") and self.TYPE and self.get('ratingKey')
                and ('items' in util.INTERFACE.getPreference('cache_requests') or always_return)):
            return "_".join((self.TYPE, self.ratingKey))

    def _clearCache(self, cks, urls):
        if not urls:
            return

        if util.DEBUG_REQUESTS:
            util.DEBUG_LOG("Clearing cache for: {0}, {1}".format(self, urls))

        from .asyncadapter import Session
        s = Session()
        for url in urls:
            try:
                s.cache.delete_url(url)
            except Exception as e:
                util.LOG('Failed to delete cached URL {0}: {1}', url, e)

        # compact DB
        s.cache.vacuum()

        base = util.CACHED_PLEX_URLS.get(util.INTERFACE.getRCBaseKey(), {})

        # delete cache keys for collected urls
        for ck in cks:
            try:
                del base[ck]
            except:
                pass

    def clearCache(self, override_type=None, return_urls=False):
        # fixme: cache handling should be in a separate manager class
        _type = override_type or self.TYPE
        if self.cachable:
            # get cache key no matter what, even if the specific type isn't cached, we still want to clear the library
            # cache regardless
            ck = self.getCacheRef(always_return=True)
            urls = []
            if ck:
                base = util.CACHED_PLEX_URLS.get(util.INTERFACE.getRCBaseKey(), {})
                cks = []
                if base:
                    urls = base.get(ck, [])
                    cks.append(ck)

                    if _type in ("movie", "episode", "show", "season"):
                        # library cache
                        libID = self.getLibrarySectionId()
                        if libID:
                            urls += base.get("section_%s" % libID, [])
                            cks.append("section_%s" % libID)

                        # parents caches
                        if _type == "episode":
                            urls += base.get("season_%s" % self.parentRatingKey, [])
                            urls += base.get("show_%s" % self.grandparentRatingKey, [])
                            cks += ["season_%s" % self.parentRatingKey, "show_%s" % self.grandparentRatingKey]

                        if _type == "season":
                            urls += base.get("show_%s" % self.parentRatingKey, [])
                            cks.append("show_%s" % self.parentRatingKey)

                if return_urls:
                    return cks, urls

                self._clearCache(cks, urls)


    def isFullObject(self):
        return self.initpath is None or self.key is None or self.initpath == self.key

    def getAddress(self):
        return self.server.activeConnection.address

    @property
    def defaultTitle(self):
        return self.get('title')

    @property
    def defaultThumb(self):
        return self.__dict__.get('thumb') and self.thumb or PlexValue('', self)

    @property
    def defaultArt(self):
        return self.__dict__.get('art') and self.art or PlexValue('', self)

    def refresh(self):
        self.server.query('%s/refresh' % self.key, method="put")
        self.clearCache()

    def reload(self, _soft=False, **kwargs):
        """ Reload the data for this object from PlexServer XML. """
        if _soft and self._reloaded:
            return self

        try:
            if self.get('ratingKey'):
                data = self.server.query('/library/metadata/{0}'.format(self.ratingKey),
                                         cachable=self.cachable,
                                         cache_ref=self.cacheRef,
                                         params=kwargs)
            else:
                data = self.server.query(self.key, params=kwargs)
            self._reloaded = True
        except Exception as e:
            import traceback
            traceback.print_exc()
            util.ERROR(err=e)
            self.initpath = self.key
            return self

        self.initpath = self.key

        try:
            self._setData(data[0])
        except (IndexError, TypeError, AttributeError):
            util.DEBUG_LOG('No data on reload: {0}', self)
            return self

        return self

    def softReload(self, **kwargs):
        return self.reload(_soft=True, **kwargs)

    def getLibrarySectionId(self):
        ID = self.get('librarySectionID')

        if not ID:
            ID = self.container.get("librarySectionID", '')

        return ID

    def getLibrarySectionTitle(self):
        title = self.get('librarySectionTitle')

        if not title:
            title = self.container.get("librarySectionTitle", '')

        if not title:
            lsid = self.getLibrarySectionId()
            if lsid:
                data = self.server.query('/library/sections/{0}'.format(lsid))
                title = data.attrib.get('title1')
                if title:
                    self.librarySectionTitle = title
        return str(title)

    def getLibrarySectionType(self):
        type_ = self.get('librarySectionType')

        if not type_:
            type_ = self.container.get("librarySectionType", '')

        if not type_:
            lsid = self.getLibrarySectionId()
            if lsid:
                data = self.server.query('/library/sections/{0}'.format(lsid))
                type_ = data.attrib.get('type')
                if type_:
                    self.librarySectionTitle = type_
        return type_

    def getLibrarySectionUuid(self):
        uuid = self.get("uuid") or self.get("librarySectionUUID")

        if not uuid:
            uuid = self.container.get("librarySectionUUID", "")

        return uuid

    def _findLocation(self, data):
        elem = data.find('Location')
        if elem is not None:
            return elem.attrib.get('path')
        return None

    def _findPlayer(self, data):
        elem = data.find('Player')
        if elem is not None:
            return PlexObject(elem, server=self.server)
        return None

    def _findTranscodeSession(self, data):
        elem = data.find('TranscodeSession')
        if elem is not None:
            from . import media
            return media.TranscodeSession(elem, server=self.server)
        return None

    def _findBandwidths(self, data):
        elem = data.find("Bandwidths")
        if elem is not None:
            from . import media
            return PlexItemList(elem, media.Bandwidth, media.Bandwidth.TYPE, server=self.server)
        return []

    def _findUser(self, data):
        elem = data.find('User')
        if elem is not None:
            return PlexObject(elem, self.initpath)
        return None

    def _findSession(self, data):
        elem = data.find('Session')
        if elem is not None:
            return PlexObject(elem, self.initpath, server=self.server)
        return None

    def getAbsolutePath(self, attr):
        path = getattr(self, attr, None)
        if path is None:
            return None
        else:
            try:
                return self.container._getAbsolutePath(path)
            except AttributeError:
                try:
                    return self._getAbsolutePath(path)
                except AttributeError:
                    raise

    def _getAbsolutePath(self, path):
        if path.startswith('/'):
            return path
        elif "://" in path:
            return path
        else:
            return self.getAddress() + "/" + path

    def getParentPath(self, key):
        # Some containers have /children on its key while others (such as playlists) use /items
        path = self.getAbsolutePath(key)
        if path is None:
            return ""

        for suffix in ("/children", "/items"):
            path = path.replace(suffix, "")

        return path

    def getServer(self):
        return self.server

    def getTranscodeServer(self, localServerRequired=False, transcodeType=None):
        server = self.server

        # If the server is myPlex, try to use a different PMS for transcoding
        from . import myplexserver
        from . import plexapp
        if server == myplexserver.MyPlexServer:
            fallbackServer = plexapp.SERVERMANAGER.getChannelServer()

            if fallbackServer:
                server = fallbackServer
            elif localServerRequired:
                return None

        return server

    @classmethod
    def deSerialize(cls, jstring):
        from . import plexserver
        obj = json.loads(jstring)
        server = plexserver.PlexServer.deSerialize(obj['server'])
        server.identifier = None
        ad = util.AttributeDict()
        ad.attrib = obj['obj']
        ad.find = lambda x: None
        po = buildItem(server, ad, ad.initpath, container=server)

        return po

    def serialize(self, full=False):
        import json
        odict = {}
        if full:
            for k, v in self.__dict__.items():
                if k not in ('server', 'container', 'media', 'initpath', '_data') and v:
                    odict[k] = v
        else:
            odict['key'] = self.key
            odict['type'] = self.type

        odict['initpath'] = '/none'
        obj = {'obj': odict, 'server': self.server.serialize(full=full)}

        return json.dumps(obj, cls=JEncoder)


class PlexContainer(PlexObject):
    __slots__ = ("address",)

    def __init__(self, data, initpath=None, server=None, address=None):
        PlexObject.__init__(self, data, initpath, server)
        self.setAddress(address)

    def setAddress(self, address):
        if address != "/" and address.endswith("/"):
            self.address = address[:-1]
        else:
            self.address = address

        # TODO(schuyler): Do we need to make sure that we only hang onto the path here and not a full URL?
        if not self.address.startswith("/") and not self.upNext.asBool() and "node.plexapp.com" not in self.address:
            util.FATAL("Container address is not an expected path: {0}".format(address))

    def getAbsolutePath(self, path):
        if path.startswith('/'):
            return path
        elif "://" in path:
            return path
        else:
            return self.address + "/" + path


class PlexServerContainer(PlexContainer):
    __slots__ = ("resources",)

    def __init__(self, data, initpath=None, server=None, address=None):
        PlexContainer.__init__(self, data, initpath, server, address)
        from . import plexserver
        self.resources = [plexserver.PlexServer(elem) for elem in data]

    def __getitem__(self, idx):
        return self.resources[idx]

    def __iter__(self):
        for i in self.resources:
            yield i

    def __len__(self):
        return len(self.resources)


class PlexItemList(object):
    __slots__ = ("_data", "_itemClass", "_itemTag", "_server", "_container", "_items")

    def __init__(self, data, item_cls, tag, server=None, container=None):
        self._data = data
        self._itemClass = item_cls
        self._itemTag = tag
        self._server = server
        self._container = container
        self._items = None

    def __iter__(self):
        for i in self.items:
            yield i

    def __getitem__(self, idx):
        return self.items[idx]

    @property
    def items(self):
        if self._items is None:
            if self._data is not None:
                if self._server:
                    self._items = [self._itemClass(elem, server=self._server, container=self._container) for elem in self._data if elem.tag == self._itemTag]
                else:
                    self._items = [self._itemClass(elem) for elem in self._data if elem.tag == self._itemTag]
            else:
                self._items = []

        return self._items

    def __call__(self, *args):
        return self.items

    def __len__(self):
        return len(self.items)

    def append(self, item):
        self.items.append(item)


class PlexMediaItemList(PlexItemList):
    __slots__ = ("_initpath", "_media", "_items")

    def __init__(self, data, item_cls, tag, initpath=None, server=None, media=None):
        PlexItemList.__init__(self, data, item_cls, tag, server)
        self._initpath = initpath
        self._media = media
        self._items = None

    @property
    def items(self):
        if self._items is None:
            if self._data is not None:
                self._items = [self._itemClass(elem, self._initpath, self._server, self._media) for elem in self._data if elem.tag == self._itemTag]
            else:
                self._items = []

        return self._items


def findItem(server, path, title):
    for elem in server.query(path):
        if elem.attrib.get('title').lower() == title.lower():
            return buildItem(server, elem, path)
    raise exceptions.NotFound('Unable to find item: {0}'.format(title))


def buildItem(server, elem, initpath, bytag=False, container=None, tag_fallback=False, not_cachable=False):
    libtype = elem.tag if bytag else elem.attrib.get('type')
    if not libtype and tag_fallback:
        libtype = elem.tag

    if libtype in LIBRARY_TYPES:
        cls = LIBRARY_TYPES[libtype]
        return cls(elem, initpath=initpath, server=server, container=container, not_cachable=not_cachable)
    raise exceptions.UnknownType('Unknown library type: {0}'.format(libtype))


class ItemContainer(list):
    __slots__ = ("container", "totalSize")

    def __getattr__(self, attr):
        return getattr(self.container, attr)

    def init(self, container):
        self.container = container
        return self


def listItems(server, path, libtype=None, watched=None, bytag=False, data=None, container=None, offset=None,
              limit=None, tag_fallback=False, **kwargs):
    not_cachable = kwargs.pop('not_cachable', False)
    data = data if data is not None else server.query(path, offset=offset, limit=limit, **kwargs)
    container = container or PlexContainer(data, path, server, path)
    items = ItemContainer().init(container)

    if data:
        for elem in data:
            if libtype and elem.attrib.get('type') != libtype:
                continue
            if watched is True and PlexValue(elem.attrib.get('viewCount', "0")).asInt() == 0:
                continue
            if watched is False and PlexValue(elem.attrib.get('viewCount', "0")).asInt() >= 1:
                continue
            try:
                items.append(buildItem(server, elem, path, bytag, container, tag_fallback, not_cachable=not_cachable))
            except exceptions.UnknownType:
                pass

    return items


def searchType(libtype):
    stype = SEARCHTYPES.get(libtype.lower())
    if not stype:
        raise exceptions.NotFound('Unknown libtype: %s' % libtype)
    return stype
