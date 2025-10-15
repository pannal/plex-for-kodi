from __future__ import absolute_import
from functools import wraps

from . import plexobjects
from . import media
from . import plexmedia
from . import plexstream
from . import exceptions
from . import compat
from . import plexlibrary
from . import util
from . import mediachoice
from .mixins import AudioCodecMixin

from lib.data_cache import dcm
from lib.util import T


class PlexVideoItemList(plexobjects.PlexItemList):
    def __init__(self, data, initpath=None, server=None, container=None):
        self._data = data
        self._initpath = initpath
        self._server = server
        self._container = container
        self._items = None

    @property
    def items(self):
        if self._items is None:
            if self._data is not None:
                self._items = [plexobjects.buildItem(self._server, elem, self._initpath, container=self._container) for elem in self._data]
            else:
                self._items = []

        return self._items


def forceMediaChoice(method):
    @wraps(method)
    def _impl(self, *method_args, **method_kwargs):
        # set mediaChoice if we don't have any yet, or the one we have is incomplete and the new one isn't
        media = method_kwargs.get("media", None)
        partIndex = method_kwargs.get("partIndex", 0)
        if not self.mediaChoice or not self.mediaChoice.media or not self.mediaChoice.media.hasStreams():
            if not media:
                # if we don't have a chosen media yet, check whether the user has previously chosen one
                pbs = util.INTERFACE.playbackManager(self)
                if pbs.media_version:
                    for m in self.media():
                        if m.id == pbs.media_version:
                            media = m
                            break
                if not media:
                    try:
                        media = self.media()[0]
                    except (TypeError, IndexError):
                        pass

            if not self.mediaChoice or media.hasStreams():
                self.setMediaChoice(media=media, partIndex=partIndex)
        return method(self, *method_args, **method_kwargs)
    return _impl


