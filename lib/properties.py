# coding=utf-8
from kodi_six import xbmc
from lib.properties_core import _setGlobalProperty, _setGlobalBoolProperty, _getGlobalProperty


MONITOR = xbmc.Monitor()


def setGlobalProperty(key, val, wait=False, timeout=500, base='script.plex.{0}'):
    _setGlobalProperty(key, val, base=base)
    if wait:
        waited = 0
        while _getGlobalProperty(key, base=base) != val and waited < timeout:
            if MONITOR.waitForAbort(0.01):
                break
            waited += 0.01


def setGlobalBoolProperty(key, boolean, base='script.plex.{0}'):
    _setGlobalBoolProperty(key, boolean, base=base)


class IPCException(Exception):
    def __init__(self, msg, status_code=None):
        self.msg = msg
        self.status_code = status_code

    def __str__(self):
        return '{}: {}'.format(self.msg, self.status_code)


class IPCTimeoutException(IPCException):
    pass


def getGlobalProperty(key, consume=False, wait=False, interval=0.01, timeout=360000, base='script.plex.{0}'):
    resp = _getGlobalProperty(key, base=base)
    if wait and not resp:
        waited = 0
        while not MONITOR.abortRequested() and not resp and waited < timeout:
            if MONITOR.waitForAbort(interval):
                break
            resp = _getGlobalProperty(key, base=base)
            waited += 1

        if waited >= timeout:
            # timed out
            raise IPCTimeoutException('Timed out while waiting for: {}'.format(key))

    if consume:
        setGlobalProperty(key, '', wait=wait, timeout=timeout, base=base)

    return resp


def waitForGPEmpty(key, interval=0.01, timeout=360000, base='script.plex.{0}'):
    resp = _getGlobalProperty(key, base=base)
    if resp:
        waited = 0
        while not MONITOR.abortRequested() and resp and waited < timeout:
            if MONITOR.waitForAbort(interval):
                break
            resp = _getGlobalProperty(key, base=base)
            waited += 1
        if waited >= timeout:
            raise IPCTimeoutException('Timed out while waiting for emptiness of: {}'.format(key))
    return True


waitForConsumption = waitForGPEmpty