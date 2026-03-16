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
        self.wait_interval = 0.1
        self.ignore_ssevent = False

    def watchStatusChanged(self):
        self.trigger('changed.watchstatus')

    def actionStop(self):
        if xbmc.Player().isPlayingVideo():
            self.stopPlayback()
            return True
        return False

    def actionHome(self):
        from plexnet import plexapp
        from .windows import windowutils
        plexapp.util.APP.trigger('close.windows')
        plexapp.util.APP.trigger('close.dialogs')
        windowutils.HOME.go_root = True
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
            self.trigger('system.wakeup')
        elif sender == "xbmc" and method == "System.OnQuit":
            from .windows import windowutils
            LOG("OnQuit: Stopping playback")
            self.trigger('system.exit')
            self.actionStop()
            LOG("OnQuit: Closing Home")
            windowutils.HOME.closeOption = "kodi_exit"
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