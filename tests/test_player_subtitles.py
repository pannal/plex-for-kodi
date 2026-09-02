# coding=utf-8
"""Regression coverage for subtitle activation after Kodi opens the AV renderer."""

from __future__ import absolute_import

from unittest import mock

from lib import player as player_module

from .base import KodiTestCase


class FakeMonitor(object):
    def __init__(self, on_wait=None):
        self.waits = []
        self.on_wait = on_wait

    def waitForAbort(self, timeout):
        self.waits.append(timeout)
        if self.on_wait:
            self.on_wait(timeout)
        return False

    def abortRequested(self):
        return False


class FakePlayer(object):
    def __init__(self, video):
        self.video = video
        self.playerObject = None
        self.calls = []

    def setSubtitleStream(self, index):
        self.calls.append(("setSubtitleStream", index))

    def showSubtitles(self, visible):
        self.calls.append(("showSubtitles", visible))


class EmbeddedSubtitleActivationTest(KodiTestCase):
    @classmethod
    def tearDownClass(cls):
        # Importing lib.player starts its process-wide monitor.
        player_module.PLAYER._closed = True
        player_module.PLAYER.thread.join(1)

    def make_handler(self, subtitle_index=2):
        video = mock.Mock()
        video._current_subtitle_idx = subtitle_index

        handler = player_module.SeekPlayerHandler.__new__(player_module.SeekPlayerHandler)
        handler.player = FakePlayer(video)
        handler.dialog = mock.Mock()
        handler.playbackID = "playback-1"
        handler._subtitleActivationGeneration = 4
        handler._absSeekSettled = True
        handler._subtitleStreamOffset = None
        return handler, video

    def test_matching_index_is_reopened_after_av_started(self):
        handler, video = self.make_handler()
        monitor = FakeMonitor()

        with mock.patch.object(player_module.util, "MONITOR", monitor), \
                mock.patch.object(player_module.util, "CE_NEEDS_EMBEDDED_SEEKBACK", False), \
                mock.patch.object(player_module.kodijsonrpc.rpc.Player, "GetActivePlayers",
                                  return_value=[{"playerid": 1}]), \
                mock.patch.object(player_module.kodijsonrpc.rpc.Player, "GetProperties",
                                  return_value={"currentsubtitle": {"index": 2}}):
            handler._activateEmbeddedSubtitle(video, "playback-1", 4)

        self.assertEqual([0.2, 0.05], monitor.waits)
        self.assertEqual([
            ("setSubtitleStream", -1),
            ("setSubtitleStream", 2),
            ("showSubtitles", True),
        ], handler.player.calls)

    def test_deferred_activation_does_not_touch_a_replaced_playback(self):
        handler, video = self.make_handler()

        def replace_playback(timeout):
            if timeout == 0.2:
                handler.player.video = mock.Mock()

        monitor = FakeMonitor(on_wait=replace_playback)
        with mock.patch.object(player_module.util, "MONITOR", monitor), \
                mock.patch.object(player_module.kodijsonrpc.rpc.Player, "GetActivePlayers") as active_players:
            handler._activateEmbeddedSubtitle(video, "playback-1", 4)

        active_players.assert_not_called()
        self.assertEqual([], handler.player.calls)

    def test_deferred_activation_does_not_override_a_later_subtitle_choice(self):
        handler, video = self.make_handler()

        def replace_selection(timeout):
            if timeout == 0.05:
                video._current_subtitle_idx = 3

        monitor = FakeMonitor(on_wait=replace_selection)
        with mock.patch.object(player_module.util, "MONITOR", monitor), \
                mock.patch.object(player_module.util, "CE_NEEDS_EMBEDDED_SEEKBACK", False), \
                mock.patch.object(player_module.kodijsonrpc.rpc.Player, "GetActivePlayers",
                                  return_value=[{"playerid": 1}]), \
                mock.patch.object(player_module.kodijsonrpc.rpc.Player, "GetProperties",
                                  return_value={"currentsubtitle": {"index": 2}}):
            handler._activateEmbeddedSubtitle(video, "playback-1", 4)

        self.assertEqual([
            ("setSubtitleStream", -1),
            ("setSubtitleStream", 3),
            ("showSubtitles", True),
        ], handler.player.calls)
