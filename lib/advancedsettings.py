# coding=utf-8

from kodi_six import xbmcvfs

from lib.util import LOG, ERROR


class AdvancedSettings(object):
    _data = None

    def __init__(self):
        self.load()

    def __bool__(self):
        return bool(self._data)

    __nonzero__ = __bool__

    def getData(self):
        return self._data

    def load(self):
        if xbmcvfs.exists("special://profile/advancedsettings.xml"):
            try:
                f = xbmcvfs.File("special://profile/advancedsettings.xml")
                try:
                    self._data = f.read()
                finally:
                    f.close()
            except:
                LOG('script.plexmod: No advancedsettings.xml found')

    def write(self, data=None):
        self._data = data = data or self._data
        if not data:
            return

        try:
            f = xbmcvfs.File("special://profile/advancedsettings.xml", "w")
            try:
                f.write(data)
            finally:
                f.close()
        except:
            ERROR("Couldn't write advancedsettings.xml")


adv = AdvancedSettings()
