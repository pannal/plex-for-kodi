# coding=utf-8
"""Replay retained playback dialogs beneath a startup blackout.

The native boundaries model registration order and retired IDs, not rendering
or Kodi's callback scheduling.
"""
from __future__ import absolute_import

from types import SimpleNamespace
from unittest.mock import Mock, patch

from kodienv import ENV
ENV.abort_requested = True
from lib.windows import blackoutdialog, kodigui, seekdialog
from tests.base import KodiTestCase
from tests.test_dropdown import FakeAction


SEEK_ID = 13012
BLACKOUT_ID = 13011


class PlaybackDialog(seekdialog.SeekDialog):
    def __init__(self):
        # The stub has no native constructor; give its own property store an ID.
        self.windowId = SEEK_ID
        kodigui.BaseDialog.__init__(self)
        self.handler = SimpleNamespace(
            queuingNext=False, queuingSpecific=False,
            player=SimpleNamespace(STATE_STOPPED='stopped', STATE_PLAYING='playing',
                                   playState='playing', trigger=Mock()))
        self.focus = self.NO_OSD_BUTTON_ID
        self._lastAction = self._osdHideAnimationTimeout = None
        self._ignoreInput = self._ignoreTick = False
        self._playerDebugActive = self._playerNativePPIActive = False
        self._hideDelay = 4
        self.clientLikePlex = True
        self.ldTimer = False
        self.sendTimeline = Mock()
        self.killTimeKeeper = Mock()
        # Control layout and media metadata are outside this lifecycle replay.
        for name in ('resetSeeking', 'updateProperties', 'updateChapters',
                     'videoSettingsHaveChanged', 'updateProgress'):
            setattr(self, name, Mock())

    def onFirstInit(self):
        self.setBoolProperty('initialized', True)

    def getFocusId(self):
        return self.focus

    def setFocusId(self, control_id):
        self.focus = control_id


class DialogIdentityTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.live = {SEEK_ID, BLACKOUT_ID, ENV.current_window_id}
        self.active = []
        self.window = kodigui.xbmcgui.Window
        last_dialog_id = kodigui.BaseFunctions.lastDialogID
        self.addCleanup(setattr, kodigui.BaseFunctions, 'lastDialogID', last_dialog_id)
        self.patch(kodigui.xbmcgui, 'Window', self.lookup)
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'show', lambda dialog: self.show(dialog))
        self.patch(kodigui.xbmcgui.WindowXMLDialog, 'close', lambda dialog: self.close(dialog))

    def patch(self, obj, name, value):
        patcher = patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def lookup(self, window_id):
        if window_id not in self.live:
            raise RuntimeError('Window id does not exist')
        return self.window(window_id)

    def show(self, dialog):
        # Kodi does not move an already registered dialog to the top on show.
        if dialog.windowId not in self.active:
            self.active.append(dialog.windowId)
        ENV.current_dialog_id = self.active[-1]
        dialog._onInit()

    def close(self, dialog):
        if dialog.windowId in self.active:
            self.active.remove(dialog.windowId)
        ENV.current_dialog_id = self.active[-1] if self.active else 0

    def blackout(self):
        dialog = blackoutdialog.BlackoutDialog.__new__(blackoutdialog.BlackoutDialog)
        dialog.windowId = BLACKOUT_ID
        blackoutdialog.BlackoutDialog.__init__(dialog)
        self.addCleanup(dialog.doClose)
        return dialog

    def test_next_under_blackout_preserves_identity_and_up_down_open_osd(self):
        dialog = PlaybackDialog()
        self.addCleanup(kodigui.BaseDialog.doClose, dialog)
        dialog.show()
        self.assertEqual(dialog._winID, SEEK_ID)

        dialog.onClick(dialog.NEXT_BUTTON_ID)
        self.assertTrue(dialog.handler.queuingNext)
        self.assertTrue(dialog._ignoreInput)
        dialog.player.trigger.assert_called_once_with('action', action='next')

        blackout = self.blackout()
        blackout.show()
        self.assertEqual(ENV.current_dialog_id, BLACKOUT_ID)
        dialog.show()  # Same instance, as on the E02 -> E03 transition.
        dialog.handler.queuingNext = False
        dialog.onPlayBackStarted()
        self.assertFalse(dialog._ignoreInput)

        blackout.doClose()
        self.live.remove(BLACKOUT_ID)  # Handler drops the retired native window.
        self.assertEqual(ENV.current_dialog_id, SEEK_ID)
        for action_id in (kodigui.xbmcgui.ACTION_MOVE_UP, kodigui.xbmcgui.ACTION_MOVE_DOWN):
            with self.subTest(action=action_id):
                dialog.setProperty('show.OSD', '')
                dialog.focus = dialog.NO_OSD_BUTTON_ID
                dialog.onAction(FakeAction(action_id))
                self.assertEqual(dialog.getProperty('show.OSD'), '1')
                self.assertEqual(dialog.focus, dialog.PLAY_PAUSE_BUTTON_ID)
                self.assertEqual(dialog._winID, SEEK_ID)
                self.assertEqual(kodigui.BaseFunctions.lastDialogID, SEEK_ID)
        self.assertFalse(ENV.logged('Missing window'))

    def test_first_init_replaces_provisional_id_then_reinit_keeps_own_id(self):
        dialog = PlaybackDialog()
        self.addCleanup(kodigui.BaseDialog.doClose, dialog)
        dialog._winID = ENV.current_window_id  # Historical pre-show property fallback.
        dialog.show()
        self.assertEqual(dialog._winID, SEEK_ID)
        blackout = self.blackout()
        blackout.show()
        dialog.show()
        self.assertEqual(dialog._winID, SEEK_ID)
        self.assertEqual(kodigui.BaseFunctions.lastDialogID, SEEK_ID)

    def test_pre_show_properties_belong_only_to_dialog(self):
        dialog = PlaybackDialog()
        self.assertEqual(dialog._winID, '')
        dialog.setProperty('video.title', 'Episode 3')
        self.assertEqual(dialog.getProperty('video.title'), 'Episode 3')
        self.assertNotIn('video.title', ENV.window_props[ENV.current_window_id])

    def test_closing_dialog_does_not_publish_properties(self):
        dialog = PlaybackDialog()
        dialog.setProperty('show.OSD', '')
        dialog._closing = True
        dialog.setProperty('show.OSD', '1')
        self.assertEqual(dialog.getProperty('show.OSD'), '')
