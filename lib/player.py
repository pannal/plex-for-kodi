from __future__ import absolute_import
import base64
import json
import threading
import six
import re
import os
import random

from kodi_six import xbmc
from kodi_six import xbmcgui
from iso639 import languages
from . import backgroundthread
from . import kodijsonrpc
from . import colors
from .windows import seekdialog, windowutils
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
        self._lastDuration = 0
        self._progressHld = {}
        self.timelineType = None
        self.ignoreTimelines = False
        self.queuingNext = False
        self.queuingSpecific = False
        self.playQueue = None
        self.sessionID = session_id
        self.isMapped = False
        self.currentlyPlaying = None

    def onAVChange(self):
        pass

    def onAVStarted(self):
        pass

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

    def setSubtitles(self, *args, **kwargs):
        pass

    def getIntroOffset(self, offset=None, setSkipped=False):
        pass

    def setup(self, duration, meta, offset, bif_url, **kwargs):
        pass

    def reset(self):
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
        if self.player.playerObject and self.player.isPlaying():
            try:
                self._lastDuration = int(self.player.getTotalTime() * 1000)
                return self._lastDuration
            except RuntimeError:
                pass

        return self._lastDuration

    def updateNowPlaying(self, refreshQueue=False, t=None, state=None, overrideChecks=False):
        if self.ignoreTimelines:
            util.DEBUG_LOG("UpdateNowPlaying: ignoring timeline as requested")
            return

        item = self.getCurrentItem()
        if not item:
            return

        if not self.shouldSendTimeline(item):
            return

        util.DEBUG_LOG("UpdateNowPlaying: {0}, refreshQueue: {1} state: {2} (player: {5}) "
                       "overrideChecks: {3} time: {4} (player: {6})"
                       .format(item.ratingKey,
                               refreshQueue,
                               state,
                               overrideChecks,
                               t,
                               self.player.playState,
                               self.player.getTime() if self.player.isPlayingVideo() else "N/A"))

        state = state or self.player.playState

        obj = item.choice

        # Ignore sending timelines for multi-part media with no duration
        if obj and obj.part and obj.part.duration.asInt() == 0 and obj.media.parts and len(obj.media.parts) > 1:
            util.LOG("Timeline not supported: the current part doesn't have a valid duration")
            return

        # if we've been called explicitly with a time, honor
        force_time = t is not None
        _time = t or int(self.trueTime * 1000)

        # self.trigger("progress", [m, item, time])

        if refreshQueue and self.playQueue:
            self.playQueue.refreshOnTimeline = True

        data = plexnetUtil.AttributeDict({
            "key": str(item.key),
            "ratingKey": str(item.ratingKey),
            "guid": str(item.guid),
            "url": str(item.url),
            "duration": item.duration.asInt(),
            "containerKey": str(item.container.address)
        })

        new_time_stored = plexapp.util.APP.nowplayingmanager.updatePlaybackState(
            self.timelineType, data, state, _time, self.playQueue, duration=self.currentDuration(),
            force=overrideChecks, force_time=force_time, server=item.server
        )

        if new_time_stored:
            # only update our immediate progress if we should (e.g. if updatePlaybackState reported a new time based
            # on _time
            self._progressHld[str(item.ratingKey)] = _time

    def getVolume(self):
        return util.rpc.Application.GetProperties(properties=["volume"])["volume"]

    def sessionEnded(self):
        self.player.sessionID = None

    def prev(self):
        return

    def next(self):
        return

    def playAt(self, pos):
        return

    def hideOSD(self, **kwargs):
        return


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
        self.seekOnStart = 0
        self.waitingForSOS = False
        self.chapters = None
        self.stoppedManually = False
        self.endedManually = False
        self.inBingeMode = False
        self.skipPostPlay = False
        self.prePlayWitnessed = False
        self.queuingNext = False
        self.queuingSpecific = False
        self.useAlternateSeek = util.getSetting('use_alternate_seek2')
        self.useResumeFix = self.useAlternateSeek
        self.isMapped = False
        self.reset()

    def reset(self):
        self.duration = 0
        self.offset = 0
        self.baseOffset = 0
        self.seeking = self.NO_SEEK
        self.seekOnStart = 0
        self.waitingForSOS = False
        self._lastDuration = 0
        self._progressHld = {}
        self._subtitleStreamOffset = None
        self.mode = self.MODE_RELATIVE
        self.ended = False
        self.endedManually = False
        self.stoppedManually = False
        self.prePlayWitnessed = False
        self.queuingNext = False
        self.queuingSpecific = False
        self.isMapped = False
        self.creditMarkerHit = None

    def setup(self, duration, meta, offset, bif_url, title='', title2='', seeking=NO_SEEK, chapters=None,
              is_mapped=False):
        self.ended = False
        self.baseOffset = offset / 1000.0
        self.seeking = seeking
        self.duration = duration
        self._lastDuration = duration
        self._progressHld = {}
        self.bifURL = bif_url
        self.title = title
        self.title2 = title2
        self.chapters = chapters or []
        self.playedThreshold = plexapp.util.INTERFACE.getPlayedThresholdValue() # percentage
        self.stoppedManually = False
        self.inBingeMode = False
        self.skipPostPlay = False
        self.prePlayWitnessed = False
        self._subtitleStreamOffset = None
        self.isMapped = is_mapped
        self.getDialog(setup=True)
        self.dialog.setup(self.duration, meta, int(self.baseOffset * 1000), self.bifURL, self.title, self.title2,
                          chapters=self.chapters, keepMarkerDef=seeking == self.SEEK_IN_PROGRESS)

    def getDialog(self, setup=False):
        if not self.dialog:
            self.dialog = seekdialog.SeekDialog.create(show=False, handler=self)

        return self.dialog

    @property
    def isTranscoded(self):
        return self.mode == self.MODE_RELATIVE

    @property
    def isDirectPlay(self):
        return self.mode == self.MODE_ABSOLUTE

    @property
    def trueTime(self):
        if self.isTranscoded:
            return self.baseOffset + self.player.currentTime
        else:
            if not self.player.playerObject:
                return 0
            if self.seekOnStart:
                return self.player.playerObject.startOffset + (self.seekOnStart / 1000)
            else:
                return self.player.currentTime + self.player.playerObject.startOffset

    def shouldShowPostPlay(self):
        if util.getUserSetting('post_play_never', False):
            return False

        if self.player.video and self.player.video.isExtra:
            return False

        if self.playlist and self.playlist.TYPE == 'playlist':
            return False

        if not (self.stoppedManually or self.endedManually) and self.skipPostPlay:
            return False

        if (not util.addonSettings.postplayAlways and self._lastDuration <= FIVE_MINUTES_MILLIS)\
                or util.addonSettings.postplayTimeout <= 0:
            return False

        return True

    def showPostPlay(self):
        if not self.shouldShowPostPlay():
            util.DEBUG_LOG("SeekHandler: Not showing post-play")
            return
        util.DEBUG_LOG("SeekHandler: Showing post-play")

        self.seeking = self.SEEK_POST_PLAY
        self.hideOSD(delete=True)

        self.player.trigger('post.play', video=self.player.video, playlist=self.playlist, handler=self,
                            stoppedManually=self.stoppedManually)

        self.stoppedManually = False

        return True

    def getIntroOffset(self, offset=None, setSkipped=False):
        return self.getDialog().displayMarkers(onlyReturnIntroMD=True, offset=offset, setSkipped=setSkipped)

    def next(self, on_end=False):
        hasNext = False
        if self.playlist:
            hasNext = bool(next(self.playlist))
            if hasNext:
                self.seeking = self.SEEK_PLAYLIST

        self.triggerProgressEvent()

        if on_end:
            if self.showPostPlay():
                return True

        if not self.playlist or self.stoppedManually or self.endedManually or (self.playlist and not hasNext):
            return False

        self.player.playVideoPlaylist(self.playlist, handler=self, resume=False)

        return True

    def prev(self):
        if not self.playlist or not self.playlist.prev():
            return False

        self.triggerProgressEvent()
        self.seeking = self.SEEK_PLAYLIST
        self.player.playVideoPlaylist(self.playlist, handler=self, resume=False)

        return True

    def playAt(self, pos):
        if not self.playlist or not self.playlist.setCurrent(pos):
            return False

        self.triggerProgressEvent()
        self.seeking = self.SEEK_PLAYLIST
        self.dialog.prepareNewPlayback(queuing_specific=True, ignore_tick=True, ignore_input=True)
        self.player.playVideoPlaylist(self.playlist, handler=self, resume=False)

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
            self.dialog.hideOSD(closing=delete, skipMarkerFocus=True)
            if delete:
                d = self.dialog
                self.dialog = None
                d.doClose(delete=delete)
                del d
                util.garbageCollect()

    def seek(self, offset, settings_changed=False, seeking=SEEK_IN_PROGRESS):
        util.DEBUG_LOG(
            "SeekHandler: offset={0}, settings_changed={1}, seeking={2}, state={3}".format(offset,
                                                                                           settings_changed,
                                                                                           seeking,
                                                                                           self.player.playState))
        if offset is None:
            return

        self.offset = offset

        if self.isDirectPlay and not settings_changed:
            util.DEBUG_LOG('New absolute player offset: {0}', self.offset)

            if self.player.playerObject.offsetIsValid(offset / 1000) and not self.player.isExternal:
                if self.seekAbsolute(offset):
                    return

        self.seeking = self.SEEK_IN_PROGRESS

        if self.player.playState == self.player.STATE_PAUSED:
            self.player.pauseAfterPlaybackStarted = True

        util.DEBUG_LOG('New player offset: {0}, state: {1}', self.offset, self.player.playState)
        self.player._playVideo(offset, seeking=self.seeking, force_update=settings_changed)

    def fastforward(self):
        xbmc.executebuiltin('PlayerControl(forward)')

    def rewind(self):
        if self.isDirectPlay:
            xbmc.executebuiltin('PlayerControl(rewind)')
        else:
            self.seek(max(self.trueTime - 30, 0) * 1000, seeking=self.SEEK_REWIND)

    def seekAbsolute(self, seek=None):
        self.seekOnStart = seek or (self.seekOnStart if self.seekOnStart else None)

        if self.player.isExternal:
            return True

        if self.seekOnStart is not None:
            seekSeconds = self.seekOnStart / 1000.0
            try:
                if seekSeconds >= self.player.getTotalTime():
                    util.DEBUG_LOG("SeekAbsolute: Bad offset: {0}", seekSeconds)
                    return False
            except RuntimeError:  # Not playing a file
                util.DEBUG_LOG("SeekAbsolute: runtime error")
                return False

            # Some devices seem to have an issue with the self.player.seekTime function where after the seek the video
            # will be playing, but the audio won't for a few seconds(I've seen up to 15 seconds).  Using this alternate
            # way to seek avoids that issue.

            # we only apply the fix for a significant seek, otherwise the event might not fire, and we end up with
            # an unconsumed self.seekOnStart, which leads to never sending timeline events
            if self.useAlternateSeek and seekSeconds > 0.5:
                currentTime = self.player.getTime()
                relativeSeekSeconds = seekSeconds - currentTime
                util.DEBUG_LOG("SeekAbsolute: Seeking to offset: {0}, current time: {1}, relative seek: {2}".format(
                    seekSeconds, currentTime, relativeSeekSeconds))
                xbmc.executebuiltin('Seek({})'.format(relativeSeekSeconds))
            else:
                util.DEBUG_LOG("SeekAbsolute: Seeking to {0}", self.seekOnStart)
                self.player.seekTime(seekSeconds)
        return True

    def onAVChange(self):
        util.DEBUG_LOG('SeekHandler: onAVChange')
        self.player.trigger('changed.video')
        if self.dialog:
            self.dialog.onAVChange()

    def onAVStarted(self):
        util.DEBUG_LOG('SeekHandler: onAVStarted')
        self.player.trigger('started.video')

        if self.isDirectPlay:
            # handle seekOnStart/resume
            self.seekAbsolute()

        if self.dialog:
            self.dialog.onAVStarted()

        self.ignoreTimelines = False

        # check if embedded subtitle was set correctly
        if self.isDirectPlay and self.player.video and self.player.video.current_subtitle_is_embedded:
            got_player = False
            tries = 0
            while not got_player and tries < 50:
                try:
                    playerID = kodijsonrpc.rpc.Player.GetActivePlayers()[0]["playerid"]
                    got_player = True
                    currIdx = kodijsonrpc.rpc.Player.GetProperties(playerid=playerID, properties=['currentsubtitle'])[
                        'currentsubtitle']['index']
                    if currIdx != self.player.video._current_subtitle_idx + self.subtitleStreamOffset:
                        util.LOG("Embedded Subtitle index was incorrect ({}), setting to: {}".
                                 format(currIdx, self.player.video._current_subtitle_idx + self.subtitleStreamOffset))
                        self.dialog.setSubtitles()
                    else:
                        util.DEBUG_LOG("Embedded subtitle was correctly set in Kodi")
                except IndexError:
                    util.DEBUG_LOG("Player not available yet, retrying ({}/{})".format(tries, 50))
                    tries += 1
                    util.MONITOR.waitForAbort(0.1)
                except:
                    util.ERROR("Exception when trying to check for embedded subtitles")
                    break

    def onPrePlayStarted(self):
        util.DEBUG_LOG('SeekHandler: onPrePlayStarted, DP: {}', self.isDirectPlay)
        self.prePlayWitnessed = True
        if self.isDirectPlay:
            self.setSubtitles(do_sleep=False)

    def onPlayBackStarted(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackStarted, DP: {}', self.isDirectPlay)

        self.updateNowPlaying(refreshQueue=True)

        if self.dialog:
            self.dialog.onPlayBackStarted()

        #if not self.prePlayWitnessed and self.isDirectPlay:
        if self.isDirectPlay:
            self.setSubtitles(do_sleep=False)

    def onPlayBackResumed(self):
        self.updateNowPlaying()
        if self.dialog:
            self.dialog.onPlayBackResumed()

            util.CRON.forceTick()
        # self.hideOSD()

    def getVideoPlayedFac(self, ref=None):
        return (ref if ref is not None else self.trueTime * 1000) / float(self.duration)

    @property
    def videoPlayedFac(self):
        return self.getVideoPlayedFac()

    @property
    def playedThresholdPerc(self):
        server_thres = self.player.video.server.prefs.get("LibraryVideoPlayedThreshold", None)
        if server_thres is None:
            return int(self.playedThreshold)
        return int(server_thres)

    def getVideoWatched(self, ref=None):
        """
        0:at selected threshold percentage|1:at final credits marker position|2:at first credits marker position|3:earliest between threshold percent and first credits marker
        :param ref:
        :return: bool
        """
        playedAtBH = self.player.video.server.prefs.get("LibraryVideoPlayedAtBehaviour", None)
        if playedAtBH is None:
            playedAtBH = util.getSetting("played_threshold_behaviour")
        playedAtBH = int(playedAtBH)

        watchedByPerc = self.getVideoPlayedFac(ref=ref) >= self.playedThresholdPerc / 100.0 or self.player.isExternal

        if playedAtBH == 0 or not self.player.video.has_credit_markers:
            util.DEBUG_LOG("SeekPlayerHandler: Watched item due to percentage: {}", watchedByPerc)
            return watchedByPerc
        elif playedAtBH == 1 and self.creditMarkerHit == "final":
            util.DEBUG_LOG("SeekPlayerHandler: Watched item due to final credits marker")
            return True
        elif playedAtBH == 2 and self.creditMarkerHit == "first":
            util.DEBUG_LOG("SeekPlayerHandler: Watched item due to first credits marker")
            return True
        elif playedAtBH == 3 and (watchedByPerc or self.creditMarkerHit):
            util.DEBUG_LOG("SeekPlayerHandler: Watched item due to percentage or credits marker")
            return True
        return False

    @property
    def videoWatched(self):
        return self.getVideoWatched()

    def triggerProgressEvent(self):
        if not self.player.video:
            return

        rk = str(self.player.video.ratingKey)
        if rk not in self._progressHld:
            # progress already consumed
            return

        gprk = None
        prk = None
        if self.player.video.type == "episode":
            prk = self.player.video.parentRatingKey
            gprk = self.player.video.grandparentRatingKey

        self.player.trigger('video.progress', data=(gprk, prk, rk, self._progressHld[rk] if not self.getVideoWatched(
            ref=self._progressHld[rk] if self._progressHld[rk] > self.trueTime * 1000 else None) else True))
        self._progressHld = {}

    def onPlayBackStopped(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackStopped - '
                       'Seeking={0}, QueueingNext={1}, BingeMode={2}, StoppedManually={3}, SkipPostPlay={4}'
                       .format(self.seeking, self.queuingNext, self.inBingeMode, self.stoppedManually,
                               self.skipPostPlay))

        if self.dialog:
            self.dialog.onPlayBackStopped()

        if self.queuingNext or self.queuingSpecific:
            if self.isDirectPlay and self.playlist and (self.playlist.hasNext() or self.queuingSpecific):
                self.hideOSD(delete=True)
            # fixme: the on_end value is a hack here, we should rename or use a different parameter
            if self.queuingNext:
                if self.next(on_end=not self.skipPostPlay):
                    return

        if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_REWIND):
            if not self.queuingSpecific:
                self.updateNowPlaying()
            self.triggerProgressEvent()

            if not self.queuingSpecific:
                # show post play if possible, if an item has been watched (90% by Plex standards)
                if self.seeking != self.SEEK_PLAYLIST and self.duration:
                    util.DEBUG_LOG("Player - played-threshold: {}%/{}%",
                                   int(self.videoPlayedFac * 100), int(self.playedThresholdPerc))
                    if self.videoWatched and self.next(on_end=True):
                        return

        if (self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_PLAYLIST) or
                (self.seeking == self.SEEK_PLAYLIST and (self.stoppedManually or self.endedManually))):
            self.hideOSD(delete=True)
            self.sessionEnded()

    def onPlayBackEnded(self):
        util.DEBUG_LOG('SeekHandler: onPlayBackEnded - Seeking={0}, External={1}',
                       self.seeking, self.player.isExternal)

        if self.dialog:
            self.dialog.onPlayBackEnded()

        if self.player.playerObject.hasMoreParts():
            self.updateNowPlaying(state=self.player.STATE_PAUSED)  # To for update after seek
            self.seeking = self.SEEK_IN_PROGRESS
            self.player._playVideo(self.player.playerObject.getNextPartOffset(), seeking=self.seeking)
            return

        self.updateNowPlaying()
        self.triggerProgressEvent()

        if self.queuingNext:
            util.DEBUG_LOG('SeekHandler: onPlayBackEnded - event ignored')
            return

        self.stoppedManually = False if not self.player.isExternal else True

        if self.playlist and self.playlist.hasNext():
            self.queuingNext = True
        if self.next(on_end=True):
            return
        else:
            self.queuingNext = False

        if not self.ended:
            if self.seeking != self.SEEK_PLAYLIST:
                self.hideOSD()

            if self.seeking not in (self.SEEK_IN_PROGRESS, self.SEEK_PLAYLIST) or self.player.isExternal:
                self.sessionEnded()

    def onPlayBackPaused(self):
        self.updateNowPlaying()
        if self.dialog:
            self.dialog.onPlayBackPaused()

    def onPlayBackSeek(self, stime, offset):
        if self.waitingForSOS:
            return
        util.DEBUG_LOG('SeekHandler: onPlayBackSeek - {0}, {1}, {2}', stime, offset, self.seekOnStart)
        if self.dialog:
            self.dialog.onPlayBackSeek(stime, offset)

        if self.dialog and self.isDirectPlay and self.seekOnStart:
            withinSOS = self.seekOnStart - 5000

            tries = 0
            while not self.player.isPlayingVideo() and tries < 50 and not util.MONITOR.abortRequested():
                util.MONITOR.waitForAbort(0.1)
                tries += 1

            try:
                p_time = self.player.getTime()
            except RuntimeError:
                # kodi isn't playing anything
                util.LOG("SeekHandler: onPlayBackSeek: Called without playing player, exiting.")
                return

            if p_time * 1000 < withinSOS:
                if self.useResumeFix and self.seekOnStart > 500:
                    self.waitingForSOS = True
                    # checking infoLabel Player.Seeking would be the better solution here, but we're dealing with stuff like
                    # CoreELEC, which doesn't necessarily properly honor this
                    util.MONITOR.waitForAbort(0.25)
                self.seek(self.seekOnStart)

                if self.useResumeFix and self.seekOnStart > 500:
                    util.MONITOR.waitForAbort(util.addonSettings.coreelecResumeSeekWait / 1000.0)

                    util.DEBUG_LOG("OnPlayBackSeek: SeekOnStart: "
                                   "Expecting to be within 5 seconds of {}, currently at: {}, CoreELEC resume seek wait: {}ms", self.seekOnStart,
                                   p_time, util.addonSettings.coreelecResumeSeekWait)

                    tries = 0
                    max_tries = int(5000 / util.addonSettings.coreelecResumeSeekWait)
                    while self.player.isPlayingVideo() and self.player.getTime() * 1000 < withinSOS and tries < max_tries\
                            and not util.MONITOR.abortRequested():
                        util.DEBUG_LOG("OnPlayBackSeek: SeekOnStart: Not there, yet, "
                                       "seeking again ({}, {})", self.seekOnStart, self.player.getTime())
                        util.MONITOR.waitForAbort(0.25)
                        self.seek(self.seekOnStart)
                        tries += 1
                        util.MONITOR.waitForAbort(util.addonSettings.coreelecResumeSeekWait / 1000.0)
                    if tries >= max_tries:
                        util.DEBUG_LOG("OnPlayBackSeek: SeekOnStart: Couldn't properly seek on start within ~5 seconds.")
                    else:
                        util.DEBUG_LOG("OnPlayBackSeek: Seeked on start to: {0}", self.seekOnStart)
                    self.waitingForSOS = False

            # should not be necessary due to other recent changes to dialog persistence, but it doesn't hurt, either
            if self.dialog:
                self.dialog.offset = self.seekOnStart
            self.seekOnStart = 0

        self.updateOffset()
        # self.showOSD(from_seek=True)

    @property
    def subtitleStreamOffset(self):
        if self.player.playerObject and self.isDirectPlay and self.player.playerObject.metadata.isMapped:
            if self._subtitleStreamOffset is not None:
                return self._subtitleStreamOffset

            # when mapped, Kodi finds external subs on its own and places them at the top of the list, before
            # embedded subs.
            kodisubs = None
            tries = 0
            while not kodisubs and tries < 50:
                try:
                    playerID = kodijsonrpc.rpc.Player.GetActivePlayers()[0]["playerid"]
                    kodisubs = kodijsonrpc.rpc.Player.GetProperties(playerid=playerID, properties=['subtitles'])["subtitles"]
                    break
                except IndexError:
                    pass
                tries += 1
                util.MONITOR.waitForAbort(0.1)
            if not kodisubs:
                # this can happen occasionally, if the player isn't ready, yet, but we account for that
                util.DEBUG_LOG("SeekHandler: subtitleStreamOffset: Returning zero as player not available or no "
                               "subtitles found")
                return 0
            if kodisubs:
                # find embedded subtitle stream in Plex
                ess = None
                ext_subs_amount = 0
                for ss in self.player.video.subtitleStreams:
                    if not ss.languageCode:
                        util.DEBUG_LOG("Skipping subtitle: {}, no language code found".format(ss))
                        continue
                    if not ess and ss.embedded:
                        ess = ss
                    # ss.score: only downloaded external subtitles have a score; skip them, as they're not visible to
                    # Kodi
                    elif not ss.embedded and not ss.score:
                        ext_subs_amount += 1

                if not ess:
                    self._subtitleStreamOffset = 0
                    util.DEBUG_LOG("SeekHandler: subtitleStreamOffset: Returning zero as we didn't find an embedded subtitle")
                    return 0

                util.DEBUG_LOG("SeekHandler: subtitleStreamOffset: Found embedded subtitle at: {}", ext_subs_amount)

                # find embedded subtitle stream in Kodi stream list
                # we know Kodi puts external subtitles first, start there (Kodi might see more external subs or the PMS
                # hasn't detected them, so we still need to find the embedded sub we're searching for)

                # use iso639 to determine the streams' languages (Kodi uses the bibliographic language code, Plex uses
                # the terminological one (e.g: ger vs. deu, fre vs. fra)
                ess_lang = languages.get(part2t=ess.languageCode)
                for sub in kodisubs[ext_subs_amount:]:
                    if (sub['isdefault'] == ess.default.asBool() and sub['isforced'] == ess.forced.asBool() and
                            sub['name'] == six.ensure_str(ess.title) and languages.get(
                                part2b=sub['language']) == ess_lang):
                        self._subtitleStreamOffset = sub['index'] - ess.typeIndex
                        util.DEBUG_LOG("SeekHandler: subtitleStreamOffset: Returning offset: {} ({})",
                                       self._subtitleStreamOffset, sub)
                        return self._subtitleStreamOffset

                util.LOG("SeekHandler: Couldn't find embedded subtitle in Kodi subtitle list: {}, assuming no difference", ess)
                self._subtitleStreamOffset = 0

                # old implementation
                # embeddedStreams = list(filter(lambda x: x.embedded, self.player.video.subtitleStreams))
                # difflen = len(kodisubs) - len(embeddedStreams)
                ## does our sub-count differ from the one Kodi sees? if so, adjust the offset
                # if difflen > 0:
                #    self._subtitleStreamOffset = difflen
                #    return self._subtitleStreamOffset
                ## if not, do we have external subtitles? if so, we need to adjust the offset
                # self._subtitleStreamOffset = len(list(filter(lambda x: not x.embedded, self.player.video.subtitleStreams)))
                # return self._subtitleStreamOffset
        return 0

    def setSubtitles(self, do_sleep=True, honor_forced_subtitles_override=True, honor_deselect_subtitles=True,
                     ref="_current_subtitle_idx"):
        util.DEBUG_LOG("SeekHandler: setSubtitles")
        if not self.player.video:
            util.LOG("Warning: SetSubtitles: no player.video object available")
            return

        subs = self.player.video.selectedSubtitleStream(
            forced_subtitles_override=honor_forced_subtitles_override and util.getSetting("forced_subtitles_override",
                                                                                         ) and plexnetUtil.ACCOUNT.subtitlesForced == 0,
            deselect_subtitles=honor_deselect_subtitles and util.getSetting("disable_subtitle_languages") or [],
            ref=ref
        )

        # we want to get the subtitle stream offset regardless of whether we have subtitles selected or not,
        # as the subtitle amount might change during playback (e.g. kodi subtitle download adds one to the list)
        # but our concern are existing external subtitles in path mapped mode, which Kodi adds to the top of the list
        sso = self.subtitleStreamOffset
        if subs:
            if do_sleep:
                xbmc.sleep(100)

            path = subs.getSubtitleServerPath()
            if self.isDirectPlay:
                self.player.showSubtitles(False)
                if path:
                    util.DEBUG_LOG('Setting subtitle path: {0} ({1})', plexnetUtil.cleanToken(path), subs)
                    self.player.setSubtitles(path)
                    self.player.showSubtitles(True)

                else:
                    # u_til.TEST(subs.__dict__)
                    # u_til.TEST(self.player.video.mediaChoice.__dict__)

                    util.DEBUG_LOG('Enabling embedded subtitles at: {0} ({1})', subs.typeIndex + sso, subs)
                    self.player.setSubtitleStream(subs.typeIndex + sso)
                    self.player.showSubtitles(True)

        else:
            self.player.showSubtitles(False)

    def setAudioTrack(self):
        self.player.lastPlayWasBGM = False
        if self.isDirectPlay and self.player.video:
            track = self.player.video.selectedAudioStream()
            if track:
                currIdx = None
                tries = 0
                while currIdx != track.typeIndex and tries < 40:
                    try:
                        playerID = kodijsonrpc.rpc.Player.GetActivePlayers()[0]["playerid"]
                        currIdx = \
                        kodijsonrpc.rpc.Player.GetProperties(playerid=playerID, properties=['currentaudiostream'])[
                            'currentaudiostream']['index']
                    except:
                        pass
                    if currIdx == track.typeIndex:
                        util.DEBUG_LOG('Audio track is correct index: {0}', track.typeIndex)
                        return
                    util.DEBUG_LOG('Switching audio track - index: {0} (try: {1})', track.typeIndex, tries + 1)
                    util.MONITOR.waitForAbort(0.1)
                    self.player.setAudioStream(track.typeIndex)
                    tries += 1


    def updateOffset(self):
        try:
            self.offset = int(self.player.getTime() * 1000)
        except RuntimeError:
            pass

    def initPlayback(self):
        self.seeking = self.NO_SEEK

        #self.setSubtitles()
        if self.isTranscoded and self.player.getAvailableSubtitleStreams():
            util.DEBUG_LOG('Enabling first subtitle stream, as we\'re in DirectStream')
            self.player.showSubtitles(True)
        self.setAudioTrack()

    def onPlayBackFailed(self):
        if self.ended:
            return False

        if self.dialog:
            self.dialog.onPlayBackFailed()

        util.DEBUG_LOG('SeekHandler: onPlayBackFailed - Seeking={0}', self.seeking)
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
        util.DEBUG_LOG('SeekHandler: onVideoWindowOpened - Seeking={0}', self.seeking)
        self.getDialog().show()

        self.initPlayback()

    def onVideoWindowClosed(self):
        self.hideOSD()
        util.DEBUG_LOG('SeekHandler: onVideoWindowClosed - Seeking={0}', self.seeking)
        self.player.trigger('videowindow.closed', session_id=self.sessionID, video=self.player.video)
        if not self.seeking:
            # send events as we might not have seen onPlayBackEnded and/or onPlayBackStopped in certain cases,
            # especially when postplay isn't wanted and we're at the end of a show
            #self.updateNowPlaying()
            #if self._progressHld:
            #    self.triggerProgressEvent()
            if self.player.isPlaying():
                self.player.stopAndWait()

            if not self.playlist or not self.playlist.hasNext():
                if not self.shouldShowPostPlay():
                    util.DEBUG_LOG("SeekHandler: Not showing post-play (VideoWindowClosed)")
                    self.sessionEnded()

    def onVideoOSD(self):
        # xbmc.executebuiltin('Dialog.Close(seekbar,true)')  # Doesn't work :)
        util.DEBUG_LOG('SeekHandler: onVideoOSD - Seeking={0}', self.seeking)
        if self.queuingSpecific or self.queuingNext:
            return
        self.showOSD()

    def tick(self):
        if (self.seeking != self.SEEK_IN_PROGRESS and not self.ended and self.player.started and not self.seekOnStart
                and not self.queuingNext and not self.queuingSpecific and not self.stoppedManually and
                self.player.isPlayingVideo() and self.player.playState != self.player.STATE_STOPPED):
            self.updateNowPlaying(t=self.dialog.timeKeeperTime if self.player.isExternal else None)
        else:
            util.DEBUG_LOG("Not ticking UpdateNowPlaying: {}, {}, {}, {}, {}, {}, {}, {}", self.seeking,
                           self.ended, self.player.started, self.seekOnStart, self.queuingNext, self.stoppedManually,
                           self.player.isPlayingVideo(), self.player.playState)

        if self.dialog and getattr(self.dialog, "_ignoreTick", None) is not True:
            self.dialog.tick()

    def close(self):
        self.hideOSD(delete=True)

    def sessionEnded(self):
        self.player.sessionID = None
        if self.ended:
            return
        self.ended = True
        util.DEBUG_LOG('Player: Video session ended')
        self.player.trigger('session.ended', session_id=self.sessionID)
        self.hideOSD(delete=True)

    __next__ = next


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
            util.MONITOR.waitForAbort(0.1)

        if not plexID:
            return

        if not plexID.startswith('PLEX-'):
            return

        util.DEBUG_LOG('Extracting track info from comment')
        try:
            data = plexID.split(':', 1)[-1]
            from plexnet import plexobjects
            track = plexobjects.PlexObject.deSerialize(base64.urlsafe_b64decode(data.encode('utf-8')))
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
        if windowutils.HOME._shuttingDown:
            return

        plist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        just_added = kwargs.get("just_added")
        # plist.clear()

        waited = 0
        while not kodijsonrpc.rpc.Player.GetActivePlayers() and not util.MONITOR.abortRequested() and waited < 10:
            util.MONITOR.waitForAbort(0.5)
            waited += 0.5

        try:
            citem = kodijsonrpc.rpc.Player.GetItem(playerid=0, properties=['comment'])['item']
            plexID = citem['comment'].split(':', 1)[0]
        except:
            #util.ERROR()
            return

        current = plist.getposition()
        size = plist.size()

        # if we've just added items to the playqueue, we don't need to do any swappery
        if not just_added:
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

            if swap is not None:
                if util.KODI_VERSION_MAJOR >= 20:
                    vi = plist[0].getMusicInfoTag()
                    vi.setPlayCount(swap + 1)

                else:
                    plist[0].setInfo('music', {
                        'playcount': swap + 1,
                    })

            # Now swap the track to the correct position. This seems to be the only way to update the kodi playlist position to the current track's new position
            if swap is not None:
                kodijsonrpc.rpc.Playlist.Swap(playlistid=xbmc.PLAYLIST_MUSIC, position1=0, position2=swap + 1)
                try:
                    kodijsonrpc.rpc.Playlist.Remove(playlistid=xbmc.PLAYLIST_MUSIC, position=0)
                except:
                    pass
        else:
            # add added items
            idx = plist.size() + 1
            for track in just_added:
                url, li = self.player.createTrackListItem(track, index=idx)

                plist.add(url, li)
                idx += 1

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
        self.ignoreTimelines = False
        self.updateNowPlaying(state='playing')

    def onPlayBackStarted(self):
        util.DEBUG_LOG('AudioPlayerHandler: onPlayBackStarted')
        self.player.lastPlayWasBGM = False
        self.updatePlayQueue(delay=True)
        self.extractTrackInfo()
        self.ignoreTimelines = False
        self.updateNowPlaying(state='playing')

    def onAVStarted(self):
        util.DEBUG_LOG('AudioPlayerHandler: onAVStarted')
        self.player.trigger('started.audio')

    def onAVChange(self):
        util.DEBUG_LOG('AudioPlayerHandler: onAVChange')
        self.player.trigger('changed.audio')

    def onPlayBackResumed(self):
        self.updateNowPlaying(state='playing')

    def onPlayBackPaused(self):
        self.updateNowPlaying(state='paused')

    def onPlayBackStopped(self):
        self.updatePlayQueue()
        self.updateNowPlaying(state='stopped')
        self.ignoreTimelines = True
        self.player.trigger('audio.stopped')
        self.finish()

    def onPlayBackEnded(self):
        self.updatePlayQueue()
        self.updateNowPlaying(state='stopped')
        self.ignoreTimelines = True
        self.finish()

    def onPlayBackFailed(self):
        return True

    def finish(self):
        self.player.trigger('session.ended')
        util.setGlobalProperty('track.ID', '')

    def tick(self):
        if not self.player.isPlayingAudio() or util.MONITOR.abortRequested():
            return

        self.stampCurrentTime()
        self.updateNowPlaying()


