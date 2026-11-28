# coding=utf-8
from __future__ import absolute_import

import datetime

from kodi_six import xbmc
from kodi_six import xbmcgui

from lib import backgroundthread
from lib import util
from lib.util import T
from plexnet import util as plexnetUtil
from . import busy
from . import dropdown
from . import kodigui
from . import opener
from . import search
from . import windowutils

FILMOGRAPHY_PAGE_SIZE = 10
DISCOVER_HUB_SLOTS = 6
NOT_IN_LIBRARY_BATCH_SIZE = 10


class PersonDetailsTask(backgroundthread.Task):
    def __init__(self, role, callback):
        super(PersonDetailsTask, self).__init__()
        self.role = role
        self.callback = callback

    def run(self):
        if self.isCanceled():
            return
        details = self.role.getDetails()
        if not self.isCanceled():
            self.callback(details)


class PersonFilmographyTask(backgroundthread.Task):
    def __init__(self, role, media_type, callback, start=0, size=FILMOGRAPHY_PAGE_SIZE):
        super(PersonFilmographyTask, self).__init__()
        self.role = role
        self.media_type = media_type
        self.callback = callback
        self.start = start
        self.size = size

    def run(self):
        if self.isCanceled():
            return
        result = self.role.getFilmography(self.media_type, start=self.start, size=self.size)
        if not self.isCanceled():
            self.callback(result)


class ExtendFilmographyTask(backgroundthread.Task):
    def setup(self, role, start, size, callback, canceledCallback=None):
        self.role = role
        self.start = start
        self.size = size
        self.callback = callback
        self.canceledCallback = canceledCallback
        return self

    def run(self):
        if self.isCanceled():
            if self.canceledCallback:
                self.canceledCallback()
            return
        try:
            result = self.role.getFilmography(None, start=self.start, size=self.size)
            if self.isCanceled():
                if self.canceledCallback:
                    self.canceledCallback()
                return
            self.callback(result)
        except Exception as e:
            util.DEBUG_LOG('ExtendFilmographyTask failed: {0}'.format(e))
            if self.canceledCallback:
                self.canceledCallback()


class DiscoverItem(object):
    def __init__(self, credit_data):
        meta = credit_data.get('Metadata', {})
        self.title = meta.get('title', '')
        self.year = str(meta.get('year', ''))
        self.type = meta.get('type', 'movie')
        self.ratingKey = meta.get('ratingKey', '')
        self.guid = 'plex://{0}/{1}'.format(self.type, self.ratingKey)
        self.thumb = meta.get('thumb', '')
        self.art = meta.get('art', '')
        self.role = credit_data.get('role', '')
        self.order = credit_data.get('order', 999)
        self.is_discover = True


class DiscoverCreditsTask(backgroundthread.Task):
    def __init__(self, role, server, callback, credit_type=None):
        super(DiscoverCreditsTask, self).__init__()
        self.role = role
        self.server = server
        self.callback = callback
        self.credit_type = credit_type

    def run(self):
        if self.isCanceled():
            return

        credit_groups = self.role.getDiscoverCredits(credit_type=self.credit_type)
        if self.isCanceled() or not credit_groups:
            self.callback([], set())
            return

        discover_hubs = []
        all_guids = []

        for group_type, credits in credit_groups:
            group_items = []
            for credit in credits:
                item = DiscoverItem(credit)
                if item.ratingKey:
                    group_items.append(item)
                    all_guids.append(item.guid)
            if group_items:
                discover_hubs.append((group_type, group_items))

        if self.isCanceled():
            self.callback([], set())
            return

        unique_guids = list(set(all_guids))
        from plexnet import media as plexmedia
        library_guids = plexmedia.Role.checkLibraryPresence(self.server, unique_guids)

        if not self.isCanceled():
            self.callback(discover_hubs, library_guids)


