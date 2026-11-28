# coding=utf-8
"""Production request/seek/terminal paths own Home initialization per startup.

Kodi transport, dialog controls and Plex decisions are recording boundaries.
Real addon publication, request preparation, callbacks and cleanup run here;
this cannot establish native GUI lifetime or callback delivery on a device.
"""
from __future__ import absolute_import

import threading
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kodienv import ENV
ENV.abort_requested = True
from lib import player
from tests.base import KodiTestCase


FLAG = 'script.plex.playback_initializing'


def number(value):
    return SimpleNamespace(asInt=lambda: value)


def video():
    art = SimpleNamespace(asTranscodedImageURL=lambda *a, **kw: 'image')
    return SimpleNamespace(defaultArt=art, defaultThumb=art, type='movie', title='Movie',
                           grandparentTitle='', duration=number(600000), year=number(2020),
                           summary='', guid='imdb://test', chapters=[],
                           current_subtitle_is_embedded=False)


class Monitor(object):
    tv_standby = False

    def __init__(self):
        self.onWait = None
        self.aborted = False

    def abortRequested(self):
        return self.aborted

    def waitFor(self, seconds=None):
        return self.waitForAbort(seconds)

    def waitForAbort(self, seconds=None):
        if self.onWait:
            callback, self.onWait = self.onWait, None
            callback()
        return self.aborted

    def waitAmount(self, seconds):
        return 4


class Dialog(object):
    videoPausedForAudioStreamChange = False
    _ignoreTick = False

    def __init__(self):
        self.offset = self.selectedOffset = 0
        self.onPlayBackSeek = Mock()
        self.onAVStarted = Mock()
        self.onPlayBackStopped = Mock()
        self.onPlayBackEnded = Mock()
        self.onPlayBackFailed = Mock()
        self.update = Mock()


class Handler(player.SeekPlayerHandler):
    def setup(self, duration, meta, offset, bif_url, **kwargs):
        # Dialog setup is a native GUI boundary; reset/seek/terminal paths remain real.
        self.duration = 0  # suppress unrelated watched/post-play decisions
        self.dialog = Dialog()

    def getIntroOffset(self, *args, **kwargs):
        return self.player.intro

    def skipMarkersBefore(self, *args, **kwargs):
        pass

    def updateOffset(self, **kwargs):
        pass

    def updateNowPlaying(self, **kwargs):
        pass

    def triggerProgressEvent(self):
        pass

    def ensureCorrectVolume(self):
        pass

    def hideOSD(self, **kwargs):
        pass

    def next(self, **kwargs):
        return False

    def setSubtitles(self, **kwargs):
        pass


class Playback(player.PlexPlayer):
    def __init__(self):
        player.PlexPlayer.__init__(self)
        self.sessionID = 'session'
        self.handler = Handler(self, self.sessionID)
        self.video = video()
        self.playerObject = None
        self.started = self.running = self._closed = False
        self.ignoreStopEvents = self._ignorePlaybackFailure = False
        self.pauseAfterPlaybackStarted = False
        self.lavSettingControl = None
        self._originalAlternateSeek = False
        self.intro = None
        self.position = 0
        self.seeks = []
        self.plays = []
        self.controls = []
        self.state = self.STATE_PLAYING

    def open(self):
        self._closed = False

    def play(self, url, li):
        self.plays.append((url, ENV.window_props[10000].get(FLAG, '')))
        self.running = True

    def isPlaying(self):
        return self.running

    def isPlayingVideo(self):
        return self.running

    def isPlayingAudio(self):
        return False

    def isExternalPlayer(self):
        return False

    def getTime(self):
        return self.position

    def getTotalTime(self):
        return 600

    def seekTime(self, seconds):
        self.seeks.append(seconds)
        self.position = seconds

    def stop(self):
        self.running = False

    @property
    def playState(self):
        return self.state

    def control(self, cmd, **kwargs):
        self.controls.append(cmd)
        self.state = self.STATE_PAUSED if cmd == 'pause' else self.STATE_PLAYING


class InitializationTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.monitor = Monitor()
        self.settings = {'seek_back_on_start': True}
        self.meta = SimpleNamespace(streamUrls=['/media/movie.mkv'], path='/media/movie.mkv',
                                    playStart=120, isMapped=True, isTranscoded=False, size=100)
        self.obj = SimpleNamespace(metadata=self.meta, build=lambda: None, getBifUrl=lambda: '',
                                   getServerDecision=lambda: self.obj, hasMoreParts=lambda: False)
        for target, name, value in (
                (player.util, 'MONITOR', self.monitor),
                (player.util, 'CE_SB_LAV_SWITCH', False),
                (player.util, 'KODI_VERSION_MAJOR', 19),
                (player.util, 'getSetting', lambda key, *a, **kw: self.settings.get(key, False)),
                (player.plexplayer, 'PlexPlayer', lambda *a, **kw: self.obj)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.p = Playback()
        self.addCleanup(lambda: player.finishVideoStartup(self.p._videoStartup))

    def flag(self):
        return ENV.window_props[10000].get(FLAG, '')

    def start(self, offset=0):
        self.p._playVideo(offset=offset)
        return self.p._videoStartup

    @contextmanager
    def preparingReplacement(self):
        entered, release = threading.Event(), threading.Event()
        failures = []
        def build():
            entered.set()
            if not release.wait(2):
                raise AssertionError('replacement preparation was not released')
        def replacement():
            try:
                self.p._playVideo(offset=240000, session_id='replacement')
            except BaseException as error:
                failures.append(error)
        with patch.object(self.obj, 'build', build):
            thread = threading.Thread(target=replacement)
            thread.start()
            try:
                self.assertTrue(entered.wait(2), 'replacement did not reach preparation')
                yield self.p._preparingVideoStartup
            finally:
                release.set()
                thread.join(2)
                self.assertFalse(thread.is_alive(), 'replacement did not finish')
                self.assertEqual(failures, [])

    def test_failure_recovery_cannot_cancel_newer_pending_preparation(self):
        for event in ('onPlayBackFailed', 'onPlayBackError'):
            for boundary in ('reachability', 'notification', 'stop-entry'):
                with self.subTest(event=event, boundary=boundary):
                    self.p = Playback()
                    self.start()
                    self.p.started = True
                    self.p._pendingStaleStop = False
                    with ExitStack() as stack:
                        pending = []
                        def beginReplacement(*args, **kwargs):
                            pending.append(stack.enter_context(self.preparingReplacement()))
                        manager = SimpleNamespace(periodicReachabilityCheck=Mock())
                        stack.enter_context(patch.object(player.plexapp, 'SERVERMANAGER', manager))
                        if boundary == 'reachability':
                            manager.periodicReachabilityCheck.side_effect = beginReplacement
                        elif boundary == 'notification':
                            stack.enter_context(patch.object(player.util, 'showNotification', beginReplacement))
                        else:
                            originalStop = self.p.stopAndWait
                            def stop(*args, **kwargs):
                                if 'startup' in kwargs:
                                    beginReplacement()
                                return originalStop(*args, **kwargs)
                            stack.enter_context(patch.object(self.p, 'stopAndWait', stop))
                        getattr(self.p, event)()
                        self.assertEqual(len(pending), 1)
                        self.assertTrue(pending[0].current())
                        self.assertFalse(self.p._closed)
                    self.assertEqual(len(self.p.plays), 2)
                    self.assertEqual(self.flag(), '1')
                    self.assertEqual(self.p.sessionID, 'replacement')

    def test_explicit_stop_cancels_pending_replacement_but_old_owned_cleanup_does_not(self):
        self.start()
        old = self.p._videoStartup
        with self.preparingReplacement() as pending:
            self.p.stopAndWait(startup=old)
            self.p.close(startup=old)
            self.assertTrue(pending.current())
            self.assertFalse(self.p._closed)
            self.p.stopAndWait()
            self.assertFalse(pending.current())
        self.assertEqual(self.flag(), '')
        self.assertEqual(len(self.p.plays), 1)

    def test_full_forward_delay_return_pair_and_resume_keep_signal_until_complete(self):
        for offset in (0, 120000):
            with self.subTest(offset=offset):
                self.p.running = False
                token = self.start(offset)
                self.assertTrue(self.p.plays)
                self.assertEqual(self.p.plays[-1][1], '1')
                self.p.onAVStarted()
                self.assertEqual(self.flag(), '1', 'AVStarted must not release detector initialization')
                if not offset:
                    self.monitor.onWait = lambda: self.assertEqual(self.flag(), '1')
                    self.p.onPlayBackSeek(5000, 5000)
                    self.assertEqual(self.flag(), '1', 'forward callback must retain the complete pair')
                    self.assertTrue(self.p.handler.seekingBackTo)
                    self.assertEqual(self.p.seeks[-1], .05)
                    self.p.onPlayBackSeek(50, -4950)
                    self.assertTrue(self.p.handler.seekBackToDone)
                else:
                    self.p.onPlayBackSeek(120000, 120000)
                self.assertEqual(self.flag(), '')
                self.assertFalse(token.current())

    def test_abandoned_preplay_then_transcoded_or_no_seek_request_has_no_orphan(self):
        for transcoded in (False, True):
            with self.subTest(transcoded=transcoded):
                self.p.running = False
                self.meta.isTranscoded = False
                with patch.object(player.xbmcgui, 'ListItem', side_effect=ValueError('metadata failed')):
                    with self.assertRaises(ValueError):
                        self.start()
                self.assertEqual(self.flag(), '')
                self.assertEqual(self.p.plays, [])
                self.settings['seek_back_on_start'] = False
                self.meta.isTranscoded = transcoded
                self.start()
                self.assertEqual(len(self.p.plays), 1)
                self.assertEqual(self.p.plays[-1][1], '')
                self.p.plays[:] = []
                self.settings['seek_back_on_start'] = True

    def test_replacement_retires_signal_before_server_decision_or_build_failure(self):
        self.start()
        with patch.object(player.util, 'ERROR'), patch.object(self.obj, 'build', side_effect=ValueError('decision')):
            self.start()
        self.assertEqual(self.flag(), '')
        self.assertFalse(self.p._videoStartup.current())

    def test_outgoing_terminal_during_server_preparation_cannot_cancel_replacement(self):
        for event in ('onPlayBackStopped', 'onPlayBackEnded', 'onPlayBackError', 'onPlayBackFailed'):
            with self.subTest(event=event):
                self.p = Playback()
                self.start()
                self.p.started = True
                self.p._pendingStaleStop = False
                with patch.object(self.obj, 'build', side_effect=getattr(self.p, event)):
                    self.start(120000)
                self.assertEqual(len(self.p.plays), 2)
                self.assertEqual(self.flag(), '1')
                self.assertEqual(self.p.sessionID, 'session')
                self.assertEqual(self.p.handler.seekOnStart, 120000)

    def test_old_resume_poll_cannot_reseek_new_playback(self):
        self.start(120000)
        self.p.onAVStarted()
        self.p.position = 0  # old resume seek did not land; enter its polling path
        def replacement():
            self.meta.playStart = 240
            self.start(240000)
            self.p.position = 0
        self.monitor.onWait = replacement
        self.p.onPlayBackSeek(120000, 120000)
        self.assertEqual(self.flag(), '1')
        self.assertEqual(self.p.handler.seekOnStart, 240000)
        # One initial seek and at most one pre-replacement retry; none after it.
        self.assertEqual(self.p.seeks, [120.0, 120.0])
        self.assertEqual(self.p.position, 0)

    def test_old_alternate_seek_wait_cannot_issue_seek_for_new_playback(self):
        self.start(120000)
        self.p.handler.useAlternateSeek = True
        def replacement():
            self.meta.playStart = 240
            self.start(240000)
        self.monitor.onWait = replacement
        self.p.handler.seekAbsolute()
        self.assertEqual(self.flag(), '1')
        self.assertEqual(self.p.handler.seekOnStart, 240000)
        self.assertFalse(any(command.startswith('Seek(') for command in ENV.builtins))

    def test_ordinary_seek_after_initialization_completed_remains_usable(self):
        self.start(120000)
        self.p.onAVStarted()
        self.p.onPlayBackSeek(120000, 120000)
        self.assertEqual(self.flag(), '')
        self.p.handler.seekAbsolute(240000)
        self.assertEqual(self.p.seeks[-1], 240)
        self.p.onPlayBackSeek(240000, 120000)
        self.assertEqual(self.flag(), '')

    def test_reentrant_handler_terminal_callback_preserves_reused_startup(self):
        self.start()
        self.p.started = True
        self.p.handler.dialog.onPlayBackStopped.side_effect = lambda: self.start(120000)
        self.p._pendingStaleStop = False
        self.p.onPlayBackStopped()
        self.assertEqual(self.flag(), '1')
        self.assertEqual(self.p.sessionID, 'session')
        self.assertEqual(self.p.handler.seekOnStart, 120000)

    def test_intro_and_alternate_resume_sequences_release_only_after_seek(self):
        self.p.intro = 45000
        self.start()
        self.p.onAVStarted()
        self.assertEqual(self.flag(), '1')
        self.assertEqual(self.p.seeks, [45.0])
        self.p.onPlayBackSeek(45000, 45000)
        self.assertEqual(self.flag(), '')
        self.p.intro = None
        self.start(120000)
        self.p.handler.useAlternateSeek = self.p.handler.useResumeFix = True
        self.p.onAVStarted()
        self.assertEqual(self.flag(), '1')
        self.p.position = 120
        self.p.onPlayBackSeek(120000, 120000)
        self.assertEqual(self.flag(), '')

    def test_stop_before_submission_clears_without_kodi_playing(self):
        self.p.on('starting.video', lambda **kw: self.p.stopAndWait())
        self.start()
        self.assertEqual(self.flag(), '')
        self.assertEqual(self.p.plays, [])

    def test_submission_exception_and_abort_retire_the_owned_startup(self):
        with patch.object(self.p, 'play', side_effect=RuntimeError('Kodi failed')):
            with self.assertRaises(RuntimeError):
                self.start()
        self.assertEqual(self.flag(), '')
        self.p.on('starting.video', lambda **kw: setattr(self.monitor, 'aborted', True))
        self.start()
        self.assertEqual(self.flag(), '')
        self.assertEqual(self.p.plays, [])

    def test_old_preparation_finally_cannot_clear_reentrant_new_startup(self):
        def replacement(**kwargs):
            self.p.off('starting.video', replacement)
            self.start(120000)
            raise ValueError('old preparation abandoned')
        self.p.on('starting.video', replacement)
        with self.assertRaises(ValueError):
            self.start()
        self.assertEqual(self.flag(), '1')
        self.assertEqual(len(self.p.plays), 1)

    def test_stale_handler_cleanup_and_token_cannot_clear_new_startup(self):
        old = self.start()
        old_handler = self.p.handler
        self.p.handler = Handler(self.p, self.p.sessionID)
        self.start(120000)
        old.finish()
        old_handler.reset()
        old_handler.close()
        old_handler.sessionEnded()
        self.assertEqual(self.flag(), '1')
        self.assertTrue(self.p._videoStartup.current())

    def test_delayed_old_forward_callback_cannot_seek_or_clear_reused_handler(self):
        self.start()
        self.p.onAVStarted()
        def replacement():
            self.start(120000)  # same handler, new immutable request identity
        self.monitor.onWait = replacement
        self.p.onPlayBackSeek(5000, 5000)
        self.assertEqual(self.flag(), '1')
        self.assertEqual(self.p.handler.seekOnStart, 120000)
        self.assertEqual(self.p.seeks, [5.0], 'obsolete return seek must not run')

    def test_stale_terminal_fence_preserves_new_flag_and_current_terminal_clears(self):
        for event in ('onPlayBackStopped', 'onPlayBackEnded', 'onPlayBackError'):
            with self.subTest(event=event):
                self.p.sessionID = 'session'
                self.p.started = True
                self.p.ignoreStopEvents = False
                self.start()
                self.p._pendingStaleStop = True
                getattr(self.p, event)()
                self.assertEqual(self.flag(), '1')
                self.p.running = False
                with patch.object(player.plexapp, 'SERVERMANAGER',
                                  SimpleNamespace(periodicReachabilityCheck=Mock())):
                    getattr(self.p, event)()
                self.assertEqual(self.flag(), '')

    def test_failure_listener_starting_new_request_is_not_cleaned_by_old_callback(self):
        for event in ('onPlayBackFailed', 'onPlayBackError'):
            with self.subTest(event=event):
                self.p.sessionID = 'session'
                self.p.ignoreStopEvents = False
                self.start()
                self.p._pendingStaleStop = False
                def replacement(**kw):
                    self.p.off('playback.failed', replacement)
                    self.start(120000)
                self.p.on('playback.failed', replacement)
                getattr(self.p, event)()
                self.assertEqual(self.flag(), '1')
                self.assertFalse(self.p._closed)

    def test_owned_reset_close_session_and_stop_clear_even_without_native_playback(self):
        for method in ('stopAndWait', 'close', 'reset', 'init'):
            with self.subTest(method=method):
                self.p = Playback()
                self.start()
                self.p.running = False
                with patch.object(self.p, 'monitor'):
                    getattr(self.p, method)()
                self.assertEqual(self.flag(), '')
        for method in ('reset', 'close', 'sessionEnded', 'onPlayBackFailed'):
            with self.subTest(handler=method):
                self.p = Playback()
                self.start()
                getattr(self.p.handler, method)()
                self.assertEqual(self.flag(), '')

    def test_seek_without_callback_or_seek_exception_retires_initialization(self):
        for mode in ('external', 'bad-offset', 'not-playing', 'tiny-alternate', 'exception'):
            with self.subTest(mode=mode):
                self.p = Playback()
                self.start()
                h = self.p.handler
                if mode == 'external':
                    self.p.isExternal = True
                elif mode == 'bad-offset':
                    h.seekOnStart = 1000000
                elif mode == 'not-playing':
                    self.p.getTotalTime = Mock(side_effect=RuntimeError('not ready'))
                elif mode == 'tiny-alternate':
                    h.useAlternateSeek = True
                    self.p.position = h.seekOnStart / 1000.0
                elif mode == 'exception':
                    self.p.seekTime = Mock(side_effect=RuntimeError('seek failed'))
                if mode == 'exception':
                    with self.assertRaises(RuntimeError):
                        h.seekAbsolute()
                else:
                    h.seekAbsolute()
                self.assertEqual(self.flag(), '')
