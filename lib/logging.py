# coding=utf-8
import sys
import traceback
import types

from kodi_six import xbmc


def log(msg, *args, **kwargs):
    if args:
        # resolve dynamic args
        msg = msg.format(*[arg() if isinstance(arg, types.FunctionType) else arg for arg in args])

    level = kwargs.pop("level", xbmc.LOGINFO)

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
