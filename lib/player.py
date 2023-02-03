from __future__ import absolute_import
import base64
import threading
import six

from kodi_six import xbmc
from kodi_six import xbmcgui
from . import backgroundthread
from . import kodijsonrpc
from . import colors
from .windows import seekdialog
from . import util
from plexnet import plexplayer
from plexnet import plexapp
from plexnet import signalsmixin
from plexnet import util as plexnetUtil

from six.moves import range

FIVE_MINUTES_MILLIS = 300000


class BasePlayerHandler(object):
    def __init__(self, player, session_id=None):
        self.player = player
        self.media = None
        self.baseOffset = 0
        self.timelineType = None
        self.lastTimelineState = None
        self.ignoreTimelines = False
        self.playQueue = None
        self.sessionID = session_id

    def onPrePlayStarted(self):
        pass

    def onPlayBackStarted(self):
        pass

    def onPlayBackPaused(self):
        pass

    def onPlayBackResumed(self):
        pass

    def onPlayBackStopped(self):
        pass

    def onPlayBackEnded(self):
        pass

    def onPlayBackSeek(self, stime, offset):
        pass

    def onPlayBackFailed(self):
        pass

    def onVideoWindowOpened(self):
        pass

    def onVideoWindowClosed(self):
        pass

    def onVideoOSD(self):
        pass

    def onSeekOSD(self):
        pass

    def onMonitorInit(self):
        pass

    def tick(self):
        pass

    def close(self):
        pass

    @property
    def trueTime(self):
        return self.baseOffset + self.player.currentTime

    def getCurrentItem(self):
        if self.player.playerObject:
            return self.player.playerObject.item
        return None

    def shouldSendTimeline(self, item):
        return item.ratingKey and item.getServer()

    def currentDuration(self):
        if self.player.playerObject:
            try:
                return int(self.player.getTotalTime() * 1000)
            except RuntimeError:
                pass

        return 0

    def updateNowPlaying(self, force=False, refreshQueue=False, state=None):
        if self.ignoreTimelines:
            return

        item = self.getCurrentItem()
        if not item:
            return

        if not self.shouldSendTimeline(item):
            return

        state = state or self.player.playState
        # Avoid duplicates
        if state == self.lastTimelineState and not force:
            return

        self.lastTimelineState = state
        # self.timelineTimer.reset()

        time = int(self.trueTime * 1000)

        # self.trigger("progress", [m, item, time])

        if refreshQueue and self.playQueue:
            self.playQueue.refreshOnTimeline = True

        plexapp.util.APP.nowplayingmanager.updatePlaybackState(
            self.timelineType, self.player.playerObject, state, time, self.playQueue, duration=self.currentDuration()
        )


