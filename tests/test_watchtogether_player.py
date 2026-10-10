# coding=utf-8
"""lib/player.py — the Watch Together local-broadcast gate (spec: phase 2).

The gate is two attributes on PlexPlayer: wt_broadcast (callback into the
bridge, None until a room is joined) and wt_applying_remote (a monotonic
deadline set by the bridge before it applies remote state)."""

from __future__ import absolute_import

from kodienv import ENV

ENV.abort_requested = True
from lib import player  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakeHandler(object):
    def __init__(self):
        self.calls = []

    def onPlayBackPaused(self):
        self.calls.append("paused")

    def onPlayBackResumed(self):
        self.calls.append("resumed")

    def onPlayBackSeek(self, time, offset):
        self.calls.append("seek")


class WTGateTest(KodiTestCase):
    def bare_player(self):
        p = player.PlexPlayer.__new__(player.PlexPlayer)
        p.sessionID = "sid"
        p.handler = FakeHandler()
        p.wt_applying_remote = 0.0
        self.fired = []
        p.wt_broadcast = self.fired.append
        return p

    def test_pause_reaches_the_bridge(self):
        p = self.bare_player()
        p.onPlayBackPaused()
        self.assertEqual(self.fired, ["pause"])
        self.assertEqual(p.handler.calls, ["paused"])

    def test_resume_reaches_the_bridge(self):
        p = self.bare_player()
        p.onPlayBackResumed()
        self.assertEqual(self.fired, ["play"])

    def test_seek_reaches_the_bridge(self):
        p = self.bare_player()
        p.onPlayBackSeek(12, 4000)
        self.assertEqual(self.fired, ["seek"])

    def test_armed_deadline_swallows_the_echo(self):
        p = self.bare_player()
        p.wt_applying_remote = float("inf")     # bridge applied remote state
        p.onPlayBackPaused()
        p.onPlayBackResumed()
        p.onPlayBackSeek(9, -1000)
        self.assertEqual(self.fired, [])
        self.assertEqual(p.handler.calls, ["paused", "resumed", "seek"],
                         "the local handler path still runs")

    def test_disarmed_deadline_forwards_again(self):
        p = self.bare_player()
        p.wt_applying_remote = float("inf")
        p.onPlayBackPaused()
        p.wt_applying_remote = 0.0
        p.onPlayBackPaused()
        self.assertEqual(self.fired, ["pause"])

    def test_no_plex_session_means_no_broadcast(self):
        p = self.bare_player()
        p.sessionID = None
        p.onPlayBackPaused()
        self.assertEqual(self.fired, [])

    def test_no_bridge_listener_is_a_noop(self):
        p = self.bare_player()
        p.wt_broadcast = None
        p.onPlayBackPaused()               # must not raise
        self.assertEqual(p.handler.calls, ["paused"])