class Video(media.MediaItem, AudioCodecMixin):
    __slots__ = ("_settings",)

    TYPE = None
    manually_selected_sub_stream = False
    current_subtitle_is_embedded = False
    _current_subtitle_idx = None
    _prev_subtitle_idx = None
    _noSpoilers = False

    def __init__(self, *args, **kwargs):
        self._settings = None
        media.MediaItem.__init__(self, *args, **kwargs)
        AudioCodecMixin.__init__(self)
        self._noSpoilers = False

    def __eq__(self, other):
        return other and self.ratingKey == other.ratingKey

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.ratingKey)

    def __repr__(self):
        return '<%s:%s>' % (self.__class__.__name__, self.ratingKey)

    @property
    def settings(self):
        if not self._settings:
            from . import plexapp
            self._settings = plexapp.PlayerSettingsInterface()

        return self._settings

    @settings.setter
    def settings(self, value):
        self._settings = value

    # overridden by Movie/Episode
    @property
    def subtitleStreams(self):
        return []

    @property
    def videoStreams(self):
        return []

    @property
    def audioStreams(self):
        return []

    @property
    def playbackSettings(self):
        return util.INTERFACE.playbackManager(self)

    def selectedVideoStream(self, fallback=False):
        if self.videoStreams:
            for stream in self.videoStreams:
                if stream.isSelected():
                    return stream
            if fallback:
                return self.videoStreams[0]
        return None

    def selectedAudioStream(self, fallback=False):
        if self.audioStreams:
            for stream in self.audioStreams:
                if stream.isSelected():
                    return stream
            if fallback:
                return self.audioStreams[0]
        return None

    def selectedSubtitleStream(self, forced_subtitles_override=False, deselect_subtitles=None,
                               fallback=False, ref="_current_subtitle_idx", force_from_plex=False):
        if ref:
            sidx = getattr(self, ref)
            if sidx:
                try:
                    return self.subtitleStreams[sidx]
                except IndexError:
                    pass

        selas = self.selectedAudioStream()

        if self.subtitleStreams:
            for stream in self.subtitleStreams:
                if stream.isSelected():
                    if force_from_plex:
                        if stream != force_from_plex:
                            continue
                        util.DEBUG_LOG("Subtitle stream requested to be the Plex decision, returning: {}", stream)
                        return stream

                    sel_stream = stream
                    stream_forced = sel_stream.forced.asBool()
                    if forced_subtitles_override and \
                            stream_forced and self.manually_selected_sub_stream != sel_stream.id:
                        # try finding a non-forced variant of this stream
                        possible_alt = None
                        for alt_stream in self.subtitleStreams:
                            if alt_stream.language == stream.language and alt_stream != stream \
                                    and not alt_stream.forced.asBool():
                                if possible_alt and not possible_alt.key and alt_stream.key:
                                    possible_alt = alt_stream
                                    break
                                if not possible_alt:
                                    possible_alt = alt_stream
                        if possible_alt:
                            util.DEBUG_LOG("Selecting stream {} instead of {}", possible_alt, stream)
                            stream.setSelected(False)
                            possible_alt.setSelected(True)
                            stream_forced = False

                            sel_stream = possible_alt
                    if (not self.manually_selected_sub_stream or self.manually_selected_sub_stream != sel_stream.id) and \
                        deselect_subtitles and selas and str(selas.languageCode) in deselect_subtitles and \
                          not stream_forced:
                        util.DEBUG_LOG("Not selecting {} subtitle stream because audio is {}",
                                       sel_stream.languageCode, selas.languageCode)
                        self._current_subtitle_idx = None
                        return

                    if self._current_subtitle_idx != sel_stream.typeIndex:
                        self._current_subtitle_idx = sel_stream.typeIndex
                    self.current_subtitle_is_embedded = sel_stream.embedded
                    return sel_stream
            if fallback:
                stream = self.subtitleStreams[0]
                if deselect_subtitles and selas and str(selas.languageCode) in deselect_subtitles and not stream.forced.asBool():
                    return
                if self._current_subtitle_idx != stream.typeIndex:
                    self._current_subtitle_idx = stream.typeIndex
                return stream
        return None

    def setMediaChoice(self, media=None, partIndex=0):
        try:
            media = media or self.media()[0]
        except (TypeError, IndexError):
            return

        self.mediaChoice = mediachoice.MediaChoice(media, partIndex=partIndex)

    @forceMediaChoice
    def selectStream(self, stream, _async=True, from_session=False, session_id=None, sync_to_server=True):
        if sync_to_server:
            self.mediaChoice.part.setSelectedStream(stream.streamType.asInt(), stream.id, _async, from_session=from_session,
                                                    session_id=session_id, video=self)
        # Update any affected streams
        if stream.streamType.asInt() == plexstream.PlexStream.TYPE_AUDIO:
            for audioStream in self.audioStreams:
                if audioStream.id == stream.id:
                    audioStream.setSelected(True)
                elif audioStream.isSelected():
                    audioStream.setSelected(False)
        elif stream.streamType.asInt() == plexstream.PlexStream.TYPE_SUBTITLE:
            self._current_subtitle_idx = None
            self.current_subtitle_is_embedded = False
            for subtitleStream in self.subtitleStreams:
                if subtitleStream.id == stream.id:
                    subtitleStream.setSelected(True)
                    self.current_subtitle_is_embedded = subtitleStream.embedded
                    self._current_subtitle_idx = subtitleStream.typeIndex
                elif subtitleStream.isSelected():
                    subtitleStream.setSelected(False)

    @forceMediaChoice
    def cycleSubtitles(self, forward=True, sync_to_server=False):
        """
        Only used by SeekDialog Subtitle Quick Settings to toggle subs
        @param sync_to_server: Don't persist changes to the PMS
        @return: selected stream
        """
        amount = len(self.subtitleStreams)
        if not amount:
            return False
        cur = self.selectedSubtitleStream()
        if not cur:
            # use fallback
            stream = self.selectedSubtitleStream(fallback=True)
        else:
            # set next if we're not at the end of the list
            if forward:
                if cur.typeIndex < len(self.subtitleStreams) - 1:
                    stream = self.subtitleStreams[cur.typeIndex+1]
                else:
                    stream = self.subtitleStreams[0]
            else:
                if cur.typeIndex > 0:
                    stream = self.subtitleStreams[cur.typeIndex - 1]
                else:
                    stream = self.subtitleStreams[-1]

        util.DEBUG_LOG("Selecting subtitle stream: {} (was: {})", stream, cur)
        self.selectStream(stream, sync_to_server=sync_to_server)
        return stream

    @forceMediaChoice
    def disableSubtitles(self, sync_to_server=False):
        """
        Only used by SeekDialog Subtitle Quick Settings to toggle subs
        @param sync_to_server: Don't persist changes to the PMS
        @return:
        """
        # store previously selected subtitle on disable, to be able to re-enable it from seekdialog
        self._prev_subtitle_idx = self._current_subtitle_idx
        self.selectStream(plexstream.NONE_STREAM, sync_to_server=sync_to_server)

    @forceMediaChoice
    def enableSubtitles(self, sync_to_server=False):
        """
        Only used by SeekDialog Subtitle Quick Settings to toggle subs
        @param sync_to_server: Don't persist changes to the PMS
        @return: selected stream
        """
        stream = self.selectedSubtitleStream(ref="_prev_subtitle_idx")
        if not stream:
            # use fallback
            stream = self.selectedSubtitleStream(fallback=True)
        self.selectStream(stream, sync_to_server=sync_to_server)
        return stream

    def findSubtitles(self, language="en", hearing_impaired=0, forced=0):
        data = self.server.query('%s/subtitles' % self.key, language=language, hearingImpaired=hearing_impaired,
                                 forced=forced)
        if data:
            return [media.SubtitleStream(elem, initpath=self.initpath, server=self.server) for elem in data]
        return []

    def downloadSubtitles(self, key):
        self.server.query('%s/subtitles' % self.key, key=key, codec="srt", method=self.server.session.put)

    @property
    def hasSubtitle(self):
        return bool(self.selectedSubtitleStream())

    @property
    def hasSubtitles(self):
        return bool(self.subtitleStreams)

    def isVideoItem(self):
        return True

    @forceMediaChoice
    def _findStreams(self, streamtype, withMC=True):
        idx = 0
        streams = []
        source = [self.mediaChoice.media] if withMC else self.media()
        for media_ in source:
            parts = [self.mediaChoice.part] if withMC else media_.parts
            for part in parts:
                for stream in part.streams:
                    if stream.streamType.asInt() == streamtype:
                        stream.typeIndex = idx
                        streams.append(stream)
                        idx += 1
        return streams

    def analyze(self):
        """ The primary purpose of media analysis is to gather information about that media
            item. All of the media you add to a Library has properties that are useful to
            know - whether it's a video file, a music track, or one of your photos.
        """
        self.server.query('/%s/analyze' % self.key)

    def refresh(self):
        self.server.query('/library/metadata/%s/refresh' % self.ratingKey, method="put")
        self.clearCache()

    def markWatched(self, **kwargs):
        path = '/:/scrobble?key=%s&identifier=com.plexapp.plugins.library' % self.ratingKey
        self.server.query(path)
        self.clearCache()
        self.reload(**kwargs)

    def markUnwatched(self, **kwargs):
        path = '/:/unscrobble?key=%s&identifier=com.plexapp.plugins.library' % self.ratingKey
        self.server.query(path)
        self.clearCache()
        self.reload(**kwargs)

    def removeFromContinueWatching(self, **kwargs):
        path = '/actions/removeFromContinueWatching?ratingKey={}'.format(self.ratingKey)
        self.server.query(path, method=self.server.session.put)
        self.reload(**kwargs)

    removeCW = removeFromContinueWatching

    # def play(self, client):
    #     client.playMedia(self)


    def _getStreamURL(self, **params):
        if self.TYPE not in ('movie', 'episode', 'track'):
            raise exceptions.Unsupported('Fetching stream URL for %s is unsupported.' % self.TYPE)
        mvb = params.get('maxVideoBitrate')
        vr = params.get('videoResolution')

        # import plexapp

        params = {
            'path': self.key,
            'offset': params.get('offset', 0),
            'copyts': params.get('copyts', 1),
            'protocol': params.get('protocol', 'hls'),
            'mediaIndex': params.get('mediaIndex', 0),
            'directStream': '1',
            'directPlay': '0',
            'X-Plex-Platform': params.get('platform', util.X_PLEX_PLATFORM),
            'X-Plex-Platform-Version': params.get('platformVersion', util.X_PLEX_PLATFORM_VERSION),
            # 'X-Plex-Platform': params.get('platform', util.INTERFACE.getGlobal('platform')),
            'maxVideoBitrate': max(mvb, 64) if mvb else None,
            'videoResolution': '{0}x{1}'.format(*vr) if vr else None
        }

        final = {}

        for k, v in params.items():
            if v is not None:  # remove None values
                final[k] = v

        streamtype = 'audio' if self.TYPE in ('track', 'album') else 'video'
        server = self.getTranscodeServer(True, self.TYPE)

        return server.buildUrl('/{0}/:/transcode/universal/start.m3u8?{1}'.format(streamtype, compat.urlencode(final)), includeToken=True)
        # path = "/video/:/transcode/universal/" + command + "?session=" + AppSettings().GetGlobal("clientIdentifier")

    @forceMediaChoice
    def resolutionString(self):
        if not self.mediaChoice:
            return ''
        res = self.mediaChoice.media.videoResolution
        if not res:
            return ''

        if res.isdigit():
            return '{0}p'.format(self.mediaChoice.media.videoResolution)
        else:
            return res.upper()

    @forceMediaChoice
    def audioCodecString(self):
        if not self.mediaChoice:
            return ''
        codec = (self.mediaChoice.media.audioCodec or '').lower()

        return self.translateAudioCodec(codec).upper()

    @forceMediaChoice
    def videoCodecString(self):
        if not self.mediaChoice:
            return ''
        return (self.mediaChoice.media.videoCodec or '').upper()

    @property
    @forceMediaChoice
    def videoCodecRendering(self):
        if not self.mediaChoice:
            return ''
        stream = self.mediaChoice.videoStream

        if not stream:
            return ''

        return stream.videoCodecRendering

    @forceMediaChoice
    def audioChannelsString(self, translate_func=util.dummyTranslate):
        if not self.mediaChoice:
            return ''
        channels = self.mediaChoice.media.audioChannels.asInt()

        if channels == 1:
            return translate_func("Mono")
        elif channels == 2:
            return translate_func("Stereo")
        elif channels > 0:
            return "{0}.1".format(channels - 1)
        else:
            return ""

    @property
    def remainingTime(self):
        return self._remainingTime()

    def _remainingTime(self, view_offset=None):
        view_offset = view_offset if view_offset is not None else self.viewOffset.asInt()
        if not view_offset:
            return
        return (self.duration.asInt() - view_offset) // 1000

    @property
    def remainingTimeString(self):
        return self._remainingTimeString()

    def _remainingTimeString(self, view_offset=None):
        remt = self._remainingTime(view_offset=view_offset)
        if not remt:
            return ''
        seconds = remt
        hours = seconds // 3600
        minutes = (seconds - hours * 3600) // 60
        return (hours and "{}h ".format(hours) or '') + (minutes and "{}m".format(minutes) or "0m")

    def available(self):
        return any(v.isAccessible() for v in self.media())

    @property
    def combined_roles(self):
        roles = []
        if self.directors():
            roles += self.directors()[:2]
        if self.roles():
            roles += self.roles()
        return roles


