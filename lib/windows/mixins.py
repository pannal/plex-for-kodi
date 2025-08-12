# coding=utf-8

import math
import os
from six import ensure_str
from plexnet import util as pnUtil
from plexnet import plexapp
from plexnet import exceptions
from plexnet import plexobjects
from kodi_six import xbmcvfs
from kodi_six import xbmc

from lib import util
from lib import backgroundthread
from lib.data_cache import dcm
from lib.util import T
from lib.path_mapping import pmm
from lib.genres import GENRES_TV_BY_SYN
from . import busy
from . import kodigui
from . import optionsdialog


class SeasonsMixin(object):
    SEASONS_CONTROL_ATTR = "subItemListControl"

    THUMB_DIMS = {
        'show': {
            'main.thumb': util.scaleResolution(347, 518),
            'item.thumb': util.scaleResolution(174, 260)
        },
        'episode': {
            'main.thumb': util.scaleResolution(347, 518),
            'item.thumb': util.scaleResolution(198, 295)
        },
        'artist': {
            'main.thumb': util.scaleResolution(519, 519),
            'item.thumb': util.scaleResolution(215, 215)
        }
    }

    def _createListItem(self, mediaItem, obj):
        mli = kodigui.ManagedListItem(
            obj.title or '',
            thumbnailImage=obj.defaultThumb.asTranscodedImageURL(*self.THUMB_DIMS[mediaItem.type]['item.thumb']),
            data_source=obj
        )
        return mli

    def getSeasonProgress(self, show, season):
        """
        calculates the season progress based on how many episodes are watched and, optionally, if there's an episode
        in progress, take that into account as well
        """
        watchedPerc = season.viewedLeafCount.asInt() / season.leafCount.asInt() * 100
        for v in show.onDeck:
            if v.parentRatingKey == season.ratingKey and v.viewOffset:
                vPerc = int((v.viewOffset.asInt() / v.duration.asFloat()) * 100)
                watchedPerc += vPerc / season.leafCount.asFloat()
        return watchedPerc > 0 and math.ceil(watchedPerc) or 0

    def fillSeasons(self, show, update=False, seasonsFilter=None, selectSeason=None, do_focus=True):
        seasons = show.seasons()
        if not seasons or (seasonsFilter and not seasonsFilter(seasons)):
            return False

        items = []
        idx = 0
        focus = None
        for season in seasons:
            if selectSeason and season == selectSeason:
                continue

            mli = self._createListItem(show, season)
            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
                mli.setProperty('unwatched.count', not season.isWatched and str(season.unViewedLeafCount) or '')
                mli.setBoolProperty('unwatched.count.large', not season.isWatched and season.unViewedLeafCount > 999)
                mli.setBoolProperty('watched', season.isFullyWatched)
                if not season.isWatched and focus is None and season.index.asInt() > 0:
                    focus = idx
                    mli.setProperty('progress', util.getProgressImage(None, self.getSeasonProgress(show, season)))
                items.append(mli)
                idx += 1

        subItemListControl = getattr(self, self.SEASONS_CONTROL_ATTR)
        if update:
            subItemListControl.replaceItems(items)
        else:
            subItemListControl.reset()
            subItemListControl.addItems(items)

        if focus is not None and do_focus:
            subItemListControl.setSelectedItemByPos(focus)

        return True


class DeleteMediaMixin(object):
    def delete(self, item=None):
        item = item or self.mediaItem
        button = optionsdialog.show(
            T(32326, 'Really delete?'),
            T(33035, "Delete {}: {}?").format(type(item).__name__, item.defaultTitle),
            T(32328, 'Yes'),
            T(32329, 'No')
        )

        if button != 0:
            return

        if not self._delete(item=item):
            util.messageDialog(T(32330, 'Message'), T(32331, 'There was a problem while attempting to delete the media.'))
            return
        return True

    @busy.dialog()
    def _delete(self, item, do_close=False):
        success = item.delete()
        util.LOG('Media DELETE: {0} - {1}', item, success and 'SUCCESS' or 'FAILED')
        if success and do_close:
            self.doClose()
        return success


