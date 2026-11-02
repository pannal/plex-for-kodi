# coding=utf-8
from __future__ import absolute_import

import threading

from lib import util
from . import kodigui


class BlackoutDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-blackout_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self._stateLock = threading.Lock()
        self._retired = False
        self._showAdmitted = False

    def cancel(self):
        # State only: handler reset can run under the startup ownership lock.
        with self._stateLock:
            self._retired = True

    def _closeIfRetired(self):
        with self._stateLock:
            retired = self._retired
        if retired:
            kodigui.BaseDialog.doClose(self)
        return retired

    def show(self):
        with self._stateLock:
            if self._retired or self._showAdmitted:
                return False
            self._showAdmitted = True
        # Never hold a Python lock across native window calls. Cleanup can run
        # while show yields; close again afterwards if it won that race.
        try:
            kodigui.BaseDialog.show(self)
        finally:
            retired = self._closeIfRetired()
        return not retired

    def _onInit(self):
        if self._closeIfRetired():
            return
        try:
            kodigui.BaseDialog._onInit(self)
        finally:
            # A late native init must not leave a close.dialogs subscription.
            self._closeIfRetired()

    def doClose(self, **kw):
        self.cancel()
        kodigui.BaseDialog.doClose(self, **kw)
