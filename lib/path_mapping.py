# coding=utf-8

import os
import copy
import re
import json

import plexnet.util

from kodi_six import xbmcvfs

from .util import translatePath, ADDON, ERROR, LOG, getSetting


PM_MCMT_RE = re.compile(r'/\*.+\*/\s?', re.IGNORECASE | re.MULTILINE | re.DOTALL)
PM_CMT_RE = re.compile(r'[\t ]+//.+\n?')
PM_COMMA_RE = re.compile(r',\s*}\s*}')


def norm_sep(s):
    return "\\" in s and "\\" or "/"


class PathMappingManager(object):
    mapfile = os.path.join(translatePath(ADDON.getAddonInfo("profile")), "path_mapping.json")
    PATH_MAP = {}

    def __init__(self):
        self.load()

    def load(self):
        if xbmcvfs.exists(self.mapfile):
            try:
                f = xbmcvfs.File(self.mapfile)
                # sanitize json

                # remove multiline comments
                data = PM_MCMT_RE.sub("", f.read())
                # remove comments
                data = PM_CMT_RE.sub("", data)
                # remove invalid trailing comma

                data = PM_COMMA_RE.sub("}}", data)
                self.PATH_MAP = json.loads(data)
                f.close()
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
            f.write(json.dumps(self.PATH_MAP))
            f.close()
        except:
            ERROR("Couldn't write path_mapping.json")
        else:
            return True


pmm = PathMappingManager()
