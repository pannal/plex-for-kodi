# coding=utf-8
"""
plexnet.util._safeUname - the platform identity sent in the X-Plex-* headers.

On Kodi for Xbox (UWP), platform.uname() raises AttributeError ('_winapi' has
no attribute 'CreateProcess'), and plexnet.util calls it at import, so the
whole addon failed to start. The fallback has to keep both indexes the headers
read ([0] platform, [2] release) answerable.
"""

from __future__ import absolute_import

import platform
import sys

from plexnet import util

from .base import KodiTestCase


class SafeUnameTest(KodiTestCase):
    def setUp(self):
        super(SafeUnameTest, self).setUp()
        self._uname = platform.uname

    def tearDown(self):
        platform.uname = self._uname
        super(SafeUnameTest, self).tearDown()

    def _raise(self, exc):
        def uname():
            raise exc
        platform.uname = uname

    def test_a_working_uname_is_passed_through(self):
        self.assertEqual(platform.uname(), util._safeUname())

    def test_no_createprocess_falls_back_to_sys(self):
        self._raise(AttributeError("module '_winapi' has no attribute 'CreateProcess'"))
        uname = util._safeUname()
        expected = 'Windows' if sys.platform == 'win32' else sys.platform
        self.assertEqual(expected, uname[0])
        self.assertIsInstance(uname[2], str)

    def test_an_oserror_falls_back_too(self):
        self._raise(OSError("ver failed"))
        self.assertEqual(3, len(util._safeUname()))

    def test_the_headers_are_set(self):
        self.assertTrue(util.X_PLEX_PLATFORM)
        self.assertIsInstance(util.X_PLEX_PLATFORM_VERSION, str)
