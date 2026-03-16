# coding=utf-8
from __future__ import absolute_import

import gc
import atexit
import threading
import six
import sys
import logging
import time

try:
    from _thread import interrupt_main
except:
    from thread import interrupt_main

from kodi_six import xbmc

#import cProfile, pstats, io
#from pstats import SortKey

sys.modules['_asyncio'] = None

from . import plex

from plexnet import plexapp
from .templating import render_templates
from .windows import background, userselect, home, windowutils, kodigui, busy
from . import player
from . import backgroundthread
from . import util
from .logging import KodiLogProxyHandler
from .data_cache import dcm

BACKGROUND = None
quitKodi = False
restart = False
skipEnsureLastUsed = False


if six.PY2:
    _Timer = threading._Timer
else:
    _Timer = threading.Timer


if util.addonSettings.debugRequests:
    logger = logging.getLogger("urllib3")
    logger.addHandler(KodiLogProxyHandler(level=logging.DEBUG,
                                          log_func=lambda *a, **kw: util.log(*a, prepend_msg="[urllib3]", **kw)))
    logger.setLevel(logging.DEBUG)


def waitForThreads():
    util.DEBUG_LOG('Main: Checking for any remaining threads (current: {})'.format(threading.currentThread().name))
    started = time.time()
    exit_timer_was_alive = exit_timer.is_alive()

    # if the exit timer was still alive at this point, try cancelling all threads for 5 seconds
    if not exit_timer_started or exit_timer_was_alive:
        while len(threading.enumerate()) > 1 and time.time() < started + util.addonSettings.maxShutdownWait:
            alive_threads = [t for t in list(threading.enumerate()) if t.is_alive()]
            alive_threads_out = ", ".join(t.name for t in alive_threads)
            alive_threads_count = len(alive_threads)

            # With certain linux instances we might have two threads, while Dummy is the one we're on.
            if alive_threads_count == 2 and "Dummy" in alive_threads_out and "MainThread" in alive_threads_out:
                break

            for t in threading.enumerate():
                if t != threading.currentThread():
                    if t.is_alive():
                        util.DEBUG_LOG('Main: Waiting on: {0}... (alive: {1})', t.name, alive_threads_out)
                        if isinstance(t, _Timer):
                            t.cancel()

                        try:
                            t.join(.25)
                        except:
                            util.ERROR()
            util.MONITOR.waitForAbort(0.05)
    else:
        util.DEBUG_LOG("Main: Not waiting for remaining threads as exit already took to long; hard exit")

    if time.time() >= started + util.addonSettings.maxShutdownWait or (exit_timer_started and not exit_timer_was_alive):
        util.LOG('Main: script.plexmod: threads took too long or timer hit, HARD EXITING')
        sys.exit(0)

@atexit.register
def realExit():
    xbmc.log('Main: script.plexmod: REALLY FINISHED', xbmc.LOGINFO)
    if quitKodi:
        xbmc.log('Main: script.plexmod: QUITTING KODI', xbmc.LOGINFO)
        xbmc.executebuiltin('Quit')

    elif restart:
        xbmc.executebuiltin('RunScript(script.plexmod)')
    else:
        if not skipEnsureLastUsed and util.getSetting('ensure_lastused'):
            updateLastUsedAddon()


def signout():
    util.setSetting('auth.token', '')
    util.DEBUG_LOG('Main: Signing out...')
    plexapp.ACCOUNT.signOut()

exit_timer_started = False

def hardExit():
    util.LOG('Main: script.plexmod: timer hit, triggering hard exit...')
    xbmc.executebuiltin('StopScript(script.plexmod)')
    interrupt_main()


exit_timer = threading.Timer(util.addonSettings.maxShutdownWait, hardExit)
exit_timer.name = 'HARDEXIT-TIMER'


def main(force_render=False):
    global BACKGROUND

    try:
        with kodigui.GlobalProperty('rendering'):
            render_templates(force=force_render)

        # cleanup cache folder
        util.cleanupCacheFolder()

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


def updateLastUsedAddon():
    """
    Runs our plugin endpoint with a stub value, so it immediately returns, then issues a Back action to back out of it.
    This is called atExit if necessary and updates the recently used video addon list with our addon (as it's a script,
    it would normally not get its lastused property updated when ran from service or script video endpoint)
    :return:
    """
    try:
        util.setGlobalProperty('ignore_spinner', '1', wait=True)
        xbmc.executebuiltin("RunAddon(script.plexmod,stub)")
        xbmc.executebuiltin('Action(back)')
    finally:
        util.setGlobalProperty('ignore_spinner', '')


