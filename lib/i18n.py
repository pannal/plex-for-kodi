# coding=utf-8
from kodi_six import xbmcaddon


ADDON = xbmcaddon.Addon()


def T(ID, eng=''):
    s = ADDON.getLocalizedString(ID)
    return s if s != "" else eng
