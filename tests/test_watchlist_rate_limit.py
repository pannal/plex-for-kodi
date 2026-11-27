# coding=utf-8
"""Discover throttling must not block initialization or invent an empty Watchlist."""
from __future__ import absolute_import

from email.utils import formatdate
from unittest.mock import Mock, patch

from kodienv import ENV

ENV.abort_requested = True
from lib.windows import home, library  # noqa: E402
from lib.windows.mixins.watchlist import is_watchlisted  # noqa: E402
from plexnet import asyncadapter, exceptions, myplexaccount, plexapp, plexserver  # noqa: E402

from .base import KodiTestCase, ensure_plex_interface  # noqa: E402

ensure_plex_interface()
# Server-manager import normally follows account setup in plexapp.init().
with patch.object(plexapp, 'ACCOUNT', myplexaccount.ACCOUNT), \
        patch.object(plexapp.util.APP, 'on'):
    from plexnet import myplexserver  # noqa: E402


def response(status=200, retry_after=None):
    headers = {} if retry_after is None else {'Retry-After': retry_after}
    return Mock(status_code=status, headers=headers, text='<MediaContainer size="0"/>')


class DiscoverCooldownTest(KodiTestCase):
    def setUp(self):
        super(DiscoverCooldownTest, self).setUp()
        ensure_plex_interface()
        self.now = 1000.0
        self.clock = patch.object(plexserver, '_cooldownTime', lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.limits = patch.object(plexserver, '_RATE_LIMIT_UNTIL', {})
        self.limits.start()
        self.addCleanup(self.limits.stop)
        self.wait = patch.object(plexserver.MONITOR, 'waitForAbort', side_effect=self.advance)
        self.wait_mock = self.wait.start()
        self.addCleanup(self.wait.stop)

    def advance(self, seconds):
        self.now += seconds
        return False

    def server(self, token='account-a', server_class=myplexserver.PlexDiscoverServer):
        session = Mock()
        session.adapters = {'https://': Mock(max_retries=asyncadapter.StoppableRetry(3))}
        session.get = Mock(return_value=response())
        session.get.__name__ = 'get'
        with patch.object(plexserver.http, 'Session', return_value=session):
            server = server_class()
        server.getToken = lambda: token
        return server

    def test_429_passes_through_transport_while_connection_retries_remain(self):
        server = self.server()
        retry = server.session.adapters['https://'].max_retries
        self.assertFalse(retry.is_retry('GET', 429, has_retry_after=True))
        self.assertFalse(retry.new().is_retry('GET', 429, has_retry_after=True))
        self.assertEqual(asyncadapter.MAX_RETRIES, retry.total)
        self.assertEqual(asyncadapter.MAX_RETRIES - 1, retry.increment(error=Exception()).total)
        # Other status retry behavior stays as it was.
        self.assertTrue(retry.is_retry('GET', 503, has_retry_after=True))

    def test_count_and_chunks_share_cooldown_across_fresh_servers(self):
        first = self.server()
        first.session.get.return_value = response(429, '90')
        with self.assertRaises(exceptions.RateLimited) as caught:
            first.query('/library/sections/watchlist/all', limit=0)
        self.assertEqual(90, caught.exception.retry_after)
        self.assertIsInstance(caught.exception, exceptions.BadRequest)
        second = self.server()
        self.now += 0.2
        with self.assertRaises(exceptions.RateLimited) as caught:
            second.query('/hubs/sections/home', limit=50)
        self.assertEqual(90, caught.exception.retry_after)
        second.session.get.assert_not_called()
        self.now = 1090
        self.assertEqual('MediaContainer', second.query('/hubs/sections/home').tag)
        second.session.get.assert_called_once()

    def test_missing_header_uses_60_second_cooldown(self):
        server = self.server()
        server.session.get.return_value = response(429)
        with self.assertRaises(exceptions.RateLimited) as caught:
            server.query('/library/sections/watchlist/all')
        self.assertEqual(60, caught.exception.retry_after)
        self.wait_mock.assert_called_once_with(2)
        self.assertEqual(2, server.session.get.call_count)
        with self.assertRaises(exceptions.RateLimited):
            server.query('/actions/removeFromWatchlist', method='put')
        server.session.put.assert_not_called()

    def test_silent_retry_recovers_without_error(self):
        server = self.server()
        server.session.get.side_effect = [response(429), response()]
        self.assertEqual('MediaContainer', server.query('/watchlist').tag)
        self.wait_mock.assert_called_once_with(2)
        self.assertEqual(2, server.session.get.call_count)
        # The short cooldown has expired, so ordinary requests work again.
        server.session.get.side_effect = None
        self.assertEqual('MediaContainer', server.query('/next').tag)

    def test_short_retry_after_is_respected_on_first_retry(self):
        server = self.server()
        server.session.get.side_effect = [response(429, '5'), response()]
        self.assertEqual('MediaContainer', server.query('/watchlist').tag)
        self.wait_mock.assert_called_once_with(5)

    def test_final_short_retry_after_overrides_60_second_fallback(self):
        server = self.server()
        server.session.get.side_effect = [response(429), response(429, '3')]
        with self.assertRaises(exceptions.RateLimited) as caught:
            server.query('/watchlist')
        self.assertEqual(3, caught.exception.retry_after)
        self.now += 3
        server.session.get.side_effect = None
        self.assertEqual('MediaContainer', server.query('/watchlist').tag)

    def test_long_retry_after_returns_without_waiting_or_retrying_early(self):
        server = self.server()
        server.session.get.return_value = response(429, '120')
        with self.assertRaises(exceptions.RateLimited) as caught:
            server.query('/watchlist')
        self.assertEqual(120, caught.exception.retry_after)
        self.wait_mock.assert_not_called()
        server.session.get.assert_called_once()

    def test_shutdown_cancels_silent_retry(self):
        server = self.server()
        server.session.get.return_value = response(429)
        self.wait_mock.side_effect = None
        self.wait_mock.return_value = True
        self.assertIsNone(server.query('/watchlist'))
        server.session.get.assert_called_once()

    def test_cooldown_does_not_cross_users_or_origins_or_local_servers(self):
        first = self.server()
        first.session.get.return_value = response(429, '60')
        with self.assertRaises(exceptions.RateLimited):
            first.query('/limited')
        other_user = self.server('account-b')
        other_origin = self.server()
        other_origin.activeConnection.address = 'https://metadata.provider.plex.tv'
        local = self.server(server_class=plexserver.PlexServer)
        local.buildUrl = first.buildUrl  # Even an identical URL cannot enable the opt-in cooldown.
        for server in (other_user, other_origin, local):
            self.assertEqual('MediaContainer', server.query('/ok').tag)
            server.session.get.assert_called_once()

    def test_other_http_errors_keep_their_existing_type_and_no_cooldown(self):
        server = self.server()
        server.session.get.side_effect = [response(401), response()]
        with self.assertRaises(exceptions.BadRequest) as caught:
            server.query('/bad')
        self.assertNotIsInstance(caught.exception, exceptions.RateLimited)
        self.assertEqual('MediaContainer', server.query('/ok').tag)

    def test_local_server_429_keeps_existing_bad_request_handling(self):
        server = self.server(server_class=plexserver.PlexServer)
        server.buildUrl = lambda *args, **kwargs: 'http://localhost:32400/all'
        server.session.get.return_value = response(429)
        with self.assertRaises(exceptions.BadRequest) as caught:
            server.query('/all')
        self.assertNotIsInstance(caught.exception, exceptions.RateLimited)
        self.wait_mock.assert_not_called()

    def test_success_preserves_query_options_and_raw_return(self):
        server = self.server()
        self.assertEqual(b'<MediaContainer size="0"/>',
                         server.query('/all', raw=True, params={'type': 2}, offset=10, limit=25))
        url = server.session.get.call_args[0][0]
        for part in ('type=2', 'X-Plex-Container-Start=10', 'X-Plex-Container-Size=25'):
            self.assertIn(part, url)


class RetryAfterTest(KodiTestCase):
    def test_seconds_date_missing_and_malformed_headers(self):
        now = 1000000000
        cases = [('120', 120), (' 5 ', 5), ('0', 0), (None, 60),
                 ('nonsense', 60), ('-10', 60), ('1.5', 60),
                 (formatdate(now + 75, usegmt=True), 75),
                 (formatdate(now - 75, usegmt=True), 0)]
        with patch.object(plexserver.time, 'time', return_value=now):
            for value, expected in cases:
                with self.subTest(value=value):
                    self.assertEqual(expected, plexserver.retryAfterSeconds(value))


class WatchlistRecoveryTest(KodiTestCase):
    def setUp(self):
        super(WatchlistRecoveryTest, self).setUp()
        ensure_plex_interface()

    def test_initial_count_failure_clears_filling_and_keeps_retryable(self):
        win = library.LibraryWindow.__new__(library.LibraryWindow)
        win.section = Mock(TYPE='movies_shows')
        win.section.all.side_effect = exceptions.RateLimited(45)
        win.sort = 'watchlistedAt'
        win.subDir = False
        win.boolFilters = {}
        win.refill = False
        win.setBoolProperty = Mock()
        win.getFilterOpts = Mock(return_value=None)
        win.getSortOpts = Mock(return_value=('watchlistedAt', 'desc'))
        with patch.object(library.busy.BusyWindow, 'create'), \
                patch.object(library.util, 'messageDialog') as message, \
                patch.object(library, 'ITEM_TYPE', 'show'):
            self.assertIs(False, win.fill())
        win.section.all.assert_called_once()
        win.setBoolProperty.assert_any_call('content.filling', False)
        self.assertTrue(win.refill)
        self.assertNotIn(('no.content', True), [c.args for c in win.setBoolProperty.call_args_list])
        self.assertIn('45', message.call_args[0][1])

    def test_failed_refill_keeps_home_navigation_and_retries_on_reinit(self):
        win = Mock(spec=library.LibraryWindow)
        win.section = Mock(TYPE='movies_shows')
        win.subDir = False
        win.sort = 'watchlistedAt'
        win.refill = True
        win._listGeneration = 0
        win.fill.return_value = False
        win.setBoolProperty = Mock()
        win.setFocusId = Mock()
        win.HOME_BUTTON_ID = 101
        win.POSTERS_PANEL_ID = 200
        win.KEY_LIST_ID = 201
        with patch.object(library.kodigui, 'ManagedControlList'):
            library.LibraryWindow.doRefill(win)
        self.assertTrue(win.refill)
        win.setFocusId.assert_called_with(win.HOME_BUTTON_ID)
        with patch.object(library.player.PLAYER, 'bgmPlaying', False):
            library.LibraryWindow.onReInit(win)
        win.doRefill.assert_called_once()

    def test_direct_sort_fill_is_also_guarded(self):
        win = library.LibraryWindow.__new__(library.LibraryWindow)
        win._fillShows = Mock(side_effect=exceptions.RateLimited(30))
        win.setBoolProperty = Mock()
        win.refill = False
        with patch.object(library.busy.BusyWindow, 'create'), \
                patch.object(library.util, 'messageDialog'):
            library.LibraryWindow.sortShowPanel(win, 'watchlistedAt', force_refresh=True)
        self.assertTrue(win.refill)
        win.setBoolProperty.assert_called_with('content.filling', False)

    def test_cooldown_revisits_do_not_repeat_the_message(self):
        win = library.LibraryWindow.__new__(library.LibraryWindow)
        win._fillShows = Mock(side_effect=exceptions.RateLimited(30, from_cooldown=True))
        win.setBoolProperty = Mock()
        with patch.object(library.util, 'messageDialog') as message:
            self.assertIs(False, win.fillShows())
        message.assert_not_called()
        self.assertTrue(win.refill)

    def test_home_keeps_local_libraries_when_watchlist_is_rate_limited(self):
        win = home.HomeWindow.__new__(home.HomeWindow)
        win.librarySettings = {}
        win.anyLibraryHidden = False
        win.sectionPinnedTypes = Mock(return_value=[])
        win.sectionList = Mock()
        win.setFocusId = Mock()
        section = Mock(key='1', title='Movies', type='movie')
        server = Mock()
        server.library.sections.return_value = [section]
        server.playlists.return_value = []
        server.hasHubs.return_value = False
        with patch.object(home.plexapp, 'ACCOUNT', Mock(isOffline=False)), \
                patch.object(home.plexapp, 'SERVERMANAGER', Mock(selectedServer=server)), \
                patch.object(home.plexlibrary, 'WatchlistSection', side_effect=exceptions.RateLimited(60)), \
                patch.object(home, 'pmm', Mock(mapping={})), \
                patch.object(home.util, 'getUserSetting', return_value=True), \
                patch.object(home.util, 'showNotification') as notification:
            win.showSections()
        self.assertIs(section, win.allSections['1'])
        self.assertIn(section, [item.dataSource for item in win.sectionList.addItems.call_args[0][0]])
        notification.assert_called_once()

    def test_failed_membership_check_remains_unknown(self):
        server = Mock()
        server.query.side_effect = exceptions.RateLimited(60)
        self.assertIsNone(is_watchlisted('item', server))
