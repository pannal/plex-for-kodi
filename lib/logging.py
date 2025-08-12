# coding=utf-8
from __future__ import absolute_import

import sys
import traceback
import types
import logging

from kodi_six import xbmc


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