class SeekPlayerHandler(BasePlayerHandler):
    NO_SEEK = 0
    SEEK_IN_PROGRESS = 2
    SEEK_PLAYLIST = 3
    SEEK_REWIND = 4
    SEEK_POST_PLAY = 5

    MODE_ABSOLUTE = 0
    MODE_RELATIVE = 1

    def __init__(self, player, session_id=None):
        BasePlayerHandler.__init__(self, player, session_id)
        self.dialog = None
        self.playlist = None
        self.playQueue = None
        self.timelineType = 'video'
        self.ended = False
        self.bifURL = ''
        self.title = ''
        self.title2 = ''
        self.reset()

    def reset(self):
        self.duration = 0
        self.offset = 0
        self.baseOffset = 0
        self.seeking = self.NO_SEEK
        self.seekOnStart = 0
        self.mode = self.MODE_RELATIVE
        self.ended = False

    def setup(self, duration, offset, bif_url, title='', title2='', seeking=NO_SEEK, chapters=None):
        self.ended = False
        self.baseOffset = offset / 1000.0
        self.seeking = seeking
        self.duration = duration
        self.bifURL = bif_url
        self.title = title
        self.title2 = title2
        self.chapters = chapters or []
        self.getDialog(setup=True)
        self.dialog.setup(self.duration, int(self.baseOffset * 1000), self.bifURL, self.title, self.title2, chapters=self.chapters)

    def getDialog(self, setup=False):
        if not self.dialog:
            self.dialog = seekdialog.SeekDialog.create(show=False, handler=self)

        return self.dialog

    @property
    def trueTime(self):
        if self.mode == self.MODE_RELATIVE:
            return self.baseOffset + self.player.currentTime
        else:
            if self.seekOnStart:
                return self.player.playerObject.startOffset + (self.seekOnStart / 1000)
            else:
                return self.player.currentTime + self.player.playerObject.startOffset

    def shouldShowPostPlay(self):
        if self.playlist and self.playlist.TYPE == 'playlist':
            return False

        if (not util.advancedSettings.postplayAlways and self.player.video.duration.asInt() <= FIVE_MINUTES_MILLIS)\
                or util.advancedSettings.postplayTimeout <= 0:
            return False

        return True

    def showPostPlay(self):
        if not self.shouldShowPostPlay():
            return

        self.seeking = self.SEEK_POST_PLAY
        self.hideOSD(delete=True)

        self.player.trigger('post.play', video=self.player.video, playlist=self.playlist, handler=self)

        return True

    def next(self, on_end=False):
        if self.playlist and next(self.playlist):
            self.seeking = self.SEEK_PLAYLIST

        if on_end:
            if self.showPostPlay():
                return True

        if not self.playlist:
            return False

        self.player.playVideoPlaylist(self.playlist, handler=self)

        return True

    def prev(self):
        if not self.playlist or not self.playlist.prev():
            return False

        self.seeking = self.SEEK_PLAYLIST
        self.player.playVideoPlaylist(self.playlist, handler=self)

        return True

    def playAt(self, pos):
        if not self.playlist or not self.playlist.setCurrent(pos):
            return False

        self.seeking = self.SEEK_PLAYLIST
        self.player.playVideoPlaylist(self.playlist, handler=self)

        return True

    def onSeekAborted(self):
        if self.seeking:
            self.seeking = self.NO_SEEK
            self.player.control('play')

    def showOSD(self, from_seek=False):
        self.updateOffset()
        if self.dialog:
            self.dialog.update(self.offset, from_seek)
            self.dialog.showOSD()

    def hideOSD(self, delete=False):
        util.CRON.forceTick()
        if self.dialog:
            self.dialog.hideOSD()
            if delete:
                d = self.dialog
                self.dialog = None
                d.doClose()
                del d
                util.garbageCollect()

    def seek(self, offset, settings_changed=False, seeking=SEEK_IN_PROGRESS):
        if offset is None:
            return

        self.offset = offset

        if self.mode == self.MODE_ABSOLUTE and not settings_changed:
            util.DEBUG_LOG('New absolute player offset: {0}'.format(self.offset))

            if self.player.playerObject.offsetIsValid(offset / 1000):
                if self.seekAbsolute(offset):
                    return

        self.updateNowPlaying(state=self.player.STATE_PAUSED)  # To for update after seek

        self.seeking = self.SEEK_IN_PROGRESS

        if self.player.playState == self.player.STATE_PAUSED:
            self.player.pauseAfterPlaybackStarted = True

        util.DEBUG_LOG('New player offset: {0}'.format(self.offset))
        self.player._playVideo(offset, seeking=self.seeking, force_update=settings_changed)

    def fastforward(self):
        xbmc.executebuiltin('PlayerControl(forward)')

    def rewind(self):
        if self.mode == self.MODE_ABSOLUTE:
            xbmc.executebuiltin('PlayerControl(rewind)')
        else:
            self.seek(max(self.trueTime - 30, 0) * 1000, seeking=self.SEEK_REWIND)

    def seekAbsolute(self, seek=None):
        self.seekOnStart = seek or (self.seekOnStart if self.seekOnStart else None)
        if self.seekOnStart is not None:
            seekSeconds = self.seekOnStart / 1000.0
            try:
                if seekSeconds >= self.player.getTotalTime():
                    util.DEBUG_LOG("SeekAbsolute: Bad offset: {0}".format(seekSeconds))
                    return False
            except RuntimeError:  # Not playing a file
                util.DEBUG_LOG("SeekAbsolute: runtime error")
                return False
            self.updateNowPlaying(state=self.player.STATE_PAUSED)  # To for update after seek

            util.DEBUG_LOG("SeekAbsolute: Seeking to {0}".format(self.seekOnStart))
            self.player.seekTime(self.seekOnStart / 1000.0)
        return True

    def onPlayBackStarted(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackStarted - mode={0}'.format(self.mode))
        self.updateNowPlaying(force=True, refreshQueue=True)

        if self.dialog:
            self.dialog.onPlaybackStarted()

    def onPlayBackResumed(self):
        self.updateNowPlaying()
        if self.dialog:
            self.dialog.onPlaybackResumed()

            util.CRON.forceTick()
        # self.hideOSD()

    def onPlayBackStopped(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackStopped - Seeking={0}'.format(self.seeking))

        if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_REWIND):
            self.updateNowPlaying()

            # show post play if possible, if an item has been watched (90% by Plex standards)
            if self.trueTime * 1000 / float(self.duration) >= 0.90 and self.next(on_end=True):
                return

        if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_PLAYLIST):
            self.hideOSD(delete=True)
            self.sessionEnded()

    def onPlayBackEnded(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackEnded - Seeking={0}'.format(self.seeking))

        if self.player.playerObject.hasMoreParts():
            self.updateNowPlaying(state=self.player.STATE_PAUSED)  # To for update after seek
            self.seeking = self.SEEK_IN_PROGRESS
            self.player._playVideo(self.player.playerObject.getNextPartOffset(), seeking=self.seeking)
            return

        self.updateNowPlaying()

        if self.next(on_end=True):
            return

        if not self.ended:
            if self.seeking != self.SEEK_PLAYLIST:
                self.hideOSD()

            if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_PLAYLIST):
                self.sessionEnded()

    def onPlayBackPaused(self):
        self.updateNowPlaying()
        if self.dialog:
            self.dialog.onPlaybackPaused()

    def onPlayBackSeek(self, stime, offset):
        if self.seekOnStart:
            seeked = False
            if self.dialog:
                seeked = self.dialog.tick(stime)

            if seeked:
                util.DEBUG_LOG("OnPlayBackSeek: Seeked on start")
                self.seekOnStart = 0
            return

        self.updateOffset()
        # self.showOSD(from_seek=True)

    def setSubtitles(self):
        subs = self.player.video.selectedSubtitleStream(
            forced_subtitles_override=util.advancedSettings.forcedSubtitlesOverride)
        if subs:
            xbmc.sleep(100)
            self.player.showSubtitles(False)
            path = subs.getSubtitleServerPath()
            if path:
                if self.mode == self.MODE_ABSOLUTE:
                    util.DEBUG_LOG('Setting subtitle path: {0}'.format(path))
                    self.player.setSubtitles(path)
                    self.player.showSubtitles(True)
                else:
                    util.DEBUG_LOG('Transcoded. Skipping subtitle path: {0}'.format(path))
            else:
                # u_til.TEST(subs.__dict__)
                # u_til.TEST(self.player.video.mediaChoice.__dict__)
                if self.mode == self.MODE_ABSOLUTE:
                    util.DEBUG_LOG('Enabling embedded subtitles at: {0}'.format(subs.typeIndex))
                    util.DEBUG_LOG('Kodi reported subtitles: {0}'.format(self.player.getAvailableSubtitleStreams()))
                    self.player.setSubtitleStream(subs.typeIndex)
                    self.player.showSubtitles(True)
        else:
            self.player.showSubtitles(False)

    def setAudioTrack(self):
        if self.mode == self.MODE_ABSOLUTE:
            track = self.player.video.selectedAudioStream()
            if track:
                # only try finding the current audio stream when the BG music isn't playing and wasn't the last
                # thing played, because currentaudiostream doesn't populate for audio-only items; in that case,
                # always select the proper audio stream
                if not self.player.lastPlayWasBGM:
                    try:
                        playerID = kodijsonrpc.rpc.Player.GetActivePlayers()[0]["playerid"]
                        currIdx = kodijsonrpc.rpc.Player.GetProperties(playerid=playerID, properties=['currentaudiostream'])['currentaudiostream']['index']
                        if currIdx == track.typeIndex:
                            util.DEBUG_LOG('Audio track is correct index: {0}'.format(track.typeIndex))
                            return
                    except:
                        util.ERROR()

                self.player.lastPlayWasBGM = False

                xbmc.sleep(100)
                util.DEBUG_LOG('Switching audio track - index: {0}'.format(track.typeIndex))
                self.player.setAudioStream(track.typeIndex)

    def updateOffset(self):
        self.offset = int(self.player.getTime() * 1000)

    def initPlayback(self):
        self.seeking = self.NO_SEEK

        self.setSubtitles()
        self.setAudioTrack()

        if self.mode == self.MODE_ABSOLUTE:
            self.seekAbsolute()

    def onPlayBackFailed(self):
        if self.ended:
            return False

        util.DEBUG_LOG('SeekHandler: onPlayBackFailed - Seeking={0}'.format(self.seeking))
        if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_PLAYLIST):
            self.sessionEnded()

        if self.seeking == self.SEEK_IN_PROGRESS:
            return False
        else:
            self.seeking = self.NO_SEEK

        return True

    # def onSeekOSD(self):
    #     self.dialog.activate()

    def onVideoWindowOpened(self):
        self.getDialog().show()

        self.initPlayback()

    def onVideoWindowClosed(self):
        self.hideOSD()
        util.DEBUG_LOG('SeekHandler: onVideoWindowClosed - Seeking={0}'.format(self.seeking))
        if not self.seeking:
            self.player.stop()
            if not self.playlist or not self.playlist.hasNext():
                if not self.shouldShowPostPlay():
                    self.sessionEnded()

    def onVideoOSD(self):
        # xbmc.executebuiltin('Dialog.Close(seekbar,true)')  # Doesn't work :)
        self.showOSD()

    def tick(self):
        if self.seeking != self.SEEK_IN_PROGRESS:
            self.updateNowPlaying(force=True)

        if self.dialog:
            self.dialog.tick()

    def close(self):
        self.hideOSD(delete=True)

    def sessionEnded(self):
        if self.ended:
            return
        self.ended = True
        util.DEBUG_LOG('Player: Video session ended')
        self.player.trigger('session.ended', session_id=self.sessionID)
        self.hideOSD(delete=True)