class PersonWindow(kodigui.ControlledWindow, windowutils.UtilMixin):
    xmlFile = 'script-plex-person.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    THUMB_DIM = util.scaleResolution(300, 300)
    POSTER_DIM = util.scaleResolution(244, 361)

    FILMOGRAPHY_LIST_ID = 400
    DISCOVER_LIST_BASE_ID = 401
    DISCOVER_GROUP_BASE_ID = 501
    HOME_BUTTON_ID = 201
    SEARCH_BUTTON_ID = 202
    PLAYER_STATUS_BUTTON_ID = 204
    FILTER_BUTTON_ID = 300

    # Override in subclasses
    CREDIT_TYPE = None      # passed to getDiscoverCredits — None fetches all types
    PRIMARY_TYPE = 'actor'  # which credit group to use for filmography filtering
    TYPE_LABEL_ID = 32473   # strings.po ID for the role type label shown on screen

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.setProperty('loading', '1')
        self.role = kwargs.get('role')
        self.personDetails = None
        self.filmographyItems = []
        self.filmographyAllItems = []
        self.filmographyByGuid = {}
        self.filmographyFilter = None
        self.filmographyOffset = 0
        self.filmographyTotalSize = 0
        self.filmographyMore = False
        self.discoverListControls = []
        self.libraryGuids = set()
        self.tasks = backgroundthread.Tasks()
        self.exitCommand = None
        self.initialized = False

    def onFirstInit(self):
        self.setProperty('loading', '1')
        self.filmographyListControl = kodigui.ManagedControlList(self, self.FILMOGRAPHY_LIST_ID, 5)

        self.discoverListControls = []
        for i in range(DISCOVER_HUB_SLOTS):
            list_id = self.DISCOVER_LIST_BASE_ID + i
            try:
                control = kodigui.ManagedControlList(self, list_id, 5)
                self.discoverListControls.append(control)
            except Exception:
                break

        from plexnet import plexapp
        local_server = plexapp.SERVERMANAGER.selectedServer
        if local_server and self.role.server != local_server:
            self.role.server = local_server

        self.setProperty('person.name', self.role.tag or '')
        self.setProperty('person.type_label', T(self.TYPE_LABEL_ID, self.PRIMARY_TYPE.title()))
        self.setProperty('filmography.filter', T(32345, 'All'))
        if self.role.thumb:
            self.setProperty('person.thumb', self.role.thumb.asTranscodedImageURL(*self.THUMB_DIM))

        self.fetchPersonDetails()
        self.fetchFilmography()
        self.fetchDiscoverCredits()

        self.initialized = True

    def onReInit(self):
        pass

    def onAction(self, action):
        try:
            controlID = self.getFocusId()
            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                self.doClose()
                return

            if controlID == self.FILMOGRAPHY_LIST_ID:
                if self.checkFilmographyPagination(action):
                    return

        except Exception:
            util.ERROR()

        kodigui.ControlledWindow.onAction(self, action)

    def checkFilmographyPagination(self, action):
        mli = self.filmographyListControl.getSelectedItem()
        if not mli:
            return False
        if mli.getProperty('is.end') and not mli.getProperty('is.updating'):
            mli.setBoolProperty('is.updating', True)
            self.extendFilmography()
            return True
        return False

    def onClick(self, controlID):
        if controlID == self.HOME_BUTTON_ID:
            self.goHome()
        elif controlID == self.FILTER_BUTTON_ID:
            self.filterButtonClicked()
        elif controlID == self.FILMOGRAPHY_LIST_ID:
            self.filmographyItemClicked()
        elif controlID == self.SEARCH_BUTTON_ID:
            self.searchButtonClicked()
        elif controlID == self.PLAYER_STATUS_BUTTON_ID:
            self.showAudioPlayer()
        elif self.DISCOVER_LIST_BASE_ID <= controlID < self.DISCOVER_LIST_BASE_ID + DISCOVER_HUB_SLOTS:
            self.openDiscoverItem(controlID)

    def onFocus(self, controlID):
        if self.FILMOGRAPHY_LIST_ID <= controlID <= self.DISCOVER_LIST_BASE_ID + DISCOVER_HUB_SLOTS:
            self.setProperty('hub.focus', str(controlID - self.FILMOGRAPHY_LIST_ID))

        if controlID > self.FILMOGRAPHY_LIST_ID:
            self.setProperty('on.extras', '1')
        else:
            self.setProperty('on.extras', '')

    def doClose(self, **kw):
        self.tasks.kill()
        kodigui.ControlledWindow.doClose(self)

    def fetchPersonDetails(self):
        task = PersonDetailsTask(self.role, self.onPersonDetails)
        self.tasks.add(task)
        backgroundthread.BGThreader.addTask(task)

    def fetchFilmography(self):
        self.setProperty('loading', '1')
        task = PersonFilmographyTask(self.role, None, self.onFilmography, start=0, size=FILMOGRAPHY_PAGE_SIZE)
        self.tasks.add(task)
        backgroundthread.BGThreader.addTask(task)

    def extendFilmography(self):
        start = self.filmographyOffset + len(self.filmographyItems)
        task = ExtendFilmographyTask().setup(
            self.role,
            start=start,
            size=FILMOGRAPHY_PAGE_SIZE,
            callback=self.onFilmographyExtended,
            canceledCallback=self.onFilmographyExtendCanceled
        )
        self.tasks.add(task)
        backgroundthread.BGThreader.addTask(task)

    def onFilmographyExtendCanceled(self):
        for mli in self.filmographyListControl:
            if mli.getProperty('is.end'):
                mli.setBoolProperty('is.updating', False)
                break

    def onFilmographyExtended(self, result):
        items = result.get('items', [])
        self.filmographyMore = result.get('more', False)
        self.filmographyTotalSize = result.get('totalSize', 0)

        if not items:
            self.onFilmographyExtendCanceled()
            return

        self.filmographyAllItems.extend(items)

        newUniqueItems, newByGuid = self.groupFilmographyByGuid(items, existingByGuid=self.filmographyByGuid)
        self.filmographyItems.extend(newUniqueItems)

        newListItems = []
        for item in newUniqueItems:
            mli = self.createFilmographyListItem(item)
            newListItems.append(mli)

        if self.filmographyMore:
            end = kodigui.ManagedListItem('')
            end.setBoolProperty('is.end', True)
            newListItems.append(end)

        endPos = self.filmographyListControl.size() - 1
        self.filmographyListControl.replaceItem(endPos, newListItems[0])
        if len(newListItems) > 1:
            self.filmographyListControl.addItems(newListItems[1:])

        self.filmographyListControl.selectItem(endPos)
        self.setProperty('filmography.count', str(len(self.filmographyItems)))

    def onPersonDetails(self, details):
        if not details:
            util.DEBUG_LOG('PersonWindow: No details returned')
            return

        self.personDetails = details
        self.setProperty('person.name', details.get('name', ''))
        self.setProperty('person.summary', details.get('summary', ''))
        self.setProperty('person.birthPlace', details.get('birthPlace', ''))

        birthDate = details.get('birthDate', '')
        deathDate = details.get('deathDate', '')

        if birthDate:
            self.setProperty('person.birthDate', self.formatDate(birthDate))
            age = self.calculateAge(birthDate, deathDate)
            if age:
                self.setProperty('person.age', str(age))

        if deathDate:
            self.setProperty('person.deathDate', self.formatDate(deathDate))
            self.setProperty('person.deceased', '1')

        thumb = details.get('thumb', '')
        if thumb:
            self.setProperty('person.thumb', self.role.server.getImageTranscodeURL(thumb, *self.THUMB_DIM))

        tag_key = details.get('tagKey', '')
        if tag_key and not getattr(self.role, 'tagKey', None):
            self.role.tagKey = tag_key
            self.fetchDiscoverCredits()

    def fetchDiscoverCredits(self):
        if not hasattr(self.role, 'tagKey') or not self.role.tagKey:
            util.DEBUG_LOG('PersonWindow: No tagKey, skipping discover credits')
            return

        task = DiscoverCreditsTask(
            self.role, self.role.server, self.onDiscoverCredits,
            credit_type=self.CREDIT_TYPE
        )
        self.tasks.add(task)
        backgroundthread.BGThreader.addTask(task)

    def onDiscoverCredits(self, discover_hubs, library_guids):
        self.libraryGuids = library_guids

        slot = 0
        for group_type, items in discover_hubs:
            if slot >= DISCOVER_HUB_SLOTS:
                break
            not_in_library = [item for item in items if item.guid not in library_guids]
            if not_in_library:
                label = '{0} - {1}'.format(T(32479, 'Not in Library'), group_type.title())
                self.fillDiscoverHub(slot, not_in_library, label)
                slot += 1

        util.DEBUG_LOG('PersonWindow: Discover credits: {0} groups, {1} in library, {2} hubs populated',
                       len(discover_hubs), len(library_guids), slot)

        # Avoid focus trap: if filmography is empty but Discover hubs filled, move focus there
        if slot > 0 and self.filmographyListControl.size() == 0:
            self.setFocusId(self.DISCOVER_LIST_BASE_ID)

    def fillDiscoverHub(self, slot, items, label):
        if slot >= len(self.discoverListControls):
            return

        listControl = self.discoverListControls[slot]
        listItems = [self.createNotInLibraryListItem(item) for item in items]
        listControl.reset()
        listControl.addItems(listItems)
        self.setProperty('discover.hub.{0}.label'.format(slot), label)

    def createNotInLibraryListItem(self, item):
        mli = kodigui.ManagedListItem(
            item.title, item.year, thumbnailImage=item.thumb, data_source=item
        )
        mli.setProperty('media.type', item.type)
        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(
            'show' if item.type == 'show' else 'movie'))
        if item.role:
            mli.setProperty('role', item.role)
        return mli

    def openDiscoverItem(self, controlID):
        slot = controlID - self.DISCOVER_LIST_BASE_ID
        if slot < 0 or slot >= len(self.discoverListControls):
            return

        mli = self.discoverListControls[slot].getSelectedItem()
        if not mli or not mli.dataSource:
            return

        item = mli.dataSource
        if not item.ratingKey:
            return

        from plexnet import plexapp, util as pnUtil
        from plexnet.compat import quote_plus
        local_server = plexapp.SERVERMANAGER.selectedServer
        if local_server and item.guid in self.libraryGuids:
            try:
                # Resolve plex:// guid against the local PMS — getObject builds a proper PlexObject
                self.processCommand(opener.open(
                    '/library/metadata/{0}'.format(quote_plus(item.guid)), server=local_server))
                return
            except Exception as e:
                util.DEBUG_LOG('PersonWindow: Local open failed for {0}: {1}', item.guid, e)

        if pnUtil.LOCAL_MODE:
            util.DEBUG_LOG('PersonWindow: Not opening discover item in local mode')
            return

        discover_server = pnUtil.SERVERMANAGER.getDiscoverServer()
        if not discover_server:
            util.DEBUG_LOG('PersonWindow: No discover server available')
            return

        self.processCommand(opener.open(
            item.ratingKey,
            server=discover_server,
            from_watchlist=True,
            external_item=True
        ))

    def onFilmography(self, result):
        self.setProperty('loading', '')
        items = result.get('items', [])
        self.filmographyAllItems = items
        self.filmographyOffset = result.get('offset', 0)
        self.filmographyTotalSize = result.get('totalSize', len(items))
        self.filmographyMore = result.get('more', False)
        self.filmographyItems, self.filmographyByGuid = self.groupFilmographyByGuid(items)
        self.fillFilmography()

    def createFilmographyListItem(self, item):
        title = item.title if hasattr(item, 'title') else item.get('title', '')
        year = ''
        if hasattr(item, 'year'):
            year = str(item.year) if item.year else ''

        thumb = ''
        if hasattr(item, 'thumb') and item.thumb:
            thumb = item.thumb.asTranscodedImageURL(*self.POSTER_DIM)
        elif hasattr(item, 'defaultThumb') and item.defaultThumb:
            thumb = item.defaultThumb.asTranscodedImageURL(*self.POSTER_DIM)

        mli = kodigui.ManagedListItem(title, year, thumbnailImage=thumb, data_source=item)

        item_type = item.type if hasattr(item, 'type') else item.TYPE if hasattr(item, 'TYPE') else ''
        mli.setProperty('media.type', item_type)

        if hasattr(item, 'isWatched') and item.isWatched:
            mli.setProperty('watched', '1')

        mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(
            item_type in ('show', 'season', 'episode') and 'show' or 'movie'))

        return mli

    def fillFilmography(self):
        listItems = []
        for item in self.filmographyItems:
            mli = self.createFilmographyListItem(item)
            listItems.append(mli)

        if self.filmographyMore:
            end = kodigui.ManagedListItem('')
            end.setBoolProperty('is.end', True)
            listItems.append(end)

        self.filmographyListControl.reset()
        self.filmographyListControl.addItems(listItems)
        self.setProperty('filmography.count', str(len(self.filmographyItems)))

    def filterButtonClicked(self):
        options = [
            {'key': None,    'display': T(32345, 'All')},
            {'key': 'movie', 'display': T(32348, 'Movies')},
            {'key': 'show',  'display': T(32350, 'Shows')},
        ]
        choice = dropdown.showDropdown(
            options=options,
            pos=(560, 515),
            close_direction='none',
            set_dropdown_prop=False,
            align_items='left'
        )
        if choice is None:
            return
        self.filmographyFilter = choice['key']
        self.setProperty('filmography.filter', choice['display'])
        self.applyFilmographyFilter()

    def applyFilmographyFilter(self):
        self.filmographyAllItems = []
        self.filmographyItems = []
        self.filmographyByGuid = {}
        self.filmographyOffset = 0
        self.filmographyMore = False
        self.setProperty('loading', '1')
        # Filtered modes fetch all at once (smaller result set, no pagination offset mismatch)
        # "All" mode uses normal page size with pagination
        size = None if self.filmographyFilter else FILMOGRAPHY_PAGE_SIZE
        task = PersonFilmographyTask(self.role, self.filmographyFilter, self.onFilmography, start=0, size=size)
        self.tasks.add(task)
        backgroundthread.BGThreader.addTask(task)

    def filmographyItemClicked(self):
        mli = self.filmographyListControl.getSelectedItem()
        if not mli or not mli.dataSource:
            return

        item = mli.dataSource
        guid = self.getItemGuid(item)
        versions = self.filmographyByGuid.get(guid, [item]) if guid else [item]

        if len(versions) > 1:
            selectedItem = self.showVersionPicker(versions, item.type if hasattr(item, 'type') else 'movie')
            if selectedItem:
                self.processCommand(opener.open(selectedItem))
        else:
            self.processCommand(opener.open(item))

    def searchButtonClicked(self):
        self.processCommand(search.dialog(self))

    def formatDate(self, dateStr):
        if not dateStr:
            return ''
        try:
            parts = dateStr.split('-')
            if len(parts) == 3:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime.date(year, month, day).strftime('%B %d, %Y')
        except (ValueError, IndexError):
            pass
        return dateStr

    def calculateAge(self, birthDateStr, deathDateStr=None):
        if not birthDateStr:
            return None
        try:
            parts = birthDateStr.split('-')
            if len(parts) != 3:
                return None
            birthDate = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))

            if deathDateStr:
                parts = deathDateStr.split('-')
                endDate = datetime.date(int(parts[0]), int(parts[1]), int(parts[2])) if len(parts) == 3 else datetime.date.today()
            else:
                endDate = datetime.date.today()

            age = endDate.year - birthDate.year
            if (endDate.month, endDate.day) < (birthDate.month, birthDate.day):
                age -= 1
            return age
        except (ValueError, IndexError):
            return None

    def getItemGuid(self, item):
        if hasattr(item, 'guid') and item.guid:
            return str(item.guid)
        return None

    def groupFilmographyByGuid(self, items, existingByGuid=None):
        byGuid = existingByGuid if existingByGuid is not None else {}
        uniqueItems = []
        seenGuids = set(byGuid.keys()) if existingByGuid else set()

        for item in items:
            guid = self.getItemGuid(item)
            if guid:
                if guid not in byGuid:
                    byGuid[guid] = []
                byGuid[guid].append(item)
                if guid not in seenGuids:
                    seenGuids.add(guid)
                    uniqueItems.append(item)
            else:
                uniqueItems.append(item)

        for guid, versions in byGuid.items():
            if len(versions) > 1:
                versions.sort(key=lambda v: self.getItemBitrate(v), reverse=True)
                for i, uitem in enumerate(uniqueItems):
                    if self.getItemGuid(uitem) == guid:
                        uniqueItems[i] = versions[0]
                        break

        return uniqueItems, byGuid

    def getItemBitrate(self, item):
        try:
            if hasattr(item, 'media') and item.media:
                for media in item.media:
                    if hasattr(media, 'bitrate'):
                        return int(media.bitrate) if media.bitrate else 0
        except (ValueError, TypeError, AttributeError):
            pass
        return 0

    def getItemResolution(self, item):
        try:
            if hasattr(item, 'media') and item.media:
                for media in item.media:
                    if hasattr(media, 'videoResolution') and media.videoResolution:
                        return str(media.videoResolution)
        except (AttributeError, TypeError):
            pass
        return ''

    def getItemLibraryTitle(self, item):
        if hasattr(item, 'getLibrarySectionTitle'):
            return item.getLibrarySectionTitle()
        elif hasattr(item, 'librarySectionTitle'):
            return str(item.librarySectionTitle)
        return ''

    def formatVersionLabel(self, item, media_type='movie'):
        library = self.getItemLibraryTitle(item) or T(34108, 'Unknown')
        if media_type == 'movie':
            resolution = self.getItemResolution(item)
            bitrate = self.getItemBitrate(item)
            res_str = '{}p'.format(resolution) if resolution and 'k' not in str(resolution).lower() else (resolution.upper() if resolution else T(34108, 'Unknown'))
            if bitrate:
                return '{}, {} ({})'.format(library, res_str, plexnetUtil.bitrateToString(bitrate * 1000))
            return '{}, {}'.format(library, res_str)
        return library

    def showVersionPicker(self, versions, media_type='movie'):
        options = [{'key': idx, 'display': self.formatVersionLabel(item, media_type)}
                   for idx, item in enumerate(versions)]
        choice = dropdown.showDropdown(
            options=options,
            pos=(660, 441),
            close_direction='none',
            set_dropdown_prop=False,
            header=T(34109, 'Choose Version'),
            align_items='left'
        )
        if choice is not None:
            return versions[choice['key']]
        return None


class ActorWindow(PersonWindow):
    CREDIT_TYPE = None
    PRIMARY_TYPE = 'actor'
    TYPE_LABEL_ID = 32473  # "Actor"


class DirectorWindow(PersonWindow):
    CREDIT_TYPE = 'director'
    PRIMARY_TYPE = 'director'
    TYPE_LABEL_ID = 32474  # "Director"