class RatingsMixin(object):
    def populateRatings(self, video, ref, hide_ratings=False):
        def sanitize(src):
            return src.replace("themoviedb", "tmdb").replace('://', '/')

        setProperty = getattr(ref, "setProperty")
        getattr(ref, "setProperties")(('rating.stars', 'rating', 'rating.image', 'rating2', 'rating2.image'), '')

        if video.userRating:
            stars = str(int(round((video.userRating.asFloat() / 10) * 5)))
            setProperty('rating.stars', stars)

        if hide_ratings:
            return

        if video.TYPE == "movie" and "movies" not in util.getSetting("show_ratings"):
            return

        if (video.TYPE in ("episode", "show", "season") and
                "series" not in util.getSetting("show_ratings")):
            return

        audienceRating = video.audienceRating

        if video.rating or audienceRating:
            if video.rating:
                rating = video.rating
                if video.ratingImage.startswith('rottentomatoes:'):
                    rating = '{0}%'.format(int(rating.asFloat() * 10))

                setProperty('rating', rating)
                if video.ratingImage:
                    setProperty('rating.image', 'script.plex/ratings/{0}.png'.format(sanitize(video.ratingImage)))
            if audienceRating:
                if video.audienceRatingImage.startswith('rottentomatoes:'):
                    audienceRating = '{0}%'.format(int(audienceRating.asFloat() * 10))
                setProperty('rating2', audienceRating)
                if video.audienceRatingImage:
                    setProperty('rating2.image',
                                'script.plex/ratings/{0}.png'.format(sanitize(video.audienceRatingImage)))
        else:
            setProperty('rating', video.rating)


class SpoilersMixin(object):
    def __init__(self, *args, **kwargs):
        self._noSpoilers = None
        self.spoilerSetting = ["unwatched"]
        self.noTitles = False
        self.noRatings = False
        self.noImages = False
        self.noResumeImages = False
        self.noSummaries = False
        self.spoilersAllowedFor = True
        self.cacheSpoilerSettings()

    def cacheSpoilerSettings(self):
        self.spoilerSetting = util.getSetting('no_episode_spoilers4')
        self.noTitles = 'no_unwatched_episode_titles' in self.spoilerSetting
        self.noRatings = 'hide_ratings' in self.spoilerSetting
        self.noImages = 'blur_images' in self.spoilerSetting
        self.noResumeImages = 'blur_resume_images' in self.spoilerSetting
        self.noSummaries = 'hide_summary' in self.spoilerSetting
        self.spoilersAllowedFor = util.getSetting('spoilers_allowed_genres2')

    @property
    def noSpoilers(self):
        return self.getNoSpoilers()

    def getCachedGenres(self, rating_key):
        genres = dcm.getCacheData("show_genres", rating_key)
        if genres:
            return [pnUtil.AttributeDict(tag=g) for g in genres]

    def getNoSpoilers(self, item=None, show=None):
        """
        when called without item or show, retains a global noSpoilers value, otherwise return dynamically based on item
        or show
        returns: "off" if spoilers unnecessary, otherwise "unwatched" or "funwatched"
        """
        if not item and not show and self._noSpoilers is not None:
            return self._noSpoilers

        if item and item.type != "episode":
            return "off"

        nope = "funwatched" if "in_progress" in self.spoilerSetting else "unwatched" \
            if "unwatched" in self.spoilerSetting else "off"

        if nope != "off" and self.spoilersAllowedFor:
            # instead of making possibly multiple separate API calls to find genres for episode's shows, try to get
            # a cached value instead
            genres = []
            if item or show:
                genres = self.getCachedGenres(item and item.grandparentRatingKey or show.ratingKey)

            if not genres:
                show = getattr(self, "show_", show or (item and item.show()) or None)
                if not show:
                    return "off"

            if not genres and show:
                genres = show.genres()

            for g in genres:
                main_tag = GENRES_TV_BY_SYN.get(g.tag)
                if main_tag and main_tag in self.spoilersAllowedFor:
                    nope = "off"
                    break

        if item or show:
            self._noSpoilers = nope
            return self._noSpoilers
        return nope

    def hideSpoilers(self, ep, fully_watched=None, watched=None, use_cache=True):
        """
        returns boolean on whether we should hide spoilers for the given episode
        """
        watched = watched if watched is not None else ep.isWatched
        fullyWatched = fully_watched if fully_watched is not None else ep.isFullyWatched
        nspoil = self.getNoSpoilers(item=ep if not use_cache else None)
        return ((nspoil == 'funwatched' and not fullyWatched) or
                (nspoil == 'unwatched' and not watched))

    def getThumbnailOpts(self, ep, fully_watched=None, watched=None, hide_spoilers=None):
        if not self.noImages or self.getNoSpoilers(item=ep) == "off":
            return {}
        return (hide_spoilers if hide_spoilers is not None else
                self.hideSpoilers(ep, fully_watched=fully_watched, watched=watched)) \
            and {"blur": util.addonSettings.episodeNoSpoilerBlur} or {}