class AudioPlayerHandler(BasePlayerHandler):
    def __init__(self, player):
        BasePlayerHandler.__init__(self, player)
        self.timelineType = 'music'
        util.setGlobalProperty('track.ID', '')
        self.extractTrackInfo()

    def extractTrackInfo(self):
        if not self.player.isPlayingAudio():
            return

        plexID = None
        for x in range(10):  # Wait a sec (if necessary) for this to become available
            try:
                item = kodijsonrpc.rpc.Player.GetItem(playerid=0, properties=['comment'])['item']
                plexID = item['comment']
            except:
                util.ERROR()

            if plexID:
                break
            xbmc.sleep(100)

        if not plexID:
            return

        if not plexID.startswith('PLEX-'):
            return

        util.DEBUG_LOG('Extracting track info from comment')
        try:
            data = plexID.split(':', 1)[-1]
            from plexnet import plexobjects
            track = plexobjects.PlexObject.deSerialize(base64.urlsafe_b64decode(data[1:].encode('utf-8')))
            track.softReload()
            self.media = track
            pobj = plexplayer.PlexAudioPlayer(track)
            self.player.playerObject = pobj
            self.updatePlayQueueTrack(track)
            util.setGlobalProperty('track.ID', track.ratingKey)  # This is used in the skins to match a listitem
        except:
            util.ERROR()

    def setPlayQueue(self, pq):
        self.playQueue = pq
        pq.on('items.changed', self.playQueueCallback)

    def playQueueCallback(self, **kwargs):
        plist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        # plist.clear()
        try:
            citem = kodijsonrpc.rpc.Player.GetItem(playerid=0, properties=['comment'])['item']
            plexID = citem['comment'].split(':', 1)[0]
        except:
            util.ERROR()
            return

        current = plist.getposition()
        size = plist.size()

        # Remove everything but the current track
        for x in range(size - 1, current, -1):  # First everything with a greater position
            kodijsonrpc.rpc.Playlist.Remove(playlistid=xbmc.PLAYLIST_MUSIC, position=x)
        for x in range(current):  # Then anything with a lesser position
            kodijsonrpc.rpc.Playlist.Remove(playlistid=xbmc.PLAYLIST_MUSIC, position=0)

        swap = None
        for idx, track in enumerate(self.playQueue.items()):
            tid = 'PLEX-{0}'.format(track.ratingKey)
            if tid == plexID:
                # Save the position of the current track in the pq
                swap = idx

            url, li = self.player.createTrackListItem(track, index=idx + 1)

            plist.add(url, li)

        plist[0].setInfo('music', {
            'playcount': swap + 1,
        })

        # Now swap the track to the correct position. This seems to be the only way to update the kodi playlist position to the current track's new position
        if swap is not None:
            kodijsonrpc.rpc.Playlist.Swap(playlistid=xbmc.PLAYLIST_MUSIC, position1=0, position2=swap + 1)
            kodijsonrpc.rpc.Playlist.Remove(playlistid=xbmc.PLAYLIST_MUSIC, position=0)

        self.player.trigger('playlist.changed')

    def updatePlayQueue(self, delay=False):
        if not self.playQueue:
            return

        self.playQueue.refresh(delay=delay)

    def updatePlayQueueTrack(self, track):
        if not self.playQueue:
            return

        self.playQueue.selectedId = track.playQueueItemID or None

    @property
    def trueTime(self):
        try:
            return self.player.getTime()
        except:
            return self.player.currentTime

    def stampCurrentTime(self):
        try:
            self.player.currentTime = self.player.getTime()
        except RuntimeError:  # Not playing
            pass

    def onMonitorInit(self):
        self.extractTrackInfo()
        self.updateNowPlaying(state='playing')

    def onPlayBackStarted(self):
        self.player.lastPlayWasBGM = False
        self.updatePlayQueue(delay=True)
        self.extractTrackInfo()
        self.updateNowPlaying(state='playing')

    def onPlayBackResumed(self):
        self.updateNowPlaying(state='playing')

    def onPlayBackPaused(self):
        self.updateNowPlaying(state='paused')

    def onPlayBackStopped(self):
        self.updatePlayQueue()
        self.updateNowPlaying(state='stopped')
        self.finish()

    def onPlayBackEnded(self):
        self.updatePlayQueue()
        self.updateNowPlaying(state='stopped')
        self.finish()

    def onPlayBackFailed(self):
        return True

    def finish(self):
        self.player.trigger('session.ended')
        util.setGlobalProperty('track.ID', '')

    def tick(self):
        self.stampCurrentTime()
        self.updateNowPlaying(force=True)