class SectionOnDeckMixin(object):
    _sectionOnDeckCount = None

    def sectionOnDeck(self, offset=None, limit=None):
        query = '/library/sections/{0}/onDeck'.format(self.getLibrarySectionId())
        return plexobjects.listItems(self.server, query, offset=offset, limit=limit)

    @property
    def sectionOnDeckCount(self):
        if self._sectionOnDeckCount is None:
            self._sectionOnDeckCount = self.sectionOnDeck(0, 0).totalSize

        return self._sectionOnDeckCount


class CachableItemsMixin(object):
    @property
    def cachable(self):
        return 'items' in util.INTERFACE.getPreference('cache_requests') and not self._not_cachable

    def clearChildCaches(self, return_urls=False):
        # clear caches of this season and its items
        if not self.cachable:
            return
        cks = []
        urls = []
        for e in self.getImmediateChildren():
            cks_, urls_ = e.clearCache(return_urls=True)
            cks += cks_
            urls += urls_

        cks = list(set(cks))
        urls = list(set(urls))

        if return_urls:
            return cks, urls

        self._clearCache(cks, urls)


class PlayableVideo(CachableItemsMixin, Video, media.RelatedMixin):
    __slots__ = ("extras", "guids", "chapters")
    TYPE = None
    _videoStreams = None
    _audioStreams = None
    _subtitleStreams = None
    _current_subtitle_idx = None
    isExtra = False

    def _setData(self, data):
        Video._setData(self, data)
        if self.isFullObject():
            self.extras = PlexVideoItemList(data.find('Extras'), initpath=self.initpath, server=self.server, container=self)
            self.guids = plexobjects.PlexItemList(data, media.Guid, media.Guid.TYPE, server=self.server)

            # the PMS Extras API can return protocol=mp4 when it doesn't make sense, mark this as an extra so the MDE
            # knows what to do
            for extra in self.extras:
                extra.isExtra = True
            self.chapters = plexobjects.PlexItemList(data, media.Chapter, media.Chapter.TYPE, server=self.server)

        self.resetStreams()

    def setMediaChoice(self, *args, **kwargs):
        """
        Reset cached streams after setting a mediaChoice
        """
        self._current_subtitle_idx = None
        super(PlayableVideo, self).setMediaChoice(*args, **kwargs)
        self.resetStreams()

    def resetStreams(self):
        self._videoStreams = None
        self._audioStreams = None
        self._subtitleStreams = None

    def reload(self, *args, **kwargs):
        if not kwargs.get('_soft'):
            if self.get('viewCount'):
                del self.viewCount
            if self.get('viewOffset'):
                del self.viewOffset

        fromMediaChoice = kwargs.pop("fromMediaChoice", False)
        forceSubtitlesFromPlex = kwargs.pop("forceSubtitlesFromPlex", False)

        kwargs["includeMarkers"] = 1

        # capture current IDs
        mediaID = None
        partID = None
        streamIDs = None
        reSelect = False
        if fromMediaChoice and self.mediaChoice:
            reSelect = True
            mediaID = self.mediaChoice.media.id
            partID = self.mediaChoice.part.id
            streamIDs = []
            if self.mediaChoice.media.hasStreams():
                if forceSubtitlesFromPlex:
                    subtitleStream = self.selectedSubtitleStream(ref=None, force_from_plex=forceSubtitlesFromPlex)
                else:
                    subtitleStream = self.selectedSubtitleStream(fallback=False,
                                                                 forced_subtitles_override=self.settings.getPreference("forced_subtitles_override", False) and util.ACCOUNT.subtitlesForced == 0,
                                                                 deselect_subtitles=self.settings.getPreference("disable_subtitle_languages", []))
                videoStream = self.selectedVideoStream(fallback=True)
                audioStream = self.selectedAudioStream(fallback=True)
                streamIDs = []
                if videoStream:
                    streamIDs.append(videoStream.id)
                if audioStream:
                    streamIDs.append(audioStream.id)
                if subtitleStream:
                    streamIDs.append(subtitleStream.id)

        Video.reload(self, *args, **kwargs)

        # re-select selected IDs
        if reSelect:
            selMedia = None
            selPartIndex = 0
            for media in self.media:
                if media.id == mediaID:
                    selMedia = media
                    media.set('selected', '1')
                    for index, part in enumerate(media.parts):
                        if part.id == partID:
                            selPartIndex = index
                            for stream in part.streams:
                                if stream.id in streamIDs:
                                    stream.setSelected(True)
            self.mediaChoice = mediachoice.MediaChoice(selMedia, partIndex=selPartIndex)

        return self

    def postPlay(self, **params):
        query = '/hubs/metadata/{0}/postplay'.format(self.ratingKey)
        data = self.server.query(query, params=params)
        container = plexobjects.PlexContainer(data, initpath=query, server=self.server, address=query)

        hubs = {}

        for elem in data:
            hub = plexlibrary.Hub(elem, server=self.server, container=container)
            hubs[hub.hubIdentifier] = hub
        return hubs

    def fetchExternalExtras(self):
        query = '{}/extras'.format(self.key)
        data = self.server.query(query)
        container = plexobjects.PlexContainer(data, initpath=query, server=self.server, address=query)
        items = plexobjects.PlexItemList(data, Clip, "Video", server=self.server, container=container)
        self.extras = list(items)

    @property
    def in_progress(self):
        return bool(self.get('viewOffset').asInt())

    @property
    def has_credit_markers(self):
        if hasattr(self, 'markers'):
            return bool(filter(lambda m: m.type == 'credits', self.markers))


