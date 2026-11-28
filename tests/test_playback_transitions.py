# coding=utf-8
"""Production fullscreen polling and handler lifecycle under controlled Kodi events.

The monitor may survive a complete autoplay stop. Neither a queue wait nor a
busy dialog guarantees that it samples fullscreen false before the new item.
These tests record GUI boundaries; native input, rendering and timing need Kodi.
"""
from __future__ import absolute_import

from types import SimpleNamespace
from unittest.mock import patch

from kodienv import ENV
ENV.abort_requested = True
from lib import player
from lib.windows import seekdialog
from lib.windows.videoplayer import VideoPlayerWindow
from tests.base import KodiTestCase


class Dialog(seekdialog.SeekDialog):
    def __init__(self, handler):
        self.handler = handler
        self.shown = 0
        self.props = {}
        self._lastAction = self._currentMarker = self._osdHideAnimationTimeout = None
        self._ignoreInput = self._ignoreTick = self._seeking = self._applyingSeek = False
        self._playerDebugActive = self._playerNativePPIActive = self.waitingForBuffer = False

    def resetTimeout(self):
        pass

    def getFocusId(self):
        return self.MAIN_BUTTON_ID

    def getProperty(self, name):
        return self.props.get(name, '')

    def setProperty(self, name, value):
        self.props[name] = value

    def osdVisible(self):
        return False

    def sendTimeline(self, **kwargs):
        pass

    def doClose(self, **kwargs):
        pass

    def show(self):
        self.shown += 1
        self.handler.player.opened.append(self.handler.playbackID)
        if self.handler.player.afterOpen:
            self.handler.player.afterOpen()

    def onPlayBackStopped(self):
        pass


class Handler(player.SeekPlayerHandler):
    def getDialog(self, setup=False):
        if self.dialog is None:
            self.dialog = Dialog(self)
        return self.dialog

    def setAudioTrack(self):
        self.player.audioSet.append(self.playbackID)

    def hideOSD(self, delete=False, **kwargs):
        if delete:
            self.dialog = None

    def updateNowPlaying(self, **kwargs):
        pass

    def triggerProgressEvent(self):
        pass

    def ensureCorrectVolume(self):
        pass

    def shouldShowPostPlay(self):
        return False

    def onPlayBackStarted(self):
        self.player.starts += 1

    def tick(self):
        pass


class Playback(player.PlexPlayer):
    def __init__(self):
        player.PlexPlayer.__init__(self)
        self.sessionID = 'session'
        self.handler = Handler(self, self.sessionID)
        self.handler.mode = self.handler.MODE_ABSOLUTE
        self.handler.playbackID = 'E3'
        self._closed = False
        self.started = True
        self.ignoreStopEvents = False
        self.hasOSD = self.hasSeekOSD = False
        self.lavSettingControl = None
        self._originalAlternateSeek = False
        self.video = SimpleNamespace(clearCache=lambda: None)
        self.running = self.ready = self.fullscreen = True
        self.busy = self.abort = False
        self.opened = []
        self.audioSet = []
        self.stopCalls = self.starts = 0
        self.afterOpen = None

    def isPlaying(self):
        return self.running

    def isPlayingVideo(self):
        return self.running

    def getTime(self):
        if not self.ready:
            raise RuntimeError('Not ready')
        return 1.0

    def stop(self):
        self.stopAndWait()

    def stopAndWait(self, **kwargs):
        self.running = False
        self.stopCalls += 1
        self.onPlayBackStopped()

    def visible(self, condition):
        return {'VideoPlayer.IsFullscreen': self.fullscreen,
                'Window.IsVisible(busydialog)': self.busy}.get(condition, False)


class ScriptedMonitor(object):
    def __init__(self, playback, steps):
        self.playback = playback
        self.steps = iter(steps)

    def abortRequested(self):
        return self.playback.abort

    def waitForAbort(self, seconds):
        step = next(self.steps, None)
        if step is None:
            self.playback.running = False
            self.playback._closed = True
        else:
            step()
        return False


