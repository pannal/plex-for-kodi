# coding=utf-8
from __future__ import absolute_import

import gc
import atexit
import threading
import six
import sys

from kodi_six import xbmc

#import cProfile, pstats, io
#from pstats import SortKey

sys.modules['_asyncio'] = None

from . import plex

from plexnet import plexapp
from .templating import render_templates
from .windows import background, userselect, home, windowutils, kodigui
from . import player
from . import backgroundthread
from . import util
from .data_cache import dcm

BACKGROUND = None
quitKodi = False
restart = False


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
                    util.DEBUG_LOG('Main: Waiting on: {0}...', t.name)
                    if isinstance(t, _Timer):
                        t.cancel()

                    try:
                        t.join(.25)
                    except:
                        util.ERROR()


@atexit.register
def realExit():
    xbmc.log('Main: script.plexmod: REALLY FINISHED', xbmc.LOGINFO)
    if quitKodi:
        xbmc.log('Main: script.plexmod: QUITTING KODI', xbmc.LOGINFO)
        xbmc.executebuiltin('Quit')

    elif restart:
        xbmc.executebuiltin('RunScript(script.plexmod)')


def signout():
    util.setSetting('auth.token', '')
    util.DEBUG_LOG('Main: Signing out...')
    plexapp.ACCOUNT.signOut()


def main(force_render=False):
    global BACKGROUND

    try:
        with kodigui.GlobalProperty('rendering'):
            render_templates(force=force_render)

        with util.Cron(1 / util.addonSettings.tickrate):
            BACKGROUND = background.BackgroundWindow.create(function=_main)
            if BACKGROUND.waitForOpen():
                with kodigui.GlobalProperty('running'):
                    BACKGROUND.modal()

                    # we've had an XMLError during modalizing, rebuild templates
                    if BACKGROUND._errored:
                        return main(force_render=True)
                    del BACKGROUND
            else:
                util.LOG("Couldn't start main loop, exiting.")
    finally:
        try:
            util.setGlobalProperty('ignore_spinner', '')
            util.setGlobalProperty('is_active', '')
        except:
            pass


def _main():
    global quitKodi, restart

    # uncomment to profile code #1
    #pr = cProfile.Profile()
    #pr.enable()

    util.DEBUG_LOG('[ STARTED: {0} -------------------------------------------------------------------- ]', util.ADDON.getAddonInfo('version'))
    if util.KODI_VERSION_MAJOR > 19 and util.DEBUG and util.getSetting('dump_config', False):
        lv = len(util.ADDON.getAddonInfo('version'))
        util.DEBUG_LOG('[ SETTINGS DUMP {0}-------------------------------------------------------------------- '
                       ']', (lv - 4)*'-')
        util.dumpSettings()
        util.DEBUG_LOG('[ /SETTINGS DUMP {0}------------------------------------------------------------------- '
                       ']', (lv - 3) * '-')

    util.DEBUG_LOG('USER-AGENT: {0}', lambda: plex.defaultUserAgent())
    util.DEBUG_LOG('Aspect ratio: {:.2f} (default: {:.2f}), needs scaling: {}', util.CURRENT_AR, 1920 / 1080,
                   util.NEEDS_SCALING)
    background.setSplash()
    util.setGlobalProperty('is_active', '1')

    try:
        while not util.MONITOR.abortRequested():
            if plex.init():
                background.setSplash(False)
                fromSwitch = False
                while not util.MONITOR.abortRequested():
                    if (
                        not plexapp.ACCOUNT.isOffline and not
                        plexapp.ACCOUNT.isAuthenticated and
                        (len(plexapp.ACCOUNT.homeUsers) > 1 or plexapp.ACCOUNT.isProtected)

                    ):
                        result = userselect.start(BACKGROUND._winID)
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
                        elif result == 'cancel':
                            return
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

                                    selectedServer = plexapp.SERVERMANAGER.checkSelectedServerSearch(
                                        skip_preferred=skip_preferred, skip_owned=skip_owned)
                                    if selectedServer:
                                        break
                                else:
                                    util.DEBUG_LOG('Main: Finished waiting for selected server...')
                            finally:
                                background.setBusy(False)

                        util.DEBUG_LOG('Main: STARTING WITH SERVER: {0}', selectedServer)

                        windowutils.HOME = home.HomeWindow.create()
                        if windowutils.HOME.waitForOpen(base_win_id=BACKGROUND._winID):
                            windowutils.HOME.modal()
                        else:
                            util.LOG("Couldn't open home window, exiting")
                            return
                        util.CRON.cancelReceiver(windowutils.HOME)

                        if not windowutils.HOME.closeOption or windowutils.HOME.closeOption in ("quit", "exit"):
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
                        elif closeOption == 'recompile':
                            render_templates(force=True)
                            util.LOG("Restarting Home")
                            continue
                        elif closeOption == 'restart':
                            util.LOG("Restarting Addon")
                            restart = True
                            return
                    finally:
                        windowutils.shutdownHome()
                        BACKGROUND.activate()
                        background.setShutdown()
                        gc.collect(2)

            else:
                break
    except:
        util.ERROR()
    finally:
        util.DEBUG_LOG('Main: SHUTTING DOWN...')
        dcm.storeDataCache()
        dcm.deinit()
        plexapp.util.INTERFACE.playbackManager.deinit()
        player.shutdown()
        plexapp.util.APP.preShutdown()
        util.CRON.stop()
        backgroundthread.BGThreader.shutdown()
        plexapp.util.APP.shutdown()
        waitForThreads()
        background.setBusy(False)
        background.setSplash(False)
        background.killMonitor()

        # uncomment to profile code #2
        #pr.disable()
        #sortby = SortKey.CUMULATIVE
        #s = io.StringIO()
        #ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        #ps.print_stats()
        #util.DEBUG_LOG(s.getvalue())

        util.DEBUG_LOG('FINISHED')
        util.shutdown()
        gc.collect(2)

        if util.KODI_VERSION_MAJOR == 18:
            realExit()