@plexobjects.registerLibType
class Movie(PlayableVideo):
    __slots__ = ("collections", "countries", "directors", "genres", "media", "producers", "roles", "reviews",
                 "writers", "studios", "markers", "sessionKey", "user", "player", "session", "transcodeSession")
    TYPE = 'movie'

    def _setData(self, data):
        PlayableVideo._setData(self, data)
        if self.isFullObject():
            self.collections = plexobjects.PlexItemList(data, media.Collection, media.Collection.TYPE,
                                                        server=self.server)
            self.countries = plexobjects.PlexItemList(data, media.Country, media.Country.TYPE, server=self.server)
            self.directors = plexobjects.PlexItemList(data, media.Director, media.Director.TYPE, server=self.server)
            self.genres = plexobjects.PlexItemList(data, media.Genre, media.Genre.TYPE, server=self.server)
            self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE,
                                                       initpath=self.initpath, server=self.server, media=self)
            self.producers = plexobjects.PlexItemList(data, media.Producer, media.Producer.TYPE, server=self.server)
            self.roles = plexobjects.PlexItemList(data, media.Role, media.Role.TYPE, server=self.server,
                                                  container=self.container)
            self.studios = plexobjects.PlexItemList(data, media.Studio, media.Studio.TYPE, server=self.server,
                                                  container=self.container)
            self.reviews = plexobjects.PlexItemList(data, media.Review, media.Review.TYPE, server=self.server,
                                                    container=self.container)
            self.writers = plexobjects.PlexItemList(data, media.Writer, media.Writer.TYPE, server=self.server)
            #self.related = plexobjects.PlexItemList(data.find('Related'), plexlibrary.Hub, plexlibrary.Hub.TYPE, server=self.server, container=self)
        else:
            if data.find(media.Media.TYPE) is not None:
                self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE, initpath=self.initpath, server=self.server, media=self)

        self.markers = plexobjects.PlexItemList(data, media.Marker, media.Marker.TYPE, server=self.server)

        # data for active sessions
        self.sessionKey = plexobjects.PlexValue(data.attrib.get('sessionKey', ''), self)
        self.user = self._findUser(data)
        self.player = self._findPlayer(data)
        self.session = self._findSession(data)
        self.transcodeSession = self._findTranscodeSession(data)

    @property
    def defaultTitle(self):
        title = self.title or ''
        if self.editionTitle:
            title = title + " \u2022 " + self.editionTitle
        return title

    @property
    def maxHeight(self):
        height = 0
        for m in self.media:
            if m.height.asInt() > height:
                height = m.height.asInt()
        return height

    @property
    def videoStreams(self):
        if self._videoStreams is None:
            self._videoStreams = self._findStreams(plexstream.PlexStream.TYPE_VIDEO)
        return self._videoStreams

    @property
    def audioStreams(self):
        if self._audioStreams is None:
            self._audioStreams = self._findStreams(plexstream.PlexStream.TYPE_AUDIO)
        return self._audioStreams

    @property
    def subtitleStreams(self):
        if self._subtitleStreams is None:
            self._subtitleStreams = self._findStreams(plexstream.PlexStream.TYPE_SUBTITLE)
        return self._subtitleStreams

    @property
    def actors(self):
        return self.roles

    @property
    def isWatched(self):
        return self.get('viewCount').asInt() > 0 or self.get('viewOffset').asInt() > 0

    @property
    def isFullyWatched(self):
        return self.get('viewCount').asInt() > 0 and not self.get('viewOffset').asInt()

    def getStreamURL(self, **params):
        return self._getStreamURL(**params)


