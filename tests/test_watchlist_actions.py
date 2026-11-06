# coding=utf-8
"""Manual watch actions must check the whole show's Watchlist eligibility."""
from __future__ import absolute_import

import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from kodienv import ENV
ENV.abort_requested = True
from lib import playback_sync
from lib.windows import home, library
from lib.windows.mixins import common, watchlist
from plexnet import video

from .base import KodiTestCase, ensure_plex_interface


DEFAULT_RESPONSE = object()


def container(element):
    root = ET.Element('MediaContainer', size='1')
    root.append(copy.deepcopy(element))
    return root


class WatchlistActionsTest(KodiTestCase):
    def setUp(self):
        super(WatchlistActionsTest, self).setUp()
        ensure_plex_interface()
        self.auto_remove = True
        self.use_watchlist = True
        self.removal = Mock()
        get_setting = common.util.getSetting
        patches = [
            patch.object(watchlist.util, 'getUserSetting', side_effect=self.setting),
            patch.object(common.util, 'getSetting', side_effect=lambda key, *args, **kwargs:
                         False if key == 'home_confirm_actions' else get_setting(key, *args, **kwargs)),
            patch.object(playback_sync, 'supersedeWrites', return_value=None),
            patch.object(watchlist.pnUtil, 'ACCOUNT', SimpleNamespace(isOffline=False)),
        ]
        # Capture only the cloud removal boundary; exercise the real window,
        # common watch action, plexnet mark/reload, and completion properties.
        for module in (library, watchlist):
            patches.append(patch.object(module, 'removeFromWatchlistBlind', self.removal))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def setting(self, key, default=None):
        return {'watchlist_auto_remove': self.auto_remove,
                'use_watchlist': self.use_watchlist}.get(key, default)

    def setup_item(self, kind='episode', cached_complete=False, fresh_complete=False):
        self.server = Mock(uuid='server')
        self.server.query.side_effect = self.query
        self.show_data = ET.fromstring(
            '<Directory type="show" ratingKey="show" key="/library/metadata/show/children" '
            'guid="plex://show/example" title="Show" leafCount="20" viewedLeafCount="5"/>')
        cached = copy.deepcopy(self.show_data)
        cached.set('viewedLeafCount', '20' if cached_complete else '5')
        self.cached_show = video.Show(cached, server=self.server)
        self.show_data.set('viewedLeafCount', '20' if fresh_complete else '5')
        self.show_response = DEFAULT_RESPONSE
        self.show_error = None
        self.item_data = ET.fromstring(
            '<Video type="episode" ratingKey="item" key="/library/metadata/item" '
            'grandparentRatingKey="show" grandparentKey="/library/metadata/show" '
            'parentRatingKey="season" parentKey="/library/metadata/season" '
            'viewCount="1" viewOffset="120000"/>')
        if kind in ('season', 'show'):
            self.item_data.tag = 'Directory'
            self.item_data.set('leafCount', '20')
            self.item_data.set('viewedLeafCount', '5')
        self.item_data.set('type', kind)
        if kind == 'season':
            self.item_data.set('parentRatingKey', 'show')
            self.item_data.set('parentKey', '/library/metadata/show')
        if kind == 'show':
            self.item_data = copy.deepcopy(self.show_data)
        elif kind == 'movie':
            self.item_data.set('guid', 'plex://movie/example')
        cls = {'episode': video.Episode, 'season': video.Season,
               'show': video.Show, 'movie': video.Movie}[kind]
        self.item = cls(copy.deepcopy(self.item_data), server=self.server)
        if kind == 'episode':
            self.item._show = self.cached_show
        self.item.clearCache = Mock()
        self.removal.reset_mock()
        return self.item

    def query(self, path, **kwargs):
        if path.startswith(('/:/scrobble?', '/:/unscrobble?')):
            watched = path.startswith('/:/scrobble?')
            self.item_data.set('viewCount', '2' if watched else '0')
            self.item_data.set('viewOffset', '0')
            if self.item.TYPE in ('show', 'season'):
                self.item_data.set('viewedLeafCount', '20' if watched else '0')
            if self.item.TYPE == 'show':
                self.show_data = copy.deepcopy(self.item_data)
            return b''
        if path == '/library/metadata/show':
            if self.show_error:
                raise self.show_error
            if self.show_response is not DEFAULT_RESPONSE:
                return self.show_response
            return container(self.show_data)
        if path == '/library/metadata/item':
            return container(self.item_data)
        raise AssertionError('Unexpected Plex request: ' + path)

    def act(self, screen, state=True):
        if screen == 'home':
            win = home.HomeWindow.__new__(home.HomeWindow)
            win._updateOnDeckHubs = Mock()
            win.toggleWatched(item=self.item, state=state)
            win._updateOnDeckHubs.assert_called_once()
        else:
            win = library.LibraryWindow.__new__(library.LibraryWindow)
            win._current = None
            win.updateUnwatchedAndProgress = Mock()
            mli = SimpleNamespace(dataSource=self.item)
            win.toggleWatched(mli, state=state, confirmed=True)
            win.updateUnwatchedAndProgress.assert_called_once_with(mli)

    def test_rewatched_episode_keeps_incomplete_show_even_if_cached_complete(self):
        for screen in ('home', 'library'):
            with self.subTest(screen=screen):
                self.setup_item(cached_complete=True)
                self.act(screen)
                self.assertTrue(self.item.isFullyWatched)
                self.removal.assert_not_called()

    def test_last_episode_or_season_removes_only_the_freshly_completed_show(self):
        for screen in ('home', 'library'):
            for kind in ('episode', 'season'):
                with self.subTest(screen=screen, kind=kind):
                    self.setup_item(kind, fresh_complete=True)
                    self.act(screen)
                    self.removal.assert_called_once()
                    guid, reference = self.removal.call_args[0]
                    self.assertEqual('plex://show/example', guid)
                    self.assertEqual('show', reference.TYPE)
                    self.assertTrue(reference.isFullyWatched)
                    self.server.query.assert_any_call('/library/metadata/show', cachable=False, includeOnDeck=1)

    def test_completed_season_keeps_incomplete_show(self):
        for screen in ('home', 'library'):
            with self.subTest(screen=screen):
                self.setup_item('season')
                self.act(screen)
                self.assertTrue(self.item.isFullyWatched)
                self.removal.assert_not_called()

    def test_equal_counts_with_another_episode_in_progress_keep_show(self):
        for screen in ('home', 'library'):
            with self.subTest(screen=screen):
                self.setup_item(fresh_complete=True)
                ET.SubElement(ET.SubElement(self.show_data, 'OnDeck'), 'Video',
                              type='episode', viewCount='1', viewOffset='60000')
                self.act(screen)
                self.removal.assert_not_called()

    def test_failed_or_invalid_show_metadata_never_uses_cached_completion(self):
        for screen in ('home', 'library'):
            for failure in ('exception', 'none', 'empty', 'wrong_key', 'wrong_type', 'missing_counts', 'zero', 'malformed'):
                with self.subTest(screen=screen, failure=failure):
                    self.setup_item(cached_complete=True, fresh_complete=True)
                    if failure == 'exception':
                        self.show_error = RuntimeError('unavailable')
                    elif failure == 'none':
                        self.show_response = None
                    elif failure == 'empty':
                        self.show_response = ET.Element('MediaContainer', size='0')
                    elif failure == 'wrong_key':
                        self.show_data.set('ratingKey', 'different')
                    elif failure == 'wrong_type':
                        self.show_data.set('type', 'season')
                    elif failure == 'missing_counts':
                        del self.show_data.attrib['leafCount']
                        del self.show_data.attrib['viewedLeafCount']
                    elif failure == 'zero':
                        self.show_data.set('leafCount', '0')
                        self.show_data.set('viewedLeafCount', '0')
                    else:
                        self.show_data.set('leafCount', 'unknown')
                    self.act(screen)
                    self.removal.assert_not_called()

    def test_disabled_or_offline_watchlist_never_auto_removes(self):
        for reason in ('auto_remove', 'use_watchlist', 'offline'):
            self.auto_remove = reason != 'auto_remove'
            self.use_watchlist = reason != 'use_watchlist'
            watchlist.pnUtil.ACCOUNT.isOffline = reason == 'offline'
            for screen in ('home', 'library'):
                for kind in ('episode', 'season', 'movie', 'show'):
                    with self.subTest(reason=reason, screen=screen, kind=kind):
                        self.setup_item(kind, fresh_complete=True)
                        self.act(screen)
                        self.removal.assert_not_called()
                        # A show action itself reloads show metadata; children
                        # should not need any additional parent lookup here.
                        if kind != 'show':
                            self.assertNotIn('/library/metadata/show', [c.args[0] for c in self.server.query.call_args_list])

    def test_completed_movie_and_whole_show_still_remove(self):
        for screen in ('home', 'library'):
            for kind in ('movie', 'show'):
                with self.subTest(screen=screen, kind=kind):
                    self.setup_item(kind)
                    self.act(screen)
                    self.removal.assert_called_once()

    def test_forced_unplayed_and_default_toggle_never_remove(self):
        for screen in ('home', 'library'):
            for state in (False, None):
                with self.subTest(screen=screen, state=state):
                    self.setup_item('movie')
                    self.item.set('viewOffset', 0)
                    self.item_data.set('viewOffset', '0')
                    self.act(screen, state=state)
                    self.assertFalse(self.item.isFullyWatched)
                    self.removal.assert_not_called()

    def test_library_forced_played_on_already_played_movie_does_not_toggle(self):
        self.setup_item('movie')
        self.item.set('viewOffset', 0)
        self.item_data.set('viewOffset', '0')
        self.act('library', state=True)
        self.assertTrue(self.item.isFullyWatched)
        self.removal.assert_called_once()

    def test_library_forced_unplayed_on_in_progress_episode_does_not_toggle(self):
        self.setup_item()
        self.act('library', state=False)
        self.assertEqual(0, self.item.viewCount.asInt())
        self.assertEqual(0, self.item.viewOffset.asInt())
        self.removal.assert_not_called()

    def test_library_explicit_remove_still_allows_incomplete_show_with_auto_remove_off(self):
        self.auto_remove = False
        self.setup_item('show')
        self.assertFalse(self.item.isFullyWatched)
        mli = Mock(dataSource=self.item, label='Show', label2='')
        mli.getProperty.return_value = ''
        win = library.LibraryWindow.__new__(library.LibraryWindow)
        win._current = None
        win.section = SimpleNamespace(TYPE='movies_shows')
        win.showPanelControl = Mock()
        win.showPanelControl.getSelectedItem.return_value = mli
        win.doRefill = Mock()
        with patch.object(library.dropdown, 'showDropdown', return_value={'key': 'remove_from_watchlist'}):
            self.assertTrue(win.itemOptions())
        self.removal.assert_called_once_with(self.item.guid, self.item)
        win.doRefill.assert_called_once()

    def test_cancelled_show_confirmation_keeps_watch_state_and_watchlist(self):
        for screen in ('home', 'library'):
            with self.subTest(screen=screen):
                self.setup_item('show')
                with patch.object(common.util, 'getSetting', return_value=True), \
                        patch.object(common.optionsdialog, 'show', return_value=1):
                    if screen == 'home':
                        win = home.HomeWindow.__new__(home.HomeWindow)
                        win._updateOnDeckHubs = Mock()
                        win.toggleWatched(item=self.item, state=True)
                        win._updateOnDeckHubs.assert_not_called()
                    else:
                        win = library.LibraryWindow.__new__(library.LibraryWindow)
                        win._current = None
                        win.updateUnwatchedAndProgress = Mock()
                        win.toggleWatched(SimpleNamespace(dataSource=self.item), state=True)
                        win.updateUnwatchedAndProgress.assert_not_called()
                self.assertFalse(self.item.isFullyWatched)
                self.server.query.assert_not_called()
                self.removal.assert_not_called()
