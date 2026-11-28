# coding=utf-8
"""
lib/player.py - theme music fade ownership.

Rapid navigation queues one theme per screen, BGThreader runs three tasks at once, and every window close
spawns its own fade-out thread. They all drive the one global Kodi volume, so a fade that has been superseded
has to drop out instead of finishing its ramp - and must never stop the player, because by then the player is
playing the theme that replaced it.

Supersession is injected on an exact volume write rather than raced in with sleeps, so these stay deterministic.

Importing lib.player starts its monitor thread, which spins until Kodi says abort; setting abort_requested
first lets it exit immediately.
"""

from __future__ import absolute_import

from kodienv import ENV

ENV.abort_requested = True
from lib import player  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakePlayer(object):
    """Only the surface BGMPlayerHandler actually touches."""

    def __init__(self):
        self.bgmGeneration = 0
        self.bgmPlaying = True
        self.stopCalls = 0

    def stop(self):
        self.stopCalls += 1

    def isPlayingAudio(self):
        return True


class RecordingHandler(player.BGMPlayerHandler):
    """
    Records volume writes instead of issuing them, and runs an optional hook on the Nth write so a theme
    switch can be dropped in at a chosen point of the ramp.
    """

    def __init__(self, *args, **kwargs):
        self.volumes = []
        self.onWrite = None
        self.startVolume = 20
        player.BGMPlayerHandler.__init__(self, *args, **kwargs)

    def getVolume(self):
        # _getVolume() delegates here, so this covers both read paths
        return self.startVolume

    def _setVolume(self, vlm, wait=True):
        self.volumes.append(int(vlm))
        if self.onWrite:
            self.onWrite(len(self.volumes))


class BGMFadeOwnershipTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ENV.abort_requested = False
        self.player = FakePlayer()

    def handler(self, rating_key="1", old_volume=None):
        return RecordingHandler(self.player, [None, 20, rating_key], old_volume=old_volume)

    def switchTheme(self):
        """What playBackgroundMusic does when it installs a new handler."""
        self.player.bgmGeneration += 1

    # the theme that still owns the player

    def test_current_fade_runs_its_ramp_and_stops_the_player(self):
        h = self.handler()
        h.fade(0, fast=True, stop=True)

        self.assertTrue(h.volumes)
        self.assertEqual(h.volumes[0], 20)
        self.assertEqual(h.volumes[-1], 1, "fade out must land on 1, never 0")
        self.assertEqual(self.player.stopCalls, 1)

    # superseded by a newer theme

    def test_fade_superseded_before_it_starts_writes_nothing(self):
        h = self.handler()
        self.switchTheme()
        h.fade(0, fast=True, stop=True)

        self.assertEqual(h.volumes, [])
        self.assertEqual(self.player.stopCalls, 0)

    def test_fade_superseded_mid_ramp_drops_out_and_leaves_the_player_alone(self):
        h = self.handler()

        def switchOnSecondWrite(n):
            if n == 2:
                self.switchTheme()

        h.onWrite = switchOnSecondWrite
        h.fade(0, stop=True)

        # stopped at the ownership check of the step after the switch, and never wrote the final target
        self.assertEqual(len(h.volumes), 2)
        self.assertEqual(self.player.stopCalls, 0,
                         "a superseded fade stopping the player kills the theme that replaced it")

    def test_newer_fade_on_the_same_handler_retires_the_older_one(self):
        h = self.handler()

        def startAnotherFade(n):
            if n == 1:
                h.fadeSeq += 1  # what a second fade() entry does

        h.onWrite = startAnotherFade
        h.fade(0, stop=True)

        self.assertEqual(len(h.volumes), 1)
        self.assertEqual(self.player.stopCalls, 0)

    # the user's volume across a switch

    def test_old_volume_carries_across_a_theme_switch(self):
        h = self.handler(old_volume=42)
        self.assertEqual(h.oldVolume, 42,
                         "re-reading here records a mid-fade volume as the user's own")

    def test_old_volume_is_read_when_no_theme_preceded_us(self):
        self.assertEqual(self.handler().oldVolume, 20)

    # stop events

    def test_stop_for_the_current_theme_restores_the_volume(self):
        h = self.handler(old_volume=55)
        h.onPlayBackStopped(rm=False)

        self.assertFalse(self.player.bgmPlaying)
        self.assertEqual(h.volumes, [55])

    def test_fade_out_with_audio_already_gone_restores_volume_when_current(self):
        h = self.handler(old_volume=55)
        self.player.isPlayingAudio = lambda: False
        h.fadeOut()

        self.assertEqual(h.volumes, [55])

    def test_fade_out_with_audio_already_gone_leaves_a_superseded_theme_alone(self):
        # the deferred thread can land here after a new theme replaced us but before its audio is up
        h = self.handler(old_volume=55)
        self.player.isPlayingAudio = lambda: False
        self.switchTheme()
        h.fadeOut()

        self.assertEqual(h.volumes, [],
                         "the last unguarded volume write in the BGM path")

    def test_stop_for_a_superseded_theme_leaves_volume_and_state_alone(self):
        h = self.handler(old_volume=55)
        self.switchTheme()
        h.onPlayBackStopped(rm=False)

        self.assertTrue(self.player.bgmPlaying,
                        "the theme that replaced ours is still playing")
        self.assertEqual(h.volumes, [],
                         "restoring the pre-BGM volume here would drop the live theme mid-playback")
