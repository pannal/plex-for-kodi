# coding=utf-8
from __future__ import absolute_import
import logging
import tempfile
import sys

from lib.logging import log, KodiLogProxyHandler
# noinspection PyUnresolvedReferences
from lib.kodi_util import translatePath, xbmc, xbmcgui
from lib.properties import getGlobalProperty, setGlobalProperty
from tendo_singleton import SingleInstance, SingleInstanceException

# tempfile's standard temp dirs won't work on specific OS's (android)
tempfile.tempdir = translatePath("special://temp/")

# add custom logger for tendo.singleton, so we can capture its messages
logger = logging.getLogger("tendo.singleton")
logger.addHandler(KodiLogProxyHandler(level=logging.DEBUG))
logger.setLevel(logging.DEBUG)


from_kiosk = False
kiosk_always = False
boot_delay = False
argvlen = len(sys.argv)
if argvlen > 1:
    from_kiosk = int(sys.argv[1]) > 0
    kiosk_always = int(sys.argv[1]) > 1
    if argvlen > 2:
        boot_delay = int(sys.argv[2])
        if argvlen > 3:
            update_successful = bool(int(sys.argv[3]))

started = False
set_waiting_for_start = False
try:
    # reactivate/maximize
    if getGlobalProperty('running'):
        try:
            log('Main: script.plexmod: Trying to reactivate minimized addon')
            xbmc.executebuiltin('NotifyAll({0},{1},{2})'.format('script.plexmod', 'RESTORE', '{}'))
        except:
            log('Main: script.plexmod: Already running or faulty, couldn\'t reactivate other instance, exiting.')
        else:
            sys.exit(0)
    else:
        # addon not started
        if not getGlobalProperty('started'):
            # we're waiting for the addon to start, immediate start was requested
            if getGlobalProperty('waiting_for_start'):
                setGlobalProperty('waiting_for_start', '', wait=True)
                log('Main: script.plexmod: Currently waiting for start, immediate start was requested.')
                sys.exit(0)

            # only allow a single instance
            with SingleInstance("pm4k"):
                started = True
                skip_ensure_home = False
                from lib import main

                # called from service.py?
                if from_kiosk:
                    waited = 0
                    if boot_delay:
                        set_waiting_for_start = True
                        setGlobalProperty('waiting_for_start', '1', wait=True)
                        log('Main: script.plexmod: Delaying start for {}s.', boot_delay)
                        while (not main.util.MONITOR.abortRequested() and waited < boot_delay
                               and getGlobalProperty('waiting_for_start')):
                            waited += 0.1
                            main.util.MONITOR.waitForAbort(0.1)

                    # boot delay canceled by immediate start
                    if waited < boot_delay:
                        log('Main: script.plexmod: Forced start before auto-start delay ({:.1f}/{} s).',
                            waited, boot_delay)
                        skip_ensure_home = True

                    if kiosk_always:
                        skip_ensure_home = True

                    waited = 0
                    # wait 120s if we're not at home right now or have an active dialog until starting the addon
                    if not skip_ensure_home and \
                            (xbmcgui.getCurrentWindowId() > 10000 or xbmcgui.getCurrentWindowDialogId() > 9999):
                        setGlobalProperty('waiting_for_start', '1', wait=True)

                        while getGlobalProperty('waiting_for_start') and not main.util.MONITOR.abortRequested() and \
                                waited < 120 and (
                                xbmcgui.getCurrentWindowId() > 10000 or xbmcgui.getCurrentWindowDialogId() > 9999):
                            if waited == 0:
                                log('Main: script.plexmod: Waiting for auto-start; we\'re not home or have an '
                                    'active dialog.')
                            waited += 0.1
                            main.util.MONITOR.waitForAbort(0.1)

                        if from_kiosk:
                            # no immediate start requested
                            main.util.MONITOR.waitForAbort(0.5)

                setGlobalProperty('waiting_for_start', '', wait=True)
                setGlobalProperty('started', '1', wait=True)

                main.main()
        else:
            log('Main: script.plexmod: Already running, exiting')

except SingleInstanceException:
    pass

except SystemExit as e:
    if e.code not in (-1, 0):
        raise

finally:
    if started:
        setGlobalProperty('started', '')
    if set_waiting_for_start:
        setGlobalProperty('waiting_for_start', '')