@plexobjects.registerLibType
class Show(CachableItemsMixin, Video, media.RelatedMixin, SectionOnDeckMixin):
    __slots__ = ("_genres", "guids", "onDeck", "locations")
    TYPE = 'show'

    def _setData(self, data):
        Video._setData(self, data)
        if self.isFullObject():
            self._genres = plexobjects.PlexItemList(data, media.Genre, media.Genre.TYPE, server=self.server)
            self.directors = plexobjects.PlexItemList(data, media.Director, media.Director.TYPE, server=self.server,
                                                  container=self.container)
            self.roles = plexobjects.PlexItemList(data, media.Role, media.Role.TYPE, server=self.server, container=self.container)
            self.guids = plexobjects.PlexItemList(data, media.Guid, media.Guid.TYPE, server=self.server)
            #self.related = plexobjects.PlexItemList(data.find('Related'), plexlibrary.Hub, plexlibrary.Hub.TYPE, server=self.server, container=self)
            self.extras = PlexVideoItemList(data.find('Extras'), initpath=self.initpath, server=self.server, container=self)
            self.onDeck = PlexVideoItemList(data.find('OnDeck'), initpath=self.initpath, server=self.server,
                                            container=self)
            self.locations = plexobjects.PlexItemList(data, media.Location, media.Location.TYPE, server=self.server)

    @property
    def unViewedLeafCount(self):
        return self.leafCount.asInt() - self.viewedLeafCount.asInt()

    @property
    def isWatched(self):
        return self.viewedLeafCount == self.leafCount

    @property
    def isFullyWatched(self):
        return self.isWatched

    def seasons(self):
        path = self.key
        return plexobjects.listItems(self.server, path, Season.TYPE, cachable=self.cachable, cache_ref=self.cacheRef,
                                     not_cachable=self._not_cachable)

    def season(self, title):
        path = self.key
        return plexobjects.findItem(self.server, path, title)

    def episodes(self, watched=None, offset=None, limit=None):
        leavesKey = '/library/metadata/%s/allLeaves' % self.ratingKey
        return plexobjects.listItems(self.server, leavesKey, watched=watched, offset=offset, limit=limit,
                                     cachable=self.cachable, cache_ref=self.cacheRef, not_cachable=self._not_cachable)

    def episode(self, title):
        path = '/library/metadata/%s/allLeaves' % self.ratingKey
        return plexobjects.findItem(self.server, path, title)

    def all(self, unwatched=False, *args, **kwargs):
        if unwatched:
            eps = self.episodes(watched=False)
            if eps:
                return eps
        return self.episodes()

    def watched(self):
        return self.episodes(watched=True)

    def unwatched(self):
        return self.episodes(watched=False)

    def genres(self):
        genres = dcm.getCacheData("show_genres", self.ratingKey)
        if genres:
            return [media.Genre(util.AttributeDict(tag="genre", attrib={"tag": g}, virtual=True)) for g in genres]

        if not self.isFullObject():
            self.reload(soft=True)

        dcm.setCacheData("show_genres", self.ratingKey, [g.tag for g in self._genres])
        return self._genres

    def getImmediateChildren(self):
        return self.seasons()

    def clearCache(self, return_urls=False, **kwargs):
        if return_urls:
            return self.clearChildCaches(return_urls=True)
        self.clearChildCaches()


