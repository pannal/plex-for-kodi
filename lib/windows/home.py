from __future__ import absolute_import

import json
import threading
import time
import math

import plexnet
from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import plexapp, plexresource
from six.moves import range

from lib import backgroundthread
from lib import player
from lib import util
from lib.path_mapping import pmm
from lib.plex_hosts import pdm
from lib.util import T
from . import busy
from . import dropdown
from . import kodigui
from . import opener
from . import optionsdialog
from . import playlists
from . import search
from . import windowutils
from . import background
from .mixins import SpoilersMixin, removeFromWatchlistBlind

HUBS_REFRESH_INTERVAL = 300  # 5 Minutes
HUB_PAGE_SIZE = 10

MOVE_SET = frozenset(
    (
        xbmcgui.ACTION_MOVE_LEFT,
        xbmcgui.ACTION_MOVE_RIGHT,
        xbmcgui.ACTION_MOVE_UP,
        xbmcgui.ACTION_MOVE_DOWN,
        xbmcgui.ACTION_MOUSE_MOVE,
        xbmcgui.ACTION_PAGE_UP,
        xbmcgui.ACTION_PAGE_DOWN,
        xbmcgui.ACTION_FIRST_PAGE,
        xbmcgui.ACTION_LAST_PAGE,
        xbmcgui.ACTION_MOUSE_WHEEL_DOWN,
        xbmcgui.ACTION_MOUSE_WHEEL_UP
    )
)


class HubsList(list):
    def init(self):
        self.lastUpdated = time.time()
        self.invalid = False
        return self


