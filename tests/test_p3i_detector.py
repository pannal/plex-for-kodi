# coding=utf-8
"""lib/p3i_detector.py — the explicit job client (detect→bind→play pre-scan)."""

from __future__ import absolute_import

import json
from unittest.mock import patch

from tests.base import KodiTestCase
from lib import p3i_detector


class JobClientTest(KodiTestCase):
    """Scripts xbmc.executeJSONRPC and asserts the exact method/params shapes."""

    def setUp(self):
        super(JobClientTest, self).setUp()
        self.calls = []
        self.results = {}
        p3i_detector._job_supported = None
        patcher = patch.object(p3i_detector.xbmc, 'executeJSONRPC', self.fake_rpc)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_rpc(self, raw):
        request = json.loads(raw)
        method = request['method'].split('.')[-1]
        self.calls.append((method, request.get('params')))
        result = self.results.get(method)
        if result is None:
            # Stock Kodi: the optional extension is not registered.
            return json.dumps({'jsonrpc': '2.0', 'error': {'code': -32601}, 'id': 1})
        return json.dumps({'jsonrpc': '2.0', 'result': result, 'id': 1})

    def _jobs_available(self):
        self.results['GetCapabilities'] = {'version': 1, 'supported': True, 'resultbinding': 1}

    def test_job_supported_probed_once_and_false_on_stock_kodi(self):
        self.assertIs(p3i_detector.job_supported(), False)
        self.assertIs(p3i_detector.job_supported(), False)
        self.assertEqual(self.calls, [('GetCapabilities', None)])

    def test_job_supported_requires_resultbinding(self):
        self.results['GetCapabilities'] = {'version': 1, 'supported': True, 'ownedskip': True}
        self.assertIs(p3i_detector.job_supported(), False)

    def test_start_returns_requestid_on_accepted(self):
        self._jobs_available()
        self.results['Start'] = {'status': 'accepted', 'requestid': 'job-1'}
        self.assertEqual(p3i_detector.start('/media/movie.mkv'), 'job-1')
        self.assertEqual(self.calls[-1][1], {'path': '/media/movie.mkv',
                                             'options': {'streamindex': -1, 'allowhttp': True}})

    def test_start_returns_none_on_non_accepted(self):
        self._jobs_available()
        self.results['Start'] = {'status': 'busy'}
        self.assertIsNone(p3i_detector.start('/media/movie.mkv'))

    def test_start_returns_none_when_unsupported(self):
        p3i_detector._job_supported = False
        self.assertIsNone(p3i_detector.start('/media/movie.mkv'))
        self.assertEqual(self.calls, [])

    def test_status_returns_the_result_dict(self):
        self.results['GetStatus'] = {'status': 'completed', 'requestid': 'job-1'}
        self.assertEqual(p3i_detector.status('job-1')['status'], 'completed')

    def test_bind_returns_property_and_bindingid(self):
        self._jobs_available()
        self.results['Bind'] = {'status': 'ready', 'bindingid': 'bind-1',
                                'property': 'p3i.detector.binding'}
        self.assertEqual(p3i_detector.bind('job-1', '/media/movie.mkv'),
                         {'property': 'p3i.detector.binding', 'bindingid': 'bind-1'})

    def test_bind_returns_none_on_not_ready(self):
        self._jobs_available()
        self.results['Bind'] = {'status': 'not_found'}
        self.assertIsNone(p3i_detector.bind('job-1', '/media/movie.mkv'))

    def test_release_and_cancel_call_the_rpc(self):
        p3i_detector.release('bind-1')
        p3i_detector.cancel('job-1')
        self.assertEqual(self.calls, [
            ('ReleaseBinding', {'bindingid': 'bind-1'}),
            ('Cancel', {'requestid': 'job-1'}),
        ])
        p3i_detector.release(None)
        p3i_detector.cancel(None)
        self.assertEqual(len(self.calls), 2)
