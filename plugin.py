from __future__ import absolute_import
from kodi_six import xbmc
from kodi_six import xbmcplugin
from kodi_six import xbmcgui
import sys
import base64
from lib import _included_packages, plex, util
from plexnet import audio, plexplayer, plexapp
from plexnet import util as plexnetUtil

HANDLE = int(sys.argv[1])

BASE_LOG = util.LOG


def LOG(msg):
    BASE_LOG('(plugin) - {0}'.format(plexnetUtil.cleanToken(msg)))


util.LOG = LOG


def playTrack(track):
    track.reload()
    apobj = plexplayer.PlexAudioPlayer(track)
    url = apobj.build()['url']
    url = util.addURLParams(url, {
        'X-Plex-Client-Profile-Name': 'Chrome',
        'X-Plex-Client-Identifier': plexapp.util.INTERFACE.getGlobal('clientIdentifier')
    })
    LOG('Playing URL: {0}'.format(url))

    return xbmcgui.ListItem(path=url)


def playVideo(video):
    return None


def play(data):
    try:
        from plexnet import plexobjects

        plexObject = plexobjects.PlexObject.deSerialize(base64.urlsafe_b64decode(data[1:]))

        if plexObject.type == 'track':
            listitem = playTrack(plexObject)
        elif plexObject.type in ('episode', 'movie', 'clip'):
            listitem = playVideo(plexObject)
    except:
        util.ERROR()
        xbmcplugin.setResolvedUrl(HANDLE, False, None)
        return

    xbmcplugin.setResolvedUrl(HANDLE, True, listitem)


def main():
    try:
        if len(sys.argv) < 3:
            return

        path = sys.argv[0].split('/', 3)[-1]
        data = sys.argv[2].lstrip('?')

        if path == 'play':
            play(data)
        else:  # This is a hack since it's both a plugin and a script. My Addons and Shortcuts otherwise can't launch the add-on
            xbmc.executebuiltin('Action(back)')  # This sometimes works to back out of the plugin directory display
            xbmc.executebuiltin('RunScript(script.plexmod)')
    except:
        util.ERROR()


main()