class BGMPlayerHandler(BasePlayerHandler):
    def __init__(self, player, rating_key):
        BasePlayerHandler.__init__(self, player)
        self.timelineType = 'music'
        self.currentlyPlaying = rating_key
        util.setGlobalProperty('track.ID', '')
        util.setGlobalProperty('theme_playing', '1')

        self.oldVolume = util.rpc.Application.GetProperties(properties=["volume"])["volume"]

    def onPlayBackStarted(self):
        util.DEBUG_LOG("BGM: playing theme for %s" % self.currentlyPlaying)
        self.player.bgmPlaying = True

    def setVolume(self, volume=None, reset=False):
        vlm = self.oldVolume if reset else volume
        util.DEBUG_LOG("BGM: %ssetting volume to: %s" % ("re-" if reset else "", vlm))
        xbmc.executebuiltin("SetVolume(%s)" % vlm)

    def resetVolume(self):
        self.setVolume(reset=True)

    def onPlayBackStopped(self):
        util.DEBUG_LOG("BGM: stopped theme for %s" % self.currentlyPlaying)
        util.setGlobalProperty('theme_playing', '')
        self.player.bgmPlaying = False
        self.resetVolume()

    def onPlayBackEnded(self):
        self.onPlayBackStopped()

    def onPlayBackFailed(self):
        self.onPlayBackStopped()

    def close(self):
        self.player.stopAndWait()
        self.onPlayBackStopped()


