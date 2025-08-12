# coding=utf-8
import json
import os
from collections import namedtuple, OrderedDict

from kodi_six import xbmc, xbmcaddon, xbmcvfs
from plexnet import plexapp

from lib import util



ADDON = util.ADDON


ATTR_MAP = {
    "b": "binge_mode",
    "i": "auto_skip_intro",
    "c": "auto_skip_credits",
    "e": "show_intro_skip_early",
    "p": "skip_post_play_tv",
    "v": "media_version",
}

VIRTUAL_ATTRS = ("media_version",)

# I know dicts are ordered in py3, but we want to be compatible with py2.
TRANS_MAP = OrderedDict((
    ("binge_mode", 33618),
    ("auto_skip_intro", 32522),
    ("auto_skip_credits", 32526),
    ("show_intro_skip_early", 33505),
    ("skip_post_play_tv", 32973),
))

ATTR_MAP_REV = dict((v, k) for k, v in ATTR_MAP.items())


PlaybackSettings = namedtuple("PlaybackSettings", list(v for v in ATTR_MAP.values()))


class PlaybackManager(object):
    """
    Manages the playback settings for individual shows; falls back to the global default if no specifics set
    """
    version = 1
    _data = None
    _currentServerUUID = None
    _currentUserID = None

    transMap = TRANS_MAP

    dataPath = os.path.join(util.translatePath(ADDON.getAddonInfo("profile")), "playback_settings.json")

    # this could be a property, but w/e
    glob = None

    def __init__(self):
        self.reset()
        # bind settings change signals
        for k, v in ATTR_MAP.items():
            if k in VIRTUAL_ATTRS:
                continue
            plexapp.util.APP.on('change:{}'.format(v), lambda **kwargs: self.setGlob(**kwargs))

        plexapp.util.APP.on('change:selectedServer', lambda **kwargs: self.setServerUUID(**kwargs))
        plexapp.util.APP.on('change:tempServer', lambda **kwargs: self.setServerUUID(**kwargs))
        plexapp.util.APP.on("loaded:cached_user", lambda **kwargs: self.setUserID(**kwargs))
        plexapp.util.APP.on("change:user", lambda **kwargs: self.setUserID(**kwargs))
        plexapp.util.APP.on('init', lambda **kwargs: self.setUserID(**kwargs))

    def deinit(self):
        # unbind settings change signals
        for k, v in ATTR_MAP.items():
            if k in VIRTUAL_ATTRS:
                continue
            plexapp.util.APP.off('change:{}'.format(v), lambda **kwargs: self.setGlob(**kwargs))

        plexapp.util.APP.off('change:selectedServer', lambda **kwargs: self.setServerUUID(**kwargs))
        plexapp.util.APP.off('change:tempServer', lambda **kwargs: self.setServerUUID(**kwargs))
        plexapp.util.APP.off("loaded:cached_user", lambda **kwargs: self.setUserID(**kwargs))
        plexapp.util.APP.off("change:user", lambda **kwargs: self.setUserID(**kwargs))
        plexapp.util.APP.off('init', lambda **kwargs: self.setUserID(**kwargs))

    def __call__(self, obj, key=None, value=None, kv_dict=None):
        # shouldn't happen
        if not self._currentServerUUID:
            util.DEBUG_LOG("APP.PlaybackManager, something's wrong: ServerUUID: {}, UserID: {}",
                           self._currentServerUUID, self._currentUserID)
            return

        csid = self._currentServerUUID
        cuid = self._currentUserID

        # set
        if (key is not None and value is not None) or kv_dict is not None:
            # prepare value dict
            if csid not in self._data:
                self._data[csid] = {}

            if cuid not in self._data[csid]:
                self._data[csid][cuid] = {}

            ukv = {key: value} if not kv_dict else kv_dict

            if obj.ratingKey not in self._data[csid][cuid]:
                self._data[csid][cuid][obj.ratingKey] = {}

            for k, v in ukv.items():
                # don't write globals into the storage
                if v != getattr(self.glob, k):
                    self._data[csid][cuid][obj.ratingKey][ATTR_MAP_REV[k]] = v
                else:
                    # new val set to global default, delete specific val
                    if ATTR_MAP_REV[k] in self._data[csid][cuid][obj.ratingKey]:
                        del self._data[csid][cuid][obj.ratingKey][ATTR_MAP_REV[k]]

            # empty specific settings? clean up
            if not self._data[csid][cuid][obj.ratingKey]:
                del self._data[csid][cuid][obj.ratingKey]

            self.save()
            return self.glob._replace(**ukv)

        if not obj.ratingKey:
            return self.glob

        # get
        data = self._data.get(csid, {}).get(cuid, {}).get(obj.ratingKey, None)
        if data:
            return self.glob._replace(**dict((ATTR_MAP[k], v) for k, v in data.items()))
        return self.glob

    def reset(self):
        self._data = self.load()
        if plexapp.SERVERMANAGER and plexapp.SERVERMANAGER.selectedServer:
            self.setServerUUID()

        if plexapp.ACCOUNT:
            self.setUserID()
        self.setGlob()

    def setGlob(self, skey=None, value=None, **kwargs):
        if skey is not None and value is not None:
            self.glob = self.glob._replace(**{skey: value})
        else:
            self.glob = PlaybackSettings(**dict((k, util.getUserSetting(k, False)) for k in ATTR_MAP.values()))

    def setServerUUID(self, server=None):
        if not server and not plexapp.SERVERMANAGER.selectedServer:
            return
        self._currentServerUUID = (server if server is not None else plexapp.SERVERMANAGER.selectedServer).uuid

    def setUserID(self, account=None, reallyChanged=False):
        if not account and not plexapp.ACCOUNT:
            return
        self._currentUserID = (account if account is not None and reallyChanged else plexapp.ACCOUNT).ID
        self.setGlob()

    def load(self):
        # new load method, v1
        if os.path.isfile(self.dataPath):
            try:
                f = xbmcvfs.File(self.dataPath)
                obj = json.loads(f.read())
                f.close()

                version = obj["version"]
                data = obj["data"]
            except:
                util.ERROR("Couldn't load playback_settings.json")
                return {}

            if version < self.version:
                migratedAny = False
                for v in range(version + 1, self.version + 1):
                    migFunc = "migrateV{}".format(v)
                    if hasattr(self, migFunc):
                        migResult, data = getattr(self, migFunc)(data)
                        if migResult:
                            util.DEBUG_LOG("Migrated playback_settings.json to format v{}", v)
                            migratedAny = True
                if migratedAny:
                    self.save(data=data)

            return data

        else:
            # migrate legacy data
            jstring = plexapp.util.INTERFACE.getRegistry("BingeModeSettings")
            if not jstring:
                # fallback
                jstring = plexapp.util.INTERFACE.getRegistry("AutoSkipSettings")
            if not jstring:
                return {}

            try:
                util.DEBUG_LOG("Loading old BingeModeSettings")
                obj = json.loads(jstring)
                migData = {}
                # migrate old BM settings into new format
                for serverID, userIDs in obj.items():
                    migData[serverID] = {}
                    for userID, ratingKeys in userIDs.items():
                        migData[serverID][userID] = {}
                        for ratingKey, value in ratingKeys.items():
                            migData[serverID][userID][ratingKey] = {"b": value}

                # plexapp.util.INTERFACE.clearRegistry("BingeModeSettings")
                self.save(data=migData)
                return migData
            except:
                util.DEBUG_LOG("Couldn't parse old BingeModeSettings")
            return {}

    def save(self, data=None):
        try:
            f = xbmcvfs.File(self.dataPath, "w")
            f.write(json.dumps({"version": self.version, "data": data or self._data}))
            f.close()
        except:
            util.ERROR("Couldn't write playback_settings.json")
            return
