from __future__ import absolute_import
import sys
import platform
import traceback
import uuid
import json
import threading
import time
import requests
import six

from kodi_six import xbmc, xbmcaddon

from plexnet import plexapp, myplex, util as plexnet_util, asyncadapter, http as pnhttp

from .playback_utils import PlaybackManager
from . windows.settings import PlayedThresholdSetting
from . import util
from six.moves import range

if six.PY2:
    _Event = threading._Event
else:
    _Event = threading.Event


class PlexTimer(plexapp.util.Timer):
    def shouldAbort(self):
        return util.MONITOR.abortRequested()


def abortFlag():
    return util.MONITOR.abortRequested()


plexapp.util.setTimer(PlexTimer)
plexapp.setAbortFlagFunction(abortFlag)

maxVideoRes = plexapp.Res((3840, 2160))  # INTERFACE.globals["supports4k"] and plexapp.Res((3840, 2160)) or plexapp.Res((1920, 1080))

CLIENT_ID = util.getSetting('client.ID')
if not CLIENT_ID:
    CLIENT_ID = str(uuid.uuid4())
    util.setSetting('client.ID', CLIENT_ID)


def defaultUserAgent():
    """Return a string representing the default user agent."""
    _implementation = platform.python_implementation()

    if _implementation == 'CPython':
        _implementation_version = platform.python_version()
    elif _implementation == 'PyPy':
        _implementation_version = '%s.%s.%s' % (sys.pypy_version_info.major,
                                                sys.pypy_version_info.minor,
                                                sys.pypy_version_info.micro)
        if sys.pypy_version_info.releaselevel != 'final':
            _implementation_version = ''.join([_implementation_version, sys.pypy_version_info.releaselevel])
    elif _implementation == 'Jython':
        _implementation_version = platform.python_version()  # Complete Guess
    elif _implementation == 'IronPython':
        _implementation_version = platform.python_version()  # Complete Guess
    else:
        _implementation_version = 'Unknown'

    try:
        p_system = platform.system()
        p_release = platform.release()
    except IOError:
        p_system = 'Unknown'
        p_release = 'Unknown'

    return " ".join(['%s/%s' % ('PM4K', util.ADDON.getAddonInfo('version')),
                     '%s/%s' % ('Kodi', xbmc.getInfoLabel('System.BuildVersion').replace(' ', '-')),
                     '%s/%s' % (_implementation, _implementation_version),
                     '%s/%s' % (p_system, p_release)])


