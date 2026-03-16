from __future__ import absolute_import

from kodi_six import xbmc
from kodi_six import xbmcgui

from lib import player
from lib import util
from . import currentplaylist
from . import kodigui
from . import opener


def timeDisplay(ms):
    h = ms / 3600000
    m = (ms % 3600000) / 60000
    s = (ms % 60000) / 1000
    return '{0:0>2}:{1:0>2}:{2:0>2}'.format(h, m, s)


def simplifiedTimeDisplay(ms):
    left, right = timeDisplay(ms).rsplit(':', 1)
    left = left.lstrip('0:') or '0'
    return left + ':' + right


class MusicPlayerWindow(currentplaylist.CurrentPlaylistWindow):
    xmlFile = 'script-plex-music_player.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    SEEK_BUTTON_ID = 500
    SEEK_IMAGE_ID = 200
    SHUFFLE_REMOTE_BUTTON_ID = 422
    REPEAT_BUTTON_ID = 401
    SKIP_PREV_BUTTON_ID = 404
    SKIP_NEXT_BUTTON_ID = 409
    STOP_BUTTON_ID = 407

    SEEK_IMAGE_WIDTH = 1920

    BAR_RIGHT = 1920

    def __init__(self, *args, **kwargs):
        kodigui.ControlledWindow.__init__(self, *args, **kwargs)
        self.track = kwargs.get('track')
        self.playlist = kwargs.get('playlist')
        self.album = kwargs.get('album')
        self.selectedOffset = 0
        self.exitCommand = None
        self.duration = None
        self.ignoreStopCommands = False

        if self.track:
            self.duration = self.track.duration.asInt()
        else:
            self.setDuration()

    def onFirstInit(self):
        if self.playlist and self.playlist.isRemote:
            self.playlist.on('change', self.updateProperties)
        self.setupSeekbar()
        self.selectionBoxMax = self.SEEK_IMAGE_WIDTH - (self.selectionBoxHalf - 3)

        self.commonInit()
        self.updateProperties()
        self.play()
        self.setFocusId(406)

    def doClose(self, **kwargs):
        player.PLAYER.off('av.started', self.onPlayBackStarted)
        if self.playlist and self.playlist.isRemote:
            self.playlist.off('change', self.updateProperties)

        self.commonDeinit()
        kodigui.ControlledWindow.doClose(self)

    def processCommand(self, command):
        if command == "STOP":
            self.doClose()
            return
        super(MusicPlayerWindow, self).processCommand(command)

    def onAction(self, action):
        if self.ignoreStopCommands and action in (xbmcgui.ACTION_PREVIOUS_MENU,
                                                  xbmcgui.ACTION_NAV_BACK):
            if not self.is_current_window:
                return
        elif not self.ignoreStopCommands:
            if not self.is_current_window and action != xbmcgui.ACTION_STOP:
                return
        try:
            if action == xbmcgui.ACTION_STOP:
                self.stopButtonClicked()
                return
        except:
            util.ERROR()

        super(MusicPlayerWindow, self).onAction(action)

    def onClick(self, controlID):
        if controlID == self.PLAYLIST_BUTTON_ID:
            self.showPlaylist()
        elif controlID == self.SEEK_BUTTON_ID:
            self.seekButtonClicked()
        elif controlID == self.SHUFFLE_REMOTE_BUTTON_ID:
            self.playlist.setShuffle()
        elif controlID == self.REPEAT_BUTTON_ID:
            self.repeatButtonClicked()
        elif controlID == self.SKIP_PREV_BUTTON_ID:
            self.skipPrevButtonClicked()
        elif controlID == self.SKIP_NEXT_BUTTON_ID:
            self.skipNextButtonClicked()
        elif controlID == self.OPTIONS_BUTTON_ID:
            self.optionsButtonClicked((1240, 1060))
        elif controlID == self.STOP_BUTTON_ID:
            self.stopButtonClicked()

    def repeatButtonClicked(self):
        if self.playlist and self.playlist.isRemote:
            if xbmc.getCondVisibility('Playlist.IsRepeatOne'):
                xbmc.executebuiltin('PlayerControl(RepeatOff)')
            elif self.playlist.isRepeat:
                self.playlist.setRepeat(False)
                self.playlist.refresh(force=True)
                xbmc.executebuiltin('PlayerControl(RepeatOne)')
            else:
                self.playlist.setRepeat(True)
                self.playlist.refresh(force=True)
        else:
            xbmc.executebuiltin('PlayerControl(Repeat)')

    def skipPrevButtonClicked(self):
        if not xbmc.getCondVisibility('MusicPlayer.HasPrevious') and self.playlist and self.playlist.isRemote:
            util.DEBUG_LOG('MusicPlayer: No previous in Kodi playlist - refreshing remote PQ')
            if not self.playlist.refresh(force=True, wait=True):
                return

        self.onAudioStarting()
        xbmc.executebuiltin('PlayerControl(Previous)')

    def skipNextButtonClicked(self):
        if not xbmc.getCondVisibility('MusicPlayer.HasNext') and self.playlist and self.playlist.isRemote:
            util.DEBUG_LOG('MusicPlayer: No next in Kodi playlist - refreshing remote PQ')
            if not self.playlist.refresh(force=True, wait=True):
                return

        self.onAudioStarting()
        xbmc.executebuiltin('PlayerControl(Next)')

    def showPlaylist(self):
        self.processCommand(opener.handleOpen(currentplaylist.CurrentPlaylistWindow, winID=self._winID))

    def stopButtonClicked(self):
        player.PLAYER.stopAndWait(fade=True)
        self.doClose()

    def updateProperties(self, **kwargs):
        if self.playlist:
            if self.playlist.isRemote:
                self.setProperty('pq.isRemote', '1')
                self.setProperty('pq.hasnext', self.playlist.allowSkipNext and '1' or '')
                self.setProperty('pq.hasprev', self.playlist.allowSkipPrev and '1' or '')
                self.setProperty('pq.repeat', self.playlist.isRepeat and '1' or '')
                self.setProperty('pq.shuffled', self.playlist.isShuffled and '1' or '')
            else:
                self.setProperties(('pq.isRemote', 'pq.hasnext', 'pq.hasprev', 'pq.repeat', 'pq.shuffled'), '')

    def play(self):
        if not self.track:
            return

        if util.trackIsPlaying(self.track):
            return

        self.onAudioStarting()

        fanart = None
        if self.playlist:
            fanart = self.playlist.get('composite') or self.playlist.defaultArt
        # player.PLAYER.playAudio(self.track, fanart=self.getProperty('background'))
        if self.album:
            index = 0
            for i, track in enumerate(self.album.tracks()):
                if track == self.track:
                    index = i
            player.PLAYER.playAlbum(self.album, startpos=index, fanart=fanart)
        elif self.playlist:
            player.PLAYER.playAudioPlaylist(self.playlist, startpos=list(self.playlist.items()).index(self.track), fanart=fanart)
        else:
            player.PLAYER.playAudio(self.track)
