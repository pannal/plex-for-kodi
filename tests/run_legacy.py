# coding=utf-8
"""Offline Leia suite: python2.7 -B -m tests.run_legacy.

Requires six >= 1.15 and Leia-compatible requests. The full suite additionally
uses Python 3 unittest/mock and AST APIs; run it separately under Python 3.
"""
from __future__ import absolute_import

import unittest


MODULES = (
    'test_advancedsettings', 'test_bgm_fade', 'test_cache', 'test_dropdown',
    'test_home_hubs', 'test_localmode', 'test_pinned_sections',
    'test_plexnet_platform', 'test_runtime_compat', 'test_settings_util',
)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ['tests.' + name for name in MODULES])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