class BGMPlayerTask(backgroundthread.Task):
    def setup(self, source, player, *args, **kwargs):
        self.source = source
        self.player = player
        return self

    def cancel(self):
        self.player.stopAndWait()
        self.player = None
        backgroundthread.Task.cancel(self)

    def run(self):
        if self.isCanceled():
            return

        self.player.play(self.source, windowed=True)


class PlexPlayer(xbmc.Player, signalsmixin.SignalsMixin):
    STATE_STOPPED = "stopped"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_BUFFERING = "buffering"

    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        signalsmixin.SignalsMixin.__init__(self)

    def init(self):
        self._closed = False
        self._nextItem = None
        self.started = False
        self.bgmPlaying = False
        self.lastPlayWasBGM = False
        self.BGMTask = None
        self.pauseAfterPlaybackStarted = False
        self.video = None
        self.hasOSD = False
        self.hasSeekOSD = False
        self.handler = AudioPlayerHandler(self)
        self.playerObject = None
        self.currentTime = 0
        self.thread = None
        if xbmc.getCondVisibility('Player.HasMedia'):
            self.started = True
        self.open()

        return self

    def open(self):
        self._closed = False
        self.monitor()

    def close(self, shutdown=False):
        self._closed = True

    def reset(self):
        self.video = None
        self.started = False
        self.bgmPlaying = False
        self.playerObject = None
        self.pauseAfterPlaybackStarted = False
        self.handler = AudioPlayerHandler(self)
        self.currentTime = 0

    def control(self, cmd):
        if cmd == 'play':
            self.pauseAfterPlaybackStarted = False
            util.DEBUG_LOG('Player - Control:  Command=Play')
            if xbmc.getCondVisibility('Player.Paused | !Player.Playing'):
                util.DEBUG_LOG('Player - Control:  Playing')
                xbmc.executebuiltin('PlayerControl(Play)')
        elif cmd == 'pause':
            util.DEBUG_LOG('Player - Control:  Command=Pause')
            if not xbmc.getCondVisibility('Player.Paused'):
                util.DEBUG_LOG('Player - Control:  Pausing')
                xbmc.executebuiltin('PlayerControl(Play)')

    @property
    def playState(self):
        if xbmc.getCondVisibility('Player.Playing'):
            return self.STATE_PLAYING
        elif xbmc.getCondVisibility('Player.Caching'):
            return self.STATE_BUFFERING
        elif xbmc.getCondVisibility('Player.Paused'):
            return self.STATE_PAUSED

        return self.STATE_STOPPED

    def videoIsFullscreen(self):
        return xbmc.getCondVisibility('VideoPlayer.IsFullscreen')

    def currentTrack(self):
        if self.handler.media and self.handler.media.type == 'track':
            return self.handler.media
        return None

    def playAt(self, path, ms):
        """
        Plays the video specified by path.
        Optionally set the start position with h,m,s,ms keyword args.
        """
        seconds = ms / 1000.0

        h = int(seconds / 3600)
        m = int((seconds % 3600) / 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)

        kodijsonrpc.rpc.Player.Open(
            item={'file': path},
            options={'resume': {'hours': h, 'minutes': m, 'seconds': s, 'milliseconds': ms}}
        )

    def play(self, *args, **kwargs):
        self.started = False
        xbmc.Player.play(self, *args, **kwargs)

    def playBackgroundMusic(self, source, volume, rating_key, *args, **kwargs):
        if self.isPlaying():
            if not self.lastPlayWasBGM:
                return

            else:
                # don't re-queue the currently playing theme
                if self.handler.currentlyPlaying == rating_key:
                    return

                # cancel any currently playing theme before starting the new one
                else:
                    self.stopAndWait()

        if self.BGMTask and self.BGMTask.isValid():
            self.BGMTask.cancel()

        self.started = False
        self.handler = BGMPlayerHandler(self, rating_key)

        self.lastPlayWasBGM = True

        self.handler.setVolume(volume)

        self.BGMTask = BGMPlayerTask().setup(source, self, *args, **kwargs)
        backgroundthread.BGThreader.addTask(self.BGMTask)

    def playVideo(self, video, resume=False, force_update=False, session_id=None, handler=None):
        if self.bgmPlaying:
            self.stopAndWait()

        self.handler = handler or SeekPlayerHandler(self, session_id)
        self.video = video
        self.open()
        self._playVideo(resume and video.viewOffset.asInt() or 0, force_update=force_update)

    def _playVideo(self, offset=0, seeking=0, force_update=False, playerObject=None):
        self.trigger('new.video', video=self.video)
        self.trigger(
            'change.background',
            url=self.video.defaultArt.asTranscodedImageURL(1920, 1080, opacity=60, background=colors.noAlpha.Background)
        )
        try:
            if not playerObject:
                self.playerObject = plexplayer.PlexPlayer(self.video, offset, forceUpdate=force_update)
                self.playerObject.build()
            self.playerObject = self.playerObject.getServerDecision()
        except plexplayer.DecisionFailure as e:
            util.showNotification(e.reason, header=util.T(32448, 'Playback Failed!'))
            return
        except:
            util.ERROR(notify=True)
            return

        meta = self.playerObject.metadata

        # Kodi 19 will try to look for subtitles in the directory containing the file. '/' and `/file.mkv` both point
        # to the file, and Kodi will happily try to read the whole file without recognizing it isn't a directory.
        # To get around that, we omit the filename here since it is unnecessary.
        url = meta.streamUrls[0].replace("file.mkv", "")

        bifURL = self.playerObject.getBifUrl()
        util.DEBUG_LOG('Playing URL(+{1}ms): {0}{2}'.format(plexnetUtil.cleanToken(url), offset, bifURL and ' - indexed' or ''))

        self.stopAndWait()  # Stop before setting up the handler to prevent player events from causing havoc

        self.handler.setup(self.video.duration.asInt(), offset, bifURL, title=self.video.grandparentTitle, title2=self.video.title, seeking=seeking, chapters=self.video.chapters)

        if meta.isTranscoded:
            self.handler.mode = self.handler.MODE_RELATIVE
        else:
            if offset:
                self.handler.seekOnStart = meta.playStart * 1000
            self.handler.mode = self.handler.MODE_ABSOLUTE

        url = util.addURLParams(url, {
            'X-Plex-Client-Profile-Name': 'Chrome',
            'X-Plex-Client-Identifier': plexapp.util.INTERFACE.getGlobal('clientIdentifier')
        })
        li = xbmcgui.ListItem(self.video.title, path=url)
        vtype = self.video.type if self.video.type in ('movie', 'episode', 'musicvideo') else 'video'
        li.setInfo('video', {
            'mediatype': vtype,
            'title': self.video.title,
            'originaltitle': self.video.title,
            'tvshowtitle': self.video.grandparentTitle,
            'episode': self.video.index.asInt(),
            'season': self.video.parentIndex.asInt(),
            'year': self.video.year.asInt(),
            'plot': self.video.summary
        })
        li.setArt({
            'poster': self.video.defaultThumb.asTranscodedImageURL(347, 518),
            'fanart': self.video.defaultArt.asTranscodedImageURL(1920, 1080),
            'thumb': self.video.defaultThumb.asTranscodedImageURL(256, 256),
        })

        self.play(url, li)

    def playVideoPlaylist(self, playlist, resume=True, handler=None, session_id=None):
        if self.bgmPlaying:
            self.stopAndWait()

        if handler:
            self.handler = handler
        else:
            self.handler = SeekPlayerHandler(self, session_id)

        self.handler.playlist = playlist
        if playlist.isRemote:
            self.handler.playQueue = playlist
        self.video = playlist.current()
        self.video.softReload()
        self.open()
        self._playVideo(resume and self.video.viewOffset.asInt() or 0, seeking=handler and handler.SEEK_PLAYLIST or 0, force_update=True)

    # def createVideoListItem(self, video, index=0):
    #     url = 'plugin://script.plex/play?{0}'.format(base64.urlsafe_b64encode(video.serialize()))
    #     li = xbmcgui.ListItem(self.video.title, path=url, thumbnailImage=self.video.defaultThumb.asTranscodedImageURL(256, 256))
    #     vtype = self.video.type if self.video.vtype in ('movie', 'episode', 'musicvideo') else 'video'
    #     li.setInfo('video', {
    #         'mediatype': vtype,
    #         'playcount': index,
    #         'title': video.title,
    #         'tvshowtitle': video.grandparentTitle,
    #         'episode': video.index.asInt(),
    #         'season': video.parentIndex.asInt(),
    #         'year': video.year.asInt(),
    #         'plot': video.summary
    #     })
    #     li.setArt({
    #         'poster': self.video.defaultThumb.asTranscodedImageURL(347, 518),
    #         'fanart': self.video.defaultArt.asTranscodedImageURL(1920, 1080),
    #     })

    #     return url, li

    def playAudio(self, track, fanart=None):
        if self.bgmPlaying:
            self.stopAndWait()

        self.handler = AudioPlayerHandler(self)
        url, li = self.createTrackListItem(track, fanart)
        self.stopAndWait()
        self.play(url, li)

    def playAlbum(self, album, startpos=-1, fanart=None):
        if self.bgmPlaying:
            self.stopAndWait()

        self.handler = AudioPlayerHandler(self)
        plist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        plist.clear()
        index = 1
        for track in album.tracks():
            url, li = self.createTrackListItem(track, fanart, index=index)
            plist.add(url, li)
            index += 1
        xbmc.executebuiltin('PlayerControl(RandomOff)')
        self.stopAndWait()
        self.play(plist, startpos=startpos)

    def playAudioPlaylist(self, playlist, startpos=-1, fanart=None):
        if self.bgmPlaying:
            self.stopAndWait()

        self.handler = AudioPlayerHandler(self)
        plist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        plist.clear()
        index = 1
        for track in playlist.items():
            url, li = self.createTrackListItem(track, fanart, index=index)
            plist.add(url, li)
            index += 1

        if playlist.isRemote:
            self.handler.setPlayQueue(playlist)
        else:
            if playlist.startShuffled:
                plist.shuffle()
                xbmc.executebuiltin('PlayerControl(RandomOn)')
            else:
                xbmc.executebuiltin('PlayerControl(RandomOff)')
        self.stopAndWait()
        self.play(plist, startpos=startpos)

    def createTrackListItem(self, track, fanart=None, index=0):
        data = base64.urlsafe_b64encode(track.serialize().encode("utf8")).decode("utf8")
        url = 'plugin://script.plexmod/play?{0}'.format(data)
        li = xbmcgui.ListItem(track.title, path=url)
        li.setInfo('music', {
            'artist': six.text_type(track.originalTitle or track.grandparentTitle),
            'title': six.text_type(track.title),
            'album': six.text_type(track.parentTitle),
            'discnumber': track.parentIndex.asInt(),
            'tracknumber': track.get('index').asInt(),
            'duration': int(track.duration.asInt() / 1000),
            'playcount': index,
            'comment': 'PLEX-{0}:{1}'.format(track.ratingKey, data)
        })
        art = fanart or track.defaultArt
        li.setArt({
            'fanart': art.asTranscodedImageURL(1920, 1080),
            'landscape': util.backgroundFromArt(art),
            'thumb': track.defaultThumb.asTranscodedImageURL(800, 800),
        })
        if fanart:
            li.setArt({'fanart': fanart})
        return (url, li)

    def onPrePlayStarted(self):
        util.DEBUG_LOG('Player - PRE-PLAY')
        self.trigger('preplay.started')
        if not self.handler:
            return
        self.handler.onPrePlayStarted()

    def onPlayBackStarted(self):
        self.started = True
        if self.pauseAfterPlaybackStarted:
            self.control('pause')
            self.pauseAfterPlaybackStarted = False

        util.DEBUG_LOG('Player - STARTED')
        self.trigger('playback.started')
        if not self.handler:
            return
        self.handler.onPlayBackStarted()

    def onPlayBackPaused(self):
        util.DEBUG_LOG('Player - PAUSED')
        if not self.handler:
            return
        self.handler.onPlayBackPaused()

    def onPlayBackResumed(self):
        util.DEBUG_LOG('Player - RESUMED')
        if not self.handler:
            return

        self.handler.onPlayBackResumed()

    def onPlayBackStopped(self):
        if not self.started:
            self.onPlayBackFailed()

        util.DEBUG_LOG('Player - STOPPED' + (not self.started and ': FAILED' or ''))
        if not self.handler:
            return
        self.handler.onPlayBackStopped()

    def onPlayBackEnded(self):
        if not self.started:
            self.onPlayBackFailed()

        util.DEBUG_LOG('Player - ENDED' + (not self.started and ': FAILED' or ''))
        if not self.handler:
            return
        self.handler.onPlayBackEnded()

    def onPlayBackSeek(self, time, offset):
        util.DEBUG_LOG('Player - SEEK: %i' % offset)
        if not self.handler:
            return
        self.handler.onPlayBackSeek(time, offset)

    def onPlayBackFailed(self):
        util.DEBUG_LOG('Player - FAILED')
        if not self.handler:
            return

        if self.handler.onPlayBackFailed():
            util.showNotification(util.T(32448, 'Playback Failed!'))
            # xbmcgui.Dialog().ok('Failed', 'Playback failed')

    def onVideoWindowOpened(self):
        util.DEBUG_LOG('Player: Video window opened')
        try:
            self.handler.onVideoWindowOpened()
        except:
            util.ERROR()

    def onVideoWindowClosed(self):
        util.DEBUG_LOG('Player: Video window closed')
        try:
            self.handler.onVideoWindowClosed()
            # self.stop()
        except:
            util.ERROR()

    def onVideoOSD(self):
        util.DEBUG_LOG('Player: Video OSD opened')
        try:
            self.handler.onVideoOSD()
        except:
            util.ERROR()

    def onSeekOSD(self):
        util.DEBUG_LOG('Player: Seek OSD opened')
        try:
            self.handler.onSeekOSD()
        except:
            util.ERROR()

    def stopAndWait(self):
        if self.isPlaying():
            util.DEBUG_LOG('Player: Stopping and waiting...')
            self.stop()
            while not util.MONITOR.waitForAbort(0.1) and self.isPlaying():
                pass
            util.MONITOR.waitForAbort(0.2)
            util.DEBUG_LOG('Player: Stopping and waiting...Done')

    def monitor(self):
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._monitor, name='PLAYER:MONITOR')
            self.thread.start()

    def _monitor(self):
        try:
            while not util.MONITOR.abortRequested() and not self._closed:
                if not self.isPlaying():
                    util.DEBUG_LOG('Player: Idling...')

                while not self.isPlaying() and not util.MONITOR.abortRequested() and not self._closed:
                    util.MONITOR.waitForAbort(0.1)

                if self.isPlayingVideo():
                    util.DEBUG_LOG('Monitoring video...')
                    self._videoMonitor()
                elif self.isPlayingAudio():
                    util.DEBUG_LOG('Monitoring audio...')
                    self._audioMonitor()
                elif self.isPlaying():
                    util.DEBUG_LOG('Monitoring pre-play...')
                    self._preplayMonitor()

            self.handler.close()
            self.close()
            util.DEBUG_LOG('Player: Closed')
        finally:
            self.trigger('session.ended')

    def _preplayMonitor(self):
        self.onPrePlayStarted()
        while self.isPlaying() and not self.isPlayingVideo() and not self.isPlayingAudio() and not util.MONITOR.abortRequested() and not self._closed:
            util.MONITOR.waitForAbort(0.1)

        if not self.isPlayingVideo() and not self.isPlayingAudio():
            self.onPlayBackFailed()

    def _videoMonitor(self):
        hasFullScreened = False

        ct = 0
        while self.isPlayingVideo() and not util.MONITOR.abortRequested() and not self._closed:
            self.currentTime = self.getTime()
            util.MONITOR.waitForAbort(0.1)
            if xbmc.getCondVisibility('Window.IsActive(videoosd)'):
                if not self.hasOSD:
                    self.hasOSD = True
                    self.onVideoOSD()
            else:
                self.hasOSD = False

            if xbmc.getCondVisibility('Window.IsActive(seekbar)'):
                if not self.hasSeekOSD:
                    self.hasSeekOSD = True
                    self.onSeekOSD()
            else:
                self.hasSeekOSD = False

            if xbmc.getCondVisibility('VideoPlayer.IsFullscreen'):
                if not hasFullScreened:
                    hasFullScreened = True
                    self.onVideoWindowOpened()
            elif hasFullScreened and not xbmc.getCondVisibility('Window.IsVisible(busydialog)'):
                hasFullScreened = False
                self.onVideoWindowClosed()

            ct += 1
            if ct > 9:
                ct = 0
                self.handler.tick()

        if hasFullScreened:
            self.onVideoWindowClosed()

    def _audioMonitor(self):
        self.started = True
        self.handler.onMonitorInit()
        ct = 0
        while self.isPlayingAudio() and not util.MONITOR.abortRequested() and not self._closed:
            self.currentTime = self.getTime()
            util.MONITOR.waitForAbort(0.1)

            ct += 1
            if ct > 9:
                ct = 0
                self.handler.tick()


def shutdown():
    global PLAYER
    PLAYER.close(shutdown=True)
    del PLAYER


PLAYER = PlexPlayer().init()
