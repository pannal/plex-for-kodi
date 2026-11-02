# coding=utf-8
"""Replay blackout ownership and idle-stop with recording native GUI calls.

Events force show/cleanup overlap; these tests do not simulate Kodi rendering.
"""
from __future__ import absolute_import

import threading
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from kodienv import ENV
ENV.abort_requested = True
from lib import player
from lib.windows import blackoutdialog, kodigui, seekdialog
from tests.base import KodiTestCase
from tests.test_playback_transitions import Playback


class IdleDialog(seekdialog.SeekDialog):
    def __init__(self, handler):
        self.handler = handler
        self.started = True
        self.stopPlaybackOnIdle = 1200
        self.idleTime = 1
        self.timeKeeper = None
        self.sendTimeline = Mock()


class BlackoutCleanupTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.visible = set()
        self.shows = []
        self.closes = []
        self.volume = 80
        self.volumes = []
        self.showEntered = threading.Event()
        self.releaseShow = threading.Event()
        self.blockShow = False
        self.showErrors = []
        self.workers = []
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'setProperty', lambda *a: None)
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'show', lambda dialog: self.nativeShow(dialog))
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'close', lambda dialog: self.nativeClose(dialog))
        self.playback = Playback()
        self.handler = self.playback.handler
        self.handler.prePlayVolume = 80
        self.handler.getVolume = lambda: self.volume
        self.handler.setVolume = self.setVolume
        self.handler.ensureCorrectVolume = MethodType(player.SeekPlayerHandler.ensureCorrectVolume, self.handler)
        self.dialog = self.newBlackout()
        self.handler.blackoutDialog = self.dialog
        self.handler.blackout = self.handler.blackoutWasWanted = True

    def patch(self, obj, name, value):
        patcher = patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.releaseShow.set()
        for worker in self.workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        for dialog in list(self.visible):
            dialog.doClose()
        KodiTestCase.tearDown(self)

    def newBlackout(self):
        return blackoutdialog.BlackoutDialog.create(show=False)

    def setVolume(self, volume):
        self.volume = volume
        self.volumes.append(volume)

    def nativeShow(self, dialog):
        self.shows.append(dialog)
        if self.blockShow:
            self.showEntered.set()
            if not self.releaseShow.wait(2):
                raise AssertionError('cleanup did not release native show')
        self.visible.add(dialog)

    def nativeClose(self, dialog):
        self.closes.append(dialog)
        self.visible.discard(dialog)

    def startBlockedShow(self):
        self.blockShow = True

        def show():
            try:
                self.handler.start_blackout()
            except Exception as exc:
                self.showErrors.append(exc)

        worker = threading.Thread(target=show)
        self.workers.append(worker)
        worker.start()
        self.assertTrue(self.showEntered.wait(2))
        return worker

    def finishShow(self, worker):
        self.releaseShow.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.showErrors, [])

    def assertRetired(self, dialog):
        self.assertNotIn(dialog, self.visible)
        self.assertFalse(dialog.isOpen)
        shows = len(self.shows)
        dialog.show()
        self.assertEqual(len(self.shows), shows, 'a retired dialog must not reopen')

    def test_pause_timeout_stops_and_dismisses_blackout_with_stale_flags(self):
        p, h, d = self.playback, self.handler, self.dialog
        d.show()
        # Reproduce an orphan: the actual overlay is open, flags say otherwise.
        h.blackoutShown = d.isOpen = False
        self.volume = 1
        idle = IdleDialog(h)
        h.dialog = idle
        p.playerObject = object()
        p.stopAndWait = MethodType(player.PlexPlayer.stopAndWait, p)
        ended = threading.Event()
        p.on('session.ended', lambda **kw: ended.set())

        def stop():
            p.running = False
            callback = threading.Thread(target=p.onPlayBackStopped)
            self.workers.append(callback)
            callback.start()

        p.stop = stop
        ready = threading.Event()
        errors = []

        def tick():
            try:
                if not ready.wait(2):
                    raise AssertionError('timer was not installed')
                idle.onTimeKeeperCallback()
            except Exception as exc:
                errors.append(exc)
                ended.set()

        with patch.object(seekdialog.time, 'time', return_value=1202):
            timer = player.plexapp.util.RepeatingCounterTimer(0.001, tick)
            idle.timeKeeper = timer
            ready.set()
            try:
                self.assertTrue(ended.wait(2), 'idle stop did not complete')
            finally:
                timer.cancel()
                timer.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(timer.is_alive())
        self.assertIsNone(idle.timeKeeper)
        self.assertTrue(h.stoppedManually)
        self.assertTrue(h.ended)
        self.assertIsNone(p.sessionID)
        self.assertIsNone(h.blackoutDialog)
        self.assertRetired(d)
        self.assertEqual(self.volume, 80)
        idle.sendTimeline.assert_called_once_with(state=p.STATE_STOPPED)
        self.assertNotIn('1', [ENV.window_props[10000].get('script.plex.playback_started', ''),
                               ENV.window_props[10000].get('script.plex.playback_started_event', '')])

    def test_pending_show_cannot_survive_session_end_or_mute_after_cleanup(self):
        worker = self.startBlockedShow()
        self.handler.sessionEnded()
        self.assertIsNone(self.handler.blackoutDialog)
        self.finishShow(worker)
        self.assertRetired(self.dialog)
        self.assertEqual(self.volumes, [])
        self.assertFalse(self.handler.blackoutShown)
        self.assertFalse(self.handler.blackoutWasWanted)

    def test_pending_show_cannot_survive_successful_seek_cleanup(self):
        worker = self.startBlockedShow()
        self.handler.stop_blackout()
        self.finishShow(worker)
        self.assertRetired(self.dialog)
        self.assertNotIn(1, self.volumes)
        self.assertEqual(ENV.window_props[10000]['script.plex.playback_started'], '1')
        self.assertTrue(self.handler.blackoutWasWanted)

    def test_cleanup_of_old_pending_show_does_not_close_replacement_overlay(self):
        worker = self.startBlockedShow()
        self.handler.sessionEnded()
        replacement = self.newBlackout()
        self.blockShow = False
        replacement.show()
        self.finishShow(worker)
        self.assertRetired(self.dialog)
        self.assertIn(replacement, self.visible)
        self.assertNotIn(replacement, self.closes)

    def test_duplicate_show_and_late_init_cannot_revive_retired_dialog(self):
        d = self.dialog
        d.show()
        d.show()
        self.assertEqual(self.shows, [d])
        d.doClose()
        d._onInit()
        self.assertRetired(d)
        self.assertFalse(player.plexapp.util.APP.has_signal('close.dialogs', d.onCloseSignal))

    def test_retirement_during_init_removes_late_subscription(self):
        d = self.dialog
        original = kodigui.BaseDialog._onInit

        def init(dialog):
            dialog.doClose()
            original(dialog)

        with patch.object(kodigui.BaseDialog, '_onInit', init):
            d._onInit()
        self.assertFalse(player.plexapp.util.APP.has_signal('close.dialogs', d.onCloseSignal))
        self.assertRetired(d)

    def test_internal_seek_stop_keeps_blackout_until_seek_finishes(self):
        h = self.handler
        h.start_blackout()
        h.seeking = h.SEEK_IN_PROGRESS
        h.onPlayBackStopped()
        self.assertIn(self.dialog, self.visible)
        self.assertIs(h.blackoutDialog, self.dialog)
        h.stop_blackout()
        self.assertRetired(self.dialog)
        self.assertEqual(self.volume, 80)

    def test_terminal_end_and_failure_retire_without_starting_playback(self):
        for callback in ('onPlayBackEnded', 'onPlayBackFailed', 'close'):
            with self.subTest(callback=callback):
                h = self.handler
                h.ended = False
                h.blackout = h.blackoutWasWanted = True
                h.blackoutDialog = self.newBlackout()
                d = h.blackoutDialog
                h.start_blackout()
                self.playback.playerObject = SimpleNamespace(hasMoreParts=lambda: False)
                h.next = Mock(return_value=False)
                getattr(h, callback)()
                self.assertRetired(d)
                self.assertEqual(self.volume, 80)
                self.assertNotEqual(ENV.window_props[10000].get('script.plex.playback_started'), '1')

    def test_stale_handler_close_only_dismisses_its_own_overlay(self):
        old = self.handler
        old.start_blackout()
        replacement = player.SeekPlayerHandler(self.playback, 'new')
        self.playback.handler = replacement
        replacement.blackoutDialog = self.newBlackout()
        replacement.blackoutDialog.show()
        self.volume = 35
        old.close()
        self.assertRetired(self.dialog)
        self.assertIn(replacement.blackoutDialog, self.visible)
        self.assertEqual(self.volume, 35)

    def test_reset_cancels_pending_show_without_native_calls_under_startup_lock(self):
        worker = self.startBlockedShow()
        closes = len(self.closes)
        with player.VideoStartup._lock:
            self.handler.reset()
            self.assertEqual(len(self.closes), closes)
        self.finishShow(worker)
        self.assertRetired(self.dialog)
        self.assertNotIn(1, self.volumes)

    def test_reused_handler_restores_baseline_and_allocates_fresh_dialog(self):
        h = self.handler
        h.start_blackout()
        self.assertEqual(self.volume, 1)
        with player.VideoStartup._lock:
            h.reset()
        seek = SimpleNamespace(setup=Mock())
        with patch.object(h, 'getDialog', return_value=seek), \
                patch.object(player.plexapp.util, 'INTERFACE',
                             SimpleNamespace(getPlayedThresholdValue=lambda: 90)):
            h.dialog = seek
            h.setup(600000, None, 0, '')
        self.assertRetired(self.dialog)
        self.assertEqual(self.volume, 80)
        self.assertEqual(h.prePlayVolume, 80)
        self.assertIsNot(h.blackoutDialog, self.dialog)
        h.blackout = h.blackoutWasWanted = True
        h.start_blackout()
        self.assertIn(h.blackoutDialog, self.visible)
        self.assertEqual(self.volume, 1)

    def test_stop_dismisses_before_postplay_early_return(self):
        h = self.handler
        h.start_blackout()
        h.duration = 1000000
        h.playedThreshold = 90
        self.playback.video = SimpleNamespace(server=SimpleNamespace(prefs={}))
        h.getVideoPlayedFac = lambda: 0.95
        h.getVideoWatched = lambda: True
        h.next = Mock(return_value=True)
        h.onPlayBackStopped()
        h.next.assert_called_once_with(on_end=True)
        self.assertFalse(h.ended, 'post-play keeps the session alive')
        self.assertRetired(self.dialog)
        self.assertEqual(self.volume, 80)

    def test_stale_cleanup_admission_cannot_retire_reused_handlers_new_dialog(self):
        for callback in ('sessionEnded', 'onPlayBackStopped', 'onPlayBackEnded',
                         'onPlayBackFailed', 'stop_blackout'):
            with self.subTest(callback=callback):
                h, p = self.handler, self.playback
                h._videoStartup = p._videoStartup = None
                h.ended = False
                h.blackout = True
                h.blackoutDialog = self.newBlackout()
                p.sessionID = 'old'
                replacement = self.newBlackout()
                token = SimpleNamespace(finish=Mock())
                dismiss = h._dismiss_blackout

                def replace(**kwargs):
                    # Model reset/setup between callback validation and its
                    # attempt to claim the captured owner's blackout.
                    h.blackoutDialog.doClose()
                    with player.VideoStartup._lock:
                        h._videoStartup = p._videoStartup = token
                        h.blackoutDialog = replacement
                        p.sessionID = 'new'
                    replacement.show()
                    return dismiss(**kwargs)

                with patch.object(h, '_dismiss_blackout', replace):
                    getattr(h, callback)()
                self.assertIn(replacement, self.visible)
                self.assertIs(h.blackoutDialog, replacement)
                self.assertEqual(p.sessionID, 'new')
                self.assertFalse(h.ended)
                replacement.doClose()

