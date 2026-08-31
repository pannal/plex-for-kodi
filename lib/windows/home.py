from __future__ import absolute_import

import json
import threading
import time
import math

import plexnet
from kodi_six import xbmc
from kodi_six import xbmcgui
from plexnet import plexapp, plexlibrary, plexresource
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
from . import background
from .mixins.spoilers import SpoilersMixin
from .mixins.watchlist import removeFromWatchlistBlind
from .mixins.common import CommonMixin


HUBS_REFRESH_INTERVAL = 300  # 5 Minutes
REACHABILITY_CHECK_INTERVAL = 600  # 10 Minutes
PATH_MAPPING_PROBE_INTERVAL = 60  # 1 Minute
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

NO_HUB = "__NO_HUB__"

PLAYLIST_HUB_TITLES = {
    'playlists.audio': T(34094, 'Audio Playlists'),
    'playlists.video': T(34095, 'Video Playlists'),
}

class HubsList(list):
    identifier = NO_HUB
    def init(self):
        self.lastUpdated = time.time()
        self.invalid = False
        return self



class SectionHubsTask(backgroundthread.Task):
    def setup(self, section, callback, section_keys=None, reselect_pos_dict=None):
        self.section = section
        self.callback = callback
        self.section_keys = section_keys
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
                                                                      section_ids=self.section_keys)).init()
            hubs.identifier = self.section.key
            if self.isCanceled():
                return
            self.callback(self.section, hubs, reselect_pos_dict=self.reselect_pos_dict)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on section: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)
        except:
            util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
            util.DEBUG_LOG('Generic exception when fetching section: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)


class ResolveForeignTask(backgroundthread.Task):
    """Resolve un-cached foreign-library records off the GUI thread.

    Fills the per-sectionId resolution cache with (section, offline); live results let
    the callback upgrade placeholders -> live and refresh the rail.
    """

    def setup(self, win, records, manager=None):
        self.win = win
        self.records = records
        self.manager = manager
        return self

    def run(self):
        if self.isCanceled() or not self.records:
            return
        if self._resolve_records():
            self.win._onForeignResolved()

    def _resolve_records(self):
        upgraded = False
        for record in self.records:
            if self.isCanceled():
                break
            key = u'{0}:{1}'.format(record.get('server_uuid'), record.get('section_key'))
            cache = getattr(self.win, '_foreignResolved', None) or {}
            if key in cache:
                continue  # already resolved this session
            section, offline = self.win.resolveForeignLibrary(record, manager=self.manager)
            if not offline:
                upgraded = True  # placeholder -> live: caller refreshes the rail
            self.win._foreignResolved[key] = (section, offline)
        return upgraded


class PinnedTypeHubsTask(backgroundthread.Task):
    """Builds the one hub a pinned item-type view shows: the library's collections."""

    def setup(self, section, callback, reselect_pos_dict=None):
        self.section = section
        self.callback = callback
        self.reselect_pos_dict = reselect_pos_dict
        return self

    def run(self):
        if self.isCanceled():
            return

        if not plexapp.SERVERMANAGER.selectedServer or not self.section.server:
            # Could happen during sign-out for instance
            return

        try:
            hub = plexlibrary.CollectionsHub(self.section.librarySection)
            # the server names its hubs; this one is ours, so it needs its own title
            hub.set('title', T(32490, 'Collections'))
            hubs = HubsList([hub] if hub.items else []).init()
            hubs.identifier = self.section.key
            if self.isCanceled():
                return
            self.callback(self.section, hubs, reselect_pos_dict=self.reselect_pos_dict)
        except plexnet.exceptions.BadRequest:
            util.DEBUG_LOG('404 on collections of: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)
        except:
            util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
            util.DEBUG_LOG('Generic exception when fetching collections of: {0}', repr(self.section.title))
            hubs = HubsList().init()
            hubs.invalid = True
            self.callback(self.section, hubs)


class PathMappingProbeTask(backgroundthread.Task):
    """Checks the Kodi-side roots of mapped libraries. Runs in the background because a
    dead SMB/NFS share blocks for the full mount timeout, which would stall the section
    list every time Home is drawn.
    """
    def setup(self, targets, callback):
        self.targets = targets
        self.callback = callback
        return self

    def run(self):
        changed = False
        announce = []
        util.DEBUG_LOG("Path mapping probe: checking {} root(s)", len(self.targets))
        for server_name, map_path, title in self.targets:
            if self.isCanceled():
                return

            if pmm.verifyMapping(server_name, map_path):
                changed = True
            util.DEBUG_LOG("Path mapping probe: {} -> {}", map_path,
                           pmm.isMappingBroken(server_name, map_path) and "unreachable" or "ok")

            if (pmm.isMappingBroken(server_name, map_path)
                    and pmm.claimNotification(server_name, map_path, "root")):
                announce.append(title or map_path)

        if self.isCanceled():
            return

        if announce:
            # one popup for the whole run: Kodi queues notifications, so one per library
            # would keep the screen covered for 5s * number of mapped libraries
            pmm.notify(T(35037, "Path mapping unavailable for: {}").format(" / ".join(announce)))

        if changed:
            self.callback()


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
            util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
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
            util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
        except:
            util.DEBUG_LOG('Something went wrong when extending hub: {0}', repr(self.hub.hubIdentifier))
            util.ERROR()


class DiscoverHubsTask(backgroundthread.Task):
    """Background task to discover all available hubs across all library sections."""

    def setup(self, sections, callback):
        self.sections = sections  # List of all sections (including home_section)
        self.callback = callback
        return self

    def run(self):
        if self.isCanceled():
            return

        if not plexapp.SERVERMANAGER.selectedServer:
            return

        availableHubs = {}

        for section in self.sections:
            if self.isCanceled():
                return

            try:
                section_key = section.key
                section_id = sectionId(section)
                section_type = getattr(section, 'type', 'unknown')
                section_title = getattr(section, 'title', T(32411, 'Unknown'))

                # Fetch hubs for this section
                hubs = section.server.hubs(section_key, count=HUB_PAGE_SIZE)

                for hub in hubs:
                    clean_identifier = hub.getCleanHubIdentifier(is_home=(section_key is None))

                    # Create section-specific catalog identifier
                    # Home hubs: use clean identifier (e.g., "home.continue")
                    # Library hubs: prefix with sectionId (e.g., "SERVERUUID:1|movie.recentlyadded")
                    if section_key is None:
                        catalog_id = clean_identifier
                    else:
                        catalog_id = HomeWindow.foreignCatalogId(section_id, clean_identifier)

                    # Determine native display type from hub content
                    native_display = 'poster'  # Default
                    if hub.items:
                        item_type = hub.items[0].type
                        native_display = {
                            'episode': 'ar16x9', 'clip': 'ar16x9', 'video': 'ar16x9',
                            'album': 'square', 'artist': 'square', 'photo': 'square', 'track': 'square',
                        }.get(item_type, 'poster')

                    # Resolve hub title — playlist hubs have no server-provided title
                    hub_title = hub.title
                    if not hub_title:
                        hub_title = PLAYLIST_HUB_TITLES.get(clean_identifier, clean_identifier)

                    # Store hub info - each section's hubs are stored separately
                    if catalog_id not in availableHubs:
                        availableHubs[catalog_id] = {
                            'catalog_id': str(catalog_id),
                            'identifier': str(clean_identifier),
                            'title': str(hub_title),
                            'hubIdentifier': str(hub.hubIdentifier),
                            'source_section_key': section_id,
                            'source_section_title': str(section_title) if section_title else T(32411, 'Unknown'),
                            'source_section_type': str(section_type) if section_type else 'unknown',
                            'native_display': native_display,
                            'item_count': len(hub.items) if hub.items else 0,
                        }

            except plexnet.exceptions.BadRequest:
                pass
            except Exception as e:
                pass


        if not self.isCanceled():
            self.callback(availableHubs)


class VirtualSection(object):
    locations = []
    isMapped = False
    mappedPaths = []
    mappingBroken = False

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


# item types that can be pinned to the top bar as a view of their own, per library type
PINNABLE_TYPES = {
    'movie': ('collection',),
    'show': ('collection',),
    'artist': ('collection',),
}


class PinnedTypeSection(object):
    """A library pinned to the top bar showing one fixed item type, e.g. its collections.

    Everything but the key, the title and the item type is delegated to the library it was
    pinned from, so all queries still run against the real section. The separate key is the
    point of the whole thing: LibrarySettings stores sort and filters per section key, so a
    pinned collections view keeps its own alphabetical sort while the library itself keeps
    the user's filters, and neither switching item types nor visiting one touches the other.
    """
    def __init__(self, section, item_type):
        self.librarySection = section
        self.itemType = item_type
        self.key = pinnedSectionKey(section.key, item_type)
        self.title = T(35043, '{} Collections').format(section.title) if item_type == 'collection' \
            else u'{} {}'.format(section.title, item_type)

    def __getattr__(self, name):
        # only reached for attributes we don't define ourselves; guarded so an access
        # before __init__ completed raises instead of recursing
        if name == 'librarySection':
            raise AttributeError(name)
        return getattr(self.librarySection, name)

    def __repr__(self):
        return '<PinnedTypeSection:{0}>'.format(self.key)

    def getLibrarySectionId(self):
        # view type (poster/list) is shared with the library, unlike sort and filters
        return self.librarySection.key


def pinnedSectionKey(section_key, item_type):
    return '{0}#{1}'.format(section_key, item_type)


def sectionId(section):
    """Collision-safe identity for a rail section, separate from its wire `key`.

    Real sections are keyed by owning-server uuid + section key, so two servers with
    the same numeric key (e.g. both '1') never collide in the same rail. Virtual
    sections get fixed sentinels. A foreign placeholder carries its identity verbatim.
    """
    if isinstance(section, PinnedTypeSection):
        return '{0}#{1}'.format(sectionId(section.librarySection), section.itemType)
    stored = getattr(section, 'sectionId', None)
    if stored:
        return stored
    if section.key is None:
        return 'home'
    if getattr(section, 'key', None) == 'playlists':
        return 'playlists'
    if getattr(section, 'ID', None) == 'watchlist':
        return 'watchlist'
    return '{0}:{1}'.format(section.server.uuid, section.key)


def hubSectionKey(section_key, server_uuid):
    """Compose a persisted sectionId key from its parts: '{uuid}:{key}'.

    Same output shape as sectionId() but from raw persisted parts (a bare key + the
    owning server's uuid) rather than a live section object. Only used during the
    on-disk sectionId settings migration (see rekeyLibrarySettings/rekeyHubSettings).
    Home is None. Already sectionId-shaped keys are never passed here.
    """
    if section_key is None:
        return None
    return u'{0}:{1}'.format(server_uuid, section_key)


def _is_bare_key(key):
    """True when a persisted settings key is a bare section wire key (needs re-key).

    Used by the sectionId settings migration (rekeyLibrarySettings/rekeyHubSettings):
    a bare key ('1') has no server, so under multi-server it is ambiguous and must be
    re-keyed to 'uuid:1'. Bare keys are integer strings with no ':' separator.
    sectionId keys ('uuid:key') and sentinel strings ('playlists',
    '/library/sections/watchlist', '__home__') are distinct and pass through untouched.
    """
    if key is None:
        return False
    s = str(key)
    return s.lstrip('-').isdigit() and ':' not in s


class ForeignLibrarySection(object):
    """Stand-in for a foreign library whose server is unknown or unreachable.

    Carries the config record's denormalized labels and an explicit sectionId, so it
    renders in the rail (suffixed title) and keeps the same identity even with server
    None. Resolves to a live LibrarySection when the server is reachable.
    """
    offline = True
    server = None
    key = None
    type = None
    isMapped = False
    mappingBroken = False

    def __init__(self, server_uuid, section_key, server_name, section_title):
        self.server_uuid = server_uuid
        self.section_key = str(section_key)
        self.server_name = server_name
        self.section_title = section_title
        self.title = u'{0} - {1}'.format(section_title, server_name)
        self.sectionId = u'{0}:{1}'.format(server_uuid, self.section_key)

    @classmethod
    def placeholder(cls, **kwargs):
        return cls(**kwargs)


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


class HomeWindow(kodigui.BaseWindow, util.CronReceiver, CommonMixin, SpoilersMixin):
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

    USER_MENU_BG_ID = 801
    USER_MENU_GROUP_ID = 901

    PLAYER_STATUS_BUTTON_ID = 204

    # Hub base ID - hubs are dynamically generated starting from this ID
    HUB_BASE_ID = 400

    def getHubDisplayType(self, hub, identifier):
        """Determine the display type for a hub: 'poster', 'ar16x9', or 'square'.

        With dynamic hub templating, all hubs support all display types via
        conditional visibility based on the hub.display.4XX window property.
        """
        # Mixed content hubs (like Continue Watching) always use poster
        if identifier in self.HUBS_MIXED_CONTENT:
            return 'poster'

        # Check identifier prefixes first (works even if items not loaded yet)
        if identifier:
            for prefix, display_type in self.HUB_DISPLAY_DEFAULTS.items():
                if identifier.startswith(prefix):
                    return display_type

            # Check for keywords in identifier (e.g., 'recentlyAddedAlbums' contains 'album')
            identifier_lower = identifier.lower()
            for keyword in self.HUB_SQUARE_KEYWORDS:
                if keyword in identifier_lower:
                    return 'square'
            for keyword in self.HUB_16X9_KEYWORDS:
                if keyword in identifier_lower:
                    return 'ar16x9'

        # Check hub's type attribute (Plex sets this to indicate content type)
        if hub:
            hub_type = getattr(hub, 'type', None)
            if hub_type in ('episode', 'clip', 'video'):
                return 'ar16x9'
            elif hub_type in ('album', 'artist', 'photo', 'track'):
                return 'square'

        # Detect from hub content as fallback
        if hub and hub.items:
            item_type = getattr(hub.items[0], 'type', None)
            # 16x9 content types - episodes, clips, videos
            if item_type in ('episode', 'clip', 'video'):
                return 'ar16x9'
            # Square content types - albums, artists, photos, tracks
            elif item_type in ('album', 'artist', 'photo', 'track'):
                return 'square'

        # Default to poster for everything else (movies, shows, mixed content)
        return 'poster'

    # Hub identifiers that should NOT show progress (watchlist/discovery hubs)
    HUBS_NO_PROGRESS = {
        'watchlist.continueWatching', 'watchlist.coming-soon', 'watchlist.recently-added',
        'home.top_watchlisted', 'home.coming-soon', 'home.trending-friends',
        'home.trending-for-you', 'home.new-for-you',
    }

    # Hub identifier prefixes that indicate 16x9 display format
    HUB_PREFIXES_16X9 = ('video.', 'playlists.video', 'music.videos.')

    # Hub identifiers that have mixed content (movies + episodes) - always use poster format
    HUBS_MIXED_CONTENT = {
        'continueWatching',  # Combined continue watching hub (modern Plex clients) - mixed movies/episodes
        'home.ondeck',  # Old-style On Deck hub - uses show posters
        'tv.inprogress', 'tv.ondeck', 'movie.inprogress',
    }
    # Note: home.continue (old Continue Watching) is NOT in HUBS_MIXED_CONTENT
    # because it shows episodes only and should use 16x9 thumbnails

    def getHubRenderFlags(self, hub, identifier):
        """Get rendering flags for a hub based on identifier patterns and content.

        Returns dict with: with_progress, do_updates, text2lines, ar16x9, with_art
        All hubs get sensible defaults - no fixed index mapping.
        """
        # Default flags - most hubs want these
        flags = {
            'with_progress': True,
            'do_updates': True,
            'text2lines': True,
            'ar16x9': False,
            'with_art': False,
        }

        # Watchlist/discovery hubs don't show progress
        if identifier in self.HUBS_NO_PROGRESS:
            flags['with_progress'] = False

        # Mixed content hubs (continue watching, on deck, in progress) always use poster
        # Don't auto-detect from content as they contain both movies and episodes
        if identifier in self.HUBS_MIXED_CONTENT:
            return flags

        # Check if identifier matches a known display type prefix
        # This prevents content-based detection from overriding the intended display
        identifier_has_known_prefix = False
        if identifier:
            # Check 16x9 prefixes first
            for prefix in self.HUB_PREFIXES_16X9:
                if identifier.startswith(prefix):
                    flags['ar16x9'] = True
                    flags['with_art'] = True  # 16x9 hubs use art/thumb images
                    identifier_has_known_prefix = True
                    break

            # Check poster/square prefixes from HUB_DISPLAY_DEFAULTS
            # Also set ar16x9 flags if the display type is ar16x9
            if not identifier_has_known_prefix:
                for prefix, display_type in self.HUB_DISPLAY_DEFAULTS.items():
                    if identifier.startswith(prefix):
                        identifier_has_known_prefix = True
                        if display_type == 'ar16x9':
                            flags['ar16x9'] = True
                            flags['with_art'] = True
                        break

        # Only detect from hub content if identifier doesn't have a known prefix
        # This prevents "tv.recentlyadded" (poster) from being detected as 16x9 due to episode content
        if not identifier_has_known_prefix and not flags['ar16x9'] and hub and hub.items:
            item_type = getattr(hub.items[0], 'type', None)
            if item_type in ('episode', 'clip', 'video'):
                flags['ar16x9'] = True
                flags['with_art'] = True  # 16x9 hubs use art/thumb images

        return flags

    # Display type mapping for auto-detection based on item type
    TYPE_TO_DISPLAY = {
        # 16x9 wide format
        'episode': 'ar16x9',
        'clip': 'ar16x9',
        'video': 'ar16x9',
        # Square format
        'album': 'square',
        'artist': 'square',
        'photo': 'square',
        'track': 'square',
        # Poster format (default for movies, shows, seasons)
        'movie': 'poster',
        'show': 'poster',
        'season': 'poster',
    }

    THUMB_POSTER_DIM = util.scaleResolution(244, 361)
    THUMB_AR16X9_DIM = util.scaleResolution(532, 299)
    THUMB_SQUARE_DIM = util.scaleResolution(244, 244)

    def __init__(self, *args, **kwargs):
        kodigui.BaseWindow.__init__(self, *args, **kwargs)
        SpoilersMixin.__init__(self, *args, **kwargs)
        self.lastSection = home_section
        self.lastHubs = None
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
        self._recheckPD = False
        self._checkingPD = False
        self._applyTheme = False
        self._ignoreTick = False
        self._ignoreInput = False
        self._ignoreReInit = False
        self._goRootHoldUntil = 0
        self._restarting = False
        self._anyItemAction = False
        self._odHubsDirty = False
        self._updateSourceChanged = False
        self.librarySettings = None
        self.hubSettings = None
        self.availableHubs = {}  # Catalog of all discovered hubs
        self.hubDiscoveryTask = None  # Background hub discovery task
        self._managingHubsForSection = None  # Section key while Manage Hubs dialog is open
        self.anyLibraryHidden = False
        self.wantedSections = None
        self.movingSection = False
        self._initialMovingSectionPos = None
        self.block_section_change = False
        self.go_root = False
        self.kodi_exiting = False
        self._lastReachabilityCheck = 0
        self._lastPathMappingProbe = 0
        self._pathMappingTargets = []

        from . import windowutils
        windowutils.HOME = self

        # Re-entrant: the background hub callbacks (sectionHubsCallback,
        # crossSectionHubsCallback, updateHubCallback) acquire this and then call
        # showHubs()/showHub(), which re-acquire it via the showHubs() funnel.
        # It serializes every draw pass so an off-GUI-thread refresh (wake/tick/
        # reinit) can't run _showHub() on the same controls while a worker callback
        # is mid-replaceItems() — that race freed list items out from under
        # CGUIListItem::SetProperty and crashed guilib.
        self.lock = threading.RLock()

        util.setGlobalBoolProperty('off.sections', '')

    def onFirstInit(self):
        # Migrate existing CE_VS10 users: inject video_show_vs10 into saved button list
        # if it was saved before the VS10 feature existed
        if util.CE_VS10 and not util.getSetting('vs10_button_migrated', False):
            button_settings = util.getUserSetting('player_show_buttons')

            if button_settings is not None and 'video_show_vs10' not in button_settings:
                button_settings.append('video_show_vs10')
                util.setSetting('player_show_buttons.{}'.format(plexapp.ACCOUNT.ID), json.dumps(button_settings))
            util.setSetting('vs10_button_migrated', True)

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
        self.userList = kodigui.ManagedControlList(self, self.USER_LIST_ID, 5)

        # Dynamic hub control generation based on hub_count setting
        hub_count = util.getSetting('hub_count', 8)
        self.hubControls = tuple(
            kodigui.ManagedControlList(self, self.HUB_BASE_ID + i, 5)
            for i in range(hub_count)
        )
        self.hubFocusIndexes = tuple(range(hub_count))

        self.bottomItem = 0
        if self.serverRefresh():
            self.setFocusId(self.SECTION_LIST_ID)

        self.hookSignals()
        util.CRON.registerReceiver(self)
        self.updateProperties()
        self.checkPlexDirectHosts(list(plexapp.SERVERMANAGER.serversByUuid.values()), source="stored")

    def closeWRecompileTpls(self):
        self._applyTheme = False
        self._shuttingDown = True
        self.closeOption = "recompile"
        self.doClose()

    def show(self, **kwargs):
        super(HomeWindow, self).show(**kwargs)
        if self.go_root:
            util.DEBUG_LOG("Home: Go root requested, reinitializing")
            self.onReInit()

    def onReInit(self):
        util.DEBUG_LOG("Home: On ReInit")
        if self._ignoreReInit or time.time() < self._goRootHoldUntil:
            return

        if player.PLAYER.bgmPlaying:
            player.PLAYER.stopAndWait(fade=util.addonSettings.themeMusicFade, deferred=True)

        self._anyItemAction = False
        if self._applyTheme:
            self.closeWRecompileTpls()
            return

        if self.go_root:
            self.setProperty('hub.focus', '')
            # cancel any pending async section change so the focus call below doesn't trigger a redundant reload
            self.sectionChangeTimeout = None
            # decide whether we need to switch the displayed hubs before overwriting state
            needs_hub_switch = self.lastHubs != home_section.key
            self.lastFocusID = self.SECTION_LIST_ID
            self.lastSection = home_section
            self.lastHubs = home_section.key
            if needs_hub_switch:
                self.showHubs(home_section)
            self.setFocusId(self.SECTION_LIST_ID)
            self.sectionList.setSelectedItemByPos(0)
            # somehow we need to do this as well.
            xbmc.executebuiltin('Control.SetFocus({0}, {1})'.format(self.SECTION_LIST_ID, 0))
            self.go_root = False
            # set the hold deadline AT THE END so the 150ms window is measured from when the
            # post-branch event queue starts draining (showHubs can take several hundred ms,
            # which would otherwise blow past the deadline before any stray fires).
            self._goRootHoldUntil = time.time() + 0.15
            return

        if self._reloadOnReinit:
            if self._recheckPD:
                self.checkPlexDirectHosts(list(plexapp.SERVERMANAGER.serversByUuid.values()))
            self.serverRefresh()
            self._reloadOnReinit = False
            self._recheckPD = False

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

            elif self.lastFocusID == self.SECTION_LIST_ID:
                if self.lastSection and self.lastHubs != self.lastSection.key:
                    self.showHubs(self.lastSection)

            else:
                if self.getFocusId() != self.lastFocusID:
                    self.setFocusId(self.lastFocusID)

        if self._odHubsDirty:
            self._odHubsDirty = False
            # If section is stale, do a full section refresh instead of individual
            # hub updates. Running both causes race conditions and index errors.
            hubs = self.sectionHubs.get(self.cacheKeyForSection(self.lastSection)) if self.lastSection else None
            if hubs is not None and time.time() - hubs.lastUpdated > HUBS_REFRESH_INTERVAL:
                util.DEBUG_LOG('UpdateOnDeckHubs: Section stale, doing full refresh instead')
                self.showHubs(self.lastSection, update=True)
            else:
                self._updateOnDeckHubs()

    def checkPlexDirectHosts(self, servers, source="stored", *args, **kwargs):
        while self._checkingPD:
            util.MONITOR.waitFor()
        try:
            self._checkingPD = True
            util.DEBUG_LOG("Home: checkPlexDirectHosts: {} ({})", servers, source)
            handlePD = util.getSetting('handle_plexdirect')
            if handlePD == "never":
                return

            forcePD = util.getSetting('force_pd_mapping')

            hosts = []
            s = []
            for server in servers:
                force_check = False
                # we might have an active connection that's marked as local but a combination of settings doesn't allow us
                # to connect insecurely; force plex.direct handling in this case
                if (server.activeConnection and ".plex.direct:" in server.activeConnection.address and
                        not server.activeConnection.pdHostnameResolved) or forcePD:
                    util.DEBUG_LOG("Forcing check for plex.direct connections of: {} (force: {})", server, forcePD)
                    force_check = True

                if not force_check:
                    # only check stored or myplex servers
                    if server.sourceType not in (None, plexresource.ResourceConnection.SOURCE_MYPLEX):
                        continue
                    # if we're set to honor dnsRebindingProtection=1 and the server has this flag at 0 or
                    # if we're set to honor publicAddressMatches=1 and the server has this flag at 0, and we haven't seen the
                    # server locally, skip plex.direct handling
                    if (((util.addonSettings.honorPlextvDnsrebind and not server.dnsRebindingProtection) or
                            (util.addonSettings.honorPlextvPam and not server.sameNetwork and not server.anyLANConnection))
                            and not server.anyPDHostNotResolvable):
                        util.DEBUG_LOG("Ignoring DNS handling for plex.direct connections of: {}", server)
                        continue
                hosts += [c.address for c in server.connections]
                s.append(server.name)

            knownHosts = pdm.getHosts()
            pdHosts = [host for host in hosts if ".plex.direct:" in host]

            util.DEBUG_LOG("Checking host mapping for {} {} connections: {}, servers: {}",
                           len(pdHosts), source, ", ".join(pdHosts), ", ".join(s))

            newHosts = set(pdHosts) - set(knownHosts)
            if newHosts:
                force_mapping = []
                # even for docker hosts we might want to force the mapping if it's the active connection and it didn't
                # resolve
                for server in servers:
                    if not server.anyPDHostNotResolvable and not forcePD:
                        continue
                    addrs = [c.address for c in server.connections if ".plex.direct:" in c.address and (not c.pdHostnameResolved or forcePD)]
                    force_mapping += addrs
                    util.DEBUG_LOG("Forcing mapping for connections via: {}", addrs)
                pdm.newHosts(newHosts, source=source, force_mapping=force_mapping)
            diffLen = len(pdm.diff)

            # there are situations where the myPlexManager's resources are ready earlier than
            # any other. In that case, force the check.
            force = plexapp.MANAGER.gotResources

            util.DEBUG_LOG("Plex.direct hosts that we'll add to advancedsettings.xml: {}", pdm.diff)

            if ((source == "stored" and plexapp.ACCOUNT.isOffline) or source == "myplex" or force or forcePD) and pdm.differs:
                if handlePD == 'ask':
                    button = optionsdialog.show(
                        T(32993, '').format(diffLen),
                        T(32994, '').format(diffLen),
                        T(32328, 'Yes'),
                        T(32035, 'Always'),
                        T(32033, 'Never'),
                    )
                    if button not in (0, 1, 2):
                        pdm.resetHosts()
                        return

                    if button == 1:
                        util.setSetting('handle_plexdirect', 'always')
                    elif button == 2:
                        util.setSetting('handle_plexdirect', 'never')
                        pdm.resetHosts()
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
        finally:
            self._checkingPD = False

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
        self.librarySettings = self.rekeyLibrarySettings(self.librarySettings)

    def saveLibrarySettings(self):
        if self.librarySettings:
            setting_key = 'home.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:],
                                                       plexapp.ACCOUNT.ID)
            util.setSetting(setting_key, json.dumps(self.librarySettings))

    def foreignSettingKey(self):
        # account scope identical to loadLibrarySettings/loadHubSettings (home.py:1010,1118)
        return 'home.foreign_libraries.{}'.format(plexapp.ACCOUNT.ID)

    def loadForeignLibraries(self):
        self._foreignLibraries = []
        try:
            data = util.getSetting(self.foreignSettingKey(), '')
            self._foreignLibraries = json.loads(data) if data else []
        except ValueError:
            util.ERROR()

    def saveForeignLibraries(self):
        util.setSetting(self.foreignSettingKey(), json.dumps(self._foreignLibraries))

    def foreignLibraries(self):
        if not getattr(self, '_foreignLibraries', None):
            self.loadForeignLibraries()
        return self._foreignLibraries

    def pinForeignLibrary(self, server_uuid, section_key, server_name, section_title):
        libs = self.foreignLibraries()
        for record in libs:
            if record.get('server_uuid') == server_uuid and record.get('section_key') == str(section_key):
                record['server_name'] = server_name
                record['section_title'] = section_title
                break
        else:
            libs.append({
                'server_uuid': server_uuid,
                'section_key': str(section_key),
                'server_name': server_name,
                'section_title': section_title,
            })
        self.saveForeignLibraries()

    def unpinForeignLibrary(self, server_uuid=None, section_key=None):
        libs = self.foreignLibraries()
        before = len(libs)
        self._foreignLibraries = [
            r for r in libs
            if not ((server_uuid is not None and r.get('server_uuid') == server_uuid)
                    and (section_key is not None and r.get('section_key') == str(section_key)))
        ]
        if len(self._foreignLibraries) != before:
            self.saveForeignLibraries()

    def pruneForeignLibraries(self, known_servers):
        libs = self.foreignLibraries()
        self._foreignLibraries = [r for r in libs if r.get('server_uuid') in known_servers]
        self.saveForeignLibraries()
        return self._foreignLibraries

    def resolveForeignLibrary(self, record, manager=None):
        """Resolve a foreign config record to a live section or an offline placeholder.

        Returns (section, offline). Live sections refresh the record's denormalized title.
        """
        if manager is None:
            manager = plexapp.SERVERMANAGER
        server = self._findServerByUuid(manager, record.get('server_uuid'))
        if server is None:
            return ForeignLibrarySection.placeholder(**{
                'server_uuid': record.get('server_uuid'),
                'section_key': record.get('section_key'),
                'server_name': record.get('server_name'),
                'section_title': record.get('section_title'),
            }), True
        try:
            for section in server.library.sections():
                if str(section.key) == str(record.get('section_key')):
                    record['section_title'] = section.title
                    return section, False
        except Exception:
            util.ERROR()
        return ForeignLibrarySection.placeholder(**{
            'server_uuid': record.get('server_uuid'),
            'section_key': record.get('section_key'),
            'server_name': record.get('server_name'),
            'section_title': record.get('section_title'),
        }), True

    def foreignRailSections(self, manager=None, selected_server_uuid=None):
        """Resolve the foreign-library config into rail-appendable sections.

        Serves from the per-sectionId resolution cache; un-cached records (not yet
        resolved this session) render as offline placeholders so the GUI thread never
        blocks on a foreign server's network call. Resolution happens off-thread via
        ResolveForeignTask and upgrades placeholders to live in place.
        """
        if selected_server_uuid is None:
            sel = plexapp.SERVERMANAGER.selectedServer
            selected_server_uuid = sel.uuid if sel else None

        def record_key(record):
            return u'{0}:{1}'.format(record.get('server_uuid'), record.get('section_key'))

        sections = []
        for record in self.foreignLibraries():
            if record.get('server_uuid') == selected_server_uuid:
                continue
            cache = getattr(self, '_foreignResolved', None) or {}
            resolved = cache.get(record_key(record))
            if resolved is not None:
                section, offline = resolved
            else:
                # not resolved this session: show placeholder now, resolve in background
                section, offline = (
                    ForeignLibrarySection.placeholder(**{
                        'server_uuid': record.get('server_uuid'),
                        'section_key': record.get('section_key'),
                        'server_name': record.get('server_name'),
                        'section_title': record.get('section_title'),
                    }), True)
            section.is_foreign = True
            if not offline:
                section.title = u'{0} - {1}'.format(
                    section.title, record.get('server_name'))
            sections.append(section)
        return sections

    def isSectionPinnedToHome(self, section):
        return any(
            r.get('server_uuid') == section.server.uuid
            and r.get('section_key') == str(section.key)
            for r in self.foreignLibraries())

    def _orderRailSections(self, sections, foreign_sections, order):
        """Order locals plus foreign into the rail render order.

        Locals and pins follow the saved `order`. A foreign library that was moved keeps
        the slot its sectionId holds in `order`; one never moved (absent from `order`)
        goes to the end of the rail. Before this, foreign libraries were always appended
        last, so a moved one snapped back to the end after a restart.
        """

        def orderPos(s):
            ck = self.cacheKeyForSection(s)
            if ck in order:
                return order.index(ck), 0
            if isinstance(s, PinnedTypeSection):
                lib_ck = self.cacheKeyForSection(s.librarySection)
                if lib_ck in order:
                    # pinned after the order was stored: follow its library instead of
                    # ending up in front of everything
                    return order.index(lib_ck), 1
            if getattr(s, 'is_foreign', False):
                return len(order), 0  # never-ordered foreign: end of rail
            return -1, 0

        return sorted(sections + foreign_sections, key=orderPos)

    @staticmethod
    def _sameRailSection(a, b):
        """Two rail sections are the same rail item iff their sectionIds match."""
        return sectionId(a) == sectionId(b)

    def cacheKeyForSection(self, section):
        """Collision-safe sectionHubs key for a section object.

        Real libraries and pinned type-views key by sectionId ('uuid:key' / 'uuid:key#type'),
        which is unique per server. Virtual sections (Home/Playlists/Watchlist) keep their
        existing scalar keys.
        """
        if section is None:
            return None  # Home
        sid = sectionId(section)
        if sid in ('playlists', 'watchlist', 'home'):
            return getattr(section, 'key', None)  # virtual: keep existing scalar key
        return sid  # real + pinned-type + foreign placeholder

    @staticmethod
    def foreignCatalogId(section_key, identifier):
        """Compose a catalog_id embedding a section key, recovering both parts."""
        if section_key is None:
            return identifier
        return u'{0}|{1}'.format(section_key, identifier)

    @staticmethod
    def parseCatalogId(catalog_id):
        """Split a catalog_id back into (source_section_key, identifier). Home => (None, id)."""
        if '|' in str(catalog_id):
            src, ident = str(catalog_id).rsplit('|', 1)
            return src, ident
        return None, catalog_id

    def scheduleForeignHubFetches(self, sections):
        """Schedule hub fetch for live foreign sections; offline placeholders never fetch."""
        if not plexapp.SERVERMANAGER.selectedServer.hasHubs():
            # no hub pipeline on servers without hubs; nothing to schedule
            return
        tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections)
                 for s in sections
                 if not getattr(s, 'offline', False) and s.server
                 and not getattr(s.server, 'DEFER_HUBS', False)]
        self.tasks += tasks
        if tasks:
            backgroundthread.BGThreader.addTasks(tasks)

    def _onForeignResolved(self):
        """Called from ResolveForeignTask on a worker thread: upgrade placeholders and
        refresh the rail once."""
        with self.lock:
            self._foreignResolveScheduled = False
            if not any(not offline for _, offline in
                       (getattr(self, '_foreignResolved', {}) or {}).values()):
                return  # nothing went live; nothing to refresh
            for server_uuid in {r.get('server_uuid') for r in self.foreignLibraries()}:
                self._reResolveForeignPlaceholders(server_uuid)
            self.serverRefresh()

    def _kickForeignResolution(self):
        """Start background resolution for foreign records not yet resolved this session."""
        if getattr(self, '_foreignResolved', None) is None:
            self._foreignResolved = {}
        if getattr(self, '_foreignResolveScheduled', False):
            return  # one in-flight resolve round is enough
        pending = [r for r in self.foreignLibraries()
                   if u'{0}:{1}'.format(r.get('server_uuid'), r.get('section_key'))
                   not in self._foreignResolved]
        if not pending:
            return
        self._foreignResolveScheduled = True
        task = ResolveForeignTask().setup(self, pending)
        self.tasks.append(task)
        backgroundthread.BGThreader.addTask(task)

    # --- SectionId settings migration (backward compat) -----------------------
    # Before sectionId, this addon (a released 1.13.x/1.14.x) persisted settings
    # against *bare* library wire keys ('1') and *colon* catalog_ids ('1:Movies').
    # Multi-server means two servers can share a wire key, so the rail now keys by
    # sectionId ('uuid:key') instead. These three re-key methods migrate already-
    # saved settings to the new sectionId shape the first time they load, so existing
    # users' hidden-state, ordering, and hub edits survive the upgrade instead of
    # silently resetting. They run once, are idempotent, and never touch foreign
    # or already-sectionId-shaped data. Top-level helpers: hubSectionKey /
    # parseCatalogId. Kept intentionally; do not delete without a data-migration plan.

    def rekeyLibrarySettings(self, settings):
        """Re-key bare section keys in persisted librarySettings to sectionId (selected server)."""
        if not settings:
            return settings
        server_uuid = plexapp.SERVERMANAGER.selectedServer.uuid
        out = {}
        for key, value in settings.items():
            if key == 'order':
                out[key] = [k if not _is_bare_key(k) else hubSectionKey(k, server_uuid)
                             for k in value]
            elif key == 'playlists' or key == '/library/sections/watchlist':
                out[key] = value
            elif _is_bare_key(key):
                out[hubSectionKey(key, server_uuid)] = value
            else:
                out[key] = value
        return out

    def rekeyHubSettings(self, settings):
        """Re-key persisted hubSettings to sectionId; re-key nested catalog_ids to '|' schema."""
        if not settings:
            return settings
        server_uuid = plexapp.SERVERMANAGER.selectedServer.uuid
        out = {}
        for key, value in settings.items():
            if key == '__home__':
                nk = None
            elif _is_bare_key(key):
                nk = hubSectionKey(key, server_uuid)
            else:
                nk = key  # already sectionId-shaped (own forward-written or foreign)
            if isinstance(value, dict) and 'hubs' in value:
                value = dict(value)
                value['hubs'] = [
                    dict(h, catalog_id=self.rekeyCatalogId(h.get('catalog_id', ''), server_uuid))
                    for h in value.get('hubs', [])
                ]
            out[nk] = value
        return out

    def rekeyCatalogId(self, catalog_id, server_uuid):
        """Re-key a stored ':'-schema catalog_id to the '|' schema."""
        if '|' in str(catalog_id):
            return catalog_id
        if ':' in str(catalog_id):
            src, ident = str(catalog_id).split(':', 1)
            if src.isdigit():
                return u'{0}|{1}'.format(hubSectionKey(src, server_uuid), ident)
        return catalog_id

    @staticmethod
    def _findServerByUuid(manager, uuid):
        if manager is None or not uuid:
            return None
        for server in manager.getServers():
            if getattr(server, 'uuid', None) == uuid:
                return server
        return None

    def loadHubSettings(self):
        setting_key = 'hub.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:], plexapp.ACCOUNT.ID)
        data = util.getSetting(setting_key, '')
        self.hubSettings = {}
        try:
            loaded = json.loads(data)

            # Convert "__home__" key back to None (JSON doesn't support None keys)
            for key, value in loaded.items():
                if key == '_version':
                    continue  # Skip legacy version key
                if key == '__home__':
                    self.hubSettings[None] = value
                else:
                    self.hubSettings[key] = value
        except ValueError:
            pass
        except:
            util.ERROR()
        self.hubSettings = self.rekeyHubSettings(self.hubSettings)

    def saveHubSettings(self):
        setting_key = 'hub.settings.{}.{}'.format(plexapp.SERVERMANAGER.selectedServer.uuid[-8:],
                                                  plexapp.ACCOUNT.ID)
        # Convert None key to "__home__" for JSON storage
        to_save = {}
        for key, value in self.hubSettings.items():
            if key is None:
                to_save['__home__'] = value
            else:
                to_save[key] = value
        json_str = json.dumps(to_save)
        util.setSetting(setting_key, json_str)

    @staticmethod
    def inferDisplayType(hub):
        """Infer display type from the first item in the hub."""
        if not hub.items:
            return "poster"  # Default fallback

        item_type = hub.items[0].type
        return HomeWindow.TYPE_TO_DISPLAY.get(item_type, "poster")

    # Display type defaults for known hub identifiers (by prefix)
    # This ensures correct display regardless of hub content
    HUB_DISPLAY_DEFAULTS = {
        # TV/Show hubs - always poster (shows, not episodes)
        'tv.': 'poster',
        'show.': 'poster',
        # Movie hubs - always poster
        'movie.': 'poster',
        # Music hubs - always square (various prefix patterns)
        'music.': 'square',
        'artist.': 'square',
        'album.': 'square',
        'hub.music.': 'square',
        'track.': 'square',
        # Photo hubs - square
        'photo.': 'square',
        'hub.photo.': 'square',
        # Video hubs - ar16x9
        'video.': 'ar16x9',
        'hub.video.': 'ar16x9',
        # Playlist hubs
        'playlists.audio': 'square',
        'playlists.video': 'ar16x9',
        # Watchlist/discover hubs - always poster (mixed movies + episodes, matches Pannal's original intent)
        'watchlist.': 'poster',
        # Home merged hubs
        'home.television.': 'poster',
        'home.movies.': 'poster',
        'home.music.': 'square',
        'home.photos.': 'square',
        'home.videos.': 'ar16x9',
        # Old-style split Continue Watching hub (episodes only)
        'home.continue': 'ar16x9',
        # Hub prefixed variants
        'hub.tv.': 'poster',
        'hub.show.': 'poster',
        'hub.movie.': 'poster',
        'hub.artist.': 'square',
        'hub.album.': 'square',
        'hub.track.': 'square',
    }

    # Identifiers that indicate square display (contains these substrings)
    HUB_SQUARE_KEYWORDS = ('album', 'artist', 'track', 'music', 'photo')

    # Identifiers that indicate ar16x9 display (contains these substrings)
    HUB_16X9_KEYWORDS = ('episode', 'clip', 'video')

    # Note: getHubDisplayType is defined earlier in the class (around line 400)
    # and handles display type determination with proper 'ar16x9' values

    def discoverAllHubs(self):
        """Start background task to discover all available hubs across all sections."""
        if not plexapp.SERVERMANAGER.selectedServer:
            return

        # Cancel any existing discovery task
        if self.hubDiscoveryTask:
            self.hubDiscoveryTask.cancel()

        # Build list of all sections to query
        sections_to_query = [home_section]

        try:
            library_sections = plexapp.SERVERMANAGER.selectedServer.library.sections()
            sections_to_query.extend(library_sections)
        except:
            return

        # Add playlists section if available
        try:
            pl = plexapp.SERVERMANAGER.selectedServer.playlists()
            if pl:
                sections_to_query.append(playlists_section)
        except:
            pass


        self.hubDiscoveryTask = DiscoverHubsTask().setup(sections_to_query, self.onHubsDiscovered)
        backgroundthread.BGThreader.addTask(self.hubDiscoveryTask)

    def onHubsDiscovered(self, availableHubs):
        """Callback when hub discovery is complete."""
        with self.lock:
            self.availableHubs = availableHubs

    def _discoverHubsSync(self):
        """Synchronous hub discovery - called lazily when user opens Manage Hubs."""
        if not plexapp.SERVERMANAGER.selectedServer:
            return

        # Build list of all sections to query
        sections_to_query = [home_section]

        try:
            library_sections = plexapp.SERVERMANAGER.selectedServer.library.sections()
            sections_to_query.extend(library_sections)
        except:
            return

        # Add playlists section if available
        try:
            pl = plexapp.SERVERMANAGER.selectedServer.playlists()
            if pl:
                sections_to_query.append(playlists_section)
        except:
            pass

        availableHubs = {}

        for section in sections_to_query:
            try:
                section_key = section.key
                section_id = sectionId(section)
                section_type = getattr(section, 'type', 'unknown')
                section_title = getattr(section, 'title', T(32411, 'Unknown'))

                # Fetch hubs for this section
                hubs = section.server.hubs(section_key, count=HUB_PAGE_SIZE)

                for hub in hubs:
                    clean_identifier = hub.getCleanHubIdentifier(is_home=(section_key is None))

                    # Create section-specific catalog identifier
                    if section_key is None:
                        catalog_id = clean_identifier
                    else:
                        catalog_id = HomeWindow.foreignCatalogId(section_id, clean_identifier)

                    # Determine native display type from hub content
                    native_display = 'poster'
                    if hub.items:
                        item_type = hub.items[0].type
                        native_display = self.TYPE_TO_DISPLAY.get(item_type, 'poster')

                    # Resolve hub title — playlist hubs have no server-provided title
                    hub_title = hub.title
                    if not hub_title:
                        hub_title = PLAYLIST_HUB_TITLES.get(clean_identifier, clean_identifier)

                    if catalog_id not in availableHubs:
                        availableHubs[catalog_id] = {
                            'catalog_id': str(catalog_id),
                            'identifier': str(clean_identifier),
                            'title': str(hub_title),
                            'hubIdentifier': str(hub.hubIdentifier),
                            'source_section_key': section_id,
                            'source_section_title': str(section_title) if section_title else T(32411, 'Unknown'),
                            'source_section_type': str(section_type) if section_type else 'unknown',
                            'native_display': native_display,
                            'item_count': len(hub.items) if hub.items else 0,
                        }

            except plexnet.exceptions.BadRequest:
                pass
            except Exception as e:
                pass

        self.availableHubs = availableHubs

    def isHubHidden(self, identifier, section_key=None):
        """Check if user has explicitly hidden this hub.

        Args:
            identifier: The clean hub identifier (e.g., 'movie.recentlyadded')
            section_key: The section key to check configuration for
        """
        # Normalize key for config lookup
        config_key = str(section_key) if section_key is not None else None
        section_config = self.hubSettings.get(config_key) if self.hubSettings else None

        if not section_config or not section_config.get('custom'):
            # No custom config - show all native hubs from Plex
            return False

        # Build catalog_id for this hub in this section
        if section_key is None:
            catalog_id = identifier
        else:
            catalog_id = self.foreignCatalogId(section_key, identifier)

        # Use getEnabledHubsForSection so CW mode mapping is applied consistently.
        # (e.g. config has 'continueWatching' but old mode expects 'home.continue'/'home.ondeck')
        enabled = self.getEnabledHubsForSection(section_key)
        if enabled is None:
            return False
        return catalog_id not in enabled

    def sortHubsByUserOrder(self, hubs, is_home=False, section_key=None):
        """Sort hubs by user-defined order, preserving server order for unordered hubs."""
        # Normalize key to string (hubSettings uses string keys)
        config_key = str(section_key) if section_key is not None else None

        # Get section config if available (config_key can be None for Home)
        section_config = None
        if self.hubSettings:
            section_config = self.hubSettings.get(config_key)

        # Build lookup for user-defined order
        user_order = {}
        if section_config and section_config.get('custom'):
            for idx, hub_config in enumerate(section_config.get('hubs', [])):
                cat_id = hub_config.get('catalog_id', hub_config.get('identifier'))
                user_order[cat_id] = hub_config.get('order', idx)

        # When CW mode changes, map order between old/new identifiers so user ordering is preserved.
        if section_key is None:  # Home section only
            use_new_continue_watching = util.getSetting('hubs_use_new_continue_watching', False)
            if use_new_continue_watching:
                if 'home.continue' in user_order and 'continueWatching' not in user_order:
                    user_order['continueWatching'] = user_order['home.continue']
                elif 'home.ondeck' in user_order and 'continueWatching' not in user_order:
                    user_order['continueWatching'] = user_order['home.ondeck']
            else:
                if 'continueWatching' in user_order:
                    cw_order = user_order['continueWatching']
                    if 'home.continue' not in user_order:
                        user_order['home.continue'] = cw_order
                    if 'home.ondeck' not in user_order:
                        user_order['home.ondeck'] = cw_order + 0.5

        # Pre-compute hub index lookup for O(1) access instead of O(n) per hub
        hubs_list = list(hubs)
        hub_index = {id(hub): idx for idx, hub in enumerate(hubs_list)}

        def get_order(hub):
            identifier = hub.getCleanHubIdentifier(is_home=is_home)

            # Build catalog_id
            if section_key is None:
                catalog_id = identifier
            else:
                catalog_id = self.foreignCatalogId(section_key, identifier)

            # Check user-defined order
            if catalog_id in user_order:
                return (0, user_order[catalog_id])  # User-ordered hubs first

            # Fall back to server order (use pre-computed index)
            return (1, hub_index.get(id(hub), 999))

        return sorted(hubs_list, key=get_order)

    def _buildHubSettingsOptions(self, section_key, section_title):
        """Build the list of option dicts for the hub settings dialog."""
        config_key = section_key
        section_config = self.hubSettings.get(config_key, {}) if self.hubSettings else {}
        has_custom_config = section_config.get('custom', False)
        configured_hubs = section_config.get('hubs', []) if has_custom_config else []

        configured_catalog_ids = {h.get('catalog_id', h.get('identifier')) for h in configured_hubs}

        # Determine enabled/disabled state for all hubs
        hub_states = {}  # catalog_id -> (is_enabled, hub_info)
        for catalog_id, hub_info in self.availableHubs.items():
            if has_custom_config:
                is_enabled = catalog_id in configured_catalog_ids
            else:
                hub_source_key = hub_info.get('source_section_key')
                if section_key is None:
                    # Home section - all native Plex Home hubs are enabled by default
                    is_enabled = (hub_source_key is None)
                else:
                    # Library section - native hubs enabled by default (compare sectionIds)
                    is_enabled = (hub_source_key == section_key if hub_source_key is not None else False)
            hub_states[catalog_id] = (is_enabled, hub_info)

        # Helper to create option entry
        def make_option(catalog_id, hub_info, is_enabled, position=None):
            base_title = hub_info.get('title', catalog_id)
            if 'collection' in hub_info.get('identifier', ''):
                base_title = u'{} ({})'.format(base_title, T(32382, 'Collection'))
            source_label = hub_info.get('source_section_title', T(32411, 'Unknown'))
            if position is not None:
                display_title = u'{}. {} [{}]'.format(position, base_title, source_label)
            else:
                display_title = u'{} [{}]'.format(base_title, source_label)
            indicator = 'script.plex/indicators/circle-19.png' if is_enabled else ''
            return {
                'key': 'toggle_hub',
                'catalog_id': catalog_id,
                'identifier': hub_info.get('identifier', catalog_id),
                'hub_info': hub_info,
                'enabled': is_enabled,
                'display': display_title,
                'indicator': indicator,
                'has_submenu': is_enabled,
            }

        # Show enabled hubs first, in their configured order
        options = []
        enabled_hubs_shown = set()
        if has_custom_config and configured_hubs:
            for idx, hub_config in enumerate(configured_hubs):
                cat_id = hub_config.get('catalog_id', hub_config.get('identifier'))
                if cat_id in hub_states:
                    is_enabled, hub_info = hub_states[cat_id]
                    if is_enabled:
                        options.append(make_option(cat_id, hub_info, True, position=idx + 1))
                        enabled_hubs_shown.add(cat_id)
        else:
            # No custom config - show enabled hubs in ACTUAL SCREEN ORDER from sectionHubs
            ordered_catalog_ids = []
            cached_hubs = self.sectionHubs.get(section_key, [])
            is_home = section_key is None
            for hub in cached_hubs:
                identifier = hub.getCleanHubIdentifier(is_home=is_home)
                if is_home:
                    catalog_id = identifier
                else:
                    catalog_id = self.foreignCatalogId(section_key, identifier)
                if catalog_id in hub_states:
                    is_enabled, hub_info = hub_states[catalog_id]
                    if is_enabled:
                        ordered_catalog_ids.append((catalog_id, hub_info))
            for idx, (catalog_id, hub_info) in enumerate(ordered_catalog_ids):
                options.append(make_option(catalog_id, hub_info, True, position=idx + 1))
                enabled_hubs_shown.add(catalog_id)

        # Separator between enabled and disabled hubs
        if options:
            options.append(dropdown.SEPARATOR)

        # Group remaining hubs by source section
        hubs_by_source = {}
        for catalog_id, (is_enabled, hub_info) in hub_states.items():
            if catalog_id in enabled_hubs_shown:
                continue
            source = hub_info.get('source_section_title', T(32411, 'Unknown'))
            if source not in hubs_by_source:
                hubs_by_source[source] = []
            hubs_by_source[source].append((catalog_id, hub_info, is_enabled))

        # Sort sources: current section first, then Home, then alphabetically
        def source_sort_key(x):
            if str(x) == str(section_title):
                return (0, str(x))
            if str(x) == 'Home':
                return (1, str(x))
            return (2, str(x))

        sorted_sources = sorted(hubs_by_source.keys(), key=source_sort_key)
        for source in sorted_sources:
            if options and options[-1] != dropdown.SEPARATOR:
                options.append(dropdown.SEPARATOR)
            for catalog_id, hub_info, is_enabled in sorted(hubs_by_source[source], key=lambda x: x[1].get('title', '')):
                options.append(make_option(catalog_id, hub_info, is_enabled))

        # Reset and refresh options at the end
        options.append(dropdown.SEPARATOR)
        options.append({'key': 'refresh_hubs', 'display': T(34093, "Refresh Hub List")})
        options.append({'key': 'reset_hubs', 'display': T(34081, "Reset to Default")})

        return options

    def showHubSettingsDialog(self, section):
        """Show dialog to manage hubs for the given section."""

        # Store the sectionId (cacheKeyForSection) for use in the toggle callback
        # (self.lastSection might not be reliable during dialog interaction)
        self._managingHubsForSection = self.cacheKeyForSection(section)
        self._hubsSettingsChanged = False  # Track if any hubs were toggled

        # Lazy discovery - only fetch hubs when user actually opens Manage Hubs
        if not self.availableHubs:
            with busy.BusyContext(delay=True, delay_time=0.2):
                self._discoverHubsSync()
            if not self.availableHubs:
                return

        section_key = self.cacheKeyForSection(section)  # None for Home
        section_title = section.title if hasattr(section, 'title') else 'Home'
        self._managingHubsForSectionTitle = section_title

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key

        # Get current hub configuration for this section
        section_config = self.hubSettings.get(config_key, {}) if self.hubSettings else {}
        has_custom_config = section_config.get('custom', False)
        configured_hubs = section_config.get('hubs', []) if has_custom_config else []

        # Normalize CW identifiers in config to match the current mode, so Manage Hubs shows
        # the correct enabled state and _moveHubToPosition can find entries by catalog_id.
        if section_key is None and has_custom_config and configured_hubs:
            use_new_continue_watching = util.getSetting('hubs_use_new_continue_watching', False)
            configured_ids = {h.get('catalog_id', h.get('identifier')) for h in configured_hubs}
            if use_new_continue_watching and ('home.continue' in configured_ids or 'home.ondeck' in configured_ids) \
                    and 'continueWatching' not in configured_ids:
                # Old-style split hubs in config but new CW mode active: collapse to continueWatching
                old_entries = [h for h in configured_hubs
                               if h.get('catalog_id') in ('home.continue', 'home.ondeck')]
                min_order = min(h.get('order', 999) for h in old_entries)
                new_hubs = [h for h in configured_hubs
                            if h.get('catalog_id') not in ('home.continue', 'home.ondeck')]
                new_hubs.append({'catalog_id': 'continueWatching', 'order': min_order})
                new_hubs.sort(key=lambda h: h.get('order', 999))
                for i, h in enumerate(new_hubs):
                    h['order'] = i
                section_config['hubs'] = new_hubs
                self.saveHubSettings()
            elif not use_new_continue_watching and 'continueWatching' in configured_ids \
                    and 'home.continue' not in configured_ids and 'home.ondeck' not in configured_ids:
                # Combined hub in config but old CW mode active: expand to split hubs
                cw_entry = next(h for h in configured_hubs if h.get('catalog_id') == 'continueWatching')
                cw_order = cw_entry.get('order', 0)
                new_hubs = [h for h in configured_hubs if h.get('catalog_id') != 'continueWatching']
                new_hubs.append({'catalog_id': 'home.continue', 'order': cw_order})
                new_hubs.append({'catalog_id': 'home.ondeck', 'order': cw_order + 0.5})
                new_hubs.sort(key=lambda h: h.get('order', 999))
                for i, h in enumerate(new_hubs):
                    h['order'] = i
                section_config['hubs'] = new_hubs
                self.saveHubSettings()

        options = self._buildHubSettingsOptions(section_key, section_title)
        if not options:
            return

        try:
            choice = dropdown.showDropdown(
                options,
                pos=(460, 200),
                close_direction='none',
                set_dropdown_prop=False,
                with_indicator=True,
                header=T(34082, "Manage Hubs: {}").format(section_title),
                align_items="left",
                close_only_with_back=True,
                options_callback=self.onHubSettingToggle,
                suboption_callback=self._hubSubOptionCallback,
                dialog_props=self.carriedProps,
                move_mode_callback=self._onHubMoveCallback,
            )
        except Exception as e:
            util.ERROR('Hub Settings: Error showing dropdown: {}'.format(e))
            return

        # Refresh the home screen after dialog closes if any changes were made
        if self._hubsSettingsChanged:
            str_last_key = str(self.lastSection.key) if self.lastSection and self.lastSection.key is not None else None
            str_section_key = str(section_key) if section_key is not None else None
            if self.lastSection and (str_last_key == str_section_key or self.lastSection.key == section_key):
                self.showHubs(self.lastSection, update=False, force=True)

    def _hubSubOptionCallback(self, choice):
        """Return sub-menu options for an enabled hub, or None if no sub-menu needed."""
        if choice.get('key') != 'toggle_hub' or not choice.get('enabled'):
            return None  # No sub-menu for disabled hubs or Reset button

        catalog_id = choice.get('catalog_id')
        section_key = getattr(self, '_managingHubsForSection', None)

        can_move_up, can_move_down = self._canMoveHub(catalog_id, section_key)
        can_move = can_move_up or can_move_down

        options = []
        if can_move:
            options.append({'key': 'move', 'display': T(34089, 'Move')})
        options.append({'key': 'disable', 'display': T(34085, 'Disable')})
        return options

    def onHubSettingToggle(self, optionsList, mli):
        """Callback when a hub is toggled in the settings dialog."""
        choice = mli.dataSource
        if not choice:
            return

        # Handle Refresh Hub List - re-discover hubs from server and rebuild list
        if choice.get('key') == 'refresh_hubs':
            section_key = getattr(self, '_managingHubsForSection', self.lastSection.key)
            section_title = getattr(self, '_managingHubsForSectionTitle', '')
            self._discoverHubsSync()
            options = self._buildHubSettingsOptions(section_key, section_title)
            return ('rebuild', options, 0)

        # Handle Reset to Defaults - rebuild list in place
        if choice.get('key') == 'reset_hubs':
            section_key = getattr(self, '_managingHubsForSection', self.cacheKeyForSection(self.lastSection))
            section_title = getattr(self, '_managingHubsForSectionTitle', '')
            self.resetSectionHubs(section_key)
            self._hubsSettingsChanged = True
            options = self._buildHubSettingsOptions(section_key, section_title)
            return ('rebuild', options, 0)

        if choice.get('key') != 'toggle_hub':
            return

        catalog_id = choice.get('catalog_id', choice.get('identifier'))
        # Use the stored sectionId from when the dialog was opened
        section_key = getattr(self, '_managingHubsForSection', self.cacheKeyForSection(self.lastSection))
        is_currently_enabled = choice.get('enabled', False)

        # If hub is currently enabled, show Move/Disable sub-menu
        if is_currently_enabled:
            # Ensure custom config exists before any move/disable action
            config_created = self._ensureCustomConfigExists(section_key)
            if config_created:
                self._refreshHubSettingsDialog(optionsList, section_key)

            sub = choice.get('sub')  # Set by _hubSubOptionCallback framework
            if not sub:
                return None  # User cancelled sub-menu

            if sub.get('key') == 'move':
                # Enter pick-and-place move mode (via sub-menu — don't eat next SELECT)
                self._movingHubCatalogId = catalog_id
                self._movingHubSectionKey = section_key
                self._movingHubOptionsList = optionsList
                return 'enter_move_mode_sub'

            elif sub.get('key') == 'disable':
                focus_pos = optionsList.getSelectedPos()
                self._disableHub(catalog_id, section_key)
                self._hubsSettingsChanged = True
                section_title = getattr(self, '_managingHubsForSectionTitle', '')
                options = self._buildHubSettingsOptions(section_key, section_title)
                return ('rebuild', options, focus_pos)

            return None  # Stay open
        else:
            new_enabled = True


        # section_key is already a sectionId string (or None for Home)
        config_key = section_key

        # Update hubSettings
        if not self.hubSettings:
            self.hubSettings = {}

        # Check if this is first customization for this section
        need_init = config_key not in self.hubSettings or not self.hubSettings.get(config_key, {}).get('custom')

        if config_key not in self.hubSettings:
            self.hubSettings[config_key] = {'custom': False, 'hubs': []}

        section_config = self.hubSettings[config_key]

        if need_init:
            # First customization - initialize with default enabled hubs IN SCREEN ORDER
            # Use sectionHubs (actual display order) instead of availableHubs (discovery order)
            section_config['custom'] = True
            section_config['hubs'] = []
            is_home = section_key is None

            # Get hubs from sectionHubs in their actual display order
            cached_hubs = self.sectionHubs.get(section_key, [])

            # Add all native hubs in screen order (same logic for Home and libraries)
            for hub in cached_hubs:
                hub_identifier = hub.getCleanHubIdentifier(is_home=is_home)
                if is_home:
                    cat_id = hub_identifier
                else:
                    cat_id = '{}:{}'.format(section_key, hub_identifier)

                if cat_id in self.availableHubs:
                    section_config['hubs'].append({
                        'catalog_id': cat_id,
                        'identifier': hub_identifier,
                        'order': len(section_config['hubs'])
                    })

        # Find and update the hub in the config
        hub_found = False
        for hub_config in section_config['hubs']:
            config_cat_id = hub_config.get('catalog_id', hub_config.get('identifier'))
            if config_cat_id == catalog_id:
                hub_found = True
                if not new_enabled:
                    section_config['hubs'].remove(hub_config)
                break

        if new_enabled and not hub_found:
            hub_info = choice.get('hub_info', {})
            section_config['hubs'].append({
                'catalog_id': catalog_id,
                'identifier': hub_info.get('identifier', catalog_id),
                'order': len(section_config['hubs'])
            })

        self.saveHubSettings()
        self._hubsSettingsChanged = True

        focus_pos = optionsList.getSelectedPos()
        section_title = getattr(self, '_managingHubsForSectionTitle', '')
        options = self._buildHubSettingsOptions(section_key, section_title)
        return ('rebuild', options, focus_pos)

    def _onHubMoveCallback(self, action, mli, old_pos, new_pos):
        """Handle move mode callbacks from the dropdown dialog.

        Args:
            action: 'move', 'confirm', or 'cancel'
            mli: The ManagedListItem being moved
            old_pos: Original position (or position before this move)
            new_pos: New position (or target position)
        """
        section_key = getattr(self, '_movingHubSectionKey', None)
        catalog_id = getattr(self, '_movingHubCatalogId', None)
        optionsList = getattr(self, '_movingHubOptionsList', None)

        if action == 'move':
            # Update the underlying data order to match the visual order
            if catalog_id:
                self._moveHubToPosition(catalog_id, section_key, old_pos, new_pos, optionsList)
            # Don't clear references - more moves may follow
            return
        elif action == 'confirm':
            # Finalize the move - save settings and refresh display
            if optionsList:
                self._refreshHubSettingsDialog(optionsList, section_key)
            self.saveHubSettings()
            self._hubsSettingsChanged = True
        elif action == 'cancel':
            # Restore original position - the dropdown already moved the item back visually
            # We need to restore the data order as well
            if catalog_id and optionsList:
                self._restoreHubOrder(section_key, optionsList)

        # Clear move mode references only on confirm/cancel, not on move
        self._movingHubCatalogId = None
        self._movingHubSectionKey = None
        self._movingHubOptionsList = None

    def _moveHubToPosition(self, catalog_id, section_key, from_visual_pos, to_visual_pos, optionsList):
        """Move a hub from one visual position to another in the settings.

        The visual position directly maps to the config index for enabled hubs since
        both lists have enabled hubs in order starting from position 0.
        """
        if not self.hubSettings or from_visual_pos == to_visual_pos:
            return

        config_key = section_key
        section_config = self.hubSettings.get(config_key)
        if not section_config or not section_config.get('custom'):
            return

        hubs = section_config.get('hubs', [])

        # Visual position maps directly to config index for enabled hubs
        from_idx = from_visual_pos
        to_idx = to_visual_pos

        # Clamp to valid range
        if from_idx < 0 or from_idx >= len(hubs):
            return
        if to_idx < 0 or to_idx >= len(hubs):
            return

        # Remove the hub from its current position and insert at new position
        hub = hubs.pop(from_idx)
        hubs.insert(to_idx, hub)

        # Update order values
        for idx, hub_config in enumerate(hubs):
            hub_config['order'] = idx

    def _restoreHubOrder(self, section_key, optionsList):
        """Restore hub order from saved settings after a cancelled move."""
        # Reload settings and refresh the display
        self.loadHubSettings()
        if optionsList:
            self._refreshHubSettingsDialog(optionsList, section_key)

    def _disableHub(self, catalog_id, section_key):
        """Disable a hub by removing it from the enabled list."""
        if not self.hubSettings:
            return

        config_key = section_key
        section_config = self.hubSettings.get(config_key)
        if not section_config or not section_config.get('custom'):
            return

        hubs = section_config.get('hubs', [])
        for hub_config in hubs[:]:  # Iterate over a copy
            if hub_config.get('catalog_id') == catalog_id:
                hubs.remove(hub_config)
                break

        # Update order values
        for idx, hub_config in enumerate(hubs):
            hub_config['order'] = idx

        self.saveHubSettings()

    def _ensureCustomConfigExists(self, section_key):
        """Ensure custom hub config exists for a section, initializing with defaults if needed.
        Returns True if config was just created, False if it already existed."""
        if not self.hubSettings:
            self.hubSettings = {}

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key

        if config_key in self.hubSettings and self.hubSettings[config_key].get('custom'):
            return False  # Already has custom config

        # Initialize with defaults
        if config_key not in self.hubSettings:
            self.hubSettings[config_key] = {'custom': False, 'hubs': []}

        section_config = self.hubSettings[config_key]
        section_config['custom'] = True
        section_config['hubs'] = []

        # Build config in SCREEN ORDER (from sectionHubs) to match what user sees
        is_home = config_key is None
        cached_hubs = self.sectionHubs.get(section_key, [])

        # Add all native hubs in screen order (same logic for Home and libraries)
        for hub in cached_hubs:
            hub_identifier = hub.getCleanHubIdentifier(is_home=is_home)
            if is_home:
                cat_id = hub_identifier
            else:
                cat_id = self.foreignCatalogId(section_key, hub_identifier)

            section_config['hubs'].append({
                'catalog_id': cat_id,
                'identifier': hub_identifier,
                'order': len(section_config['hubs'])
            })

            # Backfill availableHubs so _buildHubSettingsOptions can display this hub
            if cat_id not in self.availableHubs:
                source_title = T(32332, 'Home')
                source_type = 'home'
                if section_key is not None:
                    source_section = self.allSections.get(section_key)
                    if source_section:
                        source_title = str(source_section.title)
                        source_type = str(source_section.type)

                self.availableHubs[cat_id] = {
                    'catalog_id': str(cat_id),
                    'identifier': str(hub_identifier),
                    'title': str(hub.title) if hub.title else PLAYLIST_HUB_TITLES.get(hub_identifier, hub_identifier),
                    'hubIdentifier': str(hub.hubIdentifier) if hub.hubIdentifier else hub_identifier,
                    'source_section_key': section_key,
                    'source_section_title': source_title,
                    'source_section_type': source_type,
                    'native_display': self.TYPE_TO_DISPLAY.get(hub.items[0].type, 'poster') if hub.items else 'poster',
                    'item_count': len(hub.items) if hub.items else 0,
                }

        self.saveHubSettings()
        self._hubsSettingsChanged = True
        return True

    def _canMoveHub(self, catalog_id, section_key):
        """Check if a hub can move up or down in the order."""
        # section_key is already a sectionId string (or None for Home)
        config_key = section_key

        if self.hubSettings:
            section_config = self.hubSettings.get(config_key)
            if section_config and section_config.get('custom'):
                hubs = section_config.get('hubs', [])
                if len(hubs) <= 1:
                    return False, False

                # Find the hub's current position
                current_idx = None
                for idx, hub_config in enumerate(hubs):
                    if hub_config.get('catalog_id') == catalog_id:
                        current_idx = idx
                        break

                if current_idx is None:
                    return False, False

                can_move_up = current_idx > 0
                can_move_down = current_idx < len(hubs) - 1
                return can_move_up, can_move_down

        # No custom config yet - fall back to sectionHubs count.
        # _ensureCustomConfigExists will create the config when the user picks Move,
        # so we just need to know whether moving is possible at all.
        cached_hubs = self.sectionHubs.get(section_key, [])
        can_move = len(cached_hubs) > 1
        return can_move, can_move

    def _moveHubInOrder(self, catalog_id, section_key, direction):
        """Move a hub up (-1) or down (+1) in the order."""
        if not self.hubSettings:
            return

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        section_config = self.hubSettings.get(config_key)
        if not section_config or not section_config.get('custom'):
            return

        hubs = section_config.get('hubs', [])

        # Find the hub's current position
        current_idx = None
        for idx, hub_config in enumerate(hubs):
            if hub_config.get('catalog_id') == catalog_id:
                current_idx = idx
                break

        if current_idx is None:
            return

        new_idx = current_idx + direction
        if new_idx < 0 or new_idx >= len(hubs):
            return

        # Swap the hubs
        hubs[current_idx], hubs[new_idx] = hubs[new_idx], hubs[current_idx]

        # Update order values
        for idx, hub_config in enumerate(hubs):
            hub_config['order'] = idx

        self.saveHubSettings()
        self._hubsSettingsChanged = True


    def _refreshHubSettingsDialog(self, optionsList, section_key):
        """Refresh the hub settings dropdown to reflect new order."""
        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        # Get the current hub configuration
        section_config = self.hubSettings.get(config_key, {}) if self.hubSettings else {}
        has_custom_config = section_config.get('custom', False)
        configured_hubs = section_config.get('hubs', []) if has_custom_config else []

        # Build a map of catalog_id to order for enabled hubs (only when custom config exists)
        enabled_order = {}
        for idx, hub_config in enumerate(configured_hubs):
            cat_id = hub_config.get('catalog_id', hub_config.get('identifier'))
            enabled_order[cat_id] = idx + 1  # 1-based position for display

        # Update each item in the options list
        for mli in optionsList:
            ds = mli.dataSource
            if not ds or ds.get('key') != 'toggle_hub':
                continue

            catalog_id = ds.get('catalog_id', ds.get('identifier'))
            hub_info = ds.get('hub_info', {})
            hub_source_key = hub_info.get('source_section_key')
            hub_identifier = hub_info.get('identifier', '')

            if has_custom_config:
                # Custom config: enabled if in the configured list
                is_enabled = catalog_id in enabled_order
            else:
                # Default state: all native hubs for the current section are enabled
                if section_key is None:
                    # Home section - all native Plex Home hubs enabled
                    is_enabled = (hub_source_key is None)
                else:
                    # Library section - native hubs enabled by default
                    is_enabled = (hub_source_key == section_key if hub_source_key is not None else False)

            # Update enabled state
            ds['enabled'] = is_enabled
            indicator = 'script.plex/indicators/circle-19.png' if is_enabled else ''
            mli.setProperty('indicator', indicator)
            mli.setThumbnailImage(indicator)

            # Update display to show position for enabled hubs (only with custom config)
            base_title = hub_info.get('title', catalog_id)
            source_label = hub_info.get('source_section_title', T(32411, 'Unknown'))

            if has_custom_config and is_enabled:
                position = enabled_order[catalog_id]
                display_title = u'{}. {} [{}]'.format(position, base_title, source_label)
            else:
                display_title = u'{} [{}]'.format(base_title, source_label)

            ds['display'] = display_title
            mli.setLabel(display_title)

    def resetSectionHubs(self, section_key):
        """Reset hub configuration for a section to defaults."""
        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        if self.hubSettings and config_key in self.hubSettings:
            del self.hubSettings[config_key]
            self.saveHubSettings()

    def hasCrossSectionHubs(self, section_key):
        """Check if a section has any cross-section hubs configured."""
        required = self.getRequiredSourceSections(section_key)
        for source in required:
            if source != section_key:
                return True
        return False

    def getRequiredSourceSections(self, section_key):
        """Get list of source section keys needed for this section's custom hub config."""
        required = set()

        if not self.hubSettings:
            return required

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        section_config = self.hubSettings.get(config_key)
        if not section_config or not section_config.get('custom'):
            return required

        for hub_config in section_config.get('hubs', []):
            catalog_id = hub_config.get('catalog_id', '')
            source_key, _ = self.parseCatalogId(catalog_id)
            required.add(source_key)

        return required

    def getEnabledHubsForSection(self, section_key):
        """Get list of enabled hub catalog_ids for a section."""
        if not self.hubSettings:
            return None

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        section_config = self.hubSettings.get(config_key)
        if not section_config or not section_config.get('custom'):
            return None

        enabled = {h.get('catalog_id', h.get('identifier')) for h in section_config.get('hubs', [])}

        # When CW mode changes, the hub identifiers change but saved config may have old ones.
        # Map between them so hubs stay enabled after switching modes.
        if section_key is None:  # Home section only
            use_new_continue_watching = util.getSetting('hubs_use_new_continue_watching', False)
            if use_new_continue_watching:
                if 'home.continue' in enabled or 'home.ondeck' in enabled:
                    enabled.add('continueWatching')
            else:
                if 'continueWatching' in enabled:
                    enabled.add('home.continue')
                    enabled.add('home.ondeck')

        return enabled

    def getCombinedHubsForSection(self, section, include_cross_section=True):
        """Get combined list of hubs for a section, including cross-section hubs if enabled."""
        section_key = self.cacheKeyForSection(section)
        is_home = section_key is None

        # Get native hubs for this section
        native_hubs = self.sectionHubs.get(section_key)
        if native_hubs is None:
            return None

        # Check if we have custom config with cross-section hubs
        if not include_cross_section:
            return native_hubs

        # section_key is already a sectionId string (or None for Home)
        config_key = section_key
        section_config = None
        if self.hubSettings:
            section_config = self.hubSettings.get(config_key)

        if not section_config or not section_config.get('custom'):
            # No custom config - show native hubs from Plex as-is
            return native_hubs

        # Get enabled hub catalog_ids
        enabled_catalog_ids = self.getEnabledHubsForSection(section_key)
        if enabled_catalog_ids is None:
            return native_hubs

        # Get required source sections
        required_sources = self.getRequiredSourceSections(section_key)

        # Check if all required source sections are cached
        missing_sources = []
        for source_key in required_sources:
            if source_key != section_key and self.sectionHubs.get(source_key) is None:
                missing_sources.append(source_key)

        if missing_sources:
            self.fetchMissingSections(missing_sources)
            # Filter native hubs based on enabled list while waiting
            filtered_native = []
            for hub in native_hubs:
                clean_id = hub.getCleanHubIdentifier(is_home=is_home)
                if section_key is None:
                    catalog_id = clean_id
                else:
                    catalog_id = self.foreignCatalogId(section_key, clean_id)
                if catalog_id in enabled_catalog_ids:
                    hub._crossSectionSource = section_key
                    hub._catalogId = catalog_id
                    filtered_native.append(hub)
            result = HubsList(filtered_native)
            result.identifier = section_key
            result.lastUpdated = native_hubs.lastUpdated
            result.invalid = native_hubs.invalid
            return result

        # Combine hubs from all required sources
        combined = []
        seen_identifiers = set()

        for source_key in required_sources:
            source_hubs = self.sectionHubs.get(source_key) or []
            source_is_home = source_key is None

            for hub in source_hubs:
                clean_id = hub.getCleanHubIdentifier(is_home=source_is_home)

                if source_key is None:
                    catalog_id = clean_id
                else:
                    catalog_id = self.foreignCatalogId(source_key, clean_id)

                if catalog_id not in enabled_catalog_ids:
                    continue

                if catalog_id in seen_identifiers:
                    continue
                seen_identifiers.add(catalog_id)

                hub._crossSectionSource = source_key
                hub._catalogId = catalog_id
                combined.append(hub)

        # Sort by user's configured order
        configured_hubs = section_config.get('hubs', [])
        catalog_id_to_order = {h.get('catalog_id', h.get('identifier')): i for i, h in enumerate(configured_hubs)}

        # When CW mode changes, map order between old/new identifiers so user ordering is preserved.
        if section_key is None:  # Home section only
            use_new_continue_watching = util.getSetting('hubs_use_new_continue_watching', False)
            if use_new_continue_watching:
                if 'home.continue' in catalog_id_to_order and 'continueWatching' not in catalog_id_to_order:
                    catalog_id_to_order['continueWatching'] = catalog_id_to_order['home.continue']
                elif 'home.ondeck' in catalog_id_to_order and 'continueWatching' not in catalog_id_to_order:
                    catalog_id_to_order['continueWatching'] = catalog_id_to_order['home.ondeck']
            else:
                if 'continueWatching' in catalog_id_to_order:
                    cw_order = catalog_id_to_order['continueWatching']
                    if 'home.continue' not in catalog_id_to_order:
                        catalog_id_to_order['home.continue'] = cw_order
                    if 'home.ondeck' not in catalog_id_to_order:
                        catalog_id_to_order['home.ondeck'] = cw_order + 0.5

        def get_order(hub):
            cat_id = getattr(hub, '_catalogId', None)
            if cat_id and cat_id in catalog_id_to_order:
                return catalog_id_to_order[cat_id]
            return 999

        combined.sort(key=get_order)


        result = HubsList(combined)
        result.identifier = section_key
        result.lastUpdated = native_hubs.lastUpdated
        result.invalid = native_hubs.invalid


        return result

    def fetchMissingSections(self, section_keys):
        """Trigger background fetch for missing section hubs."""
        # Use sections from sectionList to avoid expensive network call
        sections_by_key = {None: home_section, 'playlists': playlists_section}
        if hasattr(self, 'sectionList') and self.sectionList:
            for mli in self.sectionList:
                if mli.dataSource and hasattr(mli.dataSource, 'key'):
                    sections_by_key[self.cacheKeyForSection(mli.dataSource)] = mli.dataSource

        # Also include hidden libraries so cross-section hubs can still be fetched
        if hasattr(self, 'allSections'):
            for key, section_obj in self.allSections.items():
                if key not in sections_by_key:
                    sections_by_key[key] = section_obj

        for section_key in section_keys:
            section_obj = sections_by_key.get(section_key)

            if section_obj is None or getattr(section_obj, 'offline', False):
                continue

            already_fetching = False
            for task in self.tasks:
                if hasattr(task, 'section') and self.cacheKeyForSection(task.section) == section_key:
                    already_fetching = True
                    break

            if already_fetching:
                continue

            task = SectionHubsTask().setup(section_obj, self.crossSectionHubsCallback, self.wantedSections)
            self.tasks.append(task)
            backgroundthread.BGThreader.addTask(task)

    def _refreshCrossSectionSources(self, section_key):
        """Refresh library sections that feed cross-section hubs into the given section.

        When a section is refreshed (e.g. by tick staleness), getCombinedHubsForSection
        pulls cross-section hubs from other sections' caches. If those caches are stale,
        the cross-section hubs show old data. This method ensures source sections are
        also refreshed so fresh data is available when the section is rendered.
        """
        required_sources = self.getRequiredSourceSections(section_key)
        if not required_sources:
            return

        tasks_to_add = []

        for source_key in required_sources:
            if source_key == section_key:
                continue  # Skip the section itself — already being refreshed

            # Check if source section hubs are stale
            source_hubs = self.sectionHubs.get(source_key)

            if source_hubs is not None and time.time() - source_hubs.lastUpdated <= HUBS_REFRESH_INTERVAL:
                continue  # Source is still fresh

            # Find the section object
            section_obj = self.allSections.get(source_key) if hasattr(self, 'allSections') else None
            if section_obj is None or getattr(section_obj, 'offline', False):
                continue

            # Mark as refreshing so we don't double-fetch
            if source_hubs is not None:
                source_hubs.lastUpdated = time.time()

            task = SectionHubsTask().setup(section_obj, self.crossSectionHubsCallback, self.wantedSections)
            self.tasks.append(task)
            tasks_to_add.append((task, source_key))

        # Set counter BEFORE adding tasks to BGThreader — a fast-completing task
        # could call crossSectionHubsCallback before we set the counter, leaving
        # it permanently too high so Home never redraws.
        self._pendingCrossSources = len(tasks_to_add)
        for task, _ in tasks_to_add:
            backgroundthread.BGThreader.addTask(task)

        if tasks_to_add:
            util.DEBUG_LOG('Refreshing cross-section sources for {}: {}',
                           'Home' if section_key is None else section_key,
                           [s for _, s in tasks_to_add])

    def crossSectionHubsCallback(self, section, hubs, reselect_pos_dict=None):
        """Callback for cross-section hub fetches."""
        try:
            with self.lock:
                is_home = section.key is None

                sorted_hubs = HubsList(self.sortHubsByUserOrder(hubs, is_home=is_home, section_key=self.cacheKeyForSection(section)))
                sorted_hubs.lastUpdated = hubs.lastUpdated
                sorted_hubs.invalid = hubs.invalid

                ck = self.cacheKeyForSection(section)
                self.sectionHubs[ck] = sorted_hubs

                # Decrement pending cross-section source counter
                pending = getattr(self, '_pendingCrossSources', 0)
                if pending > 0:
                    self._pendingCrossSources = pending - 1

                # Trigger redisplay if needed
                if self.lastSection:
                    should_redisplay = False

                    # Check if this section is required for custom config
                    required = self.getRequiredSourceSections(self.cacheKeyForSection(self.lastSection))
                    str_section_key = self.cacheKeyForSection(section)
                    if str_section_key in required:
                        should_redisplay = True

                    # Also redisplay if we're on Home with default settings (no custom config)
                    # and a library section was just fetched (for per-library Recently Added hubs)
                    if self.lastSection.key is None and section.key is not None:
                        section_config = self.hubSettings.get(None) if self.hubSettings else None
                        has_custom = section_config and section_config.get('custom')
                        if not has_custom:
                            should_redisplay = True

                    # Fallback: Also redisplay if the current section has custom hub config
                    # This ensures cross-section hubs are shown even if required_sources check fails
                    if not should_redisplay and self.lastSection.key is not None:
                        config_key = self.cacheKeyForSection(self.lastSection)
                        section_config = self.hubSettings.get(config_key) if self.hubSettings else None
                        if section_config and section_config.get('custom'):
                            should_redisplay = True

                    if should_redisplay:
                        if self.lastSection.key is None:
                            # Defer Home drawing until all cross-section sources complete
                            if self._pendingCrossSources == 0:
                                home_hubs = self.sectionHubs.get(None)
                                if home_hubs is not None:
                                    self.showHubs(self.lastSection, update=bool(home_hubs))
                            # else: wait for remaining sources
                        else:
                            self.showHubs(self.lastSection, update=False)
        except Exception:
            util.ERROR("Error in crossSectionHubsCallback")

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
        plexapp.util.APP.on('change:path_mapping_indicators', self.setDirty)
        plexapp.util.APP.on('change:hub_season_thumbnails', self.setDirty)
        plexapp.util.APP.on('change:use_watchlist', self.setDirty)
        plexapp.util.APP.on('change:hubs_linear', self.onLinearHubsChanged)
        plexapp.util.APP.on('change:hubs_use_new_continue_watching', self.onContinueWatchingModeChanged)
        plexapp.util.APP.on('change:force_pd_mapping', self.setHostsDirty)
        plexapp.util.APP.on('change:debug', self.setDebugFlag)
        plexapp.util.APP.on('change:update_source', self.updateSourceChanged)
        plexapp.util.APP.on('watchlist:modified', self.watchlistDirty)
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
        plexapp.util.APP.off('change:path_mapping_indicators', self.setDirty)
        plexapp.util.APP.off('change:hub_season_thumbnails', self.setDirty)
        plexapp.util.APP.off('change:use_watchlist', self.setDirty)
        plexapp.util.APP.off('change:hubs_linear', self.onLinearHubsChanged)
        plexapp.util.APP.off('change:force_pd_mapping', self.setHostsDirty)
        plexapp.util.APP.off('change:debug', self.setDebugFlag)
        plexapp.util.APP.off('change:update_source', self.updateSourceChanged)
        plexapp.util.APP.off('watchlist:modified', self.watchlistDirty)
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


    def doUpdate(self):
        self._shuttingDown = True
        self._ignoreTick = True
        self.stopRetryingRequests()

        self.closeOption = "update"
        self.unhookSignals()
        self.doClose()
        return True


    def service_responder(self):
        if util.getGlobalProperty('notify_update'):
            is_downgrade = bool(util.getGlobalProperty('update_is_downgrade', consume=True))
            self.showBusy(False)
            button = optionsdialog.show(
                T(33670, 'Update available'),
                T(33671, 'Current: {current_version}\nNew: {new_version}\n\nChangelog:\n{changelog}').format(
                    current_version=util.ADDON.getAddonInfo('version'),
                    new_version=util.getGlobalProperty('update_available'),
                    changelog=util.getGlobalProperty('update_changelog'),
                ),
                T(33683, 'Exit, download and install'),
                T(33684, 'Later') if not is_downgrade else T(32329, 'No'),
                delay_buttons=1.8, big=True, close_timeout=3600
            )
            if button == 0:
                resp = "commence"
            else:
                resp = "cancel"
            util.setGlobalProperty('update_response', resp, wait=True)
            util.setGlobalProperty('notify_update', '', wait=True)

            if resp == "commence":
                # wait for it to be consumed
                try:
                    util.waitForConsumption('update_response', timeout=200)
                except Exception:
                    pass
                return self.doUpdate()

    def tick(self):
        if self._shuttingDown:
            util.DEBUG_LOG("Home: Not ticking, shutdown flag set")
            return

        if self.movingSection:
            util.DEBUG_LOG("Home: Not ticking, currently moving a section")
            return

        if self.is_active and self.service_responder():
            util.DEBUG_LOG("Home: Not ticking, service responder signalled positive exit")
            return

        if self.is_active and self._updateSourceChanged:
            util.setGlobalProperty('update_source_changed', self._updateSourceChanged, wait=True)
            self._updateSourceChanged = False

        if not self.lastSection or self._ignoreTick:
            return

        hubs = self.sectionHubs.get(self.cacheKeyForSection(self.lastSection))
        if hubs is None:
            return

        now = time.time()
        playing = xbmc.Player().isPlayingVideo()

        if (self.is_active and not self._checkingForExit and now - hubs.lastUpdated > HUBS_REFRESH_INTERVAL and
                not playing):
            util.DEBUG_LOG("Home: Ticking, section stale, calling showHubs(update=True)")
            self.showHubs(self.lastSection, update=True)
            util.cleanupCacheFolder()

        if (not playing and util.getSetting('periodic_reachability_check', False) and
                now - self._lastReachabilityCheck > REACHABILITY_CHECK_INTERVAL):
            self._lastReachabilityCheck = now
            plexapp.SERVERMANAGER.periodicReachabilityCheck()

        # re-probe mapped roots, otherwise a share that comes back keeps its red dot until
        # the next full home refresh
        if (not playing and self._pathMappingTargets and
                now - self._lastPathMappingProbe > PATH_MAPPING_PROBE_INTERVAL):
            self.startPathMappingProbe()

    def doClose(self, force=True):
        util.DEBUG_LOG("Home: doClose called, triggering close.windows")
        plexapp.util.APP.trigger('close.windows')

        #if self.sectionChangeThread and self.sectionChangeThread.isAlive():
        #    self.sectionChangeThread.join(timeout=2.0)

        super(HomeWindow, self).doClose(force=force)

    def stopRetryingRequests(self, state=True):
        util.DEBUG_LOG("{} request retries", state and "Disabling" or "Enabling")
        plexnet.asyncadapter.STOP_RETRYING_REQUESTS = state

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

        # belt: any user input ends the post-go_root hold window early
        if self._goRootHoldUntil:
            self._goRootHoldUntil = 0

        try:
            if self._skipNextAction:
                util.DEBUG_LOG("Home: Skipping next action")
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
                elif self.isWatchedAction(action):
                    self.toggleWatched(controlID)
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
                    if util.getSetting('disable_exit_on_back', False):
                        return
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
                            self.doClose()
                            return
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
        # within the 150ms hold window after go_root, any non-section-list focus event is the
        # stray Kodi fires when HOME reactivates with its previously-focused control still
        # recorded. Snap it back and consume the deadline so user input (which arrives well
        # after the window closes) passes through unblipped.
        if (time.time() < self._goRootHoldUntil
                and 100 < controlID < 500 and controlID != self.SECTION_LIST_ID):
            self._goRootHoldUntil = 0
            self.setFocusId(self.SECTION_LIST_ID)
            return

        if controlID != 204 and controlID < 500:
            # don't store focus for mini music player
            self.lastFocusID = controlID

        if 399 < controlID < 500:
            self.setProperty('hub.focus', str(self.hubFocusIndexes[controlID - 400]))

        if self.movingSection:
            return

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

    def toggleWatched(self, controlID=None, item=None, state=None):
        if not controlID and not item:
            return

        if controlID:
            control = self.hubControls[controlID - 400]
            mli = control.getSelectedItem()
            if not mli:
                return

            if mli.dataSource is None:
                return
            item = mli.dataSource

        if super(HomeWindow, self).toggleWatched(item, state=state) is None:
            return

        if item.isFullyWatched:
            ref = item.show() if item.TYPE in ('episode', 'season') else item
            removeFromWatchlistBlind(ref.guid, ref)
        self._updateOnDeckHubs()


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
        #    tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections)
        #             for s in [self.lastSection] + list(sections) if not s.server.DEFER_HUBS and s != self.lastSection]
        #else:
        # fetch hubs we need to update
        rp = self.getCurrentHubsPositions(self.lastSection)
        tasks = [UpdateHubTask().setup(hub, self.updateHubCallback,
                                       reselect_pos=rp.get(hub.getCleanHubIdentifier(not self.lastSection or self.lastSection.key is None)))
                 for hub in self.updateHubs.values()]
        self.tasks += tasks
        backgroundthread.BGThreader.addTasks(tasks)

    def showBusy(self, on=True):
        self.setProperty('busy', on and '1' or '')

    def setDirty(self, *args, **kwargs):
        self._reloadOnReinit = True
        self.cacheSpoilerSettings()

    def setHostsDirty(self, *args, **kwargs):
        self._recheckPD = True
        self.setDirty()

    def watchlistDirty(self, *args, **kwargs):
        # mark watchlist hub dirty
        if watchlist_section:
            hubs = self.sectionHubs.get(self.cacheKeyForSection(watchlist_section))
            if hubs:
                util.DEBUG_LOG("Home: Setting watchlist hubs dirty")
                hubs.lastUpdated = time.time() - HUBS_REFRESH_INTERVAL - 1

    def setThemeDirty(self, *args, **kwargs):
        self._applyTheme = util.getSetting("theme")

    def onLinearHubsChanged(self, *args, **kwargs):
        """Handle change in Linear Hubs setting - clear all hub caches and re-fetch."""
        try:
            # Clear hub caches for all sections since random hubs can appear anywhere
            self.sectionHubs.clear()

            self._reloadOnReinit = True

            if self.lastSection:
                self.showHubs(self.lastSection, force=True)
        except Exception as e:
            util.ERROR("Error in onLinearHubsChanged: {}".format(e))

    def onContinueWatchingModeChanged(self, *args, **kwargs):
        """Handle change in Continue Watching mode (combined vs separate hubs)."""
        try:

            # Clear the Home section hub cache (key None)
            if None in self.sectionHubs:
                del self.sectionHubs[None]

            # Clear the server's currentHubs cache
            server = plexapp.SERVERMANAGER.selectedServer
            if server:
                server.currentHubs = {}

            # Clear the available hubs cache so Manage Hubs shows updated options
            self.availableHubs = {}

            # Mark for reload and trigger refresh if we're on Home
            self._reloadOnReinit = True

            # If currently showing Home, refresh immediately with force=True
            # to ensure fresh hub fetch from server with new continue watching mode
            if self.lastSection and self.lastSection.key is None:
                self.showHubs(self.lastSection, force=True)
        except Exception as e:
            util.ERROR("Error in onContinueWatchingModeChanged: {}".format(e))

    def setDebugFlag(self, *args, **kwargs):
        util.DEBUG = util.getSetting("debug")
        util.addonSettings.debug = util.DEBUG

    def fullyRefreshHome(self, *args, **kwargs):
        section = kwargs.pop("section", None)
        self.showSections(focus_section=section or home_section)
        self.backgroundSet = False
        # Don't call showHubs() here — showSections() just cleared sectionHubs,
        # so there's nothing to draw. Let background tasks call showHubs() via
        # sectionHubsCallback when data actually arrives.

    def disableUpdates(self, *args, **kwargs):
        util.LOG("Sleep event, stopping updates")
        self._ignoreTick = True

    def enableUpdates(self, *args, **kwargs):
        util.LOG("Wake event, resuming updates")
        self._ignoreTick = False

    def refreshLastSection(self, *args, **kwargs):
        self.enableUpdates()
        if not xbmc.Player().isPlayingVideo() and not self._shuttingDown and self.is_active:
            util.LOG("Refreshing last section after wake events")
            self.showHubs(self.lastSection, force=True, update=True)

    def onWake(self, *args, **kwargs):
        if util.getSetting('periodic_reachability_check', False):
            self._lastReachabilityCheck = time.time()
            plexapp.SERVERMANAGER.periodicReachabilityCheck()

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
            if plexapp.SERVERMANAGER.selectedServer:
                self.loadLibrarySettings()
                self.loadHubSettings()
                # Clear hub catalog on server change - will be discovered lazily when needed
                self.availableHubs = {}
            if not plexapp.SERVERMANAGER.selectedServer:
                self.setFocusId(self.USER_BUTTON_ID)
                return False

            self.fullyRefreshHome(section=section)
            if section is not None:
                for mli in self.sectionList:
                    if mli.dataSource and self._sameRailSection(mli.dataSource, section):
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
            util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
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
            # All hubs default to text2lines=True now
            return dict(
                ('hub.text2lines.4{0:02d}'.format(i), '1') for i, hubCtrl in enumerate(self.hubControls) if
                hubCtrl.dataSource)

    def sectionPinnedTypes(self, section):
        """Item types this library has pinned to the top bar as views of their own."""
        if not self.librarySettings or isinstance(section, PinnedTypeSection):
            return []

        # playlists and the watchlist are plain virtual sections without a TYPE
        pinnable = PINNABLE_TYPES.get(str(getattr(section, 'TYPE', None)), ())
        ck = self.cacheKeyForSection(section)
        stored = self.librarySettings.get(ck, {}).get('pinned_types') or []
        return [t for t in stored if t in pinnable]

    def setSectionPinned(self, section, item_type, pinned):
        ck = self.cacheKeyForSection(section)
        settings = self.librarySettings.setdefault(ck, {})
        types = [t for t in settings.get('pinned_types') or [] if t != item_type]
        if pinned:
            types.append(item_type)
        settings['pinned_types'] = types
        self.saveLibrarySettings()

    def sectionMenu(self):
        item = self.sectionList.getSelectedItem()
        if not item or not item.getProperty('item'):
            return

        section = item.dataSource
        choice = None
        if isinstance(section, PinnedTypeSection):
            choice = dropdown.showDropdown(
                [{'key': 'unpin', 'display': T(35045, "Unpin collections from the top bar")},
                 {'key': 'move', 'display': T(33039, "Move")}],
                pos=(660, 441),
                close_direction='none',
                set_dropdown_prop=False,
                header=T(33030, 'Choose action for: {}').format(section.title),
                select_index=0,
                align_items="left",
                dialog_props=self.carriedProps
            )

        elif not section.key:
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
                ck = self.cacheKeyForSection(s)
                section_settings = self.librarySettings.get(ck)
                if section_settings and not section_settings.get("show", True):
                    options.append({'key': 'show',
                                    'section_id': ck,
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

            # Add Manage Hubs and Refresh Hubs options
            if options:
                options.append(dropdown.SEPARATOR)
            options.append({'key': 'manage_hubs', 'display': T(34080, "Manage Hubs")})
            options.append({'key': 'refresh_hubs', 'display': T(34096, "Refresh Hubs")})

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

            if 'collection' in PINNABLE_TYPES.get(str(getattr(section, 'TYPE', None)), ()) \
                    and 'collection' not in self.sectionPinnedTypes(section):
                options.append({'key': 'pin_collections',
                                'display': T(35044, "Pin collections to the top bar")})

            options.append({'key': 'hide', 'display': T(33028, "Hide library")})
            options.append({'key': 'move', 'display': T(33039, "Move")})

            if section not in (watchlist_section, playlists_section):
                if self.isSectionPinnedToHome(section):
                    options.append({'key': 'unpin_from_home', 'display': T(35071, "Remove from home")})
                else:
                    options.append({'key': 'pin_to_home', 'display': T(35070, "Pin to home")})

            options.append(dropdown.SEPARATOR)

            if 'libraries' in util.getSetting('cache_requests') and section != watchlist_section:
                options.append({'key': 'section_cache_reset', 'display': T(33721, "Clear library cache (not items)")})
                options.append(dropdown.SEPARATOR)

            # Add Manage Hubs and Refresh Hubs options (not applicable to watchlist)
            if section != watchlist_section:
                options.append(dropdown.SEPARATOR)
                options.append({'key': 'manage_hubs', 'display': T(34080, "Manage Hubs")})
                options.append({'key': 'refresh_hubs', 'display': T(34096, "Refresh Hubs")})

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
        elif choice["key"] == "pin_collections":
            self.setSectionPinned(section, 'collection', True)
            return section
        elif choice["key"] == "unpin":
            self.setSectionPinned(section.librarySection, section.itemType, False)
            return section.librarySection
        elif choice["key"] == "hide":
            ck = self.cacheKeyForSection(section)
            if ck not in self.librarySettings:
                self.librarySettings[ck] = {}
            self.librarySettings[ck]['show'] = False
            self.saveLibrarySettings()
            return self.sectionList[self.sectionList.prev()].dataSource
        elif choice["key"] == "show":
            if "section_id" in choice:
                if choice["section_id"] in self.librarySettings:
                    self.librarySettings[choice["section_id"]]['show'] = True
                    self.saveLibrarySettings()
                    return self.lastSection
        elif choice["key"] == "move":
            self.sectionMover(item, "init")
        elif choice["key"] == "pin_to_home":
            self.pinForeignLibrary(
                server_uuid=section.server.uuid,
                section_key=section.key,
                server_name=section.server.name or '',
                section_title=section.title)
            return section
        elif choice["key"] == "unpin_from_home":
            self.unpinForeignLibrary(
                server_uuid=section.server.uuid,
                section_key=section.key)
            return section
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

        elif choice["key"] == "manage_hubs":
            self.showHubSettingsDialog(section)
            # Don't return lastSection - showHubSettingsDialog handles refresh internally
            # Returning a section would trigger serverRefresh which cancels background tasks
            # and clears availableHubs, breaking cross-section hub fetches
            return

        elif choice["key"] == "refresh_hubs":
            self.showHubs(self.lastSection, force=True, update=True)
            return

    def hubMenu(self, hubControlID):
        hub = self.currentHub
        if not hub:
            return

        control = self.hubControls[hubControlID - 400]
        mli = control.getSelectedItem()
        if not mli:
            return

        if mli.dataSource is None or mli.dataSource is kodigui.DUMMY_DATA_SOURCE:
            return

        ds = mli.dataSource

        # Determine the hub's source section and catalog_id
        is_home = not self.lastSection or self.lastSection.key is None
        cross_source = hub.__dict__.get('_crossSectionSource')
        hub_source_key = cross_source if cross_source is not None else self.lastSection.key
        hub_is_home = hub_source_key is None
        clean_identifier = hub.getCleanHubIdentifier(is_home=hub_is_home)

        # Build catalog_id for Manage Hubs integration
        if hub_is_home:
            catalog_id = clean_identifier
        else:
            catalog_id = '{}:{}'.format(hub_source_key, clean_identifier)

        hub_title = hub.__dict__.get('_displayTitle') or hub.title or clean_identifier

        select_base = 0

        options = []
        has_prev = False
        is_watchlist = self.lastSection == watchlist_section
        # Don't allow disabling/adding hubs for watchlist or main CW/On Deck hubs
        if not is_watchlist and hub.hubIdentifier not in ("continueWatching", "home.continue", "home.ondeck"):
            options.append({'key': 'disable_hub', 'display': T(33659, "Disable Hub: {}").format(hub_title)})
            has_prev = True

            # Offer "Add to Home" when viewing a library section (not Home)
            if not is_home:
                # Check if this hub is already on Home
                home_config = self.hubSettings.get(None, {}) if self.hubSettings else {}
                home_hubs = home_config.get('hubs', []) if home_config.get('custom') else []
                already_on_home = any(h.get('catalog_id') == catalog_id for h in home_hubs)
                if not already_on_home:
                    options.append({'key': 'add_to_home', 'display': 'Add to Home: {}'.format(hub_title)})

        if ds.TYPE in ('episode', 'season', 'movie', 'show'):
            if has_prev:
                options.append(dropdown.SEPARATOR)

            has_mp = False
            if not mli.getProperty('watched'):
                options.append({'key': 'mark_watched', 'display': T(32319, "Mark Played")})
                select_base = has_prev and 1 or 0
                has_mp = True

            if ds.isFullyWatched or ds.isWatched or ds.viewedLeafCount.asInt() > 0:
                options.append({'key': 'mark_unwatched', 'display': T(32318, "Mark Unplayed")})
                select_base = has_prev and 1 or has_mp and 0
                has_mp = True

            if ds.TYPE in ('episode', 'movie'):
                if (hub.hubIdentifier in ("continueWatching", "home.continue", "home.ondeck") or
                        clean_identifier in ("tv.inprogress", "movie.inprogress")):
                    # allow removing items from CW / On Deck
                    options.append(dropdown.SEPARATOR)
                    options.append({'key': 'remove_cw', 'display': T(33662, "Remove from Continue Watching")})
                    if not has_mp:
                        select_base = 1
                if util.getSetting('home_inprogress_resume') and ds.in_progress:
                    # this is an in progress item that would be auto resumed; add specific entry to visit media instead
                    options.insert(0, dropdown.SEPARATOR)
                    options.insert(1, {'key': 'start_over', 'display': T(32317, 'Play from beginning')})
                    options.insert(2, {'key': 'to_item', 'display': T(33019, "Visit media item")})
                    select_base = 1
                elif ds.in_progress:
                    options.insert(0, dropdown.SEPARATOR)
                    options.insert(1, {'key': 'start_over', 'display': T(32317, 'Play from beginning')})
                    options.insert(2, {'key': 'resume', 'display': T(32429, "Resume from {}").format(util.timeDisplay(ds.viewOffset.asInt()).lstrip('0').lstrip(':'))})


            if ds.TYPE in ('episode', 'season'):
                options.append(dropdown.SEPARATOR)
                options.append({'key': 'to_show', 'display': T(32323, "Go To Show")})
                if ds.TYPE == 'episode':
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

        elif choice["key"] == "disable_hub":
            # Disable hub via Manage Hubs settings (same as disabling in the dialog)
            section_key = self.lastSection.key
            self._ensureCustomConfigExists(section_key)
            self._disableHub(catalog_id, section_key)
            self.showHubs(self.lastSection, update=False, force=True)
            return

        elif choice["key"] == "add_to_home":
            # Add this hub to Home as a cross-section hub
            self._ensureCustomConfigExists(None)  # None = Home section
            home_config = self.hubSettings.get(None, {})
            hubs_list = home_config.get('hubs', [])
            # Add at the end
            new_order = max((h.get('order', 0) for h in hubs_list), default=-1) + 1
            hubs_list.append({'catalog_id': catalog_id, 'order': new_order})
            self.saveHubSettings()
            return

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
                self.toggleWatched(item=ds, state=True)

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

            ds.removeFromContinueWatching()
            self._updateOnDeckHubs()

        elif choice["key"] in ("to_season", "to_show"):
            target = ds.show() if choice["key"] == "to_show" else ds.season()
            try:
                command = opener.open(target, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
                return

        elif choice["key"] == "to_item":
            try:
                command = opener.open(ds, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
                return

        elif choice["key"] == "start_over":
            try:
                command = opener.open(ds, auto_play=True, start_over=True, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
                return
            return

        elif choice["key"] == "resume":
            try:
                command = opener.open(ds, auto_play=True, dialog_props=self.carriedProps)
                if command == "NODATA":
                    raise util.NoDataException
            except util.NoDataException:
                util.ERROR("No data - deleted or server disconnected?", notify=True, time_ms=5000)
                return
            return

        elif choice["key"] == "cache_reset":
            try:
                util.DEBUG_LOG('Clearing requests cache for {}...', ds)
                ds.clearCache()
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
            self.sectionList.selectItem(next_index)

        elif action == xbmcgui.ACTION_SELECT_ITEM:
            stop_moving()
            # store section order
            self.librarySettings["order"] = [self.cacheKeyForSection(i.dataSource) for i in self.sectionList.items if i.dataSource]
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
                            util.MONITOR.waitFor()

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
        self.setProperty('user.avatar', plexapp.ACCOUNT.safeUserThumb(plexapp.ACCOUNT.ID,
                                                                      thumb=plexapp.ACCOUNT.thumb))
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
        while any(self.tasks) and waited < util.MONITOR.waitAmount(2):
            if waited > 5:
                self.showBusy(True)
            util.MONITOR.waitFor()
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
            while not util.MONITOR.waitFor():
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
                util.MONITOR.waitFor()

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
            ck = self.cacheKeyForSection(section)
            update = bool(self.sectionHubs.get(ck))
            is_home = section.key is None

            # Sort hubs: user-defined order > server order
            sorted_hubs = HubsList(self.sortHubsByUserOrder(hubs, is_home=is_home, section_key=self.cacheKeyForSection(section)))
            sorted_hubs.lastUpdated = hubs.lastUpdated
            sorted_hubs.invalid = hubs.invalid
            sorted_hubs.identifier = hubs.identifier

            self.sectionHubs[ck] = sorted_hubs
            self.setBoolProperty('loading.content', False)

            on_home = self.lastSection and self.lastSection.key is None
            has_cross = self.hasCrossSectionHubs(None) if on_home else False

            if is_home:
                if has_cross:
                    # Cross-section hubs need library data — defer drawing until all sources complete
                    pending_libs = getattr(self, '_pendingLibrarySections', -1)
                    pending_cross = getattr(self, '_pendingCrossSources', 0)
                    if pending_libs == 0 and pending_cross == 0:
                        # All sources already done, draw now
                        self.showHubs(section, update=update, reselect_pos_dict=reselect_pos_dict)
                    # else: wait for library/cross-section tasks to finish
                else:
                    # No cross-section hubs — draw immediately
                    self.showHubs(section, update=update, reselect_pos_dict=reselect_pos_dict)
            else:
                # Library section completed
                if self.lastSection == section:
                    # User is viewing this library section — draw it
                    self.showHubs(section, update=update, reselect_pos_dict=reselect_pos_dict)

                # Track library section completion. A pinned view is not a library and feeds
                # no cross-section hub, so counting it here would let Home draw before the
                # libraries its hubs are built from have arrived.
                if not isinstance(section, PinnedTypeSection):
                    pending = getattr(self, '_pendingLibrarySections', 0)
                    if pending > 0:
                        self._pendingLibrarySections = pending - 1

                    # When all libraries are done and we're on Home with cross-section hubs, draw once
                    if self._pendingLibrarySections == 0 and on_home and has_cross:
                        if self.sectionHubs.get(None) is not None:
                            self.showHubs(self.lastSection, update=False)

    def updateHubCallback(self, hub, items=None, reselect_pos=None):
        with self.lock:
            # First, find and update the hub in its source section's sectionHubs
            hub_source_section = None
            # Collect section keys already checked via sectionList
            checked_keys = set()
            for mli in self.sectionList:
                section = mli.dataSource
                if not section:
                    continue

                ck = self.cacheKeyForSection(section)
                checked_keys.add(ck)
                hubs = self.sectionHubs.get(ck, ())
                if not hubs:
                    continue

                for idx, ihub in enumerate(hubs):
                    if ihub == hub:
                        hubs[idx] = hub
                        hub_source_section = section
                        break
                if hub_source_section:
                    break

            # If not found, check sectionHubs for hidden sections not in sectionList
            # (e.g., hidden Playlists section providing cross-section hubs)
            if not hub_source_section:
                for section_key, section_hubs in self.sectionHubs.items():
                    if section_key in checked_keys or not section_hubs:
                        continue
                    for idx, ihub in enumerate(section_hubs):
                        if ihub == hub:
                            section_hubs[idx] = hub
                            hub_source_section = True
                            break
                    if hub_source_section:
                        break

            if not hub_source_section:
                util.DEBUG_LOG('Hub {0} not found in any sectionHubs'.format(hub.hubIdentifier))
                return

            # Now check if this hub is currently displayed (either on its own section
            # or as a cross-section hub on the current section like Home)
            # Check by looking for the hub in hubControls
            hub_slot_index = None
            for slot_idx, hubCtrl in enumerate(self.hubControls):
                if hubCtrl.dataSource == hub:
                    hub_slot_index = slot_idx
                    break

            if hub_slot_index is not None:
                # Hub is currently displayed - determine correct is_home flag
                # Use the hub's cross-section source if set, otherwise use lastSection
                cross_source = hub.__dict__.get('_crossSectionSource') if '_crossSectionSource' in hub.__dict__ else "__UNDEF__"
                if cross_source != "__UNDEF__":
                    is_home = cross_source is None
                else:
                    is_home = self.lastSection.key is None if self.lastSection else False

                util.DEBUG_LOG('Hub {0} updated - refreshing (slot {1}, is_home={2})'.format(
                    hub.hubIdentifier, hub_slot_index, is_home))
                self.showHub(hub, items=items, reselect_pos=reselect_pos,
                             is_home=is_home, hub_index=hub_slot_index)
            else:
                util.DEBUG_LOG('Hub {0} updated but not currently displayed'.format(hub.hubIdentifier))

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
        self.allSections = {}  # All libraries including hidden, for cross-section hub fetching
        for section in _sections:
            ck = self.cacheKeyForSection(section)
            self.allSections[ck] = section
            if ck in self.librarySettings and not self.librarySettings[ck].get("show", True):
                self.anyLibraryHidden = True
                continue
            sections.append(section)
            self.wantedSections.append(section.key)

        # add the item-type views pinned to the top bar next to the library they belong to
        pinned = []
        for section in sections:
            pinned.append(section)
            for item_type in self.sectionPinnedTypes(section):
                pinned.append(PinnedTypeSection(section, item_type))
        sections = pinned

        # foreign libraries resolved once (network); merged into the rail render order
        # below so a moved foreign library keeps its saved position across restart.
        # They stay out of the cross-section hub pipeline, which only handles locals.
        foreign_sections = self.foreignRailSections()
        self._kickForeignResolution()
        for fs in foreign_sections:
            self.allSections[self.cacheKeyForSection(fs)] = fs

        hub_sections = list(sections)

        # sort libraries (locals + foreign merge for render order)
        if "order" in self.librarySettings:
            sections = self._orderRailSections(
                sections, foreign_sections, self.librarySettings["order"])
        else:
            sections = sections + foreign_sections

        # speedup if we don't have any hidden libraries
        if not self.anyLibraryHidden:
            self.wantedSections = None

        if plexapp.SERVERMANAGER.selectedServer.hasHubs():
            # Include hidden sections that are needed for cross-section hubs.
            # Pinned item-type views share their library's hubs, so they're never fetched.
            fetch_sections = [s for s in hub_sections if not isinstance(s, PinnedTypeSection)]
            required_sources = self.getRequiredSourceSections(None)  # Home's required sources
            for source_key in required_sources:
                if source_key and source_key in self.allSections:
                    if not any(self.cacheKeyForSection(s) == source_key for s in fetch_sections):
                        fetch_sections.append(self.allSections[source_key])

            self.tasks = [SectionHubsTask().setup(s, self.sectionHubsCallback, self.wantedSections)
                          for s in [home_section] + fetch_sections if not s.server.DEFER_HUBS]
            # Track pending library sections for cross-section hub rendering. Pinned views
            # are not hub sources for anything, so they're counted nowhere and fetched apart.
            self._pendingLibrarySections = len([s for s in fetch_sections if not s.server.DEFER_HUBS])
            self.tasks += [PinnedTypeHubsTask().setup(s, self.sectionHubsCallback)
                           for s in hub_sections if isinstance(s, PinnedTypeSection)
                           and not s.server.DEFER_HUBS]
            backgroundthread.BGThreader.addTasks(self.tasks)

        self.scheduleForeignHubFetches(foreign_sections)

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
            elif isinstance(section, PinnedTypeSection):
                # no icon of its own; it keeps the library's type icon
                mli.setProperty('is.pinned.type', section.itemType)
            elif isinstance(section, ForeignLibrarySection) or getattr(section, 'is_foreign', None):
                mli.setProperty('is.foreign', '1')
            if pmm.mapping:
                # a mapping that doesn't work is an error rather than decoration, so it shows
                # even when the indicator setting is off
                mli.setBoolProperty('is.mapped.broken', section.mappingBroken)
                if show_pm_indicator:
                    mli.setBoolProperty('is.mapped', section.isMapped)
            items.append(mli)

        self.bottomItem = len(items) - 1

        for x in range(len(items), 8):
            mli = kodigui.ManagedListItem()
            items.append(mli)

        self.lastSection = focus_section or home_section
        self.sectionList.reset()
        self.sectionList.addItems(items)

        if pmm.mapping:
            self.startPathMappingProbe(sections)

        if not focus_section:
            if items:
                self.setFocusId(self.SECTION_LIST_ID)
            else:
                self.setFocusId(self.SERVER_BUTTON_ID)
        else:
            self.setFocusId(self.SECTION_LIST_ID)

    def startPathMappingProbe(self, sections=None):
        if sections is not None:
            targets = []
            seen = set()
            for section in sections:
                server_name = section.server and section.server.name
                if not server_name:
                    continue

                for map_path in section.mappedPaths:
                    if (server_name, map_path) in seen:
                        continue
                    seen.add((server_name, map_path))
                    targets.append((server_name, map_path, section.title))
            self._pathMappingTargets = targets

        if not self._pathMappingTargets:
            return

        self._lastPathMappingProbe = time.time()
        task = PathMappingProbeTask().setup(self._pathMappingTargets, self.pathMappingProbeCallback)
        self.tasks.append(task)
        backgroundthread.BGThreader.addTask(task)

    def pathMappingProbeCallback(self):
        with self.lock:
            for mli in self.sectionList:
                section = mli.dataSource
                if section is None:
                    continue
                mli.setBoolProperty('is.mapped.broken', section.mappingBroken)

    def showHubs(self, section=None, update=False, force=False, reselect_pos_dict=None):
        # Single choke point for all hub drawing. The lock (RLock) makes every
        # entry point — background callbacks AND the wake/tick/reinit/click paths
        # that previously bypassed it — mutually exclusive, so two _showHubs()
        # passes can never mutate the same hub controls concurrently.
        with self.lock:
            self.setBoolProperty('no.content', False)
            if not update:
                self.setProperty('drawing', '1')
            try:
                self._showHubs(section=section, update=update, force=force, reselect_pos_dict=reselect_pos_dict)
            finally:
                self.setProperty('drawing', '')

    def getCurrentHubsPositions(self, section):
        is_home = not section or section.key is None
        rp = {}

        # Iterate through hub controls to find current positions
        for hubCtrl in self.hubControls:
            if not hubCtrl.dataSource:
                continue

            identifier = hubCtrl.dataSource.getCleanHubIdentifier(is_home=is_home)
            pos = hubCtrl.getSelectedPos()
            if pos is not None:
                mli = hubCtrl.getItemByPos(pos)
                if mli and mli.dataSource:
                    # continue/inprogress/ondeck hubs update their order after items have changed their state, skip those
                    if (identifier in ('continueWatching', 'continue', 'ondeck')
                            or identifier.endswith('.inprogress') or identifier.endswith('.ondeck')):
                        rp[identifier] = (str(mli.dataSource.ratingKey), 0)
                        continue
                    rp[identifier] = (str(mli.dataSource.ratingKey), pos)
        return rp

    @busy.busy_property()
    def _showHubs(self, section=None, update=False, force=False, reselect_pos_dict=None):
        if not update:
            self.clearHubs()

        if getattr(section, 'offline', False):
            # foreign placeholder: server is None, no hubs to fetch
            return

        if not section.server.DEFER_HUBS and not plexapp.SERVERMANAGER.selectedServer.hasHubs():
            return

        if section.key is False:
            return

        ck = self.cacheKeyForSection(section)
        hubs = self.sectionHubs.get(ck)
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
            # Cancel any in-flight UpdateHubTasks to prevent their callbacks
            # from racing with the full section refresh
            for task in self.tasks:
                if isinstance(task, UpdateHubTask) and not task.finished:
                    task.cancel()
            self.cleanTasks()

            rpd = self.getCurrentHubsPositions(section)

            if not update:
                if ck in self.sectionHubs:
                    self.sectionHubs[ck] = None
            if isinstance(section, PinnedTypeSection):
                task = PinnedTypeHubsTask().setup(section, self.sectionHubsCallback, reselect_pos_dict=rpd)
            else:
                task = SectionHubsTask().setup(section, self.sectionHubsCallback, self.wantedSections,
                                               reselect_pos_dict=rpd)
            self.tasks.append(task)
            backgroundthread.BGThreader.addTask(task)

            # Also refresh source library sections that feed cross-section hubs
            # into this section, otherwise getCombinedHubsForSection pulls stale data
            self._refreshCrossSectionSources(self.cacheKeyForSection(section))

            return

        util.DEBUG_LOG('Showing hubs - Section: {0} - Update: {1}', section.key, update)

        # Get combined hubs including cross-section hubs if configured
        combined_hubs = self.getCombinedHubsForSection(section)
        if combined_hubs is not None and len(combined_hubs) > 0:
            hubs = combined_hubs

        # Append library's name in cross section hubs
        is_home = section.key is None
        linear_hubs = util.getSetting('hubs_linear', False)
        for hub in hubs:
            hub.__dict__.pop('_displayTitle', None)  # Clear stale display titles
            source_key = hub.__dict__.get('_crossSectionSource') if '_crossSectionSource' in hub.__dict__ else "__UNDEF__"
            source_is_home = source_key is None
            if hub.title:
                if source_key is None and hub.hubIdentifier:
                    parts = hub.hubIdentifier.rsplit('.', 2)
                    if len(parts) >= 2 and parts[-2].isdigit():
                        source_key = parts[-2]
                if not source_is_home and source_key != "__UNDEF__" and section.key != source_key:
                    # hub's source is different to the current section
                    section_obj = self.allSections.get(str(source_key))
                    if section_obj and section_obj.title.lower() not in hub.title.lower():
                        hub._displayTitle = u'{} \u2014 {}'.format(hub.title, section_obj.title)
                elif source_is_home and not is_home:
                    # hub's source is Home
                    hub._displayTitle = u'{} \u2014 {}'.format(hub.title, T(32332, 'Home'))

            # Mark randomised hubs in the title when linear mode is off
            if hub.random == '1' and not linear_hubs:
                base_title = hub.__dict__.get('_displayTitle', hub.title)
                if base_title:
                    hub._displayTitle = u'{} (Random)'.format(base_title)

            # In linear mode, replace random hub items with sorted results from hub.key
            if hub.random == '1' and linear_hubs and hub.key:
                try:
                    hub.items = hub.extend(start=0, size=hub.size.asInt() or 10)
                except:
                    pass  # Fall back to the random items if re-fetch fails

        # Sequential slot assignment - hubs are assigned to slots in order
        # Display type is determined per-hub and set as a window property for the skin
        hasContent = False
        skip = {}
        displayed_count = 0
        hidden_count = 0
        hub_index = 0  # Sequential counter for slot assignment

        for hub in hubs:
            # Check if we've used all available slots
            if hub_index >= len(self.hubControls):
                break

            # For cross-section hubs, use the source section's is_home flag
            # Use __dict__.get() instead of hasattr() because PlexObject.__getattr__ can cause false positives
            cross_section_source = hub.__dict__.get('_crossSectionSource') if '_crossSectionSource' in hub.__dict__ else "__UNDEF__"
            hub_source_key = cross_section_source if cross_section_source != "__UNDEF__" else section.key
            hub_is_home = hub_source_key is None
            cross_is_home = cross_section_source is None
            identifier = hub.getCleanHubIdentifier(is_home=hub_is_home or cross_is_home)

            # Check if hub should be hidden (for native hubs not in combined list)
            # Use string comparison to handle potential int/string mismatches
            str_cross_source = str(cross_section_source) if cross_section_source != "__UNDEF__" else None
            str_section_key = str(section.key) if section.key is not None else None
            is_cross_section = str_cross_source is not None and str_cross_source != str_section_key

            if not is_cross_section:
                if self.isHubHidden(identifier, self.cacheKeyForSection(section)):
                    hidden_count += 1
                    continue

            # Skip hubs with no content - they don't take a slot, but will appear
            # automatically when they have content on the next refresh.
            # This prevents empty hubs from breaking the scroll animation chain.
            if not hub.items:
                continue

            # Determine display type for this hub and set as window property for skin
            display_type = self.getHubDisplayType(hub, identifier)
            self.setProperty('hub.display.4{0:02d}'.format(hub_index), display_type)

            skip[hub_index] = 1


            if self.showHub(hub, is_home=hub_is_home,
                            reselect_pos=reselect_pos_dict.get(identifier) if reselect_pos_dict else None,
                            hub_index=hub_index):
                displayed_count += 1
                if hub.items:
                    hasContent = True
                # All hubs with items get updates by default
                if hub.items:
                    self.updateHubs[identifier] = hub

            hub_index += 1


        if not hasContent:
            self.setBoolProperty('no.content', True)

        # store last visited hubslist identifier (e.g. section key or None for Home)
        self.lastHubs = hubs.identifier

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
                # `focus`/`lastSkip` are 0-based hub indices, NOT Kodi control IDs
                # (hub controls are 400+index). focusFirstValidHub() does the
                # conversion, verifies the target still has content, and falls back
                # to the section list. Passing the raw index straight to setFocusId()
                # targets a non-existent control and throws off the GUI thread, which
                # takes the whole window down when the focused hub empties out on an
                # update refresh - e.g. returning to the Watchlist after its last item
                # was auto-removed as watched.
                try:
                    self.focusFirstValidHub(focus)
                except Exception:
                    util.ERROR("Home: failed to restore focus after hub cleanup")
        self.storeLastBG()

    def showHub(self, hub, items=None, is_home=False, reselect_pos=None, hub_index=None):
        identifier = hub.getCleanHubIdentifier(is_home=is_home)

        if hub_index is None:
            return False

        # Get rendering flags based on hub identifier and content
        flags = self.getHubRenderFlags(hub, identifier)


        # Build kwargs from flags
        kwargs = {
            'index': hub_index,
            'with_progress': flags['with_progress'],
            'with_art': flags['with_art'],
            'ar16x9': flags['ar16x9'],
            'text2lines': flags['text2lines'],
        }
        self._showHub(hub, hubitems=items, reselect_pos=reselect_pos, identifier=identifier, **kwargs)
        return True

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
        mli = self.createGrandparentedListItem(obj, *(self.THUMB_AR16X9_DIM if wide else self.THUMB_POSTER_DIM))
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
        if wide:
            thumb = obj.defaultArt.asTranscodedImageURL(*self.THUMB_AR16X9_DIM)
        else:
            thumb = obj.defaultThumb.asTranscodedImageURL(*self.THUMB_POSTER_DIM)
        mli = kodigui.ManagedListItem(obj.defaultTitle, obj.year, thumbnailImage=thumb, data_source=obj)
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

    def createCollectionListItem(self, obj, wide=False):
        w, h = self.THUMB_POSTER_DIM
        # a collection often has no poster of its own; the library grid falls back to the
        # composite of its members, so match that here
        if obj.defaultThumb:
            thumb = obj.defaultThumb.asTranscodedImageURL(w, h)
        else:
            thumb = obj.server.getImageTranscodeURL(obj.artCompositeURL(w * 2, h * 2), w, h)

        mli = kodigui.ManagedListItem(obj.title or '', thumbnailImage=thumb, data_source=obj)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie.png')
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
        'playlist': createPlaylistListItem,
        'collection': createCollectionListItem
    }

    def createListItem(self, obj, wide=False):
        return self.CREATE_LI_MAP.get(obj.type, self.unhandledHub)(self, obj, wide)

    def clearHubs(self):
        self.updateHubs = {}
        for i, control in enumerate(self.hubControls):
            control.reset()
            # Clear display type property for this hub slot
            self.setProperty('hub.display.4{0:02d}'.format(i), '')

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

        display_title = hub.__dict__.get('_displayTitle') or hub.title or kwargs.get('title')
        self.setProperty('hub.4{0:02d}'.format(index), display_title)
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
            if obj.type == 'episode' and hub.hubIdentifier in ("continueWatching", "home.continue", "home.ondeck", "watchlist.continueWatching") and self.spoilerSetting != "off":
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

        if any([with_progress, with_art, ar16x9]):
            for mli in items:
                if with_progress:
                    mli.setProperty('progress', util.getProgressImage(mli.dataSource))
                if with_art:
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
                if last_pos < control.size() and self.updateBackgroundFrom(control[last_pos].dataSource):
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
                    if pos < control.size() and self.updateBackgroundFrom(control[pos].dataSource):
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
                if pos < control.size() and self.updateBackgroundFrom(control[pos].dataSource):
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

    def _reResolveForeignPlaceholders(self, server_uuid):
        """Upgrade placeholders for `server_uuid` to their live section.

        Uses the resolution cache when available (no network); falls back to a network
        resolve for records not resolved this session (e.g. a server that became
        reachable after startup). Returns True if any placeholder went live.
        """
        upgraded = False
        cache = getattr(self, '_foreignResolved', None) or {}
        for key, record in list(getattr(self, 'allSections', {}).items()):
            if not isinstance(record, ForeignLibrarySection):
                continue
            if record.server_uuid != server_uuid:
                continue
            cached = cache.get(record.sectionId)
            if cached is not None and not cached[1]:
                self.allSections[key] = cached[0]  # reuse cached live, no network
                upgraded = True
            else:
                resolved, offline = self.resolveForeignLibrary({
                    'server_uuid': record.server_uuid,
                    'section_key': record.section_key,
                    'server_name': record.server_name,
                    'section_title': record.section_title,
                })
                if not offline:
                    self.allSections[key] = resolved
                    upgraded = True
        return upgraded

    def onReachableServer(self, server=None, **kwargs):
        if server is not None and self._reResolveForeignPlaceholders(server.uuid):
            self.serverRefresh()
            return
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

            if plexapp.util.LOCAL_MODE:
                # local mode can only ever use servers with a plain LAN connection
                servers = [s for s in servers if s.hasLocalModeConnection()]

            items = []
            for s in servers:
                item = ServerListItem(s.name, not s.owned and s.owner or '', data_source=s)
                item.uuid = s.uuid
                item.onUpdate()
                if plexapp.SERVERMANAGER.selectedServer:
                    item.setProperty('current', plexapp.SERVERMANAGER.selectedServer.uuid == s.uuid and '1' or '')
                items.append(item)

            if len(items) > 1:
                items[0].setProperty('first', '1')
                items[-1].setProperty('last', '1')
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
            self.changingServer = False
            return


        with busy.BusySignalContext(plexapp.util.APP, "change:selectedServer") as bc:

            changed = plexapp.SERVERMANAGER.setSelectedServer(server, force=True)
            if not changed:
                bc.ignoreSignal = True
                self.changingServer = False
            else:
                util.setSetting('previous_server.{}'.format(plexapp.ACCOUNT.ID), prevUUID)

    def showUserMenu(self, mouse=False):
        items = []
        if util.getGlobalProperty("update_available"):
            items.append(kodigui.ManagedListItem(T(33670, 'Update available'), data_source='update'))
        if plexapp.ACCOUNT.isSignedIn:
            if not len(plexapp.ACCOUNT.homeUsers) and not util.addonSettings.cacheHomeUsers:
                plexapp.ACCOUNT.updateHomeUsers(refreshSubscription=True)

            if len(plexapp.ACCOUNT.homeUsers) > 1:
                items.append(kodigui.ManagedListItem(T(32342, 'Switch User'), data_source='switch'))
            else:
                items.append(kodigui.ManagedListItem(T(32980, 'Refresh Users'), data_source='refresh_users'))
        elif plexapp.ACCOUNT.isOffline and plexapp.util.LOCAL_MODE:
            from lib import localmode
            if len(plexapp.ACCOUNT.homeUsers) > 1:
                items.append(kodigui.ManagedListItem(T(32342, 'Switch User'), data_source='switch'))
            if localmode.isAccountLess():
                items.append(kodigui.ManagedListItem(T(35042, 'Local users'), data_source='local_users'))
        items.append(kodigui.ManagedListItem(T(32343, 'Settings'), data_source='settings'))
        if plexapp.ACCOUNT.isSignedIn:
            items.append(kodigui.ManagedListItem(T(35019, 'Go local'), data_source='go_local'))
            items.append(kodigui.ManagedListItem(T(32344, 'Sign Out'), data_source='signout'))
        elif plexapp.ACCOUNT.isOffline:
            if plexapp.util.LOCAL_MODE:
                items.append(kodigui.ManagedListItem(T(35020, 'Go online'), data_source='go_online'))
            else:
                items.append(kodigui.ManagedListItem(T(32459, 'Offline Mode'), data_source='go_online'))
        else:
            items.append(kodigui.ManagedListItem(T(32460, 'Sign In'), data_source='signin'))
        items.append(kodigui.ManagedListItem(T(32924, 'Minimize'), data_source='minimize'))
        items.append(kodigui.ManagedListItem(T(32336, 'Exit'), data_source='exit'))

        if len(items) > 1:
            items[0].setProperty('first', '1')
            items[-1].setProperty('last', '1')
        else:
            items[0].setProperty('only', '1')
        # somehow dynamically setting the list height here doesn't work. We need a height that's bigger than our
        # possible available items in the template

        self.userList.reset()
        self.userList.addItems(items)
        itemHeight = util.vscale(66, r=0)

        self.userList.setHeight((len(items) * itemHeight))
        self.getControl(self.USER_MENU_GROUP_ID).setHeight((len(items) * itemHeight))
        self.getControl(self.USER_MENU_BG_ID).setHeight((len(items) * itemHeight) + 80)

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
        elif option == 'update':
            self.setBoolProperty('show.options', False)
            self.showBusy()
            self.setFocusId(self.SECTION_LIST_ID)
            util.setGlobalProperty('update_requested', '1', wait=True)
        elif option == 'go_online':
            if plexapp.util.LOCAL_MODE:
                # leave local mode via a clean re-init (re-verifies the account or opens sign-in)
                self.closeOption = option
                kill_background()
                self.doClose()
                return
            plexapp.ACCOUNT.refreshAccount()
        elif option == 'refresh_users':
            plexapp.ACCOUNT.updateHomeUsers(refreshSubscription=True)
            return True
        elif option == 'local_users':
            from lib import localmode
            localmode.seedUsersFromServer(reselect=True)
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
        elif option == 'exit':
            self._shuttingDown = True
            util.DEBUG_LOG("Home: Initiating shutdown, setting background")
            background.setShutdown()
            self.closeOption = "exit"
            self.doClose()
            return
        elif option == 'minimize':
            self.storeLastBG()
            util.setGlobalProperty('is_active', '')
            xbmc.executebuiltin('ActivateWindow(10000)')
            return
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
