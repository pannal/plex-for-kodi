# -*- coding: utf-8 -*-
from __future__ import absolute_import

# noinspection PyUnresolvedReferences
from lib.kodi_util import xbmc, ADDON, getGlobalProperty, setGlobalProperty, FROM_KODI_REPOSITORY
from lib.update_checker import update_loop
from lib.logging import service_log


def main():
    if getGlobalProperty('service.started'):
        # Prevent add-on updates from starting a new version of the addon
        return

    service_log('Started', realm="Service")
    setGlobalProperty('service.started', '1', wait=True)

    if ADDON.getSetting('kiosk.mode') == 'true':
        xbmc.log('script.plexmod: Starting from service (Kiosk Mode)', xbmc.LOGINFO)
        delay = ADDON.getSetting('kiosk.delay') or "0"
        xbmc.executebuiltin('RunScript(script.plexmod,1{})'.format(",{}".format(delay) if delay != "0" else ""))

    if not FROM_KODI_REPOSITORY and ADDON.getSetting('auto_update_check') != "false":
        update_loop()

if __name__ == '__main__':
    main()
    service_log("Exited", realm="Service")
