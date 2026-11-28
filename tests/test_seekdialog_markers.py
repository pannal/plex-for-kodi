# coding=utf-8
"""Marker timing uses landed time; signalling protects only overlays needing it."""
from __future__ import absolute_import

from types import SimpleNamespace
from unittest.mock import patch

import json

from kodienv import ENV
ENV.abort_requested = True
from lib import player
from lib.windows import seekdialog
from tests.base import KodiTestCase
from tests.test_osd import PICTURE_LABEL, BUTTON_LABEL, WINDOW_ID, picture, button


class RecordingDialog(seekdialog.SeekDialog):
    def __init__(self):
        p = SimpleNamespace(isExternal=False, playerObject=SimpleNamespace(startOffset=0),
                            playState='playing', STATE_PLAYING='playing', STATE_PAUSED='paused', position=1490.689)
        p.getTime = lambda: p.position
        self.handler = SimpleNamespace(player=p, seekOnStart=None, waitingForSOS=False,
                                       seekBackTo=None, playlist=None, creditMarkerHit=None)
        self.props = {'initialized': '1'}
        self._winID = WINDOW_ID
        self._closing = False
        self.playlistDialog = None
        self.initialized = True
        self._ignoreTick = False
        self.offset = 1492040
        self.selectedOffset = self.offset
        self.pausedAt = None
        self.ldTimer = False
        self.idleTime = None
        self.hasDialog = False
        self._playlistDialogVisible = False
        self._seeking = self._applyingSeek = False
        self.autoSeekTimeout = None
        self.timeout = float('inf')
        self.useAlternateSeek = False
        self.isDirectPlay = True
        self.baseOffset = 0
        self._duration = 1600000
        self._enableMarkerSkip = True
        self.showSkipIntro = self.showSkipCredits = True
        self.showIntroSkipEarly = False
        self.bingeMode = False
        self.autoSkipCredits = True
        self._creditsSkipShownStarted = None
        self.skipCreditsButtonTimeout = 100
        self._currentMarker = None
        self._navigatedViaMarkerOrChapter = False
        self.lastFocusID = None
        self.osd = False
        self.seeks = []
        self.updated = []
        self.resets = 0
        m = seekdialog.MARKERS['credits'].copy()
        m.update(marker_type='credits', marker=seekdialog.Marker({
            'startTimeOffset':1495040, 'endTimeOffset':1600000, 'final':True}))
        self._markers = [m]

    def setProperty(self, name, value):
        self.props[name] = value

    def getProperty(self, name):
        return self.props.get(name, '')

    def getBoolProperty(self, name):
        return bool(self.getProperty(name))

    def osdVisible(self):
        return self.osd

    def updateCurrent(self, **kwargs):
        self.updated.append(self.offset)

    def resetSeeking(self):
        self.resets += 1

    def resetAutoSeekTimer(self, value):
        self.autoSeekTimeout = None

    def doSeek(self, *args, **kwargs):
        self.seeks.append(self.offset)


class SeekDialogMarkerTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.setting = patch.object(seekdialog.util.addonSettings, 'autoSkipOffset', 1)
        self.setting.start()
        self.addCleanup(self.setting.stop)
        self.d = RecordingDialog()
        ENV.infolabels[PICTURE_LABEL] = json.dumps(picture())
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button())

    def test_optimistic_chapter_target_does_not_flash_then_hide_countdown(self):
        visible = []
        names = []
        # Device E1: requested early-show boundary1492040, actual playback is behind it.
        for position in (1490.689, 1491.809, 1492.889, 1494.089, 1495.089):
            self.d.player.position = position
            self.d.tick()
            visible.append(bool(self.d.getProperty('show.markerSkip')))
            names.append(self.d.getProperty('skipMarkerName'))
        self.assertEqual(visible, [False, False, True, True, True])
        self.assertEqual(names[2:], ['Skipping credits (3)', 'Skipping credits (2)', 'Skipping credits (1)'])
        self.assertEqual(self.d.seeks, [], 'keyframe preroll must not cause a corrective seek')

    def test_backward_seek_hides_marker_on_first_actual_position_tick(self):
        self.d.player.position = 1493
        self.d.tick()
        self.assertTrue(self.d.getProperty('show.markerSkip'))
        self.d.player.position = 1400
        self.d.tick()
        self.assertFalse(self.d.getProperty('show.markerSkip'))
        self.assertIsNone(self.d._markers[0]['countdown'])

    def test_current_position_crossing_marker_boundary_is_not_one_tick_late(self):
        self.d.offset = 1491000
        self.d.player.position = 1493
        self.d.tick()
        self.assertTrue(self.d.getProperty('show.markerSkip'))

    def test_buffer_wait_refreshes_position_after_wait(self):
        self.d.offset = 1491000
        def buffered():
            self.d.player.position = 1493
            return True
        self.d.waitForBuffer = buffered
        self.d.tick(waitForBuffer=True)
        self.assertTrue(self.d.getProperty('show.markerSkip'))
        self.assertEqual(self.d.offset, 1493000)

    def test_cancelled_buffer_wait_does_not_refresh_or_advance_markers(self):
        self.d.waitForBuffer = lambda: False
        self.d.tick(waitForBuffer=True)
        self.assertEqual(self.d.offset, 1492040)
        self.assertIsNone(self.d._currentMarker)

    def test_stopped_player_resets_without_advancing_marker_countdown(self):
        def stopped():
            raise RuntimeError('Stopped')
        self.d.player.getTime = stopped
        self.d.tick()
        self.assertEqual(self.d.resets, 1)
        self.assertIsNone(self.d._currentMarker)

    def test_startup_seek_and_explicit_preinit_offset_keep_their_existing_path(self):
        for field in ('seekOnStart', 'waitingForSOS', 'seekBackTo'):
            with self.subTest(field=field):
                d = RecordingDialog()
                d.player.position = 1493
                setattr(d.handler, field, 5000)
                d.tick()
                self.assertIsNone(d._currentMarker)
        self.d.initialized = False
        self.d.tick(offset=5000)
        self.assertEqual(self.d.seeks, [5000])
        self.assertIsNone(self.d._currentMarker)

    def test_osd_pauses_countdown_and_cancel_hides_it_without_seek(self):
        self.d.player.position = 1493
        self.d.tick()
        count = self.d._markers[0]['countdown']
        self.d.osd = True
        self.d.tick()
        self.assertEqual(self.d._markers[0]['countdown'], count)
        self.d.displayMarkers(cancelTimer=True)
        self.assertFalse(self.d.getProperty('show.markerSkip'))
        self.assertEqual(self.d.seeks, [])

    def test_contained_standalone_intro_and_credits_buttons_do_not_signal_osd(self):
        for marker_type in ('intro', 'credits'):
            for auto_skip in (False, True):
                with self.subTest(marker_type=marker_type, auto_skip=auto_skip):
                    d = RecordingDialog()
                    marker = seekdialog.MARKERS[marker_type].copy()
                    marker.update(marker_type=marker_type, marker=d._markers[0]['marker'])
                    d._markers = [marker]
                    setattr(d, marker['markerAutoSkip'], auto_skip)
                    setattr(d, marker['markerAutoSkipShownTimer'], None)
                    setattr(d, marker['markerSkipBtnTimeout'], 100)
                    d.player.position = 1493
                    d.tick()
                    self.assertTrue(d.getProperty('show.markerSkip'))
                    self.assertFalse(d.getProperty('show.markerSkip_OSDOnly'))
                    self.assertFalse(d.getProperty('show.OSD'))
                    self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_marker_timeout_does_not_signal_osd(self):
        self.d.autoSkipCredits = False
        self.d.player.position = 1493
        self.d.tick()
        self.assertTrue(self.d.getProperty('show.markerSkip'))
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        self.d._creditsSkipShownStarted = 0
        self.d.tick()
        self.assertTrue(self.d.getProperty('show.markerSkip_OSDOnly'))
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_osd_show_hide_with_marker_does_not_reassert_signal(self):
        self.d.playlistDialog = None
        with patch.object(self.d, 'osdVisible', lambda: bool(self.d.getProperty('show.OSD'))):
            self.d.player.position = 1493
            self.d.tick()
            self.d.showOSD(focusButton=False)
            self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
            self.d.tick()
            self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
            self.d.hideOSD()
            self.assertTrue(self.d.getProperty('show.markerSkip'))
            self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
            self.d.tick()
            self.assertTrue(self.d.getProperty('show.markerSkip'))
            self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_marker_disappearance_and_cancellation_keep_open_osd_signalled(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                d = RecordingDialog()
                d.player.position = 1493
                d.tick()
                d.showOSD(focusButton=False)
                if cancel:
                    d.displayMarkers(cancelTimer=True)
                else:
                    d.player.position = 1400
                    d.tick()
                self.assertFalse(d.getProperty('show.markerSkip'))
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
                d.hideOSD(closing=True)
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_unavailable_geometry_restores_old_visible_marker_signal(self):
        for label in (PICTURE_LABEL, BUTTON_LABEL):
            with self.subTest(label=label):
                ENV.infolabels[PICTURE_LABEL] = json.dumps(picture())
                ENV.infolabels[BUTTON_LABEL] = json.dumps(button())
                ENV.infolabels[label] = ''
                d = RecordingDialog()
                d.player.position = 1493
                d.tick()
                self.assertTrue(d.getProperty('show.markerSkip'))
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
                d.displayMarkers(cancelTimer=True)
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_outside_marker_signal_clears_on_timeout_and_disappearance(self):
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        for disappear in (False, True):
            with self.subTest(disappear=disappear):
                d = RecordingDialog()
                d.autoSkipCredits = False
                d.player.position = 1493
                d.tick()
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
                if disappear:
                    d.player.position = 1400
                else:
                    d._creditsSkipShownStarted = 0
                d.tick()
                self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_paused_tick_refreshes_geometry_without_changing_marker_countdown(self):
        self.d.player.position = 1493
        self.d.tick()
        countdown = self.d._markers[0]['countdown']
        self.d.player.playState = self.d.player.STATE_PAUSED
        self.d.pausedAt = 0
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button())
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        ENV.infolabels[PICTURE_LABEL] = ''
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        self.assertEqual(self.d._markers[0]['countdown'], countdown)
        self.assertEqual(self.d.seeks, [])

    def test_hiding_full_osd_keeps_protection_for_an_outside_marker(self):
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        self.d.player.position = 1493
        self.d.tick()
        self.d.showOSD(focusButton=False)
        self.d.hideOSD()
        self.assertTrue(self.d.getProperty('show.markerSkip'))
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')

    def test_closing_fences_late_marker_signal_refresh(self):
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        self.d.player.position = 1493
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        self.d.hideOSD(closing=True)
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        seekdialog.util.setGlobalProperty('osd_active', '1')  # a new playback owns it now
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')

    def test_direct_close_clears_and_fences_signal(self):
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        self.d.player.position = 1493
        self.d.tick()
        with patch.object(self.d, 'killTimeKeeper'), \
                patch.object(seekdialog.kodigui.BaseDialog, 'doClose'):
            self.d.doClose()
        self.assertTrue(self.d._closing)
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_closing_during_snapshot_read_does_not_reassert_signal(self):
        self.d.setProperty('show.markerSkip', '1')

        def close_during_read(window_id, control_id):
            self.d.hideOSD(closing=True)
            return True

        with patch.object(seekdialog, 'markerNeedsOSD', side_effect=close_during_read):
            self.d._updateOSDSignal()
        self.assertTrue(self.d._closing)
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_osd_opening_during_snapshot_read_keeps_full_osd_signal(self):
        self.d.setProperty('show.markerSkip', '1')

        def open_during_read(window_id, control_id):
            self.d.showOSD(focusButton=False)
            return False

        with patch.object(seekdialog, 'markerNeedsOSD', side_effect=open_during_read):
            self.d._updateOSDSignal()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')

    def test_marker_hidden_during_snapshot_read_does_not_reassert_signal(self):
        self.d.setProperty('show.markerSkip', '1')

        def hide_during_read(window_id, control_id):
            self.d.setProperty('show.markerSkip', '')
            return True

        with patch.object(seekdialog, 'markerNeedsOSD', side_effect=hide_during_read):
            self.d._updateOSDSignal()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_hidden_parent_and_marker_reset_clear_marker_owned_signal(self):
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button(bottom=960))
        self.d.player.position = 1493
        self.d.tick()
        self.d.setProperty('initialized', '')
        self.d._updateOSDSignal()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        self.d.setProperty('initialized', '1')
        self.d._updateOSDSignal()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        self.d.resetMarkerStates()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')

    def test_metadata_only_marker_queries_do_not_write_osd_signal(self):
        with patch.object(seekdialog.util, 'setGlobalProperty') as write:
            self.d.displayMarkers(setMarkersSkipped=True, offset=1)
            self.d._markers = []
            self.d.displayMarkers(onlyReturnIntroMD=True, offset=1000)
            # An early intro query returns before display/visibility handling.
            marker = seekdialog.MARKERS['intro'].copy()
            marker.update(marker_type='intro', marker=seekdialog.Marker({
                'startTimeOffset': 1000, 'endTimeOffset': 5000}))
            self.d._markers = [marker]
            self.d.autoSkipIntro = True
            self.d.offset = 1000
            self.d.displayMarkers(onlyReturnIntroMD=True, offset=1000)
        write.assert_not_called()

    def test_back_hides_marker_and_clears_its_fallback_signal(self):
        class Action(object):
            def getId(self):
                return seekdialog.xbmcgui.ACTION_NAV_BACK

            def __eq__(self, other):
                return self.getId() == other

        ENV.infolabels[PICTURE_LABEL] = ''
        self.d.autoSkipCredits = False
        self.d.player.position = 1493
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        self.d._lastAction = None
        self.d._ignoreInput = self.d._playerNativePPIActive = False
        with patch.object(self.d, 'resetTimeout'), \
                patch.object(self.d, 'getFocusId', return_value=self.d.SKIP_MARKER_BUTTON_ID), \
                patch.object(seekdialog.util.MONITOR, 'tv_standby', False), \
                patch.object(seekdialog.util, 'ERROR', side_effect=AssertionError('action failed')):
            self.d.onAction(Action())
        self.assertFalse(self.d.getProperty('show.markerSkip'))
        self.assertTrue(self.d.getProperty('show.markerSkip_OSDOnly'))
        self.assertTrue(self.d._currentMarker['hidden'])
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
        self.assertEqual(self.d.seeks, [])

    def test_auto_skip_clears_marker_signal_before_seeking(self):
        ENV.infolabels[PICTURE_LABEL] = ''
        self.d.player.position = 1493
        self.d.tick()
        self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '1')
        self.d._currentMarker['countdown'] = 0
        self.d._currentMarker['marker'].final = False

        def seek(target):
            self.assertEqual(seekdialog.util.getGlobalProperty('osd_active'), '')
            self.assertEqual(target, 1600000 + seekdialog.MARKER_END_JUMP_OFF)

        with patch.object(self.d, 'doSeek', side_effect=seek) as call:
            self.assertTrue(self.d.displayMarkers())
        call.assert_called_once()
        self.assertFalse(self.d.getProperty('show.markerSkip'))
        self.assertIsNone(self.d._currentMarker['countdown'])
