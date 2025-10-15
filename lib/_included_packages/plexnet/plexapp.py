from __future__ import print_function, absolute_import
import platform
import uuid

from . import signalsmixin
from . import simpleobjects
from . import util
import six

Res = simpleobjects.Res
SERVERMANAGER = None
ACCOUNT = None
MANAGER = None

PLATFORM = util.X_PLEX_DEVICE


def init():
    global MANAGER, SERVERMANAGER, ACCOUNT
    from . import myplexaccount
    ACCOUNT = myplexaccount.ACCOUNT
    util.DEBUG_LOG("Waiting for account initialization...")
    ACCOUNT.init()
    from . import plexservermanager
    SERVERMANAGER = plexservermanager.MANAGER
    from . import myplexmanager
    util.MANAGER = MANAGER = myplexmanager.MANAGER
    util.ACCOUNT = ACCOUNT
    util.SERVERMANAGER = SERVERMANAGER
    util.DEBUG_LOG("Verifying account...")
    ACCOUNT.verifyAccount()


class App(signalsmixin.SignalsMixin):
    def __init__(self):
        signalsmixin.SignalsMixin.__init__(self)
        self.pendingRequests = {}
        self.initializers = {}
        self.timers = []
        from . import nowplayingmanager
        self.nowplayingmanager = nowplayingmanager.NowPlayingManager()

    def addTimer(self, timer):
        self.timers.append(timer)

    @property
    def serverManager(self):
        return SERVERMANAGER

    def startRequest(self, request, context, body=None, contentType=None):
        context.request = request

        started = request.startAsync(body=body, contentType=contentType, context=context)

        if started:
            requestID = context.request.getIdentity()
            self.pendingRequests[requestID] = context
        elif context.callback:
            context.callback(None, context)

        return started

    def onRequestTimeout(self, context):
        requestID = context.request.getIdentity()

        if requestID not in self.pendingRequests:
            return

        context.request.cancel()

        util.WARN_LOG("Request to {0} timed out after {1} sec".format(util.cleanToken(context.request.url), context.timeout))

        if context.callback:
            context.callback(None, context)

    def delRequest(self, request):
        requestID = request.getIdentity()
        if requestID not in self.pendingRequests:
            return

        del self.pendingRequests[requestID]

    def addInitializer(self, name):
        self.initializers[name] = True

    def clearInitializer(self, name):
        if name in self.initializers:
            del self.initializers[name]
            if self.isInitialized():
                self.onInitialized()

    def isInitialized(self):
        return not self.initializers

    def onInitialized(self):
        # Wire up a few of our own listeners
        # PlexServerManager()
        # self.on("change:user", callback.Callable(self.onAccountChange))

        self.trigger('init')

    def cancelAllTimers(self):
        for timer in self.timers:
            timer.cancel()

    def preShutdown(self):
        from . import http
        http.HttpRequest._cancel = True
        if self.pendingRequests:
            util.DEBUG_LOG('Closing down {0} App() requests...', lambda: len(self.pendingRequests))
            for k in list(self.pendingRequests.keys()):
                p = self.pendingRequests.get(k)
                if p:
                    p.request.cancel()

        if self.timers:
            util.DEBUG_LOG('Canceling App() timers...')
            self.cancelAllTimers()

        if SERVERMANAGER.selectedServer:
            util.DEBUG_LOG('Closing server...')
            SERVERMANAGER.selectedServer.close()

    def shutdown(self):
        if self.timers:
            util.DEBUG_LOG('Waiting for {0} App() timers: Started', lambda: len(self.timers))

            self.cancelAllTimers()

            for timer in self.timers:
                timer.join()

            util.DEBUG_LOG('Waiting for App() timers: Finished')


class DeviceInfo(object):
    def getCaptionsOption(self, key):
        return None


