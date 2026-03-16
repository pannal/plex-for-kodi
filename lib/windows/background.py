from __future__ import absolute_import

from lib import util
from . import kodigui

util.setGlobalProperty('background.busy', '')
util.setGlobalProperty('background.shutdown', '')
util.setGlobalProperty('background.splash', '')


class BackgroundWindow(kodigui.BaseWindow):
    xmlFile = 'script-plex-background.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    def __init__(self, *args, **kwargs):
        kodigui.BaseWindow.__init__(self, *args, **kwargs)
        self.function = kwargs.get('function')

    def _activate(self, *args, **kwargs):
        self.activate()

    def onFirstInit(self):
        # try accessing our dummy control to trigger an error if our XML is broken
        util.MONITOR.on("background.activate", self._activate)
        self.function()
        self.doClose()

    def doClose(self, **kwargs):
        try:
            # MONITOR might be dead already
            util.MONITOR.off("background.activate", self._activate)
        except:
            pass
        super(BackgroundWindow, self).doClose(**kwargs)

    def onAction(self, action):
        pass


def setBusy(on=True):
    util.setGlobalProperty('background.busy', on and '1' or '')


def setSplash(on=True):
    util.setGlobalProperty('background.splash', on and '1' or '')


def setShutdown(on=True):
    util.setGlobalProperty('background.shutdown', on and '1' or '')


def killMonitor():
    kodigui.MONITOR = None
