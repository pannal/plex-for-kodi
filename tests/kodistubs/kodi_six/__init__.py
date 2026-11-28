# coding=utf-8
"""
Stand-in for the `kodi-six` shim PM4K imports everywhere.

On Python 3 the real kodi-six is a straight passthrough to the Kodi modules
(its unicode wrapping only mattered on Python 2), so this just re-exports the
stubs and registers them as submodules for `import kodi_six.xbmc` style
imports.
"""

from __future__ import absolute_import

import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

for _name, _mod in (("xbmc", xbmc), ("xbmcaddon", xbmcaddon), ("xbmcgui", xbmcgui),
                    ("xbmcplugin", xbmcplugin), ("xbmcvfs", xbmcvfs)):
    sys.modules["kodi_six.{0}".format(_name)] = _mod

__all__ = ["xbmc", "xbmcaddon", "xbmcgui", "xbmcplugin", "xbmcvfs"]
