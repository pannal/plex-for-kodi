# coding=utf-8
import re
from kodi_six import xbmcvfs

from lib.logging import log as LOG, log_error as ERROR

HAS_AUDIO_FIX_RE = re.compile(r'<superviseaudiodelay>.*true.*</superviseaudiodelay>',
                              re.MULTILINE | re.DOTALL | re.IGNORECASE)


class AdvancedSettings(object):
    _data = None
    has_audio_fix = False

    def __init__(self):
        self.load()
        if self._data:
            self.has_audio_fix = bool(HAS_AUDIO_FIX_RE.search(self._data))

    def __bool__(self):
        return bool(self._data)

    def getData(self):
        return self._data

    def load(self):
        if xbmcvfs.exists("special://profile/advancedsettings.xml"):
            try:
                f = xbmcvfs.File("special://profile/advancedsettings.xml")
                self._data = f.read()
                f.close()
            except:
                LOG('script.plexmod: No advancedsettings.xml found')

    def write(self, data=None):
        self._data = data = data or self._data
        if not data:
            return

        try:
            f = xbmcvfs.File("special://profile/advancedsettings.xml", "w")
            f.write(data)
            f.close()
        except:
            ERROR("Couldn't write advancedsettings.xml")


adv = AdvancedSettings()
