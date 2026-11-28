from __future__ import absolute_import

import json
import os
import random
import threading

import plexnet
import six
import six.moves.urllib.error
import six.moves.urllib.parse
import six.moves.urllib.request
from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import playqueue
from plexnet import playlist
from plexnet import plexobjects
from plexnet import util as pnUtil
from six.moves import range

from lib import backgroundthread
from lib import player
from lib import util
from lib import shuffle
from lib.util import T
from . import busy
from . import dropdown
from . import kodigui
from . import opener
from . import videoplayer
from . import optionsdialog
from . import preplay
from . import search
from . import subitems
from . import windowutils
from .mixins.playbackbtn import PlaybackBtnMixin
from .mixins.watchlist import autoRemoveFromWatchlist, removeFromWatchlistBlind
from .mixins.common import CommonMixin

KEYS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

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

THUMB_POSTER_DIM = util.scaleResolution(268, 402)
THUMB_AR16X9_DIM = util.scaleResolution(619, 348)
THUMB_SQUARE_DIM = util.scaleResolution(355, 355)
ART_AR16X9_DIM = util.scaleResolution(630, 355)

TYPE_KEYS = {
    'episode': {
        'fallback': 'show',
        'thumb_dim': THUMB_POSTER_DIM,
    },
    'season': {
        'fallback': 'show',
        'thumb_dim': THUMB_POSTER_DIM
    },
    'movie': {
        'fallback': 'movie',
        'thumb_dim': THUMB_POSTER_DIM,
        'art_dim': ART_AR16X9_DIM
    },
    'show': {
        'fallback': 'show',
        'thumb_dim': THUMB_POSTER_DIM,
        'art_dim': ART_AR16X9_DIM
    },
    'collection': {
        'fallback': 'movie',
        'thumb_dim': THUMB_POSTER_DIM,
        'art_dim': ART_AR16X9_DIM
    },
    'album': {
        'fallback': 'music',
        'thumb_dim': THUMB_SQUARE_DIM
    },
    'artist': {
        'fallback': 'music',
        'thumb_dim': THUMB_SQUARE_DIM
    },
    'track': {
        'fallback': 'music',
        'thumb_dim': THUMB_SQUARE_DIM
    },
    'photo': {
        'fallback': 'photo',
        'thumb_dim': THUMB_SQUARE_DIM
    },
    'clip': {
        'fallback': 'movie16x9',
        'thumb_dim': THUMB_POSTER_DIM
    },
}

TYPE_PLURAL = {
    'artist': T(32347, 'artists'),
    'album': T(32461, 'albums'),
    'movie': T(32348, 'Movies'),
    'photo': T(32349, 'photos'),
    'show': T(32350, 'Shows'),
    'episode': T(32458, 'Episodes'),
    'collection': T(32490, 'Collections'),
    'folder': T(32491, 'Folders'),
    'track': T(33644, 'Tracks'),
    # watchlist
    'movies_shows': T(34002, "Movies & Shows"),
}

SORT_KEYS = {
    'movie': {
        'titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'addedAt': {'title': T(32351, 'By Date Added'), 'display': T(32352, 'Date Added'), 'defSortDesc': True},
        'originallyAvailableAt': {'title': T(32353, 'By Release Date'), 'display': T(32354, 'Release Date'),
                                  'defSortDesc': True, 'subDisplay': 'originallyAvailableAt', 'subDisplayExclusive': True},
        'lastViewedAt': {'title': T(32355, 'By Date Viewed'), 'display': T(32356, 'Date Viewed'), 'defSortDesc': True, 'subDisplay': 'lastViewedAt'},
        'rating': {'title': T(33107, 'By Critic Rating'), 'display': T(33108, ' Critic Rating'), 'defSortDesc': True},
        'audienceRating': {'title': T(33101, 'By Audience Rating'), 'display': T(33102, 'Audience Rating'),
                           'defSortDesc': True},
        # called "Rating" in PlexWeb, using more obvious "This is this user's rating" here
        'userRating': {'title': T(33103, 'By my Rating'), 'display': T(33104, 'My Rating'), 'defSortDesc': True},
        'contentRating': {'title': T(33105, 'By Content Rating'), 'display': T(33106, 'Content Rating'),
                          'defSortDesc': False, 'subDisplay': 'contentRating'},
        'resolution': {'title': T(32361, 'By Resolution'), 'display': T(32362, 'Resolution'), 'defSortDesc': True, 'subDisplay': 'resolutionString'},
        'duration': {'title': T(32363, 'By Duration'), 'display': T(32364, 'Duration'), 'defSortDesc': True, 'subDisplay': 'duration'},
        'unwatched': {'title': T(32367, 'By Unplayed'), 'display': T(32368, 'Unplayed'), 'defSortDesc': False},
        'year': {'title': T(32377, 'Year'), 'display': T(32377, 'Year'), 'defSortDesc': True},
        'viewOffset': {'title': T(34040, 'By Progress'), 'display': T(34041, 'Progress'), 'defSortDesc': True},
        'viewCount': {'title': T(32371, 'By Play Count'), 'display': T(32372, 'Play Count'), 'defSortDesc': True, 'subDisplay': 'viewCount'},
        'mediaBitrate': {'title': T(33731, 'By Bitrate'), 'display': T(33732, 'Bitrate'), 'defSortDesc': True, 'subDisplay': 'mediaBitrate'},
        'random': {'title': T(33730, 'Randomly'), 'display': T(33730, 'Randomly'), 'defSortDesc': True},
    },
    'show': {
        'titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'year': {'title': T(32377, "Year"), 'display': T(32377, "Year"), 'defSortDesc': True},
        'show.titleSort': {'title': T(32457, 'By Show'), 'display': T(32456, 'Show'), 'defSortDesc': False},
        'originallyAvailableAt': {'title': T(32353, 'By Release Date'), 'display': T(32354, 'Release Date'),
                                  'defSortDesc': True, 'subDisplay': 'originallyAvailableAt', 'subDisplayExclusive': True},
        'rating': {'title': T(33107, 'By Critic Rating'), 'display': T(33108, ' Critic Rating'), 'defSortDesc': True},
        'audienceRating': {'title': T(33101, 'By Audience Rating'), 'display': T(33102, 'Audience Rating'),
                           'defSortDesc': True},
        # called "Rating" in PlexWeb, using more obvious "This is this user's rating" here
        'userRating': {'title': T(33103, 'By my Rating'), 'display': T(33104, 'My Rating'), 'defSortDesc': True},
        'contentRating': {'title': T(33105, 'By Content Rating'), 'display': T(33106, 'Content Rating'),
                          'defSortDesc': True, 'subDisplay': 'contentRating'},
        'unviewedLeafCount': {'title': T(32367, 'By Unplayed'), 'display': T(32368, 'Unplayed'), 'defSortDesc': True},
        'episode.addedAt': {'title': T(33042, 'Episode Date Added'), 'display': T(33042, 'Episode Date Added'), 'defSortDesc': True},
        'addedAt': {'title': T(32351, 'By Date Added'), 'display': T(32352, 'Date Added'), 'defSortDesc': True, 'subDisplay': 'addedAt'},
        'lastViewedAt': {'title': T(32355, 'By Date Added'), 'display': T(32356, 'Date Added'), 'defSortDesc': True, 'subDisplay': 'lastViewedAt'},
        'random': {'title': T(33730, 'Randomly'), 'display': T(33730, 'Randomly'), 'defSortDesc': True},
    },
    'artist': {
        'titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'userRating': {'title': T(33103, 'By my Rating'), 'display': T(33104, 'My Rating'), 'defSortDesc': True},
        'addedAt': {'title': T(32351, 'By Date Added'), 'display': T(32352, 'Date Added'), 'defSortDesc': True, 'subDisplay': 'addedAt'},
        'lastViewedAt': {'title': T(32369, 'By Date Played'), 'display': T(32370, 'Date Played'), 'defSortDesc': False},
        'viewCount': {'title': T(32371, 'By Play Count'), 'display': T(32372, 'Play Count'), 'defSortDesc': True, 'subDisplay': 'viewCount'},
        'random': {'title': T(33730, 'Randomly'), 'display': T(33730, 'Randomly'), 'defSortDesc': True},
    },
    'track': {
        'titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'userRating': {'title': T(33103, 'By my Rating'), 'display': T(33104, 'My Rating'), 'defSortDesc': True},
        'artist.titleSort': {'title': T(32463, 'By Artist'), 'display': T(32462, 'Artist'), 'defSortDesc': False},
        'lastViewedAt': {'title': T(32369, 'By Date Played'), 'display': T(32370, 'Date Played'), 'defSortDesc': True},
        'viewCount': {'title': T(32371, 'By Play Count'), 'display': T(32372, 'Play Count'), 'defSortDesc': True}
    },
    'photo': {
        'addedAt': {'title': T(32351, 'By Date Added'), 'display': T(32352, 'Date Added'), 'defSortDesc': True, 'subDisplay': 'addedAt'},
        'originallyAvailableAt': {'title': T(32373, 'By Date Taken'), 'display': T(32374, 'Date Taken'),
                                  'defSortDesc': True, 'subDisplay': 'originallyAvailableAt', 'subDisplayExclusive': True},
        'photos.titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'mediaCount': {'title': T(34042, 'By Album'), 'display': T(34043, 'Album'), 'defSortDesc': False},
    },
    'photodirectory': {},
    'collection': {},
    # watchlist
    'movies_shows': {
        'watchlistedAt': {'title': T(32351, 'By Date Added'), 'display': T(32352, 'Date Added'), 'defSortDesc': True},
        'titleSort': {'title': T(32357, 'By Title'), 'display': T(32358, 'Title'), 'defSortDesc': False},
        'firstAvailableAt': {'title': T(32353, 'By Release Date'), 'display': T(32354, 'Release Date'),
                                          'defSortDesc': True},
        'rating': {'title': T(33107, 'By Critic Rating'), 'display': T(33108, ' Critic Rating'), 'defSortDesc': True},
        'audienceRating': {'title': T(33101, 'By Audience Rating'), 'display': T(33102, 'Audience Rating'),
                           'defSortDesc': True},
    }
}

ITEM_TYPE = None

