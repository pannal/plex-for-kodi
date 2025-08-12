from __future__ import absolute_import

import threading
import time

from kodi_six import xbmcgui, xbmc
from plexnet import plexapp

from lib import util
from lib.kodijsonrpc import rpc
from . import kodigui
from . import opener
from . import windowutils


class SearchDialog(kodigui.BaseDialog, windowutils.UtilMixin):
    xmlFile = 'script-plex-search.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LETTERS = 'abcdefghijklmnopqrstuvwxyz0123456789 '
    SECTION_BUTTONS = {
        901: 'all',
        902: 'movie',
        903: 'show',
        904: 'artist',
        905: 'photo'
    }

    EDIT_CONTROL_ID = 650
    BUTTON_A_ID = 1001

    HUB_POSTER_00 = 2100
    HUB_SQUARE_01 = 2101
    HUB_AR16X9_02 = 2102
    HUB_CIRCLE_03 = 2103
    HUB_POSTER_04 = 2104
    HUB_SQUARE_05 = 2105
    HUB_AR16X9_06 = 2106
    HUB_CIRCLE_07 = 2107
    HUB_POSTER_08 = 2108
    HUB_SQUARE_09 = 2109
    HUB_AR16X9_10 = 2110
    HUB_CIRCLE_11 = 2111
    HUB_POSTER_12 = 2112
    HUB_SQUARE_13 = 2113
    HUB_AR16X9_14 = 2114
    HUB_CIRCLE_15 = 2115
    HUB_POSTER_16 = 2116
    HUB_SQUARE_17 = 2117
    HUB_AR16X9_18 = 2118
    HUB_CIRCLE_19 = 2119
    HUB_POSTER_20 = 2120
    HUB_SQUARE_21 = 2121
    HUB_AR16X9_22 = 2122
    HUB_CIRCLE_23 = 2123
    HUB_POSTER_24 = 2124
    HUB_SQUARE_25 = 2125
    HUB_AR16X9_26 = 2126
    HUB_CIRCLE_27 = 2127
    HUB_POSTER_28 = 2128
    HUB_SQUARE_29 = 2129
    HUB_AR16X9_30 = 2130
    HUB_CIRCLE_31 = 2131
    HUB_POSTER_32 = 2132
    HUB_SQUARE_33 = 2133
    HUB_AR16X9_34 = 2134
    HUB_CIRCLE_35 = 2135
    HUB_POSTER_36 = 2136
    HUB_SQUARE_37 = 2137
    HUB_AR16X9_38 = 2138
    HUB_CIRCLE_39 = 2139
    HUB_POSTER_40 = 2140
    HUB_SQUARE_41 = 2141
    HUB_AR16X9_42 = 2142
    HUB_CIRCLE_43 = 2143
    HUB_POSTER_44 = 2144
    HUB_SQUARE_45 = 2145
    HUB_AR16X9_46 = 2146
    HUB_CIRCLE_47 = 2147

    HUBMAP = {
        'track': {'type': 'square'},
        'episode': {'type': 'ar16x9'},
        'movie': {'type': 'poster'},
        'show': {'type': 'poster'},
        'artist': {'type': 'square'},
        'album': {'type': 'square'},
        'photoalbum': {'type': 'square'},
        'photo': {'type': 'square'},
        'actor': {'type': 'circle'},
        'director': {'type': 'circle'},
        'genre': {'type': 'circle'},
        'playlist': {'type': 'square'},
    }

    SECTION_TYPE_MAP = {
        '1': {'thumb': 'script.plex/section_type/movie.png'},  # Movie
        '2': {'thumb': 'script.plex/section_type/show.png'},  # Show
        '3': {'thumb': 'script.plex/section_type/show.png'},  # Season
        '4': {'thumb': 'script.plex/section_type/show.png'},  # Episode
        '8': {'thumb': 'script.plex/section_type/music.png'},  # Artist
        '9': {'thumb': 'script.plex/section_type/music.png'},  # Album
        '10': {'thumb': 'script.plex/section_type/music.png'},  # Track
    }

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        windowutils.UtilMixin.__init__(self)
        self.parentWindow = kwargs.get('parent_window')
        self.sectionID = kwargs.get('section_id')
        self.resultsThread = None
        self.updateResultsTimeout = 0
        self.isActive = True
        self.useKodiKbd = util.getSetting('search_use_kodi_kbd')

    def onFirstInit(self):
        self.hubControls = (
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_00, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_01, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_02, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_03, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_04, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_05, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_06, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_07, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_08, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_09, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_10, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_11, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_12, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_13, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_14, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_15, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_16, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_17, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_18, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_19, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_20, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_21, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_22, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_23, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_24, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_25, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_26, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_27, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_28, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_29, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_30, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_31, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_32, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_33, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_34, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_35, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_36, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_37, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_38, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_39, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_40, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_41, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_42, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_43, 5)
            },
            {
                'poster': kodigui.ManagedControlList(self, self.HUB_POSTER_44, 5),
                'square': kodigui.ManagedControlList(self, self.HUB_SQUARE_45, 5),
                'ar16x9': kodigui.ManagedControlList(self, self.HUB_AR16X9_46, 5),
                'circle': kodigui.ManagedControlList(self, self.HUB_CIRCLE_47, 5)
            },
        )

        self.edit = kodigui.SafeControlEdit(self.EDIT_CONTROL_ID, 651, self, key_callback=self.updateFromEdit,
                                            grab_focus=True)
        self.edit.setCompatibleMode(rpc.Application.GetProperties(properties=["version"])["version"]["major"] < 17)
        if self.useKodiKbd:
            self.setProperty('hide.kbd', '1')
            self.setFocusId(self.EDIT_CONTROL_ID)
            xbmc.executebuiltin('Action(Select,{0})'.format(self._winID))
        else:
            self.setFocusId(self.BUTTON_A_ID)
        self.setProperty('search.section', 'all')
        self.updateQuery()

    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                self.isActive = False
        except:
            util.ERROR()

        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if 1000 < controlID < 1037:
            self.letterClicked(controlID)
        elif controlID in self.SECTION_BUTTONS:
            self.sectionClicked(controlID)
        elif controlID == 951:
            self.deleteClicked()
        elif controlID == 952:
            self.letterClicked(1037)
        elif controlID == 953:
            self.clearClicked()
        elif 2099 < controlID < 2200:
            self.hubItemClicked(controlID)

    def onFocus(self, controlID):
        if 2099 < controlID < 2200:
            self.setProperty('hub.focus', str(controlID - 2099))

    def updateFromEdit(self, actionID, oldVal, newVal):
        if actionID == xbmcgui.ACTION_PREVIOUS_MENU:
            self.isActive = False
            self.doClose()
            return

        self.updateQuery()

    def updateQuery(self):
        self.updateResults()

    def updateResults(self):
        self.updateResultsTimeout = time.time() + 1
        if not self.resultsThread or not self.resultsThread.is_alive():
            self.resultsThread = threading.Thread(target=self._updateResults, name='search.update')
            self.resultsThread.start()

    def _updateResults(self):
        while time.time() < self.updateResultsTimeout and not util.MONITOR.waitForAbort(0.1):
            pass

        self._reallyUpdateResults()

    def _reallyUpdateResults(self):
        query = self.edit.getText()
        if query:
            with self.propertyContext('searching'):
                hubs = plexapp.SERVERMANAGER.selectedServer.hubs(count=10, search_query=query, section=self.sectionID)
                self.showHubs(hubs)
        else:
            self.clearHubs()

    def sectionClicked(self, controlID):
        section = self.SECTION_BUTTONS[controlID]
        old = self.getProperty('search.section')
        self.setProperty('search.section', section)
        if old != section:
            self.updateResults()

    def letterClicked(self, controlID):
        letter = self.LETTERS[controlID - 1001]
        self.edit.append(letter)
        self.updateQuery()

    def deleteClicked(self):
        self.edit.delete()
        self.updateQuery()

    def clearClicked(self):
        self.edit.setText('')
        self.updateQuery()

    def hubItemClicked(self, hubControlID):
        for controls in self.hubControls:
            for control in controls.values():
                if control.controlID == hubControlID:
                    break
            else:
                continue
            break
        else:
            return

        mli = control.getSelectedItem()
        if not mli:
            return

        hubItem = mli.dataSource
        if hubItem.TYPE == 'playlist' and not hubItem.exists():  # Workaround for server bug
            util.messageDialog('No Access', 'Playlist not accessible by this user.')
            util.DEBUG_LOG('Search: Playlist does not exist - probably wrong user')
            return

        self.doClose()
        try:
            command = opener.open(hubItem)

            if not hubItem.exists():
                control.removeManagedItem(mli)

            self.processCommand(command)
        finally:
            if not self.exitCommand:
                self.show()
            else:
                self.isActive = False

    def createListItem(self, hubItem):
        if hubItem.TYPE in ('Genre', 'Director', 'Role'):
            if hubItem.TYPE == 'Genre':
                thumb = (self.SECTION_TYPE_MAP.get(hubItem.librarySectionType) or {}).get('thumb', '')
                mli = kodigui.ManagedListItem(hubItem.tag, hubItem.reasonTitle, thumbnailImage=thumb, data_source=hubItem)
                mli.setProperty('thumb.fallback', thumb)
            else:
                mli = kodigui.ManagedListItem(
                    hubItem.tag, hubItem.reasonTitle, thumbnailImage=hubItem.get('thumb').asTranscodedImageURL(256, 256), data_source=hubItem
                )
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/role.png')
        else:
            if hubItem.TYPE == 'playlist':
                mli = kodigui.ManagedListItem(hubItem.tag, thumbnailImage=hubItem.get('composite').asTranscodedImageURL(256, 256), data_source=hubItem)
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/{0}.png'.format(hubItem.playlistType == 'audio' and 'music' or 'movie'))
            elif hubItem.TYPE == 'photodirectory':
                mli = kodigui.ManagedListItem(hubItem.title, thumbnailImage=hubItem.get('composite').asTranscodedImageURL(256, 256), data_source=hubItem)
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/photo.png')
            else:
                mli = kodigui.ManagedListItem(hubItem.title, thumbnailImage=hubItem.get('thumb').asTranscodedImageURL(256, 256), data_source=hubItem)
                if hubItem.TYPE in ('movie', 'clip'):
                    mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/movie.png')
                elif hubItem.TYPE in ('artist', 'album', 'track'):
                    mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/music.png')
                elif hubItem.TYPE in ('show', 'season', 'episode'):
                    mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
                elif hubItem.TYPE == 'photo':
                    mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/photo.png')

        return mli

    def showHubs(self, hubs):
        self.clearHubs()
        self.opaqueBackground(on=False)

        allowed = None
        if self.getProperty('search.section') == 'movie':
            allowed = ('movie',)
        elif self.getProperty('search.section') == 'show':
            allowed = ('show', 'season', 'episode')
        elif self.getProperty('search.section') == 'artist':
            allowed = ('artist', 'album', 'track')
        elif self.getProperty('search.section') == 'photo':
            allowed = ('photo', 'photodirectory')

        controlID = None
        i = 0
        for h in hubs:
            if allowed and h.type not in allowed:
                continue

            if h.size.asInt() > 0:
                self.opaqueBackground()
                cid = self.showHub(h, i)
                controlID = controlID or cid
                i += 1

        if controlID:
            self.setProperty('no.results', '')
        else:
            self.setProperty('no.results', '1')

    def showHub(self, hub, idx):
        util.DEBUG_LOG('Showing search hub: {0} at {1}', hub.type, idx)
        info = self.HUBMAP.get(hub.type)
        if not info:
            util.DEBUG_LOG('Unhandled hub type: {0}', hub.type)
            return

        itemListControl = self.hubControls[idx][info['type']]
        if itemListControl is None:
            util.DEBUG_LOG('No control defined')
            return

        self.setProperty('hub.{0}'.format(itemListControl.controlID), hub.title)

        items = []
        for hubItem in hub.items:
            mli = self.createListItem(hubItem)
            items.append(mli)

        itemListControl.reset()
        itemListControl.addItems(items)

        return itemListControl.controlID

    def clearHubs(self):
        self.opaqueBackground(on=False)
        self.setProperty('no.results', '')
        for controls in self.hubControls:
            for control in controls.values():
                if control:
                    control.reset()
        self.setProperty('hub.focus', '')

    def opaqueBackground(self, on=True):
        self.parentWindow.setProperty('search.dialog.hasresults', on and '1' or '')

    def wait(self):
        while self.isActive and not util.MONITOR.waitForAbort(0.1):
            pass


def dialog(parent_window, section_id=None):
    parent_window.setProperty('search.dialog.hasresults', '')
    with parent_window.propertyContext('search.dialog'):
        try:
            w = SearchDialog.open(parent_window=parent_window, section_id=section_id)
            w.wait()
            command = w.exitCommand or ''
            del w
            return command
        finally:
            parent_window.setProperty('search.dialog.hasresults', '')