class BGMPlayerHandler(BasePlayerHandler):
    def __init__(self, player, init_data):
        BasePlayerHandler.__init__(self, player)
        self.timelineType = 'music'
        self.initData = init_data
        self.currentlyPlaying = init_data[2]
        util.setGlobalProperty('track.ID', '')

        self.oldVolume = util.rpc.Application.GetProperties(properties=["volume"])["volume"]

    def onPlayBackStarted(self):
        self.player.bgmStarting = False
        self.player.trigger('bgm.started')
        util.DEBUG_LOG("BGM: playing theme for {}", self.currentlyPlaying)

    def _setVolume(self, vlm):
        xbmc.executebuiltin("SetVolume({})".format(vlm))

    def setVolume(self, volume=None, reset=False):
        vlm = self.oldVolume if reset else volume
        curVolume = self.getVolume()

        if curVolume != vlm:
            util.DEBUG_LOG("BGM: {}setting volume to: {}", "re-" if reset else "", vlm)
            self._setVolume(vlm)
        else:
            util.DEBUG_LOG("BGM: Volume already at {}", vlm)
            return

        waited = 0
        waitMax = 5
        while curVolume != vlm and waited < waitMax:
            util.DEBUG_LOG("Waiting for volume to change from {} to {}", curVolume, vlm)
            xbmc.sleep(100)
            waited += 1
            curVolume = self.getVolume()

        if waited == waitMax:
            util.DEBUG_LOG("BGM: Timeout setting volume to {} (is: {}). Might have been externally changed in the "
                           "meantime".format(vlm, self.getVolume()))

    def resetVolume(self):
        self.setVolume(reset=True)

    def onPlayBackStopped(self):
        util.DEBUG_LOG("BGM: stopped theme for {}", self.currentlyPlaying)
        util.setGlobalProperty('theme_playing', '')
        self.player.bgmPlaying = False
        self.resetVolume()

    def onPlayBackEnded(self):
        self.onPlayBackStopped()

        if util.getSetting('theme_music_loop') and not self.player.dontRequeueBGM:
            self.player.playBackgroundMusic(*self.initData)

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

        self.player.bgmPlaying = True
        util.setGlobalProperty('theme_playing', '1')
        ct = 0
        while ct < 10 and not util.getGlobalProperty('theme_playing') and not util.MONITOR.abortRequested():
            util.MONITOR.waitForAbort(0.1)
            ct += 1

        self.player.play(self.source, windowed=True)