class PlaybackBtnMixin(object):
    def __init__(self, *args, **kwargs):
        self.playBtnClicked = False

    def reset(self, *args, **kwargs):
        self.playBtnClicked = False

    def onReInit(self):
        self.playBtnClicked = False


class ThemeMusicTask(backgroundthread.Task):
    def setup(self, url, volume, rating_key):
        self.url = url
        self.volume = volume
        self.rating_key = rating_key
        return self

    def run(self):
        from lib import player
        player.PLAYER.playBackgroundMusic(self.url, self.volume, self.rating_key)


class ThemeMusicMixin(object):
    """
    needs watchlistmixin as well to work
    """
    def isPlayingOurs(self, item):
        from lib import player
        return (player.PLAYER.bgmPlaying and player.PLAYER.handler.currentlyPlaying in
                         [self.wl_ref, item.ratingKey]+self.wl_item_children)

    def themeMusicInit(self, item, locations=None):
        isPlayingOurs = self.isPlayingOurs(item)
        playBGM = False
        if not isPlayingOurs:
            playBGM = True

        if util.getSetting("slow_connection"):
            playBGM = False

        if playBGM:
            self.playThemeMusic(item.theme and item.theme.asURL(True) or None, item.ratingKey, locations or [loc.get("path") for loc in item.locations],
                                item.server)


    def themeMusicReinit(self, item):
        from lib import player
        if player.PLAYER.bgmPlaying and not self.isPlayingOurs(item):
            player.PLAYER.stopAndWait()
        self.useBGM = False

    def playThemeMusic(self, theme_url, identifier, locations, server):
        volume = pnUtil.INTERFACE.getThemeMusicValue()
        if not volume:
            return

        if pmm.mapping:
            theme_found = False
            for loc in locations:
                path, pms_path, sep = pmm.getMappedPathFor(loc, server, return_rep=True)
                if path and pms_path:
                    for codec in pnUtil.AUDIO_CODECS_TC:
                        final_path = os.path.join(path, "theme.{}".format(codec)).replace(sep == "/" and "\\" or "/", sep)
                        if path and xbmcvfs.exists(final_path):
                            theme_url = final_path
                            theme_found = True
                            util.DEBUG_LOG("ThemeMusicMixin: Using {} as theme music", theme_url)
                            break
                    if theme_found:
                        break

        if theme_url:
            task = ThemeMusicTask().setup(theme_url, volume, identifier)
            backgroundthread.BGThreader.addTask(task)
            self.useBGM = True
        else:
            from lib import player
            if player.PLAYER.bgmPlaying:
                player.PLAYER.stopAndWait()


