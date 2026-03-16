# coding=utf-8
from __future__ import absolute_import

import sys
import traceback
import types
import logging

from kodi_six import xbmc

from .kodi_util import ADDON, translatePath
from .addonsettings import addonSettings

_SHUTDOWN = False

def setShutdown():
    global _SHUTDOWN
    _SHUTDOWN = True


def log(msg, *args, **kwargs):
    if args:
        # resolve dynamic args
        msg = msg.format(*[arg() if isinstance(arg, types.FunctionType) else arg for arg in args])

    level = kwargs.pop("level", xbmc.LOGINFO)

    prepend_msg = kwargs.pop('prepend_msg', None)
    if prepend_msg:
        msg = '{0}: {1}'.format(prepend_msg, msg)

    if kwargs:
        # resolve dynamic kwargs
        msg = msg.format(**dict((k, v()) if isinstance(v, types.FunctionType) else v for k, v in kwargs.items()))
    xbmc.log('script.plexmod: {0}'.format(msg), level)


def log_error(txt='', hide_tb=False):
    short = str(sys.exc_info()[1])
    if hide_tb:
        xbmc.log('script.plexmod: ERROR: {0} - {1}'.format(txt, short), xbmc.LOGERROR)
        return short

    tb = traceback.format_exc()
    xbmc.log("_________________________________________________________________________________", xbmc.LOGERROR)
    xbmc.log('script.plexmod: ERROR: ' + txt, xbmc.LOGERROR)
    for l in tb.splitlines():
        xbmc.log('    ' + l, xbmc.LOGERROR)
    xbmc.log("_________________________________________________________________________________", xbmc.LOGERROR)
    xbmc.log("`", xbmc.LOGERROR)



def LOG(msg, *args, **kwargs):
    return log(msg, *args, **kwargs)


def DEBUG_LOG(msg, *args, **kwargs):
    if _SHUTDOWN:
        return

    if not addonSettings.debug and not xbmc.getCondVisibility('System.GetBool(debug.showloginfo)'):
        return

    return log(msg, *args, **kwargs)


def ERROR(txt='', hide_tb=False, notify=False, time_ms=3000):
    short = log_error(txt, hide_tb)
    if notify:
        showNotification('ERROR: {0}'.format(txt or short), time_ms=time_ms)
    return short


def TEST(msg):
    xbmc.log('---TEST: {0}'.format(msg), xbmc.LOGINFO)


def showNotification(message, time_ms=3000, icon_path=None, header=ADDON.getAddonInfo('name')):
    try:
        icon_path = icon_path or translatePath(ADDON.getAddonInfo('icon'))
        xbmc.executebuiltin('Notification({0},{1},{2},{3})'.format(header, message, time_ms, icon_path))
    except RuntimeError:  # Happens when disabling the addon
        xbmc.log(message, xbmc.LOGINFO)


def service_log(msg, level=xbmc.LOGINFO, realm="Updater"):
    xbmc.log('script.plexmod/{}: {}'.format(realm, msg), level)


class KodiLogProxyHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET, log_func=log):
        self.log_func = log_func
        super(KodiLogProxyHandler, self).__init__(level)

    def emit(self, record):
        try:
            self.log_func(self.format(record))
        except:
            self.handleError(record)
