# coding=utf-8
"""
plexnet.http.HttpRequest._startAsync - a request that fails with a connection error.

The callback must still run, as it does for a timeout. Otherwise a server
reachability test stays pending forever and every later test of that
connection is skipped ("has pending request"), so a server that was offline
when PM4K started is never found again.
"""

from __future__ import absolute_import

import requests

try:
    from unittest import mock
except ImportError:
    import mock

from .base import KodiTestCase, ensure_plex_interface


class ConnectionErrorCallbackTest(KodiTestCase):
    def test_connection_error_calls_back_with_a_failed_response(self):
        ensure_plex_interface()
        from plexnet import http, util

        responses = []
        request = http.HttpRequest("http://10.0.0.5:32400/")
        context = request.createRequestContext("reachability", mock.Mock(side_effect=lambda req, res, ctx: responses.append(res)))

        with mock.patch.object(util, "APP", mock.Mock()), \
                mock.patch.object(request.session, "get", side_effect=requests.exceptions.ConnectionError("refused")):
            request._startAsync(context=context)

        self.assertEqual(1, len(responses))
        self.assertFalse(responses[0].isSuccess())
