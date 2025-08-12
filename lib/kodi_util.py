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


ICON_PATH = translatePath(ADDON.getAddonInfo('icon'))


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
