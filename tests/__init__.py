# coding=utf-8
"""
Test bootstrap for PM4K.

Importing this package installs the Kodi stubs on sys.path *before* anything
under lib/ gets imported, which is what makes the addon importable outside
Kodi at all. Every test module lives inside this package, so `unittest
discover` and pytest both run this first.

    python3 -m unittest discover -s tests -t .        # no dependencies
    python3 -m pytest tests                           # nicer output
"""

from __future__ import absolute_import

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_ROOT = os.path.join(REPO_ROOT, "tests")
STUBS_ROOT = os.path.join(TESTS_ROOT, "kodistubs")
FIXTURES_ROOT = os.path.join(TESTS_ROOT, "fixtures")

# kodistubs first: `import xbmc` and `from kodi_six import xbmc` must resolve
# to the stubs, not to a real Kodi install that happens to be on the path.
for _path in (STUBS_ROOT, REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# lib/__init__.py appends lib/_included_packages to sys.path, which is how the
# addon makes `plexnet`, `ibis` and friends importable. Do it here so test
# modules can import them by their bare names too.
import lib  # noqa: E402,F401