class PlexInterface(plexapp.AppInterface):
    _regs = {
        None: {},
    }
    _globals = {
        'platform': 'Kodi',
        'appVersionStr': util.ADDON.getAddonInfo('version'),
        'clientIdentifier': CLIENT_ID,
        'platformVersion': xbmc.getInfoLabel('System.BuildVersion'),
        'product': 'PM4K',
        'provides': 'player',
        'device': util.getPlatform() or plexapp.PLATFORM,
        'model': 'Unknown',
        'friendlyName': util.rpc.Settings.GetSettingValue(setting='services.devicename').get('value') or 'Kodi',
        'supports1080p60': True,
        'vp9Support': True,
        'audioChannels': '2.0',
        'transcodeVideoQualities': [
            "10", "20", "30", "30", "40", "60", "60", "75", "100", "60", "75", "90", "100", "100"
        ],
        'transcodeVideoResolutions': [
            plexapp.Res((220, 180)),
            plexapp.Res((220, 128)),
            plexapp.Res((284, 160)),
            plexapp.Res((420, 240)),
            plexapp.Res((576, 320)),
            plexapp.Res((720, 480)),
            plexapp.Res((1024, 768)),
            plexapp.Res((1280, 720)),
            plexapp.Res((1280, 720)),
            maxVideoRes, maxVideoRes, maxVideoRes, maxVideoRes, maxVideoRes
        ],
        'transcodeVideoBitrates': [
            "64", "96", "208", "320", "720", "1500", "2000", "3000", "4000", "8000", "10000", "12000", "20000", "0"
        ],
        'deviceInfo': plexapp.DeviceInfo()
    }

    bingeModeManager = None

    def getPreference(self, pref, default=None):
        if pref == 'manual_connections':
            return self.getManualConnections()
        else:
            return util.getSetting(pref, default)

    def getManualConnections(self):
        conns = []
        for i in range(2):
            ip = util.getSetting('manual_ip_{0}'.format(i))
            if not ip:
                continue
            port = util.getSetting('manual_port_{0}'.format(i), 32400)
            conns.append({'connection': ip, 'port': port})
        return json.dumps(conns)

    def setPreference(self, pref, value):
        util.setSetting(pref, value)

    def getRegistry(self, reg, default=None, sec=None):
        if sec == 'myplex' and reg == 'MyPlexAccount':
            ret = util.getSetting('{0}.{1}'.format(sec, reg), default)
            if ret:
                return ret
            return json.dumps({'authToken': util.getSetting('auth.token')})
        else:
            return util.getSetting('{0}.{1}'.format(sec, reg), default)

    def setRegistry(self, reg, value, sec=None):
        util.setSetting('{0}.{1}'.format(sec, reg), value)

    def clearRegistry(self, reg, sec=None):
        util.setSetting('{0}.{1}'.format(sec, reg), '')

    def addInitializer(self, sec):
        pass

    def clearInitializer(self, sec):
        pass

    def getGlobal(self, glbl, default=None):
        if glbl == 'transcodeVideoResolutions':
            maxres = self.getPreference('allow_4k', True) and plexapp.Res((3840, 2160)) or plexapp.Res((1920, 1080))
            self._globals['transcodeVideoResolutions'][-5:] = [maxres] * 5
        elif glbl == 'audioChannels':
            try:
                self._globals['audioChannels'] = \
                    util.CHANNELMAPPING[util.rpc.Settings.GetSettingValue(setting='audiooutput.channels').get('value')]
            except:
                util.DEBUG_LOG("Limiting audio channel definition to 2.0 due to error: %s" % traceback.format_exc())
                self._globals['audioChannels'] = "2.0"

        return self._globals.get(glbl, default)

    def getCapabilities(self):
        return ''

    def LOG(self, msg):
        util.DEBUG_LOG('API: {0}'.format(msg))

    def DEBUG_LOG(self, msg):
        self.LOG('DEBUG: {0}'.format(msg))

    def WARN_LOG(self, msg):
        self.LOG('WARNING: {0}'.format(msg))

    def ERROR_LOG(self, msg):
        self.LOG('ERROR: {0}'.format(msg))

    def ERROR(self, msg=None, err=None):
        if err:
            self.LOG('ERROR: {0} - {1}'.format(msg, getattr(err, "message", "Unknown Error")))
        else:
            util.ERROR()

    def supportsAudioStream(self, codec, channels):
        return True
        # if codec = invalid then return true

        # canDownmix = (m.globals["audioDownmix"][codec] <> invalid)
        # supportsSurroundSound = m.SupportsSurroundSound()

        # if not supportsSurroundSound and canDownmix then
        #     maxChannels = m.globals["audioDownmix"][codec]
        # else
        #     maxChannels = firstOf(m.globals["audioDecoders"][codec], 0)
        # end if

        # if maxChannels > 2 and not canDownmix and not supportsSurroundSound then
        #     ' It's a surround sound codec and we can't do surround sound
        #     supported = false
        # else if maxChannels = 0 or maxChannels < channels then
        #     ' The codec is either unsupported or can't handle the requested channels
        #     supported = false
        # else
        #     supported = true

        # return supported

    def supportsSurroundSound(self):
        return True

    def getQualityIndex(self, qualityType):
        if qualityType == self.QUALITY_LOCAL:
            return self.getPreference("local_quality", 13)
        elif qualityType == self.QUALITY_ONLINE:
            return self.getPreference("online_quality", 13)
        else:
            return self.getPreference("remote_quality", 13)

    def getMaxResolution(self, quality_type, allow4k=False):
        qualityIndex = self.getQualityIndex(quality_type)

        if qualityIndex >= 9:
            if self.getPreference('allow_4k', True):
                return allow4k and 2160 or 1088
            else:
                return 1088
        elif qualityIndex >= 6:
            return 720
        elif qualityIndex >= 5:
            return 480
        else:
            return 360

    def getThemeMusicValue(self):
        index = 10 - self.getPreference("theme_music", 5)
        if index > 0:
            return index * 10
        return 0

    def getPlayedThresholdValue(self):
        values = list(reversed(PlayedThresholdSetting.options))
        return int(values[self.getPreference("played_threshold", 1)].replace(" %", "")) / 100.0


def onSmartDiscoverLocalChange(value=None, **kwargs):
    plexnet_util.CHECK_LOCAL = value
    plexapp.refreshResources(True)


def onPreferLANChange(value=None, **kwargs):
    plexnet_util.LOCAL_OVER_SECURE = value
    plexapp.refreshResources(True)


def onPreferLocalChange(**kwargs):
    plexapp.refreshResources(True)


def onManualIPChange(**kwargs):
    plexapp.refreshResources(True)


plexapp.util.setInterface(PlexInterface())
plexapp.util.INTERFACE.playbackManager = PlaybackManager()
plexapp.util.APP.on('change:smart_discover_local', onSmartDiscoverLocalChange)
plexapp.util.APP.on('change:prefer_local', onPreferLANChange)
plexapp.util.APP.on('change:same_network', onPreferLocalChange)
plexapp.util.APP.on('change:manual_ip_0', onManualIPChange)
plexapp.util.APP.on('change:manual_ip_1', onManualIPChange)
plexapp.util.APP.on('change:manual_port_0', onManualIPChange)
plexapp.util.APP.on('change:manual_port_1', onManualIPChange)

plexapp.util.CHECK_LOCAL = util.getSetting('smart_discover_local', True)
plexapp.util.LOCAL_OVER_SECURE = util.getSetting('prefer_local', False)