class PlaybackTransitionTest(KodiTestCase):
    def runMonitor(self, p, steps):
        monitor = ScriptedMonitor(p, steps)
        with patch.object(player.util, 'MONITOR', monitor), \
                patch.object(player.xbmc, 'getCondVisibility', p.visible):
            p._videoMonitor()

    def test_autoplay_hidden_or_busy_masked_close_initializes_new_item_and_back_ends_session(self):
        for masked in (False, True):
            for queue in ('queuingNext', 'queuingSpecific'):
                with self.subTest(masked=masked, queue=queue):
                    p = Playback()
                    backdrop = SimpleNamespace(sessionID=p.sessionID, closed=0)
                    backdrop.doClose = lambda: setattr(backdrop, 'closed', backdrop.closed + 1)
                    p.on('session.ended', lambda **kw: VideoPlayerWindow.sessionEnded(backdrop, **kw))
                    def queueItem():
                        p.afterOpen = None
                        setattr(p.handler, queue, True)
                        p.fullscreen = False
                    p.afterOpen = queueItem
                    def newItem():
                        # Same handler/session; setup replaces the per-playback ID/dialog.
                        p.handler.dialog = None
                        p.handler.playbackID = 'E4'
                        p.handler.seeking = p.handler.SEEK_PLAYLIST
                        setattr(p.handler, queue, False)
                        p.fullscreen = not masked
                        p.busy = masked
                        p.ready = False
                    def ready():
                        p.ready = True
                    def fullscreen():
                        p.fullscreen = True
                    def dismissBusy():
                        p.busy = False
                    def back():
                        p.fullscreen = False
                    self.runMonitor(p, [lambda: None, lambda: None, newItem, ready,
                                        lambda: None, fullscreen, dismissBusy, back])
                    self.assertEqual(p.opened, ['E3', 'E4'])
                    self.assertEqual(p.audioSet, ['E3', 'E4'])
                    self.assertEqual(p.handler.seeking, p.handler.NO_SEEK)
                    self.assertEqual(p.stopCalls, 1)
                    self.assertEqual(backdrop.closed, 1, 'one Back must terminate the matching backdrop session')

    def test_same_item_seek_and_busy_overlay_do_not_reinitialize(self):
        p = Playback()
        def seeking():
            p.handler.seeking = p.handler.SEEK_IN_PROGRESS
            p.busy = True
        def maskedClose():
            p.fullscreen = False
        def landed():
            p.fullscreen = True
            p.handler.seeking = p.handler.NO_SEEK
            p.busy = False
        self.runMonitor(p, [lambda: None, seeking, maskedClose, landed, lambda: None])
        self.assertEqual(p.opened, ['E3'])
        self.assertEqual(p.audioSet, ['E3'])

    def test_observed_close_and_reopen_same_item_still_open_twice(self):
        p = Playback()
        def close():
            p.handler.seeking = p.handler.SEEK_IN_PROGRESS
            p.fullscreen = False
        def reopen():
            p.fullscreen = True
        self.runMonitor(p, [lambda: None, close, reopen])
        self.assertEqual(p.opened, ['E3', 'E3'])

    def test_new_playback_with_retained_dialog_still_initializes(self):
        p = Playback()
        def replace():
            p.handler.playbackID = 'part2'
            p.handler.seeking = p.handler.SEEK_IN_PROGRESS
        self.runMonitor(p, [lambda: None, replace])
        self.assertEqual(p.opened, ['E3', 'part2'])
        self.assertEqual(p.handler.seeking, p.handler.NO_SEEK)

    def test_cancelled_queue_wait_does_not_initialize_replacement(self):
        for cancellation in ('_closed', 'abort'):
            with self.subTest(cancellation=cancellation):
                p = Playback()
                def queueItem():
                    p.afterOpen = None
                    p.handler.queuingNext = True
                p.afterOpen = queueItem
                def cancel():
                    p.handler.playbackID = 'cancelled'
                    p.handler.seeking = p.handler.SEEK_PLAYLIST
                    setattr(p, cancellation, True)
                self.runMonitor(p, [lambda: None, cancel])
                self.assertEqual(p.opened, ['E3'])
                self.assertEqual(p.stopCalls, 0)

    def test_replacement_handler_initializes_its_own_session(self):
        p = Playback()
        old = p.handler
        def replacement():
            p.sessionID = 'replacement'
            p.handler = Handler(p, p.sessionID)
            p.handler.mode = p.handler.MODE_ABSOLUTE
            p.handler.playbackID = 'new-session'
            p.handler.seeking = p.handler.SEEK_PLAYLIST
        self.runMonitor(p, [lambda: None, replacement])
        self.assertEqual(p.opened, ['E3', 'new-session'])
        self.assertEqual(p.handler.seeking, p.handler.NO_SEEK)
        self.assertFalse(old.ended)

    def test_addon_back_and_manual_stop_after_reused_monitor_end_matching_backdrop(self):
        class Action(object):
            def __init__(self, action):
                self.action = action

            def getId(self):
                return self.action

            def getButtonCode(self):
                return 0

            def __eq__(self, other):
                return self.action == other

        for action in (seekdialog.xbmcgui.ACTION_NAV_BACK, seekdialog.xbmcgui.ACTION_STOP):
            with self.subTest(action=action):
                p = Playback()
                backdrop = SimpleNamespace(sessionID=p.sessionID, closed=0)
                backdrop.doClose = lambda: setattr(backdrop, 'closed', backdrop.closed + 1)
                p.on('session.ended', lambda **kw: VideoPlayerWindow.sessionEnded(backdrop, **kw))
                def newItem():
                    p.afterOpen = None
                    p.handler.dialog = None
                    p.handler.playbackID = 'E4'
                    p.handler.seeking = p.handler.SEEK_PLAYLIST
                p.afterOpen = newItem
                def press():
                    self.assertIsNotNone(p.handler.dialog)
                    p.handler.dialog.onAction(Action(action))
                self.runMonitor(p, [lambda: None, lambda: None, press])
                self.assertEqual(p.opened, ['E3', 'E4'])
                self.assertEqual(p.stopCalls, 1)
                self.assertTrue(p.handler.stoppedManually)
                self.assertEqual(backdrop.closed, 1)

    def test_stale_terminal_ignored_but_stop_after_new_start_ends_session(self):
        p = Playback()
        p._pendingStaleStop = True
        p.handler.seeking = p.handler.SEEK_PLAYLIST
        p.onPlayBackStopped()
        self.assertFalse(p.handler.ended)
        self.assertFalse(p._pendingStaleStop)
        p._pendingStaleStop = True
        p.onPlayBackStarted()
        self.assertFalse(p._pendingStaleStop)
        self.assertEqual(p.starts, 1)
        p.handler.stoppedManually = True
        p.running = False
        p.onPlayBackStopped()
        self.assertTrue(p.handler.ended)
        self.assertIsNone(p.sessionID)

    def test_old_session_end_cannot_close_replacement_backdrop(self):
        backdrop = SimpleNamespace(sessionID='new', closed=0)
        backdrop.doClose = lambda: setattr(backdrop, 'closed', backdrop.closed + 1)
        VideoPlayerWindow.sessionEnded(backdrop, session_id='old')
        self.assertEqual(backdrop.closed, 0)
        VideoPlayerWindow.sessionEnded(backdrop, session_id='new')
        self.assertEqual(backdrop.closed, 1)
