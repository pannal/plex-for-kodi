# coding=utf-8
import os
import datetime
import json

from lib.kodi_util import (xbmc, xbmcgui, ADDON, IPCTimeoutException, waitForGPEmpty,
                           setGlobalProperty, getGlobalProperty, KODI_VERSION_MAJOR)
from lib.settings_util import getSetting, setSetting
from lib.i18n import T
from lib.logging import service_log as log


def update_loop():
    # update checker and auto update logic
    from lib.updater import get_updater, ServiceMonitor, UpdateException, UpdaterSkipException

    monitor = ServiceMonitor()
    last_update_check = getSetting('last_update_check', datetime.datetime.fromtimestamp(0))
    check_interval = datetime.timedelta(hours=getSetting('update_interval_hours', 4))
    check_immediate = getSetting('update_check_startup', True)
    mode = getSetting('update_source', 'repository')

    updater = get_updater(mode)(branch='develop_kodi21' if KODI_VERSION_MAJOR > 18 else 'addon_kodi18')

    def should_check():
        return not any([
            xbmc.Player().isPlaying(),
            getGlobalProperty('running') != '1',
            getGlobalProperty('started') != '1',
            getGlobalProperty('is_active') != '1',
            getGlobalProperty('waiting_for_start')
        ])

    def disable_enable_addon():
        log("Toggling")
        try:
            xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
                                     'params': {'addonid': 'script.plexmod', 'enabled': False}}))
            xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
                                     'params': {'addonid': 'script.plexmod', 'enabled': True}}))
        except:
            raise

    while not getGlobalProperty('running') and not monitor.abortRequested():
        if monitor.waitForAbort(1):
            return

    log('Checking for updates periodically')

    while not monitor.abortRequested():
        now = datetime.datetime.now()

        # try consuming an update mode change
        mode_change = getGlobalProperty('update_source_changed', consume=True)
        allow_downgrade = False
        if mode_change and mode_change != mode:
            updater = get_updater(mode_change)(branch='develop_kodi21' if KODI_VERSION_MAJOR > 18 else 'addon_kodi18')
            mode = mode_change
            allow_downgrade = True
            check_immediate = True

        if (last_update_check + check_interval <= now or check_immediate) and not monitor.sleeping:
            if should_check():
                addon_version = ADDON.getAddonInfo('version')
                try:
                    if check_immediate:
                        check_immediate = False

                    log('Checking for updates')
                    update_version = updater.check(addon_version, allow_downgrade=allow_downgrade)

                    last_update_check = datetime.datetime.now()
                    setSetting('last_update_check', last_update_check)

                    if update_version:
                        log("Update found: {}".format(update_version))
                        # notify user in main app and wait for response
                        setGlobalProperty('update_is_downgrade', updater.is_downgrade and '1' or '', wait=True)
                        setGlobalProperty('update_available', update_version, wait=True)

                        try:
                            resp = getGlobalProperty('update_response', consume=True, wait=True)
                        except IPCTimeoutException:
                            # timed out
                            raise UpdateException('No user response')

                        log("User response: {}".format(resp))

                        if resp == "commence":
                            # wait for UI to close
                            try:
                                waitForGPEmpty('running', timeout=200)
                            except IPCTimeoutException:
                                raise UpdateException('Timeout waiting for UI to close')
                        else:
                            raise UpdaterSkipException()

                        pd = xbmcgui.DialogProgressBG()
                        pd.create("Update", message="Downloading")
                        had_already = os.path.exists(updater.archive_path)
                        if not had_already:
                            log("Update found: {}, downloading".format(update_version))
                            zip_loc = updater.download()

                            if zip_loc:
                                log("Update zip downloaded to: {}".format(zip_loc))
                        else:
                            log("Update {} previously downloaded, using previous zip".format(update_version))

                        pd.update(25, message="Unpacking")

                        dir_loc = updater.unpack()

                        has_major_changes = updater.get_major_changes()

                        pd.update(50, message="Installing")

                        if dir_loc:
                            dest_loc = updater.install(dir_loc)
                            if dest_loc:
                                log("Version {} installed. Major changes: {}".format(update_version,
                                                                                     has_major_changes))
                                pd.update(75, message="Cleaning up")
                                updater.cleanup()
                                pd.update(100, message="Preparing to start")
                                monitor.waitForAbort(1.0)

                                do_start = True
                                if has_major_changes:
                                    kw = {}
                                    if KODI_VERSION_MAJOR >= 20:
                                        kw = {'defaultbutton': xbmcgui.DLG_YESNO_YES_BTN}
                                    do_start = xbmcgui.Dialog().yesno(
                                        T(33681, 'Major changes detected'),
                                        T(33682, 'The update {} has major changes. '
                                                 'A Kodi restart could be necessary. You can still try running the'
                                                 ' addon, but it isn\'t guaranteed to be stable, especially when you\'ve '
                                                 'downgraded. Do you still want to run the addon?').format(update_version),
                                        nolabel=T(32329, "No"),
                                        yeslabel=T(32328, "Yes"),
                                        **kw
                                    )

                                xbmc.executebuiltin('UpdateLocalAddons', True)
                                xbmc.executebuiltin('ActivateWindow(Home)', True)
                                pd.close()
                                del pd
                                #disable_enable_addon()

                                if do_start:
                                    xbmc.executebuiltin('RunScript(script.plexmod)')

                except UpdateException as e:
                    log(e, xbmc.LOGWARNING)

                except UpdaterSkipException:
                    log("Update skipped")

                finally:
                    setGlobalProperty('update_available', '')
                    setGlobalProperty('update_response', '')
                    setGlobalProperty('update_source_changed', '')
                    setGlobalProperty('update_is_downgrade', '')

        # tick every two seconds if home or settings windows are active, otherwise every 10
        interval = getGlobalProperty('active_window') in ("HomeWindow", "SettingsWindow") and 2 or 10
        if monitor.waitForAbort(interval):
            break

        if not getSetting('auto_update_check', True):
            break
