# coding=utf-8
"""Playback returns keep local progress while detached I/O runs off the GUI owner."""
from __future__ import absolute_import

import copy
import threading
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
from six.moves.queue import Queue

from kodienv import ENV
ENV.abort_requested = True
from lib import playback_sync
from lib.windows import busy, episodes, preplay, kodigui
from lib.windows.mixins.playbackreturn import PlaybackReturnMixin
from lib.windows.mixins import common
from plexnet import plexobjects, video
from tests.base import KodiTestCase, fixture, ensure_plex_interface


SCOPE = ('account', 'profile', 'token', False)


def model(server, key='1234', kind='movie'):
    data = ET.fromstring(fixture('plexnet', 'movie.xml'))[0]
    data.set('ratingKey', key)
    data.set('key', '/library/metadata/' + key)
    data.set('type', kind)
    if kind == 'episode':
        data.set('grandparentRatingKey', 'show')
        data.set('parentRatingKey', 'season')
        data.set('parentIndex', '1')
        data.set('index', '1' if key == 'e1' else '2')
    cls = video.Movie if kind == 'movie' else video.Episode
    return cls(data, initpath='/library/metadata/' + key, server=server)


class MovieScreen(preplay.PrePlayWindow):
    def __init__(self, item):
        PlaybackReturnMixin.__init__(self)
        self.video = item
        self.fromPlayback = True
        self._closing = False
        self.isOpen = True
        self._winID = 13020
        self.wl_enabled = False
        self.is_watchlisted = False
        self._progressHooked = False
        self._watchlistPlaybackScope = None
        self.props = {}
        self.refreshed = []
        self.themeMusicReinit = Mock()
        self.checkIsWatchlisted = Mock()
        self.wl_auto_remove = Mock(return_value=False)
        self.relatedPaginator = None

    def refreshInfo(self, **kwargs):
        self.refreshed.append((threading.current_thread().ident,
                               self.video.isFullyWatched, self.video.viewOffset.asInt()))

    def setProperty(self, key, value):
        self.props[key] = value


class Item(object):
    def __init__(self, source, pos):
        self.dataSource = source
        self.props = {}
        self.position = pos

    def setProperty(self, key, value):
        self.props[key] = value

    def pos(self):
        return self.position


class Items(list):
    def __init__(self, *args):
        list.__init__(self, *args)
        self.selected = 0

    def getSelectedItem(self):
        return self[self.selected]

    def isLastItem(self, item):
        return item is self[-1]

    def selectItem(self, pos):
        self.selected = pos

    def getSelectedPos(self):
        return self.selected


class EpisodeScreen(episodes.EpisodesWindow):
    def __init__(self, server):
        PlaybackReturnMixin.__init__(self)
        self._closing = self.closing = False
        self._returnRefreshFailed = False
        self._watchlistPlayback = None
        self.isOpen = True
        self._winID = 13020
        self.wl_enabled = False
        self.is_watchlisted = False
        self.show_ = video.Show(ET.fromstring('<Directory type="show" ratingKey="show" key="/library/metadata/show/children" leafCount="2" viewedLeafCount="0"/>'),
                                initpath='/library/metadata/show/children', server=server)
        self.season = SimpleNamespace(ratingKey='season', isFullyWatched=False, index='1')
        self.episodeListControl = Items([Item(model(server, 'e1', 'episode'), 0), Item(model(server, 'e2', 'episode'), 1)])
        self.episode = self.episodeListControl[0].dataSource
        self.episodesPaginator = SimpleNamespace(setEpisode=Mock())
        self.manuallySelected = self.manuallySelectedSeason = self.hadUserInteraction = False
        self.cameFrom = None
        self.tasks = [SimpleNamespace(finished=True)]
        self.noRatings = False
        self.themeMusicReinit = Mock()
        self.setUserItemInfo = Mock()
        self.selectPlayButton = Mock()
        self.setProgress = Mock()
        self.setCondFocusId = Mock()
        self.checkIsWatchlisted = Mock()
        self.postpone_simple = Mock()
        self.props = {}
        self._reloadItem = Mock()

    def setProperty(self, key, value):
        self.props[key] = value


class PlaybackReturnTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ensure_plex_interface()
        ENV.current_window_id = 13020
        self.jobs = []
        self.patches = [
            patch.object(playback_sync, 'accountScope', return_value=SCOPE),
            patch.object(playback_sync, 'cacheURLs', return_value=()),
            patch.object(playback_sync, '_PENDING', self.jobs),
            patch.object(playback_sync, '_READ_REVISIONS', {}),
            patch.object(playback_sync, '_PROGRESS_REVISIONS', {}),
            patch.object(playback_sync.PlaybackReturnJob, 'start', lambda job: self.jobs.append(job)),
            patch.object(busy.BusyWindow, 'create', return_value=SimpleNamespace(doClose=Mock(), show=Mock())),
            patch.object(busy.threading, 'Timer', return_value=SimpleNamespace(start=Mock(), is_alive=lambda: False)),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.server = SimpleNamespace(uuid='server', query=Mock(side_effect=AssertionError('network on GUI owner')))
        self.screen = MovieScreen(model(self.server))
        self.addCleanup(episodes.VIDEO_PROGRESS.clear)

    def queue_metadata(self, screen=None, **attrs):
        screen = screen or self.screen
        item = screen.video
        data = copy.deepcopy(item.data)
        data.attrib.update({k: str(v) for k, v in attrs.items()})
        screen._returnResults.put((screen._returnGeneration, SCOPE, 'metadata', {str(item.ratingKey): data}))

    def test_movie_consumes_its_progress_event_and_returns_watched_without_network(self):
        with patch.object(preplay.player, 'PLAYER', SimpleNamespace(video=self.screen.video)):
            self.screen.onVideoProgress(data=(None, None, '1234', True))
        self.screen.onReInit()
        self.server.query.assert_not_called()
        self.assertEqual(self.screen.refreshed[-1][1:], (True, 0))
        self.assertEqual(self.jobs[0].completed, ('1234',))
        self.assertTrue(self.screen.initialized)

    def test_movie_resume_and_short_playback_reset_use_local_tracking(self):
        for state, expected in ((1801234, 1801234), (30000, 0), (0, 0)):
            with self.subTest(state=state):
                self.screen.storePlaybackProgress(self.screen.video, state)
                self.screen.fromPlayback = True
                self.screen.onReInit()
                self.assertEqual(self.screen.refreshed[-1][2], expected)
                self.assertEqual(self.jobs[-1].completed, ())
        self.server.query.assert_not_called()

    def test_movie_ignores_progress_for_another_item_or_server(self):
        self.screen._setupProgressHook = Mock()
        for key, server in [('other', self.server), ('1234', SimpleNamespace(uuid='different'))]:
            with patch.object(preplay.player, 'PLAYER', SimpleNamespace(video=SimpleNamespace(server=server))):
                self.screen.onVideoProgress(data=(None, None, key, True))
        self.assertEqual(self.screen._returnProgress, {})

    def test_non_playback_movie_reinit_still_reloads_synchronously(self):
        self.screen.fromPlayback = False
        with patch.object(self.screen.video, 'reload') as reload_:
            self.screen.onReInit()
        self.assertTrue(reload_.call_args.kwargs['skip_cache'])
        self.assertEqual(self.jobs, [])

    def test_episode_return_uses_local_completion_and_selects_next_without_network(self):
        screen = EpisodeScreen(self.server)
        episodes.VIDEO_PROGRESS['show'] = OrderedDict([('season', OrderedDict([('e1', True)]))])
        screen.onReInit()
        self.server.query.assert_not_called()
        self.assertTrue(screen.episodeListControl[0].dataSource.isFullyWatched)
        self.assertEqual(screen.episodeListControl.selected, 1)
        self.assertEqual(self.jobs[-1].completed, ('e1',))
        self.assertEqual({key for key, _ in self.jobs[-1].requests}, {'e1', 'e2', 'show'})
        self.assertEqual(self.jobs[-1].seasons, str(screen.show_.key))
        self.assertFalse(screen.currentItemLoaded)
        screen.postpone_simple.assert_not_called()

    def test_returned_seasons_use_the_show_children_key_as_their_initpath(self):
        screen = EpisodeScreen(self.server)
        data = ET.fromstring('<MediaContainer><Directory type="season" ratingKey="season" '
                             'key="/library/metadata/season/children" index="1"/></MediaContainer>')
        with patch.object(screen, 'fillSeasons') as fill:
            screen.onPlaybackReturnSeasons(data)
        seasons = fill.call_args.kwargs['seasons']
        self.assertEqual(len(seasons), 1)
        self.assertIsInstance(seasons[0], video.Season)
        self.assertEqual(seasons[0].initpath, str(screen.show_.key))
        self.server.query.assert_not_called()

    def test_stale_server_metadata_cannot_undo_local_completion_or_resume(self):
        for state, watched, offset in [(True, True, 0), (234567, False, 234567)]:
            with self.subTest(state=state):
                self.screen.storePlaybackProgress(self.screen.video, state)
                self.screen.fromPlayback = True
                self.screen.onReInit()
                self.queue_metadata(viewCount=0, viewOffset=0)
                self.screen.processPendingPlaybackReturn()
                self.assertEqual(self.screen.refreshed[-1][1:], (watched, offset))
                self.server.query.assert_not_called()

    def test_new_playback_or_navigation_invalidates_old_completion(self):
        self.screen.onReInit()
        self.queue_metadata(viewCount=1, viewOffset=0)
        self.screen.invalidatePlaybackReturn(clear_progress=True)
        self.screen.processPendingPlaybackReturn()
        self.assertEqual(len(self.screen.refreshed), 1)

    def test_profile_change_or_replaced_movie_discards_completion(self):
        for change in ('profile', 'movie', 'server'):
            with self.subTest(change=change):
                self.screen = MovieScreen(model(self.server))
                self.screen.onReInit()
                self.queue_metadata(viewCount=1, viewOffset=0)
                if change == 'profile':
                    context = patch.object(playback_sync, 'accountScope', return_value=('new',))
                else:
                    self.screen.video = model(SimpleNamespace(uuid='new') if change == 'server' else self.server,
                                              '1234' if change == 'server' else 'other')
                    context = patch.object(playback_sync, 'accountScope', return_value=SCOPE)
                with context:
                    self.screen.processPendingPlaybackReturn()
                self.assertEqual(len(self.screen.refreshed), 1)

    def test_child_window_and_wrong_thread_never_apply_gui_results(self):
        self.screen.onReInit()
        self.queue_metadata(viewCount=1, viewOffset=0)
        ENV.current_window_id = 13021
        self.screen.processPendingPlaybackReturn()
        self.assertEqual(len(self.screen.refreshed), 1)
        ENV.current_window_id = 13020
        worker = threading.Thread(target=self.screen.processPendingPlaybackReturn)
        worker.start()
        worker.join(1)
        self.assertEqual(len(self.screen.refreshed), 1)
        self.screen.processPendingPlaybackReturn()
        self.assertEqual(len(self.screen.refreshed), 2)
        self.assertEqual(self.screen.refreshed[-1][0], threading.current_thread().ident)

    def test_empty_metadata_snapshot_never_falls_back_to_network(self):
        self.screen.onReInit()
        self.screen._returnResults.put((self.screen._returnGeneration, SCOPE, 'metadata',
                                       {'1234': ET.fromstring('<Video ratingKey="1234" viewCount="1"/>')}))
        self.screen.processPendingPlaybackReturn()
        self.server.query.assert_not_called()
        self.assertTrue(self.screen.video.isFullyWatched)

    def test_back_during_blocked_request_does_not_wait_or_touch_closed_window(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        job = self.jobs[-1]
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        client = SimpleNamespace(session=SimpleNamespace(close=Mock()))
        def query(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release network request')
            return b''
        client.query = query
        def run():
            try:
                with patch.object(job, 'client', return_value=client):
                    job.run()
            finally:
                finished.set()
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            def close(window, **kwargs):
                window._closing = True
                window.isOpen = False
            with patch.object(preplay.TasksMixin, 'doClose'), patch.object(kodigui.ControlledWindow, 'doClose', close):
                self.screen.doClose()
            self.assertFalse(finished.is_set(), 'Back must finish before the network request does')
            self.queue_metadata(viewCount=0, viewOffset=123456)
        finally:
            release.set()
            worker.join(2)
        self.assertTrue(finished.is_set())
        self.screen.processPendingPlaybackReturn()
        self.assertEqual(len(self.screen.refreshed), 1)
        client.session.close.assert_called_once()

    def test_worker_scrobbles_before_metadata_and_uses_empty_response_as_success(self):
        screen = self.screen
        screen.storePlaybackProgress(screen.video, True)
        screen.onReInit()
        job = self.jobs[-1]
        calls = []
        def query(path, **kwargs):
            calls.append(path)
            if path == '/:/scrobble':
                return b''
            return ET.fromstring('<MediaContainer><Video ratingKey="1234" viewCount="1"/></MediaContainer>')
        client = SimpleNamespace(query=query, session=SimpleNamespace(close=Mock()))
        with patch.object(job, 'client', return_value=client):
            job.run()
        self.assertEqual(calls, ['/:/scrobble', '/library/metadata/1234'])
        self.assertEqual(len(screen.refreshed), 1, 'worker must not update the GUI')
        screen.processPendingPlaybackReturn()
        self.assertEqual(len(screen.refreshed), 2)

    def test_transport_failure_keeps_local_completion_and_worker_alive(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        client = SimpleNamespace(query=Mock(return_value=None), session=SimpleNamespace(close=Mock()))
        with patch.object(self.jobs[-1], 'client', return_value=client):
            self.jobs[-1].run()
        self.screen.processPendingPlaybackReturn()
        self.assertTrue(self.screen.video.isFullyWatched)
        client.session.close.assert_called_once()

    def test_window_owner_loop_delivers_pending_results(self):
        seen = []
        window = SimpleNamespace(_closing=False, processPendingPlaybackReturn=lambda: seen.append('delivered'))
        with patch.object(kodigui, 'MONITOR', SimpleNamespace(waitFor=Mock(side_effect=[False, True]))):
            kodigui.ControlledBase.wait(window)
        self.assertEqual(seen, ['delivered'])

    def test_profile_switch_prevents_queued_server_writes(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        with patch.object(playback_sync, 'accountScope', return_value=('new',)), patch.object(self.jobs[-1], 'client') as create:
            self.jobs[-1].run()
        create.assert_not_called()

    def test_explicit_unwatched_supersedes_an_older_queued_completion_write(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        old_job = self.jobs[-1]
        scope = self.screen.beginManualPlaybackChange()
        self.screen.video.set('viewCount', 0)
        self.screen.video.set('viewOffset', 0)
        self.screen.finishManualPlaybackChange(self.screen.video, False, scope)
        calls = []
        client = SimpleNamespace(query=lambda path, **kw: calls.append(path) or b'',
                                 session=SimpleNamespace(close=Mock()))
        for job in (old_job, self.jobs[-1]):
            with patch.object(job, 'client', return_value=client):
                job.run()
        self.assertEqual(calls, ['/:/unscrobble'])
        self.assertFalse(self.screen.video.isFullyWatched)

    def test_manual_choice_is_reasserted_after_an_inflight_completion_write(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        old_job = self.jobs[-1]
        entered, release = threading.Event(), threading.Event()
        remote = {'watched': False}
        calls = []
        def old_query(path, **kw):
            calls.append(path)
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test did not release request')
            remote['watched'] = True
            return b''
        client = SimpleNamespace(query=old_query, session=SimpleNamespace(close=Mock()))
        def run():
            with patch.object(old_job, 'client', return_value=client):
                old_job.run()
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            scope = self.screen.beginManualPlaybackChange()
            remote['watched'] = False  # The foreground manual Unwatched request.
            self.screen.finishManualPlaybackChange(self.screen.video, False, scope)
        finally:
            release.set()
            worker.join(2)
        self.assertTrue(remote['watched'], 'the old in-flight response may arrive last')
        def latest_query(path, **kw):
            calls.append(path)
            remote['watched'] = False
            return b''
        client.query = latest_query
        with patch.object(self.jobs[-1], 'client', return_value=client):
            self.jobs[-1].run()
        self.assertFalse(remote['watched'])
        self.assertEqual(calls, ['/:/scrobble', '/:/unscrobble'])

    def test_actual_movie_refresh_rechecks_closure_generation_and_focus_after_sleep(self):
        for action in ('close', 'new_playback', 'child_window'):
            with self.subTest(action=action):
                screen = MovieScreen(model(self.server))
                screen.getFocusId = Mock(return_value=screen.PLAY_BUTTON_ID)
                screen.setInfo = Mock()
                screen.focusPlayButton = Mock()
                ENV.current_window_id = 13020
                def during_sleep(ms):
                    if action == 'close':
                        screen.invalidatePlaybackReturn(closed=True)
                        screen._closing = True
                    elif action == 'new_playback':
                        screen.invalidatePlaybackReturn(clear_progress=True)
                    else:
                        ENV.current_window_id = 13021
                with patch.object(preplay.xbmc, 'sleep', side_effect=during_sleep):
                    preplay.PrePlayWindow.refreshInfo(screen, from_reinit=True)
                screen.focusPlayButton.assert_not_called()

    def test_failed_next_episode_refresh_settles_and_play_retries(self):
        screen = EpisodeScreen(self.server)
        episodes.VIDEO_PROGRESS['show'] = OrderedDict([('season', OrderedDict([('e1', True)]))])
        screen.onReInit()
        self.assertFalse(screen.currentItemLoaded)
        client = SimpleNamespace(query=Mock(return_value=None), session=SimpleNamespace(close=Mock()))
        with patch.object(self.jobs[-1], 'client', return_value=client):
            self.jobs[-1].run()
        screen.processPendingPlaybackReturn()
        self.assertTrue(screen.currentItemLoaded)
        self.assertTrue(screen._returnRefreshFailed)
        selected = screen.episodeListControl.getSelectedItem()
        def retry(*args, **kwargs):
            screen.closing = True  # Stand in for the existing terminal failure UI.
        with patch.object(screen, 'reloadItems', side_effect=retry) as reload_:
            screen.episodeListClicked()
        reload_.assert_called_once_with([selected], with_progress=True, set_item_info=True)
        self.assertFalse(screen._returnRefreshFailed)

    def test_manual_mark_and_unmark_clear_local_resume_and_stale_read_results(self):
        for watched in (False, True):
            with self.subTest(watched=watched):
                screen = MovieScreen(model(self.server))
                screen.storePlaybackProgress(screen.video, 765432)
                screen.onReInit()
                self.queue_metadata(screen=screen, viewCount=0, viewOffset=765432)
                with patch.object(screen.video, 'markWatched') as mark, \
                        patch.object(screen.video, 'markUnwatched') as unmark, \
                        patch.object(preplay.util.MONITOR, 'watchStatusChanged'):
                    screen.toggleWatched(screen.video, state=watched)
                (mark if watched else unmark).assert_called_once()
                screen.processPendingPlaybackReturn()
                self.assertEqual(screen.video.viewOffset.asInt(), 0)
                self.assertEqual(screen.video.isFullyWatched, watched)
                self.assertNotIn('1234', screen._returnProgress)

    def test_cancelling_confirmation_keeps_local_progress_and_pending_requests(self):
        screen = EpisodeScreen(self.server)
        screen.beforeWatchedChange = Mock()
        item = SimpleNamespace(TYPE='season', parentTitle='Show', title='Season')
        with patch.object(common.util, 'getSetting', return_value=True), \
                patch.object(common.optionsdialog, 'show', return_value=1):
            result = common.CommonMixin.toggleWatched(screen, item, state=False)
        self.assertIsNone(result)
        screen.beforeWatchedChange.assert_not_called()

    def test_manual_action_in_another_view_supersedes_old_closed_view_write(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        old_job = self.jobs[-1]
        self.screen.invalidatePlaybackReturn(closed=True)
        same_movie = model(self.server)
        with patch.object(same_movie, 'markUnwatched'):
            common.CommonMixin.toggleWatched(SimpleNamespace(), same_movie, state=False)
        self.assertEqual(old_job.cancelledKeys, {'1234'})
        self.assertEqual(self.jobs[-1].unwatched, ('1234',))
        self.assertEqual(same_movie.viewOffset.asInt(), 0)
        self.assertFalse(same_movie.isFullyWatched)

    def test_manual_episode_change_preserves_other_pending_completions(self):
        job = playback_sync.PlaybackReturnJob(self.server, [('e1', {}), ('e2', {})], ('e1', 'e2'), (),
                                              SCOPE, 1, Queue(), parents={'e1': ('show', 's1'), 'e2': ('show', 's2')})
        self.jobs.append(job)
        first = model(self.server, 'e1', 'episode')
        self.assertEqual(playback_sync.supersedeWrites(first), SCOPE)
        calls = []
        client = SimpleNamespace(query=lambda path, **kw: calls.append((path, kw.get('key'))) or b'',
                                 session=SimpleNamespace(close=Mock()))
        with patch.object(job, 'client', return_value=client):
            job.run()
        self.assertEqual(calls, [('/:/scrobble', 'e2')])

    def test_manual_episode_state_clears_retained_progress_for_only_that_item(self):
        episodes.VIDEO_PROGRESS['show'] = OrderedDict([('season', OrderedDict([('e1', True), ('e2', 123456)]))])
        item = model(self.server, 'e1', 'episode')
        playback_sync.finishWatchChange(item, False, None)
        self.assertEqual(episodes.VIDEO_PROGRESS['show']['season'], {'e2': 123456})
        self.assertEqual(item.viewOffset.asInt(), 0)

    def test_another_view_manual_action_invalidates_already_queued_read_snapshot(self):
        self.screen.storePlaybackProgress(self.screen.video, 765432)
        self.screen.onReInit()
        self.queue_metadata(viewCount=0, viewOffset=765432)
        edited = model(self.server)
        with patch.object(edited, 'markUnwatched'):
            common.CommonMixin.toggleWatched(SimpleNamespace(), edited, state=False)
        self.screen.processPendingPlaybackReturn()
        self.assertEqual(len(self.screen.refreshed), 1)
        self.screen.applyPlaybackProgress(edited)
        self.assertEqual(edited.viewOffset.asInt(), 0)

    def test_session_setup_failure_publishes_terminal_episode_result(self):
        screen = EpisodeScreen(self.server)
        episodes.VIDEO_PROGRESS['show'] = OrderedDict([('season', OrderedDict([('e1', True)]))])
        screen.onReInit()
        with patch.object(self.jobs[-1], 'client', side_effect=RuntimeError('cache/session unavailable')):
            self.jobs[-1].run()
        screen.processPendingPlaybackReturn()
        self.assertTrue(screen.currentItemLoaded)
        self.assertTrue(screen._returnRefreshFailed)

    def test_unrelated_manual_action_cannot_strand_next_episode_readiness(self):
        screen = EpisodeScreen(self.server)
        episodes.VIDEO_PROGRESS['show'] = OrderedDict([('season', OrderedDict([('e1', True)]))])
        screen.onReInit()
        playback_sync.supersedeWrites(model(self.server, 'unrelated'))
        screen.processPendingPlaybackReturn()  # No result need be published for an invalidated job.
        self.assertTrue(screen.currentItemLoaded)
        self.assertTrue(screen._returnRefreshFailed)
        self.assertTrue(self.jobs[-1].discard.is_set())

    def test_show_manual_choice_supersedes_queued_episode_and_season_corrections(self):
        show = video.Show(ET.fromstring('<Directory type="show" ratingKey="show" key="/library/metadata/show" leafCount="2"/>'),
                          initpath='/library/metadata/show', server=self.server)
        season = video.Season(ET.fromstring('<Directory type="season" ratingKey="season" parentRatingKey="show" key="/library/metadata/season" leafCount="2"/>'),
                              initpath='/library/metadata/season', server=self.server)
        for item in (model(self.server, 'e1', 'episode'), season):
            playback_sync.finishWatchChange(item, True, SCOPE)
        scope = playback_sync.supersedeWrites(show)
        self.assertEqual(scope, SCOPE)
        playback_sync.finishWatchChange(show, False, scope)
        calls = []
        client = SimpleNamespace(query=lambda path, **kw: calls.append((path, kw.get('key'))) or b'',
                                 session=SimpleNamespace(close=Mock()))
        for job in self.jobs:
            with patch.object(job, 'client', return_value=client):
                job.run()
        self.assertEqual(calls, [('/:/unscrobble', 'show')])

    def test_already_confirmed_home_action_does_not_ask_twice(self):
        show = video.Show(ET.fromstring('<Directory type="show" ratingKey="show" key="/library/metadata/show" leafCount="2"/>'),
                          initpath='/library/metadata/show', server=self.server)
        with patch.object(show, 'markUnwatched') as mark, \
                patch.object(common.util, 'getSetting', return_value=True), \
                patch.object(common.optionsdialog, 'show') as confirm:
            common.CommonMixin.toggleWatched(SimpleNamespace(), show, state=False, confirmed=True)
        mark.assert_called_once()
        confirm.assert_not_called()

    def test_successful_empty_body_scrobble_allows_watchlist_removal(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        job = self.jobs[-1]
        job.watchlist = dict(key='1234', type='movie', guid='guid', watched=True,
                             remove=True, server=SimpleNamespace(uuid='discover'))
        pms = SimpleNamespace(session=SimpleNamespace(close=Mock()), query=Mock(side_effect=[b'', ET.fromstring(
            '<MediaContainer><Video ratingKey="1234" viewCount="1"/></MediaContainer>')]))
        discover = SimpleNamespace(session=SimpleNamespace(close=Mock()), query=Mock())
        with patch.object(job, 'client', side_effect=[pms, discover]), patch('lib.windows.mixins.watchlist.is_watchlisted', return_value=False):
            job.run()
        discover.query.assert_called_once_with('/actions/removeFromWatchlist', ratingKey='guid', method='put')
        with patch.object(preplay.plexapp.util.APP, 'trigger') as trigger, patch.object(preplay.util, 'showNotification') as notify:
            self.screen.processPendingPlaybackReturn()
        trigger.assert_called_once_with('watchlist:modified')
        notify.assert_called_once()
        self.assertFalse(self.screen.is_watchlisted)

    def test_failed_scrobble_does_not_allow_watchlist_auto_removal(self):
        self.screen.storePlaybackProgress(self.screen.video, True)
        self.screen.onReInit()
        job = self.jobs[-1]
        job.watchlist = dict(key='1234', type='movie', guid='guid', watched=True,
                             remove=True, server=SimpleNamespace(uuid='discover'))
        pms = SimpleNamespace(session=SimpleNamespace(close=Mock()), query=Mock(return_value=None))
        discover = SimpleNamespace(session=SimpleNamespace(close=Mock()), query=Mock())
        with patch.object(job, 'client', side_effect=[pms, discover]), patch('lib.windows.mixins.watchlist.is_watchlisted', return_value=None):
            job.run()
        self.screen.is_watchlisted = True
        self.screen.processPendingPlaybackReturn()
        self.assertTrue(self.screen.is_watchlisted, 'unknown state must preserve the previous state')
        discover.query.assert_not_called()
        self.assertTrue(self.screen.video.isFullyWatched)

    def test_owner_applies_snapshot_preserving_media_part_and_audio_selection(self):
        from plexnet import mediachoice
        item = self.screen.video
        item.mediaChoice = mediachoice.MediaChoice(item.media()[0])
        before = (str(item.mediaChoice.media.id), str(item.mediaChoice.part.id), str(item.mediaChoice.audioStream.id))
        self.screen.onReInit()
        self.queue_metadata(viewCount=0, viewOffset=100000)
        self.screen.processPendingPlaybackReturn()
        after = (str(item.mediaChoice.media.id), str(item.mediaChoice.part.id), str(item.mediaChoice.audioStream.id))
        self.assertEqual(before, after)
        self.server.query.assert_not_called()

    def test_worker_cleans_captured_urls_before_fetch_without_touching_ui(self):
        self.screen.onReInit()
        job = self.jobs[-1]
        job.urls = ('http://server/item?token=one', 'http://server/section?token=one')
        calls = []
        cache = SimpleNamespace(delete_url=lambda u: calls.append(('delete', u)),
                                vacuum=lambda: calls.append(('vacuum',)))
        client = SimpleNamespace(session=SimpleNamespace(cache=cache, close=Mock()),
                                 query=lambda *a, **kw: calls.append(('fetch',)) or None)
        with patch.object(job, 'client', return_value=client):
            job.run()
        self.assertEqual([c[0] for c in calls], ['delete', 'delete', 'vacuum', 'fetch'])
        self.assertEqual(len(self.screen.refreshed), 1)

    def test_real_dedicated_worker_serializes_jobs_and_is_reused(self):
        entered, release, second, stop = (threading.Event() for _ in range(4))
        owner = threading.current_thread().ident
        threads = []
        def first():
            threads.append(threading.current_thread().ident)
            entered.set()
            release.wait(2)
        def next_():
            threads.append(threading.current_thread().ident)
            second.set()
        with patch.object(playback_sync, '_JOBS', Queue()), patch.object(playback_sync, '_WORKER', None), \
                patch.object(playback_sync.util, 'MONITOR', SimpleNamespace(abortRequested=stop.is_set)):
            playback_sync.submit(SimpleNamespace(run=first))
            worker = playback_sync._WORKER
            try:
                self.assertTrue(entered.wait(1))
                playback_sync.submit(SimpleNamespace(run=next_))
                self.assertIs(worker, playback_sync._WORKER)
                self.assertFalse(second.is_set())
                release.set()
                self.assertTrue(second.wait(1))
                self.assertEqual(threads[0], threads[1])
                self.assertNotEqual(owner, threads[0])
            finally:
                release.set()
                stop.set()
                worker.join(1)
            self.assertFalse(worker.is_alive())


class CacheSnapshotTest(KodiTestCase):
    def test_collecting_urls_does_not_modify_live_invalidation_lists(self):
        # Save the production function independently of test fixture monkeypatches.
        base = {'episode_e1': ['item'], 'season_season': ['season'], 'show_show': ['show'],
                'section_1': ['section']}
        original = copy.deepcopy(base)
        item = SimpleNamespace(TYPE='episode', parentRatingKey='season', grandparentRatingKey='show',
                               getCacheRef=lambda **kw: 'episode_e1', getLibrarySectionId=lambda: '1')
        interface = SimpleNamespace(getRCBaseKey=lambda: 'scope')
        with patch.object(playback_sync.pnUtil, 'INTERFACE', interface), \
                patch.object(playback_sync.pnUtil, 'CACHED_PLEX_URLS', {'scope': base}):
            urls = playback_sync.cacheURLs([item])
        self.assertEqual(set(urls), {'item', 'season', 'show', 'section'})
        self.assertEqual(base, original)
