# coding=utf-8
"""
Stand-in for Kodi's `xbmcvfs`, backed by the real filesystem.

Backing it with real files rather than an in-memory dict matters here: the
template engine's write() path checks `Stat().st_size()` against the length of
the data it just wrote, and PM4K's caches round-trip through actual files.
"""

from __future__ import absolute_import

import os
import shutil

from kodienv import ENV


def translatePath(path):
    return ENV.translate_path(path)


def validatePath(path):
    return ENV.translate_path(path)


def makeLegalFilename(filename):
    return ENV.translate_path(filename)


def exists(path):
    """Kodi branches on the trailing separator: with one this is a directory lookup
    (CDirectory::Exists), without one a file lookup (CFile::Exists) - see
    xbmc/interfaces/legacy/ModuleXbmcvfs.cpp. So a directory asked about without the
    separator does NOT exist. os.path.exists() would answer yes to both and hide a
    real, easy-to-hit trap.
    """
    real = ENV.translate_path(path)
    if path.endswith("/") or path.endswith("\\"):
        return os.path.isdir(real)
    return os.path.isfile(real)


def mkdir(path):
    real = ENV.translate_path(path)
    try:
        os.mkdir(real)
    except OSError:
        return False
    return True


def mkdirs(path):
    real = ENV.translate_path(path)
    if os.path.isdir(real):
        return False
    os.makedirs(real)
    return True


def rmdir(path, force=False):
    real = ENV.translate_path(path)
    try:
        shutil.rmtree(real) if force else os.rmdir(real)
    except OSError:
        return False
    return True


def delete(file):
    real = ENV.translate_path(file)
    try:
        os.remove(real)
    except OSError:
        return False
    return True


def rename(file, newFile):
    try:
        os.rename(ENV.translate_path(file), ENV.translate_path(newFile))
    except OSError:
        return False
    return True


def copy(strSource, strDestination):
    try:
        shutil.copyfile(ENV.translate_path(strSource), ENV.translate_path(strDestination))
    except (OSError, IOError):
        return False
    return True


def listdir(path):
    """Kodi returns (dirs, files); a missing path yields two empty lists."""
    real = ENV.translate_path(path)
    dirs, files = [], []
    if os.path.isdir(real):
        for name in sorted(os.listdir(real)):
            (dirs if os.path.isdir(os.path.join(real, name)) else files).append(name)
    return dirs, files


class File(object):
    def __init__(self, filepath, mode="r"):
        self.path = ENV.translate_path(filepath)
        self.mode = mode
        # Kodi's File is bytes-oriented under the hood but read() hands back
        # text; open in binary and decode on the way out to match.
        self._fp = open(self.path, "wb" if "w" in mode else "rb")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read(self, numBytes=0):
        data = self._fp.read(numBytes) if numBytes else self._fp.read()
        return data.decode("utf-8", "replace")

    def readBytes(self, numBytes=0):
        return self._fp.read(numBytes) if numBytes else self._fp.read()

    def write(self, buffer):
        if isinstance(buffer, str):
            buffer = buffer.encode("utf-8")
        self._fp.write(buffer)
        return True

    def size(self):
        return os.path.getsize(self.path)

    def seek(self, seekBytes, iWhence=0):
        return self._fp.seek(seekBytes, iWhence)

    def close(self):
        if not self._fp.closed:
            self._fp.close()


class Stat(object):
    def __init__(self, path):
        self._stat = os.stat(ENV.translate_path(path))

    def st_size(self):
        return self._stat.st_size

    def st_mtime(self):
        return int(self._stat.st_mtime)

    def st_atime(self):
        return int(self._stat.st_atime)

    def st_ctime(self):
        return int(self._stat.st_ctime)

    def st_mode(self):
        return self._stat.st_mode
