# coding=utf-8

from __future__ import absolute_import

from copy import copy

from . import simpleobjects
import re
import sys
import time
import platform
import uuid
import threading
import six
from kodi_six import xbmcaddon

from . import verlib
from . import compat

if six.PY2:
    Event = threading._Event
else:
    Event = threading.Event

BASE_HEADERS = ''

# to maintain py2 compatibility, duplicate ADDON from lib.util to avoid circular import
ADDON = xbmcaddon.Addon()


def resetBaseHeaders():
    return {
        'X-Plex-Platform': X_PLEX_PLATFORM,
        'X-Plex-Platform-Version': X_PLEX_PLATFORM_VERSION,
        'X-Plex-Provides': X_PLEX_PROVIDES,
        'X-Plex-Product': "PM4K",
        'X-Plex-Version': ADDON.getAddonInfo('version'),
        'X-Plex-Device': X_PLEX_DEVICE,
        'X-Plex-Client-Identifier': X_PLEX_IDENTIFIER,
        'Accept-Encoding': 'gzip,deflate',
        'Accept-Language': ACCEPT_LANGUAGE,
        'User-Agent': '{0}/{1}'.format("PM4K", ADDON.getAddonInfo('version'))
    }


# Core Settings
PROJECT = 'PlexNet'                                 # name provided to plex server
VERSION = '0.0.0a1'                                 # version of this api
TIMEOUT = 10                                        # request timeout
LONG_TIMEOUT = 20                                   # s
CONN_CHECK_TIMEOUT = 2.5                            # s
LAN_REACHABILITY_TIMEOUT = 0.01                     # s
CHECK_LOCAL = False
LOCAL_OVER_SECURE = False
X_PLEX_CONTAINER_SIZE = 50                          # max results to return in a single search page

ACCEPT_LANGUAGE = 'en-US,en'

# Plex Header Configuation
X_PLEX_PROVIDES = 'player,controller'          # one or more of [player, controller, server]
X_PLEX_PLATFORM = platform.uname()[0]          # Platform name, eg iOS, MacOSX, Android, LG, etc
X_PLEX_PLATFORM_VERSION = platform.uname()[2]  # Operating system version, eg 4.3.1, 10.6.7, 3.2
X_PLEX_PRODUCT = PROJECT                       # Plex application name, eg Laika, Plex Media Server, Media Link
X_PLEX_VERSION = VERSION                       # Plex application version number
USER_AGENT = '{0}/{1}'.format(PROJECT, VERSION)

INTERFACE = None
TIMER = None
APP = None
MANAGER = None

try:
    _platform = platform.system()
except:
    try:
        _platform = platform.platform(terse=True)
    except:
        _platform = sys.platform

X_PLEX_DEVICE = _platform                     # Device name and model number, eg iPhone3,2, Motorola XOOM, LG5200TV
X_PLEX_IDENTIFIER = str(hex(uuid.getnode()))  # UUID, serial number, or other number unique per device

BASE_HEADERS = resetBaseHeaders()

QUALITY_LOCAL = 0
QUALITY_REMOTE = 1
QUALITY_ONLINE = 2

Res = simpleobjects.Res
AttributeDict = simpleobjects.AttributeDict


def setInterface(interface):
    global INTERFACE
    INTERFACE = interface


def setTimer(timer):
    global TIMER
    TIMER = timer


def setApp(app):
    global APP
    APP = app


def LOG(msg):
    INTERFACE.LOG(msg)


def DEBUG_LOG(msg):
    INTERFACE.DEBUG_LOG(msg)


def ERROR_LOG(msg):
    INTERFACE.ERROR_LOG(msg)


def WARN_LOG(msg):
    INTERFACE.WARN_LOG(msg)


def ERROR(msg=None, err=None):
    INTERFACE.ERROR(msg, err)


def FATAL(msg=None):
    INTERFACE.FATAL(msg)


def TEST(msg):
    INTERFACE.LOG(' ---TEST: {0}'.format(msg))


def userAgent():
    return INTERFACE.getGlobal("userAgent")


def dummyTranslate(string):
    return string


def trimString(s, limit=20, ellipsis='…'):
    s = s.strip()
    if len(s) > limit:
        return s[:limit-1].strip() + ellipsis
    return s


def hideToken(token):
    # return 'X' * len(token)
    if not token:
        return token
    return '****' + token[-4:]


def cleanToken(url):
    return re.sub(r'X-Plex-Token=[^&]+', 'X-Plex-Token=****', url)


def cleanObjTokens(dorig, flistkeys=("streamUrls",), fstrkeys=("url", "token")):
    d = {}
    dcopy = copy(dorig)

    # filter lists
    for k in flistkeys:
        if k not in d:
            continue
        d[k] = list(map(lambda x: cleanToken(x), d[k][:]))

    # filter strings
    for k in fstrkeys:
        if k not in d:
            continue
        d[k] = "****" if k == "token" else cleanToken(d[k])

    dcopy.update(d)
    return dcopy


