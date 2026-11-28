# coding=utf-8
"""Stand-in for Kodi's `xbmc` module, backed by kodienv.ENV."""

from __future__ import absolute_import

from kodienv import (ENV, LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL,  # noqa: F401
                      LOGNONE)

PLAYLIST_MUSIC = 0
PLAYLIST_VIDEO = 1

TRAY_OPEN = 16
DRIVE_NOT_READY = 1
TRAY_CLOSED_NO_MEDIA = 64
TRAY_CLOSED_MEDIA_PRESENT = 96


def log(msg, level=LOGDEBUG):
    ENV.log(msg, level)


def executebuiltin(function, wait=False):
    ENV.builtins.append(function)


def executeJSONRPC(jsonrpccommand):
    return ENV.execute_jsonrpc(jsonrpccommand)


def sleep(timemillis):
    ENV.sleeps.append(timemillis)


def getInfoLabel(cLine):
    # Window(<id>).Property(<key>) is how PM4K reads its own global properties
    if cLine.startswith("Window(") and ").Property(" in cLine:
        win, _, prop = cLine.partition(").Property(")
        try:
            win_id = int(win[len("Window("):])
        except ValueError:
            win_id = 10000
        return ENV.window_props[win_id].get(prop.rstrip(")"), "")
    return ENV.infolabels.get(cLine, "")


def getCondVisibility(condition):
    value = ENV.cond_visibility.get(condition, False)
    return bool(value(condition)) if callable(value) else bool(value)


def getRegion(id):
    return ENV.regions.get(id, "")


def getSkinDir():
    return ENV.skin_dir


def getUserAgent():
    return ENV.user_agent


def getLanguage(format=0, region=False):
    return ENV.language


def getLocalizedString(id):
    return ENV.strings().get(id, "")


def translatePath(path):
    """Kodi <= 18 location of translatePath; PM4K only uses it as a fallback."""
    return ENV.translate_path(path)


def getSupportedMedia(mediaType):
    return ""


def shutdown():
    ENV.power_calls.append("shutdown")


def restart():
    ENV.power_calls.append("restart")


class Monitor(object):
    def __init__(self, *args, **kwargs):
        pass

    def abortRequested(self):
        return ENV.abort_requested

    def waitForAbort(self, timeout=None):
        ENV.waits.append(timeout)
        return ENV.abort_on_wait

    def onNotification(self, sender, method, data):
        pass

    def onSettingsChanged(self):
        pass

    def onScreensaverActivated(self):
        pass

    def onScreensaverDeactivated(self):
        pass

    def onDPMSActivated(self):
        pass

    def onDPMSDeactivated(self):
        pass

    def onCleanStarted(self, library=""):
        pass

    def onCleanFinished(self, library=""):
        pass

    def onScanStarted(self, library=""):
        pass

    def onScanFinished(self, library=""):
        pass


class Player(object):
    """
    Minimal player stand-in. Playback state lives on the class so that code
    which constructs a throwaway `xbmc.Player()` still observes it.
    """
    playing = False
    playing_video = False
    playing_audio = False
    playing_file = ""
    time = 0.0
    total_time = 0.0
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def isPlaying(self):
        return Player.playing or Player.playing_video or Player.playing_audio

    def isPlayingVideo(self):
        return Player.playing_video

    def isPlayingAudio(self):
        return Player.playing_audio

    def getPlayingFile(self):
        if not self.isPlaying():
            raise RuntimeError("Kodi is not playing any file")
        return Player.playing_file

    def getTime(self):
        return Player.time

    def getTotalTime(self):
        return Player.total_time

    def seekTime(self, seekTime):
        Player.calls.append(("seekTime", seekTime))
        Player.time = seekTime

    def pause(self):
        Player.calls.append(("pause", None))

    def stop(self):
        Player.calls.append(("stop", None))
        Player.playing = Player.playing_video = Player.playing_audio = False

    def play(self, *args, **kwargs):
        Player.calls.append(("play", args))

    def getVideoInfoTag(self):
        return InfoTagVideo()

    def getAvailableSubtitleStreams(self):
        return []

    def getAvailableAudioStreams(self):
        return []

    def setSubtitleStream(self, iStream):
        Player.calls.append(("setSubtitleStream", iStream))

    def setAudioStream(self, iStream):
        Player.calls.append(("setAudioStream", iStream))

    def showSubtitles(self, bVisible):
        Player.calls.append(("showSubtitles", bVisible))


class InfoTagVideo(object):
    def getDuration(self):
        return 0

    def getTitle(self):
        return ""


class PlayList(object):
    lists = {}

    def __init__(self, playList):
        self.playListId = playList
        PlayList.lists.setdefault(playList, [])

    @property
    def _items(self):
        return PlayList.lists[self.playListId]

    def __len__(self):
        return len(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def add(self, url, listitem=None, index=-1):
        if index < 0:
            self._items.append(url)
        else:
            self._items.insert(index, url)

    def clear(self):
        del self._items[:]

    def size(self):
        return len(self._items)

    def getposition(self):
        return 0


class Keyboard(object):
    def __init__(self, line="", heading="", hidden=False):
        self._text = line
        self._confirmed = True

    def doModal(self, autoclose=0):
        pass

    def isConfirmed(self):
        return self._confirmed

    def getText(self):
        return self._text
