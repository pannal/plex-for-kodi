from __future__ import absolute_import
import json
import sys
import time
from urllib.parse import parse_qs
from lib.kodi_util import ensureHome, xbmc
from lib.properties import setGlobalProperty


def main():
    try:
        data = sys.argv[2].lstrip('?')

        if data == "stub":
            return

        # Check for JSON-RPC Addons.ExecuteAddon deep-link play request.
        params = parse_qs(data)
        action = params.get("action", [""])[0]
        rating_key = params.get("rating_key", [""])[0]
        if action == "play" and rating_key:
            server_uuid = params.get("server_uuid", [""])[0]
            start_over = params.get("start_over", [""])[0].lower() in ("1", "true")
            play_arg = json.dumps({
                "rating_key":  rating_key,
                "server_uuid": server_uuid,
                "start_over": start_over,
                "ts": time.time(),
            })
            setGlobalProperty("deeplink_play", play_arg, wait=True)
    except:
        pass
    # This is a hack since it's both a plugin and a script. My Addons and Shortcuts otherwise can't launch the add-on
    ensureHome()
    xbmc.executebuiltin('RunScript(script.plexmod,fromplugin)')


main()
