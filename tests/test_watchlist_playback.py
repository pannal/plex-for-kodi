# coding=utf-8
"""Autoplay cleanup uses the complete playlist baseline and this session's events."""
from __future__ import absolute_import

from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from kodienv import ENV
ENV.abort_requested = True
from lib import playback_sync
from lib.windows import episodes, preplay
from lib.windows.mixins import watchlist
from lib.windows.mixins.playbackreturn import PlaybackReturnMixin
from plexnet import video

from .base import KodiTestCase, ensure_plex_interface


class WatchlistPlaybackTest(KodiTestCase):
    def setUp(self):
        super(WatchlistPlaybackTest, self).setUp()
        ensure_plex_interface()
        self.auto_remove = True
        self.use_watchlist = True
        self.server = SimpleNamespace(uuid='server', query=Mock(side_effect=AssertionError('unexpected PMS read')))
        self.player = SimpleNamespace(video=None)
        self.scope = ('account', 'profile', 'token', False)
        self.revision = 0
        self.removal = Mock()
        get_setting = episodes.util.getSetting
        patches = [
            patch.object(playback_sync, 'accountScope', side_effect=lambda: self.scope),
            patch.object(playback_sync, 'readRevision', side_effect=lambda server: self.revision),
            patch.object(episodes.player, 'PLAYER', self.player),
            patch.object(episodes.util, 'getSetting', side_effect=lambda key, *a, **kw:
                         True if key == 'assume_resume' else get_setting(key, *a, **kw)),
            patch.object(watchlist.util, 'getUserSetting', side_effect=self.setting),
            patch.object(watchlist.pnUtil, 'ACCOUNT', SimpleNamespace(isOffline=False)),
            patch.object(watchlist, 'removeFromWatchlistBlind', self.removal),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(episodes.VIDEO_PROGRESS.clear)

    def setting(self, key, default=None):
        return {'watchlist_auto_remove': self.auto_remove, 'use_watchlist': self.use_watchlist,
                'preplay_preroll': False, 'preplay_trailers': 5}.get(key, default)

    def episode(self, key, viewed=False, offset=0, season='season'):
        data = ET.Element('Video', type='episode', ratingKey=key, key='/library/metadata/' + key,
                          grandparentRatingKey='show', parentRatingKey=season,
                          viewCount='1' if viewed else '0', viewOffset=str(offset))
        item = video.Episode(data, server=self.server)
        item.available = Mock(return_value=True)
        return item

    def episode_window(self, items, leaf_count=None):
        win = episodes.EpisodesWindow.__new__(episodes.EpisodesWindow)
        PlaybackReturnMixin.__init__(win)
        win._watchlistPlayback = None
        win.show_ = video.Show(ET.Element('Directory', type='show', ratingKey='show',
                                         key='/library/metadata/show/children', guid='plex://show/example',
                                         leafCount=str(len(items) if leaf_count is None else leaf_count),
                                         viewedLeafCount=str(len(items))), server=self.server)
        win.show_.all = Mock(return_value=items)
        win.season = SimpleNamespace(ratingKey='season')
        win.openedWithAutoPlay = True
        win.started = False
        win._returnRefreshFailed = False
        win.playBtnClicked = False
        win.useBGM = False
        win.dialogProps = {}
        win.processCommand = Mock()
        return win

    def emit(self, win, item, state):
        self.player.video = item
        win.onVideoProgress(data=(str(item.grandparentRatingKey), str(item.parentRatingKey),
                                  str(item.ratingKey), state))

    def play(self, win, selected, events):
        def playback(**kwargs):
            for item, state in events:
                self.emit(win, item, state)
            return ''
        with patch.object(episodes.videoplayer, 'play', side_effect=playback):
            self.assertTrue(win.episodeListClicked(force_episode=selected, from_auto_play=True))

    def finish(self, win):
        win.onBlindClose()
        self.server.query.assert_not_called()

    def test_watching_one_episode_keeps_show_with_other_unwatched_episodes(self):
        first, last = self.episode('first'), self.episode('last')
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_binge_across_seasons_completes_show_without_pms_read(self):
        first, last = self.episode('first'), self.episode('last', season='next-season')
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True), (last, True)])
        self.finish(win)
        self.removal.assert_called_once_with(win.show_.guid, win.show_)

    def test_rewatch_completion_does_not_count_as_another_watched_episode(self):
        first, last = self.episode('first', viewed=True), self.episode('last')
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True), (first, True)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_other_in_progress_rewatch_blocks_removal(self):
        first, last = self.episode('first'), self.episode('last', viewed=True, offset=120000)
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_finishing_rewatch_clears_its_initial_offset(self):
        first, last = self.episode('first', viewed=True, offset=120000), self.episode('last', viewed=True)
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True)])
        self.finish(win)
        self.removal.assert_called_once()

    def test_latest_progress_wins_over_earlier_completion(self):
        first = self.episode('first')
        win = self.episode_window([first])
        self.play(win, first, [(first, True), (first, 120000)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_incomplete_playback_does_not_make_unwatched_episode_complete(self):
        for offset in (0, 30000, 120000):
            with self.subTest(offset=offset):
                first = self.episode('first')
                win = self.episode_window([first])
                self.play(win, first, [(first, offset)])
                self.finish(win)
                self.removal.assert_not_called()

    def test_stale_global_progress_and_stale_show_counts_do_not_trigger_removal(self):
        first = self.episode('first')
        win = self.episode_window([first])
        episodes.VIDEO_PROGRESS['show'] = {'season': {'first': True}}
        self.play(win, first, [])
        self.finish(win)
        self.removal.assert_not_called()

    def test_playlist_model_mutation_cannot_change_captured_baseline(self):
        first, last = self.episode('first'), self.episode('last')
        win = self.episode_window([first, last])
        self.play(win, first, [(first, True)])
        last.set('viewCount', 1)
        self.finish(win)
        self.removal.assert_not_called()

    def test_selected_reloaded_episode_replaces_stale_playlist_copy_before_snapshot(self):
        stale, last = self.episode('first', viewed=True), self.episode('last', viewed=True)
        selected = self.episode('first')
        win = self.episode_window([stale, last])
        self.play(win, selected, [(selected, 0)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_incomplete_or_duplicate_playlist_never_proves_show_complete(self):
        for reason in ('partial', 'duplicate', 'zero', 'foreign_server', 'foreign_show'):
            with self.subTest(reason=reason):
                first, last = self.episode('first'), self.episode('last', viewed=True)
                items = [first, last]
                count = 3 if reason == 'partial' else 0 if reason == 'zero' else 2
                if reason == 'duplicate':
                    items = [first, first]
                elif reason == 'foreign_server':
                    last.server = SimpleNamespace(uuid='other')
                elif reason == 'foreign_show':
                    last.set('grandparentRatingKey', 'other')
                win = self.episode_window(items, leaf_count=count)
                self.play(win, first, [(first, True)])
                self.finish(win)
                self.removal.assert_not_called()

    def test_unknown_episode_invalidates_session_coverage(self):
        first, unknown = self.episode('first', viewed=True), self.episode('unknown')
        win = self.episode_window([first])
        self.play(win, first, [(unknown, True)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_malformed_cleanup_metadata_does_not_interrupt_playback(self):
        for field in ('leafCount', 'viewCount', 'viewOffset'):
            with self.subTest(field=field):
                first, last = self.episode('first'), self.episode('last')
                win = self.episode_window([first, last])
                (win.show_ if field == 'leafCount' else last).set(field, 'unknown')
                self.play(win, first, [(first, True)])
                self.finish(win)
                self.removal.assert_not_called()

    def test_cleanup_consumes_completion_once(self):
        first = self.episode('first')
        win = self.episode_window([first])
        self.play(win, first, [(first, True)])
        self.finish(win)
        self.finish(win)
        self.removal.assert_called_once()

    def test_mismatched_current_video_cannot_complete_another_episode(self):
        first, last = self.episode('first', viewed=True), self.episode('last')
        win = self.episode_window([first, last])
        self.play(win, first, [])
        self.player.video = first
        win.onVideoProgress(data=('show', 'season', 'last', True))
        self.finish(win)
        self.removal.assert_not_called()

    def test_foreign_server_event_does_not_complete_our_episode(self):
        first = self.episode('first')
        other = self.episode('first')
        other.server = SimpleNamespace(uuid='other')
        win = self.episode_window([first])
        self.play(win, first, [(other, True)])
        self.finish(win)
        self.removal.assert_not_called()

    def test_settings_and_changed_account_or_manual_revision_block_removal(self):
        for reason in ('disabled', 'hidden', 'offline', 'account', 'revision'):
            with self.subTest(reason=reason):
                self.auto_remove = reason != 'disabled'
                self.use_watchlist = reason != 'hidden'
                watchlist.pnUtil.ACCOUNT.isOffline = reason == 'offline'
                first = self.episode('first')
                win = self.episode_window([first])
                self.play(win, first, [(first, True)])
                if reason == 'account':
                    self.scope = ('other', 'profile', 'token', False)
                elif reason == 'revision':
                    self.revision += 1
                self.finish(win)
                self.removal.assert_not_called()

    def test_shuffle_with_full_show_baseline_tracks_session(self):
        first, last = self.episode('first'), self.episode('last')
        win = self.episode_window([first, last])
        win.season = None
        def playback(**kwargs):
            self.emit(win, first, True)
            self.emit(win, last, True)
        with patch.object(episodes.videoplayer, 'play', side_effect=playback):
            self.assertTrue(win.playButtonClicked(shuffle=True))
        self.finish(win)
        self.removal.assert_called_once()

    def movie_window(self):
        win = preplay.PrePlayWindow.__new__(preplay.PrePlayWindow)
        PlaybackReturnMixin.__init__(win)
        win.video = video.Movie(ET.Element('Video', type='movie', ratingKey='movie',
                                           key='/library/metadata/movie', guid='plex://movie/example',
                                           viewCount='1', viewOffset='0'), server=self.server)
        win.video.available = Mock(return_value=True)
        win._watchlistPlaybackScope = None
        win._setupProgressHook = Mock()
        win._removeProgressHook = Mock()
        win.playBtnClicked = False
        win.startOver = False
        win.useBGM = False
        win.openedWithAutoPlay = True
        win.started = False
        win.processCommand = Mock()
        return win

    def test_movie_cleanup_uses_session_completion_and_respects_preference(self):
        for state, enabled, remove in ((True, True, True), (True, False, False),
                                       (120000, True, False), (0, True, False), (None, True, False)):
            with self.subTest(state=state, enabled=enabled):
                self.auto_remove = enabled
                self.removal.reset_mock()
                win = self.movie_window()
                def playback(**kwargs):
                    if state is not None:
                        self.player.video = win.video
                        win.onVideoProgress(data=(None, None, 'movie', state))
                with patch.object(preplay.videoplayer, 'play', side_effect=playback):
                    self.assertTrue(win.playVideo(from_auto_play=True))
                self.finish(win)
                self.assertEqual(int(remove), self.removal.call_count)
                win._removeProgressHook.assert_called_once()

    def test_movie_account_change_blocks_old_session_removal(self):
        win = self.movie_window()
        def playback(**kwargs):
            self.player.video = win.video
            win.onVideoProgress(data=(None, None, 'movie', True))
        with patch.object(preplay.videoplayer, 'play', side_effect=playback):
            win.playVideo(from_auto_play=True)
        self.scope = ('other', 'profile', 'token', False)
        self.finish(win)
        self.removal.assert_not_called()

    def test_movie_cleanup_consumes_completion_once(self):
        win = self.movie_window()
        def playback(**kwargs):
            self.player.video = win.video
            win.onVideoProgress(data=(None, None, 'movie', True))
        with patch.object(preplay.videoplayer, 'play', side_effect=playback):
            win.playVideo(from_auto_play=True)
        self.finish(win)
        self.finish(win)
        self.removal.assert_called_once()
