# coding=utf-8
import os
import _strptime
import datetime
import json
import traceback

import lib.kodi_util
# noinspection PyUnresolvedReferences
from lib.kodi_util import xbmc, xbmcgui, xbmcaddon, ICON_PATH, KODI_VERSION_MAJOR
from lib.settings_util import getSetting, setSetting
from lib.properties import IPCTimeoutException, waitForGPEmpty, setGlobalProperty, getGlobalProperty
from lib.updater import get_updater, UpdateException, UpdaterSkipException
from lib.addonsettings import addonSettings
from lib.i18n import T
from lib.logging import service_log as log

class ServiceMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self, *args, **kwargs)
        self.device_sleeping = False

    def onNotification(self, sender, method, data):
        if sender == "xbmc" and method == "System.OnSleep":
            self.device_sleeping = True

        elif sender == "xbmc" and method == "System.OnWake":
            self.device_sleeping = False

MONITOR = ServiceMonitor()


def disable_enable_addon():
    log("Toggling")
    try:
        xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
                                 'params': {'addonid': 'script.plexmod', 'enabled': False}}))
        xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'Addons.SetAddonEnabled',
                                 'params': {'addonid': 'script.plexmod', 'enabled': True}}))
    except:
        raise


def update_loop():
    last_update_check = getSetting('last_update_check', datetime.datetime.fromtimestamp(0))
    check_interval = datetime.timedelta(hours=getSetting('update_interval_hours', 4))
    check_immediate = getSetting('update_check_startup', True)
    branch = getSetting('update_branch', "develop_kodi21")
    mode = getSetting('update_source', 'repository')
    setGlobalProperty("update_available", '')

    updater = get_updater(mode)(branch=branch if KODI_VERSION_MAJOR > 18 else 'addon_kodi18')

    while not getGlobalProperty('running') and not MONITOR.abortRequested():
        if MONITOR.waitForAbort(0.1):
            break

    log('Checking for updates periodically (last: {})'.format(str(last_update_check)))

    while not MONITOR.abortRequested():
        now = datetime.datetime.now()

        # try consuming an update mode change
        mode_change = getGlobalProperty('update_source_changed', consume=True)
        allow_downgrade = False
        ui_trigger_update = False
        if mode_change and mode_change != mode:
            updater = get_updater(mode_change)(branch=branch if KODI_VERSION_MAJOR > 18 else 'addon_kodi18')
            mode = mode_change
            allow_downgrade = True
            check_immediate = True
        else:
            ui_trigger_update = getGlobalProperty('update_requested', consume=True, timeout=600)

        if getSetting('last_update_check', datetime.datetime.fromtimestamp(0)) != last_update_check:
            setSetting('last_update_check', last_update_check)

        if (last_update_check + check_interval <= now or check_immediate or ui_trigger_update) and not MONITOR.device_sleeping:
            if not any([
                    xbmc.Player().isPlaying(),
                    getGlobalProperty('running') != '1',
                    getGlobalProperty('started') != '1',
                    getGlobalProperty('is_active') != '1',
                    getGlobalProperty('waiting_for_start')
                ]):
                addon_version = lib.kodi_util.ADDON.getAddonInfo('version')
                try:
                    pd = None
                    if check_immediate:
                        check_immediate = False

                    if not ui_trigger_update or not updater.remote_version:
                        log('Checking for updates')
                        update_version = updater.check(addon_version, allow_downgrade=allow_downgrade)
                        log('Current: {}, Latest: {}, Update/Sidegrade/Downgrade: {}'.format(addon_version,
                                                                                             updater.remote_version,
                                                                                             update_version))
                    else:
                        update_version = updater.remote_version if addon_version != updater.remote_version else None

                    last_update_check = datetime.datetime.now()
                    setSetting('last_update_check', last_update_check)
                    setGlobalProperty('last_update_check', last_update_check.strftime('%Y-%m-%dT%H:%M:%S.%f'))

                    if update_version:
                        log("Update found: {}".format(update_version))
                        # get github ref for update
                        if not ui_trigger_update and not updater.remote_ref:
                            ref = updater.get_ref()
                            if ref:
                                log('Found remote ref for {}: {}'.format(update_version, ref))

                        # notify user in main app and wait for response
                        setGlobalProperty('update_is_downgrade', updater.is_downgrade and '1' or '', wait=True)
                        setGlobalProperty('update_available', update_version, wait=True)
                        setGlobalProperty('notify_update', update_version, wait=True)
                        setGlobalProperty('update_changelog', updater.remote_changelog, wait=True)

                        try:
                            resp = getGlobalProperty('update_response', consume=True, wait=True)
                        except IPCTimeoutException:
                            # timed out
                            raise UpdaterSkipException('No user response')

                        log("User response: {}".format(resp))

                        if resp == "commence":
                            # wait for UI to close
                            waitForSecs = (addonSettings.requestsTimeoutConnect * addonSettings.maxRetries1
                                           + addonSettings.requestsTimeoutRead + 2)
                            log("Waiting for UI to close for: {}s".format(waitForSecs))
                            setGlobalProperty("update_available", '', wait=True)
                            try:
                                waitForGPEmpty('running', timeout=waitForSecs * 10)
                            except IPCTimeoutException:
                                #raise UpdateException('Timeout waiting for UI to close')
                                log('Timeout waiting for UI to close')
                                try:
                                    xbmc.executebuiltin('StopScript(script.plexmod)')
                                except:
                                    pass
                        else:
                            raise UpdaterSkipException()

                        pd = xbmcgui.DialogProgressBG()
                        pd.create("Update", message="Downloading")
                        had_already = os.path.exists(updater.archive_path)
                        if not had_already:
                            log("Update found: {}, downloading (ref: {})".format(update_version, ref))
                            zip_loc = updater.download()

                            if zip_loc:
                                log("Update zip downloaded to: {}".format(zip_loc))
                        else:
                            log("Update {} previously downloaded, using previous zip".format(update_version))

                        pd.update(25, message="Unpacking")

                        dir_loc = updater.unpack()

                        pd.update(35, message="Calculating changes")

                        major_changes = updater.get_major_changes()

                        pd.update(50, message="Installing")

                        if dir_loc:
                            dest_loc = updater.install(dir_loc)
                            if dest_loc:
                                log("Version {} installed. Major changes: {}".format(update_version,
                                                                                     major_changes))
                                pd.update(75, message="Cleaning up")
                                updater.cleanup()
                                pd.update(100, message="Preparing to start")
                                if MONITOR.waitForAbort(1.0):
                                    break

                                do_start = True
                                if "service" in major_changes or "updater" in major_changes or "language" in major_changes:
                                    log("Major changes detected, prompting the user: {}".format(major_changes))

                                    kw = {}
                                    if KODI_VERSION_MAJOR >= 20:
                                        kw = {'defaultbutton': xbmcgui.DLG_YESNO_YES_BTN}
                                    do_start = xbmcgui.Dialog().yesno(
                                        T(33681, 'Service updated')
                                        if "service" in major_changes or "updater" in major_changes else
                                        T(33687, 'Translation updated'),
                                        (T(33682, 'The update {} has had changes to the updater itself. In '
                                                  'order for the updated updater service to work, a Kodi restart is '
                                                  'necessary. The addon will work normally, though. Do you still '
                                                  'want to run the addon?')
                                         if "service" in major_changes or "updater" in major_changes else
                                         T(33688, 'The currently in-use translation has been updated. In '
                                                  'order to load the new translation, a Kodi restart is necessary. '
                                                  'The addon will still run properly, but you might see badly or '
                                                  'untranslated strings. Do you still want to run the addon?')
                                         ).format(update_version),
                                        nolabel=T(32329, "No"),
                                        yeslabel=T(32328, "Yes"),
                                        **kw
                                    )

                                xbmc.executebuiltin('UpdateLocalAddons', True)
                                xbmc.executebuiltin('ActivateWindow(Home)', True)
                                pd.close()
                                del pd
                                #disable_enable_addon()

                                # reload addon info
                                lib.kodi_util.ADDON = xbmcaddon.Addon()

                                if do_start:
                                    xbmc.executebuiltin('RunScript(script.plexmod,0,0,1)')

                                if "updater" in major_changes or "service" in major_changes:
                                    return True

                except UpdateException as e:
                    log(e, xbmc.LOGWARNING)

                except UpdaterSkipException:
                    log("Update skipped")

                except Exception as e:
                    log(traceback.format_exc(), xbmc.LOGERROR)
                    xbmc.executebuiltin('Notification({0},"{1}",{2},{3})'.format("Update",
                                                                               "Update failed, see log, not starting.",
                                                                               5000,
                                                                               ICON_PATH))

                finally:
                    setGlobalProperty('update_response', '')
                    setGlobalProperty('notify_update', '')
                    setGlobalProperty('update_source_changed', '')
                    setGlobalProperty('update_is_downgrade', '')
                    # lel
                    try:
                        if pd:
                            try:
                                pd.close()
                                del pd
                            except:
                                pass
                    except:
                        pass

        # tick every two seconds if home or settings windows are active, otherwise every 10
        interval = getGlobalProperty('active_window') in ("HomeWindow", "SettingsWindow") and 2.0 or 10.0
        if MONITOR.waitForAbort(interval):
            break

        if not getSetting('auto_update_check', True):
            break