class AppInterface(object):
    QUALITY_LOCAL = 0
    QUALITY_REMOTE = 1
    QUALITY_ONLINE = 2

    _globals = {}

    def __init__(self):
        self.setQualities()

    def setQualities(self):
        # Calculate the max quality based on 4k support
        if self._globals.get("supports4k"):
            maxQuality = simpleobjects.AttributeDict({
                'height': 2160,
                'maxHeight': 2160,
                'origHeight': 1080
            })
            maxResolution = self._globals.get("Is4k") and "4k" or "1080p"
        else:
            maxQuality = simpleobjects.AttributeDict({
                'height': 1080,
                'maxHeight': 1088
            })
            maxResolution = "1080p"

        self._globals['qualities'] = [
            simpleobjects.AttributeDict({'title': "Original", 'index': 16, 'maxBitrate': 1000000}),
            simpleobjects.AttributeDict({'title': "26 Mbps", 'index': 15, 'maxBitrate': 26000}),
            simpleobjects.AttributeDict({'title': "20 Mbps", 'index': 14, 'maxBitrate': 20000}),
            simpleobjects.AttributeDict({'title': "16 Mbps", 'index': 13, 'maxBitrate': 16000}),
            simpleobjects.AttributeDict({'title': "12 Mbps", 'index': 12, 'maxBitrate': 12000}),
            simpleobjects.AttributeDict({'title': "10 Mbps", 'index': 11, 'maxBitrate': 10000}),
            simpleobjects.AttributeDict({'title': "8 Mbps", 'index': 10, 'maxBitrate': 8000}),
            simpleobjects.AttributeDict({'title': "6 Mbps", 'index': 9, 'maxBitrate': 8000}),
            simpleobjects.AttributeDict({'title': "4 Mbps", 'index': 8, 'maxBitrate': 4000, 'maxHeight': 720}),
            simpleobjects.AttributeDict({'title': "3 Mbps", 'index': 7, 'maxBitrate': 3000, 'maxHeight': 720}),
            simpleobjects.AttributeDict({'title': "2 Mbps", 'index': 6, 'maxBitrate': 2000, 'maxHeight': 720}),
            simpleobjects.AttributeDict({'title': "1.5 Mbps", 'index': 5, 'maxBitrate': 1500, 'maxHeight': 480}),
            simpleobjects.AttributeDict({'title': "720 Kbps", 'index': 4, 'maxBitrate': 720, 'maxHeight': 360}),
            simpleobjects.AttributeDict({'title': "320 Kbps", 'index': 3, 'maxBitrate': 320, 'maxHeight': 360}),
            maxQuality
        ]

        for quality in self._globals['qualities']:
            if quality.index is not None and quality.index >= 9:
                quality.update(maxQuality)

    def getPreference(self, pref, default=None, **kw):
        raise NotImplementedError

    def setPreference(self, pref, value):
        raise NotImplementedError

    def clearRegistry(self, reg, sec=None):
        raise NotImplementedError

    def getRegistry(self, reg, default=None, sec=None):
        raise NotImplementedError

    def setRegistry(self, reg, value, sec=None):
        raise NotImplementedError

    def getGlobal(self, glbl, default=None):
        raise NotImplementedError

    def getCapabilities(self):
        raise NotImplementedError

    def LOG(self, msg):
        raise NotImplementedError

    def DEBUG_LOG(self, msg):
        self.LOG(msg)

    def WARN_LOG(self, msg):
        self.LOG(msg)

    def ERROR_LOG(self, msg):
        self.LOG(msg)

    def ERROR(self, msg=None, err=None):
        self.LOG(msg)

    def FATAL(self, msg=None):
        self.ERROR_LOG('FATAL: {0}'.format(msg))

    def supportsAudioStream(self, codec, channels):
        return False

    def supportsSurroundSound(self):
        return False

    def getMaxResolution(self, quality_type, allow4k=False):
        return 480

    def getQualityIndex(self, qualityType):
        if qualityType == self.QUALITY_LOCAL:
            return self.getPreference("local_quality2", 16)
        elif qualityType == self.QUALITY_ONLINE:
            return self.getPreference("online_quality2", 16)
        else:
            return self.getPreference("remote_quality2", 16)

    def settingsGetMaxResolution(self, qualityType, allow4k):
        qualityIndex = self.getQualityIndex(qualityType)

        if qualityIndex >= 9:
            return allow4k and 2160 or 1088
        elif qualityIndex >= 6:
            return 720
        elif qualityIndex >= 5:
            return 480
        else:
            return 360

    def getMaxBitrate(self, qualityType):
        qualityIndex = self.getQualityIndex(qualityType)

        qualities = self.getGlobal("qualities", [])
        for quality in qualities:
            if quality.index == qualityIndex:
                return util.validInt(quality.maxBitrate)

        return 0


