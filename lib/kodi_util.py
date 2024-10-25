# coding=utf-8

# noinspection PyUnresolvedReferences
from kodi_six import xbmc, xbmcgui, xbmcvfs, xbmcaddon

ADDON = xbmcaddon.Addon()


_build = None
# buildversion looks like: XX.X[-TAG] (a+.b+.c+) (.+); there are kodi builds that don't set the build version
sys_ver = xbmc.getInfoLabel('System.BuildVersion')
_ver = sys_ver

try:
    if ' ' in sys_ver and '(' in sys_ver:
        _ver, _build = sys_ver.split()[:2]

    _splitver = _ver.split(".")
    KODI_VERSION_MAJOR, KODI_VERSION_MINOR = int(_splitver[0].split("-")[0].strip()), \
                                             int(_splitver[1].split(" ")[0].split("-")[0].strip())
except:
    xbmc.log('script.plexmod: Couldn\'t determine Kodi version, assuming 19.4. Got: {}'.format(sys_ver), xbmc.LOGINFO)
    # assume something "old"
    KODI_VERSION_MAJOR = 19
    KODI_VERSION_MINOR = 4

_bmajor, _bminor, _bpatch = (KODI_VERSION_MAJOR, KODI_VERSION_MINOR, 0)
parsedBuild = False
if _build:
    try:
        _bmajor, _bminor, _bpatch = _build[1:-1].split(".")
        parsedBuild = True
    except:
        pass
if not parsedBuild:
    xbmc.log('script.plexmod: Couldn\'t determine build version, falling back to Kodi version', xbmc.LOGINFO)

# calculate a comparable build number
KODI_BUILD_NUMBER = int("{0}{1:02d}{2:03d}".format(_bmajor, int(_bminor), int(_bpatch)))

FROM_KODI_REPOSITORY = ADDON.getAddonInfo('name') == "PM4K for Plex"


if KODI_VERSION_MAJOR > 18:
    translatePath = xbmcvfs.translatePath
else:
    translatePath = xbmc.translatePath


def setGlobalProperty(key, val, base='script.plex.{0}', wait=False):
    xbmcgui.Window(10000).setProperty(base.format(key), val)
    if wait:
        waited = 0
        while getGlobalProperty(key) != val and waited < 2:
            xbmc.Monitor().waitForAbort(0.1)
            waited += 0.1


def setGlobalBoolProperty(key, boolean, base='script.plex.{0}'):
    xbmcgui.Window(10000).setProperty(base.format(key), boolean and '1' or '')



class IPCException(Exception):
    def __init__(self, msg, status_code=None):
        self.msg = msg
        self.status_code = status_code

    def __str__(self):
        return '{}: {}'.format(self.msg, self.status_code)


class IPCTimeoutException(IPCException):
    pass


def getGlobalProperty(key, consume=False, wait=False, interval=0.1, timeout=36000, monitor_cls=xbmc.Monitor):
    resp = xbmc.getInfoLabel('Window(10000).Property(script.plex.{0})'.format(key))
    if wait and not resp:
        waited = 0
        monitor = monitor_cls()
        while not monitor.abortRequested() and not resp and waited < timeout:
            if monitor.waitForAbort(interval):
                break
            resp = xbmc.getInfoLabel('Window(10000).Property(script.plex.{0})'.format(key))
            waited += 1

        if waited >= timeout:
            # timed out
            raise IPCTimeoutException('Timed out while waiting for: {}'.format(key))

    if consume:
        setGlobalProperty(key, '', wait=wait)

    return resp


def waitForGPEmpty(key, interval=0.1, timeout=36000, monitor_cls=xbmc.Monitor):
    resp = xbmc.getInfoLabel('Window(10000).Property(script.plex.{0})'.format(key))
    if resp:
        waited = 0
        monitor = monitor_cls()
        while not monitor.abortRequested() and resp and waited < timeout:
            if monitor.waitForAbort(interval):
                break
            resp = xbmc.getInfoLabel('Window(10000).Property(script.plex.{0})'.format(key))
            waited += 1
        if waited >= timeout:
            raise IPCTimeoutException('Timed out while waiting for emptiness of: {}'.format(key))
    return True


waitForConsumption = waitForGPEmpty


def ensureHome():
    if xbmcgui.getCurrentWindowId() != 10000:
        xbmc.log("Switching to home screen before starting addon: {}".format(xbmcgui.getCurrentWindowId()),
                 xbmc.LOGINFO)
        xbmc.executebuiltin('Action(back)')
        xbmc.executebuiltin('Dialog.Close(all,1)')
        xbmc.executebuiltin('ActivateWindow(home)')
        ct = 0
        while xbmcgui.getCurrentWindowId() != 10000 and ct <= 50:
            xbmc.Monitor().waitForAbort(0.1)
            ct += 1
        if ct > 50:
            xbmc.log("Still active window: {}", xbmc.LOGINFO)