# Maps a server filter key -> (string id, fallback) for localized labels. Unknown filter
# keys fall back to the server-provided title (hybrid labels).
FILTER_LABELS = {
    'year': (32377, 'Year'),
    'decade': (32378, 'Decade'),
    'genre': (32379, 'Genre'),
    'contentRating': (32380, 'Content Rating'),
    'network': (32381, 'Network'),
    'collection': (32382, 'Collection'),
    'director': (32383, 'Director'),
    'actor': (32384, 'Actor'),
    'writer': (32402, 'Writer'),
    'producer': (34031, 'Producer'),
    'country': (32385, 'Country'),
    'studio': (32386, 'Studio'),
    'resolution': (32362, 'Resolution'),
    'audioLanguage': (34032, 'Audio Language'),
    'subtitleLanguage': (34033, 'Subtitle Language'),
    'editionTitle': (34035, 'Editions'),
    'label': (32387, 'Labels'),
    'released': (34001, 'Released'),
    'make': (32388, 'Camera Make'),
    'model': (32389, 'Camera Model'),
    'aperture': (32390, 'Aperture'),
    'exposure': (32391, 'Shutter Speed'),
    'iso': (None, 'ISO'),  # no dedicated string id; 'ISO' is universal
    'lens': (32392, 'Lens'),
    'location': (34034, 'Folder Location'),
    'unwatched': (32368, 'Unplayed'),
    'hdr': (34037, 'HDR'),
    'dovi': (34036, 'DOVI'),
}


def setItemType(type_=None):
    assert type_ is not None, "Invalid type: None"
    global ITEM_TYPE
    ITEM_TYPE = type_
    util.setGlobalProperty('item.type', str(ITEM_TYPE))

def getQueryItemType(section, fallback_to_section_type=False, force_include_collections=False):
    base_type = ITEM_TYPE

    if fallback_to_section_type and not base_type:
        base_type = section.TYPE

    if not base_type:
        return

    type_ = plexobjects.SEARCHTYPES.get(base_type)

    # combine collections into types, otherwise jumpList/firstCharacter returns different results with
    # includeCollections=1
    if force_include_collections and type_ is not None and type_ != 18:
        type_ = "{},{}".format(type_, 18)
    return type_

class CreateDefaultItemsTask(backgroundthread.Task):
    def setup(self, startPos, count, totalSize, fallback, callback, key=None):
        self.startPos = startPos
        self.count = count
        self.totalSize = totalSize
        self.endPos = self.startPos + self.count
        if self.endPos > self.totalSize:
            self.endPos = self.totalSize
        self.fallback = fallback
        self.callback = callback
        self.key = key
        return self

    def contains(self, pos):
        return self.startPos <= pos < self.endPos

    def run(self):
        if self.isCanceled():
            return

        items = []
        firstMli = None
        for x in range(self.startPos, self.endPos):
            mli = kodigui.ManagedListItem('')
            mli.setProperty('thumb.fallback', self.fallback)
            mli.setProperty('index', str(x))
            if self.key:
                mli.setProperty('key', self.key)
                if x == self.startPos:  # i.e. first item
                    firstMli = mli
            items.append(mli)
        self.callback(items, self.key, firstMli)

class ChunkRequestTask(backgroundthread.Task):
    def setup(self, section, start, size, callback, filter_=None, sort=None, subDir=False, bool_filters=None):
        self.section = section
        self.start = start
        self.size = size
        self.callback = callback
        self.filter = filter_
        self.sort = sort
        self.bool_filters = bool_filters or {}
        self.subDir = subDir
        return self

    def contains(self, pos):
        return self.start <= pos <= (self.start + self.size)

    def run(self):
        if self.isCanceled():
            return

        try:
            type_ = getQueryItemType(self.section)

            if ITEM_TYPE == 'folder':
                items = self.section.folder(self.start, self.size, self.subDir)
            else:
                # supplying this type kills all results (bug: 2025/10/21)
                if type_ == plexobjects.SEARCHTYPES["photo"]:
                    type_ = None
                items = self.section.all(self.start, self.size, self.filter, self.sort, type_=type_,
                                         bool_filters=self.bool_filters)

            if self.isCanceled():
                return
            self.callback(items, self.start)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on section: {0}', repr(self.section.title))


class PhotoPropertiesTask(backgroundthread.Task):
    def setup(self, photo, callback):
        self.photo = photo
        self.callback = callback
        return self

    def run(self):
        if self.isCanceled():
            return

        try:
            self.photo.reload()
            self.callback(self.photo)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on photo reload: {0}', self.photo)


def realSection(section):
    """The library a section belongs to. Pinned top bar item-type views proxy one."""
    return section.__dict__.get('librarySection') or section


class LibrarySettings(object):
    def __init__(self, section_or_server_id, ignoreLibrarySettings=False):
        self.ignoreLibrarySettings = ignoreLibrarySettings
        self.forcedItemType = None
        if isinstance(section_or_server_id, six.string_types):
            self.serverID = section_or_server_id
            self.sectionID = None
        else:
            self.serverID = section_or_server_id.getServer().uuid
            self.sectionID = section_or_server_id.key
            # a pinned item-type view always opens in its own type, no matter which type was
            # last selected while inside it
            self.forcedItemType = section_or_server_id.__dict__.get('itemType')

        self._loadSettings()

    def _loadSettings(self):
        if self.ignoreLibrarySettings:
            self._settings = {}
            return

        if not self.sectionID:
            return

        jsonString = util.getSetting('library.settings.{0}'.format(self.serverID), '')
        self._settings = {}
        try:
            self._settings = json.loads(jsonString)
        except ValueError:
            pass
        except:
            util.ERROR()

        setItemType(self.forcedItemType or self.getItemType() or ITEM_TYPE)

    def getItemType(self):
        if not self._settings or self.sectionID not in self._settings:
            return None

        return self._settings[self.sectionID].get('ITEM_TYPE')

    def setItemType(self, item_type):
        setItemType(item_type)

        if self.sectionID not in self._settings:
            self._settings[self.sectionID] = {}

        self._settings[self.sectionID]['ITEM_TYPE'] = item_type

        self._saveSettings()

    def _saveSettings(self):
        jsonString = json.dumps(self._settings)
        util.setSetting('library.settings.{0}'.format(self.serverID), jsonString)

    def setSection(self, section_id):
        self.sectionID = section_id

    def getSetting(self, setting, default=None):
        if not self._settings or self.sectionID not in self._settings:
            return default

        if ITEM_TYPE not in self._settings[self.sectionID]:
            return default

        return self._settings[self.sectionID][ITEM_TYPE].get(setting, default)

    def setSetting(self, setting, value):
        if self.sectionID not in self._settings:
            self._settings[self.sectionID] = {}

        if ITEM_TYPE not in self._settings[self.sectionID]:
            self._settings[self.sectionID][ITEM_TYPE] = {}

        self._settings[self.sectionID][ITEM_TYPE][setting] = value

        self._saveSettings()


