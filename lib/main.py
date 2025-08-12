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
    global quitKodi, restart, exit_timer_started

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

                        # store previous account ID for fast user switch
                        if oldAccID and oldAccID != plexapp.ACCOUNT.ID:
                            util.setSetting('previous_user', oldAccID)

                    closeOption = "exit"
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
                            # store last user ID
                            util.DEBUG_LOG('Main: Switching users...: {}', plexapp.ACCOUNT.ID)
                            plexapp.ACCOUNT.isAuthenticated = False
                            fromSwitch = True
                        elif isinstance(closeOption, dict):
                            if closeOption.get('fast_switch'):
                                uid = closeOption['fast_switch']
                                util.DEBUG_LOG('Main: Fast-Switching users...: {}', uid)
                                util.setSetting('previous_user', plexapp.ACCOUNT.ID)
                                with busy.BusySignalContext(plexapp.util.APP, "account:response"):
                                    if plexapp.ACCOUNT.switchHomeUser(uid) and plexapp.ACCOUNT.switchUser:
                                        util.DEBUG_LOG('Waiting for user change...')

                        elif closeOption == 'recompile':
                            render_templates(force=True)
                            util.LOG("Restarting Home")
                            continue
                        elif closeOption == 'restart':
                            util.LOG("Restarting Addon")
                            restart = True
                            return
                    finally:
                        if closeOption in ("quit", "exit", "restart"):
                            util.DEBUG_LOG("Main: Starting hard exit timer of {} seconds...", util.addonSettings.maxShutdownWait)
                            exit_timer.start()
                            exit_timer_started = True
                        windowutils.shutdownHome()
                        BACKGROUND.activate()
                        background.setShutdown()
                        gc.collect(2)

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
            return

        if util.KODI_VERSION_MAJOR == 18:
            realExit()
