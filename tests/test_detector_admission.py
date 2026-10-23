# coding=utf-8
"""Real final submission and optional helper; Kodi RPC/play are owned boundaries."""
from __future__ import absolute_import

import json
from types import SimpleNamespace
from unittest.mock import patch
from tests.base import KodiTestCase
from tests import test_playback_initialization as initialization
from lib import player, p3i_detector


class AdmissionTest(KodiTestCase):
    setUp = initialization.InitializationTest.setUp
    start = initialization.InitializationTest.start

    def set_server(self, available=True):
        self.generation = 0
        self.value = ''
        self.calls = []
        self.skips = []
        self.bindings = []
        self.binds = []
        self.releases = []
        self.cancels = []
        self.p.bgmPlaying = False
        self.p.video.settings = SimpleNamespace(getGlobal=lambda key: 'synthetic-client')
        self.available = available
        self.on_arm = None
        self.on_play = None
        self.addCleanup(patch.stopall)
        patch.object(p3i_detector, '_supported', None).start()
        patch.object(p3i_detector, '_job_supported', None).start()
        patch.object(p3i_detector.xbmc, 'executeJSONRPC', self.rpc).start()
        original = self.p.play
        def submit(url, li):
            # Kodi snapshots synchronously before queuing its asynchronous open.
            self.skips.append(self.value == '1')
            if self.value == '1':
                self.value = ''
            if self.on_play:
                self.on_play()
            self.bindings.append(li.getProperty('p3i.detector.binding'))
            original(url, li)
        patch.object(self.p, 'play', submit).start()

    def rpc(self, raw):
        request = json.loads(raw)
        method = request['method'].split('.')[-1]
        self.calls.append(method)
        if not self.available:
            return json.dumps({'jsonrpc': '2.0', 'error': {'code': -32601}, 'id': 1})
        if method == 'GetCapabilities':
            result = {'version': 1, 'supported': True, 'ownedskip': True, 'resultbinding': 1}
        elif method == 'Start':
            result = {'status': 'accepted', 'requestid': 'job-1'}
        elif method == 'GetStatus':
            result = {'status': 'completed'}
        elif method == 'Bind':
            self.binds.append(request.get('params'))
            result = {'status': 'ready', 'bindingid': 'bind-1', 'property': 'p3i.detector.binding'}
        elif method == 'ReleaseBinding':
            self.releases.append(request.get('params'))
            result = {'status': 'released'}
        elif method == 'Cancel':
            self.cancels.append(request.get('params'))
            result = {'status': 'cancelled'}
        elif method == 'SetSkipNext':
            self.generation += 1
            self.value = '1'
            result = {'version': 1, 'status': 'armed', 'token': str(self.generation)}
            if self.on_arm:
                self.on_arm()
        elif method == 'ClearSkipNext':
            cleared = request['params']['token'] == str(self.generation) and self.value == '1'
            if cleared:
                self.value = ''
            result = {'version': 1, 'status': 'cleared' if cleared else 'unchanged'}
        else:
            raise AssertionError(method)
        return json.dumps({'jsonrpc': '2.0', 'result': result, 'id': 1})

    def test_final_modes_direct_play_mapped_local_http_and_direct_stream_transcode(self):
        self.set_server()
        for url, mapped, transcoded in (
                ('/media/movie.mkv', True, False),
                ('smb://test.invalid/movie.mkv', True, False),
                ('https://test.invalid/library/parts/1/2/file.mkv', False, False),
                ('https://test.invalid/transcode/video-copy-audio.mkv', False, True),
                ('https://test.invalid/transcode/video.mkv', False, True)):
            with self.subTest(url=url):
                self.p.running = False
                self.meta.isMapped = mapped
                self.meta.isTranscoded = transcoded
                self.meta.streamUrls = [url]
                self.meta.path = url
                self.start()
                self.assertEqual(self.skips[-1], transcoded)
                self.assertEqual(self.value, '')
        self.assertEqual(self.calls.count('GetCapabilities'), 1)
        self.assertEqual(self.calls.count('SetSkipNext'), 2)
        self.assertNotIn('ClearSkipNext', self.calls)

    def test_final_server_decision_replaces_original_metadata(self):
        self.set_server()
        final = SimpleNamespace(**vars(self.meta))
        final.isTranscoded = True
        chosen = SimpleNamespace(metadata=final, getBifUrl=lambda: '', hasMoreParts=lambda: False)
        with patch.object(self.obj, 'getServerDecision', lambda: chosen):
            self.start()
        self.assertFalse(self.meta.isTranscoded)
        self.assertEqual(self.skips, [True])

    def test_stock_or_unsupported_kodi_is_probed_once_and_never_changes_play(self):
        self.set_server(False)
        self.meta.isTranscoded = True
        for unused in range(3):
            self.p.running = False
            self.start()
        self.assertEqual(self.skips, [False, False, False])
        self.assertEqual(self.calls, ['GetCapabilities'])

    def test_failed_preparation_never_arms_following_play_stays_eligible(self):
        self.set_server()
        self.meta.isTranscoded = True
        with patch.object(player.xbmcgui, 'ListItem', side_effect=ValueError('metadata')):
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.calls, [])
        self.meta.isTranscoded = False
        self.start()
        self.assertEqual(self.skips, [False])
        self.assertEqual(self.calls, [])

    def test_submission_failure_clears_only_its_owned_signal_and_retry_rearms(self):
        self.set_server()
        self.meta.isTranscoded = True
        with patch.object(self.p, 'play', side_effect=ValueError('submission')):
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.value, '')
        self.assertEqual(self.calls[-1], 'ClearSkipNext')
        self.p.running = False
        self.start()
        self.assertEqual(self.skips, [True])
        self.assertEqual(self.calls.count('SetSkipNext'), 2)
        self.assertEqual(self.value, '')

    def test_cancel_during_arm_cannot_submit_or_leak_signal(self):
        self.set_server()
        self.meta.isTranscoded = True
        self.on_arm = lambda: player.VideoStartup._current.finish()
        self.start()
        self.assertEqual(self.skips, [])
        self.assertEqual(self.value, '')
        self.assertEqual(self.calls[-1], 'ClearSkipNext')

    def test_stale_failure_cannot_clear_another_callers_newer_signal(self):
        self.set_server()
        self.meta.isTranscoded = True
        def abandoned(url, li):
            p3i_detector.arm_skip()  # another request publishes a later generation
            raise ValueError('old submission')
        with patch.object(self.p, 'play', abandoned):
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.value, '1')
        self.assertEqual(self.generation, 2)
        self.assertEqual(self.calls[-1], 'ClearSkipNext')
        p3i_detector.clear_skip('2')
        self.assertEqual(self.value, '')

    def test_terminal_cleanup_after_submission_does_not_clear_later_publication(self):
        self.set_server()
        self.meta.isTranscoded = True
        old = self.start()
        p3i_detector.arm_skip()
        old.finish()
        self.assertEqual(self.value, '1')
        p3i_detector.clear_skip(str(self.generation))

    def test_rpc_failure_and_malformed_reply_remain_optional(self):
        self.set_server()
        self.meta.isTranscoded = True
        for response in ('not JSON', '{}', '{"result":[]}', '{"result":{"version":2}}'):
            with patch.object(p3i_detector, '_supported', None), patch.object(p3i_detector.xbmc, 'executeJSONRPC', return_value=response):
                self.p.running = False
                self.start()
        self.assertEqual(self.skips, [False] * 4)

    def test_multipart_end_advances_through_real_final_submission(self):
        self.set_server()
        self.meta.isTranscoded = True
        self.start()
        self.p.started = True
        self.obj.hasMoreParts = lambda: True
        self.obj.getNextPartOffset = lambda: 240000
        original_build = self.obj.build
        def next_part():
            self.meta.isTranscoded = False
            self.meta.streamUrls = ['/media/part2.mkv']
            original_build()
        self.obj.build = next_part
        self.p.onPlayBackEnded()
        self.assertEqual(self.skips, [True, False])
        self.assertEqual(len(self.p.plays), 2)
        self.assertEqual(self.calls.count('SetSkipNext'), 1)
        self.assertEqual(self.value, '')

    def test_video_playlist_reuses_handler_and_decides_each_item(self):
        self.set_server()
        self.p.video.softReload = lambda **kwargs: None
        playlist = SimpleNamespace(isRemote=False, current=lambda: self.p.video)
        handler = self.p.handler
        for transcoded in (True, False, True):
            self.meta.isTranscoded = transcoded
            self.p.running = False
            self.p.playVideoPlaylist(playlist, handler=handler)
        self.assertEqual(self.skips, [True, False, True])
        self.assertEqual(self.calls.count('GetCapabilities'), 1)
        self.assertEqual(self.calls.count('SetSkipNext'), 2)
        self.assertEqual(self.value, '')

    def test_bind_is_mockable(self):
        self.set_server()
        self.assertIs(p3i_detector.job_supported(), True)
        self.assertEqual(p3i_detector.start('/media/movie.mkv'), 'job-1')
        self.assertEqual(p3i_detector.status('job-1')['status'], 'completed')
        self.assertEqual(p3i_detector.bind('job-1', '/media/movie.mkv'),
                         {'property': 'p3i.detector.binding', 'bindingid': 'bind-1'})
        self.assertEqual(self.calls.count('Bind'), 1)
        self.assertEqual(self.binds, [{'requestid': 'job-1', 'path': '/media/movie.mkv',
                                       'options': {'association': 'source', 'streamindex': -1}}])
        p3i_detector.release('bind-1')
        p3i_detector.cancel('job-1')
        self.assertEqual(self.releases, [{'bindingid': 'bind-1'}])
        self.assertEqual(self.cancels, [{'requestid': 'job-1'}])

    def test_direct_play_binds_and_sets_property_before_play(self):
        self.set_server()
        self.p.wt_detector_requestid = 'job-1'
        self.meta.isTranscoded = False
        self.meta.streamUrls = ['/media/movie.mkv']
        self.meta.isMapped = False    # HTTP direct play: the played url is rewritten
        self.start()
        self.assertEqual(self.calls.count('Bind'), 1)
        self.assertEqual(self.binds[0]['path'], '/media/movie.mkv')
        self.assertEqual(self.binds[0]['options'], {'association': 'source', 'streamindex': -1})
        self.assertEqual(self.bindings, ['bind-1'])
        self.assertNotIn('SetSkipNext', self.calls)
        # the played url carries HTTP params; the bind must still use the original
        self.assertNotEqual(self.p.plays[-1][0], '/media/movie.mkv',
                            "the harness must make the played url differ from "
                            "meta.streamUrls[0], or a bind of the rewritten url "
                            "would pass this test")

    def test_transcoded_never_binds(self):
        self.set_server()
        self.p.wt_detector_requestid = 'job-1'
        self.meta.isTranscoded = True
        self.start()
        self.assertNotIn('Bind', self.calls)
        self.assertEqual(self.bindings, [''])

    def test_bind_releases_only_on_submission_failure(self):
        self.set_server()
        self.p.wt_detector_requestid = 'job-1'
        self.meta.isTranscoded = False
        with patch.object(self.p, 'play', side_effect=ValueError('submission')):
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.calls.count('ReleaseBinding'), 1)
        self.p.running = False
        self.start()
        self.assertEqual(self.calls.count('ReleaseBinding'), 1)

    def test_multipart_skips_the_bind(self):
        self.set_server()
        self.p.wt_detector_requestid = 'job-1'
        self.p.wt_detector_part_index = 0
        self.meta.partIndex = 1
        self.meta.isTranscoded = False
        self.start()
        self.assertNotIn('Bind', self.calls)