@plexobjects.registerLibType
class Season(CachableItemsMixin, Video):
    TYPE = 'season'

    def _setData(self, data):
        Video._setData(self, data)
        if self.isFullObject():
            self.extras = PlexVideoItemList(data.find('Extras'), initpath=self.initpath, server=self.server, container=self)

    @property
    def defaultTitle(self):
        return T(32303, "Season {}").format(self.index)

    @property
    def unViewedLeafCount(self):
        return self.leafCount.asInt() - self.viewedLeafCount.asInt()

    @property
    def isWatched(self):
        return self.viewedLeafCount == self.leafCount

    @property
    def isFullyWatched(self):
        return self.isWatched

    def episodes(self, watched=None, offset=None, limit=None):
        path = self.key
        return plexobjects.listItems(self.server, path, watched=watched, offset=offset, limit=limit,
                                     cachable=self.cachable, cache_ref=self.cacheRef, not_cachable=self._not_cachable)

    def episode(self, title):
        path = self.key
        return plexobjects.findItem(self.server, path, title)

    def all(self, *args, **kwargs):
        return self.episodes()

    def show(self):
        return plexobjects.listItems(self.server, self.parentKey, cachable=self.cachable, cache_ref=self.cacheRef,
                                     not_cachable=self._not_cachable)[0]

    def watched(self):
        return self.episodes(watched=True)

    def unwatched(self):
        return self.episodes(watched=False)

    def getImmediateChildren(self):
        return self.episodes()

    def clearCache(self, return_urls=False, **kwargs):
        if return_urls:
            return self.clearChildCaches(return_urls=True)
        self.clearChildCaches()


