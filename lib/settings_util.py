# coding=utf-8
import threading
import datetime
import binascii
import json

import plexnet.util

from lib.kodi_util import ADDON

SETTINGS_LOCK = threading.Lock()
JSON_SETTINGS = []
USER_SETTINGS = []


def _processSetting(setting, default, is_json=False):
    if not setting:
        return default
    if isinstance(default, bool):
        return setting.lower() == 'true'
    elif isinstance(default, float):
        return float(setting)
    elif isinstance(default, int):
        return int(float(setting or 0))
    elif isinstance(default, list):
        if setting and not is_json:
            return json.loads(binascii.unhexlify(setting))
        elif setting and is_json:
            return json.loads(setting)
        else:
            return default
    elif isinstance(default, datetime.datetime):
        return datetime.datetime.strptime(setting, '%Y-%m-%dT%H:%M:%S.%f')

    return setting



def getSetting(key, default=None):
    with SETTINGS_LOCK:
        setting = ADDON.getSetting(key)
        is_json = key in JSON_SETTINGS
        return _processSetting(setting, default, is_json=is_json)


def getUserSetting(key, default=None):
    if not plexnet.util.ACCOUNT:
        return default

    is_json = key in JSON_SETTINGS

    key = '{}.{}'.format(key, plexnet.util.ACCOUNT.ID)
    with SETTINGS_LOCK:
        setting = ADDON.getSetting(key)
        return _processSetting(setting, default, is_json=is_json)


def setSetting(key, value):
    with SETTINGS_LOCK:
        value = _processSettingForWrite(value)
        ADDON.setSetting(key, value)


def _processSettingForWrite(value):
    if isinstance(value, list):
        value = binascii.hexlify(json.dumps(value))
    elif isinstance(value, bool):
        value = value and 'true' or 'false'
    elif isinstance(value, datetime.datetime):
        value = value.strftime('%Y-%m-%dT%H:%M:%S.%f')
    return str(value)
