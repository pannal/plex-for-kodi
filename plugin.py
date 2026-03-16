from __future__ import absolute_import
import sys
from lib.kodi_util import ensureHome, xbmc


def main():
    try:
        data = sys.argv[2].lstrip('?')

        if data == "stub":
            return
    except:
        pass
    # This is a hack since it's both a plugin and a script. My Addons and Shortcuts otherwise can't launch the add-on
    ensureHome()
    xbmc.executebuiltin('RunScript(script.plexmod,fromplugin)')


main()