class LibraryWindow(PlaybackBtnMixin, kodigui.MultiWindow, windowutils.UtilMixin, CommonMixin):
    bgXML = 'script-plex-blank.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'

    # Needs to be an even multiple of 6(posters) and 10(small posters) and 12(list)
    # so that we fill an entire row
    CHUNK_SIZE = 240
    CHUNK_OVERCOMMIT = 6
    DEFAULT_ITEMS_CHUNK_SIZE = 250
    DEFAULT_ITEMS_CHUNK_SIZE_BIG = 500

    def __init__(self, *args, **kwargs):
        PlaybackBtnMixin.__init__(self)
        kodigui.MultiWindow.__init__(self, *args, **kwargs)
        windowutils.UtilMixin.__init__(self)
        self.section = kwargs.get('section')
        self.filter = kwargs.get('filter_')
        self.subDir = kwargs.get('subDir')
        self.keyItems = {}
        self.firstOfKeyItems = {}
        self.tasks = backgroundthread.Tasks()
        self.backgroundSet = False
        self.showPanelControl = None
        self.keyListControl = None
        self.lastItem = None
        self.lastFocusID = None
        self.lastNonOptionsFocusID = None
        self.refill = False
        # Bumped every time doRefill() rebuilds showPanelControl. Used to detect that
        # the panel (and its ListItems) was replaced while a modal child window was open,
        # so we never touch a freed ListItem afterwards (see showPanelClicked).
        self._listGeneration = 0
        self.subOptionCache = {}
        self._filterTypeByKey = {}
        self.closing = False

        self.dcpjPos = 0
        self.dcpjThread = None
        self.dcpjTimeout = 0

        self.dragging = False

        self.cleared = True
        self.librarySettings = LibrarySettings(self.section,
                                               ignoreLibrarySettings=kwargs.get("ignoreLibrarySettings", False))
        self.reset()

        self.lock = threading.Lock()

    def reset(self):
        PlaybackBtnMixin.reset(self)
        util.setGlobalProperty('sort', '')
        # Active boolean filters as {filter_key: True}. Start clean on upgrade: old
        # filter.unwatched/filter.hdr/filter.dovi keys are intentionally not read.
        self.boolFilters = self.librarySettings.getSetting('filter.bools', {}) or {}
        self.filter = self.filter or self.librarySettings.getSetting('filter', None)
        self.sort = self.librarySettings.getSetting('sort', self.section.DEFAULT_SORT)
        self.sortDesc = self.librarySettings.getSetting('sort.desc', self.section.DEFAULT_SORT_DESC)

        self.alreadyFetchedChunkList = set()
        self.finalChunkPosition = 0

        if self.section.TYPE == 'movies_shows':
            self.CHUNK_SIZE = min(100, util.addonSettings.libraryChunkSize)
        else:
            self.CHUNK_SIZE = util.addonSettings.libraryChunkSize

        key = self.section.key
        if not key.isdigit():
            key = self.section.getLibrarySectionId()
        viewtype = util.getSetting('viewtype.{0}.{1}'.format(self.section.server.uuid, key))

        if self.section.TYPE in ('artist', 'photo', 'photodirectory'):
            self.setWindows(VIEWS_SQUARE.get('all'))
            self.setDefault(VIEWS_SQUARE.get(viewtype))
        else:
            self.setWindows(VIEWS_POSTER.get('all'))
            self.setDefault(VIEWS_POSTER.get(viewtype))

    def setWatchlistDirty(self, *args, **kwargs):
        if self.section.TYPE == 'movies_shows':
            util.DEBUG_LOG("Library: Watchlist item state changed, setting dirty")
            self.refill = True

    @busy.dialog()
    def doClose(self, **kw):
        self.closing = True
        pnUtil.APP.off("watchlist:modified", self.setWatchlistDirty)
        util.MONITOR.off("library.back_home", self.goHomeRoot)
        self.tasks.kill()
        kodigui.MultiWindow.doClose(self)

    def onFirstInit(self):
        pnUtil.APP.on("watchlist:modified", self.setWatchlistDirty)
        util.MONITOR.on("library.back_home", self.goHomeRoot)
        if self.showPanelControl and not self.refill:
            self.showPanelControl.newControl(self)
            self.keyListControl.newControl(self)
            self.showPanelControl.selectItem(0)
            self.setFocusId(self.VIEWTYPE_BUTTON_ID)
            self.setBoolProperty("initialized", True)
        else:
            self.doRefill()

    def doRefill(self):
        # The previous panel's ListItems are about to be freed and replaced; bump the
        # generation so any caller holding a stale ListItem reference can detect it.
        self._listGeneration += 1
        self.showPanelControl = kodigui.ManagedControlList(self, self.POSTERS_PANEL_ID, 5)

        hideFilterOptions = self.section.TYPE == 'photodirectory' or self.section.TYPE == 'collection'

        self.keyListControl = kodigui.ManagedControlList(self, self.KEY_LIST_ID, 27)
        self.setProperty('disable_playback', self.section.TYPE == 'movies_shows' and '1' or '')
        self.setProperty('subDir', self.subDir and '1' or '')
        self.setProperty('no.options', self.section.TYPE != 'photodirectory' and '1' or '')
        self.setProperty('unwatched.hascount', self.section.TYPE == 'show' and '1' or '')
        util.setGlobalProperty('sort', self.sort)
        # Seed the filter display from current state (value filter + any active booleans),
        # not just unwatched, since boolFilters persists across sessions.
        self.updateFilterDisplay()
        try:
            self.setProperty('sort.display',
                             SORT_KEYS[self.section.TYPE].get(self.sort, SORT_KEYS['movie'].get(self.sort))['title'])
        except TypeError:
            self.resetSort()
            self.setProperty('sort.display',
                             SORT_KEYS[self.section.TYPE].get(self.sort, SORT_KEYS['movie'].get(self.sort))['title'])
        self.setProperty('media.itemType', ITEM_TYPE or self.section.TYPE)
        self.setProperty('media.type', TYPE_PLURAL.get(ITEM_TYPE or self.section.TYPE, self.section.TYPE))
        self.setProperty('media', self.section.TYPE)
        self.setProperty('hide.filteroptions', hideFilterOptions and '1' or '')

        self.setTitle()
        self.setBoolProperty("initialized", True)
        if self.fill() is False:
            self.setFocusId(self.HOME_BUTTON_ID)
            return
        self.refill = False
        if self.getProperty('no.content') or self.getProperty('no.content.filtered'):
            self.setFocusId(self.HOME_BUTTON_ID)
        else:
            self.setFocusId(self.POSTERS_PANEL_ID)

    def onReInit(self):
        if self.refill:
            self.doRefill()
        if player.PLAYER.bgmPlaying:
            player.PLAYER.stopAndWait(fade=util.addonSettings.themeMusicFade, deferred=True)

    def onAction(self, action):
        try:
            if self.dragging:
                if not action == xbmcgui.ACTION_MOUSE_DRAG:
                    self.dragging = False
                    self.setBoolProperty('dragging', self.dragging)

            if action.getId() in MOVE_SET:
                mli = self.showPanelControl.getSelectedItem()
                if mli:
                    self.requestChunk(mli.pos())

                if util.addonSettings.dynamicBackgrounds:
                    if mli and mli.dataSource:
                        self.updateBackgroundFrom(mli.dataSource)

                controlID = self.getFocusId()
                if controlID == self.POSTERS_PANEL_ID or controlID == self.SCROLLBAR_ID:
                    self.updateKey()
            elif action == xbmcgui.ACTION_MOUSE_DRAG:
                self.onMouseDrag(action)
            elif action == xbmcgui.ACTION_CONTEXT_MENU:
                # item action possible?
                had_action = self.itemOptions()
                if not had_action:
                    if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)):
                        self.lastNonOptionsFocusID = self.lastFocusID
                        self.setFocusId(self.OPTIONS_GROUP_ID)
                        return
                    else:
                        if self.lastNonOptionsFocusID:
                            self.setFocusId(self.lastNonOptionsFocusID)
                            self.lastNonOptionsFocusID = None
                            return
                else:
                    return
            elif self.isWatchedAction(action):
                mli = self.showPanelControl.getSelectedItem()
                if not mli or not mli.dataSource:
                    return
                self.toggleWatched(mli)
                return

            elif action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                if not xbmc.getCondVisibility('ControlGroup({0}).HasFocus(0)'.format(self.OPTIONS_GROUP_ID)) and \
                        (not util.addonSettings.fastBack or action == xbmcgui.ACTION_CONTEXT_MENU):
                    if xbmc.getCondVisibility('Integer.IsGreater(Container(101).ListItem.Property(index),5)'):
                        self.showPanelControl.selectItem(0)
                        return

            self.updateItem()

        except:
            util.ERROR()

        kodigui.MultiWindow.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.POSTERS_PANEL_ID:
            self.showPanelClicked()
        elif controlID == self.KEY_LIST_ID:
            self.keyClicked()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif controlID == self.PLAY_BUTTON_ID:
            self.playButtonClicked()
        elif controlID == self.SHUFFLE_BUTTON_ID:
            self.shuffleButtonClicked()
        elif controlID == self.OPTIONS_BUTTON_ID:
            self.optionsButtonClicked()
        elif controlID == self.VIEWTYPE_BUTTON_ID:
            self.viewTypeButtonClicked()
        elif controlID == self.SORT_BUTTON_ID:
            self.sortButtonClicked()
        elif controlID == self.FILTER1_BUTTON_ID:
            self.filter1ButtonClicked()
        elif controlID == self.ITEM_TYPE_BUTTON_ID:
            self.itemTypeButtonClicked()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()

    def onFocus(self, controlID):
        self.lastFocusID = controlID

        if controlID == self.KEY_LIST_ID:
            self.selectKey()

    def onItemChanged(self, mli):
        if not mli:
            return

        if not mli.dataSource or not mli.dataSource.TYPE == 'photo':
            return

        self.showPhotoItemProperties(mli.dataSource)

    def toggleWatched(self, mli, state=None, **kw):
        item = mli.dataSource
        watched = super(LibraryWindow, self).toggleWatched(item, state=state, **kw)
        if watched is None:
            return

        if watched:
            autoRemoveFromWatchlist(item)
        self.updateUnwatchedAndProgress(mli)

    def itemOptions(self):
        mli = self.showPanelControl.getSelectedItem()
        if not mli:
            return True

        if mli.dataSource is None:
            return True

        if mli.dataSource.TYPE in ('episode', 'season', 'movie', 'show'):
            options = []
            ds = mli.dataSource
            wl_ref = ds.show() if ds.TYPE in ('episode', 'season') else ds

            if self.section.TYPE != "movies_shows":
                # we don't want mark watched for watchlist items
                if not mli.getProperty('watched'):
                    options.append({'key': 'mark_watched', 'display': T(32319, "Mark Played")})

                if (ds.isFullyWatched or ds.isWatched or
                        (ds.TYPE in ("show", "season") and 0 < ds.unViewedLeafCount < ds.leafCount)):
                    options.append({'key': 'mark_unwatched', 'display': T(32318, "Mark Unplayed")})
            else:
                options.append({'key': 'remove_from_watchlist', 'display': T(34011, "Remove from watchlist")})

            title = mli.label
            secondary = mli.label2
            if ds.TYPE in ("movie", "show"):
                secondary = mli.getProperty('year')
            elif ds.TYPE == "episode":
                title = ds.defaultTitle
                secondary = mli.getProperty('subtitle')

            label = u"{} ({})".format(six.ensure_str(title), six.ensure_str(secondary))

            choice = dropdown.showDropdown(
                options,
                pos=(660, 441),
                close_direction='none',
                set_dropdown_prop=False,
                header=T(33030, 'Choose action for: {}').format(label),
                align_items="left",
            )

            if choice and choice["key"] in ("mark_watched", "mark_unwatched", "remove_from_watchlist"):
                if util.getSetting('home_confirm_actions'):
                    button = optionsdialog.show(
                        T(32319, "Mark Played") if choice["key"] == "mark_watched"
                        else T(34011,"Remove from watchlist")
                        if choice["key"] == "remove_from_watchlist" else T(32318, "Mark Unplayed"),
                        label,
                        T(32328, 'Yes'),
                        T(32329, 'No'),
                    )

                    if button != 0:
                        return True

                if choice["key"] == "mark_watched":
                    self.toggleWatched(mli, state=True)

                elif choice["key"] == "mark_unwatched":
                    self.toggleWatched(mli, state=False)

                elif choice["key"] == "remove_from_watchlist":
                    removeFromWatchlistBlind(wl_ref.guid, wl_ref)
                    self.doRefill()
            return True


    def updateKey(self, mli=None):
        mli = mli or self.showPanelControl.getSelectedItem()
        if not mli:
            return

        if self.lastItem != mli:
            self.lastItem = mli
            self.onItemChanged(mli)

        util.setGlobalProperty('key', mli.getProperty('key'))

        self.selectKey(mli)

    def selectKey(self, mli=None):
        if not mli:
            mli = self.showPanelControl.getSelectedItem()
            if not mli:
                return

        li = self.keyItems.get(mli.getProperty('key'))
        if not li or not li.pos():
            return
        self.keyListControl.selectItem(li.pos())

    def searchButtonClicked(self):
        # a pinned item-type view searches the library it belongs to
        self.processCommand(search.dialog(self, section_id=realSection(self.section).key))

    def browseGenres(self):
        from . import genres as genres_window
        self.processCommand(opener.handleOpen(genres_window.GenreBrowserWindow,
                                              section=realSection(self.section)))

    def keyClicked(self):
        li = self.keyListControl.getSelectedItem()
        if not li:
            return

        mli = self.firstOfKeyItems.get(li.dataSource)
        if not mli:
            return
        pos = mli.pos()

        # This code is a little goofy but what it's trying to do is move the selected item from the
        # jumplist up to the top of the panel and then it requests the chunk for the current position
        # and the chunk for the current position + CHUNK_OVERCOMMIT.  The reason we need to potentially
        # request a different chunk is if the items on the panel are in two different chunks this code
        # will request both chunks so that we don't have blank items.  The requestChunk will only request
        # chunks that haven't already been fetched so if the current position and current position
        # plus the CHUNK_OVERCOMMIT are in the same chunk then the second requestChunk call doesn't
        # do anything.
        chunkOC = getattr(self._current, "CHUNK_OVERCOMMIT", self.CHUNK_OVERCOMMIT)
        self.showPanelControl.selectItem(pos+chunkOC)
        self.showPanelControl.selectItem(pos)
        self.requestChunk(pos)
        self.requestChunk(pos+chunkOC)

        self.setFocusId(self.POSTERS_PANEL_ID)
        util.setGlobalProperty('key', li.dataSource)

    def playButtonClicked(self, shuffle=False):
        if self.playBtnClicked:
            return

        self.subOptionCache = {}

        self.playBtnClicked = True
        filter_ = self.getFilterOpts()
        sort = self.getSortOpts()
        args = {}
        if filter_:
            args[filter_[0]] = filter_[1]

        if sort:
            args['sort'] = '{0}:{1}'.format(*sort)

        if self.section.TYPE == 'movie':
            args['sourceType'] = '1'
        elif self.section.TYPE == 'show':
            args['sourceType'] = '2'
        elif self.section.TYPE != 'collection':
            args['sourceType'] = '8'

        # When the list is filtered by unwatched, play and shuffle button should only play unwatched videos
        if self.boolFilters.get('unwatched'):
            args['unwatched'] = '1'

        pq = playqueue.createPlayQueueForItem(self.section, options={'shuffle': shuffle}, args=args)
        opener.open(pq, auto_play=True, auto_play_open=True)

    def shuffleButtonClicked(self):
        # TV and movie libraries open the Shuffle Mode menu; other section types
        # keep the classic server-side random shuffle.
        if self.section.TYPE == 'show':
            self.shuffleModeSelected()
        elif self.section.TYPE == 'movie':
            self.movieShuffleSelected()
        else:
            self.playButtonClicked(shuffle=True)

    def movieShuffleSelected(self):
        options = [
            {'key': shuffle.MODE_UNWATCHED, 'display': T(35010, "Unwatched")},
            {'key': shuffle.MODE_REWATCH, 'display': T(35011, "Rewatch")},
            {'key': 'classic', 'display': T(35018, "Shuffle All")},
        ]
        choice = dropdown.showDropdown(
            options,
            pos=(660, 441),
            close_direction='none',
            set_dropdown_prop=False,
            header=T(35009, "Shuffle Mode"),
            select_index=0,
            align_items="left",
        )
        if not choice:
            return
        if choice['key'] == 'classic':
            self.playButtonClicked(shuffle=True)
            return
        self.startMovieShuffle(choice['key'])

    def startMovieShuffle(self, mode):
        with busy.BusyContext(delay=True, delay_time=0.2):
            movies = self.section.all(type_=1)
            pool = shuffle.eligible_movies(movies, mode)
            if not pool:
                util.messageDialog(T(35009, "Shuffle Mode"),
                                   T(35013, "No matching items are available for this shuffle mode."))
                return
            ordered = shuffle.pick(pool, len(pool))

        pl = playlist.LocalPlaylist(ordered, self.section.getServer())
        self.processCommand(videoplayer.play(play_queue=pl))

    def shuffleModeSelected(self):
        options = [
            {'key': shuffle.MODE_UNWATCHED, 'display': T(35010, "Unwatched")},
            {'key': shuffle.MODE_REWATCH, 'display': T(35011, "Rewatch")},
            {'key': shuffle.MODE_CATCHUP, 'display': T(35012, "Catchup")},
            {'key': 'classic', 'display': T(35018, "Shuffle All")},
        ]
        choice = dropdown.showDropdown(
            options,
            pos=(660, 441),
            close_direction='none',
            set_dropdown_prop=False,
            header=T(35009, "Shuffle Mode"),
            select_index=0,
            align_items="left",
        )
        if not choice:
            return
        if choice['key'] == 'classic':
            self.playButtonClicked(shuffle=True)
            return
        self.startShuffleMode(choice['key'])

    def startShuffleMode(self, mode):
        section = self.section
        threshold = util.getSetting('shuffle_catchup_episode_threshold', 3)
        series_count = util.getSetting('shuffle_catchup_series_count', 5)
        specials_mode = util.getSetting('tv_specials_order', 'default')

        items = []
        with busy.BusyContext(delay=True, delay_time=0.2):
            shows = section.all(type_=2)
            pool = shuffle.eligible_shows(shows, mode, threshold=threshold)
            if not pool:
                util.messageDialog(T(35009, "Shuffle Mode"),
                                   T(35013, "No shows are available for this shuffle mode."))
                return

            pick_count = series_count if mode == shuffle.MODE_CATCHUP else 1
            start_index = 0
            for show in shuffle.pick(pool, pick_count):
                episodes = show.all()
                if mode == shuffle.MODE_CATCHUP:
                    # Eligibility counts PMS viewedLeafCount (fully-watched leaves only),
                    # so in-progress episodes are dropped here and a show may contribute
                    # fewer episodes than its unwatched count implied. The empty-queue
                    # guard below handles the case where nothing is left to play.
                    episodes = shuffle.unwatched_episodes(episodes)
                episodes = playlist.reorder_with_specials(episodes, mode=specials_mode)
                for ep in episodes:
                    # let the player reach show metadata, mirroring episodes.py
                    ep._show = show
                if not items:
                    # first show that actually contributes: start on its own first real
                    # episode (skip a leading special), not somewhere later in the queue
                    start_index = shuffle.first_regular_index(episodes)
                items.extend(episodes)

        if not items:
            util.messageDialog(T(35009, "Shuffle Mode"),
                               T(35013, "No shows are available for this shuffle mode."))
            return

        pl = playlist.LocalPlaylist(items, section.getServer())
        pl.setCurrent(items[start_index])
        self.processCommand(videoplayer.play(play_queue=pl))

    def optionsButtonClicked(self):
        options = []
        if xbmc.getCondVisibility('Player.HasAudio + MusicPlayer.HasNext'):
            options.append({'key': 'play_next', 'display': T(32325, 'Play Next')})

        if self.section.TYPE == 'photodirectory':
            if options:
                options.append(dropdown.SEPARATOR)
            options.append({'key': 'to_section', 'display': T(32324, u'Go to {0}').format(self.section.getLibrarySectionTitle())})

        choice = dropdown.showDropdown(options, (255, 205))
        if not choice:
            return

        if choice['key'] == 'play_next':
            xbmc.executebuiltin('PlayerControl(Next)')
        elif choice['key'] == 'to_section':
            self.goHome(self.section.getLibrarySectionId())

    def itemTypeButtonClicked(self):
        options = []

        if self.section.TYPE == 'show':
            for t in ('show', 'episode', 'collection'):
                options.append({'type': t, 'display': TYPE_PLURAL.get(t, t)})
            options.append({'type': 'browse_genres', 'display': T(34102, 'Categories')})
        elif self.section.TYPE == 'movie':
            for t in ('movie', 'collection'):
                options.append({'type': t, 'display': TYPE_PLURAL.get(t, t)})
            options.append({'type': 'browse_genres', 'display': T(34102, 'Categories')})
            options.append({'type': 'folder', 'display': TYPE_PLURAL.get('folder', 'folder')})
        elif self.section.TYPE == 'artist':
            for t in ('artist', 'album', 'collection', 'track'):
                options.append({'type': t, 'display': TYPE_PLURAL.get(t, t)})
        elif self.section.TYPE == 'movies_shows':
            for t in ('movies_shows', 'movie', 'show'):
                options.append({'type': t, 'display': TYPE_PLURAL.get(t, t)})
        else:
            return

        selectItem = None
        curType = self.librarySettings.getItemType()
        try:
            selectItem = list(filter(lambda o: o["type"] == curType, options))[0]
        except:
            pass

        result = dropdown.showDropdown(options, (1280, 106), with_indicator=True,
                                       select_item=not self.getBoolProperty('no.content.filtered') and selectItem or None)
        if not result:
            return

        choice = result['type']

        if choice == 'browse_genres':
            self.browseGenres()
            return

        if choice == ITEM_TYPE:
            return

        with self.lock:
            if self.tasks and any(list(filter(lambda x: not x.finished, self.tasks))):
                util.DEBUG_LOG("Waiting for tasks to finish")
                with busy.BusyContext(delay=True, delay_time=0.2):
                    while self.tasks and not util.MONITOR.abortRequested():
                        task = self.tasks.pop()
                        if task.isValid():
                            task.cancel()
                            ct = 0
                            while not task.finished and not util.MONITOR.abortRequested() and ct < 40:
                                xbmc.sleep(100)
                                ct += 1
                        del task

            try:
                self.showPanelControl.reset()
            except:
                util.DEBUG_LOG("Couldn't reset showPanelControl on view change")
            self.showPanelControl = None  # TODO: Need to do some check here I think

        self.librarySettings.setItemType(choice)

        # LibrarySettings keys sort and filters by item type, so reset() below restores
        # whatever this type was left in. Only the outgoing type's in-memory filter has to
        # go, otherwise reset() would carry it over ("self.filter or <stored>").
        self.filter = None
        self.reset()
        self.updateFilterDisplay()
        util.setGlobalProperty('sort', self.sort)

        if not self.nextWindow(False):
            self.setProperty('media.type', TYPE_PLURAL.get(ITEM_TYPE or self.section.TYPE, self.section.TYPE))
            try:
                self.setProperty('sort.display', SORT_KEYS[self.section.TYPE].get(self.sort, SORT_KEYS['movie'].get(self.sort))['title'])
            except TypeError:
                # stored sort isn't valid for this item type
                self.resetSort()
            self.fill()

    def sortButtonClicked(self):
        desc = 'script.plex/indicators/arrow-down.png'
        asc = 'script.plex/indicators/arrow-up.png'
        ind = self.sortDesc and desc or asc

        options = []
        defSortByOption = {}

        if self.section.TYPE == 'movie':
            searchTypes = ['titleSort', 'year', 'originallyAvailableAt', 'rating', 'audienceRating', 'userRating',
                           'contentRating', 'duration', 'viewOffset', 'viewCount', 'addedAt', 'lastViewedAt',
                           'resolution', 'mediaBitrate', 'random']
            if ITEM_TYPE == 'collection':
                searchTypes = ['titleSort', 'addedAt', 'contentRating']

            for stype in searchTypes:
                option = SORT_KEYS['movie'].get(stype).copy()
                option['type'] = stype
                option['indicator'] = self.sort == stype and ind or ''
                defSortByOption[stype] = option.get('defSortDesc')
                options.append(option)
        elif self.section.TYPE == 'show':
            searchTypes = ['titleSort', 'year', 'originallyAvailableAt', 'rating', 'audienceRating', 'userRating',
                           'contentRating', 'unviewedLeafCount', 'episode.addedAt',
                           'addedAt', 'lastViewedAt', 'random']
            if ITEM_TYPE == 'episode':
                searchTypes = ['titleSort', 'show.titleSort', 'addedAt', 'originallyAvailableAt', 'lastViewedAt',
                               'rating', 'audienceRating', 'userRating', 'mediaBitrate', 'random']
            elif ITEM_TYPE == 'collection':
                searchTypes = ['titleSort', 'addedAt']

            for stype in searchTypes:
                option = SORT_KEYS['show'].get(stype, SORT_KEYS['movie'].get(stype, {})).copy()
                if not option:
                    continue
                option['type'] = stype
                option['indicator'] = self.sort == stype and ind or ''
                defSortByOption[stype] = option.get('defSortDesc')
                options.append(option)
        elif self.section.TYPE == 'artist':
            searchTypes = ['titleSort', 'userRating', 'addedAt', 'lastViewedAt', 'viewCount', 'random']
            if ITEM_TYPE == 'album':
                searchTypes = ['titleSort', 'artist.titleSort', 'addedAt', 'lastViewedAt', 'viewCount',
                               'originallyAvailableAt', 'rating', 'random']
            elif ITEM_TYPE == 'collection':
                searchTypes = ['titleSort', 'addedAt']
            elif ITEM_TYPE == 'track':
                searchTypes = ['titleSort', 'addedAt', 'lastViewedAt', 'viewCount']

            for stype in searchTypes:
                option = SORT_KEYS['artist'].get(stype, SORT_KEYS['movie'].get(stype)).copy()
                option['type'] = stype
                option['indicator'] = self.sort == stype and ind or ''
                defSortByOption[stype] = option.get('defSortDesc')
                options.append(option)
        elif self.section.TYPE == 'photo':
            searchTypes = ['addedAt', 'originallyAvailableAt', 'photos.titleSort', 'mediaCount']
            for stype in searchTypes:
                option = SORT_KEYS['photo'].get(stype, SORT_KEYS['movie'].get(stype)).copy()
                option['type'] = stype
                option['indicator'] = self.sort == stype and ind or ''
                defSortByOption[stype] = option.get('defSortDesc')
                options.append(option)
        elif self.section.TYPE == 'movies_shows':
            searchTypes = self.section.ALLOWED_SORT
            for stype in searchTypes:
                option = SORT_KEYS['movies_shows'].get(stype, SORT_KEYS['movie'].get(stype)).copy()
                option['type'] = stype
                option['indicator'] = self.sort == stype and ind or ''
                defSortByOption[stype] = option.get('defSortDesc')
                options.append(option)
        else:
            return

        selectItem = None
        try:
            selectItem = list(filter(lambda o: o["type"] == self.sort, options))[0]
        except:
            pass

        result = dropdown.showDropdown(options, (1280, 106), with_indicator=True,
                                       select_item=not self.getBoolProperty('no.content.filtered') and selectItem or None)
        if not result:
            return

        choice = result['type']

        if choice == self.sort:
            self.sortDesc = not self.sortDesc
        else:
            self.sortDesc = defSortByOption.get(choice, False)

        if choice == "random":
            self.section.clearCache()
        self.sort = choice

        self.librarySettings.setSetting('sort', self.sort)
        self.librarySettings.setSetting('sort.desc', self.sortDesc)

        util.setGlobalProperty('sort', choice)
        self.setProperty('sort.display', result['title'])

        self.sortShowPanel(choice, True)

    def viewTypeButtonClicked(self):
        for task in self.tasks:
            if task.isValid():
                task.cancel()
                self.refill = True

        with self.lock:
            self.showPanelControl.invalidate()
            win = self.nextWindow()

        key = self.section.key
        if not key.isdigit():
            key = self.section.getLibrarySectionId()
        util.setSetting('viewtype.{0}.{1}'.format(self.section.server.uuid, key), win.VIEWTYPE)

    def sortShowPanel(self, choice, force_refresh=False):
        if force_refresh or self.showPanelControl.size() == 0:
            self.fillShows()
            return

        # inline sorting is disabled; this code will never be reached

        if choice == 'addedAt':
            self.showPanelControl.sort(lambda i: i.dataSource.addedAt, reverse=self.sortDesc)
        elif choice == 'originallyAvailableAt':
            self.showPanelControl.sort(lambda i: i.dataSource.get('originallyAvailableAt'), reverse=self.sortDesc)
        elif choice == 'lastViewedAt':
            self.showPanelControl.sort(lambda i: i.dataSource.get('lastViewedAt'), reverse=self.sortDesc)
        elif choice == 'viewCount':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title)
            self.showPanelControl.sort(lambda i: i.dataSource.get('viewCount').asInt(), reverse=self.sortDesc)
        elif choice == 'titleSort':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title, reverse=self.sortDesc)
            self.keyListControl.sort(lambda i: i.getProperty('original'), reverse=self.sortDesc)
        elif choice == 'show.titleSort':
            self.showPanelControl.sort(lambda i: i.label, reverse=self.sortDesc)
            self.keyListControl.sort(lambda i: i.getProperty('original'), reverse=self.sortDesc)
        elif choice == 'artist.titleSort':
            self.showPanelControl.sort(lambda i: i.label, reverse=self.sortDesc)
            self.keyListControl.sort(lambda i: i.getProperty('original'), reverse=self.sortDesc)
        elif choice == 'rating':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title)
            self.showPanelControl.sort(lambda i: i.dataSource.get('rating').asFloat(), reverse=self.sortDesc)
        elif choice == 'audienceRating':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title)
            self.showPanelControl.sort(lambda i: i.dataSource.get('audienceRating').asFloat(), reverse=self.sortDesc)
        elif choice == 'userRating':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title)
            self.showPanelControl.sort(lambda i: i.dataSource.get('userRating').asFloat(), reverse=self.sortDesc)
        elif choice == 'contentRating':
            self.showPanelControl.sort(lambda i: i.dataSource.get('titleSort') or i.dataSource.title)
            self.showPanelControl.sort(lambda i: i.dataSource.get('contentRating'), reverse=self.sortDesc)
        elif choice == 'resolution':
            self.showPanelControl.sort(lambda i: i.dataSource.maxHeight, reverse=self.sortDesc)
        elif choice == 'duration':
            self.showPanelControl.sort(lambda i: i.dataSource.duration.asInt(), reverse=self.sortDesc)
        elif choice == 'unviewedLeafCount':
            self.showPanelControl.sort(lambda i: i.dataSource.unViewedLeafCount, reverse=self.sortDesc)

        self.showPanelControl.selectItem(0)
        self.setFocusId(self.POSTERS_PANEL_ID)
        self.backgroundSet = False
        self.setBackground([item.dataSource for item in self.showPanelControl], 0,
                           randomize=not util.addonSettings.dynamicBackgrounds)

    def subOptionCallback(self, option):
        check = 'script.plex/home/device/check.png'
        options = None
        subKey = None
        if self.filter and self.filter.get('sub'):
            subKey = self.filter['sub']['val']

        ftype = self._filterTypeByKey.get(option['type'])
        if ftype and ftype != 'boolean':
            # cache suboptions
            ck = (self.librarySettings.getItemType() or self.section.TYPE, option['type'])
            if ck in self.subOptionCache:
                options = self.subOptionCache[ck]
            else:
                options = [{'val': o.key, 'display': o.title, 'indicator': o.key == subKey and check or ''} for o in
                            self.section.listChoices(option['type'],
                                                     libtype=self.librarySettings.getItemType() or self.section.TYPE)]
                self.subOptionCache[ck] = options

            if not options:
                options = [{'val': None, 'display': T(32375, 'No filters available'), 'ignore': True}]

        return options

    def _filterLabel(self, fkey, server_title):
        # Hybrid labels: use pm4k's localized strings for filters we have ids for
        # (keeps wording/translations consistent), and fall back to the server's
        # own title for any filter we don't recognise (e.g. atmos, codec filters).
        known = FILTER_LABELS.get(fkey)
        if known:
            sid, fallback = known
            return T(sid, fallback) if sid else fallback
        return server_title or fkey

    def filter1ButtonClicked(self):
        check = 'script.plex/home/device/check.png'

        libtype = self.librarySettings.getItemType()
        try:
            filters = self.section.listFilters(libtype=libtype)
        except Exception:
            util.ERROR('filter1ButtonClicked: listFilters failed')
            filters = None

        self._filterTypeByKey = {}

        if not filters:
            util.DEBUG_LOG('No filters available for section {0}', self.section.key)
            dropdown.showDropdown(
                [{'val': None, 'display': T(32375, 'No filters available'), 'ignore': True}],
                (980, 106))
            return

        # Group boolean toggles (HDR/DOVI/Atmos/Unwatched/...) at the top, separated from
        # the value filters (genre/year/...). Server order is preserved within each group.
        boolOptions = []
        valueOptions = []

        for f in filters:
            fkey = f.filter
            ftype = f.filterType
            if not fkey:
                continue
            # Folder location filtering is admin-oriented; only surface it for admins.
            if fkey == 'location' and not pnUtil.ACCOUNT.isAdmin:
                continue

            self._filterTypeByKey[fkey] = ftype
            label = self._filterLabel(fkey, f.title)

            if ftype == 'boolean':
                # Caps signals these are combinable toggles, distinct from the
                # single-select (title-case) value categories.
                boolOptions.append({'type': fkey, 'display': label.upper(),
                                    'indicator': self.boolFilters.get(fkey) and check or '',
                                    'is_bool': True})
            else:
                active = self.filter and self.filter.get('type') == fkey
                valueOptions.append({'type': fkey, 'display': label, 'is_sub_list': True,
                                     'indicator': active and check or ''})

        options = []
        if self.filter or any(self.boolFilters.values()):
            options.append({'type': 'clear_filter', 'display': T(32376, 'CLEAR FILTER').upper(),
                            'indicator': 'script.plex/indicators/remove.png'})
            options.append(None)  # Separator

        options.extend(boolOptions)
        if boolOptions and valueOptions:
            options.append(None)  # Separator between toggles and value filters
        options.extend(valueOptions)

        result = dropdown.showDropdown(options, (980, 106), with_indicator=True,
                                       suboption_callback=self.subOptionCallback,
                                       select_item=not self.getBoolProperty('no.content.filtered') and self.filter or None,
                                       open_sublists=not self.getBoolProperty('no.content.filtered'))
        if not result:
            return

        choice = result['type']

        if choice == 'clear_filter':
            self.clearFilters(skip_display=True)
        elif result.get('is_bool') or self._filterTypeByKey.get(choice) == 'boolean':
            if self.boolFilters.get(choice):
                del self.boolFilters[choice]
            else:
                self.boolFilters[choice] = True
            self.librarySettings.setSetting('filter.bools', self.boolFilters)
        else:
            self.filter = result
            self.librarySettings.setSetting('filter', self.filter)

        self.updateFilterDisplay()

        if self.filter or choice == 'clear_filter' or result.get('is_bool') or self._filterTypeByKey.get(choice) == 'boolean':
            self.fill()

    def clearFilters(self, skip_display=False):
        self.filter = None
        self.boolFilters = {}
        self.librarySettings.setSetting('filter.bools', self.boolFilters)
        self.librarySettings.setSetting('filter', None)
        if not skip_display:
            self.updateFilterDisplay()

    def resetSort(self):
        self.sort = 'titleSort'
        self.sortDesc = False

        self.librarySettings.setSetting('sort', self.sort)
        self.librarySettings.setSetting('sort.desc', self.sortDesc)

        util.setGlobalProperty('sort', self.sort)
        self.setProperty('sort.display', SORT_KEYS[self.section.TYPE].get(self.sort, SORT_KEYS['movie'].get(self.sort))['title'])

    def updateFilterDisplay(self):
        boolLabels = [self._filterLabel(k, k) for k, on in self.boolFilters.items() if on]
        if self.filter:
            disp = self.filter['display']
            if self.filter.get('sub'):
                disp = u'{0}: {1}'.format(disp, self.filter['sub']['display'])
            self.setProperty('filter1.display', disp)
            self.setProperty('filter2.display', ", ".join(boolLabels))
        else:
            self.setProperty('filter2.display', '')
            if not boolLabels:
                boolLabels = [T(32345, 'All')]
            self.setProperty('filter1.display', ", ".join(boolLabels))

    def showPanelClicked(self):
        mli = self.showPanelControl.getSelectedItem()
        if not mli or not mli.dataSource:
            return

        sectionType = self.section.TYPE

        updateUnwatchedAndProgress = False
        # Remember the panel generation before we open any (modal) child window. If the
        # panel gets rebuilt while we're away (e.g. a watchlist item auto-removed on full
        # watch triggers doRefill via onReInit), `mli` below is backed by a freed ListItem
        # and must not be touched - doing so hard-crashes Kodi (SIGSEGV in
        # CGUIListItem::SetProperty).
        listGeneration = self._listGeneration

        self.subOptionCache = {}

        extra_kwargs = {}

        # watchlist
        if sectionType == 'movies_shows':
            extra_kwargs['from_watchlist'] = True
            extra_kwargs['directly_from_watchlist'] = True
            extra_kwargs['external_item'] = True

        if mli.dataSource.TYPE == 'collection':
            prevItemType = self.librarySettings.getItemType() or ITEM_TYPE
            self.processCommand(opener.open(mli.dataSource))
            self.librarySettings.setItemType(prevItemType)
        elif self.section.TYPE == 'show' or mli.dataSource.TYPE == 'show' or mli.dataSource.TYPE == 'season' or mli.dataSource.TYPE == 'episode':
            if ITEM_TYPE == 'episode' or mli.dataSource.TYPE == 'episode' or mli.dataSource.TYPE == 'season':
                self.openItem(mli.dataSource)
            else:
                self.processCommand(opener.handleOpen(subitems.ShowWindow, media_item=mli.dataSource, parent_list=self.showPanelControl, **extra_kwargs))
            if mli.dataSource.TYPE != 'season': # NOTE: A collection with Seasons doesn't have the leafCount/viewedLeafCount until you actually go into the season so we can't update the unwatched count here
                updateUnwatchedAndProgress = True
        elif self.section.TYPE == 'movie' or mli.dataSource.TYPE == 'movie':
            datasource = mli.dataSource
            if datasource.isDirectory():
                cls = self.section.__class__
                section = cls(self.section.data, self.section.initpath, self.section.server, self.section.container)
                sectionId = section.key
                if not sectionId.isdigit():
                    sectionId = section.getLibrarySectionId()

                section.set('librarySectionID', sectionId)
                section.key = datasource.key
                section.title = datasource.title

                self.processCommand(opener.handleOpen(LibraryWindow, windows=self._windows, default_window=self._next, section=section, filter_=self.filter, subDir=True))
                self.librarySettings.setItemType(self.librarySettings.getItemType() or ITEM_TYPE)
            else:
                self.processCommand(opener.handleOpen(preplay.PrePlayWindow if not sectionType == 'movies_shows' else preplay.PrePlayWindowWL, video=datasource, parent_list=self.showPanelControl, **extra_kwargs))
                updateUnwatchedAndProgress = True
        elif self.section.TYPE == 'artist' or mli.dataSource.TYPE == 'artist' or mli.dataSource.TYPE == 'album' or mli.dataSource.TYPE == 'track':
            if ITEM_TYPE == 'album' or mli.dataSource.TYPE == 'album' or mli.dataSource.TYPE == 'track':
                self.openItem(mli.dataSource)
            else:
                self.processCommand(opener.handleOpen(subitems.ArtistWindow, media_item=mli.dataSource, parent_list=self.showPanelControl))
        elif self.section.TYPE in ('photo', 'photodirectory'):
            self.showPhoto(mli.dataSource)

        if self._closeSignalled:
            return

        if not mli:
            return

        if self._listGeneration != listGeneration:
            # Panel was rebuilt while the child window was open; `mli` is stale. The fresh
            # panel already reflects current watched/progress state, so nothing to do.
            return

        if mli.dataSource and not mli.dataSource.exists():
            self.showPanelControl.removeItem(mli.pos())
            return

        if updateUnwatchedAndProgress:
            self.updateUnwatchedAndProgress(mli)

    def showPhoto(self, photo):
        self.subOptionCache = {}
        if isinstance(photo, plexnet.photo.Photo) or photo.TYPE == 'clip':
            self.processCommand(opener.open(photo))
        else:
            self.processCommand(opener.sectionClicked(photo))

    def updateUnwatchedAndProgress(self, mli):
        mli.dataSource.reload()
        if mli.dataSource.isWatched:
            mli.setProperty('unwatched', '')
            mli.setProperty('unwatched.count', '')
        else:
            if self.section.TYPE == 'show' or mli.dataSource.TYPE == 'show' or mli.dataSource.TYPE == 'season':
                mli.setProperty('unwatched.count', str(mli.dataSource.unViewedLeafCount))
                mli.setBoolProperty('unwatched.count.large', mli.dataSource.unViewedLeafCount > 999)
            else:
                mli.setProperty('unwatched', '1')
        mli.setBoolProperty('watched', mli.dataSource.isFullyWatched)
        mli.setProperty('progress', util.getProgressImage(mli.dataSource))

    def setTitle(self):
        self.setProperty('screen.title', self.section.title.upper())

        self.updateFilterDisplay()

    def updateItem(self, mli=None):
        mli = mli or self.showPanelControl.getSelectedItem()
        if not mli or mli.dataSource:
            return

        for task in self.tasks:
            if task.contains(mli.pos()):
                util.DEBUG_LOG('Moving task to front: {0}', task)
                backgroundthread.BGThreader.moveToFront(task)
                break

    def setBackground(self, items, position, randomize=True):
        if self.backgroundSet:
            return

        if randomize:
            item = random.choice(items)
            self.updateBackgroundFrom(item)
        else:
            # we want the first item of the first chunk
            if position != 0:
                return

            self.updateBackgroundFrom(items[0])
        self.backgroundSet = True

    def fill(self):
        self.backgroundSet = False

        if self.section.TYPE in ('photo', 'photodirectory'):
            return self.fillPhotos()
        else:
            return self.fillShows()

    def getFilterOpts(self):
        if not self.filter:
            return None

        if not self.filter.get('sub'):
            #util.DEBUG_LOG('Filter missing sub-filter data')
            return self.filter['type'], "1"

        if isinstance(self.filter['sub']['val'], six.string_types) and self.filter['sub']['val'].startswith("/"):
            return self.filter['type'], self.filter['sub']['val']
        return self.filter['type'], six.moves.urllib.parse.unquote_plus(self.filter['sub']['val'])

    def getSortOpts(self):
        if not self.sort:
            return None

        return (self.sort, self.sortDesc and 'desc' or 'asc')


    def getDefChunkSize(self, size):
        return self.DEFAULT_ITEMS_CHUNK_SIZE if size < 1000 else self.DEFAULT_ITEMS_CHUNK_SIZE_BIG

    @property
    def thumb_fallback(self):
        return 'script.plex/thumb_fallbacks/{0}.png'.format(TYPE_KEYS.get(self.section.type, TYPE_KEYS['movie'])['fallback'])

    def fillShows(self):
        try:
            return self._fillShows()
        except plexnet.exceptions.RateLimited as error:
            self.setBoolProperty('content.filling', False)
            self.refill = True
            if not error.from_cooldown:
                util.messageDialog(T(34000, 'Watchlist'),
                                   T(35050, 'Plex is temporarily limiting Watchlist requests. Try again in {} seconds.').format(error.retry_after))
            return False

    @busy.dialog()
    def _fillShows(self):
        self.setBoolProperty('no.content', False)
        self.setBoolProperty('no.content.filtered', False)
        self.setBoolProperty('content.filling', True)
        items = []
        jitems = []
        self.keyItems = {}
        self.firstOfKeyItems = {}
        totalSize = 0
        self.alreadyFetchedChunkList = set()
        self.finalChunkPosition = 0

        type_ = getQueryItemType(self.section)
        # supplying this type kills all results (bug: 2025/10/21)
        if type_ == plexobjects.SEARCHTYPES["photo"]:
            type_ = None

        tasks = []

        # boolean filters (hdr/dovi/unwatched/inProgress/...) flow through as a dict
        bool_filters = self.boolFilters

        if self.sort != 'titleSort' or ITEM_TYPE in ('folder', 'episode') or self.subDir \
            or self.section.TYPE in ("collection", "movies_shows"):
            if ITEM_TYPE == 'folder':
                sectionAll = self.section.folder(0, 0, self.subDir)
            else:
                sectionAll = self.section.all(0, 0, filter_=self.getFilterOpts(), sort=self.getSortOpts(),
                                              type_=type_, bool_filters=bool_filters)

            totalSize = sectionAll.totalSize.asInt()

            if not totalSize:
                self.showPanelControl.reset()
                self.keyListControl.reset()

                if (self.filter or any(self.boolFilters.values())
                        or self.librarySettings.getItemType()):
                    self.setBoolProperty('no.content.filtered', True)
                else:
                    self.setBoolProperty('no.content', True)

                return
            else:
                for startPosition in range(0, totalSize, self.getDefChunkSize(totalSize)):
                    tasks.append(CreateDefaultItemsTask().setup(startPosition, self.getDefChunkSize(totalSize), totalSize, self.thumb_fallback, self._defaultItemsCallback))
        else:
            # find library collection mode setting, as we need to force-feed the collection type to the jumpList,
            # if collection_mode is 2, otherwise the returned item count differs from /all with the same parameters
            collection_mode = self.section.settings.get("collectionMode",
                                                       {"value": plexobjects.PlexValue(2)})["value"].asInt()

            jl_type = type_
            if collection_mode == 2 and not (self.filter or self.boolFilters.get('unwatched')):
                jl_type = getQueryItemType(self.section, fallback_to_section_type=True, force_include_collections=True)

            jumpList = self.section.jumpList(filter_=self.getFilterOpts(), sort=self.getSortOpts(),
                                             type_=jl_type, bool_filters=bool_filters)

            if not jumpList:
                self.showPanelControl.reset()
                self.keyListControl.reset()

                if (self.filter or any(self.boolFilters.values())
                        or self.librarySettings.getItemType()):
                    self.setBoolProperty('no.content.filtered', True)
                else:
                    self.setBoolProperty('no.content', True)

                if jumpList is None:
                    util.messageDialog("Error", "There was an error.")

                return

            idx = 0
            for kidx, ji in enumerate(jumpList):
                ji_size = ji.size.asInt()
                mli = kodigui.ManagedListItem(ji.title, data_source=ji.key)
                mli.setProperty('key', ji.key)
                mli.setProperty('index', str(kidx))
                mli.setProperty('original', '{0:02d}'.format(kidx))
                self.keyItems[ji.key] = mli
                jitems.append(mli)
                totalSize += ji_size

                tasks.append(CreateDefaultItemsTask().setup(idx, ji.size.asInt(), totalSize, self.thumb_fallback, self._defaultItemsCallback, key=ji.key))
                idx += ji_size

            util.DEBUG_LOG('JumpList item size: {}', totalSize)

            util.setGlobalProperty('key', jumpList[0].key)

        self.setProperty("items.count", str(totalSize))

        self.showPanelControl.reset()
        self.keyListControl.reset()

        # Start the background tasks to create the default items
        self.tasks.add(tasks)
        backgroundthread.BGThreader.addTasksToFront(tasks)

        # Wait for the default items to be created
        while backgroundthread.BGThreader.working() and not util.MONITOR.abortRequested():
            util.MONITOR.waitFor()

        if jitems:
            self.keyListControl.addItems(jitems)

        self.showPanelControl.selectItem(0)
        self.setFocusId(self.POSTERS_PANEL_ID)

        tasks = []
        for startChunkPosition in range(0, totalSize, self.CHUNK_SIZE):
            tasks.append(
                ChunkRequestTask().setup(
                    self.section, startChunkPosition, self.CHUNK_SIZE, self._chunkCallback, filter_=self.getFilterOpts(),
                    sort=self.getSortOpts(), subDir=self.subDir, bool_filters=bool_filters
                )
            )

            # If we're retrieving media as we navigate then we just want to request the first
            # chunk of media and stop.  We'll fetch the rest as the user navigates to those items
            if not util.addonSettings.retrieveAllMediaUpFront:
                # Calculate the end chunk's starting position based on the totalSize of items
                self.finalChunkPosition = (totalSize // self.CHUNK_SIZE) * self.CHUNK_SIZE
                # Keep track of the chunks we've already fetched by storing the chunk's starting position
                self.alreadyFetchedChunkList.add(startChunkPosition)
                break

        self.tasks.add(tasks)
        backgroundthread.BGThreader.addTasksToFront(tasks)

    def showPhotoItemProperties(self, photo):
        if photo.isFullObject():
            return

        task = PhotoPropertiesTask().setup(photo, self._showPhotoItemProperties)
        self.tasks.add(task)
        backgroundthread.BGThreader.addTasksToFront([task])

    def _showPhotoItemProperties(self, photo):
        mli = self.showPanelControl.getSelectedItem()
        if not mli or not mli.dataSource.TYPE == 'photo':
            for mli in self.showPanelControl:
                if mli.dataSource == photo:
                    break
            else:
                return

        mli.setProperty('camera.model', photo.media[0].model)
        mli.setProperty('camera.lens', photo.media[0].lens)

        attrib = []
        if photo.media[0].height:
            attrib.append(u'{0} x {1}'.format(photo.media[0].width, photo.media[0].height))

        orientation = photo.media[0].parts[0].orientation
        if orientation:
            attrib.append(u'{0} Mo'.format(orientation))

        container = photo.media[0].container_ or os.path.splitext(photo.media[0].parts[0].file)[-1][1:].lower()
        if container == 'jpg':
            container = 'jpeg'
        attrib.append(container.upper())
        if attrib:
            mli.setProperty('photo.dims', u' \u2022 '.join(attrib))

        settings = []
        if photo.media[0].iso:
            settings.append('ISO {0}'.format(photo.media[0].iso))
        if photo.media[0].aperture:
            settings.append('{0}'.format(photo.media[0].aperture))
        if photo.media[0].exposure:
            settings.append('{0}'.format(photo.media[0].exposure))
        mli.setProperty('camera.settings', u' \u2022 '.join(settings))
        mli.setProperty('photo.summary', photo.get('summary'))

    @busy.dialog()
    def fillPhotos(self):
        self.setBoolProperty('no.content', False)
        self.setBoolProperty('no.content.filtered', False)
        items = []
        keys = []
        self.firstOfKeyItems = {}
        idx = 0

        if self.section.TYPE == 'photodirectory':
            photos = self.section.all()
        else:
            photos = self.section.all(filter_=self.getFilterOpts(), sort=self.getSortOpts(), bool_filters=self.boolFilters)

        if not photos:
            return

        photo = random.choice(photos)
        self.updateBackgroundFrom(photo)
        thumbDim = TYPE_KEYS.get(self.section.type, TYPE_KEYS['movie'])['thumb_dim']
        fallback = 'script.plex/thumb_fallbacks/{0}.png'.format(TYPE_KEYS.get(self.section.type, TYPE_KEYS['movie'])['fallback'])

        if not photos:
            if self.filter or any(self.boolFilters.values()):
                self.setBoolProperty('no.content.filtered', True)
            else:
                self.setBoolProperty('no.content', True)
            return

        self.setProperty("items.count", photos.totalSize)

        for photo in photos:
            title = photo.title
            if photo.TYPE == 'photodirectory':
                thumb = photo.composite.asTranscodedImageURL(*thumbDim)
                mli = kodigui.ManagedListItem(title, thumbnailImage=thumb, data_source=photo)
                mli.setProperty('is.folder', '1')
            else:
                thumb = photo.defaultThumb.asTranscodedImageURL(*thumbDim)
                label2 = util.cleanLeadingZeros(photo.originallyAvailableAt.asDatetime('%d %B %Y'))
                mli = kodigui.ManagedListItem(title, label2, thumbnailImage=thumb, data_source=photo)

            mli.setProperty('thumb.fallback', fallback)
            mli.setProperty('index', str(idx))

            key = title[0].upper()
            if key not in KEYS:
                key = '#'
            if key not in keys:
                self.firstOfKeyItems[key] = mli
                keys.append(key)
            mli.setProperty('key', str(key))
            items.append(mli)
            idx += 1

        litems = []
        self.keyItems = {}
        for i, key in enumerate(keys):
            mli = kodigui.ManagedListItem(key, data_source=key)
            mli.setProperty('key', key)
            mli.setProperty('original', '{0:02d}'.format(i))
            self.keyItems[key] = mli
            litems.append(mli)

        self.showPanelControl.reset()
        self.keyListControl.reset()

        self.showPanelControl.addItems(items)
        self.keyListControl.addItems(litems)

        if keys:
            util.setGlobalProperty('key', keys[0])

    def _defaultItemsCallback(self, items, key, firstMli):
        if not items:
            return

        while True:
            self.lock.acquire()
            # When creating the default items for the title sort we need to add them to the list
            # in order.  So we look at the first index of the incoming items to see if it's the
            # next batch of items to add.  If not then it releases the lock and adds a small delay
            # so that other threads can grab the lock.
            if key and firstMli:
                if int(firstMli.getProperty('index')) != self.showPanelControl.size():
                    self.lock.release()
                    xbmc.sleep(1)
                    continue

                self.firstOfKeyItems[key] = firstMli

            self.showPanelControl.addItems(items)
            self.lock.release()
            break

    def _chunkCallback(self, items, start):
        if not self.showPanelControl or not items or self.closing:
            return

        with self.lock:
            pos = start
            self.setBackground(items, pos, randomize=not util.addonSettings.dynamicBackgrounds)

            thumbDim = TYPE_KEYS.get(self.section.type, TYPE_KEYS['movie'])['thumb_dim']
            artDim = TYPE_KEYS.get(self.section.type, TYPE_KEYS['movie']).get('art_dim', (256, 256))

            if not self.showPanelControl:
                return

            if ITEM_TYPE == 'episode':
                for offset, obj in enumerate(items):
                    mli = self.showPanelControl[pos]
                    if obj:
                        mli.dataSource = obj
                        mli.setProperty('index', str(pos))
                        if obj.index:
                            subtitle = u'{0} \u2022 {1}'.format(T(32310, 'S').format(obj.parentIndex),
                                                                T(32311, 'E').format(obj.index))
                            mli.setProperty('subtitle', subtitle)
                            subtitle = "\n" + subtitle
                        else:
                            subtitle = ' - ' + obj.originallyAvailableAt.asDatetime('%m/%d/%y')
                        mli.setLabel((obj.defaultTitle or ''))# + subtitle)

                        mli.setThumbnailImage(obj.defaultThumb.asTranscodedImageURL(*thumbDim))

                        mli.setProperty('summary', obj.summary)

                        #mli.setLabel2(util.durationToText(obj.fixedDuration()))
                        mli.setLabel2(subtitle)
                        mli.setProperty('art', obj.defaultArt.asTranscodedImageURL(*artDim))
                        if not obj.isWatched:
                            mli.setProperty('unwatched', '1')
                        mli.setBoolProperty('watched', obj.isFullyWatched)
                        mli.setProperty('initialized', '1')
                    else:
                        mli.clear()
                        if obj is False:
                            mli.setProperty('index', str(pos))
                        else:
                            mli.setProperty('index', '')

                    pos += 1

            elif ITEM_TYPE == 'album':
                for offset, obj in enumerate(items):
                    mli = self.showPanelControl[pos]
                    if obj:
                        mli.dataSource = obj
                        mli.setProperty('index', str(pos))
                        mli.setLabel(u'{0}\n{1}'.format(obj.parentTitle, obj.title))

                        mli.setThumbnailImage(obj.defaultThumb.asTranscodedImageURL(*thumbDim))

                        mli.setProperty('summary', obj.summary)

                        mli.setLabel2(obj.year)
                    else:
                        mli.clear()
                        if obj is False:
                            mli.setProperty('index', str(pos))
                        else:
                            mli.setProperty('index', '')

                    pos += 1
            else:
                for offset, obj in enumerate(items):

                    try:
                        mli = self.showPanelControl[pos]
                    except RuntimeError:
                        util.LOG("Library/ChunkCallback: {} not found", pos)
                        pos += 1
                        continue

                    if obj:
                        mli.setProperty('index', str(pos))

                        if obj.TYPE == 'track':
                            mli.setLabel("{} - {}: {}".format(obj.grandparentTitle, obj.parentTitle, obj.title))
                        else:
                            mli.setLabel(obj.defaultTitle or '')

                        if obj.TYPE == 'collection':
                            colArtDim = TYPE_KEYS.get('collection').get('art_dim', (256, 256))
                            mli.setProperty('art', obj.artCompositeURL(*colArtDim))
                            mli.setThumbnailImage(obj.server.getImageTranscodeURL(
                                obj.artCompositeURL(*tuple(2*dim for dim in thumbDim)), *thumbDim)
                            )
                        else:
                            if obj.TYPE == 'photodirectory' and obj.composite:
                                mli.setThumbnailImage(obj.composite.asTranscodedImageURL(*thumbDim))
                            else:
                                mli.setThumbnailImage(obj.defaultThumb.asTranscodedImageURL(*thumbDim))
                        mli.dataSource = obj
                        mli.setProperty('summary', obj.get('summary'))

                        # get secondary sort based info
                        sk_data = SORT_KEYS[self.section.TYPE].get(self.sort, {'subDisplay': None})
                        sub_display = sk_data.get('subDisplay', None)
                        sub_title = obj.get('year')
                        if sub_display:
                            if hasattr(obj, "meta_{}".format(sub_display)):
                                res = getattr(obj, "meta_{}".format(sub_display))('')
                                if res:
                                    exclusive = sk_data.get('subDisplayExclusive', False)
                                    sub_title = res
                                    if not exclusive:
                                        sub_title = "{} ({})".format(res, obj.get('year'))
                        mli.setProperty('year', sub_title)

                        if obj.TYPE != 'collection':
                            if not obj.isDirectory() and obj.get('duration').asInt():
                                mli.setLabel2(util.durationToText(obj.fixedDuration()))
                            mli.setProperty('art', obj.defaultArt.asTranscodedImageURL(*artDim))
                            if not obj.isWatched and obj.TYPE != "Directory":
                                if self.section.TYPE == 'show' or obj.TYPE == 'show' or obj.TYPE == 'season':
                                    mli.setProperty('unwatched.count', str(obj.unViewedLeafCount))
                                    mli.setBoolProperty('unwatched.count.large', obj.unViewedLeafCount > 999)
                                else:
                                    mli.setProperty('unwatched', '1')
                            elif obj.isFullyWatched and obj.TYPE != "Directory":
                                mli.setBoolProperty('watched', '1')
                            mli.setProperty('initialized', '1')

                        mli.setProperty('progress', util.getProgressImage(obj))
                    else:
                        mli.clear()
                        if obj is False:
                            mli.setProperty('index', str(pos))
                        else:
                            mli.setProperty('index', '')

                    pos += 1

        self.setBoolProperty('content.filling', False)

    def requestChunk(self, start):
        if util.addonSettings.retrieveAllMediaUpFront:
            return

        # Calculate the correct starting chunk position for the item they passed in
        startChunkPosition = (start // self.CHUNK_SIZE) * self.CHUNK_SIZE
        # If we calculated a chunk position that's beyond the end chunk then just return
        if startChunkPosition > self.finalChunkPosition:
            return

        # Check if the chunk has already been requested, if not then go fetch the data
        if startChunkPosition not in self.alreadyFetchedChunkList:
            util.DEBUG_LOG('Position {0} so requesting chunk {1}', start, startChunkPosition)
            # Keep track of the chunks we've already fetched by storing the chunk's starting position
            self.alreadyFetchedChunkList.add(startChunkPosition)
            task = ChunkRequestTask().setup(self.section, startChunkPosition, self.CHUNK_SIZE,
                                            self._chunkCallback, filter_=self.getFilterOpts(), sort=self.getSortOpts(),
                                            subDir=self.subDir, bool_filters=self.boolFilters)

            self.tasks.add(task)
            backgroundthread.BGThreader.addTasksToFront([task])


class PostersWindow(kodigui.ControlledWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-posters.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    POSTERS_PANEL_ID = 101
    KEY_LIST_ID = 151
    SCROLLBAR_ID = 152

    OPTIONS_GROUP_ID = 200

    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202
    PLAYER_STATUS_BUTTON_ID = 204

    SORT_BUTTON_ID = 210
    FILTER1_BUTTON_ID = 211
    FILTER2_BUTTON_ID = 212
    ITEM_TYPE_BUTTON_ID = 312

    PLAY_BUTTON_ID = 301
    SHUFFLE_BUTTON_ID = 302
    OPTIONS_BUTTON_ID = 303
    VIEWTYPE_BUTTON_ID = 304

    VIEWTYPE = 'panel'
    MULTI_WINDOW_ID = 0

    ROW_SIZE = 6
    CHUNK_OVERCOMMIT = 6


class PostersCompactWindow(PostersWindow):
    xmlFile = 'script-plex-posters-compact.xml'
    VIEWTYPE = 'panel3'
    MULTI_WINDOW_ID = 3
    ROW_SIZE = 10
    CHUNK_OVERCOMMIT = 30


class PostersSmallWindow(PostersWindow):
    xmlFile = 'script-plex-posters-small.xml'
    VIEWTYPE = 'panel2'
    MULTI_WINDOW_ID = 1
    ROW_SIZE = 10
    CHUNK_OVERCOMMIT = 30


class PostersSmallCompactWindow(PostersWindow):
    xmlFile = 'script-plex-posters-small-compact.xml'
    VIEWTYPE = 'panel4'
    MULTI_WINDOW_ID = 4
    ROW_SIZE = 10
    CHUNK_OVERCOMMIT = 30


class ListView16x9Window(PostersWindow):
    xmlFile = 'script-plex-listview-16x9.xml'
    VIEWTYPE = 'list'
    MULTI_WINDOW_ID = 2
    ROW_SIZE = 0
    CHUNK_OVERCOMMIT = 12


class SquaresWindow(PostersWindow):
    xmlFile = 'script-plex-squares.xml'
    VIEWTYPE = 'panel'
    MULTI_WINDOW_ID = 0


class ListViewSquareWindow(PostersWindow):
    xmlFile = 'script-plex-listview-square.xml'
    VIEWTYPE = 'list'
    ROW_SIZE = 0
    MULTI_WINDOW_ID = 1


VIEWS_POSTER = {
    'panel': PostersWindow,
    'panel2': PostersSmallWindow,
    'panel3': PostersCompactWindow,
    'panel4': PostersSmallCompactWindow,
    'list': ListView16x9Window,
    'all': (PostersWindow, PostersCompactWindow, PostersSmallWindow, PostersSmallCompactWindow, ListView16x9Window)
}

VIEWS_SQUARE = {
    'panel': SquaresWindow,
    'list': ListViewSquareWindow,
    'all': (SquaresWindow, ListViewSquareWindow)
}
