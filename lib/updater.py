# coding=utf-8
import os
import re

import requests
import shutil
import traceback
import hashlib

from zipfile import ZipFile
from .version import version_compare
# noinspection PyUnresolvedReferences
from .kodi_util import translatePath, xbmc, ADDON
from .kodijsonrpc import rpc


VERSION_RE = re.compile(r'<addon id="script\.plexmod".*version="([A-Za-z0-9.+:~-]+)".*?<requires>',
                        re.MULTILINE | re.DOTALL | re.S)

TEMP_PATH = translatePath("special://temp/")

try:
    LANGUAGE_RESOURCE = rpc.Settings.GetSettingValue(setting='locale.language')['value']
except:
    LANGUAGE_RESOURCE = "resource.language.en_gb"


class ServiceMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self, *args, **kwargs)

        self.sleeping = False

    def onNotification(self, sender, method, data):
        if sender == "xbmc" and method == "System.OnSleep":
            self.sleeping = True

        elif sender == "xbmc" and method == "System.OnWake":
            self.sleeping = False


UPDATERS = {}

def register_updater(cls):
    UPDATERS[cls.mode] = cls
    return cls


class UpdateException(Exception):
    def __init__(self, msg, status_code=None):
        self.msg = msg
        self.status_code = status_code

    def __str__(self):
        return '{}: {}'.format(self.msg, self.status_code)


class UpdateCheckFailed(UpdateException):
    pass


class UpdateDownloadFailed(UpdateException):
    pass

class UpdateUnpackFailed(UpdateException):
    pass

class UpdaterSkipException(Exception):
    pass


def get_digest(file_path):
    h = hashlib.md5()

    with open(file_path, 'rb') as file:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            chunk = file.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


@register_updater
class Updater(object):
    repo = "pannal/plex-for-kodi"
    mode = "beta"
    branch = None
    remote_version = None
    is_downgrade = False
    headers = {
        'User-Agent': xbmc.getUserAgent()
    }

    def __init__(self, branch="develop_kodi21", mode="beta"):
        self.branch = branch
        self.mode = mode
        self.is_downgrade = False

    @property
    def kodi_ver_name(self):
        name = "matrix"
        if self.branch == "addon_kodi18":
            name = "leia"
        return name

    @property
    def info_url(self):
        return 'https://raw.githubusercontent.com/{}/{}/addon.xml'.format(self.repo, self.branch)

    @property
    def download_url(self):
        return "https://github.com/{}/archive/refs/heads/{}.zip".format(self.repo, self.branch)

    @property
    def archive_name(self):
        return 'script.plexmod-{}.zip'.format(self.remote_version)

    @property
    def archive_path(self):
        return os.path.join(TEMP_PATH, self.archive_name)

    def check(self, current_version, allow_downgrade=False):
        self.is_downgrade = False
        try:
            r = requests.get(self.info_url, timeout=10, headers=self.headers)
        except:
            tb = traceback.format_exc()
            raise UpdateCheckFailed('Update check failed: {}'.format(tb))

        data = VERSION_RE.findall(r.text)
        if data:
            self.remote_version = new_version = data[0]
            vc = version_compare(new_version, current_version)
            if allow_downgrade and vc < 0:
                self.is_downgrade = True
            return new_version if vc > 0 or (allow_downgrade and vc != 0) else False

        raise UpdateCheckFailed('Update check failed: No data returned')

    def download(self):
        archive_url = self.download_url
        zip_loc = self.archive_path
        if os.path.exists(zip_loc):
            return zip_loc

        try:
            result = requests.get(archive_url, stream=True, headers=self.headers)
        except:
            tb = traceback.format_exc()
            raise UpdateDownloadFailed('Update download failed: {}'.format(tb))

        if result.status_code != 200:
            # do something
            raise UpdateDownloadFailed('Update download failed', status_code=result.status_code)

        with open(zip_loc, 'wb') as f:
            result.raw.decode_content = True
            shutil.copyfileobj(result.raw, f)

        return zip_loc

    def unpack(self):
        try:
            zf = ZipFile(self.archive_path)
            loc = os.path.splitext(self.archive_path)[0]
            if os.path.isdir(loc):
                shutil.rmtree(loc, ignore_errors=True)
            os.mkdir(loc)

            # clean archive
            skip = (".github", ".gitignore", ".gitattributes")
            final_list = zf.namelist()
            sub_dir = None
            for entry in final_list[:]:
                a = entry.split("/", 1)
                if not sub_dir:
                    sub_dir = a[0]

                for s in skip:
                    if a[1].startswith(s):
                        final_list.remove(entry)

            zf.extractall(loc, members=final_list)
            final_dest = os.path.join(loc, "script.plexmod")
            if sub_dir != "script.plexmod":
                os.rename(os.path.join(loc, sub_dir), final_dest)
            return final_dest
        except Exception:
            tb = traceback.format_exc()
            raise UpdateUnpackFailed(tb)

    def get_major_changes(self):
        # check current language file
        ptl = ("resources", "language", LANGUAGE_RESOURCE, "strings.po")
        if get_digest(os.path.join(translatePath(ADDON.getAddonInfo('path')), *ptl)) != \
            get_digest(os.path.join(os.path.splitext(self.archive_path)[0], "script.plexmod", *ptl)):
            return "language"

        # check service.py
        if get_digest(os.path.join(translatePath(ADDON.getAddonInfo('path')), "service.py")) != \
                get_digest(os.path.join(os.path.splitext(self.archive_path)[0], "script.plexmod", "service.py")):
            return "service"

    def install(self, path):
        dest = os.path.join(translatePath('special://home/addons/'), "script.plexmod")
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(path, dest)
        return dest

    def cleanup(self):
        try:
            os.remove(self.archive_path)
            shutil.rmtree(os.path.splitext(self.archive_path)[0], ignore_errors=True)
        except:
            pass


@register_updater
class StableUpdater(Updater):
    mode = "stable"

    @property
    def info_url(self):
        return ('https://raw.githubusercontent.com/pannal/dontpanickodi/master/{}/zips/script.plexmod/'
                'addon.xml').format(self.kodi_ver_name)

    @property
    def download_url(self):
        return ('https://github.com/pannal/dontpanickodi/raw/master/{}/zips/'
                'script.plexmod/script.plexmod-{}.zip').format(self.kodi_ver_name, self.remote_version)


@register_updater
class RepositoryUpdater(Updater):
    mode = "repository"

    def check(self, current_version, allow_downgrade=False):
        xbmc.executebuiltin('UpdateAddonRepos', True)
        xbmc.executebuiltin('UpdateLocalAddons', True)
        return False


def get_updater(mode):
    return UPDATERS[mode]
