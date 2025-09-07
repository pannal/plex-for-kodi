from __future__ import absolute_import

import requests.exceptions
import copy
from kodi_six import xbmc
from kodi_six import xbmcgui
from collections import OrderedDict

from plexnet import plexapp, playlist, plexplayer, plexlibrary, util as pnUtil

from lib import backgroundthread
from lib import metadata
from lib import player
from lib import util
from lib.util import T
from . import busy
from . import dropdown
from . import info
from . import kodigui
from . import opener
from . import optionsdialog
from . import pagination
from . import playbacksettings
from . import playersettings
from . import search
from . import videoplayer
from . import windowutils
from .mixins.seasons import SeasonsMixin
from .mixins.spoilers import SpoilersMixin
from .mixins.playbackbtn import PlaybackBtnMixin
from .mixins.thememusic import ThemeMusicMixin
from .mixins.watchlist import WatchlistUtilsMixin
from .mixins.ratings import RatingsMixin
from .mixins.roles import RolesMixin
from .mixins.common import CommonMixin

VIDEO_RELOAD_KW = dict(includeExtras=1, includeExtrasCount=10, includeChapters=1)


class EpisodeReloadTask(backgroundthread.Task):
    def setup(self, episode, callback, with_progress=False, set_item_info=False):
        self.episode = episode
        self.callback = callback
        self.withProgress = with_progress
        self.setItemInfo = set_item_info
        return self

    def run(self):
        if self.isCanceled():
            return

        if not plexapp.SERVERMANAGER.selectedServer:
            # Could happen during sign-out for instance
            return

        try:
            self.episode.reload(checkFiles=1, includeChapters=1, fromMediaChoice=self.episode.mediaChoice is not None)
            if self.isCanceled():
                return
            self.callback(self, self.episode, with_progress=self.withProgress, set_item_info=self.setItemInfo)
        except requests.exceptions.RequestException:
            raise util.NoDataException
        except:
            util.ERROR()


class EpisodesPaginator(pagination.MCLPaginator):
    thumbFallback = 'script.plex/thumb_fallbacks/show.png'
    _currentEpisode = None

    def reset(self):
        super(EpisodesPaginator, self).reset()
        self._currentEpisode = None

    def getData(self, offset, amount):
        return (self.parentWindow.season or self.parentWindow.show_).episodes(offset=offset, limit=amount)

    def createListItem(self, data):
        mli = super(EpisodesPaginator, self).createListItem(data)
        self.parentWindow.setItemInfo(data, mli)
        return mli

    def prepareListItem(self, data, mli):
        mli.setBoolProperty('watched', mli.dataSource.isFullyWatched)
        if not mli.dataSource.isWatched:
            mli.setProperty('unwatched.count', str(mli.dataSource.unViewedLeafCount))
            mli.setBoolProperty('unwatched.count.large', mli.dataSource.unViewedLeafCount.asInt() > 999)
            mli.setProperty('unwatched', '1')
        mli.setProperty('progress', util.getProgressImage(mli.dataSource))

    def setEpisode(self, ep):
        self._currentEpisode = ep

    @property
    def initialPage(self):
        episode = self.parentWindow.episode
        offset = 0
        amount = self.initialPageSize
        if episode:
            self.setEpisode(episode)
            # try cutting the query short while not querying all episodes, to find the slice with the currently
            # selected episode in it
            episodes = []
            _amount = self.initialPageSize + self.orphans
            epSeasonIndex = int(episode.index or 1) - 1  # .index is 1-based
            if _amount < self.leafCount:
                _amount = self.initialPageSize * 2
                notFound = False
                while episode not in episodes:
                    offset = int(max(0, epSeasonIndex - _amount / 2))
                    episodes = self.getData(offset, int(_amount))

                    if _amount >= self.leafCount:
                        # ep not found?
                        notFound = True
                        break

                    # in case the episode wasn't found inside the slice, increase the slice's size
                    _amount *= 2

                if notFound:
                    # search conservatively
                    util.DEBUG_LOG("Episode not found with intelligent index-based search, re-trying conservatively")
                    _amount = self.initialPageSize * 2
                    offset = 0
                    episodes = self.getData(offset, int(_amount))
                    while episode not in episodes:
                        offset = _amount
                        episodes = self.getData(offset, int(_amount))

                        if _amount >= self.leafCount:
                            break

                        _amount *= 2
            else:
                # shortcut for short seasons
                episodes = self.getData(offset, int(_amount))

        else:
            return super(EpisodesPaginator, self).initialPage

        episodeFound = episode and episode in episodes
        if episodeFound:
            if self.initialPageSize + self.orphans < self.leafCount:
                # slice around the episode
                # Clamp the left side dynamically based on the item index and how many items are left in the season.
                # The episodes list might be longer than our limit, because the season doesn't necessarily have all the
                # episodes in it and we're basing the initial load on the current episode's index, which is the actual
                # index of the episode in the season, not what's physically there. To find the episode, we're
                # dynamically increasing the window size above. Re-clamp to :amount:, adding slack to both sides if
                # the remaining episodes would fit inside half of :amount:.
                tmpEpIdx = episodes.index(episode)
                leftBoundary = self.initialPageSize - len(episodes[tmpEpIdx:tmpEpIdx + self.orphans])

                left = max(tmpEpIdx - leftBoundary, 0)
                offset += left
                epsLeft = self.leafCount - offset
                # avoid short pages on the right end
                if epsLeft <= self.initialPageSize + self.orphans:
                    amount = epsLeft

                # avoid short pages on the left end
                if offset < self.orphans and amount + offset < self.initialPageSize + self.orphans:
                    amount += offset
                    left = 0
                    offset = 0

                episodes = episodes[left:left + amount]

        self.offset = offset
        self._currentAmount = len(episodes)

        return episodes

    def selectItem(self, amount, more_left=False, more_right=False, items=None):
        if not super(EpisodesPaginator, self).selectItem(amount, more_left):
            if (self._currentEpisode and items) and self._currentEpisode in items:
                self.control.selectItem(items.index(self._currentEpisode) + (1 if more_left else 0))


class RelatedPaginator(pagination.BaseRelatedPaginator):
    def getData(self, offset, amount):
        return self.parentWindow.show_.getRelated(offset=offset, limit=amount)


class RedirectToEpisode(Exception):
    episode = None
    season = None
    select_episode = True

    def __init__(self, episode, season=None, select_episode=True):
        self.episode = episode
        self.season = season
        self.select_episode = select_episode


VIDEO_PROGRESS = OrderedDict()

