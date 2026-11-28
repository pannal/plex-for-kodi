# coding=utf-8
"""
lib/windows/dropdown.py - the popup menu's action handling.

Kodi turns an Enter held for 500ms into ACTION_CONTEXT_MENU. Since a dropdown is
usually opened *by* long-pressing Enter, the next press often arrives the same way,
and the dialog used to ignore it: the menu sat there unresponsive to the very key
that had opened it, which reads as a frozen addon (see the 2026-07-25 report).

Importing lib/windows/ starts lib.player's monitor thread, which spins until Kodi
says abort; setting abort_requested first lets it exit immediately.
"""

from __future__ import absolute_import

import xbmcgui
from kodienv import ENV

ENV.abort_requested = True
from lib.windows import dropdown, kodigui  # noqa: E402

from .base import KodiTestCase  # noqa: E402


class FakeAction(object):
    """xbmcgui.Action compares equal to its id, which is how the addon tests actions."""

    def __init__(self, action_id):
        self.action_id = action_id

    def __eq__(self, other):
        return self.action_id == other

    def getId(self):
        return self.action_id


def dialog(moving=False, focus_id=0):
    """A DropdownDialog without a Kodi window behind it."""
    dlg = dropdown.DropdownDialog.__new__(dropdown.DropdownDialog)
    dlg.choice = None
    dlg.movingItem = "an item" if moving else None
    dlg.roundRobin = True
    dlg.suboptionCallback = None
    dlg.optionsList = None
    dlg.lastSelectedItem = None
    dlg._lastMoveTime = 0
    dlg.closed = []
    dlg.doClose = lambda **kw: dlg.closed.append(True)
    dlg.getFocusId = lambda: focus_id
    return dlg


class DropdownContextMenuTest(KodiTestCase):
    def test_a_held_enter_dismisses_the_menu(self):
        dlg = dialog()
        dlg.onAction(FakeAction(xbmcgui.ACTION_CONTEXT_MENU))

        self.assertEqual([True], dlg.closed)

    def test_dismissing_yields_no_choice(self):
        # showDropdown() returns the dialog's choice, so None means "cancelled"
        dlg = dialog()
        dlg.onAction(FakeAction(xbmcgui.ACTION_CONTEXT_MENU))

        self.assertIsNone(dlg.choice)

    def test_move_mode_still_ignores_it(self):
        # while moving an item, only up/down, select and back mean anything
        dlg = dialog(moving=True)
        dlg.onAction(FakeAction(xbmcgui.ACTION_CONTEXT_MENU))

        self.assertEqual([], dlg.closed)

    def test_other_actions_still_reach_the_base_handler(self):
        dlg = dialog()
        seen = []
        original = kodigui.BaseDialog.onAction
        kodigui.BaseDialog.onAction = lambda self, action: seen.append(action.getId())
        try:
            dlg.onAction(FakeAction(xbmcgui.ACTION_NAV_BACK))
        finally:
            kodigui.BaseDialog.onAction = original

        self.assertEqual([xbmcgui.ACTION_NAV_BACK], seen)
        self.assertEqual([], dlg.closed)
