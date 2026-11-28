# coding=utf-8

import os
import copy
import re
import json

import plexnet.util

from kodi_six import xbmcvfs

from .util import translatePath, ADDON, ERROR, LOG, T, getSetting, showNotification


PM_MCMT_RE = re.compile(r'/\*.+\*/\s?', re.IGNORECASE | re.MULTILINE | re.DOTALL)
PM_CMT_RE = re.compile(r'[\t ]+//.+\n?')
PM_COMMA_RE = re.compile(r',\s*}\s*}')


def norm_sep(s):
    return "\\" in s and "\\" or "/"


class PathMappingManager(object):
    mapfile = os.path.join(translatePath(ADDON.getAddonInfo("profile")), "path_mapping.json")
    PATH_MAP = {}

    # Kodi-side roots that turned out to be unreachable: {server name: {map_path: True}}
    BROKEN_MAP = {}
    # (server name, map_path, kind) we've already told the user about this session
    NOTIFIED = set()

    def __init__(self):
        self.load()

    def load(self):
        if xbmcvfs.exists(self.mapfile):
            try:
                f = xbmcvfs.File(self.mapfile)
                try:
                    raw = f.read()
                finally:
                    f.close()

                # sanitize json

                # remove multiline comments
                data = PM_MCMT_RE.sub("", raw)
                # remove comments
                data = PM_CMT_RE.sub("", data)
                # remove invalid trailing comma

                data = PM_COMMA_RE.sub("}}", data)
                self.PATH_MAP = json.loads(data)
            except:
                ERROR("Couldn't read path_mapping.json")
            else:
                LOG("Path mapping: {}".format(repr(self.PATH_MAP)))

    @property
    def mapping(self):
        return self.PATH_MAP and getSetting("path_mapping", True)

    def getMappedPathFor(self, path, server, return_rep=False):
        if self.mapping:
            match = ("", "")

            for map_path, pms_path in self.PATH_MAP.get(server.name, {}).items():
                # the longest matching path wins
                if path.startswith(pms_path) and len(pms_path) > len(match[1]):
                    match = (map_path, pms_path)

            if all(match):
                map_path, pms_path = match

                if return_rep:
                    sep = norm_sep(map_path)

                    # replace match and normalize path separator to separator style of map_path
                    url = path.replace(pms_path, map_path, 1).replace(sep == "/" and "\\" or "/", sep)

                    # fixme: this is dirty.
                    return url, pms_path, sep
                return map_path, pms_path, None
        return None, None, None

    def markMappingState(self, server_name, map_path, works):
        """Record whether the Kodi-side root map_path is currently usable.
        Returns True when the state actually changed.
        """
        states = self.BROKEN_MAP.setdefault(server_name, {})
        if states.get(map_path, False) == (not works):
            return False

        states[map_path] = not works
        if works:
            # let a later failure speak up again
            self.NOTIFIED = set(k for k in self.NOTIFIED if k[:2] != (server_name, map_path))
        LOG("Path mapping: {} on {} is {}".format(map_path, server_name,
                                                  works and "reachable again" or "unreachable"))
        return True

    def isMappingBroken(self, server_name, map_path):
        return self.BROKEN_MAP.get(server_name, {}).get(map_path, False)

    def claimNotification(self, server_name, map_path, kind):
        """True the first time a given failure needs announcing. Callers that can batch
        several roots claim them all and emit a single popup; Kodi queues notifications,
        so one per root would keep the screen covered for 5s * number of libraries.
        """
        key = (server_name, map_path, kind)
        if key in self.NOTIFIED:
            return False
        self.NOTIFIED.add(key)
        return True

    def notifyOnce(self, server_name, map_path, kind, message):
        """Notify at most once per mapped root per session and cause, so a multi-part
        title can't produce a burst of identical popups.
        """
        if self.claimNotification(server_name, map_path, kind):
            showNotification(message, time_ms=5000, header=T(35034, "Path mapping"))

    def notify(self, message):
        showNotification(message, time_ms=5000, header=T(35034, "Path mapping"))

    def verifyMapping(self, server_name, map_path, notify=False):
        """Stat a mapped root. Blocks for the full mount timeout on a dead network share,
        so keep this off the UI thread. Returns True when the broken/working state changed.
        """
        # xbmcvfs.exists() only treats a path as a directory when it ends in a separator,
        # otherwise it stats it as a file and a perfectly good mount reports missing.
        # path_mapping.json is hand-written and its documented examples have no trailing
        # separator, so normalize before asking.
        sep = norm_sep(map_path)
        probe_path = map_path if map_path.endswith(sep) else map_path + sep

        try:
            works = bool(xbmcvfs.exists(probe_path))
        except:
            ERROR("Path mapping: couldn't check {}".format(map_path))
            works = False

        changed = self.markMappingState(server_name, map_path, works)
        if notify and not works:
            self.notifyOnce(server_name, map_path, "root",
                            T(35035, "Mapped path unavailable: {}").format(map_path))
        return changed

    def reportMappedFileMissing(self, server_name, map_path):
        """A mapped file didn't exist at playback time. That alone doesn't make the mapping
        broken - the file itself may simply be gone - so check the root as well.
        """
        if self.isMappingBroken(server_name, map_path):
            # already known dead; re-statting would cost another mount timeout on the
            # playback thread and tell us nothing new
            return False

        changed = self.verifyMapping(server_name, map_path, notify=True)
        if not self.isMappingBroken(server_name, map_path):
            self.notifyOnce(server_name, map_path, "file",
                            T(35036, "Mapped file missing, streaming from the server instead"))
        return changed

    def deletePathMapping(self, target, server=None, save=True):
        server = server or plexnet.util.SERVERMANAGER.selectedServer
        if not server:
            ERROR("Delete path mapping: Something went wrong")
            return

        if server.name not in self.PATH_MAP:
            return

        pm = copy.deepcopy(self.PATH_MAP)

        deleted = None
        for s, t in pm[server.name].items():
            if target == t:
                deleted = s
                del self.PATH_MAP[server.name][s]
                break

        if deleted:
            # don't keep flagging a mapping that no longer exists
            self.BROKEN_MAP.get(server.name, {}).pop(deleted, None)
            self.NOTIFIED = set(k for k in self.NOTIFIED if k[:2] != (server.name, deleted))

        if save and deleted and self.save():
            LOG("Path mapping stored after deletion of {}:{}".format(deleted, target))

    def addPathMapping(self, source, target, server=None, save=True):
        server = server or plexnet.util.SERVERMANAGER.selectedServer
        if not server:
            ERROR("Add path mapping: Something went wrong")
            return

        if server.name not in self.PATH_MAP:
            self.PATH_MAP[server.name] = {}

        sep = norm_sep(source)

        if not source.endswith(sep):
            source += sep

        sep = norm_sep(target)

        if not target.endswith(sep):
            target += sep

        self.PATH_MAP[server.name][source] = target
        if save and self.save():
            LOG("Path mapping stored for {}:{}".format(source, target))

    def save(self):
        try:
            f = xbmcvfs.File(self.mapfile, "w")
            try:
                f.write(json.dumps(self.PATH_MAP))
            finally:
                f.close()
        except:
            ERROR("Couldn't write path_mapping.json")
        else:
            return True


pmm = PathMappingManager()
