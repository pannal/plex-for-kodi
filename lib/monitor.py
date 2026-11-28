# coding=utf-8
from kodi_six import xbmc
from .settings_util import getSetting
from .properties_core import _setGlobalProperty
from plexnet import signalsmixin
from .logging import log as LOG


class UtilityMonitor(xbmc.Monitor, signalsmixin.SignalsMixin):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self, *args, **kwargs)
        signalsmixin.SignalsMixin.__init__(self)
        self.device_sleeping = False
        self.tv_standby = False
        self.wait_interval = 0.1
        self.ignore_ssevent = False
        self._skin_reloading = False

    def watchStatusChanged(self):
        self.trigger('changed.watchstatus')

    def actionStop(self):
        if xbmc.Player().isPlayingVideo():
            self.stopPlayback()
            return True
        return False

    def actionHome(self):
        from plexnet import plexapp
        from .windows import kodigui, windowutils
        plexapp.util.APP.trigger('close.windows')
        plexapp.util.APP.trigger('close.dialogs')
        windowutils.HOME.go_root = True
        # wait for sub-windows to actually close before showing HOME
        ct = 0
        home_wid = windowutils.HOME._winID
        while home_wid and kodigui.xbmcgui.getCurrentWindowId() != home_wid and ct < self.waitAmount(2):
            self.waitFor()
            ct += 1
        windowutils.HOME.show()

    def actionQuit(self):
        LOG('OnSleep: Exit Kodi')
        xbmc.executebuiltin('Quit')

    def actionReboot(self):
        LOG('OnSleep: Reboot')
        xbmc.restart()

    def actionShutdown(self):
        LOG('OnSleep: Shutdown')
        xbmc.shutdown()

    def actionHibernate(self):
        LOG('OnSleep: Hibernate')
        xbmc.executebuiltin('Hibernate')

    def actionSuspend(self):
        LOG('OnSleep: Suspend')
        xbmc.executebuiltin('Suspend')

    def actionCecstandby(self):
        LOG('OnSleep: CEC Standby')
        xbmc.executebuiltin('CECStandby')

    def actionLogoff(self):
        LOG('OnSleep: Sign Out')
        xbmc.executebuiltin('System.LogOff')

    def onNotification(self, sender, method, data):
        if method == "Application.OnVolumeChanged":
            return

        LOG("Notification: {} {} {}".format(sender, method, data))
        if sender == 'script.plexmod' and method.endswith('RESTORE'):
            from .windows import kodigui, windowutils

            def exit_mainloop():
                LOG("Addon never properly started, can't reactivate; stopping and restarting")
                try:
                    windowutils.HOME.doClose()
                except:
                    xbmc.executebuiltin('StopScript(script.plexmod)')
                    xbmc.executebuiltin('RunScript(script.plexmod)')

            if not kodigui.BaseFunctions.lastWinID:
                LOG("No lastWinID, restarting")
                exit_mainloop()
                return
            if kodigui.BaseFunctions.lastWinID > 13000:
                from lib.util import reInitAddon
                LOG("Trying to re-activate addon via window ID: {}".format(kodigui.BaseFunctions.lastWinID))
                reInitAddon()
                _setGlobalProperty('is_active', '1')
                xbmc.executebuiltin('ReplaceWindow({0})'.format(kodigui.BaseFunctions.lastWinID))
                return
            else:
                LOG("LastWinID was: %s, restarting" % kodigui.BaseFunctions.lastWinID)
                exit_mainloop()
                return

        elif sender == "xbmc" and method == "System.OnSleep":
            self.device_sleeping = True
            if getSetting('action_on_sleep', "none") != "none":
                getattr(self, "action{}".format(getSetting('action_on_sleep', "none").capitalize()))()
            self.trigger('system.sleep')

        elif sender == "xbmc" and method == "System.OnWake":
            self.device_sleeping = False
            self.tv_standby = False
            self.trigger('system.wakeup')

        elif sender == "xbmc" and method in ("Other.OnTVStandby", "Other.OnCECSourceDeactivated"):
            # announced by p3i/CE Kodi when the TV sends a CEC standby or another
            # CEC device becomes the active source; not available on stock Kodi
            LOG("Monitor: TV/CEC display gone ({0})".format(method))
            self.tv_standby = True
            self.trigger('tv.standby')

        elif sender == "xbmc" and method == "Other.OnCECSourceActivated":
            if self.tv_standby:
                LOG("Monitor: CEC source re-activated")
            self.tv_standby = False
        elif sender == "xbmc" and method == "System.OnQuit":
            from .windows import windowutils
            LOG("OnQuit: Stopping playback")
            self.trigger('system.exit')
            self.actionStop()
            LOG("OnQuit: Closing Home")
            windowutils.HOME.closeOption = "kodi_exit"
            windowutils.HOME.doClose()
            return

        elif sender == "xbmc" and method == "GUI.OnSkinUnloading":
            # The underlying Kodi skin is being torn down (most commonly a background
            # skin-addon auto-update triggering ReloadSkin). The window manager's
            # DeInitialize() Close()s and FreeResources() our windows, but Kodi's python
            # binding never clears bModal on deinit (Window::OnDeinitWindow) - so HOME's
            # native doModal() keeps spinning over a gutted window and the UI freezes.
            # Arm the restart now so that however doModal eventually unblocks, _main is
            # already routed to "restart"; we force the unblock on OnSkinLoaded.
            from .windows import windowutils
            LOG("Skin unloading: arming UI restart for after the reload")
            self._skin_reloading = True
            if windowutils.HOME:
                windowutils.HOME.closeOption = "restart"

        elif sender == "xbmc" and method in ("GUI.OnSkinLoaded", "GUI.OnSkinLoadFailed"):
            # Skin reload settled (loaded, or failed outright). Recover via the same
            # proven path as OnQuit: doClose() HOME so its native close() clears bModal
            # and pulses doModal() out, _main sees the armed "restart" and returns, and
            # the atexit handler RunScript()s us back from a clean state. We handle the
            # failure case too so we don't hang if the default skin itself fails (the
            # non-default fallback already reloads and fires OnSkinLoaded by then).
            if not self._skin_reloading:
                return
            self._skin_reloading = False
            from .windows import windowutils
            if windowutils.HOME:
                LOG("Skin reload settled ({}): restarting addon to recover UI", method)
                windowutils.HOME.closeOption = "restart"
                windowutils.HOME.doClose()
            return

    def stopPlayback(self):
        LOG('Monitor: Stopping media playback')
        xbmc.Player().stop()

    def onScreensaverActivated(self):
        if self.ignore_ssevent:
            self.ignore_ssevent = False
            return
        LOG("Monitor: OnScreensaverActivated")
        if getSetting('player_stop_on_screensaver'):
            self.ignore_ssevent = self.actionStop()

        if getSetting('onss_library_back_home'):
            LOG("Monitor: OnScreensaverActivated: Triggering going home")
            self.trigger('library.back_home')

        # we've stopped playback during an onScreensaverActivated event, which deactivates the screensaver. Reactivate.
        if self.ignore_ssevent:
            xbmc.executebuiltin('activatescreensaver')

        self.trigger('screensaver.activated')

    def onScreensaverDeactivated(self):
        if self.ignore_ssevent:
            return
        LOG("Monitor: OnScreensaverDeactivated")
        self.trigger('screensaver.deactivated')

    def onDPMSActivated(self):
        LOG("Monitor: OnDPMSActivated")
        self.trigger('dpms.activated')
        #self.stopPlayback()

    def onDPMSDeactivated(self):
        LOG("Monitor: OnDPMSDeactivated")
        self.trigger('dpms.deactivated')
        #self.stopPlayback()

    def onSettingsChanged(self):
        """ unused stub, but works if needed """
        pass

    def waitFor(self, interval=None):
        if interval is None:
            interval = self.wait_interval
        return self.waitForAbort(interval)

    def waitAmount(self, amount, interval=None):
        if interval is None:
            interval = self.wait_interval
        return amount / float(interval)


MONITOR = UtilityMonitor()