@plexobjects.registerLibType
class Episode(PlayableVideo, SectionOnDeckMixin):
    __slots__ = ("_show", "_season")
    TYPE = 'episode'

    def init(self, data):
        self._show = None
        self._season = None

    def _setData(self, data):
        PlayableVideo._setData(self, data)
        if self.isFullObject():
            self.directors = plexobjects.PlexItemList(data, media.Director, media.Director.TYPE, server=self.server)
            self._roles = plexobjects.PlexItemList(data, media.Role, media.Role.TYPE, server=self.server)
            self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE, initpath=self.initpath, server=self.server, media=self)
            self.writers = plexobjects.PlexItemList(data, media.Writer, media.Writer.TYPE, server=self.server)
        else:
            if data.find(media.Media.TYPE) is not None:
                self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE, initpath=self.initpath, server=self.server, media=self)

        self.markers = plexobjects.PlexItemList(data, media.Marker, media.Marker.TYPE, server=self.server)

        # data for active sessions
        self.sessionKey = plexobjects.PlexValue(data.attrib.get('sessionKey', ''), self)
        self.user = self._findUser(data)
        self.player = self._findPlayer(data)
        self.session = self._findSession(data)
        self.transcodeSession = self._findTranscodeSession(data)

    @property
    def defaultTitle(self):
        return self.grandparentTitle or self.parentTitle or self.title

    @property
    def defaultThumb(self):
        if self.settings.getPreference("hub_season_thumbnails", True):
            return self.parentThumb or self.grandparentThumb or self.thumb
        return self.grandparentThumb or self.parentThumb or self.thumb

    @property
    def videoStreams(self):
        if self._videoStreams is None:
            self._videoStreams = self._findStreams(plexstream.PlexStream.TYPE_VIDEO)
        return self._videoStreams

    @property
    def audioStreams(self):
        if self._audioStreams is None:
            self._audioStreams = self._findStreams(plexstream.PlexStream.TYPE_AUDIO)
        return self._audioStreams

    @property
    def subtitleStreams(self):
        if self._subtitleStreams is None:
            self._subtitleStreams = self._findStreams(plexstream.PlexStream.TYPE_SUBTITLE)
        return self._subtitleStreams

    @property
    def isWatched(self):
        return self.get('viewCount').asInt() > 0 or self.get('viewOffset').asInt() > 0

    @property
    def isFullyWatched(self):
        return self.get('viewCount').asInt() > 0 and not self.get('viewOffset').asInt()

    @property
    def playbackSettings(self):
        return self.show().playbackSettings

    def getStreamURL(self, **params):
        return self._getStreamURL(**params)

    def season(self):
        skipParent = self.get('skipParent').asBool()
        key = self.parentKey if not skipParent else self.grandparentKey
        if not self._season:
            items = plexobjects.listItems(self.server, key, cachable=self.cachable, cache_ref=self.cacheRef,
                                          not_cachable=self._not_cachable)

            if items:
                self._season = items[0]
        return self._season

    def show(self):
        if not self._show:
            self._show = plexobjects.listItems(self.server, self.grandparentKey, cachable=self.cachable,
                                               cache_ref=self.cacheRef, not_cachable=self._not_cachable)[0]
        return self._show

    @property
    def genres(self):
        return self.show().genres

    @property
    def roles(self):
        return self._roles or self.show().roles

    def getRelated(self, offset=None, limit=None, _max=36):
        return self.show().getRelated(offset=offset, limit=limit, _max=_max)


