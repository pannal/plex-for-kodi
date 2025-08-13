# coding=utf-8
from __future__ import absolute_import

from kodi_six import xbmc
from kodi_six import xbmcgui

import plexnet
from lib import util
from lib.windows import kodigui


class SelectDialog(kodigui.BaseDialog, util.CronReceiver):
    xmlFile = 'script-plex-settings_select_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    OPTIONS_LIST_ID = 100

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.heading = kwargs.get('heading')
        self.options = kwargs.get('options')
        self.selectedIdx = kwargs.get('selected_idx')
        self.choice = None
        self.nonPlayback = kwargs.get('non_playback')
        self.lastSelectedItem = self.selectedIdx if self.selectedIdx is not None else 0
        self.roundRobin = kwargs.get('round_robin', True)
        self.trim = kwargs.get('trim', True)

    def onFirstInit(self):
        self.optionsList = kodigui.ManagedControlList(self, self.OPTIONS_LIST_ID, 8)
        self.setProperty('heading', self.heading)
        self.showOptions()
        util.CRON.registerReceiver(self)

    def onAction(self, action):
        try:
            if not xbmc.getCondVisibility('Player.HasMedia') and not self.nonPlayback:
                self.doClose()
                return
        except:
            util.ERROR()

        if self.roundRobin and action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN) and \
                self.getFocusId() == self.OPTIONS_LIST_ID:
            to_pos = None
            last_index = self.optionsList.size() - 1

            if last_index > 0:
                if action == xbmcgui.ACTION_MOVE_UP and self.lastSelectedItem == 0 and self.optionsList.topHasFocus():
                    to_pos = last_index

                elif action == xbmcgui.ACTION_MOVE_DOWN and self.lastSelectedItem == last_index \
                        and self.optionsList.bottomHasFocus():
                    to_pos = 0

                if to_pos is not None:
                    self.optionsList.setSelectedItemByPos(to_pos)
                    self.lastSelectedItem = to_pos
                    return

                self.lastSelectedItem = self.optionsList.control.getSelectedPosition()

        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
        if controlID == self.OPTIONS_LIST_ID:
            self.setChoice()

    def onClosed(self):
        util.CRON.cancelReceiver(self)

    def tick(self):
        if self.nonPlayback:
            return

        if not xbmc.getCondVisibility('Player.HasMedia'):
            self.doClose()
            return

    def setChoice(self):
        mli = self.optionsList.getSelectedItem()
        if not mli:
            return

        self.choice = self.options[self.optionsList.getSelectedPosition()][0]
        self.doClose()

    def showOptions(self):
        items = []
        for ds, title1 in self.options:
            title2 = ''
            if isinstance(title1, (list, set, tuple)):
                title1, title2 = title1
            item = kodigui.ManagedListItem(title1, self.trim and plexnet.util.trimString(title2, limit=40) or title2,
                                           data_source=ds)
            items.append(item)

        self.optionsList.reset()
        self.optionsList.addItems(items)

        if self.selectedIdx is not None:
            self.optionsList.selectItem(self.selectedIdx)

        self.setFocusId(self.OPTIONS_LIST_ID)


def showOptionsDialog(heading, options, non_playback=False, selected_idx=None, trim=True):
    w = SelectDialog.open(heading=heading, options=options, non_playback=non_playback, selected_idx=selected_idx,
                          trim=trim)
    choice = w.choice
    del w
    util.garbageCollect()
    return choice
