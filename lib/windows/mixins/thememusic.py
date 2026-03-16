# coding=utf-8
import os

from kodi_six import xbmcvfs

from lib import backgroundthread, util
from lib import player
from lib.path_mapping import pmm
from plexnet import util as pnUtil
from plexnet.http import GET


class ThemeMusicTask(backgroundthread.Task):
    temp_path = util.translatePath("special://temp/")
    def setup(self, url, volume, rating_key, is_local=False, server_is_local=False, fade_fast=False):
        self.url = url
        self.volume = volume
        self.rating_key = rating_key
        self.is_local = is_local
        self.server_is_local = server_is_local
        self.fade_fast = fade_fast
        return self

    def run(self):
        path = self.url
        is_cached = False
        if not self.is_local and util.addonSettings.cacheThemeMusic:
            if not self.server_is_local:
                fn = os.path.join(self.temp_path, "theme_{}.mp3".format(self.rating_key))
                if not os.path.exists(fn):  # and not xbmc.getCacheThumbName(tmpFn):
                    try:
                        r = GET(self.url)
                        r.raise_for_status()
                        f = xbmcvfs.File(fn, 'w')
                        f.write(r.content)
                        f.close()
                        path = fn
                        is_cached = True
                        util.DEBUG_LOG("Cached theme music for {} to: {}", self.rating_key, path)
                    except:
                        util.LOG("Couldn't download theme music: {}", self.rating_key)
                        return
            else:
                util.DEBUG_LOG("Not caching theme music for {} as the server is local", self.rating_key)

        player.PLAYER.playBackgroundMusic(path, self.volume, self.rating_key, is_local=self.is_local,
                                          is_cached=is_cached, fade=util.addonSettings.themeMusicFade,
                                          fade_fast=self.fade_fast)


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
        fadeFast = False
        if not isPlayingOurs:
            playBGM = True
            if player.PLAYER.bgmPlaying:
                fadeFast = True

        if util.getSetting("slow_connection"):
            playBGM = False

        if playBGM:
            self.playThemeMusic(item.theme and item.theme.asURL(True) or None, item.ratingKey, locations or [loc.get("path") for loc in item.locations],
                                item.server, fade_fast=fadeFast)


    def themeMusicReinit(self, item):
        if player.PLAYER.bgmPlaying and not self.isPlayingOurs(item):
            player.PLAYER.stopAndWait(fade=util.addonSettings.themeMusicFade, deferred=True)
        self.useBGM = False

    def playThemeMusic(self, theme_url, identifier, locations, server, fade_fast=False):
        volume = pnUtil.INTERFACE.getThemeMusicValue()
        if not volume:
            return

        is_local = False
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
                        is_local = True
                        break

        if theme_url:
            task = ThemeMusicTask().setup(theme_url, volume, identifier, is_local=is_local, fade_fast=fade_fast,
                                          server_is_local=server.isLocal)
            backgroundthread.BGThreader.addTask(task)
            self.useBGM = True
        else:
            from lib import player
            if player.PLAYER.bgmPlaying:
                player.PLAYER.stopAndWait(fade=True)