class EpisodesWindow(kodigui.ControlledWindow, windowutils.UtilMixin, SeasonsMixin, RatingsMixin, SpoilersMixin,
                     RolesMixin, PlaybackBtnMixin, ThemeMusicMixin, WatchlistUtilsMixin, CommonMixin,
                     playbacksettings.PlaybackSettingsMixin):
    xmlFile = 'script-plex-episodes.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    THUMB_AR16X9_DIM = util.scaleResolution(657, 393)
    POSTER_DIM = util.scaleResolution(420, 630)
    RELATED_DIM = util.scaleResolution(268, 402)
    EXTRA_DIM = util.scaleResolution(329, 185)
    ROLES_DIM = util.scaleResolution(334, 334)

    LIST_OPTIONS_BUTTON_ID = 111

    EPISODE_LIST_ID = 400
    SEASONS_LIST_ID = 401
    ROLES_LIST_ID = 402
    EXTRA_LIST_ID = 403
    RELATED_LIST_ID = 404

    OPTIONS_GROUP_ID = 200

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202
    PLAYER_STATUS_BUTTON_ID = 204

    PROGRESS_IMAGE_ID = 250

    MAIN_BUTTON_GROUP_ID = 300
    PLAY_BUTTON_ID = 301
    PLAY_BUTTON_DISABLED_ID = 306
    SHUFFLE_BUTTON_ID = 302
    OPTIONS_BUTTON_ID = 303
    INFO_BUTTON_ID = 304
    SETTINGS_BUTTON_ID = 305
    MEDIA_BUTTON_ID = 307

    SEASONS_CONTROL_ATTR = "seasonsListControl"

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        windowutils.UtilMixin.__init__(self)
        SpoilersMixin.__init__(self, *args, **kwargs)
        PlaybackBtnMixin.__init__(self, *args, **kwargs)
        WatchlistUtilsMixin.__init__(self)
        self.episode = None
        self.reset(kwargs.get('episode'), kwargs.get('season'), kwargs.get('show'))
        self.parentList = kwargs.get('parentList')
        self.cameFrom = kwargs.get('came_from')
        self.fromWatchlist = kwargs.get('from_watchlist')
        self.tasks = backgroundthread.Tasks()

    def reset(self, episode, season=None, show=None):
        self.episode = episode
        self.initialEpisode = episode
        self.season = season if season is not None else self.episode.season()
        try:
            self.show_ = show or (self.episode or self.season).show().reload(includeExtras=1, includeExtrasCount=10,
                                                                             includeOnDeck=1)
        except IndexError:
            raise util.NoDataException

        self.initialized = False
        self.closing = False
        self.parentList = None
        self.episodesPaginator = None
        self.relatedPaginator = None
        self.seasons = None
        self.manuallySelected = False
        self.manuallySelectedSeason = False
        self.hadUserInteraction = False
        self.currentItemLoaded = False
        self.lastItem = None
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.openedWithAutoPlay = False
        self.useBGM = False
        PlaybackBtnMixin.reset(self)

    def doClose(self, **kw):
        self.closing = True
        self.episodesPaginator = None
        self.relatedPaginator = None
        kodigui.ControlledWindow.doClose(self)
        if self.tasks:
            self.tasks.cancel()
            self.tasks = None
        try:
            player.PLAYER.off('new.video', self.onNewVideo)
            player.PLAYER.off('video.progress', self.onVideoProgress)
        except KeyError:
            pass

    @busy.dialog()
    def _onFirstInit(self):
        self.episodeListControl = kodigui.ManagedControlList(self, self.EPISODE_LIST_ID, 5)
        self.progressImageControl = self.getControl(self.PROGRESS_IMAGE_ID)

        self.seasonsListControl = kodigui.ManagedControlList(self, self.SEASONS_LIST_ID, 5)
        self.rolesListControl = kodigui.ManagedControlList(self, self.ROLES_LIST_ID, 5)
        self.extraListControl = kodigui.ManagedControlList(self, self.EXTRA_LIST_ID, 5)
        self.relatedListControl = kodigui.ManagedControlList(self, self.RELATED_LIST_ID, 5)

        VIDEO_PROGRESS.clear()

        if not self.openedWithAutoPlay:
            # we may have set up the hooks before
            self._setup_hooks()
        self._setup()
        self.postSetup()

    def doAutoPlay(self):
        # First reload the video to get all the other info
        self.initialEpisode.reload(checkFiles=1, **VIDEO_RELOAD_KW)

        # We're not hitting onFirstInit when autoplaying from home, setup hooks here, so we can grab video progress
        #self._setup_hooks()
        self.openedWithAutoPlay = True
        return self.playButtonClicked(force_episode=self.initialEpisode, from_auto_play=True)

    def onFirstInit(self):
        self._onFirstInit()

        if self.show_ and not util.getSetting("slow_connection") and \
                (not self.cameFrom or self.cameFrom not in (self.show_.ratingKey, "postplay")) and \
                not self.openedWithAutoPlay:
            self.themeMusicInit(self.show_)

        self.openedWithAutoPlay = False

    @busy.dialog()
    def onReInit(self):
        self.playBtnClicked = False
        self.themeMusicReinit(self.show_)
        if not self.tasks:
            self.tasks = backgroundthread.Tasks()

        vp = None
        if self.show_.ratingKey in VIDEO_PROGRESS:
            # access progress data for current show only
            vp = copy.deepcopy(VIDEO_PROGRESS[self.show_.ratingKey]).get(self.season.ratingKey, {})

        if (self.manuallySelected and not VIDEO_PROGRESS) or self.cameFrom in ("info", "show", "library"):
            if self.cameFrom in ("info", "show", "library"):
                self.cameFrom = None
                return
            util.DEBUG_LOG("Episodes: ReInit: Not doing anything, as we've previously manually selected "
                           "this item and don't have progress")
            return

        self.manuallySelected = False
        util.DEBUG_LOG("Episodes: {}: Got progress info: {}, came from: {}".format(
            self.episode and self.episode.ratingKey or None, VIDEO_PROGRESS, self.cameFrom))
        try:
            self.selectEpisode(from_reinit=True)
        except RedirectToEpisode as redirect:
            if redirect.select_episode:
                util.DEBUG_LOG("Got episode progress for a different season, redirecting")
            self.episodeListControl.reset()
            self.relatedListControl.reset()
            self.reset(episode=redirect.episode if redirect.select_episode else None, season=redirect.season)
            self.hadUserInteraction = True
            self._setup()
            self.postSetup()
            return
        except AttributeError:
            raise util.NoDataException

        if self.cameFrom == "info":
            self.cameFrom = None

        # keep progress data if we've been opened from another view, as parent views might need the updates as well
        if not self.cameFrom:
            VIDEO_PROGRESS.clear()

        mli = self.episodeListControl.getSelectedItem()
        if not mli or not self.episodesPaginator:
            return

        if vp:
            self.show_.reload(checkFiles=1, **VIDEO_RELOAD_KW)
            self.wl_auto_remove(self.show_)

        reload_items = [mli]
        skip_progress_for = None
        if vp:
            skip_progress_for = []
            break_next = False
            for m in self.episodeListControl:
                # pagination boundary
                if not m.dataSource:
                    continue

                if m.dataSource.ratingKey in vp or break_next:
                    reload_items.append(m)
                    if not break_next:
                        skip_progress_for.append(m.dataSource.ratingKey)
                        del vp[m.dataSource.ratingKey]
                    else:
                        break
                if not vp:
                    # for multi-episode videos reload the next one after this progress event as well
                    break_next = True

        reload_items = list(set(reload_items))
        #select_episode = reload_items and reload_items[-1] or mli

        #self.episodesPaginator.setEpisode(select_episode.dataSource)
        if not reload_items:
            self.selectPlayButton()
        self.reloadItems(items=reload_items, with_progress=True, skip_progress_for=skip_progress_for,
                         set_item_info=True)
        self.fillSeasons(self.show_, seasonsFilter=lambda x: len(x) > 1, selectSeason=self.season, update=True,
                         do_focus=not self.manuallySelectedSeason)
        self.fillRelated()

    def postSetup(self):
        self.checkForHeaderFocus(xbmcgui.ACTION_MOVE_DOWN, initial=True)
        if not self.hadUserInteraction:
            self.selectPlayButton()
        self.initialized = True

    def selectPlayButton(self):
        if not self.fromWatchlist:
            selected = self.episodeListControl.getSelectedItem()
            if selected:
                set_focus = self.getPlayButtonID(selected, base=not self.currentItemLoaded
                                                 and self.PLAY_BUTTON_DISABLED_ID or None)
                self.setCondFocusId(set_focus)

    @busy.dialog()
    def setup(self):
        self._setup()

    def _setup_hooks(self):
        player.PLAYER.on('new.video', self.onNewVideo)
        player.PLAYER.on('video.progress', self.onVideoProgress)

    def _setup(self):
        (self.season or self.show_).reload(checkFiles=1, **VIDEO_RELOAD_KW)

        if not self.episodesPaginator:
            self.episodesPaginator = EpisodesPaginator(self.episodeListControl,
                                                       leaf_count=int(self.season.leafCount) if self.season else 0,
                                                       parent_window=self)

        if not self.relatedPaginator:
            self.relatedPaginator = RelatedPaginator(self.relatedListControl, leaf_count=int(self.show_.relatedCount),
                                                     parent_window=self)

        self.watchlist_setup(self.show_)
        self.updateProperties()
        self.setBoolProperty("initialized", True)
        self.fillEpisodes()

        hasSeasons = self.fillSeasons(self.show_, seasonsFilter=lambda x: len(x) > 1, selectSeason=self.season)
        hasPrev = self.fillExtras(hasSeasons)

        if not hasPrev and hasSeasons:
            hasPrev = True
        hasPrev = self.fillRelated(hasPrev)
        self.fillRoles(hasPrev)

    def selectEpisode(self, from_reinit=False):
        util.DEBUG_LOG("SelectEpisode called: {}, {}, {}, {}, {}, {}", from_reinit, self.episode, self.season,
                       self.show_, VIDEO_PROGRESS, self.cameFrom)
        if not self.episodesPaginator:
            return

        had_progress_data = False
        progress_data_left = None
        progress_data = None
        if self.show_.ratingKey in VIDEO_PROGRESS:
            # access progress data for current show only
            progress_data = copy.deepcopy(VIDEO_PROGRESS[self.show_.ratingKey])

        set_main_progress_to = None
        selected_new = False

        last_mli_seen = None
        progress_for_last_mli = False

        mli = self.episodeListControl[0]

        if progress_data or not self.season.isFullyWatched:
            if progress_data:
                # check for progress data in current season
                progress_data_left = progress_data.pop(self.season.ratingKey, None)
                had_progress_data = bool(progress_data_left)

            for mli in self.episodeListControl:
                # pagination boundary
                if not mli.dataSource:
                    continue

                is_last_mli = self.episodeListControl.isLastItem(mli)

                just_fully_watched = False

                if progress_data_left and mli.dataSource:
                    progress = progress_data_left.pop(mli.dataSource.ratingKey, False)
                    progress_for_last_mli = progress and is_last_mli

                    # progress can be False (no entry), a number (progress), or True (fully watched just now)
                    # select it if it's not watched or in progress
                    if progress:
                        if progress is True:
                            # ep was just watched
                            just_fully_watched = True
                            mli.setProperty('unwatched', '')
                            mli.setProperty('watched', '1')
                            mli.setProperty('progress', '')
                            mli.setProperty('unwatched.count', '')
                            mli.setProperty('unwatched.count.large', '')
                            mli.dataSource.set('viewCount', mli.dataSource.get('viewCount', 0).asInt() + 1)
                            mli.dataSource.set('viewOffset', 0)
                            mli.dataSource.markWatched()
                            self.setUserItemInfo(mli, fully_watched=True)

                        elif progress > 60000:
                            # ep has progress
                            mli.setProperty('watched', '')
                            mli.setProperty('progress', util.getProgressImage(mli.dataSource, view_offset=progress))
                            mli.dataSource.set('viewOffset', progress)
                            self.setUserItemInfo(mli, watched=True)
                            set_main_progress_to = progress

                        elif progress <= 60000:
                            # reset progress as we might've had progress before
                            mli.setProperty('progress', '')
                            mli.dataSource.set('viewOffset', '')
                            self.setUserItemInfo(mli)
                            set_main_progress_to = 0

                        mli.dataSource.clearCache()

                        if self.noRatings:
                            self.populateRatings(mli.dataSource, mli, hide_ratings=self.hideSpoilers(mli.dataSource))

                    # after immediately updating the watched state, if we still have data left, continue
                    if progress is True and progress_data_left:
                        continue

                last_mli_seen = mli

                # first condition: we select self.episode if we've got no progress data, or we haven't watched it just now.
                # second condition: we've just come from playback with progress upon reinit. select the next available
                # episode that's either unwatched or in progress. if we're at the last item in the list, select it as well.
                # third condition: select the next unwatched episode if we don't have self.episode and didn't have any
                # player progress, which happens when being called without an episode (season view, show view).
                if (mli.dataSource == self.episode and not just_fully_watched and not progress_data_left) or \
                   (had_progress_data and not progress_data_left and ((not just_fully_watched
                    and not mli.dataSource.isFullyWatched) or (just_fully_watched and is_last_mli))) or \
                   ((not had_progress_data or not from_reinit) and not self.episode and not mli.dataSource.isFullyWatched):
                    #if self.episodeListControl.getSelectedPosition() < mli.pos():
                    self.episodeListControl.selectItem(mli.pos())
                    self.episodesPaginator.setEpisode(self.episode or mli.dataSource)
                    self.lastItem = mli
                    selected_new = mli
                    if just_fully_watched:
                        set_main_progress_to = 0

                    # this is a little counter-intuitive - None is actually valid here, and if set to None, setProgress will
                    # use the actual item progress, not ours
                    self.setProgress(mli, view_offset=set_main_progress_to)
                    break
            else:
                # no matching episode found
                mli = self.episodeListControl.getSelectedItem()
                self.setProgress(mli, view_offset=0)
        elif self.season.isFullyWatched and not self.episode:
            self.episodeListControl.selectItem(mli.pos())
            self.episodesPaginator.setEpisode(mli)
            self.lastItem = mli

        if from_reinit and had_progress_data:
            # we had progress data for our current season and still have progress data for the current TV show
            if progress_data:
                # we've probably watched something in the next season
                ns = progress_data[list(progress_data.keys())[-1]]
                key = '/library/metadata/{0}'.format(list(ns.keys())[-1])
                ep = plexapp.SERVERMANAGER.selectedServer.getObject(key)
                if ep.parentIndex != self.season.index and ep.grandparentRatingKey == self.show_.ratingKey:
                    util.LOG("Progress data left for TV show, going to season of "
                             "remaining episode with progress data: {}", ep)
                    raise RedirectToEpisode(ep)
            elif progress_for_last_mli and last_mli_seen.dataSource.isFullyWatched and self.getSeasons():
                # check if we need to go to the next season
                remaining_seasons = self.seasons[self.seasons.index(self.season)+1:]
                if remaining_seasons:
                    season = remaining_seasons[0]
                    VIDEO_PROGRESS.clear()
                    util.LOG("Season watched, going to next season: {}", season)
                    raise RedirectToEpisode(season.episodes()[0], season=season, select_episode=False)

        if selected_new:
            #self.setProperty('hub.focus', "0")
            #self.setProperty('on.extras', '')
            self.lastFocusID = None
            if not from_reinit:
                self.currentItemLoaded = False

            # wait for ep list to update
            waited = 0
            while self.episodeListControl.getSelectedItem() != selected_new and waited < 20:
                util.MONITOR.waitForAbort(0.1)
                waited += 1

        self.episode = None

    def onAction(self, action):
        try:
            controlID = self.getFocusId()

            if not controlID and self.lastFocusID and not action == xbmcgui.ACTION_MOUSE_MOVE:
                self.setCondFocusId(self.lastFocusID)

            if action == xbmcgui.ACTION_LAST_PAGE and xbmc.getCondVisibility('ControlGroup(300).HasFocus(0)'):
                next(self)
            elif action == xbmcgui.ACTION_NEXT_ITEM:
                next(self)
            elif action == xbmcgui.ACTION_FIRST_PAGE and xbmc.getCondVisibility('ControlGroup(300).HasFocus(0)'):
                self.prev()
            elif action == xbmcgui.ACTION_PREV_ITEM:
                self.prev()

            if action in (xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                self.hadUserInteraction = True

            if action == xbmcgui.ACTION_MOVE_UP and controlID in (self.EPISODE_LIST_ID, self.SEASONS_LIST_ID):
                self.updateBackgroundFrom((self.season or self.show_ or self.season.show()))

            if controlID == self.SEASONS_LIST_ID and action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                self.manuallySelectedSeason = True

            elif controlID == self.EPISODE_LIST_ID:
                if self.checkForHeaderFocus(action):
                    return
                elif self.isWatchedAction(action):
                    mli = self.episodeListControl.getSelectedItem()
                    if not mli or mli.getProperty("is.boundary"):
                        return
                    self.toggleWatched(mli)
                    self.selectEpisode()
                    return
                elif action == xbmcgui.ACTION_CONTEXT_MENU:
                    self.optionsButtonClicked(from_item=True)
                    return

            elif controlID == self.RELATED_LIST_ID:
                if self.relatedPaginator and self.relatedPaginator.boundaryHit:
                    self.relatedPaginator.paginate()
                    return
                elif action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                    self.updateBackgroundFrom(self.relatedListControl.getSelectedItem().dataSource)

            elif self.isWatchedAction(action) and xbmc.getCondVisibility('ControlGroup({}).HasFocus(0)'.format(self.MAIN_BUTTON_GROUP_ID)):
                mli = self.episodeListControl.getSelectedItem()
                if not mli or mli.getProperty("is.boundary"):
                    return

                self.toggleWatched(mli)
                self.selectEpisode()
                return

            if controlID == self.LIST_OPTIONS_BUTTON_ID and self.checkOptionsAction(action):
                return
            elif action == xbmcgui.ACTION_CONTEXT_MENU:
                if controlID in (self.PLAY_BUTTON_ID, self.PLAY_BUTTON_ID + 1000) and util.getSetting('assume_resume'):
                    self.playButtonClicked(force_resume_menu=True)
                    return

                if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                    self.lastNonOptionsFocusID = self.lastFocusID
                    self.setFocusId(self.OPTIONS_GROUP_ID)
                    return
                else:
                    if self.lastNonOptionsFocusID:
                        self.setCondFocusId(self.lastNonOptionsFocusID)
                        self.lastNonOptionsFocusID = None
                        return

            elif action == xbmcgui.ACTION_NAV_BACK:
                if (not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(
                        self.OPTIONS_GROUP_ID)) or not controlID) and \
                        not util.addonSettings.fastBack:
                    if self.getProperty('on.extras'):
                        self.setCondFocusId(self.OPTIONS_GROUP_ID)
                        return

            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                self.doClose()
        except:
            util.ERROR()

        kodigui.ControlledWindow.onAction(self, action)

    def onNewVideo(self, video=None, **kwargs):
        if not video:
            return

        if not video.type == 'episode':
            return

        util.DEBUG_LOG('Updating selected episode: {0}', video)
        self.episode = video

        return True

    def onVideoProgress(self, data=None, **kwargs):
        if not data:
            return

        util.DEBUG_LOG("Storing video progress data: {}", data)
        gprk, prk, rk, state = data
        if gprk not in VIDEO_PROGRESS:
            VIDEO_PROGRESS[gprk] = OrderedDict()

        if prk not in VIDEO_PROGRESS[gprk]:
            VIDEO_PROGRESS[gprk][prk] = OrderedDict()

        VIDEO_PROGRESS[gprk][prk][rk] = state

    def onBGMStarted(self, **kwargs):
        self.playBtnClicked = True

    def checkOptionsAction(self, action):
        if action == xbmcgui.ACTION_MOVE_UP:
            mli = self.episodeListControl.getSelectedItem()
            if not mli or mli.getProperty("is.boundary"):
                return False
            pos = mli.pos() - 1
            if self.episodeListControl.positionIsValid(pos):
                self.setCondFocusId(self.EPISODE_LIST_ID)
                self.episodeListControl.selectItem(pos)
            return True
        elif action == xbmcgui.ACTION_MOVE_DOWN:
            mli = self.episodeListControl.getSelectedItem()
            if not mli or mli.getProperty("is.boundary"):
                return False
            pos = mli.pos() + 1
            if self.episodeListControl.positionIsValid(pos):
                self.setCondFocusId(self.EPISODE_LIST_ID)
                self.episodeListControl.selectItem(pos)
            return True

        return False

    def onClick(self, controlID):
        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.EPISODE_LIST_ID:
            self.episodeListClicked()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID in (self.PLAY_BUTTON_ID, self.PLAY_BUTTON_ID+1000):
            self.playButtonClicked()
        elif controlID in (self.SHUFFLE_BUTTON_ID, self.SHUFFLE_BUTTON_ID+1000):
            self.shuffleButtonClicked()
        elif controlID in (self.OPTIONS_BUTTON_ID, self.OPTIONS_BUTTON_ID+1000):
            self.optionsButtonClicked()
        elif controlID in (self.SETTINGS_BUTTON_ID, self.SETTINGS_BUTTON_ID+1000):
            self.settingsButtonClicked()
        elif controlID == self.MEDIA_BUTTON_ID+1000:
            self.mediaButtonClicked()
        elif controlID in (self.INFO_BUTTON_ID, self.INFO_BUTTON_ID+1000):
            self.infoButtonClicked()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()
        elif controlID == self.SEASONS_LIST_ID:
            if self.fromWatchlist:
                return
            mli = self.seasonsListControl.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource
            if item != self.season:
                self.openItem(self.seasonsListControl, came_from=self.season.parentRatingKey)
            else:
                self.setCondFocusId(self.EPISODE_LIST_ID)
        elif controlID == self.ROLES_LIST_ID:
            if self.fromWatchlist:
                return
            if not self.roleClicked():
                return
        elif controlID == self.EXTRA_LIST_ID:
            self.openItem(self.extraListControl)
        elif controlID == self.RELATED_LIST_ID:
            self.openItem(self.relatedListControl)

    def onFocus(self, controlID):
        self.lastFocusID = controlID

        # we allow hidden focus on the play button when we're in multiple video files mode. in that case focus the
        # correct play button after the hidden one has been focused
        if controlID == self.PLAY_BUTTON_ID and xbmc.getCondVisibility(
                '!String.IsEmpty(Container(400).ListItem.Property(media.multiple))'):
            self.setCondFocusId(self.PLAY_BUTTON_ID + 1000)
            return

        if 399 < controlID < 500:
            self.setProperty('hub.focus', str(controlID - 400))
            if controlID == self.RELATED_LIST_ID:
                self.updateBackgroundFrom(self.relatedListControl.getSelectedItem().dataSource)
        if xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + [ControlGroup(300).HasFocus(0) | ControlGroup(1300).HasFocus(0)]'):
            self.setProperty('on.extras', '')
        elif xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + !ControlGroup(300).HasFocus(0) + !ControlGroup(1300).HasFocus(0)'):
            self.setProperty('on.extras', '1')

    def toggleWatched(self, mli=None, item=None, state=None, **kw):
        if not mli and not item:
            return

        item = item or mli.dataSource
        watched = super(EpisodesWindow, self).toggleWatched(item, state=state, **VIDEO_RELOAD_KW)
        if watched is None:
            return

        self.show_ = (self.episode or self.season).show().reload(includeExtras=1, includeExtrasCount=10,
                                                                 includeOnDeck=1)
        if watched:
            self.wl_auto_remove(self.show_)
            self.checkIsWatchlisted(self.show_)
        self.updateItems(mli)
        util.MONITOR.watchStatusChanged()

    def openItem(self, control=None, item=None, came_from=None):
        if not item:
            mli = control.getSelectedItem()
            if not mli:
                return
            item = mli.dataSource

        self.processCommand(opener.open(item, came_from=came_from))

    def roleClicked(self):
        if self.fromWatchlist:
            return

        return super(EpisodesWindow, self).roleClicked()

    def getRoleItemDDPosition(self, *args, **kwargs):
        y = 900
        if xbmc.getCondVisibility('Control.IsVisible(500)'):
            y += 380
        if xbmc.getCondVisibility('Control.IsVisible(501)'):
            y += 420
        if xbmc.getCondVisibility('!String.IsEmpty(Window.Property(on.extras))'):
            y -= 80
        if xbmc.getCondVisibility('Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(500)'):
            y -= 500
        if xbmc.getCondVisibility('Integer.IsGreater(Window.Property(hub.focus),1) + Control.IsVisible(501)'):
            y -= 500

        return super(EpisodesWindow, self).getRoleItemDDPosition(y=y, container_id="402")

    def getSeasons(self):
        if not self.seasons:
            self.seasons = self.show_.seasons()

        if not self.seasons:
            return False

        return True

    def next(self):
        if not self._next():
            return
        self.setup()

    __next__ = next

    @busy.dialog()
    def _next(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.season)
            if not mli:
                return False

            pos = mli.pos() + 1
            if not self.parentList.positionIsValid(pos):
                pos = 0

            self.season = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getSeasons():
                return False

            if self.season not in self.seasons:
                return False

            pos = self.seasons.index(self.season)
            pos += 1
            if pos >= len(self.seasons):
                pos = 0

            self.season = self.seasons[pos]

        return True

    def prev(self):
        if not self._prev():
            return
        self.setup()

    @busy.dialog()
    def _prev(self):
        if self.parentList:
            mli = self.parentList.getListItemByDataSource(self.season)
            if not mli:
                return False

            pos = mli.pos() - 1
            if pos < 0:
                pos = self.parentList.size() - 1

            self.season = self.parentList.getListItem(pos).dataSource
        else:
            if not self.getSeasons():
                return False

            if self.season not in self.seasons:
                return False

            pos = self.seasons.index(self.season)
            pos -= 1
            if pos < 0:
                pos = len(self.seasons) - 1

            self.season = self.seasons[pos]

        return True

    def searchButtonClicked(self):
        section_id = self.show_.getLibrarySectionId()
        self.processCommand(search.dialog(self, section_id=section_id or None))

    def playButtonClicked(self, shuffle=False, force_episode=None, from_auto_play=False, force_resume_menu=False):
        if shuffle:
            seasonOrShow = self.season or self.show_
            items = seasonOrShow.all()
            pl = playlist.LocalPlaylist(items, seasonOrShow.getServer())

            pl.shuffle(shuffle, first=True)
            videoplayer.play(play_queue=pl)
            return True

        else:
            return self.episodeListClicked(force_episode=force_episode, from_auto_play=from_auto_play,
                                           force_resume_menu=force_resume_menu)

    def shuffleButtonClicked(self):
        self.playButtonClicked(shuffle=True)

    def settingsButtonClicked(self):
        mli = self.episodeListControl.getSelectedItem()
        if not mli or mli.getProperty("is.boundary"):
            return

        episode = mli.dataSource

        if not episode.mediaChoice:
            playerObject = plexplayer.PlexPlayer(episode)
            playerObject.build()
        playersettings.showDialog(video=episode, non_playback=True)
        self.setItemAudioAndSubtitleInfo(episode, mli)

    def infoButtonClicked(self):
        mli = self.episodeListControl.getSelectedItem()
        if not mli or mli.getProperty("is.boundary"):
            return

        episode = mli.dataSource

        if episode.index:
            subtitle = u'{0} {1}'.format(T(32303, 'Season').format(episode.parentIndex),
                                         T(32304, 'Episode').format(episode.index))
        else:
            subtitle = episode.originallyAvailableAt.asDatetime('%B %d, %Y')

        hide_spoilers = self.hideSpoilers(episode)

        opener.handleOpen(
            info.InfoWindow,
            title=hide_spoilers and self.noTitles and T(33008, '') or episode.title,
            sub_title=subtitle,
            thumb=episode.thumb,
            thumb_opts=self.getThumbnailOpts(episode, hide_spoilers=hide_spoilers),
            thumb_fallback='script.plex/thumb_fallbacks/show.png',
            info=(hide_spoilers and self.noSummaries and T(33008, '')) or episode.summary,
            background=self.getProperty('background'),
            is_16x9=True,
            video=episode
        )
        self.cameFrom = "info"

    def episodeListClicked(self, force_episode=None, from_auto_play=False, force_resume_menu=False,
                           force_startover=False):
        if (not self.currentItemLoaded or self.playBtnClicked) and not from_auto_play:
            util.DEBUG_LOG("Not honoring play action: currentItemLoaded: {0}, "
                           "playBtnClicked: {1}, from_auto_play: {2}",
                           self.currentItemLoaded, self.playBtnClicked, from_auto_play)
            return

        if not force_episode:
            mli = self.episodeListControl.getSelectedItem()
            if not mli or mli.getProperty("is.boundary"):
                return

            episode = mli.dataSource
        else:
            episode = force_episode

        if not episode.available():
            util.messageDialog(T(32312, 'unavailable'), T(32332, 'This item is currently unavailable.'))
            return

        resume = False
        if episode.viewOffset.asInt() and not force_startover:
            if not util.getSetting('assume_resume') or force_resume_menu:
                choice = dropdown.showDropdown(
                    options=[
                        {'key': 'resume', 'display': T(32429, 'Resume from {0}').format(util.timeDisplay(episode.viewOffset.asInt()).lstrip('0').lstrip(':'))},
                        {'key': 'play', 'display': T(32317, 'Play from beginning')}
                    ],
                    pos=(660, "middle"),
                    close_direction='none',
                    set_dropdown_prop=False,
                    header=T(32314, 'In Progress'),
                    dialog_props=from_auto_play and self.dialogProps or None
                )

                if not choice:
                    return

                if choice['key'] == 'resume':
                    resume = True
            else:
                resume = True

        if not from_auto_play:
            self.playBtnClicked = True

        pl = playlist.LocalPlaylist(self.show_.all(), self.show_.getServer())
        try:
            # inject our show in case we need to access show metadata from the player
            episode._show = self.show_
            if len(pl) > 1:  # Don't use playlist if it's only this video
                for ep in pl:
                    ep._show = self.show_

                pl.setCurrent(episode)
                self.processCommand(videoplayer.play(play_queue=pl, resume=resume, bgm=self.useBGM))
                return True

            self.processCommand(videoplayer.play(video=episode, resume=resume, bgm=self.useBGM))
            return True
        except util.NoDataException:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
            self.doClose()

    def optionsButtonClicked(self, from_item=False):
        options = []

        mli = self.episodeListControl.getSelectedItem()

        if mli and not mli.getProperty("is.boundary"):
            inProgress = mli.dataSource.viewOffset.asInt()
            if inProgress and util.getSetting('assume_resume'):
                options.append({'key': 'play_startover', 'display': T(32317, 'Play from beginning')})
                options.append(dropdown.SEPARATOR)

            if not mli.dataSource.isWatched or inProgress:
                options.append({'key': 'mark_watched', 'display': T(32319, 'Mark Played')})
            if mli.dataSource.isWatched or inProgress:
                options.append({'key': 'mark_unwatched', 'display': T(32318, 'Mark Unplayed')})

            # if True:
            #     options.append({'key': 'add_to_playlist', 'display': '[COLOR FF808080]Add To Playlist[/COLOR]'})

        if xbmc.getCondVisibility('Player.HasAudio + MusicPlayer.HasNext'):
            options.append({'key': 'play_next', 'display': T(32325, 'Play Next')})

        if self.season:
            if self.season.isWatched:
                options.append({'key': 'mark_season_unwatched', 'display': T(32320, 'Mark Season Unplayed')})
            else:
                options.append({'key': 'mark_season_watched', 'display': T(32321, 'Mark Season Played')})

        if self.show_:
            if options:
                options.append(dropdown.SEPARATOR)

            options.append({'key': 'playback_settings', 'display': T(32925, 'Playback Settings')})
            options.append(dropdown.SEPARATOR)

        if plexapp.ACCOUNT.isAdmin:
            options.append({'key': 'refresh', 'display': T(33719, 'Refresh metadata')})

            if mli.dataSource.server.allowsMediaDeletion:
                options.append({'key': 'delete', 'display': T(32322, 'Delete')})

        # if xbmc.getCondVisibility('Player.HasAudio') and self.section.TYPE == 'artist':
        #     options.append({'key': 'add_to_queue', 'display': 'Add To Queue'})

        if options:
            options.append(dropdown.SEPARATOR)

        options.append({'key': 'to_show', 'display': T(32323, 'Go To Show')})
        options.append({'key': 'to_section', 'display': T(32324, u'Go to {0}').format(
            self.show_.getLibrarySectionTitle())})

        if 'items' in util.getSetting('cache_requests'):
            options.append({'key': 'cache_reset', 'display': T(33728, "Clear cache for item")})

        pos = (500, util.vscalei(620))
        bottom = False
        if from_item:
            viewPos = self.episodeListControl.getViewPosition()
            optsLen = len(list(filter(None, options)))
            # dropDown handles any overlap with the right window boundary, so we don't need to care here
            pos = (
                (((viewPos + 1) * 359) - 100),
                util.vscalei(649) if optsLen < 7 else 649 - util.vscalei(66) * (optsLen - 6))

        choice = dropdown.showDropdown(options, pos, pos_is_bottom=bottom, close_direction='left',
                                       set_dropdown_prop=False)
        if not choice:
            return

        if choice['key'] == 'play_next':
            xbmc.executebuiltin('PlayerControl(Next)')
        elif choice['key'] == 'mark_watched':
            self.toggleWatched(mli, state=True)
        elif choice['key'] == 'mark_unwatched':
            self.toggleWatched(mli, state=False)
        elif choice['key'] == 'mark_season_watched':
            self.toggleWatched(item=self.season, state=True)
        elif choice['key'] == 'mark_season_unwatched':
            self.toggleWatched(item=self.season, state=False)
        elif choice['key'] == 'to_show':
            self.cameFrom = "show"
            self.processCommand(opener.open(
                self.season.parentRatingKey,
                came_from=self.season.parentRatingKey)
            )
        elif choice['key'] == 'to_section':
            self.cameFrom = "library"
            section = plexlibrary.LibrarySection.fromFilter(self.show_)
            self.processCommand(opener.sectionClicked(section,
                came_from=self.show_.ratingKey)
            )
        elif choice['key'] == 'delete':
            self.delete(mli.dataSource)
        elif choice['key'] == 'playback_settings':
            self.playbackSettings(self.show_, pos, bottom)
        elif choice['key'] == 'refresh':
            mli.dataSource.refresh()
            self.updateItems(mli)
        elif choice['key'] == 'play_startover':
            self.episodeListClicked(force_startover=True)
        elif choice["key"] == "cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for {}...', mli.dataSource)
                mli.dataSource.clearCache()
                mli.dataSource.reload()
                self.updateItems(mli)
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear cache: {}", e)

    def mediaButtonClicked(self):
        options = []
        mli = self.episodeListControl.getSelectedItem()
        ds = mli.dataSource
        for media in ds.media:
            ind = ''
            if ds.mediaChoice and media.id == ds.mediaChoice.media.id:
                ind = 'script.plex/home/device/check.png'
            options.append({'key': media, 'display': media.versionString(), 'indicator': ind})
        choice = dropdown.showDropdown(options, header=T(32450, 'Choose Version'), with_indicator=True)
        if not choice:
            return False

        for media in ds.media:
            media.set('selected', '')

        ds.setMediaChoice(choice['key'])
        choice['key'].set('selected', 1)
        pnUtil.INTERFACE.playbackManager(mli.dataSource, key="media_version", value=choice['key'].id)
        self.setPostReloadItemInfo(ds, mli)

    def delete(self, item):
        button = optionsdialog.show(
            T(32326, 'Really delete?'),
            T(33036, "Delete episode S{0:02d}E{1:02d} from {2}?").format(item.parentIndex.asInt(),
                                                                         item.index.asInt(), item.defaultTitle),
            T(32328, 'Yes'),
            T(32329, 'No')
        )

        if button != 0:
            return

        if not self._delete():
            util.messageDialog(T(32330, 'Message'), T(32331, 'There was a problem while attempting to delete the media.'))

    @busy.dialog()
    def _delete(self):
        mli = self.episodeListControl.getSelectedItem()
        if not mli or mli.getProperty("is.boundary"):
            return

        video = mli.dataSource
        success = video.delete()
        util.LOG('Media DELETE: {0} - {1}', video, success and 'SUCCESS' or 'FAILED')
        if success:
            self.episodeListControl.removeItem(mli.pos())
            if not self.episodeListControl.size():
                self.doClose()
            else:
                (self.season or self.show_).reload()
        return success

    def checkForHeaderFocus(self, action, initial=False):
        # don't continue if we're still waiting for tasks
        if self.tasks or not self.episodesPaginator:
            if self.tasks and not initial:
                util.DEBUG_LOG("Episodes: Moving too fast through paginator, throttling.")
            return

        if self.episodesPaginator.boundaryHit:
            items = self.episodesPaginator.paginate()
            self.reloadItems(items)
            return True

        mli = self.episodeListControl.getSelectedItem()
        if not mli or mli.getProperty("is.boundary"):
            return

        lastItem = self.lastItem

        if action in (xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_MOVE_LEFT) and lastItem:
            items = self.episodesPaginator.wrap(mli, lastItem, action)
            #xbmc.sleep(100)
            mli = self.episodeListControl.getSelectedItem()
            if items:
                self.reloadItems(items)
                return True

        if mli != self.lastItem and not mli.getProperty("is.boundary"):
            self.lastItem = mli
            self.setProgress(mli)
            self.fillRoles(self.relatedPaginator and self.relatedPaginator.leafCount)

        if action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_PAGE_UP):
            if mli.getProperty('is.header'):
                xbmc.executebuiltin('Action(up)')
        if action in (xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_DOWN, xbmcgui.ACTION_MOVE_LEFT,
                      xbmcgui.ACTION_MOVE_RIGHT):
            if not initial and action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                self.manuallySelected = True
            if mli.getProperty('is.header'):
                xbmc.executebuiltin('Action(down)')

    def updateProperties(self):
        showTitle = self.show_ and self.show_.title or ''
        self.setBoolProperty('disable_playback', self.fromWatchlist)
        self.setBoolProperty('current_item.loaded', False)
        self.updateBackgroundFrom(self.season or self.show_)
        self.setProperty('season.thumb', (self.season or self.show_).thumb.asTranscodedImageURL(*self.POSTER_DIM))
        self.setProperty('show.title', showTitle)
        self.setProperty('season.title', (self.season or self.show_).title)

        if self.season:
            self.setProperty('episodes.header', u'{0} \u2022 {1}'.format(showTitle,
                                                                         T(32303, 'Season').format(self.season.index)))
            self.setProperty('extras.header', u'{0} \u2022 {1}'.format(T(32305, 'Extras'),
                                                                       T(32303, 'Season').format(self.season.index)))
        else:
            self.setProperty('episodes.header', u'Episodes')
            self.setProperty('extras.header', u'Extras')

        self.setProperty('seasons.header',
                         u'{0} \u2022 {1}'.format(showTitle, T(32942, 'Seasons')))
        self.setProperty('related.header', T(32306, 'Related Shows'))
        self.genre = self.show_.genres() and self.show_.genres()[0].tag or ''

    @busy.dialog()
    def updateItems(self, item=None):
        if item:
            item.setProperty('unwatched', not item.dataSource.isWatched and '1' or '')
            item.setProperty('watched', item.dataSource.isFullyWatched and '1' or '')
            self.setProgress(item)
            item.setProperty('progress', util.getProgressImage(item.dataSource))
            (self.season or self.show_).reload()

            if self.noRatings:
                self.populateRatings(item.dataSource, item, hide_ratings=self.hideSpoilers(item.dataSource))
            self.setUserItemInfo(item)
        else:
            self.fillEpisodes(update=True)
            if not self.cameFrom:
                VIDEO_PROGRESS.clear()

        if self.episode:
            self.episode.reload()

    def setUserItemInfo(self, mli, video=None, types=("title", "thumbnail", "summary"), watched=None,
                        fully_watched=None, hide_spoilers=None):
        video = video or mli.dataSource

        properties = {}
        methods = []
        if self.noSpoilers == "off" and not hide_spoilers:
            # no special handling
            if "title" in types:
                properties["title"] = video.title
                methods.append(("setLabel", video.title))
            if "summary" in types:
                properties["summary"] = video.summary.strip().replace('\t', ' ')

            if "thumbnail" in types:
                methods.append(("setThumbnailImage", video.thumb.asTranscodedImageURL(*self.THUMB_AR16X9_DIM)))

        else:
            hide_spoilers = hide_spoilers if hide_spoilers is not None else \
                self.hideSpoilers(video, fully_watched=fully_watched, watched=watched)
            hide_title = hide_spoilers and self.noTitles
            if "title" in types:
                tit = hide_title and T(33008, '') or video.title
                properties["title"] = tit
                methods.append(("setLabel", tit))

            if "summary" in types:
                properties["summary"] = ((hide_spoilers and self.noSummaries and T(33008, '')) or
                                         video.summary.strip().replace('\t', ' '))

            if "thumbnail" in types:
                methods.append(("setThumbnailImage",
                                video.thumb.asTranscodedImageURL(
                                    *self.THUMB_AR16X9_DIM,
                                    **self.getThumbnailOpts(video, fully_watched=fully_watched, watched=watched,
                                                            hide_spoilers=hide_spoilers)
                                )
                                ))

        for property, value in properties.items():
            mli.setProperty(property, value)

        for method, value in methods:
            getattr(mli, method)(value)

    def setItemInfo(self, video, mli):
        # video.reload(checkFiles=1)
        mli.setProperty('background', util.backgroundFromArt(video.art, width=self.width, height=self.height))
        mli.setProperty('show.title', video.grandparentTitle or (self.show_.title if self.show_ else ''))
        mli.setProperty('duration', util.durationToText(video.duration.asInt()))
        mli.setProperty('video.rendering', video.videoCodecRendering)
        self.setUserItemInfo(mli, video, types=("title", "summary"))

        if video.index:
            mli.setProperty('season', T(32303, 'Season').format(video.parentIndex))
            mli.setProperty('episode', T(32304, 'Episode').format(video.index))
        else:
            mli.setProperty('season', '')
            mli.setProperty('episode', '')

        mli.setProperty('date', util.cleanLeadingZeros(video.originallyAvailableAt.asDatetime('%B %d, %Y')))

        # mli.setProperty('related.header', 'Related Shows')
        mli.setProperty('year', video.year)
        mli.setProperty('content.rating', video.contentRating.split('/', 1)[-1])
        mli.setProperty('genre', self.genre)
        self.populateRatings(video, mli, hide_ratings=self.hideSpoilers(video) and self.noRatings)

    def setPostReloadItemInfo(self, video, mli):
        if not self.fromWatchlist:
            self.setItemAudioAndSubtitleInfo(video, mli)
            mli.setProperty('unwatched', not video.isWatched and '1' or '')
            mli.setProperty('watched', video.isFullyWatched and '1' or '')
            mli.setProperty('video.res', video.resolutionString())
            mli.setProperty('audio.codec', video.audioCodecString())
            mli.setProperty('video.codec', video.videoCodecString())
            mli.setProperty('audio.channels', video.audioChannelsString(metadata.apiTranslate))
            mli.setProperty('video.rendering', video.videoCodecRendering)
            mli.setBoolProperty('unavailable', not video.available())
            mli.setBoolProperty('media.multiple', len(list(filter(lambda x: x.isAccessible(), video.media()))) > 1)

        directors = u' / '.join([d.tag for d in video.directors()][:2])
        directorsLabel = len(video.directors) > 1 and T(32401, u'DIRECTORS').upper() or T(32383,
                                                                                          u'DIRECTOR').upper()
        mli.setProperty('directors', directors and u'{0}    {1}'.format(directorsLabel, directors) or '')
        writers = u' / '.join([r.tag for r in video.writers()][:2])
        writersLabel = len(video.writers) > 1 and T(32403, u'WRITERS').upper() or T(32402, u'WRITER').upper()
        mli.setProperty('writers',
                        writers and u'{0}{1}    {2}'.format(directors and '    ' or '', writersLabel, writers) or '')

    def setItemAudioAndSubtitleInfo(self, video, mli):
        sas = video.selectedAudioStream()

        if sas:
            if len(video.audioStreams) > 1:
                mli.setProperty(
                    'audio', sas and u'{0} \u2022 {1} {2}'.format(sas.getTitle(metadata.apiTranslate),
                                                                  len(video.audioStreams) - 1, T(32307, 'More'))
                    or T(32309, 'None')
                )
            else:
                mli.setProperty('audio', sas and sas.getTitle(metadata.apiTranslate) or T(32309, 'None'))

        sss = video.selectedSubtitleStream(forced_subtitles_override=
                                           util.getSetting("forced_subtitles_override") and pnUtil.ACCOUNT.subtitlesForced == 0,
                                           deselect_subtitles=util.getSetting("disable_subtitle_languages"))
        if sss:
            if len(video.subtitleStreams) > 1:
                mli.setProperty(
                    'subtitles', u'{0} \u2022 {1} {2}'.format(sss.getTitle(metadata.apiTranslate), len(video.subtitleStreams) - 1, T(32307, 'More'))
                )
            else:
                mli.setProperty('subtitles', sss.getTitle(metadata.apiTranslate))
        else:
            if video.subtitleStreams:
                mli.setProperty('subtitles', u'{0} \u2022 {1} {2}'.format(T(32309, 'None'), len(video.subtitleStreams), T(32308, 'Available')))
            else:
                mli.setProperty('subtitles', T(32309, 'None'))

    def setProgress(self, mli, view_offset=None):
        video = mli.dataSource
        view_offset = view_offset if view_offset is not None else video.viewOffset.asInt()
        if view_offset:
            width = view_offset and (1 + int((view_offset / video.duration.asFloat()) * self.width)) or 1
            self.progressImageControl.setWidth(width)
        else:
            self.progressImageControl.setWidth(1)

        if view_offset:
            mli.setProperty('remainingTime', T(33615,
                                               "{time} left").format(time=video._remainingTimeString(view_offset)))
        else:
            mli.setProperty('remainingTime', '')

    def createListItem(self, episode):
        if episode.index:
            subtitle = u'{0} \u2022 {1}'.format(T(32310, 'S').format(episode.parentIndex),
                                                T(32311, 'E').format(episode.index))
        else:
            subtitle = episode.originallyAvailableAt.asDatetime('%m/%d/%y')

        mli = kodigui.ManagedListItem(
            '',
            subtitle,
            data_source=episode
        )
        self.setUserItemInfo(mli, types=("title", "thumbnail"))
        mli.setProperty('episode.number', str(episode.index) or '')
        mli.setProperty('episode.duration', util.durationToText(episode.duration.asInt()))
        mli.setProperty('unwatched', not episode.isWatched and '1' or '')
        mli.setProperty('watched', episode.isFullyWatched and '1' or '')
        # mli.setProperty('progress', util.getProgressImage(obj))
        return mli

    def fillEpisodes(self, update=False):
        items = self.episodesPaginator.paginate()
        if not update:
            self.selectEpisode()
        self.reloadItems(items, with_progress=True)

    def reloadItems(self, items, with_progress=False, skip_progress_for=None, set_item_info=False):
        tasks = []
        for mli in items:
            if not mli.dataSource:
                continue

            item_progress = with_progress
            if skip_progress_for:
                item_progress = False if mli.dataSource.ratingKey in skip_progress_for else with_progress

            task = EpisodeReloadTask().setup(mli.dataSource, self.reloadItemCallback, with_progress=item_progress,
                                             set_item_info=set_item_info)
            self.tasks.add(task)
            tasks.append(task)

        backgroundthread.BGThreader.addTasks(tasks)

    def getPlayButtonID(self, mli, base=None):
        return (base and base or self.PLAY_BUTTON_ID) + (mli.getProperty('media.multiple') and 1000 or 0)

    def reloadItemCallback(self, task, episode, with_progress=False, set_item_info=False):
        self.tasks.remove(task)
        del task

        if self.closing:
            return

        selected = self.episodeListControl.getSelectedItem()

        for mli in self.episodeListControl:
            if mli.dataSource == episode:
                if not episode.mediaChoice:
                    episode.setMediaChoice()

                try:
                    self.setPostReloadItemInfo(episode, mli)
                    if set_item_info:
                        self.setUserItemInfo(mli)
                except:
                    util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
                    self.doClose()

                if with_progress:
                    self.episodesPaginator.prepareListItem(None, mli)
                if mli == selected:
                    self.lastItem = mli
                    if with_progress:
                        self.setProgress(mli)

                if not self.currentItemLoaded and (
                        mli == selected or (self.episode and self.episode == mli.dataSource)):
                    self.currentItemLoaded = True
                    self.setBoolProperty('current_item.loaded', True)
                    if not self.lastFocusID or self.lastFocusID in (
                            self.PLAY_BUTTON_DISABLED_ID, self.PLAY_BUTTON_DISABLED_ID + 1000):
                        # wait for visibility of the button
                        tries = 0
                        PBID = self.getPlayButtonID(mli)
                        while not xbmc.getCondVisibility('Control.IsVisible({})'.format(PBID)) \
                                and not util.MONITOR.abortRequested() and tries < 15:
                            util.MONITOR.waitForAbort(0.1)
                            tries += 1
                        if xbmc.getCondVisibility('Control.IsVisible({})'.format(PBID)) and self.getFocusId() != PBID:
                            self.setFocusId(PBID)

                break

    def fillExtras(self, has_prev=False):
        items = []
        idx = 0

        seasonOrShow = self.season or self.show_

        if not seasonOrShow.extras:
            self.extraListControl.reset()
            return False

        for extra in seasonOrShow.extras():
            mli = kodigui.ManagedListItem(
                extra.title or '',
                metadata.EXTRA_MAP.get(extra.extraType.asInt(), ''),
                thumbnailImage=extra.thumb.asTranscodedImageURL(*self.EXTRA_DIM),
                data_source=extra
            )

            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty(
                    'thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(extra.type in ('show', 'season', 'episode') and 'show' or 'movie')
                )
                items.append(mli)
                idx += 1

        if not items:
            return False

        self.extraListControl.reset()
        self.extraListControl.addItems(items)
        return True

    def fillRelated(self, has_prev=False):
        if not self.relatedPaginator or not self.relatedPaginator.leafCount:
            self.relatedListControl.reset()
            return has_prev

        items = self.relatedPaginator.paginate()
        if not items:
            return False

        return True

    def fillRoles(self, has_prev=False):
        items = []
        idx = 0

        ds = self.episodeListControl.getSelectedItem().dataSource

        if not ds.roles:
            self.rolesListControl.reset()
            return False

        for role in ds.combined_roles:
            mli = kodigui.ManagedListItem(role.tag, role.role or
                                          util.TRANSLATED_ROLES[role.translated_role],
                                          thumbnailImage=role.thumb.asTranscodedImageURL(*self.ROLES_DIM),
                                          data_source=role)
            mli.setProperty('index', str(idx))
            items.append(mli)
            idx += 1

        if not items:
            return False

        self.rolesListControl.reset()
        self.rolesListControl.addItems(items)
        return True