class PlexPlayer(xbmc.Player, signalsmixin.SignalsMixin):
    STATE_STOPPED = "stopped"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_BUFFERING = "buffering"

    OFFSET_RE = re.compile(r'(offset=)\d+')

    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        signalsmixin.SignalsMixin.__init__(self)
        self.sessionID = None
        self.handler = AudioPlayerHandler(self)
        self.isExternal = False

        self.on('action', self.playerAction)

    def init(self):
        self._closed = False
        self._nextItem = None
        self._ignorePlaybackFailure = False
        self.started = False
        self.bgmPlaying = False
        self.bgmStarting = False
        self.lastPlayWasBGM = False
        self.BGMTask = None
        self.pauseAfterPlaybackStarted = False
        self.video = None
        self.sessionID = None
        self.hasOSD = False
        self.hasSeekOSD = False
        self.handler = AudioPlayerHandler(self)
        self.playerObject = None
        self.currentTime = 0
        self.thread = None
        self.ignoreStopEvents = False
        self.isExternal = False
        self.dontRequeueBGM = False
        if xbmc.getCondVisibility('Player.HasMedia') and self.isPlayingAudio() and not self.bgmPlaying:
            self.started = True
        self.resume = False
        self.open()

        return self

    def open(self):
        self._closed = False
        self.monitor()

    def close(self, shutdown=False):
        self._closed = True
        if shutdown:
            self.off('action', self.playerAction)

    def reset(self):
        self.video = None
        self.started = False
        self.bgmPlaying = False
        self.playerObject = None
        self.pauseAfterPlaybackStarted = False
        self.ignoreStopEvents = False
        self._ignorePlaybackFailure = False
        self.dontRequeueBGM = False
        #self.handler = AudioPlayerHandler(self)
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

    def playerAction(self, action, **kwargs):
        """
        Signal receiver for specific player actions (called by SeekDialog for example)
        @param action: "next", "prev", "playAt"
        @param kwargs: "pos"=playlist index; in case of action == "playAt"
        @return:
        """
        if not self.handler:
            util.DEBUG_LOG("Player: Can't handle action without handler")
            return

        util.DEBUG_LOG('Player - Action: {} ({})', action, str(kwargs))

        self.handler.hideOSD()

        if action == "next":
            self.handler.next()

        elif action == "prev":
            self.handler.prev()

        elif action == "playAt":
            self.handler.playAt(kwargs['pos'])

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
                if isinstance(self.handler, BGMPlayerHandler) and self.handler.currentlyPlaying == rating_key:
                    return

                # cancel any currently playing theme before starting the new one
                else:
                    self.stopAndWait()
        self.sessionID = "BGM{}".format(rating_key)
        curVol = self.handler.getVolume()
        # no current volume, don't play BGM either
        if not curVol:
            return

        if self.BGMTask and self.BGMTask.isValid():
            self.BGMTask.cancel()

        self.started = False
        self.bgmStarting = True
        self.dontRequeueBGM = False
        self.handler = BGMPlayerHandler(self, [source, volume, rating_key])

        # store current volume if it's different from the BGM volume
        if volume < curVol:
            util.setSetting('last_good_volume', curVol)

        self.lastPlayWasBGM = True

        self.handler.setVolume(volume)

        self.BGMTask = BGMPlayerTask().setup(source, self, *args, **kwargs)
        backgroundthread.BGThreader.addTask(self.BGMTask)

    def playVideo(self, video, resume=False, force_update=False, session_id=None, handler=None):
        if self.bgmPlaying:
            self.stopAndWait()

        self.handler = handler if handler and isinstance(handler, SeekPlayerHandler) \
            else SeekPlayerHandler(self, session_id or self.sessionID)

        self.video = video
        self.resume = resume
        self.open()
        self._playVideo(resume and video.viewOffset.asInt() or 0, force_update=force_update, session_id=session_id)

    def getOSSPathHint(self, meta):
        # only hint the path one folder above for a movie, two folders above for TV
        try:
            head1, tail1 = os.path.split(meta.path)
            head2, tail2 = os.path.split(head1)
            if self.video.type == "episode":
                head3, tail3 = os.path.split(head2)
                cleaned_path = os.path.join(tail3, tail2, tail1)
            else:
                cleaned_path = os.path.join(tail2, tail1)
        except:
            cleaned_path = ""
        return cleaned_path

    def _playVideo(self, offset=0, seeking=0, force_update=False, playerObject=None, session_id=None):
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
            raise
        except:
            util.ERROR(notify=True)
            return

        meta = self.playerObject.metadata
        url = meta.streamUrls[0]

        bifURL = self.playerObject.getBifUrl()
        util.DEBUG_LOG('Playing URL(+{1}ms): {0}{2}', plexnetUtil.cleanToken(url), offset, bifURL and ' - indexed' or '')

        self.ignoreStopEvents = True
        self.stopAndWait()  # Stop before setting up the handler to prevent player events from causing havoc
        if self.handler and self.handler.queuingNext and util.addonSettings.consecutiveVideoPbWait:
            util.DEBUG_LOG(
                "Waiting for {}s until playing back next item".format(util.addonSettings.consecutiveVideoPbWait))
            util.MONITOR.waitForAbort(util.addonSettings.consecutiveVideoPbWait)

        self.ignoreStopEvents = False
        self.sessionID = session_id or self.sessionID

        # fixme: this handler might be accessing a new playerObject, not the one it's expecting to access,
        #        especially when .next() is used
        self.handler.reset()
        self.handler.setup(self.video.duration.asInt(), meta, offset, bifURL, title=self.video.grandparentTitle,
                           title2=self.video.title, seeking=seeking, chapters=self.video.chapters,
                           is_mapped=meta.isMapped)

        # try to get an early intro offset so we can skip it if necessary
        introOffset = None
        if not offset:
            # in case we're transcoded, instruct the marker handler to set the marker a skipped, so we don't re-skip it
            # after seeking
            probOff = self.handler.getIntroOffset(offset, setSkipped=meta.isTranscoded)
            if probOff:
                introOffset = probOff

        if meta.isTranscoded:
            self.handler.mode = self.handler.MODE_RELATIVE

            if introOffset:
                # cheat our way into an early intro skip by modifying the offset in the stream URL
                util.DEBUG_LOG("Immediately seeking behind intro: {}", introOffset)
                url = self.OFFSET_RE.sub(r"\g<1>{}".format(introOffset // 1000), url)
                self.handler.dialog.baseOffset = introOffset

                # probably not necessary
                meta.playStart = introOffset // 1000
        else:
            if offset:
                util.DEBUG_LOG("Using as SeekOnStart: {0}; offset: {1}", meta.playStart, offset)
                self.handler.seekOnStart = meta.playStart * 1000
            elif introOffset:
                util.DEBUG_LOG("Seeking behind intro after playstart: {}", introOffset)
                self.handler.seekOnStart = introOffset

            self.handler.mode = self.handler.MODE_ABSOLUTE

        if not meta.isMapped:
            # Kodi 19 will try to look for subtitles in the directory containing the file. '/' and `/file.mkv` both
            # point to the file, and Kodi will happily try to read the whole file without recognizing it isn't a
            # directory. To get around that, we omit the filename here since it is unnecessary.
            omit, fname = url.rsplit("/", 1)
            if fname.startswith("file."):
                url = "{}/{}".format(omit, "?" + fname.split("?")[1] if "?" in fname else "")

            url = util.addURLParams(url, {
                'X-Plex-Client-Profile-Name': 'Generic',
                'X-Plex-Client-Identifier': plexapp.util.INTERFACE.getGlobal('clientIdentifier')
            })
        li = xbmcgui.ListItem(self.video.title, path=url)
        vtype = self.video.type if self.video.type in ('movie', 'episode', 'musicvideo') else 'video'

        util.setGlobalProperty("current_path", self.getOSSPathHint(meta), base='videoinfo.{0}')
        util.setGlobalProperty("current_size", str(meta.size), base='videoinfo.{0}')

        imdbNum = None

        fill_trakt_ids = False
        trakt_ids = {}

        # generate guids when script.trakt is installed
        if "script.trakt" in util.USER_ADDONS:
            fill_trakt_ids = True

        a = self.video.guid
        if "com.plexapp.agents.imdb" in a:
            imdbNum = a.split("?lang=")[0][a.index("com.plexapp.agents.imdb://")+len("com.plexapp.agents.imdb://"):]
            if fill_trakt_ids:
                if imdbNum:
                    trakt_ids["imdb"] = imdbNum

        elif fill_trakt_ids and "com.plexapp.agents.themoviedb" in a:
            trakt_ids["tmdb"] = a.split("?lang=")[0][
                                a.index("com.plexapp.agents.themoviedb://") + len("com.plexapp.agents.themoviedb://"):]

        elif fill_trakt_ids and "com.plexapp.agents.thetvdb" in a:
            trakt_ids["tvdb"] = a.split("?lang=")[0][
                                a.index("com.plexapp.agents.thetvdb://") +
                                len("com.plexapp.agents.thetvdb://"):].split("/", 1)[0]

        elif "plex://movie" in a or "plex://episode" in a:
            ref = self.video
            if fill_trakt_ids and "plex://episode" in a:
                ref = self.video.show()
                if not ref.isFullObject():
                    ref.reload()

            for guid in ref.guids:
                if not imdbNum and guid.id.startswith('imdb://'):
                    imdbNum = guid.id.split('imdb://')[1]

                if fill_trakt_ids:
                    sabbr, gid = guid.id.split("://")
                    try:
                        gid = int(gid)
                    except:
                        pass

                    trakt_ids[sabbr] = gid
        if fill_trakt_ids:
            # generate trakt slug
            if vtype == "movie":
                year = self.video.year.asInt()
                trakt_ids['slug'] = util.slugify("{}{}".format(self.video.title, year and " {}".format(year) or ""))

            util.DEBUG_LOG("Setting Trakt IDs: {}", trakt_ids)
            # report IDs to trakt
            xbmcgui.Window(10000).setProperty('script.trakt.ids', json.dumps(trakt_ids))

        info = {
            'mediatype': vtype,
            'title': self.video.title,
            'originaltitle': self.video.title,
            'tvshowtitle': self.video.grandparentTitle,
            'year': self.video.year.asInt(),
            'plot': self.video.summary,
            'path': meta.path,
            'size': meta.size,
            'imdbnumber': imdbNum
        }
        if vtype == "episode":
            info.update({
                'episode': self.video.index.asInt(),
                'season': self.video.parentIndex.asInt(),
            })
        util.DEBUG_LOG("Setting VideoInfo: {}".format(
            plexnetUtil.cleanObjTokens(info, flistkeys=[])
        ))

        li.setArt({
            'poster': self.video.defaultThumb.asTranscodedImageURL(347, 518),
            'fanart': self.video.defaultArt.asTranscodedImageURL(1920, 1080),
            'thumb': self.video.defaultThumb.asTranscodedImageURL(256, 256),
        })

        if util.KODI_VERSION_MAJOR >= 20:
            li.setInfo('video', {'size': info['size']})

            vi = li.getVideoInfoTag()
            vi.setMediaType(info['mediatype'])
            vi.setTitle(info['title'])
            vi.setOriginalTitle(info['originaltitle'])
            vi.setTvShowTitle(info['tvshowtitle'])
            vi.setYear(info['year'])
            vi.setPlot(info['plot'])
            vi.setPath(info['path'])
            vi.setIMDBNumber(info['imdbnumber'])
            if vtype == "episode":
                vi.setEpisode(info['episode'])
                vi.setSeason(info['season'])
        else:
            li.setInfo('video', info)

        self.trigger('starting.video')
        self.handler.queuingNext = False
        self.handler.queuingSpecific = False
        self.play(url, li)

    def playVideoPlaylist(self, playlist, resume=False, handler=None, session_id=None):
        if self.bgmPlaying:
            self.stopAndWait()

        if handler and isinstance(handler, SeekPlayerHandler):
            util.DEBUG_LOG("PlayVideoPlaylist: Reusing old handler: {}", handler)
            self.handler = handler
            #self.handler.queuingNext = True
            #self.handler.seekOnStart = 0
            #self.handler.baseOffset = 0
            #if self.handler.dialog:
            #    self.handler.dialog.doClose(delete=True)
            #self.handler.dialog = None
            self.playerObject = None
            self.currentTime = 0
        else:
            self.handler = SeekPlayerHandler(self, session_id or self.sessionID)

        self.handler.playlist = playlist
        if playlist.isRemote:
            self.handler.playQueue = playlist
        self.video = playlist.current()
        self.video.softReload(includeChapters=1)
        self.resume = resume
        self.open()
        self._playVideo(resume and self.video.viewOffset.asInt() or 0, seeking=handler and handler.SEEK_PLAYLIST or 0,
                        force_update=True, session_id=session_id)

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

    def playAudio(self, track, fanart=None, **kwargs):
        if self.bgmPlaying:
            self.stopAndWait()

        self.ignoreStopEvents = True
        self.handler = AudioPlayerHandler(self)
        self.playerObject = plexplayer.PlexAudioPlayer(track)
        url, li = self.createTrackListItem(track, fanart)
        self.stopAndWait()
        self.ignoreStopEvents = False

        # maybe fixme: once started, self.sessionID will never be None for Audio
        self.sessionID = "AUD%s" % track.ratingKey
        self.trigger('starting.audio')
        self.play(url, li, **kwargs)

    def playAlbum(self, album, startpos=-1, fanart=None, **kwargs):
        if self.bgmPlaying:
            self.stopAndWait()

        self.ignoreStopEvents = True
        self.handler = AudioPlayerHandler(self)
        self.playerObject = plexplayer.PlexAudioPlayer()
        plist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        plist.clear()
        index = 1
        for track in album.tracks():
            url, li = self.createTrackListItem(track, fanart, index=index)
            plist.add(url, li)
            index += 1
        xbmc.executebuiltin('PlayerControl(RandomOff)')
        self.stopAndWait()
        self.ignoreStopEvents = False
        self.sessionID = "ALB%s" % album.ratingKey
        self.trigger('starting.audio')
        self.play(plist, startpos=startpos, **kwargs)

    def playAudioPlaylist(self, playlist, startpos=-1, fanart=None, **kwargs):
        if self.bgmPlaying:
            self.stopAndWait()

        self.ignoreStopEvents = True
        self.handler = AudioPlayerHandler(self)
        self.playerObject = plexplayer.PlexAudioPlayer()
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
        self.ignoreStopEvents = False
        self.sessionID = "PLS%s" % getattr(playlist, "ratingKey", getattr(playlist, "id", random.randint(0, 1000)))
        self.trigger('starting.audio')
        self.play(plist, startpos=startpos, **kwargs)

    def createTrackListItem(self, track, fanart=None, index=0):
        data = base64.urlsafe_b64encode(track.serialize().encode("utf8")).decode("utf8")
        if not track.isFullObject():
            track = track.reload()
        url = self.playerObject.build(track)['url']
        li = xbmcgui.ListItem(track.title, path=url)
        info = {
            'artist': six.text_type(track.originalTitle or track.grandparentTitle),
            'title': six.text_type(track.title),
            'album': six.text_type(track.parentTitle),
            'discnumber': track.parentIndex.asInt(),
            'tracknumber': track.get('index').asInt(),
            'duration': int(track.duration.asInt() / 1000),
            'playcount': index,
            # fixme: this is not really necessary, as we don't go the plugin:// route anymore.
            #        changing the track identification style would mean a bigger rewrite, though, so let's keep it.
            'comment': 'PLEX-{0}:{1}'.format(track.ratingKey, data)
        }

        art = fanart or track.defaultArt
        li.setArt({
            'fanart': art.asTranscodedImageURL(1920, 1080),
            'landscape': util.backgroundFromArt(art),
            'thumb': track.defaultThumb.asTranscodedImageURL(800, 800),
        })
        if fanart:
            li.setArt({'fanart': fanart})

        if util.KODI_VERSION_MAJOR >= 20:
            ai = li.getMusicInfoTag()
            ai.setArtist(info['artist'])
            ai.setTitle(info['title'])
            ai.setAlbum(info['album'])
            ai.setDisc(info['discnumber'])
            ai.setTrack(info['tracknumber'])
            ai.setDuration(info['duration'])
            ai.setPlayCount(info['playcount'])
            ai.setComment(info['comment'])
        else:
            li.setInfo('music', info)

        return (url, li)

    def onPrePlayStarted(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - PRE-PLAY; handler: %r' % self.handler)
        self.trigger('preplay.started')
        if not self.handler:
            return
        self.handler.onPrePlayStarted()

    def onPlayBackStarted(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - STARTED')
        self.trigger('playback.started')

        if not self.handler:
            return
        self.handler.onPlayBackStarted()

    def onAVChange(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - AVChange: Time: {}', self.getTime() if self.isPlayingVideo() else "Not playing")
        if not self.handler:
            return
        self.handler.onAVChange()

    def onAVStarted(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - AVStarted: {}, Time: {}', self.handler,
                       self.getTime() if self.isPlayingVideo() else "Not playing")
        if self.pauseAfterPlaybackStarted:
            self.control('pause')
            self.pauseAfterPlaybackStarted = False

        self.isExternal = self.isExternalPlayer()
        self.trigger('av.started')
        self.started = True
        if not self.handler:
            return
        self.handler.onAVStarted()

    def onPlayBackPaused(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - PAUSED')
        if not self.handler:
            return
        self.handler.onPlayBackPaused()

    def onPlayBackResumed(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - RESUMED')
        if not self.handler:
            return

        self.handler.onPlayBackResumed()

    def onPlayBackStopped(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - STOPPED' + (not self.started and ': FAILED' or ''))
        if self.ignoreStopEvents:
            return

        if not self.started:
            self.onPlayBackFailed()

        if not self.handler:
            return
        self.handler.onPlayBackStopped()

    def onPlayBackEnded(self):
        if not self.sessionID:
            return

        if self.isExternal:
            self.trigger('videowindow.closed', session_id=self.sessionID, video=self.video)

        util.DEBUG_LOG('Player - ENDED' + (not self.started and ': FAILED' or ''))
        if self.ignoreStopEvents:
            return

        if not self.started:
            self.onPlayBackFailed()

        if not self.handler:
            return
        self.handler.onPlayBackEnded()

    def onPlayBackSeek(self, time, offset):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - SEEK: {} {:d}', time, offset)
        if not self.handler:
            return
        self.handler.onPlayBackSeek(time, offset)

    def onPlayBackError(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - ERROR: {}', self.handler)
        if not self.handler:
            return

        if self.handler.onPlayBackFailed() and not self._ignorePlaybackFailure:
            self.ignoreStopEvents = True
            util.showNotification('Playback Error!')
            self.stopAndWait()
            self.close()

    def onPlayBackFailed(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player - FAILED: {}', self.handler)
        if not self.handler:
            return

        if self.handler.onPlayBackFailed() and not self._ignorePlaybackFailure:
            util.showNotification(util.T(32448, 'Playback Failed!'))
            self.stopAndWait()
            self.close()
            # xbmcgui.Dialog().ok('Failed', 'Playback failed')

    def onVideoWindowOpened(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player: Video window opened')
        try:
            self.handler.onVideoWindowOpened()
        except:
            util.ERROR()

    def onVideoWindowClosed(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player: Video window closed')
        try:
            self.handler.onVideoWindowClosed()
            # self.stop()
        except:
            util.ERROR()

    def onVideoOSD(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player: Video OSD opened')
        try:
            self.handler.onVideoOSD()
        except:
            util.ERROR()

    def onSeekOSD(self):
        if not self.sessionID:
            return
        util.DEBUG_LOG('Player: Seek OSD opened')
        try:
            self.handler.onSeekOSD()
        except:
            util.ERROR()

    def stopAndWait(self):
        if self.isPlaying():
            util.DEBUG_LOG('Player: Stopping and waiting...')
            self.dontRequeueBGM = True
            self.stop()
            if not util.MONITOR.abortRequested():
                while not util.MONITOR.waitForAbort(0.1) and self.isPlaying():
                    if util.MONITOR.abortRequested():
                        break
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

                while not util.MONITOR.abortRequested() and not self._closed and \
                        (not self.isPlaying() or (self.isPlaying() and not self.sessionID)):
                    util.MONITOR.waitForAbort(0.1)

                if self.isPlayingVideo():
                    util.DEBUG_LOG('Monitoring video...')
                    self._videoMonitor()
                elif self.isPlayingAudio():
                    if self.bgmPlaying:
                        util.DEBUG_LOG('Monitoring BGM...')
                        while self.isPlayingAudio() and self.bgmPlaying and not util.MONITOR.abortRequested() and \
                                not self._closed:
                            util.MONITOR.waitForAbort(0.1)
                    else:
                        util.DEBUG_LOG('Monitoring audio...')
                        self._audioMonitor()
                elif self.isPlaying():
                    util.DEBUG_LOG('Monitoring pre-play...')

                    # note: this might never be triggered depending on how fast the video playback starts.
                    # don't rely on it in any way.
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
        util.DEBUG_LOG("VideoMonitor: Initializing...")
        while self.isPlayingVideo() and not util.MONITOR.abortRequested() and not self._closed:
            if self.handler and (self.handler.queuingNext or self.handler.queuingSpecific):
                # when waiting for the next item to be fully initialized, don't set self.currentTime, otherwise
                # onPlaybackStarted could push an invalid trueTime
                util.DEBUG_LOG("VideoMonitor: Waiting for next item to queue...")
                while (self.handler and (self.handler.queuingNext or self.handler.queuingSpecific)
                       and not util.MONITOR.abortRequested() and not self._closed):
                    util.MONITOR.waitForAbort(0.1)

                util.DEBUG_LOG("VideoMonitor: Started")

            if not self.isExternal:
                p_time = None
                t_tries = 0
                while not p_time and not util.MONITOR.abortRequested() and t_tries < 50 and not self.isExternal:
                    try:
                        self.currentTime = p_time = self.getTime()
                    except RuntimeError:
                        util.DEBUG_LOG("VideoMonitor: Waiting for player readiness...")
                        t_tries += 1
                        util.MONITOR.waitForAbort(0.1)

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
            try:
                self.currentTime = self.getTime()
            except RuntimeError:
                break

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
