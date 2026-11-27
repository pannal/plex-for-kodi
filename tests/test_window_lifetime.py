# coding=utf-8
"""Production subscription/close paths must release transient Kodi windows.

Weak references check Python ownership. Recording GUI boundaries and controlled
timer interleavings do not prove Kodi native lifetime or callback scheduling.
"""
from __future__ import absolute_import

import gc
import threading
import weakref
from types import SimpleNamespace
from unittest.mock import patch

from kodienv import ENV
ENV.abort_requested = True
from lib import player, util
from lib.windows import busy, currentplaylist, episodes, home, kodigui, opener, photos, seekdialog
from plexnet import plexapp
from plexnet.signalsmixin import SignalsMixin
from tests.base import KodiTestCase, ensure_plex_interface
from tests.test_playback_return import EpisodeScreen
from tests.test_playback_transitions import Playback


def noop(*args, **kwargs):
    pass


class MusicScreen(currentplaylist.CurrentPlaylistWindow):
    setupSeekbar = fillPlaylist = selectPlayingItem = setFocusId = noop

    def updateProperties(self, **kwargs):
        pass


class PhotoScreen(photos.PhotoWindow):
    showPhoto = pause = noop

    def updateProperties(self, **kwargs):
        pass

    def fillPqueueList(self, **kwargs):
        pass