PLEX_LEGACY_LANGUAGE_MAP = {
    "pb": ("pt", "pt-BR"),
}


class PlexSubtitleDownloadMixin(object):
    def __init__(self, *args, **kwargs):
        super(PlexSubtitleDownloadMixin, self).__init__()

    @staticmethod
    def get_subtitle_language_tuple():
        from iso639 import languages
        lang_code_parse, lang_code = PLEX_LEGACY_LANGUAGE_MAP.get(pnUtil.ACCOUNT.subtitlesLanguage,
                                                                  (pnUtil.ACCOUNT.subtitlesLanguage,
                                                                   pnUtil.ACCOUNT.subtitlesLanguage))
        language = languages.get(part1=lang_code_parse)
        return language, lang_code_parse, lang_code


    def downloadPlexSubtitles(self, video, non_playback=False):
        """

        @param video:
        @return: False if user backed out, None if no subtitles found, or the downloaded subtitle stream
        """
        language, lang_code_parse, lang_code = PlexSubtitleDownloadMixin.get_subtitle_language_tuple()


        util.DEBUG_LOG("Using language {} for subtitle search", ensure_str(str(language.name)))

        subs = None
        with busy.BusyBlockingContext(delay=True):
            subs = video.findSubtitles(language=lang_code,
                                       hearing_impaired=pnUtil.ACCOUNT.subtitlesSDH,
                                       forced=pnUtil.ACCOUNT.subtitlesForced)

        if subs:
            with kodigui.WindowProperty(self, 'settings.visible', '1'):
                options = []
                for sub in sorted(subs, key=lambda s: s.score.asInt(), reverse=True):
                    info = ""
                    if sub.hearingImpaired.asInt() or sub.forced.asInt():
                        add = []
                        if sub.hearingImpaired.asInt():
                            add.append(T(33698, "HI"))
                        if sub.forced.asInt():
                            add.append(T(33699, "forced"))
                        info = " ({})".format(", ".join(add))
                    options.append((sub.key, (T(33697, "{provider_title}, Score: {subtitle_score}{subtitle_info}").format(
                        provider_title=sub.providerTitle,
                        subtitle_score=sub.score,
                        subtitle_info=info), sub.title)))
                from . import playersettings
                choice = playersettings.showOptionsDialog(T(33700, "Download subtitles: {}").format(ensure_str(language.name)),
                                                          options, trim=False, non_playback=non_playback)
                if choice is None:
                    return False

                with busy.BusyBlockingContext(delay=True):
                    video.downloadSubtitles(choice)
                    tries = 0
                    sub_downloaded = False
                    util.DEBUG_LOG("Waiting for subtitle download: {}", choice)
                    while tries < 50:
                        for stream in video.findSubtitles(language=lang_code,
                                                          hearing_impaired=pnUtil.ACCOUNT.subtitlesSDH,
                                                          forced=pnUtil.ACCOUNT.subtitlesForced):
                            if stream.downloaded.asBool():
                                util.DEBUG_LOG("Subtitle downloaded: {}", stream.extendedDisplayTitle)
                                sub_downloaded = stream
                                break
                        if sub_downloaded:
                            break
                        tries += 1
                        util.MONITOR.waitForAbort(0.1)
                    # stream will be auto selected
                    video.reload(includeExternalMedia=1, includeChapters=1, skipRefresh=1)
                    # reselect fresh media
                    media = [m for m in video.media() if m.ratingKey == video.mediaChoice.media.ratingKey][0]
                    video.setMediaChoice(media=media, partIndex=video.mediaChoice.partIndex)
                    # double reload is probably not necessary
                    video.reload(fromMediaChoice=True, forceSubtitlesFromPlex=True, skipRefresh=1)
                    for stream in video.subtitleStreams:
                        if stream.selected.asBool():
                            util.DEBUG_LOG("Selecting subtitle: {}", stream.extendedDisplayTitle)
                            return stream
        else:
            util.showNotification(util.T(33696, "No Subtitles found."),
                                  time_ms=1500, header=util.T(32396, "Subtitles"))