# set requests timeout
TIMEOUT = float(util.advancedSettings.requestsTimeout)
CONNCHECK_TIMEOUT = float(util.advancedSettings.connCheckTimeout)
plexapp.util.TIMEOUT = TIMEOUT
plexapp.util.CONN_CHECK_TIMEOUT = asyncadapter.AsyncTimeout(CONNCHECK_TIMEOUT).setConnectTimeout(CONNCHECK_TIMEOUT)
plexapp.util.LAN_REACHABILITY_TIMEOUT = util.advancedSettings.localReachTimeout / 1000.0
pnhttp.DEFAULT_TIMEOUT = asyncadapter.AsyncTimeout(TIMEOUT).setConnectTimeout(TIMEOUT)
asyncadapter.DEFAULT_TIMEOUT = pnhttp.DEFAULT_TIMEOUT
plexapp.util.ACCEPT_LANGUAGE = util.ACCEPT_LANGUAGE_CODE
plexapp.setUserAgent(defaultUserAgent())


class CallbackEvent(plexapp.util.CompatEvent):
    def __init__(self, context, signal, timeout=15, *args, **kwargs):
        plexnet_util.Event.__init__(self, *args, **kwargs)
        self.start = time.time()
        self.context = context
        self.signal = signal
        self.timeout = timeout
        self.context.on(self.signal, self.set)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.wait()

    def __repr__(self):
        return '<{0}:{1}>'.format(self.__class__.__name__, self.signal)

    def set(self, **kwargs):
        plexnet_util.Event.set(self)

    def wait(self):
        if not plexnet_util.Event.wait(self, self.timeout):
            util.DEBUG_LOG('{0}: TIMED-OUT'.format(self))
        self.close()

    def triggeredOrTimedOut(self, timeout=None):
        try:
            if time.time() - self.start > self.timeout:
                util.DEBUG_LOG('{0}: TIMED-OUT'.format(self))
                return True

            if timeout:
                plexnet_util.Event.wait(self, timeout)
        finally:
            return self.isSet()

    def close(self):
        self.set()
        self.context.off(self.signal, self.set)


def init():
    util.DEBUG_LOG('Initializing...')

    with CallbackEvent(plexapp.util.APP, 'init'):
        util.DEBUG_LOG('Waiting for plexapp initialization...')
        plexapp.init()

    util.DEBUG_LOG('Account initialized: {}'.format(plexapp.ACCOUNT.ID))

    retry = True

    while retry:
        retry = False
        if not plexapp.ACCOUNT.authToken:
            util.DEBUG_LOG("No auth token, authorizing")
            token = authorize()

            if not token:
                util.DEBUG_LOG('FAILED TO AUTHORIZE')
                return False

            with CallbackEvent(plexapp.util.APP, 'account:response'):
                plexapp.ACCOUNT.validateToken(token, force_resource_refresh=True)
                util.DEBUG_LOG('Waiting for account initialization...')

        # if not PLEX:
        #     util.messageDialog('Connection Error', u'Unable to connect to any servers')
        #     util.DEBUG_LOG('SIGN IN: Failed to connect to any servers')
        #     return False

        # util.DEBUG_LOG('SIGN IN: Connected to server: {0} - {1}'.format(PLEX.friendlyName, PLEX.baseuri))
        success = requirePlexPass()
        if success == 'RETRY':
            retry = True
            continue

        return success


def requirePlexPass():
    return True
    # if not plexapp.ACCOUNT.hasPlexPass():
    #     from windows import signin, background
    #     background.setSplash(False)
    #     w = signin.SignInPlexPass.open()
    #     retry = w.retry
    #     del w
    #     util.DEBUG_LOG('PlexPass required. Signing out...')
    #     plexapp.ACCOUNT.signOut()
    #     plexapp.SERVERMANAGER.clearState()
    #     if retry:
    #         return 'RETRY'
    #     else:
    #         return False

    # return True


def authorize():
    from .windows import signin, background

    background.setSplash(False)

    back = signin.Background.create()

    pre = signin.PreSignInWindow.open()
    try:
        if not pre.doSignin:
            return None
    finally:
        del pre

    try:
        while True:
            pinLoginWindow = signin.PinLoginWindow.create()
            try:
                pl = myplex.PinLogin()
            except requests.ConnectionError:
                util.ERROR()
                util.messageDialog(util.T(32427, 'Failed'), util.T(32449, 'Sign-in failed. Cound not connect to plex.tv'))
                return

            pinLoginWindow.setPin(pl.pin)

            try:
                pl.startTokenPolling()
                while not pl.finished():
                    if pinLoginWindow.abort:
                        util.DEBUG_LOG('SIGN IN: Pin login aborted')
                        pl.abort()
                        return None
                    xbmc.sleep(100)
                else:
                    if not pl.expired():
                        if pl.authenticationToken:
                            pinLoginWindow.setLinking()
                            return pl.authenticationToken
                        else:
                            return None
            finally:
                pinLoginWindow.doClose()
                del pinLoginWindow

            if pl.expired():
                util.DEBUG_LOG('SIGN IN: Pin expired')
                expiredWindow = signin.ExpiredWindow.open()
                try:
                    if not expiredWindow.refresh:
                        util.DEBUG_LOG('SIGN IN: Pin refresh aborted')
                        return None
                finally:
                    del expiredWindow
    finally:
        back.doClose()
        del back