@plexobjects.registerLibType
class Clip(PlayableVideo):
    TYPE = 'clip'

    def _setData(self, data):
        PlayableVideo._setData(self, data)
        if self.isFullObject():
            self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE, initpath=self.initpath, server=self.server, media=self)
        else:
            if data.find(media.Media.TYPE) is not None:
                self.media = plexobjects.PlexMediaItemList(data, plexmedia.PlexMedia, media.Media.TYPE, initpath=self.initpath, server=self.server, media=self)

    @property
    def isWatched(self):
        return self.get('viewCount').asInt() > 0 or self.get('viewOffset').asInt() > 0

    @property
    def isFullyWatched(self):
        return self.get('viewCount').asInt() > 0 and not self.get('viewOffset').asInt()

    def getStreamURL(self, **params):
        return self._getStreamURL(**params)

    @property
    def videoStreams(self):
        if self._videoStreams is None:
            self._videoStreams = self._findStreams(plexstream.PlexStream.TYPE_VIDEO)
        return self._videoStreams

    @property
    def audioStreams(self):
        if self._audioStreams is None:
            self._audioStreams = self._findStreams(plexstream.PlexStream.TYPE_AUDIO)
        return self._audioStreams

    @property
    def subtitleStreams(self):
        if self._subtitleStreams is None:
            self._subtitleStreams = self._findStreams(plexstream.PlexStream.TYPE_SUBTITLE)
        return self._subtitleStreams