class WindowLifetimeTest(KodiTestCase):
    def setUp(self):
        super(WindowLifetimeTest, self).setUp()
        ensure_plex_interface()
        self.app = SignalsMixin()
        self.bus = SignalsMixin()
        self.monitor = SignalsMixin()
        self.patch(plexapp.util, 'APP', self.app)
        self.patch(plexapp, 'ACCOUNT', SimpleNamespace(hasPlexPass=lambda: False))
        self.patch(player, 'PLAYER', self.bus)
        self.patch(util, 'MONITOR', self.monitor)
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'setProperty', noop)

    def patch(self, obj, name, value):
        patcher = patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertCollected(self, refs):
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))

    def assertNoSubscribers(self, emitter):
        self.assertFalse(any(signal.slots for signal in emitter._signals.values()))

    def seekDialog(self, server):
        handler = SimpleNamespace(player=SimpleNamespace(video=SimpleNamespace(server=server)),
                                  playlist=None, useAlternateSeek=False)
        return seekdialog.SeekDialog.create(show=False, handler=handler)

    def test_repeated_seek_dialogs_collect_after_final_close(self):
        server, refs = SignalsMixin(), []
        for _ in range(5):
            dialog = self.seekDialog(server)
            refs.append(weakref.ref(dialog))
            dialog.doClose(delete=True)
            dialog.doClose(delete=True)
            del dialog
        self.assertCollected(refs)
        self.assertNoSubscribers(server)

    def test_seek_hide_keeps_callbacks_final_close_uses_original_server(self):
        original, replacement = SignalsMixin(), SignalsMixin()
        dialog = self.seekDialog(original)
        dialog.doClose(delete=False)
        self.assertTrue(original.has_signal('np:streamTerminated', dialog.streamTerminatedCallback))
        response = SimpleNamespace(getBodyXml=lambda: 'active response')
        original.trigger('np:timelineResponse', response=response)
        self.assertEqual(dialog.lastTimelineResponse, 'active response')
        dialog.player.video.server = replacement
        replacement.on('np:timelineResponse', noop)
        dialog.doClose(delete=True)
        self.assertNoSubscribers(original)
        self.assertTrue(replacement.has_signal('np:timelineResponse', noop))
        # A dispatcher may already have copied a bound callback before off().
        dialog.timelineResponseCallback(response=SimpleNamespace(getBodyXml=lambda: 'stale'))
        dialog.streamTerminatedCallback(reason='stale')
        self.assertEqual(dialog.lastTimelineResponse, 'active response')
        self.assertFalse(dialog._terminated)

    def episodeWindow(self):
        win = EpisodeScreen(SimpleNamespace(uuid='server'))
        win.initialEpisode = SimpleNamespace(reload=noop)
        win.started = False
        win.startOver = False
        win.playButtonClicked = lambda **kw: True
        return win

    def test_repeated_blind_autoplay_releases_episode_windows(self):
        self.patch(episodes, 'autoRemoveFromWatchlist', noop)
        refs = []
        for _ in range(5):
            win = self.episodeWindow()
            win.doAutoPlay()
            self.assertTrue(self.bus.has_signal('video.progress', win.onVideoProgress))
            refs.append(weakref.ref(win))
            win.onBlindClose()
            win.onBlindClose()
            del win
        self.assertNoSubscribers(self.bus)
        self.assertCollected(refs)

    def test_episode_cleanup_uses_original_player_and_ignores_stale_events(self):
        self.patch(episodes, 'autoRemoveFromWatchlist', noop)
        win = self.episodeWindow()
        win.doAutoPlay()
        original_episode = win.episode
        with patch.object(player, 'PLAYER', SignalsMixin()):
            win.onBlindClose()
        win.onNewVideo(video=SimpleNamespace(type='episode'))
        self.assertIs(win.episode, original_episode)
        self.assertNoSubscribers(self.bus)

    def test_blind_autoplay_failure_also_removes_hooks(self):
        self.patch(episodes, 'autoRemoveFromWatchlist', noop)
        self.patch(util, 'ERROR', noop)
        refs = []

        def fail(**kwargs):
            raise RuntimeError('play preparation failed')

        def create(**kwargs):
            win = self.episodeWindow()
            win.playButtonClicked = fail
            refs.append(weakref.ref(win))
            return win

        with patch.object(episodes.EpisodesWindow, 'create', create):
            for show_after in (False, True):
                opener.handleOpen(episodes.EpisodesWindow, auto_play=True, auto_play_open=show_after)
        self.assertNoSubscribers(self.bus)
        self.assertCollected(refs)

    def setupHandler(self, playback):
        handler = playback.handler
        handler.getVolume = lambda: 80
        handler.dialog = SimpleNamespace(setup=noop)
        handler.setup(10000, None, 0, None)
        return handler

    def test_repeated_handler_sessions_release_exit_hook_and_blackout(self):
        refs = []
        for _ in range(5):
            playback = Playback()
            handler = self.setupHandler(playback)
            refs.extend((weakref.ref(handler), weakref.ref(handler.blackoutDialog)))
            self.assertTrue(self.monitor.has_signal('system.exit', handler.onKodiExit))
            handler.sessionEnded()
            self.assertIsNone(handler.blackoutDialog)
            handler.close()
            playback.handler = None
            del handler, playback
        self.assertNoSubscribers(self.monitor)
        self.assertCollected(refs)

    def test_replaced_handler_is_not_owned_by_monitor_without_terminal_callback(self):
        playback = Playback()
        handler = playback.handler
        handler._hookExit()
        ref = weakref.ref(handler)
        playback.handler = None
        del handler
        self.assertCollected([ref])
        self.assertNoSubscribers(self.monitor)

    def test_exit_hook_removes_from_original_monitor(self):
        playback = Playback()
        handler = playback.handler
        handler._hookExit()
        with patch.object(util, 'MONITOR', SignalsMixin()):
            player.BasePlayerHandler.close(handler)
        self.assertNoSubscribers(self.monitor)

    def test_exit_hook_runs_for_current_owner_but_not_retired_handler(self):
        playback = Playback()
        handler = playback.handler
        reports = []
        handler.updateNowPlaying = lambda **kw: reports.append(kw['state'])
        self.app.nowplayingmanager = SimpleNamespace(reset=noop)
        handler._hookExit()
        self.monitor.trigger('system.exit')
        self.assertEqual(reports, [playback.STATE_STOPPED])
        self.assertTrue(handler.ignoreTimelines)
        self.assertNoSubscribers(self.monitor)
        handler._hookExit()
        playback.handler = None
        self.monitor.trigger('system.exit')
        self.assertEqual(len(reports), 1)
        self.assertNoSubscribers(self.monitor)

    def test_session_listener_reusing_handler_keeps_new_dialog_and_exit_hook(self):
        playback = Playback()
        handler = self.setupHandler(playback)
        new_startup = SimpleNamespace(finish=noop)

        def restart(**kwargs):
            handler._videoStartup = playback._videoStartup = new_startup
            self.setupHandler(playback)

        playback.on('session.ended', restart)
        handler.sessionEnded()
        self.assertIsNotNone(handler.dialog)
        self.assertIsNotNone(handler.blackoutDialog)
        self.assertTrue(self.monitor.has_signal('system.exit', handler.onKodiExit))
        handler.close()

    def test_audio_finish_unhooks_and_next_track_hooks_again(self):
        playback = SimpleNamespace(isPlayingAudio=lambda: False, trigger=noop)
        handler = player.AudioPlayerHandler(playback)
        playback.handler = handler
        handler.setup()
        handler.finish()
        self.assertNoSubscribers(self.monitor)
        handler.updatePlayQueue = handler.extractTrackInfo = handler.updateNowPlaying = noop
        handler.onPlayBackStarted()
        self.assertTrue(self.monitor.has_signal('system.exit', handler.onKodiExit))
        handler.onPlayBackFailed()
        self.assertNoSubscribers(self.monitor)

    def test_session_end_yield_does_not_unhook_replacement_startup(self):
        playback = Playback()
        handler = self.setupHandler(playback)
        restores = []
        new_startup = SimpleNamespace(finish=noop)

        def restore():
            restores.append(True)
            if len(restores) == 2:
                handler._videoStartup = playback._videoStartup = new_startup
                self.setupHandler(playback)
                playback.sessionID = 'replacement'

        handler.ensureCorrectVolume = restore
        handler.sessionEnded()
        self.assertEqual(playback.sessionID, 'replacement')
        self.assertFalse(handler.ended)
        self.assertIsNotNone(handler.dialog)
        self.assertTrue(self.monitor.has_signal('system.exit', handler.onKodiExit))
        handler.close()

    def test_home_hook_unhook_is_balanced_across_recreation(self):
        manager, refs = SignalsMixin(), []
        self.patch(plexapp, 'SERVERMANAGER', manager)
        for _ in range(5):
            win = home.HomeWindow.__new__(home.HomeWindow)
            win.hookSignals()
            win.unhookSignals()
            refs.append(weakref.ref(win))
            del win
        for emitter in (manager, self.app, self.bus, self.monitor):
            self.assertNoSubscribers(emitter)
        self.assertCollected(refs)

    def test_playlist_close_unhooks_original_queue_after_handler_switch(self):
        old, new = SignalsMixin(), SignalsMixin()
        old.isRemote = new.isRemote = True
        self.bus.handler = SimpleNamespace(playQueue=old)
        self.patch(kodigui, 'ManagedControlList', lambda *a: None)
        win = MusicScreen.__new__(MusicScreen)
        win.isOpen = True
        win.onFirstInit()
        self.assertTrue(old.has_signal('change', win.updateProperties))
        self.bus.handler = SimpleNamespace(playQueue=new)
        new.on('change', noop)
        win.doClose()
        win.doClose()
        ref = weakref.ref(win)
        del win
        self.assertNoSubscribers(old)
        self.assertNoSubscribers(self.bus)
        self.assertTrue(new.has_signal('change', noop))
        self.assertCollected([ref])

    def test_photo_close_unhooks_surviving_queue_and_closes_timer(self):
        queue, timer_calls = SignalsMixin(), []
        win = PhotoScreen.__new__(PhotoScreen)
        win.isOpen = True
        win._closing = False
        win.tempFolder = self.mktemp()
        win.playQueue = queue
        win.osdTimer = SimpleNamespace(close=lambda: timer_calls.append('close'))
        win.getPlayQueue()
        win.doClose()
        win.doClose()
        self.assertEqual(timer_calls, ['close'])
        ref = weakref.ref(win)
        del win
        self.assertNoSubscribers(queue)
        self.assertCollected([ref])

    def test_photo_callbacks_after_close_do_not_access_gui_or_models(self):
        win = photos.PhotoWindow.__new__(photos.PhotoWindow)
        win._closing = True
        # No controls/models: any access to them would fail this replay.
        win.fillPqueueList()
        win.updateProperties()
        win.osdTimerCallback()
        win._reallyShowPhoto(None, None, None)

    def test_busy_close_waits_for_inflight_show_before_final_dismissal(self):
        entered, release, cancelling = threading.Event(), threading.Event(), threading.Event()
        visible, refs, errors = set(), [], []
        real_timer = threading.Timer

        class Timer(real_timer):
            def cancel(self):
                cancelling.set()
                super(Timer, self).cancel()

        class DelayedBusy(busy.BusyWindow):
            def __init__(self, *args, **kwargs):
                super(DelayedBusy, self).__init__(*args, **kwargs)
                refs.append(weakref.ref(self))

            def show(self):
                entered.set()
                if not release.wait(2):
                    errors.append('show barrier timed out')
                    return
                super(DelayedBusy, self).show()

        def show(win):
            visible.add(id(win))
            win._onInit()

        def close(win):
            visible.discard(id(win))

        self.patch(busy, 'BusyWindow', DelayedBusy)
        self.patch(threading, 'Timer', Timer)
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'show', show)
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'close', close)

        @busy.dialog(delay=True, delay_time=0)
        def work():
            if not entered.wait(2):
                raise AssertionError('timer did not enter show')

        def run():
            try:
                work()
            except Exception as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(cancelling.wait(2))
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(visible, set())
        self.assertNoSubscribers(self.app)
        self.assertCollected(refs)

    def test_busy_body_exception_still_closes_and_unhooks(self):
        refs = []

        def create(**kwargs):
            win = busy.BusyWindow.__new__(busy.BusyWindow)
            kodigui.BaseDialog.__init__(win)
            win._onInit()
            refs.append(weakref.ref(win))
            return win

        with patch.object(busy.BusyWindow, 'create', create):
            @busy.dialog(delay=False)
            def fail():
                raise ValueError('expected')
            with self.assertRaises(ValueError):
                fail()
        self.assertNoSubscribers(self.app)
        self.assertCollected(refs)