class WatchlistCheckBaseTask(backgroundthread.Task):
    def setup(self, server_uuid, guid, callback):
        self.server_uuid = server_uuid
        self.guid = guid
        self.callback = callback
        return self

    def getServer(self):
        return plexapp.SERVERMANAGER.getServer(self.server_uuid)


class AvailabilityCheckTask(WatchlistCheckBaseTask):
    def setup(self, *args, **kwargs):
        media_type = kwargs.pop('media_type', None)
        WatchlistCheckBaseTask.setup(self, *args)
        self.media_type = media_type
        return self

    def run(self):
        if self.isCanceled():
            return

        server = None
        try:
            if self.isCanceled():
                return

            server = self.getServer()
            res = server.query("/library/all", guid=self.guid, type=plexobjects.searchType(self.media_type))
            if res and res.get("size", 0):
                # find ratingKey
                found = []
                for child in res:
                    if child.tag in ("Directory", "Video"):
                        rk = child.get("ratingKey")
                        if rk:
                            metadata = {"rating_key": rk, "resolution": None, "bitrate": None, "season_count": None,
                                        "available": None, "server_uuid": str(self.server_uuid), "type": self.media_type}

                            # find resolution for movies
                            if self.media_type == "movie":
                                for _child in child:
                                    if _child.tag == "Media":
                                        metadata["resolution"] = _child.get("videoResolution")
                                        metadata["bitrate"] = _child.get("bitrate")
                                        break
                            else:
                                metadata["season_count"] = child.get("childCount")
                            metadata["available"] = child.get("originallyAvailableAt")
                            found.append((server.name, metadata))

                if found:
                    # sort by quality
                    if self.media_type == "movie" and len(found) > 1:
                        found.sort(key=lambda item: int(item[1]["bitrate"]), reverse=True)

                self.callback(found)
                return
            self.callback(None)
        except:
            util.ERROR()
        finally:
            del server

class IsWatchlistedTask(WatchlistCheckBaseTask):
    def run(self):
        if self.isCanceled():
            return

        server = None
        try:
            if self.isCanceled():
                return
            server = self.getServer()
            res = server.query("/library/metadata/{}/userState".format(self.guid))
            is_wl = False

            # some etree foo to find the watchlisted state
            if res and res.get("size", 0):
                for child in res:
                    if child.tag == "UserState":
                        if child.get("watchlistedAt", None):
                            is_wl = True
                        break
            self.callback(is_wl)
        except:
            util.ERROR()
        finally:
            del server


def wl_wrap(f):
    def wrapper(cls, item, *args, **kwargs):
        if not cls.wl_enabled:
            return

        # if watchlist not wanted, return

        return f(cls, item, *args, **kwargs)
    return wrapper


def GUIDToRatingKey(guid):
    return guid.rsplit("/")[-1]


def removeFromWatchlistBlind(guid):
    if not util.getUserSetting("use_watchlist", True):
        return

    try:
        if not guid or not guid.startswith("plex://"):
            return

        server = pnUtil.SERVERMANAGER.getDiscoverServer()
        server.query("/actions/removeFromWatchlist", ratingKey=GUIDToRatingKey(guid), method="put")
    except:
        pass


