# coding=utf-8
"""Stand-in for Kodi's `xbmcaddon`."""

from __future__ import absolute_import

from kodienv import ENV


class Settings(object):
    """The object returned by Addon.getSettings() on Kodi 20+."""

    def getBool(self, id):
        return ENV.settings.get(id, "").lower() == "true"

    def getInt(self, id):
        try:
            return int(float(ENV.settings.get(id, 0) or 0))
        except (TypeError, ValueError):
            return 0

    def getNumber(self, id):
        try:
            return float(ENV.settings.get(id, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def getString(self, id):
        return ENV.settings.get(id, "")

    def setBool(self, id, value):
        ENV.settings[id] = "true" if value else "false"

    def setInt(self, id, value):
        ENV.settings[id] = str(int(value))

    def setNumber(self, id, value):
        ENV.settings[id] = str(float(value))

    def setString(self, id, value):
        ENV.settings[id] = str(value)


class Addon(object):
    """
    Every instance reads and writes the same ENV.settings dict, which is how
    Kodi behaves: the settings store is global, not per-Addon-object. (The
    per-object staleness that bites PM4K in practice is a *write flush* of the
    whole document, not a divergent read; see lib/settings_util.setSetting.)
    """

    def __init__(self, id=None):
        self.id = id or ENV.addon_info["id"]

    def getAddonInfo(self, id):
        return ENV.addon_info.get(id, "")

    def getLocalizedString(self, id):
        return ENV.strings().get(id, "")

    def getSetting(self, id):
        return ENV.settings.get(id, "")

    def setSetting(self, id, value):
        ENV.settings[id] = value

    def getSettingBool(self, id):
        return ENV.settings.get(id, "").lower() == "true"

    def getSettingInt(self, id):
        try:
            return int(float(ENV.settings.get(id, 0) or 0))
        except (TypeError, ValueError):
            return 0

    def getSettingNumber(self, id):
        try:
            return float(ENV.settings.get(id, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def getSettingString(self, id):
        return ENV.settings.get(id, "")

    def setSettingBool(self, id, value):
        ENV.settings[id] = "true" if value else "false"

    def setSettingInt(self, id, value):
        ENV.settings[id] = str(int(value))

    def setSettingNumber(self, id, value):
        ENV.settings[id] = str(float(value))

    def setSettingString(self, id, value):
        ENV.settings[id] = str(value)

    def getSettings(self):
        return Settings()

    def openSettings(self):
        pass
