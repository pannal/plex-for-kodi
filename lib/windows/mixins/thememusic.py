# coding=utf-8
import os

from kodi_six import xbmcvfs

from lib import backgroundthread, util
from lib import player
from lib.path_mapping import pmm
from plexnet import util as pnUtil


class ThemeMusicTask(backgroundthread.Task):
    def setup(self, url, volume, rating_key):
        self.url = url
        self.volume = volume
        self.rating_key = rating_key
        return self

    def run(self):
        player.PLAYER.playBackgroundMusic(self.url, self.volume, self.rating_key)


class ThemeMusicMixin(object):
    """
    needs watchlistmixin as well to work
    """
    def isPlayingOurs(self, item):
        return (player.PLAYER.bgmPlaying and player.PLAYER.handler.currentlyPlaying in
                         [self.wl_ref, item.ratingKey]+self.wl_item_children)

    def themeMusicInit(self, item, locations=None):
        isPlayingOurs = self.isPlayingOurs(item)
        playBGM = False
        if not isPlayingOurs:
            playBGM = True

        if util.getSetting("slow_connection"):
            playBGM = False

        if playBGM:
            self.playThemeMusic(item.theme and item.theme.asURL(True) or None, item.ratingKey, locations or [loc.get("path") for loc in item.locations],
                                item.server)


    def themeMusicReinit(self, item):
        if player.PLAYER.bgmPlaying and not self.isPlayingOurs(item):
            player.PLAYER.stopAndWait()
        self.useBGM = False

    def playThemeMusic(self, theme_url, identifier, locations, server):
        volume = pnUtil.INTERFACE.getThemeMusicValue()
        if not volume:
            return

        if pmm.mapping:
            theme_found = False
            for loc in locations:
                path, pms_path, sep = pmm.getMappedPathFor(loc, server, return_rep=True)
                if path and pms_path:
                    for codec in pnUtil.AUDIO_CODECS_TC:
                        final_path = os.path.join(path, "theme.{}".format(codec)).replace(sep == "/" and "\\" or "/", sep)
                        if path and xbmcvfs.exists(final_path):
                            theme_url = final_path
                            theme_found = True
                            util.DEBUG_LOG("ThemeMusicMixin: Using {} as theme music", theme_url)
                            break
                    if theme_found:
                        break

        if theme_url:
            task = ThemeMusicTask().setup(theme_url, volume, identifier)
            backgroundthread.BGThreader.addTask(task)
            self.useBGM = True
        else:
            from lib import player
            if player.PLAYER.bgmPlaying:
                player.PLAYER.stopAndWait()
