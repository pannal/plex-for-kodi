from __future__ import absolute_import

import json
import threading
import time

from kodi_six import xbmcgui, xbmc
from plexnet import plexapp

from lib import util
from lib.util import T
from lib.kodijsonrpc import rpc
from . import kodigui
from . import opener
from . import optionsdialog
from . import windowutils


class HistoryItem(object):
    TYPE = 'history'

    def __init__(self, query, is_clear=False):
        self.query = query
        self.title = query
        self.is_clear = is_clear


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
    SEARCH_HUB_COUNT = 12  # must match core.search_hub_count in lib/templating/context.py
    HISTORY_LIST_ID = 2050
    MAX_HISTORY_ITEMS = 10

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
        self.hubControls = [
            kodigui.ManagedControlList(self, 2100 + i, 5)
            for i in range(self.SEARCH_HUB_COUNT)
        ]
        self.historyList = kodigui.ManagedControlList(self, self.HISTORY_LIST_ID, self.MAX_HISTORY_ITEMS + 1)

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
        self.showSearchHistory()

    def onReInit(self):
        # Re-displayed (e.g. returning from an opened result): re-evaluate the view.
        # onFirstInit only runs on the first init, so without this the history view
        # never re-renders after the dialog is shown again.
        if self.edit.getText():
            self.updateResults()
        else:
            self.showSearchHistory()

    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                self.isActive = False
            elif action in (xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_MOVE_UP):
                if self._skipEmptyRow(action):
                    return
        except:
            util.ERROR()

        kodigui.BaseDialog.onAction(self, action)

    def _skipEmptyRow(self, action):
        controlID = self.getFocusId()
        if not (2100 <= controlID < 2100 + self.SEARCH_HUB_COUNT):
            return False
        idx = controlID - 2100
        step = 1 if action == xbmcgui.ACTION_MOVE_DOWN else -1
        nxt = idx + step
        while 0 <= nxt < self.SEARCH_HUB_COUNT:
            control = self.hubControls[nxt]
            if control and control.size() > 0:
                self.setFocusId(2100 + nxt)
                return True
            nxt += step
        return False

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
        elif controlID == self.HISTORY_LIST_ID:
            self.historyItemClicked()

    def onFocus(self, controlID):
        if 2099 < controlID < 2200:
            self.setProperty('hub.focus', str(controlID - 2100))

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
            self.showSearchHistory()

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

    def _historyKey(self):
        server = plexapp.SERVERMANAGER.selectedServer
        if not server:
            return None
        return 'search.history.{0}.{1}'.format(server.uuid[-8:], plexapp.ACCOUNT.ID)

    def loadSearchHistory(self):
        key = self._historyKey()
        if not key:
            return []
        try:
            return json.loads(util.getSetting(key, '[]'))[:self.MAX_HISTORY_ITEMS]
        except Exception:
            util.ERROR()
            return []

    def saveSearchHistory(self, history):
        key = self._historyKey()
        if not key:
            return
        try:
            util.setSetting(key, json.dumps(history[:self.MAX_HISTORY_ITEMS]))
        except Exception:
            util.ERROR()

    def addToHistory(self, title):
        if not title or not title.strip():
            return
        title = title.strip()
        history = self.loadSearchHistory()
        if title in history:
            history.remove(title)
        history.insert(0, title)
        self.saveSearchHistory(history)

    def clearSearchHistory(self):
        key = self._historyKey()
        if key:
            try:
                util.setSetting(key, '[]')
            except Exception:
                util.ERROR()

    def showSearchHistory(self):
        self.clearHubs()
        history = self.loadSearchHistory()
        if not history:
            self.setProperty('show.history', '')
            return
        items = []
        for query in history:
            mli = kodigui.ManagedListItem(query, data_source=HistoryItem(query))
            mli.setProperty('icon', 'script.plex/buttons/search.png')
            items.append(mli)
        clear_label = T(35005, 'Clear search history')
        clear_mli = kodigui.ManagedListItem(clear_label, data_source=HistoryItem(clear_label, is_clear=True))
        clear_mli.setProperty('icon', 'script.plex/indicators/remove.png')
        items.append(clear_mli)
        self.historyList.reset()
        self.historyList.addItems(items)
        self.setProperty('show.history', '1')

    def historyItemClicked(self):
        mli = self.historyList.getSelectedItem()
        if not mli:
            return
        item = mli.dataSource
        if getattr(item, 'is_clear', False):
            button = optionsdialog.show(
                T(35005, 'Clear search history'),
                T(35006, 'Clear all search history?'),
                T(32328, 'Yes'),
                T(32329, 'No'),
            )
            if button == 0:
                self.clearSearchHistory()
                self.showSearchHistory()
            return
        self.edit.setText(item.query)
        self.updateQuery()

    def hubItemClicked(self, hubControlID):
        for control in self.hubControls:
            if control.controlID == hubControlID:
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

        self.addToHistory(self.edit.getText())
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
                if i >= self.SEARCH_HUB_COUNT:
                    break
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

        hub_id = 2100 + idx
        control = self.hubControls[idx]

        self.setProperty('hub.display.{0}'.format(hub_id), info['type'])
        self.setProperty('hub.{0}'.format(hub_id), hub.title)

        items = []
        for hubItem in hub.items:
            mli = self.createListItem(hubItem)
            if mli:
                items.append(mli)

        control.reset()
        control.addItems(items)

        return control.controlID

    def clearHubs(self):
        self.opaqueBackground(on=False)
        self.setProperty('no.results', '')
        for i, control in enumerate(self.hubControls):
            control.reset()
            hub_id = 2100 + i
            self.setProperty('hub.{0}'.format(hub_id), '')
            self.setProperty('hub.display.{0}'.format(hub_id), '')
        self.setProperty('hub.focus', '')
        self.historyList.reset()
        self.setProperty('show.history', '')

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
