from __future__ import absolute_import
from kodi_six import xbmc

if xbmc.getInfoLabel('Window(10000).Property(script.plex.running)') == "1":
    xbmc.executebuiltin('NotifyAll({0},{1},{2})'.format('script.plexmod', 'RESTORE', '{}'))
    raise SystemExit

import gc
import atexit
import threading
import six
import sys
sys.modules['_asyncio'] = None

from . import plex

from plexnet import plexapp
from .windows import background, userselect, home, windowutils
from . import player
from . import backgroundthread
from . import util

BACKGROUND = None
quitKodi = False


if six.PY2:
    _Timer = threading._Timer
else:
    _Timer = threading.Timer


def waitForThreads():
    util.DEBUG_LOG('Main: Checking for any remaining threads')
    while len(threading.enumerate()) > 1:
        for t in threading.enumerate():
            if t != threading.currentThread():
                if t.is_alive():
                    util.DEBUG_LOG('Main: Waiting on: {0}...'.format(t.name))
                    if isinstance(t, _Timer):
                        t.cancel()

                    try:
                        t.join()
                    except:
                        util.ERROR()


@atexit.register
def realExit():
    xbmc.log('Main: script.plex: REALLY FINISHED', xbmc.LOGINFO)
    if quitKodi:
        xbmc.log('Main: script.plex: QUITTING KODI', xbmc.LOGINFO)
        xbmc.executebuiltin('Quit')


def signout():
    util.setSetting('auth.token', '')
    util.DEBUG_LOG('Main: Signing out...')
    plexapp.ACCOUNT.signOut()


def main():
    global BACKGROUND
    util.ensureHome()

    try:
        with util.Cron(0.1):
            BACKGROUND = background.BackgroundWindow.create(function=_main)

            tries = 0
            while not BACKGROUND.isOpen and not util.MONITOR.waitForAbort(2) and tries < 60:
                if tries == 0:
                    util.LOG("Couldn't start main loop, other dialog open? Retrying for 120s.")
                BACKGROUND.show()
                tries += 1

            if BACKGROUND.isOpen:
                util.setGlobalProperty('running', '1')
                BACKGROUND.modal()
                del BACKGROUND
            else:
                util.LOG("Couldn't start main loop, exiting.")
    finally:
        try:
            util.setGlobalProperty('running', '')
            util.setGlobalProperty('stop_running', '')
        except:
            pass


def _main():
    global quitKodi
    util.DEBUG_LOG('[ STARTED: {0} -------------------------------------------------------------------- ]'.format(util.ADDON.getAddonInfo('version')))
    util.DEBUG_LOG('USER-AGENT: {0}'.format(plex.defaultUserAgent()))
    background.setSplash()

    try:
        while not util.MONITOR.abortRequested() and not util.getGlobalProperty('stop_running'):
            if plex.init():
                background.setSplash(False)
                fromSwitch = False
                while not util.MONITOR.abortRequested() and not util.getGlobalProperty('stop_running'):
                    if (
                        not plexapp.ACCOUNT.isOffline and not
                        plexapp.ACCOUNT.isAuthenticated and
                        (len(plexapp.ACCOUNT.homeUsers) > 1 or plexapp.ACCOUNT.isProtected)

                    ):
                        result = userselect.start()
                        if not result:
                            return
                        elif result == 'signout':
                            signout()
                            break
                        elif result == 'signin':
                            break
                        elif result == 'cancel' and fromSwitch:
                            util.DEBUG_LOG('Main: User selection canceled, reusing previous user')
                            plexapp.ACCOUNT.isAuthenticated = True

                        if not fromSwitch:
                            util.DEBUG_LOG('Main: User selected')

                    try:
                        selectedServer = plexapp.SERVERMANAGER.selectedServer

                        if not selectedServer:
                            background.setBusy()
                            util.DEBUG_LOG('Main: Waiting for selected server...')
                            try:
                                for timeout, skip_preferred, skip_owned in ((10, False, False), (10, True, True)):
                                    plex.CallbackEvent(plexapp.util.APP, 'change:selectedServer', timeout=timeout).wait()

                                    selectedServer = plexapp.SERVERMANAGER.checkSelectedServerSearch(skip_preferred=skip_preferred, skip_owned=skip_owned)
                                    if selectedServer:
                                        break
                                else:
                                    util.DEBUG_LOG('Main: Finished waiting for selected server...')
                            finally:
                                background.setBusy(False)

                        util.DEBUG_LOG('Main: STARTING WITH SERVER: {0}'.format(selectedServer))

                        windowutils.HOME = home.HomeWindow.open()
                        util.CRON.cancelReceiver(windowutils.HOME)

                        if not windowutils.HOME.closeOption or windowutils.HOME.closeOption == "quit":
                            if windowutils.HOME.closeOption == "quit":
                                quitKodi = True
                            return

                        closeOption = windowutils.HOME.closeOption

                        windowutils.shutdownHome()

                        if closeOption == 'signout':
                            signout()
                            break
                        elif closeOption == 'switch':
                            plexapp.ACCOUNT.isAuthenticated = False
                            fromSwitch = True
                    finally:
                        windowutils.shutdownHome()
                        BACKGROUND.activate()
                        gc.collect(2)

            else:
                break
    except:
        util.ERROR()
    finally:
        util.DEBUG_LOG('Main: SHUTTING DOWN...')
        background.setShutdown()
        player.shutdown()
        plexapp.util.APP.preShutdown()
        util.CRON.stop()
        backgroundthread.BGThreader.shutdown()
        plexapp.util.APP.shutdown()
        waitForThreads()
        background.setBusy(False)
        background.setSplash(False)
        background.killMonitor()

        util.DEBUG_LOG('FINISHED')
        util.shutdown()

        gc.collect(2)

        if util.KODI_VERSION_MAJOR == 18 and quitKodi:
            xbmc.log('Main: script.plex: QUITTING KODI', xbmc.LOGINFO)
            xbmc.executebuiltin('Quit')
