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

    def watchStatusChanged(self):
        self.trigger('changed.watchstatus')

    def actionStop(self):
        self.stopPlayback()

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

    def stopPlayback(self):
        LOG('Monitor: Stopping media playback')
        xbmc.Player().stop()

    def onScreensaverActivated(self):
        LOG("Monitor: OnScreensaverActivated")
        self.trigger('screensaver.activated')
        if getSetting('player_stop_on_screensaver', False) and xbmc.Player().isPlayingVideo():
            self.stopPlayback()

    def onScreensaverDeactivated(self):
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


MONITOR = UtilityMonitor()