class PlayerSettingsInterface(object):
    def __init__(self):
        self.prefOverrides = {}

    def __getattr__(self, name):
        return getattr(util.INTERFACE, name)

    def setPrefOverride(self, key, val):
        self.prefOverrides[key] = val

    def getPrefOverride(self, key, default=None):
        return self.prefOverrides.get(key, default)

    def getQualityIndex(self, qualityType):
        if qualityType == util.INTERFACE.QUALITY_LOCAL:
            return self.getPreference("local_quality2", 16)
        elif qualityType == util.INTERFACE.QUALITY_ONLINE:
            return self.getPreference("online_quality2", 16)
        else:
            return self.getPreference("remote_quality2", 16)

    def getPreference(self, key, default=None, **kw):
        if key in self.prefOverrides:
            return self.prefOverrides[key]
        else:
            return util.INTERFACE.getPreference(key, default, **kw)

    def getPlaybackFeatures(self):
        return util.INTERFACE.getPlaybackFeatures()

    def getAdditionalCodecs(self):
        return util.INTERFACE.getAdditionalCodecs()

    def getMaxResolution(self, quality_type, allow4k=False):
        qualityIndex = self.getQualityIndex(quality_type)

        if qualityIndex >= 9:
            return allow4k and util.INTERFACE.maxVerticalDPRes or 1088
        elif qualityIndex >= 6:
            return 720
        elif qualityIndex >= 5:
            return 480
        else:
            return 360

    def getMaxBitrate(self, qualityType):
        qualityIndex = self.getQualityIndex(qualityType)

        qualities = self.getGlobal("qualities", [])
        for quality in qualities:
            if quality.index == qualityIndex:
                return util.validInt(quality.maxBitrate)

        return 0


class DumbInterface(AppInterface):
    _prefs = {}
    _regs = {
        None: {}
    }
    _globals = {
        'platform': platform.uname()[0],
        'appVersionStr': '0.0.0a1',
        'clientIdentifier': str(hex(uuid.getnode())),
        'platformVersion': platform.uname()[2],
        'product': 'PlexNet.API',
        'provides': 'player',
        'device': platform.uname()[0],
        'model': 'Unknown',
        'friendlyName': 'PlexNet.API',
        'deviceInfo': DeviceInfo()
    }

    def getPreference(self, pref, default=None, **kw):
        return self._prefs.get(pref, default)

    def setPreference(self, pref, value):
        self._prefs[pref] = value

    def getRegistry(self, reg, default=None, sec=None):
        section = self._regs.get(sec)
        if section:
            return section.get(reg, default)

        return default

    def setRegistry(self, reg, value, sec=None):
        if sec and sec not in self._regs:
            self._regs[sec] = {}
        self._regs[sec][reg] = value

    def clearRegistry(self, reg, sec=None):
        del self._regs[sec][reg]

    def getGlobal(self, glbl, default=None):
        return self._globals.get(glbl, default)

    def getCapabilities(self):
        return ''

    def LOG(self, msg):
        print('PlexNet.API: {0}'.format(msg))

    def DEBUG_LOG(self, msg):
        self.LOG('DEBUG: {0}'.format(msg))

    def WARN_LOG(self, msg):
        self.LOG('WARNING: {0}'.format(msg))

    def ERROR_LOG(self, msg):
        self.LOG('ERROR: {0}'.format(msg))

    def ERROR(self, msg=None, err=None):
        if err:
            self.LOG('ERROR: {0} - {1}'.format(msg, err.message))
        else:
            import traceback
            traceback.print_exc()


def createTimer(timeout, function, repeat=False, *args, **kwargs):
    if isinstance(function, six.string_types):
        def dummy(*args, **kwargs):
            pass
        dummy.__name__ = function
        function = dummy
    timer = util.TIMER(timeout / 1000.0, function, repeat=repeat, *args, **kwargs)
    return timer


def setUserAgent(agent):
    util.USER_AGENT = agent
    util.BASE_HEADERS = util.resetBaseHeaders()


def setAbortFlagFunction(func):
    from . import asyncadapter
    asyncadapter.ABORT_FLAG_FUNCTION = func


def refreshResources(force=False):
    from . import gdm
    gdm.DISCOVERY.discover()
    util.MANAGER.refreshResources(force)
    SERVERMANAGER.refreshManualConnections()


util.setApp(App())
util.setInterface(DumbInterface())
