# coding=utf-8
import threading
import _strptime
import datetime
import binascii
import json

from lib.kodi_util import ADDON

UNDEF = "__UNDEF__"
SETTINGS_LOCK = threading.Lock()
JSON_SETTINGS = []
USER_SETTINGS = []
DEFAULT_SETTINGS = {}


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


def _getDef(key, default):
    if default == UNDEF:
        default = DEFAULT_SETTINGS.get(key, None)
    return default


def getSetting(key, default=UNDEF):
    d = _getDef(key, default)

    with SETTINGS_LOCK:
        setting = ADDON.getSetting(key)
        is_json = key in JSON_SETTINGS
        return _processSetting(setting, d, is_json=is_json)


def getUserSetting(key, default=UNDEF):
    from plexnet.util import ACCOUNT
    d = _getDef(key, default)

    if not ACCOUNT:
        return d

    is_json = key in JSON_SETTINGS

    key = '{}.{}'.format(key, ACCOUNT.ID)
    with SETTINGS_LOCK:
        setting = ADDON.getSetting(key)
        return _processSetting(setting, d, is_json=is_json)


def setSetting(key, value, addon=ADDON):
    with SETTINGS_LOCK:
        value = _processSettingForWrite(value)
        addon.setSetting(key, value)


def _processSettingForWrite(value):
    if isinstance(value, list):
        value = binascii.hexlify(json.dumps(value))
    elif isinstance(value, bool):
        value = value and 'true' or 'false'
    elif isinstance(value, datetime.datetime):
        value = value.strftime('%Y-%m-%dT%H:%M:%S.%f')
    return str(value)