def _main():
    global quitKodi, restart, exit_timer_started, skipEnsureLastUsed

    # uncomment to profile code #1
    #pr = cProfile.Profile()
    #pr.enable()

    util.DEBUG_LOG('[ STARTED: {0} -------------------------------------------------------------------- ]', util.ADDON.getAddonInfo('version'))
    if util.KODI_VERSION_MAJOR > 19 and util.DEBUG and util.getSetting('dump_config'):
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
                        oldAccID = plexapp.ACCOUNT.ID
                        result = userselect.start(BACKGROUND._winID)
                        tries = 0
                        while result == 'retry' and tries < 2:
                            util.DEBUG_LOG("Main: User select: possibly wrong pin entered, retrying after refreshing home users ({}/2)", tries + 1)
                            result = userselect.start(BACKGROUND._winID)
                            tries += 1

                        if not result:
                            return
                        elif result == 'signout':
                            signout()
                            break
                        elif result == 'signin':
                            break
                        elif result in ('cancel', 'retry') and fromSwitch:
                            if result == 'retry':
                                util.LOG("Main: User select failed multiple times possibly due to wrong pin entry.")
                            util.DEBUG_LOG('Main: User selection canceled, reusing previous user')
                            plexapp.ACCOUNT.isAuthenticated = True
                        elif result == 'cancel':
                            return
                        if not fromSwitch:
                            util.DEBUG_LOG('Main: User selected')
                        background.setBusy()
                        util.MONITOR.trigger("background.activate")

                        # store previous account ID for fast user switch
                        if oldAccID and oldAccID != plexapp.ACCOUNT.ID:
                            util.setSetting('previous_user', oldAccID)

                    closeOption = "exit"
                    try:
                        selectedServer = plexapp.SERVERMANAGER.selectedServer

                        if not selectedServer:
                            background.setBusy()
                            base_timeout = max(
                                util.addonSettings.plextvTimeoutConnect * util.addonSettings.maxRetries1 +
                                util.addonSettings.plextvTimeoutRead * util.addonSettings.maxRetries1,
                                util.addonSettings.connCheckTimeout * util.addonSettings.maxRetries1)
                            util.DEBUG_LOG('Main: Waiting for selected server... (max timeout: {})', base_timeout)
                            try:
                                for timeout, skip_preferred, skip_owned in ((base_timeout, True, False), (base_timeout, True, True)):
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
                            background.setBusy(False)
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
                            background.setBusy(True)
                            util.DEBUG_LOG('Main: Switching users...: {}', plexapp.ACCOUNT.ID)
                            plexapp.ACCOUNT.isAuthenticated = False
                            fromSwitch = True
                        elif isinstance(closeOption, dict):
                            if closeOption.get('fast_switch'):
                                uid = closeOption['fast_switch']
                                util.DEBUG_LOG('Main: Fast-Switching users...: {}', uid)
                                util.setSetting('previous_user', plexapp.ACCOUNT.ID)
                                with busy.BusySignalContext(plexapp.util.APP, "account:response", wait_max=10):
                                    if plexapp.ACCOUNT.switchHomeUser(uid, silent=True) and plexapp.ACCOUNT.switchUser:
                                        util.DEBUG_LOG('Waiting for user change...')

                        elif closeOption == 'recompile':
                            render_templates(force=True)
                            util.LOG("Restarting Home")
                            continue
                        elif closeOption == 'restart':
                            util.LOG("Restarting Addon")
                            restart = True
                            return
                        elif closeOption == 'update':
                            util.LOG("Exiting for update")
                            skipEnsureLastUsed = True
                            return
                    finally:
                        try:
                            kodiExiting = closeOption == "kodi_exit" or windowutils.HOME.closeOption == "kodi_exit"
                        except:
                            kodiExiting = False

                        if closeOption in ("quit", "exit", "restart", "update") and not kodiExiting:
                            if not exit_timer.is_alive():
                                util.DEBUG_LOG("Main: Starting hard exit timer of {} seconds...", util.addonSettings.maxShutdownWait)
                                exit_timer.start()
                            exit_timer_started = True
                        windowutils.shutdownHome()
                        BACKGROUND.activate()
                        background.setShutdown()
                        gc.collect(2)

                    if kodiExiting:
                        return

            else:
                break
    except KeyboardInterrupt:
        util.LOG("Main: Interrupted, hard exiting...")
        sys.exit(0)
    except SystemExit:
        util.LOG("Main: SystemExit exception caught (inner)...")
        return
    except:
        util.ERROR()
    finally:
        try:
            util.DEBUG_LOG('Main: SHUTTING DOWN...')
            dcm.storeDataCache()
            dcm.deinit()
            plexapp.util.INTERFACE.shutdownCache()
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
        except SystemExit:
            util.LOG("Main: SystemExit exception caught (outer)...")
        else:
            if util.KODI_VERSION_MAJOR == 18:
                realExit()