class SectionHubsTask(backgroundthread.Task):
    def setup(self, section, callback, section_keys=None, ignore_hubs=None, reselect_pos_dict=None):
        self.section = section
        self.callback = callback
        self.section_keys = section_keys
        self.ignore_hubs = ignore_hubs
        self.reselect_pos_dict = reselect_pos_dict
        return self

    def run(self):
        if self.isCanceled():
            return

        if not plexapp.SERVERMANAGER.selectedServer or not self.section.server:
            # Could happen during sign-out for instance
            return

        try:
            hubs = HubsList(self.section.server.hubs(self.section.key, count=HUB_PAGE_SIZE,
                                                                      section_ids=self.section_keys,
                                                                      ignore_hubs=self.ignore_hubs)).init()
            if self.isCanceled():
                return
            self.callback(self.section, hubs, reselect_pos_dict=self.reselect_pos_dict)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on section: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)
        except:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
            util.DEBUG_LOG('Generic exception when fetching section: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)


class UpdateHubTask(backgroundthread.Task):
    def setup(self, hub, callback, reselect_pos=None):
        self.hub = hub
        self.callback = callback
        self.reselect_pos = reselect_pos
        return self

    def run(self):
        if self.isCanceled():
            return

        if not plexapp.SERVERMANAGER.selectedServer:
            # Could happen during sign-out for instance
            return

        try:
            self.hub.reload(limit=HUB_PAGE_SIZE)
            if self.isCanceled():
                return
            self.callback(self.hub, reselect_pos=self.reselect_pos)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on hub: {0}', repr(self.hub.hubIdentifier))
        except util.NoDataException:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
        except:
            util.DEBUG_LOG('Something went wrong when updating hub: {0}', repr(self.hub.hubIdentifier))


class ExtendHubTask(backgroundthread.Task):
    def setup(self, hub, callback, canceledCallback=None, size=HUB_PAGE_SIZE, reselect_pos=None):
        self.hub = hub
        self.callback = callback
        self.canceledCallback = canceledCallback
        self.size = size
        self.reselect_pos = reselect_pos
        return self

    def run(self):
        if self.isCanceled():
            if self.canceledCallback:
                self.canceledCallback(self.hub)
            return

        if not plexapp.SERVERMANAGER.selectedServer:
            # Could happen during sign-out for instance
            return

        try:
            size = self.size
            if self.reselect_pos is not None:
                rk, pos = self.reselect_pos
                if pos == -1:
                    # we need the full hub if we want to round-robin
                    size = util.addonSettings.hubsRrMax
            start = self.hub.offset.asInt() + self.hub.size.asInt()
            items = self.hub.extend(start=start, size=size)
            if self.isCanceled():
                if self.canceledCallback:
                    self.canceledCallback(self.hub)
                return
            self.callback(self.hub, items, reselect_pos=self.reselect_pos)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on hub: {0}', repr(self.hub.hubIdentifier))
            if self.canceledCallback:
                self.canceledCallback(self.hub)
        except util.NoDataException:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
        except:
            util.DEBUG_LOG('Something went wrong when extending hub: {0}', repr(self.hub.hubIdentifier))
            util.ERROR()


class VirtualSection(object):
    locations = []
    isMapped = False

    @property
    def server(self):
        return plexapp.SERVERMANAGER.selectedServer


class HomeSection(VirtualSection):
    key = None
    type = 'home'
    title = T(32332, 'Home')

    locations = []
    isMapped = False


home_section = HomeSection()

watchlist_section = None


class PlaylistsSection(VirtualSection):
    key = 'playlists'
    type = 'playlists'
    title = T(32333, 'Playlists')

    locations = []
    isMapped = False


playlists_section = PlaylistsSection()


class ServerListItem(kodigui.ManagedListItem):
    uuid = None

    def hookSignals(self):
        self.dataSource.on('completed:reachability', self.onReachability)
        self.dataSource.on('started:reachability', self.onReachability)

    def unHookSignals(self):
        try:
            self.dataSource.off('completed:reachability', self.onReachability)
            self.dataSource.off('started:reachability', self.onReachability)
        except:
            pass

    def setRefreshing(self):
        self.safeSetProperty('status', 'refreshing.gif')

    def safeSetProperty(self, key, value):
        # For if we catch the item in the middle of being removed
        try:
            self.setProperty(key, value)
            return True
        except AttributeError:
            pass

        return False

    def safeSetLabel(self, value, func="setLabel"):
        if value is None:
            return False
        try:
            getattr(self, func)(value)
            return True
        except AttributeError:
            pass

        return False

    def safeGetDSProperty(self, prop):
        return getattr(self.dataSource, prop, None)

    def onReachability(self, **kwargs):
        plexapp.util.APP.trigger('sli:reachability:received')
        return self.onUpdate(**kwargs)

    def onUpdate(self, **kwargs):
        if not self.listItem:  # ex. can happen on Kodi shutdown
            return

        if self.dataSource == kodigui.DUMMY_DATA_SOURCE:
            return

        # this looks a little ridiculous, but we're experiencing timing issues here
        isSupported = self.safeGetDSProperty("isSupported")
        isReachable = False
        isReachableFunc = self.safeGetDSProperty("isReachable")
        isSecure = self.safeGetDSProperty("isSecure")
        isLocal = self.safeGetDSProperty("isLocal")
        name = self.safeGetDSProperty("name")
        pendingReachabilityRequests = self.safeGetDSProperty("pendingReachabilityRequests")
        owned = not self.safeGetDSProperty("owned") and self.safeGetDSProperty("owner") or ''
        if isReachableFunc:
            isReachable = isReachableFunc()

        if not isSupported or not isReachable:
            if pendingReachabilityRequests is not None and pendingReachabilityRequests > 0:
                self.safeSetProperty('status', 'refreshing.gif')
            else:
                self.safeSetProperty('status', 'unreachable.png')
        else:
            self.safeSetProperty('status', isSecure and 'secure.png' or '')
            self.safeSetProperty('secure', isSecure and '1' or '')
            self.safeSetProperty('local', isLocal and '1' or '')

        if plexapp.SERVERMANAGER.selectedServer:
            self.safeSetProperty('current', plexapp.SERVERMANAGER.selectedServer.uuid == self.uuid and '1' or '')
        if name:
            self.safeSetLabel(name)

        if owned:
            self.safeSetLabel(owned, func="setLabel2")

    def onDestroy(self):
        self.unHookSignals()


class HomeWindow(kodigui.BaseWindow, util.CronReceiver, SpoilersMixin):
    xmlFile = 'script-plex-home.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    OPTIONS_GROUP_ID = 200

    SECTION_LIST_ID = 101
    SERVER_BUTTON_ID = 201

    USER_BUTTON_ID = 202
    USER_LIST_ID = 250

    SEARCH_BUTTON_ID = 203
    SERVER_LIST_ID = 260
    REFRESH_SL_ID = 262

    PLAYER_STATUS_BUTTON_ID = 204

    HUB_AR16X9_00 = 400
    HUB_POSTER_01 = 401
    HUB_POSTER_02 = 402
    HUB_POSTER_03 = 403
    HUB_POSTER_04 = 404
    HUB_SQUARE_05 = 405
    HUB_AR16X9_06 = 406
    HUB_POSTER_07 = 407
    HUB_POSTER_08 = 408
    HUB_SQUARE_09 = 409
    HUB_SQUARE_10 = 410
    HUB_SQUARE_11 = 411
    HUB_SQUARE_12 = 412
    HUB_POSTER_13 = 413
    HUB_POSTER_14 = 414
    HUB_POSTER_15 = 415
    HUB_POSTER_16 = 416
    HUB_AR16X9_17 = 417
    HUB_AR16X9_18 = 418
    HUB_AR16X9_19 = 419

    HUB_SQUARE_20 = 420
    HUB_SQUARE_21 = 421
    HUB_SQUARE_22 = 422

    HUB_AR16X9_23 = 423

    HUBMAP = {
        # HOME
        'home.continue': {'index': 0, 'with_progress': True, 'with_art': True, 'do_updates': True, 'text2lines': True},
        # This hub can be enabled in the settings so PM4K behaves like any other Plex client.
        # It overrides home.continue and home.ondeck
        'continueWatching': {'index': 1, 'with_progress': True, 'do_updates': True, 'text2lines': True},
        'home.ondeck': {'index': 1, 'with_progress': True, 'do_updates': True, 'text2lines': True},
        'home.television.recent': {'index': 2, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        # This is a virtual hub and it appears when the library recommendation is customized in Plex and
        # Recently Released is checked.
        'home.VIRTUAL.movies.recentlyreleased': {'index': 3, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'home.movies.recent': {'index': 4, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'home.music.recent': {'index': 5, 'text2lines': True},
        'home.videos.recent': {'index': 6, 'with_progress': True, 'ar16x9': True},
        #'home.playlists': {'index': 9}, # No other Plex home screen shows playlists so removing it from here
        'home.photos.recent': {'index': 10, 'text2lines': True},
        # SHOW
        'tv.inprogress': {'index': 1, 'with_progress': True, 'do_updates': True, 'text2lines': True},
        'tv.ondeck': {'index': 2, 'with_progress': True, 'do_updates': True, 'text2lines': True},
        'tv.recentlyaired': {'index': 3, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'tv.recentlyadded': {'index': 4, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'tv.startwatching': {'index': 7, 'with_progress': True, 'do_updates': True},
        'tv.rediscover': {'index': 8, 'with_progress': True, 'do_updates': True},
        'tv.morefromnetwork': {'index': 13, 'with_progress': True, 'do_updates': True},
        'tv.toprated': {'index': 14, 'with_progress': True, 'do_updates': True},
        'tv.moreingenre': {'index': 15, 'with_progress': True, 'do_updates': True},
        'tv.recentlyviewed': {'index': 16, 'with_progress': True, 'text2lines': True, 'do_updates': True},
        # MOVIE
        'movie.inprogress': {'index': 0, 'with_progress': True, 'with_art': True, 'do_updates': True, 'text2lines': True},
        'movie.recentlyreleased': {'index': 1, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'movie.recentlyadded': {'index': 2, 'do_updates': True, 'with_progress': True, 'text2lines': True},
        'movie.genre': {'index': 3, 'with_progress': True, 'text2lines': True, 'do_updates': True},
        'movie.by.actor.or.director': {'index': 7, 'with_progress': True, 'text2lines': True, 'do_updates': True},
        'movie.topunwatched': {'index': 13, 'text2lines': True, 'do_updates': True},
        'movie.recentlyviewed': {'index': 14, 'with_progress': True, 'text2lines': True, 'do_updates': True},
        # ARTIST
        'music.recent.played': {'index': 5, 'do_updates': True},
        'music.recent.added': {'index': 9, 'text2lines': True},
        'music.recent.artist': {'index': 10, 'text2lines': True},
        'music.recent.genre': {'index': 11, 'text2lines': True},
        'music.top.period': {'index': 12, 'text2lines': True},
        'music.popular': {'index': 20, 'text2lines': True},
        'music.recent.label': {'index': 21, 'text2lines': True},
        'music.touring': {'index': 22},
        'music.videos.popular.new': {'index': 18},
        'music.videos.new': {'index': 19},
        'music.videos.recent.artists': {'index': 23},
        # PHOTO
        'photo.recent': {'index': 5, 'text2lines': True},
        'photo.random.year': {'index': 9, 'text2lines': True},
        'photo.random.decade': {'index': 10, 'text2lines': True},
        'photo.random.dayormonth': {'index': 11, 'text2lines': True},
        # VIDEO
        'video.recent': {'index': 0, 'with_progress': True, 'ar16x9': True},
        'video.random.year': {'index': 6, 'with_progress': True, 'ar16x9': True},
        'video.random.decade': {'index': 17, 'with_progress': True, 'ar16x9': True},
        'video.inprogress': {'index': 18, 'with_progress': True, 'ar16x9': True},
        'video.unwatched.random': {'index': 19, 'ar16x9': True},
        'video.recentlyviewed': {'index': 23, 'with_progress': True, 'ar16x9': True},
        # PLAYLISTS
        'playlists.audio': {'index': 5, 'text2lines': True, 'title': T(32048, 'Audio')},
        'playlists.video': {'index': 6, 'text2lines': True, 'ar16x9': True, 'title': T(32053, 'Video')},
        # WATCHLIST
        'watchlist.continueWatching': {'index': 1, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'watchlist.coming-soon': {'index': 2, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'watchlist.recently-added': {'index': 3, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'home.top_watchlisted': {'index': 4, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'home.coming-soon': {'index': 7, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'home.trending-friends': {'index': 8, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'home.trending-for-you': {'index': 13, 'with_progress': False, 'do_updates': True, 'text2lines': True},
        'home.new-for-you': {'index': 14, 'with_progress': False, 'do_updates': True, 'text2lines': True},
    }

    THUMB_POSTER_DIM = util.scaleResolution(244, 361)
    THUMB_AR16X9_DIM = util.scaleResolution(532, 299)
    THUMB_SQUARE_DIM = util.scaleResolution(244, 244)

    def __init__(self, *args, **kwargs):
        kodigui.BaseWindow.__init__(self, *args, **kwargs)
        SpoilersMixin.__init__(self, *args, **kwargs)
        self.lastSection = home_section
        self.tasks = []
        self.closeOption = None
        self.hubControls = None
        self.backgroundSet = False
        self.sectionChangeThread = None
        self.sectionChangeTimeout = 0
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.sectionHubs = {}
        self.updateHubs = {}
        self.changingServer = False
        self._shuttingDown = False
        self._checkingForExit = False
        self._skipNextAction = False
        self._reloadOnReinit = False
        self._applyTheme = False
        self._ignoreTick = False
        self._ignoreInput = False
        self._ignoreReInit = False
        self._restarting = False
        self._anyItemAction = False
        self._odHubsDirty = False
        self._updateSourceChanged = False
        self.librarySettings = None
        self.hubSettings = None
        self.anyLibraryHidden = False
        self.wantedSections = None
        self.movingSection = False
        self._initialMovingSectionPos = None
        self.block_section_change = False
        self.go_root = False
        windowutils.HOME = self

        self.lock = threading.Lock()

        util.setGlobalBoolProperty('off.sections', '')

    def onFirstInit(self):
        # set last BG image if possible
        if util.addonSettings.dynamicBackgrounds:
            bgUrl = util.getSetting("last_bg_url.{}".format(plexapp.ACCOUNT.ID))
            if bgUrl:
                self.windowSetBackground(bgUrl)

        # set good volume if we've missed re-setting BGM volume before
        lastGoodVlm = util.getSetting('last_good_volume', 0)
        BGMVlm = plexapp.util.INTERFACE.getThemeMusicValue()
        if lastGoodVlm and BGMVlm and util.rpc.Application.GetProperties(properties=["volume"])["volume"] == BGMVlm:
            util.DEBUG_LOG("Setting volume to {}, we probably missed the "
                           "re-set on the last BGM encounter".format(lastGoodVlm))
            xbmc.executebuiltin("SetVolume({})".format(lastGoodVlm))

        self.sectionList = kodigui.ManagedControlList(self, self.SECTION_LIST_ID, 7)
        self.serverList = kodigui.ManagedControlList(self, self.SERVER_LIST_ID, 10)
        self.userList = kodigui.ManagedControlList(self, self.USER_LIST_ID, 3)

        self.hubControls = (
            kodigui.ManagedControlList(self, self.HUB_AR16X9_00, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_01, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_02, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_03, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_04, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_05, 5),
            kodigui.ManagedControlList(self, self.HUB_AR16X9_06, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_07, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_08, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_09, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_10, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_11, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_12, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_13, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_14, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_15, 5),
            kodigui.ManagedControlList(self, self.HUB_POSTER_16, 5),
            kodigui.ManagedControlList(self, self.HUB_AR16X9_17, 5),
            kodigui.ManagedControlList(self, self.HUB_AR16X9_18, 5),
            kodigui.ManagedControlList(self, self.HUB_AR16X9_19, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_20, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_21, 5),
            kodigui.ManagedControlList(self, self.HUB_SQUARE_22, 5),
            kodigui.ManagedControlList(self, self.HUB_AR16X9_23, 5),
        )

        self.hubFocusIndexes = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18, 19, 20, 21, 22, 13, 14, 15, 23)

        self.bottomItem = 0
        if self.serverRefresh():
            self.setFocusId(self.SECTION_LIST_ID)

        self.hookSignals()
        util.CRON.registerReceiver(self)
        self.updateProperties()
        self.checkPlexDirectHosts(plexapp.SERVERMANAGER.serversByUuid.values(), source="stored")

    def closeWRecompileTpls(self):
        self._applyTheme = False
        self._shuttingDown = True
        self.closeOption = "recompile"
        self.doClose()

    def onReInit(self):
        util.DEBUG_LOG("Home: On ReInit")
        if self._ignoreReInit:
            return

        if player.PLAYER.bgmPlaying:
            player.PLAYER.stopAndWait()

        self._anyItemAction = False
        if self._applyTheme:
            self.closeWRecompileTpls()
            return

        if self.go_root:
            self.setProperty('hub.focus', '')
            self.setFocusId(self.SECTION_LIST_ID)
            self.sectionList.setSelectedItemByPos(0)
            # somehow we need to do this as well.
            xbmc.executebuiltin('Control.SetFocus({0}, {1})'.format(self.SECTION_LIST_ID, 0))
            self.go_root = False
            return

        if self._reloadOnReinit:
            self.serverRefresh()
            self._reloadOnReinit = False

        if self.lastFocusID:
            # try focusing the last focused ID. if that's a hub, and it's empty (=not focusable), try focusing the
            # next best hub
            if 399 < self.lastFocusID < 500:
                hubControlIndex = self.lastFocusID - 400

                if hubControlIndex in self.hubFocusIndexes and self.hubControls[hubControlIndex]:
                    # this is basically just used for setting the background upon reinit
                    # fixme: declutter, separation of concerns
                    self.checkHubItem(self.lastFocusID)
                else:
                    util.DEBUG_LOG("Focus requested on {}, which can't focus. Trying next hub", self.lastFocusID)
                    self.focusFirstValidHub(hubControlIndex)

            else:
                if self.getFocusId() != self.lastFocusID:
                    self.setFocusId(self.lastFocusID)

        if self._odHubsDirty:
            self._updateOnDeckHubs()

    def checkPlexDirectHosts(self, servers, source="stored", *args, **kwargs):
        handlePD = util.getSetting('handle_plexdirect')
        if handlePD == "never":
            return

        hosts = []
        for server in servers:
            # only check stored or myplex servers
            if server.sourceType not in (None, plexresource.ResourceConnection.SOURCE_MYPLEX):
                continue
            # if we're set to honor dnsRebindingProtection=1 and the server has this flag at 0 or
            # if we're set to honor publicAddressMatches=1 and the server has this flag at 0, and we haven't seen the
            # server locally, skip plex.direct handling
            if ((util.addonSettings.honorPlextvDnsrebind and not server.dnsRebindingProtection) or
                    (util.addonSettings.honorPlextvPam and not server.sameNetwork and not server.anyLANConnection)):
                util.DEBUG_LOG("Ignoring DNS handling for plex.direct connections of: {}", server)
                continue
            hosts += [c.address for c in server.connections]

        knownHosts = pdm.getHosts()
        pdHosts = [host for host in hosts if ".plex.direct:" in host]

        util.DEBUG_LOG("Checking host mapping for {} {} connections: {}", len(pdHosts), source, ", ".join(pdHosts))

        newHosts = set(pdHosts) - set(knownHosts)
        if newHosts:
            pdm.newHosts(newHosts, source=source)
        diffLen = len(pdm.diff)

        # there are situations where the myPlexManager's resources are ready earlier than
        # any other. In that case, force the check.
        force = plexapp.MANAGER.gotResources

        if ((source == "stored" and plexapp.ACCOUNT.isOffline) or source == "myplex" or force) and pdm.differs:
            if handlePD == 'ask':
                button = optionsdialog.show(
                    T(32993, '').format(diffLen),
                    T(32994, '').format(diffLen),
                    T(32328, 'Yes'),
                    T(32035, 'Always'),
                    T(32033, 'Never'),
                )
                if button not in (0, 1, 2):
                    return

                if button == 1:
                    util.setSetting('handle_plexdirect', 'always')
                elif button == 2:
                    util.setSetting('handle_plexdirect', 'never')
                    return

            hadHosts = pdm.hadHosts
            pdm.write()

            if not hadHosts and handlePD == "ask":
                optionsdialog.show(
                    T(32995, ''),
                    T(32996, ''),
                    T(32997, 'OK'),
                )
            else:
                # be less intrusive
                util.showNotification(T(32996, ''), header=T(32995, ''))

    def loadLibrarySettings(self):
        setting_key = 'home.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:], plexapp.ACCOUNT.ID)
        data = util.getSetting(setting_key, '')
        self.librarySettings = {}
        try:
            self.librarySettings = json.loads(data)
        except ValueError:
            pass
        except:
            util.ERROR()

    def saveLibrarySettings(self):
        if self.librarySettings:
            setting_key = 'home.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:],
                                                       plexapp.ACCOUNT.ID)
            util.setSetting(setting_key, json.dumps(self.librarySettings))

    def loadHubSettings(self):
        setting_key = 'hub.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:], plexapp.ACCOUNT.ID)
        data = util.getSetting(setting_key, '')
        self.hubSettings = {}
        try:
            self.hubSettings = json.loads(data)
        except ValueError:
            pass
        except:
            util.ERROR()

    def saveHubSettings(self):
        if self.hubSettings:
            setting_key = 'hub.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:],
                                                      plexapp.ACCOUNT.ID)
            util.setSetting(setting_key, json.dumps(self.hubSettings))

    @property
    def currentHub(self):
        try:
            hub_focus = int(self.getProperty('hub.focus'))
        except ValueError:
            return None

        if len(self.hubControls) > hub_focus and self.hubControls[hub_focus]:
            hub_control = self.hubControls[hub_focus]
            hub = hub_control.dataSource
            return hub

    @property
    def ignoredHubs(self):
        return [combo for combo, data in self.hubSettings.items() if not data.get("show", True)]

    def updateProperties(self, *args, **kwargs):
        self.setBoolProperty('bifurcation_lines', util.getSetting('hubs_bifurcation_lines'))

    def focusFirstValidHub(self, startIndex=None):
        indices = self.hubFocusIndexes
        if startIndex is not None:
            try:
                indices = self.hubFocusIndexes[self.hubFocusIndexes.index(startIndex):]
                util.DEBUG_LOG("Trying to focus the next best hub after: %i" % (400 + startIndex))
            except IndexError:
                pass

        for index in indices:
            if self.hubControls[index]:
                if self.lastFocusID != 400+index:
                    util.DEBUG_LOG("Focusing hub: %i" % (400 + index))
                    self.setFocusId(400+index)
                    self.checkHubItem(400+index)
                return

        if startIndex is not None:
            util.DEBUG_LOG("Tried all possible hubs after %i. Continuing from the top" % (400 + startIndex))
        else:
            util.DEBUG_LOG("Can't find any suitable hub to focus. This is bad.")
            self.setFocusId(self.SECTION_LIST_ID)
            return

        return self.focusFirstValidHub()

    def hookSignals(self):
        plexapp.SERVERMANAGER.on('new:server', self.onNewServer)
        plexapp.SERVERMANAGER.on('remove:server', self.onRemoveServer)
        plexapp.SERVERMANAGER.on('reachable:server', self.onReachableServer)
        plexapp.SERVERMANAGER.on('reachable:server', self.displayServerAndUser)

        plexapp.util.APP.on('change:selectedServer', self.onSelectedServerChange)
        plexapp.util.APP.on('change:map_button_home', util.homeButtonMapped)
        plexapp.util.APP.on('loaded:server_connections', self.checkPlexDirectHosts)
        plexapp.util.APP.on('account:response', self.displayServerAndUser)
        plexapp.util.APP.on('sli:reachability:received', self.displayServerAndUser)
        plexapp.util.APP.on('change:hubs_bifurcation_lines', self.updateProperties)
        plexapp.util.APP.on('change:no_episode_spoilers4', self.setDirty)
        plexapp.util.APP.on('change:spoilers_allowed_genres2', self.setDirty)
        plexapp.util.APP.on('change:hubs_use_new_continue_watching', self.setDirty)
        plexapp.util.APP.on('change:path_mapping_indicators', self.setDirty)
        plexapp.util.APP.on('change:hub_season_thumbnails', self.setDirty)
        plexapp.util.APP.on('change:use_watchlist', self.setDirty)
        plexapp.util.APP.on('change:debug', self.setDebugFlag)
        plexapp.util.APP.on('change:update_source', self.updateSourceChanged)
        plexapp.util.APP.on('theme_relevant_setting', self.setThemeDirty)

        player.PLAYER.on('session.ended', self.updateOnDeckHubs)
        util.MONITOR.on('changed.watchstatus', self.updateOnDeckHubs)
        util.MONITOR.on('screensaver.activated', self.disableUpdates)
        util.MONITOR.on('screensaver.deactivated', self.refreshLastSection)
        util.MONITOR.on('dpms.deactivated', self.refreshLastSection)
        util.MONITOR.on('system.sleep', self.disableUpdates)
        util.MONITOR.on('system.wakeup', self.onWake)

    def unhookSignals(self):
        plexapp.SERVERMANAGER.off('new:server', self.onNewServer)
        plexapp.SERVERMANAGER.off('remove:server', self.onRemoveServer)
        plexapp.SERVERMANAGER.off('reachable:server', self.onReachableServer)
        plexapp.SERVERMANAGER.off('reachable:server', self.displayServerAndUser)

        plexapp.util.APP.off('change:selectedServer', self.onSelectedServerChange)
        plexapp.util.APP.off('change:map_button_home', util.homeButtonMapped)
        plexapp.util.APP.off('loaded:server_connections', self.checkPlexDirectHosts)
        plexapp.util.APP.off('account:response', self.displayServerAndUser)
        plexapp.util.APP.off('sli:reachability:received', self.displayServerAndUser)
        plexapp.util.APP.off('change:hubs_bifurcation_lines', self.updateProperties)
        plexapp.util.APP.off('change:no_episode_spoilers4', self.setDirty)
        plexapp.util.APP.off('change:spoilers_allowed_genres2', self.setDirty)
        plexapp.util.APP.off('change:hubs_use_new_continue_watching', self.setDirty)
        plexapp.util.APP.off('change:path_mapping_indicators', self.setDirty)
        plexapp.util.APP.off('change:hub_season_thumbnails', self.setDirty)
        plexapp.util.APP.off('change:use_watchlist', self.setDirty)
        plexapp.util.APP.off('change:debug', self.setDebugFlag)
        plexapp.util.APP.off('change:update_source', self.updateSourceChanged)
        plexapp.util.APP.off('theme_relevant_setting', self.setThemeDirty)

        player.PLAYER.off('session.ended', self.updateOnDeckHubs)
        util.MONITOR.off('changed.watchstatus', self.updateOnDeckHubs)
        util.MONITOR.off('screensaver.activated', self.disableUpdates)
        util.MONITOR.off('screensaver.deactivated', self.refreshLastSection)
        util.MONITOR.off('dpms.deactivated', self.refreshLastSection)
        util.MONITOR.off('system.sleep', self.disableUpdates)
        util.MONITOR.off('system.wakeup', self.onWake)


    def updateSourceChanged(self, value, **kwargs):
        self._updateSourceChanged = value


    def service_responder(self):
        if util.getGlobalProperty('update_available'):
            is_downgrade = bool(util.getGlobalProperty('update_is_downgrade', consume=True))
            button = optionsdialog.show(
                T(33670, 'Update available'),
                T(33671, 'Current: {current_version}\nNew: {new_version}\n\nChangelog:\n{changelog}').format(
                    current_version=util.ADDON.getAddonInfo('version'),
                    new_version=util.getGlobalProperty('update_available'),
                    changelog=util.getGlobalProperty('update_changelog'),
                ),
                T(33683, 'Exit, download and install'),
                T(33684, 'Later') if not is_downgrade else T(32329, 'No'),
                delay_buttons=1.8, big=True
            )
            if button == 0:
                resp = "commence"
            else:
                resp = "cancel"
            util.setGlobalProperty('update_response', resp, wait=True)
            util.setGlobalProperty('update_available', '', wait=True)

            if resp == "commence":
                # wait for it to be consumed
                try:
                    util.waitForConsumption('update_response', timeout=200)
                finally:
                    self._shuttingDown = True
                    self._ignoreTick = True
                    self.stopRetryingRequests()

                    # fixme: add "update" to the list of closeOptions for which we should force quit if necessary?
                    #self.closeOption = "update"
                    self.unhookSignals()
                    self.doClose()
                    return True

    def tick(self):
        if self.is_active and self.service_responder():
            return

        if self.is_active and self._updateSourceChanged:
            util.setGlobalProperty('update_source_changed', self._updateSourceChanged, wait=True)
            self._updateSourceChanged = False

        if not self.lastSection or self._ignoreTick:
            return

        hubs = self.sectionHubs.get(self.lastSection.key)
        if hubs is None:
            return

        if (self.is_active and not self._checkingForExit and time.time() - hubs.lastUpdated > HUBS_REFRESH_INTERVAL and
                not xbmc.Player().isPlayingVideo()):
            util.DEBUG_LOG("Home: Ticking, section stale, calling showHubs(update=True)")
            self.showHubs(self.lastSection, update=True)

    def doClose(self):
        util.DEBUG_LOG("Home: doClose called, triggering close.windows")
        plexapp.util.APP.trigger('close.windows')
        #if self.sectionChangeThread and self.sectionChangeThread.isAlive():
        #    self.sectionChangeThread.join(timeout=2.0)

        util.DEBUG_LOG("Home: doClose called, calling super")
        super(HomeWindow, self).doClose()

    def stopRetryingRequests(self):
        util.DEBUG_LOG("Stopping request retries")
        plexnet.asyncadapter.STOP_RETRYING_REQUESTS = True

    def shutdown(self):
        util.DEBUG_LOG("Home: shutdown called")
        self._shuttingDown = True
        self._ignoreTick = True
        self.stopRetryingRequests()
        try:
            self.serverList.reset()
        except AttributeError:
            pass

        util.DEBUG_LOG("Home: unhooking signals")
        self.unhookSignals()
        if (self.closeOption != "switch" and
                (not isinstance(self.closeOption, dict) or (isinstance(self.closeOption, dict) and not self.closeOption.get('fast_switch')))):
            self.storeLastBG()
        util.DEBUG_LOG("Home: exiting shutdown method")


    def storeLastBG(self):
        if util.addonSettings.dynamicBackgrounds:
            oldbg = util.getSetting("last_bg_url.{}".format(plexapp.ACCOUNT.ID), '')
            # store BG url of first hub, first item, as this is most likely to be the one we're focusing on the
            # next start
            try:
                # only store background for home section hubs
                if self.lastSection and self.lastSection.key is None:
                    indices = self.hubFocusIndexes
                    for index in indices:
                        if self.hubControls[index]:
                            ds = self.hubControls[index][0].dataSource
                            if not ds.art:
                                continue

                            if oldbg:
                                url = plexnet.compat.quote_plus(ds.art)
                                if url in oldbg:
                                    return

                            bg = util.backgroundFromArt(ds.art, width=self.width, height=self.height)
                            if bg:
                                util.DEBUG_LOG('Storing BG for {0}, "{1}", acc {2}'.format(self.hubControls[index].dataSource,
                                                                                  ds.defaultTitle, plexapp.ACCOUNT.ID))
                                util.setSetting("last_bg_url.{}".format(plexapp.ACCOUNT.ID), bg)
                                return
            except:
                util.LOG("Couldn't store last background")

    def onAction(self, action):
        controlID = self.getFocusId()

        if self._ignoreInput or self._shuttingDown:
            return

        try:
            if self._skipNextAction:
                self._skipNextAction = False
                return

            if not controlID and not action == xbmcgui.ACTION_MOUSE_MOVE:
                if self.lastFocusID:
                    self.setFocusId(self.lastFocusID)

            if controlID == self.SECTION_LIST_ID:
                if self.movingSection:
                    self.sectionMover(self.movingSection, action)
                    return

                if action == xbmcgui.ACTION_CONTEXT_MENU:
                    try:
                        self.block_section_change = True
                        show_section = self.sectionMenu()
                    finally:
                        self.block_section_change = False
                    if not show_section:
                        return
                    else:
                        self.serverRefresh(section=show_section)
                        return
                self.checkSectionItem(action=action)

            if controlID == self.SERVER_BUTTON_ID:
                if action == xbmcgui.ACTION_SELECT_ITEM:
                    self.showServers()
                    return
                elif action == xbmcgui.ACTION_CONTEXT_MENU and util.getUserSetting('previous_server', None):
                    uuid = util.getUserSetting('previous_server', None)
                    if uuid != plexapp.SERVERMANAGER.selectedServer.uuid:
                        self.selectServer(uuid)
                    return

                elif action == xbmcgui.ACTION_MOUSE_LEFT_CLICK:
                    self.showServers(mouse=True)
                    self.setBoolProperty('show.servers', True)
                    return
            elif controlID == self.USER_BUTTON_ID:
                if action == xbmcgui.ACTION_SELECT_ITEM:
                    self.showUserMenu()
                    return
                elif action == xbmcgui.ACTION_CONTEXT_MENU and util.getSetting('previous_user'):
                    # check whether we can fast swap (account is not protected)
                    # get user
                    uid = util.getSetting('previous_user')
                    if uid == plexapp.ACCOUNT.ID:
                        return

                    user = plexapp.ACCOUNT.getHomeUser(uid)
                    if not user or user.isProtected:
                        self.doUserOption(force_option="switch")
                        return

                    self.doUserOption(force_option={"fast_switch": user.id})
                    return
                elif action == xbmcgui.ACTION_MOUSE_LEFT_CLICK:
                    self.showUserMenu(mouse=True)
                    self.setBoolProperty('show.options', True)
                    return
            elif controlID == self.SERVER_LIST_ID:
                if action == xbmcgui.ACTION_SELECT_ITEM:
                    self.setFocusId(self.SERVER_BUTTON_ID)
                    return

            if controlID == self.SERVER_BUTTON_ID and action == xbmcgui.ACTION_MOVE_RIGHT:
                self.setFocusId(self.USER_BUTTON_ID)
            elif controlID == self.USER_BUTTON_ID and action == xbmcgui.ACTION_MOVE_LEFT:
                self.setFocusId(self.SERVER_BUTTON_ID)
            elif controlID == self.SEARCH_BUTTON_ID and action == xbmcgui.ACTION_MOVE_RIGHT:
                if xbmc.getCondVisibility('Player.HasMedia + Control.IsVisible({0})'.format(self.PLAYER_STATUS_BUTTON_ID)):
                    self.setFocusId(self.PLAYER_STATUS_BUTTON_ID)
                else:
                    self.setFocusId(self.SERVER_BUTTON_ID)
            elif controlID == self.PLAYER_STATUS_BUTTON_ID and action == xbmcgui.ACTION_MOVE_RIGHT:
                self.setFocusId(self.SERVER_BUTTON_ID)
            elif 399 < controlID < 500:
                if action.getId() in MOVE_SET or action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                    _continue = self.checkHubItem(controlID, action=action)
                    if not _continue:
                        return
                elif action == xbmcgui.ACTION_PLAYER_PLAY:
                    self.hubItemClicked(controlID, auto_play=True)
                    return
                elif action == xbmcgui.ACTION_CONTEXT_MENU:
                    show_section = self.hubMenu(controlID)
                    if not show_section:
                        return
                    else:
                        self.serverRefresh(section=show_section)
                        return

            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_CONTEXT_MENU):
                optionsFocused = xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID))
                offSections = util.getGlobalProperty('off.sections')
                if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                    # fixme: cheap way of avoiding an early exit after a server change
                    if self.changingServer:
                        return

                    if self.getFocusId() == self.USER_LIST_ID:
                        self.setFocusId(self.USER_BUTTON_ID)
                        return
                    elif self.getFocusId() == self.SERVER_LIST_ID:
                        self.setFocusId(self.SERVER_BUTTON_ID)
                        return

                    if controlID == self.SECTION_LIST_ID and self.sectionList.control.getSelectedPosition() > 0:
                        self.goHome()
                        return

                    if util.addonSettings.fastBack and not optionsFocused and offSections \
                            and self.lastFocusID not in (self.USER_BUTTON_ID, self.SERVER_BUTTON_ID,
                                                         self.SEARCH_BUTTON_ID, self.SECTION_LIST_ID):
                        self.setProperty('hub.focus', '0')
                        self.setFocusId(self.SECTION_LIST_ID)
                        return

                if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                    if not optionsFocused and offSections \
                            and (not util.addonSettings.fastBack or action == xbmcgui.ACTION_CONTEXT_MENU):
                        self.lastNonOptionsFocusID = self.lastFocusID
                        self.setFocusId(self.OPTIONS_GROUP_ID)
                        return
                    elif action == xbmcgui.ACTION_CONTEXT_MENU and optionsFocused and offSections \
                            and self.lastNonOptionsFocusID:
                        self.setFocusId(self.lastNonOptionsFocusID)
                        self.lastNonOptionsFocusID = None
                        return

                if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU) and not self._checkingForExit:
                    try:
                        self._checkingForExit = True
                        if self._shuttingDown:
                            # rare case confirmed in Kodi 18 when requests are still running and we're exiting quickly
                            return

                        util.DEBUG_LOG("Home: Showing exit confirmation dialog")

                        ex = self.confirmExit()
                        # 0 = exit; 1 = minimize; 2 = cancel
                        if ex.button in (2, None):
                            return
                        elif ex.button == 1:
                            self.storeLastBG()
                            util.setGlobalProperty('is_active', '')
                            xbmc.executebuiltin('ActivateWindow(10000)')
                            return
                        elif ex.button == 0:
                            self._shuttingDown = True
                            util.DEBUG_LOG("Home: Initiating shutdown, setting background")
                            background.setShutdown()
                            if ex.modifier == "quit":
                                self.closeOption = "quit"
                                self.unhookSignals()
                            else:
                                self.closeOption = "exit"
                    finally:
                        self._checkingForExit = False

                    # 0 passes the action to the BaseWindow and exits HOME
        except:
            util.ERROR()

        kodigui.BaseWindow.onAction(self, action)

    def onClick(self, controlID):
        if self._ignoreInput:
            return

        if controlID == self.SECTION_LIST_ID:
            if not self.movingSection:
                self.sectionClicked()
        # elif controlID == self.SERVER_BUTTON_ID:
        #     self.showServers()
        elif controlID == self.SERVER_LIST_ID:
            self.setBoolProperty('show.servers', False)
            self.selectServer()
        # elif controlID == self.USER_BUTTON_ID:
        #     self.showUserMenu()
        elif controlID == self.USER_LIST_ID:
            if self.doUserOption():
                self._skipNextAction = True
            self.setBoolProperty('show.options', False)
            self.setFocusId(self.USER_BUTTON_ID)
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif 399 < controlID < 500:
            self.hubItemClicked(controlID)
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()

    def onFocus(self, controlID):
        if controlID != 204 and controlID < 500:
            # don't store focus for mini music player
            self.lastFocusID = controlID

        if 399 < controlID < 500:
            self.setProperty('hub.focus', str(self.hubFocusIndexes[controlID - 400]))

        if (controlID == self.SECTION_LIST_ID and not self.changingServer and not self._checkingForExit and not
        self._shuttingDown):
            self.checkSectionItem()

        if xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + ControlGroup(100).HasFocus(0)'):
            util.setGlobalBoolProperty('off.sections', '')
        elif controlID != 250 and xbmc.getCondVisibility('ControlGroup(50).HasFocus(0) + !ControlGroup(100).HasFocus(0)'):
            util.setGlobalBoolProperty('off.sections', '1')

    def goHome(self, **kwargs):
        self.setProperty('hub.focus', '')
        self.setFocusId(self.SECTION_LIST_ID)
        self.sectionList.setSelectedItemByPos(0)
        # set lastSection here already, otherwise tick() might interfere
        # fixme: Might still happen in a race condition, check later
        self.lastSection = home_section
        self.showHubs(home_section)
        return

    def confirmExit(self):
        lBtnExit = T(32336, 'Exit')
        lBtnQuit = T(32704, 'Quit Kodi')
        modifier = util.getSetting('exit_default_is_quit') and "quit" or "exit"

        ret = plexnet.util.AttributeDict(button=None, modifier=modifier)

        def actionCallback(dialog, actionID, controlID):
            if actionID == xbmcgui.ACTION_CONTEXT_MENU and controlID == dialog.BUTTON_IDS[0]:
                control = dialog.getControl(controlID)
                if control.getLabel() == lBtnExit:
                    control.setLabel(lBtnQuit)
                    ret.modifier = "quit"
                else:
                    control.setLabel(lBtnExit)
                    ret.modifier = "exit"

        button = optionsdialog.show(
            T(32334, 'Confirm Exit'),
            T(32335, 'Are you ready to exit Plex?'),
            modifier == "exit" and lBtnExit or lBtnQuit,
            T(32924, 'Minimize'),
            T(32337, 'Cancel'),
            action_callback=actionCallback
        )
        ret.button = button

        return ret

    def searchButtonClicked(self):
        self.processCommand(search.dialog(self))

    def updateOnDeckHubs(self, **kwargs):
        self._odHubsDirty = True

    def _updateOnDeckHubs(self, **kwargs):
        util.DEBUG_LOG('UpdateOnDeckHubs called')
        self._odHubsDirty = False
        #if util.getSetting("speedy_home_hubs2"):
        #    util.DEBUG_LOG("Using alternative home hub refresh")
        #    sections = set()
        #    for mli in self.sectionList:
        #        if mli.dataSource is not None and mli.dataSource != self.lastSection:
        #            sections.add(mli.dataSource)
        #    tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections, self.ignoredHubs)
        #             for s in [self.lastSection] + list(sections) if not s.server.DEFER_HUBS and s != self.lastSection]
        #else:
        # fetch hubs we need to update
        rp = self.getCurrentHubsPositions(self.lastSection)
        tasks = [UpdateHubTask().setup(hub, self.updateHubCallback,
                                       reselect_pos=rp.get(hub.getCleanHubIdentifier(self.lastSection.key is None)))
                 for hub in self.updateHubs.values()]
        self.tasks += tasks
        backgroundthread.BGThreader.addTasks(tasks)

    def showBusy(self, on=True):
        self.setProperty('busy', on and '1' or '')

    def setDirty(self, *args, **kwargs):
        self._reloadOnReinit = True
        self.cacheSpoilerSettings()

    def setThemeDirty(self, *args, **kwargs):
        self._applyTheme = util.getSetting("theme")

    def setDebugFlag(self, *args, **kwargs):
        util.DEBUG = util.getSetting("debug")
        util.addonSettings.debug = util.DEBUG

    def fullyRefreshHome(self, *args, **kwargs):
        section = kwargs.pop("section", None)
        self.showSections(focus_section=section or home_section)
        self.backgroundSet = False
        self.showHubs(section if section else home_section)

    def disableUpdates(self, *args, **kwargs):
        util.LOG("Sleep event, stopping updates")
        self._ignoreTick = True

    def enableUpdates(self, *args, **kwargs):
        util.LOG("Wake event, resuming updates")
        self._ignoreTick = False

    def refreshLastSection(self, *args, **kwargs):
        self.enableUpdates()
        if not xbmc.Player().isPlayingVideo() and not self._shuttingDown:
            util.LOG("Refreshing last section after wake events")
            self.showHubs(self.lastSection, force=True, update=True)

    def onWake(self, *args, **kwargs):
        wakeAction = util.getSetting('action_on_wake', util.platformFlavor == 'CoreELEC' and 'wait_5' or 'wait_1')
        if wakeAction == "restart":
            self._ignoreReInit = True
            self._restarting = True
            if not self.is_active:
                plexapp.util.APP.trigger('close.dialogs')
                plexapp.util.APP.trigger('close.windows')

            self.closeOption = "restart"
            self.doClose()
            return
        elif wakeAction.startswith("wait_"):
            seconds = int(wakeAction.split("_")[1])
            established = 0
            self._ignoreInput = True
            try:
                with busy.BusyBlockingContext():
                    with busy.ProgressDialog(T(33073, ''), T(33074, '').format(seconds)) as pd:
                        while established < seconds:
                            util.MONITOR.waitForAbort(0.5)
                            established += 0.5
                            pd.update(int(established * 100 / float(seconds)))
                            if pd.isCanceled():
                                break
                self.refreshLastSection(*args, **kwargs)
                return
            finally:
                self._ignoreInput = False

        self.refreshLastSection(*args, **kwargs)

    @busy.dialog()
    def serverRefresh(self, section=None):
        backgroundthread.BGThreader.reset()
        if self.tasks:
            for task in self.tasks:
                task.cancel()

        with self.lock:
            self.setProperty('hub.focus', '')
            self.displayServerAndUser()
            self.loadLibrarySettings()
            self.loadHubSettings()
            if not plexapp.SERVERMANAGER.selectedServer:
                self.setFocusId(self.USER_BUTTON_ID)
                return False

            self.fullyRefreshHome(section=section)
            if section is not None:
                for mli in self.sectionList:
                    if mli.dataSource and mli.dataSource.key == section.key:
                        self.sectionList.selectItem(mli.pos())
                        self.lastSection = mli.dataSource
            return True

    def hubItemClicked(self, hubControlID, auto_play=False):
        control = self.hubControls[hubControlID - 400]
        mli = control.getSelectedItem()
        if not mli:
            return

        if mli.dataSource is None:
            return

        # auto resume for in-progress items
        if util.getSetting('home_inprogress_resume'):
            if mli.dataSource.TYPE in ('episode', 'movie') and mli.dataSource.in_progress:
                auto_play = True

        carryProps = None
        if auto_play:
            carryProps = self.carriedProps

        use_ds = mli.dataSource
        ds_changed = False

        extra_kwargs = {}
        if mli.dataSource.is_watchlist:
            extra_kwargs['from_watchlist'] = True
            extra_kwargs['external_item'] = True

            if mli.dataSource.TYPE in ("season", "episode"):
                # we need to change the datasource if someone clicks an episode in a discover hub (watchlist), to go
                # to the corresponding show
                use_ds = mli.dataSource.show()
                ds_changed = True

        try:
            command = opener.open(use_ds, auto_play=auto_play, dialog_props=carryProps, **extra_kwargs)
            if command == "NODATA":
                raise util.NoDataException
        except util.NoDataException:
            util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
            return

        if self._restarting:
            return

        if not ds_changed:
            self.updateListItem(mli)

        if not mli:
            return

        # MediaItem.exists checks for the deleted and deletedAt flags. We still want to show the media if it's still
        # valid, but has deleted files. Do a more thorough check for existence in this case
        if not mli.dataSource.exists() and not mli.dataSource.exists(force_full_check=True):
            try:
                control.removeItem(mli.pos())
            except (ValueError, TypeError):
                # fixme: why?
                pass

        if not control.size():
            idx = self.hubFocusIndexes[hubControlID - 400]
            while idx > 0:
                idx -= 1
                controlID = 400 + self.hubFocusIndexes.index(idx)
                control = self.hubControls[self.hubFocusIndexes.index(idx)]
                if control.size():
                    self.setFocusId(controlID)
                    break
            else:
                self.setFocusId(self.SECTION_LIST_ID)

        self.processCommand(command)

    def processCommand(self, command):
        if command.startswith('HOME:'):
            sectionID = command.split(':', 1)[-1]
            for mli in self.sectionList:
                if mli.dataSource and mli.dataSource.key == sectionID:
                    self.sectionList.selectItem(mli.pos())
                    self.lastSection = mli.dataSource
                    self.setProperty('hub.focus', '')
                    self.setFocusId(self.SECTION_LIST_ID)
                    self._sectionReallyChanged(self.lastSection)

    @property
    def carriedProps(self):
        # carry over some props to the new window as we might end up showing a dialog not rendering the
        # underlying window. the new window class will invalidate the old one temporarily, though, as it seems
        # and the properties vanish, resulting in all text2lines enabled hubs to lose their title2 labels
        if self.hubControls:
            return dict(
                ('hub.text2lines.4{0:02d}'.format(i), '1') for i, hubCtrl in enumerate(self.hubControls) if
                hubCtrl.dataSource and self.HUBMAP[hubCtrl.dataSource.getCleanHubIdentifier()].get("text2lines"))

    def sectionMenu(self):
        item = self.sectionList.getSelectedItem()
        if not item or not item.getProperty('item'):
            return

        section = item.dataSource
        choice = None
        if not section.key:
            # home section
            sections = [playlists_section] + plexapp.SERVERMANAGER.selectedServer.library.sections()
            options = []

            use_sep = False
            if "order" in self.librarySettings and self.librarySettings["order"]:
                options.append({'key': 'reset_order', 'display': T(33040, "Reset library order")})
                use_sep = True

            if util.getSetting('cache_requests'):
                options.append({'key': 'cache_reset', 'display': T(33720, "Clear all caches")})
                use_sep = True

            if use_sep:
                options.append(dropdown.SEPARATOR)

            had_section = False
            for s in sections:
                section_settings = self.librarySettings.get(s.key)
                if section_settings and not section_settings.get("show", True):
                    options.append({'key': 'show',
                                    'section_id': s.key,
                                    'display': T(33029, "Show library: {}").format(s.title)
                                    }
                                   )
                    had_section = True

            # hack for an inexistant watchlist due to it being hidden
            if util.getUserSetting("use_watchlist", True) and not self.librarySettings.get("/library/sections/watchlist", {}).get("show", True):
                options.append({'key': 'show',
                                'section_id': "/library/sections/watchlist",
                                'display': T(33029, "Show library: {}").format(T(34000, 'Watchlist'))
                                })

            if self.hubSettings:
                had_hidden_hub = False
                hidden_hubs_opts = []
                for section_hub_key in self.ignoredHubs:
                    if not section_hub_key.startswith("None:"):
                        continue

                    hub_title = section_hub_key
                    if plexapp.SERVERMANAGER.selectedServer.currentHubs:
                        hub_title = plexapp.SERVERMANAGER.selectedServer.currentHubs.get(section_hub_key,
                                                                                         section_hub_key)
                    hidden_hubs_opts.append({'key': 'show',
                                    'hub_ident': section_hub_key,
                                    'display': T(33041, "Show hub: {}").format(hub_title)
                                    }
                                   )
                    had_hidden_hub = True

                if had_section and had_hidden_hub:
                    options.append(dropdown.SEPARATOR)
                options += hidden_hubs_opts

            if options:
                choice = dropdown.showDropdown(
                    options,
                    pos=(660, 441),
                    close_direction='none',
                    set_dropdown_prop=False,
                    header=T(33034, "Library settings"),
                    select_index=0,
                    align_items="left",
                    dialog_props=self.carriedProps
                )

        else:
            options = []

            if plexapp.ACCOUNT.isAdmin and section not in (watchlist_section, playlists_section):
                options = [{'key': 'refresh', 'display': T(33082, "Scan Library Files")},
                           {'key': 'emptyTrash', 'display': T(33083, "Empty Trash")},
                           {'key': 'analyze', 'display': T(33084, "Analyze")},
                           dropdown.SEPARATOR]

            if section.locations and util.getSetting('path_mapping'):
                for loc in section.locations:
                    source, target = section.getMappedPath(loc)
                    loc_is_mapped = source and target
                    options.append(
                        {'key': 'map', 'mapped': loc_is_mapped, 'path': loc, 'display': T(33026,
                                                                                          "Map path: {}").format(loc)
                            if not loc_is_mapped else T(33027, "Remove mapping: {}").format(target)
                         }
                    )

                options.append(dropdown.SEPARATOR)

            options.append({'key': 'hide', 'display': T(33028, "Hide library")})
            options.append({'key': 'move', 'display': T(33039, "Move")})
            options.append(dropdown.SEPARATOR)

            if 'libraries' in util.getSetting('cache_requests') and section != watchlist_section:
                options.append({'key': 'section_cache_reset', 'display': T(33721, "Clear library cache (not items)")})
                options.append(dropdown.SEPARATOR)

            if self.hubSettings:
                for section_hub_key in self.ignoredHubs:
                    if not section_hub_key.startswith("{}:".format(section.key)):
                        continue

                    hub_title = section_hub_key
                    if plexapp.SERVERMANAGER.selectedServer.currentHubs:
                        hub_title = plexapp.SERVERMANAGER.selectedServer.currentHubs.get(section_hub_key,
                                                                                         section_hub_key)
                    options.append({'key': 'show',
                                    'hub_ident': section_hub_key,
                                    'display': T(33041, "Show hub: {}").format(hub_title)
                                    }
                                   )

            choice = dropdown.showDropdown(
                options,
                pos=(660, 441),
                close_direction='none',
                set_dropdown_prop=False,
                header=T(33030, 'Choose action for: {}').format(section.title),
                select_index=0,
                align_items="left",
                dialog_props=self.carriedProps
            )

        if not choice:
            return

        if choice["key"] == "map":
            is_mapped = choice.get("mapped")
            if is_mapped:
                # show deletion
                source, target = section.getMappedPath(choice["path"])
                section.deleteMapping(target)
                return self.lastSection

            else:
                # show fb
                # select loc to map
                d = xbmcgui.Dialog().browse(0, T(33031, "Select Kodi source for {}").format(choice["path"]), "files")
                if not d:
                    return
                pmm.addPathMapping(d, choice["path"])
                return self.lastSection
        elif choice["key"] == "hide":
            if section.key not in self.librarySettings:
                self.librarySettings[section.key] = {}
            self.librarySettings[section.key]['show'] = False
            self.saveLibrarySettings()
            return self.sectionList[self.sectionList.prev()].dataSource
        elif choice["key"] == "show":
            if "hub_ident" in choice:
                if choice["hub_ident"] in self.hubSettings:
                    self.hubSettings[choice["hub_ident"]]['show'] = True
                    self.saveHubSettings()
                    return self.lastSection
            elif "section_id" in choice:
                if choice["section_id"] in self.librarySettings:
                    self.librarySettings[choice["section_id"]]['show'] = True
                    self.saveLibrarySettings()
                    return self.lastSection
        elif choice["key"] == "move":
            self.sectionMover(item, "init")
        elif choice["key"] == "reset_order":
            if "order" in self.librarySettings:
                del self.librarySettings["order"]
                self.saveLibrarySettings()
                return self.lastSection
        elif choice["key"] == "refresh":
            with busy.BusyContext(delay=True, delay_time=0.2):
                section.refresh()
            return self.lastSection
        elif choice["key"] == "emptyTrash":
            button = optionsdialog.show(
                T(33083, 'Empty Trash'),
                section.title,
                T(32328, 'Yes'),
                T(32329, 'No')
            )
            if button == 0:
                with busy.BusyContext(delay=True, delay_time=0.2):
                    section.emptyTrash()
                return self.lastSection
        elif choice["key"] == "analyze":
            with busy.BusyContext(delay=True, delay_time=0.2):
                section.analyze()
            return

        elif choice["key"] == "cache_reset":
            try:
                plexapp.util.INTERFACE.clearRequestsCache()
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear requests cache: {}", e)

        elif choice["key"] == "section_cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for section {}...', section.title)
                section.clearCache()
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear library cache: {}", e)

    def hubMenu(self, hubControlID):
        hub = self.currentHub
        if not hub:
            return

        control = self.hubControls[hubControlID - 400]
        mli = control.getSelectedItem()
        if not mli:
            return

        if mli.dataSource is None:
            return

        section_hub_key = "{}:{}".format(self.lastSection.key, hub.hubIdentifier)

        hub_title = section_hub_key
        if plexapp.SERVERMANAGER.selectedServer.currentHubs:
            hub_title = plexapp.SERVERMANAGER.selectedServer.currentHubs.get(section_hub_key,
                                                                             section_hub_key)

        select_base = 0

        options = []
        has_prev = False
        if hub.hubIdentifier not in ("home.continue", "continueWatching"):
            options.append({'key': 'hide', 'display': T(33659, "Hide Hub: {}").format(hub_title)})
            has_prev = True

        if mli.dataSource.TYPE in ('episode', 'season', 'movie', 'show'):
            if has_prev:
                options.append(dropdown.SEPARATOR)

            has_mp = False
            if not mli.getProperty('watched'):
                options.append({'key': 'mark_watched', 'display': T(32319, "Mark Played")})
                select_base = has_prev and 1 or 0
                has_mp = True

            if (mli.dataSource.isFullyWatched or mli.dataSource.isWatched or
                    mli.dataSource.viewedLeafCount.asInt() > 0):
                options.append({'key': 'mark_unwatched', 'display': T(32318, "Mark Unplayed")})
                select_base = has_prev and 1 or has_mp and 0
                has_mp = True

            if mli.dataSource.TYPE in ('episode', 'movie'):
                    #hub.hubIdentifier == "continueWatching"):
                if hub.hubIdentifier in ("home.continue", "continueWatching", "home.ondeck"):
                    # allow removing items from CW
                    options.append(dropdown.SEPARATOR)
                    options.append({'key': 'remove_cw', 'display': T(33662, "Remove from Continue Watching")})
                    if not has_mp:
                        select_base = 1
                if util.getSetting('home_inprogress_resume') and mli.dataSource.in_progress:
                    # this is an in progress item that would be auto resumed; add specific entry to visit media instead
                    options.insert(0, dropdown.SEPARATOR)
                    options.insert(0, {'key': 'to_item', 'display': T(33019, "Visit media item")})
                    select_base = 0


            if mli.dataSource.TYPE in ('episode', 'season'):
                options.append(dropdown.SEPARATOR)
                options.append({'key': 'to_show', 'display': T(32323, "Go To Show")})
                if mli.dataSource.TYPE == 'episode':
                    options.append({'key': 'to_season', 'display': T(32400, "Go To Season")})

            if 'items' in util.getSetting('cache_requests'):
                options.append({'key': 'cache_reset', 'display': T(33728, "Clear cache for item")})

        choice = dropdown.showDropdown(
            options,
            pos=(660, 441),
            close_direction='none',
            set_dropdown_prop=False,
            header=T(33030, 'Choose action for: {}').format(hub.title),
            select_index=select_base,
            align_items="left",
            dialog_props=self.carriedProps
        )

        if not choice:
            return

        elif choice["key"] == "hide":
            if section_hub_key not in self.hubSettings:
                self.hubSettings[section_hub_key] = {}
            self.hubSettings[section_hub_key]['show'] = False
            self.saveHubSettings()
            return self.lastSection

        elif choice["key"] in ("mark_watched", "mark_unwatched"):
            if util.getSetting('home_confirm_actions'):
                button = optionsdialog.show(
                    T(32319, "Mark Played") if choice["key"] == "mark_watched" else T(32318, "Mark Unplayed"),
                    u"{} {}".format(mli.label, mli.label2),
                    T(32328, 'Yes'),
                    T(32329, 'No'),
                    dialog_props=self.carriedProps
                )

                if button != 0:
                    return

            if choice["key"] == "mark_watched":
                mli.dataSource.markWatched()
                if mli.dataSource.isFullyWatched:
                    guid = mli.dataSource.show().guid if mli.dataSource.TYPE in ('episode',
                                                                                 'season') else mli.dataSource.guid
                    removeFromWatchlistBlind(guid)
                self._updateOnDeckHubs()

            elif choice["key"] == "mark_unwatched":
                mli.dataSource.markUnwatched()
                self._updateOnDeckHubs()

        elif choice["key"] == "remove_cw":
            if util.getSetting('home_confirm_actions'):
                button = optionsdialog.show(
                    T(33662, "Remove from Continue Watching"),
                    u"{} {}".format(mli.label, mli.label2),
                    T(32328, 'Yes'),
                    T(32329, 'No'),
                    dialog_props=self.carriedProps
                )

                if button != 0:
                    return

            mli.dataSource.removeFromContinueWatching()
            self._updateOnDeckHubs()

        elif choice["key"] in ("to_season", "to_show"):
            target = mli.dataSource.show() if choice["key"] == "to_show" else mli.dataSource.season()
            try:
                command = opener.open(target, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
                return

        elif choice["key"] == "to_item":
            try:
                command = opener.open(mli.dataSource, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - disconnected?", notify=True, time_ms=5000)
                return

        elif choice["key"] == "cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for {}...', mli.dataSource)
                mli.dataSource.clearCache()
            except Exception as e:
                util.DEBUG_LOG("Couldn't clear cache: {}", e)

    def sectionMover(self, item, action):
        def stop_moving(reset=False):
            # set everything to non-moving and re-insert home item
            self.movingSection = False
            self.setBoolProperty("moving", False)
            item.setBoolProperty("moving", False)
            homemli = kodigui.ManagedListItem(T(32332, 'Home'), data_source=home_section)
            homemli.setProperty('is.home', '1')
            homemli.setProperty('item', '1')
            if reset:
                if self._initialMovingSectionPos is not None:
                    self.sectionList.moveItem(item, self._initialMovingSectionPos)
                self._initialMovingSectionPos = None
            self.sectionList.insertItem(0, homemli)
            if reset:
                self.sectionList.selectItem(0)
            self.sectionChanged()

        if action == "init":
            self.movingSection = item
            self.setBoolProperty("moving", True)
            self._initialMovingSectionPos = self.sectionList.getSelectedPos() - 1

            # remove home item
            self.sectionList.removeItem(0)
            self.sectionList.setSelectedItem(item)

            item.setBoolProperty("moving", True)

        elif action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
            stop_moving(reset=True)

        elif action in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
            direction = "left" if action == xbmcgui.ACTION_MOVE_LEFT else "right"
            index = self.sectionList.getManagedItemPosition(item)
            last_index = len(self.sectionList) - 1
            next_index = min(max(0, index - 1 if direction == "left" else index + 1), last_index)
            if index == 0 and direction == "left":
                next_index = last_index
                self.sectionList.selectItem(last_index)
            elif index == last_index and direction == "right":
                next_index = 0
                self.sectionList.selectItem(0)

            self.sectionList.moveItem(item, next_index)

        elif action == xbmcgui.ACTION_SELECT_ITEM:
            stop_moving()
            # store section order
            self.librarySettings["order"] = [i.dataSource.key for i in self.sectionList.items if i.dataSource]
            self.saveLibrarySettings()

    def checkSectionItem(self, force=False, action=None):
        item = self.sectionList.getSelectedItem()
        if not item:
            return

        if not item.getProperty('item') and action:
            if action == xbmcgui.ACTION_MOVE_RIGHT:
                self.sectionList.selectItem(0)
                item = self.sectionList[0]
            elif action == xbmcgui.ACTION_MOVE_LEFT:
                self.sectionList.selectItem(self.bottomItem)
                item = self.sectionList[self.bottomItem]

        if item.getProperty('is.home'):
            self.storeLastBG()

        if item.dataSource != self.lastSection or force:
            self.sectionChanged(force=force)

    def checkHubItem(self, controlID, action=None):
        control = self.hubControls[controlID - 400]
        mli = control.getSelectedItem()
        is_valid_mli = mli and mli.getProperty('is.end') != '1'
        is_last_item = is_valid_mli and control.isLastItem(mli)

        if action:
            self._anyItemAction = True

        if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
            pos = control.getSelectedPos()
            if pos is not None and pos > 0:
                control.selectItem(0)
                self.updateBackgroundFrom(control[0].dataSource)
                return
            return True

        if util.addonSettings.dynamicBackgrounds and is_valid_mli:
            self.updateBackgroundFrom(mli.dataSource)

        if not mli or not mli.getProperty('is.end') or mli.getProperty('is.updating') == '1':
            # round robining
            if mli and util.getSetting("hubs_round_robin"):
                mlipos = control.getManagedItemPosition(mli)

                # in order to not round-robin when the next chunk is loading, implement our own cheap round-robining
                # by storing the last selected item of the current control. if we've seen it twice, we need to wrap
                # around
                if not mli.getProperty('is.end') and is_last_item and action == xbmcgui.ACTION_MOVE_RIGHT:
                    if (controlID, mlipos) == self._lastSelectedItem:
                        control.selectItem(0)
                        self._lastSelectedItem = (controlID, 0)
                        self.updateBackgroundFrom(control[0].dataSource)
                        return
                elif (action == xbmcgui.ACTION_MOVE_LEFT and mlipos == 0
                      and ((controlID, mlipos) == self._lastSelectedItem)):
                    if not control.dataSource.more.asInt():
                        last_item_index = len(control) - 1
                        control.selectItem(last_item_index)
                        while control.getSelectedPos() != last_item_index:
                            util.MONITOR.waitForAbort(0.1)

                        if not control[last_item_index].dataSource:
                            last_item_index -= 1
                            control.selectItem(last_item_index)
                            
                        self._lastSelectedItem = (controlID, last_item_index)
                        self.updateBackgroundFrom(control[last_item_index].dataSource)
                    else:
                        task = ExtendHubTask().setup(control.dataSource, self.extendHubCallback,
                                                     canceledCallback=lambda hub: mli.setBoolProperty('is.updating',
                                                                                                      False),
                                                     reselect_pos=(None, -1))
                        self.tasks.append(task)
                        backgroundthread.BGThreader.addTask(task)
                    return
                self._lastSelectedItem = (controlID, mlipos)
            return

        mli.setBoolProperty('is.updating', True)
        self.cleanTasks()
        task = ExtendHubTask().setup(control.dataSource, self.extendHubCallback,
                                     canceledCallback=lambda hub: mli.setBoolProperty('is.updating', False))
        self.tasks.append(task)
        backgroundthread.BGThreader.addTask(task)

    def displayServerAndUser(self, **kwargs):
        title = plexapp.ACCOUNT.title or plexapp.ACCOUNT.username or ' '
        self.setProperty('user.name', title)
        self.setProperty('user.avatar', plexapp.ACCOUNT.thumb)
        self.setProperty('user.avatar.letter', title[0].upper())

        if plexapp.SERVERMANAGER.selectedServer:
            self.setProperty('server.name', plexapp.SERVERMANAGER.selectedServer.name)
            self.setProperty('server.icon',
                             'script.plex/home/device/plex.png')  # TODO: Set dynamically to whatever it should be if that's how it even works :)
            self.setProperty('server.iconmod',
                             plexapp.SERVERMANAGER.selectedServer.isSecure and 'script.plex/home/device/lock.png' or '')
            self.setProperty('server.iconmod2',
                             plexapp.SERVERMANAGER.selectedServer.isLocal and 'script.plex/home/device/home_small.png'
                             or '')
        else:
            self.setProperty('server.name', T(32338, 'No Servers Found'))
            self.setProperty('server.icon', 'script.plex/home/device/error.png')
            self.setProperty('server.iconmod', '')
            self.setProperty('server.iconmod2', '')

    def cleanTasks(self):
        self.tasks = [t for t in self.tasks if t]

    def sectionChanged(self, force=False):
        if self._shuttingDown:
            return

        self.sectionChangeTimeout = time.time() + 0.5

        # wait 2s at max if we're currently awaiting any hubs to reload
        # fixme: this can be done in a better way, probably
        waited = 0
        while any(self.tasks) and waited < 20:
            if waited > 5:
                self.showBusy(True)
            util.MONITOR.waitForAbort(0.1)
            waited += 1
        self.showBusy(False)

        if force:
            self.sectionChangeTimeout = None
            self._sectionChanged(immediate=True)
            return

        if not self.sectionChangeThread or (self.sectionChangeThread and not self.sectionChangeThread.is_alive()):
            self.sectionChangeThread = threading.Thread(target=self._sectionChanged, name="sectionchanged")
            self.sectionChangeThread.start()

    def _sectionChanged(self, immediate=False):
        if self._shuttingDown:
            return

        if not immediate:
            if not self.sectionChangeTimeout:
                return
            while not util.MONITOR.waitForAbort(0.1):
                # timing issue
                if not self.sectionChangeTimeout:
                    return
                if time.time() >= self.sectionChangeTimeout:
                    break

        ds = self.sectionList.getSelectedItem().dataSource
        if self.lastSection == ds:
            return

        self._sectionReallyChanged(ds)

    def _sectionReallyChanged(self, section):
        with self.lock:
            while self.block_section_change:
                util.MONITOR.waitForAbort(0.1)

            self.setProperty('hub.focus', '')
            if util.addonSettings.dynamicBackgrounds:
                self.backgroundSet = False

            util.DEBUG_LOG('Section changed ({0}): {1}', section.key, repr(section.title))
            self.lastSection = section
            self.showHubs(section)

        # timing issue
        cur_sel_ds = self.sectionList.getSelectedItem().dataSource
        if self.lastSection != cur_sel_ds:
            util.DEBUG_LOG("Section changed in the "
                           "meantime from {} to {}, re-running the section change".format(
                            section.key,
                            cur_sel_ds.key))
            self.checkSectionItem(force=True)

    def sectionHubsCallback(self, section, hubs, reselect_pos_dict=None):
        with self.lock:
            update = bool(self.sectionHubs.get(section.key))
            # sort hubs by hubmap index
            hubs.sort(key=lambda hub: self.HUBMAP.get(hub.getCleanHubIdentifier(is_home=section.key is None),
                                                    {"index": 999})["index"])

            self.sectionHubs[section.key] = hubs
            if self.lastSection == section:
                if section.server.DEFER_HUBS:
                    self.setBoolProperty('loading.content', False)
                self.showHubs(section, update=update, reselect_pos_dict=reselect_pos_dict)

    def updateHubCallback(self, hub, items=None, reselect_pos=None):
        with self.lock:
            for mli in self.sectionList:
                section = mli.dataSource
                if not section:
                    continue

                hubs = self.sectionHubs.get(section.key, ())
                if not hubs:
                    util.LOG("Hubs for {} not found/no data", section.key)
                    continue

                for idx, ihub in enumerate(hubs):
                    if ihub == hub:
                        if self.lastSection == section:
                            util.DEBUG_LOG('Hub {0} updated - refreshing section: {1}'.format(hub.hubIdentifier,
                                                                                              repr(section.title)))
                            hubs[idx] = hub
                            self.showHub(hub, items=items, reselect_pos=reselect_pos)
                            return

    def extendHubCallback(self, hub, items, reselect_pos=None):
        util.DEBUG_LOG('ExtendHub called: {0} [{1}] (reselect: {2})'.format(hub.hubIdentifier, len(hub.items),
                                                                            reselect_pos))
        self.updateHubCallback(hub, items, reselect_pos=reselect_pos)

    def showSections(self, focus_section=None):
        global watchlist_section
        self.sectionHubs = {}
        items = []

        homemli = kodigui.ManagedListItem(T(32332, 'Home'), data_source=home_section)
        homemli.setProperty('is.home', '1')
        homemli.setProperty('item', '1')
        items.append(homemli)

        sections = []

        # https://discover.provider.plex.tv/library/sections/watchlist/all?includeAdvanced=1&includeMeta=1
        if not plexapp.ACCOUNT.isOffline and util.getUserSetting("use_watchlist", True) and ("/library/sections/watchlist" not in self.librarySettings
                or ("/library/sections/watchlist" in self.librarySettings and self.librarySettings["/library/sections/watchlist"].get("show", True))):
            # get watchlist
            from plexnet import plexlibrary
            wl = watchlist_section = plexlibrary.WatchlistSection(None, server=plexapp.SERVERMANAGER.getDiscoverServer())
            if wl.has_data():
                wl.title = T(34000, 'Watchlist')
                sections.append(wl)

        if "playlists" not in self.librarySettings \
                or ("playlists" in self.librarySettings and self.librarySettings["playlists"].get("show", True)):
            pl = plexapp.SERVERMANAGER.selectedServer.playlists()
            if pl:
                sections.append(playlists_section)

        try:
            _sections = plexapp.SERVERMANAGER.selectedServer.library.sections()
        except plexnet.exceptions.BadRequest:
            self.setFocusId(self.SERVER_BUTTON_ID)
            util.messageDialog("Error", "Bad request")
            return

        self.wantedSections = []
        for section in _sections:
            if section.key in self.librarySettings and not self.librarySettings[section.key].get("show", True):
                self.anyLibraryHidden = True
                continue
            sections.append(section)
            self.wantedSections.append(section.key)

        # sort libraries
        if "order" in self.librarySettings:
            sections = sorted(sections, key=lambda s: self.librarySettings["order"].index(s.key)
                              if s.key in self.librarySettings["order"] else -1)

        # speedup if we don't have any hidden libraries
        if not self.anyLibraryHidden:
            self.wantedSections = None

        if plexapp.SERVERMANAGER.selectedServer.hasHubs():
            self.tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections, self.ignoredHubs)
                          for s in [home_section] + sections if not s.server.DEFER_HUBS]
            backgroundthread.BGThreader.addTasks(self.tasks)

        show_pm_indicator = util.getSetting('path_mapping_indicators')
        for section in sections:
            mli = kodigui.ManagedListItem(section.title,
                                          thumbnailImage='script.plex/home/type/{0}.png'.format(section.type),
                                          data_source=section)
            mli.setProperty('item', '1')
            if section == playlists_section:
                mli.setProperty('is.playlists', '1')
                mli.setThumbnailImage('script.plex/home/type/playlists.png')
            elif section == watchlist_section:
                mli.setThumbnailImage('script.plex/home/type/watchlist.png')
            if pmm.mapping and show_pm_indicator:
                mli.setBoolProperty('is.mapped', section.isMapped)
            items.append(mli)

        self.bottomItem = len(items) - 1

        for x in range(len(items), 8):
            mli = kodigui.ManagedListItem()
            items.append(mli)

        self.lastSection = focus_section or home_section
        self.sectionList.reset()
        self.sectionList.addItems(items)

        if not focus_section:
            if items:
                self.setFocusId(self.SECTION_LIST_ID)
            else:
                self.setFocusId(self.SERVER_BUTTON_ID)
        else:
            self.setFocusId(self.SECTION_LIST_ID)

    def showHubs(self, section=None, update=False, force=False, reselect_pos_dict=None):
        self.setBoolProperty('no.content', False)
        if not update:
            self.setProperty('drawing', '1')
        try:
            self._showHubs(section=section, update=update, force=force, reselect_pos_dict=reselect_pos_dict)
        finally:
            self.setProperty('drawing', '')

    def getCurrentHubsPositions(self, section):
        is_home = section.key is None
        rp = {}
        # self.sectionHubs[section.key] might be None
        if not self.sectionHubs.get(section.key, []):
            return rp

        for hub in self.sectionHubs.get(section.key, []):
            identifier = hub.getCleanHubIdentifier(is_home=is_home)
            if identifier in self.HUBMAP:
                pos = self.hubControls[self.HUBMAP[identifier]['index']].getSelectedPos()
                if pos is not None:
                    mli = self.hubControls[self.HUBMAP[identifier]['index']].getItemByPos(pos)
                    if mli.dataSource:
                        # continue/inprogress hubs update their order after items have changed their state, skip those
                        if (identifier in ('home.continue', 'home.ondeck', 'continueWatching')
                                or identifier.endswith('.inprogress')):
                            rp[identifier] = (str(mli.dataSource.ratingKey), 0)
                            continue
                        rp[identifier] = (str(mli.dataSource.ratingKey), pos)
        return rp

    @busy.busy_property()
    def _showHubs(self, section=None, update=False, force=False, reselect_pos_dict=None):
        if not update:
            self.clearHubs()

        if not section.server.DEFER_HUBS and not plexapp.SERVERMANAGER.selectedServer.hasHubs():
            return

        if section.key is False:
            return

        hubs = self.sectionHubs.get(section.key)
        section_stale = False

        if hubs is None and section.server.DEFER_HUBS:
            util.DEBUG_LOG('Showing deferred hubs - Section: {0} - Update: {1}', section.key, update)
            force = True
            hubs = HubsList()
            self.setBoolProperty('loading.content', True)

        if not force:
            if hubs is not None:
                section_stale = time.time() - hubs.lastUpdated > HUBS_REFRESH_INTERVAL

            # hubs.invalid is True when the last hub update errored. if the hub is stale, refresh it, though
            if hubs is not None and hubs.invalid and not section_stale:
                util.DEBUG_LOG("Section fetch has failed: {}", section.key)
                self.setBoolProperty('no.content', True)
                return

            if not hubs and not section_stale:
                for task in self.tasks:
                    if task.section == section:
                        backgroundthread.BGThreader.moveToFront(task)
                        break

                if section.type != "home":
                    self.setBoolProperty('no.content', True)
                return

        if section_stale or force:
            util.DEBUG_LOG('Section is stale: {0} REFRESHING - update: {1}, failed before: {2}'.format(
                "Home" if section.key is None else section.key, update, "Unknown" if not hubs else hubs.invalid))
            hubs.lastUpdated = time.time()
            self.cleanTasks()

            rpd = self.getCurrentHubsPositions(section)

            if not update:
                if section.key in self.sectionHubs:
                    self.sectionHubs[section.key] = None
            task = SectionHubsTask().setup(section, self.sectionHubsCallback, self.wantedSections,
                                           reselect_pos_dict=rpd,
                                           ignore_hubs=self.ignoredHubs)
            self.tasks.append(task)
            backgroundthread.BGThreader.addTask(task)
            return

        util.DEBUG_LOG('Showing hubs - Section: {0} - Update: {1}', section.key, update)
        hasContent = False
        skip = {}

        for hub in hubs:
            identifier = hub.getCleanHubIdentifier(is_home=not section.key)

            if identifier not in self.HUBMAP:
                util.DEBUG_LOG('UNHANDLED - Hub: {0} [{1}]({2})'.format(hub.hubIdentifier, identifier,
                                                                        len(hub.items)))
                continue

            skip[self.HUBMAP[identifier]['index']] = 1

            if self.showHub(hub, is_home=not section.key,
                            reselect_pos=reselect_pos_dict.get(identifier) if reselect_pos_dict else None):
                if hub.items:
                    hasContent = True
                if self.HUBMAP[identifier].get('do_updates'):
                    self.updateHubs[identifier] = hub

        if not hasContent:
            self.setBoolProperty('no.content', True)

        lastSkip = 0
        if skip:
            lastSkip = min(skip.keys())

        focus = None
        if update:
            for i, control in enumerate(self.hubControls):
                if i in skip:
                    lastSkip = i
                    continue
                if self.getFocusId() == control.getId():
                    focus = lastSkip
                control.reset()

            if focus is not None:
                self.setFocusId(focus)
        self.storeLastBG()

    def showHub(self, hub, items=None, is_home=False, reselect_pos=None):
        identifier = hub.getCleanHubIdentifier(is_home=is_home)

        if identifier in self.HUBMAP:
            util.DEBUG_LOG('HUB: {0} [{1}]({2}, {3}, reselect: {4})'.format(hub.hubIdentifier,
                                                                            identifier,
                                                                            len(hub.items),
                                                                            len(items) if items else None,
                                                                            reselect_pos),
                           )
            self._showHub(hub, hubitems=items, reselect_pos=reselect_pos, identifier=identifier,
                          **self.HUBMAP[identifier])
            return True
        else:
            util.DEBUG_LOG('UNHANDLED - Hub: {0} [{1}]({1})', hub.hubIdentifier, identifier,
                           lambda: len(hub.items))
            return

    def createGrandparentedListItem(self, obj, thumb_w, thumb_h, with_grandparent_title=False):
        if with_grandparent_title and obj.get('grandparentTitle') and obj.title:
            title = u'{0} - {1}'.format(obj.grandparentTitle, obj.title)
        else:
            title = obj.get('grandparentTitle') or obj.get('parentTitle') or obj.title or ''
        mli = kodigui.ManagedListItem(title, thumbnailImage=obj.defaultThumb.asTranscodedImageURL(thumb_w, thumb_h), data_source=obj)
        return mli

    def createParentedListItem(self, obj, thumb_w, thumb_h, with_parent_title=False):
        if with_parent_title and obj.parentTitle and obj.title:
            title = u'{0} - {1}'.format(obj.parentTitle, obj.title)
        else:
            title = obj.parentTitle or obj.title or ''

        mli = kodigui.ManagedListItem(title, thumbnailImage=obj.defaultThumb.asTranscodedImageURL(thumb_w, thumb_h), data_source=obj)

        return mli

    def createSimpleListItem(self, obj, thumb_w, thumb_h):
        mli = kodigui.ManagedListItem(obj.title or '', thumbnailImage=obj.defaultThumb.asTranscodedImageURL(thumb_w, thumb_h), data_source=obj)
        return mli

    def createEpisodeListItem(self, obj, wide=False):
        mli = self.createGrandparentedListItem(obj, *self.THUMB_POSTER_DIM)
        if obj.index:
            subtitle = u'{0} \u2022 {1}'.format(T(32310, 'S').format(obj.parentIndex), T(32311, 'E').format(obj.index))
        else:
            subtitle = obj.originallyAvailableAt.asDatetime('%m/%d/%y')

        if wide:
            mli.setLabel2(u'{0} - {1}'.format(util.shortenText(obj.title, 35), subtitle))
        else:
            mli.setLabel2(subtitle)

        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
        if not obj.isWatched:
            mli.setProperty('unwatched', '1')
        mli.setBoolProperty('watched', obj.isFullyWatched)
        return mli

    def createSeasonListItem(self, obj, wide=False):
        mli = self.createParentedListItem(obj, *self.THUMB_POSTER_DIM)
        # mli.setLabel2('Season {0}'.format(obj.index))
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
        mli.setLabel2(obj.title)

        if not obj.isWatched:
            mli.setProperty('unwatched.count', str(obj.unViewedLeafCount))
            mli.setBoolProperty('unwatched.count.large', obj.unViewedLeafCount > 999)
        mli.setBoolProperty('watched', obj.isFullyWatched)
        return mli

    def createMovieListItem(self, obj, wide=False):
        mli = kodigui.ManagedListItem(obj.defaultTitle, obj.year, thumbnailImage=obj.defaultThumb.asTranscodedImageURL(*self.THUMB_POSTER_DIM), data_source=obj)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie.png')
        if not obj.isWatched:
            mli.setProperty('unwatched', '1')
        mli.setBoolProperty('watched', obj.isFullyWatched)
        return mli

    def createShowListItem(self, obj, wide=False):
        mli = self.createSimpleListItem(obj, *self.THUMB_POSTER_DIM)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
        if not obj.isWatched:
            mli.setProperty('unwatched.count', str(obj.unViewedLeafCount))
            mli.setBoolProperty('unwatched.count.large', obj.unViewedLeafCount > 999)
        mli.setBoolProperty('watched', obj.isFullyWatched)
        return mli

    def createAlbumListItem(self, obj, wide=False):
        mli = self.createParentedListItem(obj, *self.THUMB_SQUARE_DIM)
        mli.setLabel2(obj.title)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/music.png')
        return mli

    def createTrackListItem(self, obj, wide=False):
        mli = self.createGrandparentedListItem(obj, *self.THUMB_SQUARE_DIM)
        mli.setLabel2(obj.title)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/music.png')
        return mli

    def createPhotoListItem(self, obj, wide=False):
        mli = self.createSimpleListItem(obj, *self.THUMB_SQUARE_DIM)
        if obj.type == 'photo':
            mli.setLabel2(obj.originallyAvailableAt.asDatetime('%d %B %Y'))
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/photo.png')
        return mli

    def createClipListItem(self, obj, wide=False):
        mli = self.createGrandparentedListItem(obj, *self.THUMB_AR16X9_DIM, with_grandparent_title=True)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie16x9.png')
        return mli

    def createArtistListItem(self, obj, wide=False):
        mli = self.createSimpleListItem(obj, *self.THUMB_SQUARE_DIM)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/music.png')
        return mli

    def createPlaylistListItem(self, obj, wide=False):
        if obj.playlistType == 'audio':
            w, h = self.THUMB_SQUARE_DIM
            thumb = obj.buildComposite(width=w, height=h, media='thumb')
        else:
            w, h = self.THUMB_AR16X9_DIM
            thumb = obj.buildComposite(width=w, height=h, media='art')

        mli = kodigui.ManagedListItem(
            obj.title or '',
            util.durationToText(obj.duration.asInt()),
            # thumbnailImage=obj.composite.asTranscodedImageURL(*self.THUMB_DIMS[obj.playlistType]['item.thumb']),
            thumbnailImage=thumb,
            data_source=obj
        )
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(obj.playlistType == 'audio' and 'music' or 'movie'))
        return mli

    def unhandledHub(self, self2, obj, wide=False):
        util.DEBUG_LOG('Unhandled Hub item: {0}', obj.type)

    CREATE_LI_MAP = {
        'episode': createEpisodeListItem,
        'season': createSeasonListItem,
        'movie': createMovieListItem,
        'show': createShowListItem,
        'album': createAlbumListItem,
        'track': createTrackListItem,
        'photo': createPhotoListItem,
        'photodirectory': createPhotoListItem,
        'clip': createClipListItem,
        'artist': createArtistListItem,
        'playlist': createPlaylistListItem
    }

    def createListItem(self, obj, wide=False):
        return self.CREATE_LI_MAP.get(obj.type, self.unhandledHub)(self, obj, wide)

    def clearHubs(self):
        for control in self.hubControls:
            control.reset()

    def _showHub(self, hub, hubitems=None, reselect_pos=None, identifier=None, index=None, with_progress=False,
                 with_art=False, ar16x9=False, text2lines=False, **kwargs):
        control = self.hubControls[index]
        control.dataSource = hub

        if not hub.items and not hubitems:
            control.reset()
            if self.lastFocusID == index + 400 and not self._anyItemAction:
                util.DEBUG_LOG("Hub {} was focused but is gone.", identifier)
                hubControlIndex = self.lastFocusID - 400
                self.focusFirstValidHub(hubControlIndex)
            return

        if not hubitems:
            hub.reset()

        self.setProperty('hub.4{0:02d}'.format(index), hub.title or kwargs.get('title'))
        self.setProperty('hub.text2lines.4{0:02d}'.format(index), text2lines and '1' or '')

        use_reselect_pos = False
        if reselect_pos is not None:
            rk, pos = reselect_pos
            use_reselect_pos = True if rk is not None else (pos > 0 or pos == -1)

            if pos == 0 and not use_reselect_pos:
                # we might want to force the first position, check the hubs position
                if control.getSelectedPos() > 0:
                    use_reselect_pos = True

        items = []

        check_spoilers = False

        # fetch previously seen item states
        # date, view count, last viewed at
        hub_item_state_key = "_".join([plexapp.util.INTERFACE.getRCBaseKey(), identifier])
        hub_item_states = (util.HUB_ITEM_STATES.get(hub_item_state_key, {}) or {"movie": 0,
                                                                                "episode": 0,
                                                                                "season": 0,
                                                                                "show": 0})
        cks = []
        urls = []

        hub_is_watchlist = hub.is_watchlist

        for obj in hubitems or hub.items:
            if not self.backgroundSet and not use_reselect_pos:
                if self.updateBackgroundFrom(obj):
                    self.backgroundSet = True

            wide = with_art
            no_spoilers = False
            if obj.type == 'episode' and hub.hubIdentifier == "home.continue" and self.spoilerSetting != "off":
                check_spoilers = True
                obj._noSpoilers = no_spoilers = self.hideSpoilers(obj, use_cache=False)

            if obj.type == 'episode' and util.addonSettings.continueUseThumb and wide:
                # with_art sets the wide parameter which includes the episode title
                wide = no_spoilers in ("funwatched", "unwatched") and not self.noTitles

            # determine whether we need to clear caches based on item parameters
            if obj.cachable and obj.type in hub_item_states:
                seen = hub_item_states[obj.type]
                last_update = max(int(obj.get('addedAt', 0)), int(obj.get('updatedAt', 0)))
                if seen < last_update:
                    _cks, _urls = obj.clearCache(return_urls=True)
                    cks += _cks
                    urls += _urls
                    hub_item_states[obj.type] = last_update

            if hub_is_watchlist:
                obj.is_watchlist = True

            mli = self.createListItem(obj, wide=wide)
            if mli:
                items.append(mli)

        if util.getSetting('cache_requests'):
            cks = list(set(cks))
            urls = list(set(urls))
            if cks:
                obj._clearCache(cks, urls)

            util.HUB_ITEM_STATES[hub_item_state_key] = hub_item_states

        if with_progress:
            for mli in items:
                mli.setProperty('progress', util.getProgressImage(mli.dataSource))
        if with_art:
            for mli in items:
                extra_opts = {}
                thumb = mli.dataSource.art
                # use episode thumbnail for in progress episodes
                if mli.dataSource.type == 'episode' and util.addonSettings.continueUseThumb and check_spoilers:
                    # blur them if we don't want any spoilers and the episode hasn't been fully watched
                    if self.noResumeImages and mli.dataSource._noSpoilers:
                        extra_opts = {"blur": util.addonSettings.episodeNoSpoilerBlur}
                    thumb = mli.dataSource.thumb

                mli.setThumbnailImage(thumb.asTranscodedImageURL(*self.THUMB_AR16X9_DIM, **extra_opts))
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie16x9.png')
        if ar16x9:
            for mli in items:
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie16x9.png')

        more = hub.more.asBool()
        if more:
            end = kodigui.ManagedListItem('')
            end.setBoolProperty('is.end', True)
            items.append(end)

        if hubitems:
            end = control.size() - 1
            control.replaceItem(end, items[0])
            control.addItems(items[1:])
            if reselect_pos is None:
                control.selectItem(end)
        else:
            control.replaceItems(items)

        # hub reselect logic after updating a hub
        if use_reselect_pos:
            rk, pos = reselect_pos

            # round-robin
            if pos == -1:
                last_pos = control.size() - 1
                if hub.more:
                    last_pos -= 1

                control.selectItem(last_pos)
                self._lastSelectedItem = (index + 400, last_pos)
                if self.updateBackgroundFrom(control[last_pos].dataSource):
                    self.backgroundSet = True
                return

            # during hub updates, if the user manually selects a different item, do nothing
            if self._anyItemAction:
                return

            cur_pos = control.getSelectedPos()

            if rk is not None:
                rk_found = False
                # try finding the ratingKey first
                for idx, mli in enumerate(control):
                    if mli.dataSource and mli.dataSource.ratingKey and str(mli.dataSource.ratingKey) == rk:
                        if cur_pos != idx:
                            util.DEBUG_LOG("Hub {}: Reselect: Found {} in list ({} vs. {}), reselecting",
                                           identifier, rk, idx, pos)
                            control.selectItem(idx)
                            rk_found = True
                            pos = idx
                            break
                        else:
                            return
                if rk_found:
                    if self.updateBackgroundFrom(control[pos].dataSource):
                        self.backgroundSet = True
                    return

            if cur_pos == pos:
                util.DEBUG_LOG("Hub {}: Position was already correct ({})", identifier, pos)
                return

            if pos < control.size() - (more and 1 or 0):
                # we didn't find the ratingKey, try the position first, if it's smaller than our list size
                util.DEBUG_LOG("Hub {}: Reselect: We didn't find {} in list, or no item given. "
                               "Reselecting position {}", identifier, rk, pos)
                control.selectItem(pos)
                if self.updateBackgroundFrom(control[pos].dataSource):
                    self.backgroundSet = True
            else:
                if more:
                    # re-extend the hub to its original size so we can reselect the ratingKey/position
                    # calculate how many pages we need to re-arrive at the last selected position
                    # fixme: someone check for an off-by-one please
                    size = max(math.ceil((pos + 2 - control.size()) / HUB_PAGE_SIZE), 1) * HUB_PAGE_SIZE
                    util.DEBUG_LOG("Hub {}: Reselect: Hub position for {} out of bounds ({}), "
                                   "expanding hub ", identifier, rk, pos)
                    task = ExtendHubTask().setup(control.dataSource, self.extendHubCallback,
                                                 canceledCallback=lambda h: mli.setBoolProperty('is.updating', False),
                                                 size=size, reselect_pos=reselect_pos)
                    self.tasks.append(task)
                    backgroundthread.BGThreader.addTask(task)
                else:
                    control.selectItem(control.size() - 1)
                    if self.updateBackgroundFrom(control[control.size() - 1].dataSource):
                        self.backgroundSet = True

    def updateListItem(self, mli):
        if not mli or not mli.dataSource:  # May have become invalid
            return

        obj = mli.dataSource
        if obj.type in ('episode', 'movie'):
            mli.setProperty('unwatched', not obj.isWatched and '1' or '')
            mli.setProperty('watched', obj.isFullyWatched and '1' or '')
        elif obj.type in ('season', 'show', 'album'):
            mli.setProperty('watched', obj.isFullyWatched and '1' or '')
            if obj.isWatched:
                mli.setProperty('unwatched.count', '')
            else:
                mli.setProperty('unwatched.count', str(obj.unViewedLeafCount))
                mli.setBoolProperty('unwatched.count.large', obj.unViewedLeafCount > 999)

    def sectionClicked(self):
        item = self.sectionList.getSelectedItem()
        if not item:
            return

        section = item.dataSource
        self.lastSection = section

        if section.type in ('show', 'movie', 'artist', 'photo', 'mixed'):
            self.processCommand(opener.sectionClicked(section))
            self.sectionChangeTimeout = None
        elif section.type in ('playlists',):
            self.processCommand(opener.handleOpen(playlists.PlaylistsWindow))

    def onNewServer(self, **kwargs):
        self.showServers(from_refresh=True)

    def onRemoveServer(self, **kwargs):
        self.onNewServer()

    def onReachableServer(self, server=None, **kwargs):
        for mli in self.serverList:
            if mli.uuid == server.uuid:
                mli.unHookSignals()
                mli.dataSource = server
                mli.hookSignals()
                mli.onUpdate()
                return
        else:
            self.onNewServer()

    def onSelectedServerChange(self, **kwargs):
        if self.serverRefresh():
            self.setFocusId(self.SECTION_LIST_ID)
            self.changingServer = False

    def showServers(self, from_refresh=False, mouse=False):
        with self.lock:
            selection = None
            if from_refresh:
                mli = self.serverList.getSelectedItem()
                if mli:
                    selection = mli.uuid

            servers = sorted(
                plexapp.SERVERMANAGER.getServers(),
                key=lambda x: (x.owned and '0' or '1') + x.name.lower()
            )

            items = []
            for s in servers:
                item = ServerListItem(s.name, not s.owned and s.owner or '', data_source=s)
                item.uuid = s.uuid
                item.onUpdate()
                item.setProperty('current', plexapp.SERVERMANAGER.selectedServer.uuid == s.uuid and '1' or '')
                items.append(item)

            if len(items) > 1:
                items[0].setProperty('first', '1')
            elif items:
                items[0].setProperty('only', '1')

            self.serverList.replaceItems(items)
            itemHeight = util.vscale(100, r=0)

            self.getControl(800).setHeight((min(len(items), 9) * itemHeight) + 80)

            for item in items:
                if item.dataSource != kodigui.DUMMY_DATA_SOURCE:
                    item.hookSignals()

            if selection:
                for mli in self.serverList:
                    if mli.uuid == selection:
                        self.serverList.selectItem(mli.pos())

            if not from_refresh and items and not mouse:
                self.setFocusId(self.SERVER_LIST_ID)

            if not from_refresh:
                plexapp.refreshResources()

    def selectServer(self, uuid=None):
        if self._shuttingDown:
            return

        if not uuid:
            mli = self.serverList.getSelectedItem()
            if not mli:
                return
            server = mli.dataSource
        else:
            server = plexapp.SERVERMANAGER.getServer(uuid)
            if not server:
                return

        # store last used server
        prevUUID = plexapp.SERVERMANAGER.selectedServer.uuid

        self.changingServer = True

        # this is broken
        with busy.BusySignalContext(plexapp.util.APP, "change:selectedServer") as bc:
            self.setFocusId(self.SECTION_LIST_ID)

            # fixme: this might still trigger a dialog, re-triggering the previously opened windows
            if not self._shuttingDown and not server.isReachable():
                if server.pendingReachabilityRequests > 0:
                    util.messageDialog(T(32339, 'Server is not accessible'), T(32340, 'Connection tests are in '
                                                                                      'progress. Please wait.'))
                else:
                    util.messageDialog(
                        T(32339, 'Server is not accessible'), T(32341, 'Server is not accessible. Please sign into '
                                                                       'your server and check your connection.')
                    )
                bc.ignoreSignal = True
                return

            changed = plexapp.SERVERMANAGER.setSelectedServer(server, force=True)
            if not changed:
                bc.ignoreSignal = True
                self.changingServer = False
            else:
                util.setSetting('previous_server.{}'.format(plexapp.ACCOUNT.ID), prevUUID)

    def showUserMenu(self, mouse=False):
        items = []
        if plexapp.ACCOUNT.isSignedIn:
            if not len(plexapp.ACCOUNT.homeUsers) and not util.addonSettings.cacheHomeUsers:
                plexapp.ACCOUNT.updateHomeUsers(refreshSubscription=True)

            if len(plexapp.ACCOUNT.homeUsers) > 1:
                items.append(kodigui.ManagedListItem(T(32342, 'Switch User'), data_source='switch'))
            else:
                items.append(kodigui.ManagedListItem(T(32980, 'Refresh Users'), data_source='refresh_users'))
        items.append(kodigui.ManagedListItem(T(32343, 'Settings'), data_source='settings'))
        if plexapp.ACCOUNT.isSignedIn:
            items.append(kodigui.ManagedListItem(T(32344, 'Sign Out'), data_source='signout'))
        elif plexapp.ACCOUNT.isOffline:
            items.append(kodigui.ManagedListItem(T(32459, 'Offline Mode'), data_source='go_online'))
        else:
            items.append(kodigui.ManagedListItem(T(32460, 'Sign In'), data_source='signin'))

        if len(items) > 1:
            items[0].setProperty('first', '1')
            items[-1].setProperty('last', '1')
        else:
            items[0].setProperty('only', '1')

        self.userList.reset()
        self.userList.addItems(items)
        itemHeight = util.vscale(66, r=0)

        self.getControl(801).setHeight((len(items) * itemHeight) + 80)

        if not mouse:
            self.setFocusId(self.USER_LIST_ID)

    def doUserOption(self, force_option=None):
        if not force_option:
            mli = self.userList.getSelectedItem()
            if not mli:
                return

            option = mli.dataSource
        else:
            option = force_option

        def kill_background():
            util.DEBUG_LOG("Killing last background image")
            kodigui.LAST_BG_URL = None
            self.windowSetBackground(None)

        self.setFocusId(self.USER_BUTTON_ID)

        if option == 'settings':
            from . import settings
            settings.openWindow()
        elif option == 'go_online':
            plexapp.ACCOUNT.refreshAccount()
        elif option == 'refresh_users':
            plexapp.ACCOUNT.updateHomeUsers(refreshSubscription=True)
            return True
        elif option == 'signout':
            button = optionsdialog.show(
                T(32344, 'Sign Out'),
                T(33669, 'Really sign out?'),
                T(32329, 'No'),
                T(32328, 'Yes'),
                dialog_props=self.carriedProps
            )

            if button != 1:
                return
            self.closeOption = option
            kill_background()
            self.doClose()
        else:
            self.closeOption = option
            kill_background()
            self.doClose()

    def showAudioPlayer(self):
        from . import musicplayer
        self.processCommand(opener.handleOpen(musicplayer.MusicPlayerWindow))

    def finished(self):
        if self.tasks:
            for task in self.tasks:
                task.cancel()
