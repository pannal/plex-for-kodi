# coding=utf-8
"""Stand-in for Kodi's `xbmcplugin` (PM4K's plugin.py endpoint)."""

from __future__ import absolute_import

from kodienv import ENV

SORT_METHOD_NONE = 0
SORT_METHOD_LABEL = 1
SORT_METHOD_DATE = 3
SORT_METHOD_UNSORTED = 40
SORT_METHOD_VIDEO_TITLE = 24
SORT_METHOD_EPISODE = 23

# every directory item handed to Kodi, in order: (handle, url, listitem, isFolder)
DIRECTORY_ITEMS = []


def addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
    DIRECTORY_ITEMS.append((handle, url, listitem, isFolder))
    return True


def addDirectoryItems(handle, items, totalItems=0):
    for item in items:
        DIRECTORY_ITEMS.append((handle,) + tuple(item))
    return True


def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    ENV.builtins.append("endOfDirectory({0},{1})".format(handle, succeeded))


def setResolvedUrl(handle, succeeded, listitem):
    ENV.builtins.append("setResolvedUrl({0},{1})".format(handle, succeeded))


def setContent(handle, content):
    pass


def setPluginCategory(handle, category):
    pass


def addSortMethod(handle, sortMethod, label2Mask=""):
    pass


def getSetting(handle, id):
    return ENV.settings.get(id, "")


def setSetting(handle, id, value):
    ENV.settings[id] = value
