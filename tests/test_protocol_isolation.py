# coding=utf-8
"""The protocol library must stay Kodi-free (spec: Architecture)."""

from __future__ import absolute_import

import os
import re
import unittest

from . import REPO_ROOT

MODULES = ("ws.py", "syncplay.py", "watchtogether.py")
# from kodi_six import xbmc and from lib.kodi_util import ... are this repo's
# Kodi channels; direct import xbmc alone misses them. lib.kodi_util is
# Kodi-bound (calls xbmcaddon.Addon at import time).
KODI_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+xbmc"
    r"|^\s*from\s+(?:kodi_six|lib\.kodi_util)\s+import",
    re.MULTILINE,
)


class IsolationTest(unittest.TestCase):
    def test_protocol_modules_never_import_kodi(self):
        for name in MODULES:
            with open(os.path.join(REPO_ROOT, "lib", name), "r",
                      encoding="utf-8") as fp:
                source = fp.read()
            self.assertIsNone(
                KODI_IMPORT.search(source),
                "%s must not import xbmc — it is the testability boundary "
                "that keeps the protocol layer deletable (spec: risks)" % name)