def now(local=False):
    if local:
        return time.time()
    else:
        return time.mktime(time.gmtime())


def joinArgs(args, includeQuestion=True):
    if not args:
        return ''

    arglist = []
    for key in sorted(args, key=lambda x: x.lower()):
        value = str(args[key])
        arglist.append('{0}={1}'.format(key, compat.quote(value, safe='')))

    return '{0}{1}'.format(includeQuestion and '?' or '&', '&'.join(arglist))


def addPlexHeaders(transferObj, token=None):
    headers = {"X-Plex-Platform": INTERFACE.getGlobal("platform"),
               "X-Plex-Version": INTERFACE.getGlobal("appVersionStr"),
               "X-Plex-Client-Identifier": INTERFACE.getGlobal("clientIdentifier"),
               "X-Plex-Platform-Version": INTERFACE.getGlobal("platformVersion", "unknown"),
               "X-Plex-Product": INTERFACE.getGlobal("product"),
               "X-Plex-Provides": not INTERFACE.getPreference("remotecontrol", False) and 'player' or '',
               "X-Plex-Device": INTERFACE.getGlobal("device"),
               "X-Plex-Model": INTERFACE.getGlobal("model"),
               "X-Plex-Device-Name": INTERFACE.getGlobal("friendlyName"),
               }

    transferObj.session.headers.update(headers)

    # Adding the X-Plex-Client-Capabilities header causes node.plexapp.com to 500
    if not type(transferObj) == "roUrlTransfer" or 'node.plexapp.com' not in transferObj.getUrl():
        transferObj.addHeader("X-Plex-Client-Capabilities", INTERFACE.getCapabilities())

    addAccountHeaders(transferObj, token)


def addAccountHeaders(transferObj, token=None):
    if token:
        transferObj.addHeader("X-Plex-Token", token)

    # TODO(schuyler): Add username?


def validInt(int_str):
    try:
        return int(int_str)
    except:
        return 0


def bitrateToString(bits):
    if not bits:
        return ''

    speed = bits / 1000000.0
    if speed < 1:
        speed = int(round(bits / 1000.0))
        return '{0} Kbps'.format(speed)
    else:
        return '{0:.1f} Mbps'.format(speed)


def normalizedVersion(ver):
    try:
        modv = '.'.join(ver.split('.')[:4]).split('-', 1)[0]  # Clean the version i.e. Turn 1.2.3.4-asdf8-ads7f into 1.2.3.4
        return verlib.NormalizedVersion(verlib.suggest_normalized_version(modv))
    except:
        if ver:
            ERROR()
        return verlib.NormalizedVersion(verlib.suggest_normalized_version('0.0.0'))


class CompatEvent(Event):
    def wait(self, timeout):
        Event.wait(self, timeout)
        return self.isSet()


class Timer(object):
    def __init__(self, timeout, function, repeat=False, name=None, fname=None, *args, **kwargs):
        self.function = function
        self.timeout = timeout
        self.repeat = repeat
        self.args = args
        self.kwargs = kwargs
        self._reset = False
        self.name = name or 'TIMER:{0}'.format(self.function)
        self.fname = fname or repr(self.function)
        self.event = CompatEvent()
        self.start()

    def start(self):
        self.event.clear()
        self.thread = threading.Thread(target=self.run, name=self.name, *self.args, **self.kwargs)
        self.thread.start()

    def run(self):
        DEBUG_LOG('Timer {0}: {1}'.format(self.fname, self._reset and 'RESET'or 'STARTED'))
        try:
            while not self.event.isSet() and not self.shouldAbort():
                while not self.event.wait(self.timeout) and not self.shouldAbort():
                    if self._reset:
                        return

                    self.function(*self.args, **self.kwargs)
                    if not self.repeat:
                        return
        finally:
            if not self._reset:
                if self in APP.timers:
                    APP.timers.remove(self)

                DEBUG_LOG('Timer {0}: FINISHED'.format(self.fname))

            self._reset = False

    def cancel(self):
        self.event.set()

    def reset(self):
        self._reset = True
        self.cancel()
        if self.thread and self.thread.is_alive():
            self.thread.join()
        self.start()

    def is_alive(self):
        return self.thread and self.thread.is_alive()

    def shouldAbort(self):
        return False

    def join(self):
        if self.thread.is_alive():
            self.thread.join()

    def isExpired(self):
        return self.event.isSet()


class RepeatingCounterTimer(Timer):
    def __init__(self, timeout, function, repeat=True, *args, **kwargs):
        self.ticks = 0
        self._function = function
        super(RepeatingCounterTimer, self).__init__(timeout, self.count, repeat=repeat,
                                                    name='TIMER:{0}'.format(function),
                                                    fname=repr(function), *args, **kwargs)

    def count(self):
        self.ticks += 1
        self._function(*self.args, **self.kwargs)

    def reset(self):
        super(RepeatingCounterTimer, self).reset()
        self.ticks = 0


TIMER = Timer