class WatchlistUtilsMixin(object):
    WL_BTN_WAIT = 2302
    WL_BTN_MULTIPLE = 2303
    WL_BTN_SINGLE = 2304
    WL_BTN_UPCOMING = 2305

    WL_BTN_STATE_NOT_WATCHLISTED = 308
    WL_BTN_STATE_WATCHLISTED = 309

    WL_RELEVANT_BTNS = (302, WL_BTN_WAIT, WL_BTN_MULTIPLE, WL_BTN_SINGLE, WL_BTN_UPCOMING)

    WL_BTN_STATE_BTNS = (WL_BTN_STATE_NOT_WATCHLISTED, WL_BTN_STATE_WATCHLISTED)

    wl_availability = None

    def __init__(self, *args, **kwargs):
        super(WatchlistUtilsMixin, self).__init__()
        self.wl_availability = []
        self.is_watchlisted = False
        self.wl_enabled = False
        self.wl_ref = None
        self.wl_item_children = []

    def watchlist_setup(self, item):
        self.wl_enabled = util.getUserSetting("use_watchlist", True) and item.guid and item.guid.startswith("plex://")
        self.wl_ref = GUIDToRatingKey(item.guid)
        self.setBoolProperty("watchlist_enabled", self.wl_enabled)

    @wl_wrap
    def wl_item_verbose(self, meta):
        if meta["type"] == "movie":
            res = "{}p".format(meta['resolution']) if not "k" in meta['resolution'] else meta['resolution'].upper()
            sub = '{} ({})'.format(res, pnUtil.bitrateToString(int(meta['bitrate']) * 1024))
        else:
            season_str = T(34006, '{} season') if int(meta["season_count"]) == 1 else T(34003, '{} seasons')
            sub = season_str.format(meta['season_count'])
        return sub

    @wl_wrap
    def wl_item_opener(self, ref, item_open_callback, selected_item=None):
        if len(self.wl_availability) > 1 and not selected_item:
            # choose
            from . import dropdown
            options = []
            for idx, tup in enumerate(self.wl_availability):
                server, meta = tup
                verbose = self.wl_item_verbose(meta)
                options.append({'key': idx,
                                'display': '{}, {}'.format(server, verbose)
                              })

            choice = dropdown.showDropdown(
                options=options,
                pos=(660, 441),
                close_direction='none',
                set_dropdown_prop=False,
                header=T(34004, 'Choose server'),
                dialog_props=self.dialogProps,
                align_items="left"
            )

            if not choice:
                return

            return self.wl_item_opener(ref, item_open_callback, selected_item=self.wl_availability[choice['key']][1])

        item_meta = selected_item or self.wl_availability[0][1]
        rk = item_meta.get("rating_key", None)
        if rk:
            server_differs = item_meta["server_uuid"] != plexapp.SERVERMANAGER.selectedServer.uuid
            server = orig_srv = plexapp.SERVERMANAGER.selectedServer

            if server_differs:
                server = plexapp.SERVERMANAGER.getServer(item_meta["server_uuid"])

            try:
                if server_differs:
                    # fire event to temporarily change server
                    util.LOG("Temporarily changing server source to: {}", server.name)
                    plexapp.util.APP.trigger('change:tempServer', server=server)

                item_open_callback(item=rk, inherit_from_watchlist=False, server=server, is_watchlisted=True,
                                   came_from=self.wl_ref)
            finally:
                if server_differs:
                    util.LOG("Reverting to server source: {}", orig_srv.name)
                    plexapp.util.APP.trigger('change:tempServer', server=orig_srv)

            self.checkIsWatchlisted(ref)

    @wl_wrap
    def wl_auto_remove(self, ref):
        if self.is_watchlisted and ref.isFullyWatched and util.getUserSetting('watchlist_auto_remove', True):
            self.removeFromWatchlist(ref)
            util.DEBUG_LOG("Watchlist: Item {} is fully watched, removed from watchlist", ref.ratingKey)
            return True
        elif not ref.isFullyWatched:
            util.DEBUG_LOG("Watchlist: Item {} is not fully watched, skipping", ref.ratingKey)

    @wl_wrap
    def watchlistItemAvailable(self, item, shortcut_watchlisted=False):
        """
        Is a watchlisted item available on any of the user's Plex servers?
        :param item:
        :return:
        """

        if shortcut_watchlisted:
            self.is_watchlisted = True
            self.setBoolProperty("is_watchlisted", True)
        self.setBoolProperty("wl_availability_checking", True)
        self.wl_checking_servers = len(list(pnUtil.SERVERMANAGER.connectedServers))
        self.wl_play_button_id = self.WL_BTN_WAIT

        def wl_set_btn():
            if not self.lastFocusID or self.lastFocusID in self.WL_RELEVANT_BTNS:
                change_to = None
                if self.wl_checking_servers:
                    change_to = self.WL_BTN_WAIT
                elif len(self.wl_availability) > 1:
                    change_to = self.WL_BTN_MULTIPLE
                elif len(self.wl_availability) == 1:
                    change_to = self.WL_BTN_SINGLE
                elif not self.wl_availability:
                    change_to = self.WL_BTN_UPCOMING

                if change_to and self.wl_play_button_id != change_to:
                    self.wl_play_button_id = change_to
                    # wait for visibility
                    kodigui.waitForVisibility(self.wl_play_button_id)
                    self.focusPlayButton(extended=True)

        wl_set_btn()

        def wl_av_callback(data):
            if data:
                self.wl_availability += data
                for server_name, metadata in data:
                    util.DEBUG_LOG("Watchlist availability: {}: {}", server_name, metadata)
                    self.wl_item_children.append(metadata['rating_key'])

            self.setBoolProperty("wl_availability", len(self.wl_availability) == 1)
            self.setBoolProperty("wl_availability_multiple", len(self.wl_availability) > 1)
            self.wl_checking_servers -= 1
            if self.wl_checking_servers == 0:
                self.setBoolProperty("wl_availability_checking", False)
            if self.wl_availability:
                compute = ", ".join("{}: {}".format(sn, self.wl_item_verbose(meta)) for sn, meta in self.wl_availability)
                self.setProperty("wl_server_availability_verbose", compute)

            wl_set_btn()

        for cserver in pnUtil.SERVERMANAGER.connectedServers:
            task = AvailabilityCheckTask().setup(cserver.uuid, item.guid, wl_av_callback, media_type=item.type)
            backgroundthread.BGThreader.addTask(task)

    @wl_wrap
    def checkIsWatchlisted(self, item):
        """
        Is an item on the user's watch list?
        :param item:
        :return:
        """

        def callback(state):
            self.is_watchlisted = state
            self.setBoolProperty("is_watchlisted", state)
            util.DEBUG_LOG("Watchlist state for item {}: {}", item.ratingKey, state)

        wl_rk = GUIDToRatingKey(item.guid)
        task = IsWatchlistedTask().setup('plexdiscover', wl_rk, callback)
        backgroundthread.BGThreader.addTask(task)

    def _modifyWatchlist(self, item, method="addToWatchlist"):
        server = pnUtil.SERVERMANAGER.getDiscoverServer()

        try:
            server.query("/actions/{}".format(method), ratingKey=GUIDToRatingKey(item.guid), method="put")
            util.DEBUG_LOG("Watchlist action {} for {} succeeded", method, item.ratingKey)
            self.is_watchlisted = method == "addToWatchlist"
            self.setBoolProperty("is_watchlisted", method == "addToWatchlist")
            pnUtil.APP.trigger("watchlist:modified")
            return method == "addToWatchlist"
        except exceptions.BadRequest:
            util.DEBUG_LOG("Watchlist action {} for {} failed", method, item.ratingKey)

    @wl_wrap
    def addToWatchlist(self, item):
        return self._modifyWatchlist(item)

    @wl_wrap
    def removeFromWatchlist(self, item):
        return self._modifyWatchlist(item, method="removeFromWatchlist")

    @wl_wrap
    def toggleWatchlist(self, item):
        return self._modifyWatchlist(item, method="removeFromWatchlist" if self.is_watchlisted else "addToWatchlist")
