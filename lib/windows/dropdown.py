# coding=utf-8
from __future__ import absolute_import

import time

from kodi_six import xbmc, xbmcgui

from lib import util
from . import kodigui

SEPARATOR = None


class DropdownDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-dropdown.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080
    optionHeight = util.vscalei(66)
    separatorHeight = util.vscalei(2)
    dropWidth = 360
    borderOff = -20

    GROUP_ID = 100
    OPTIONS_LIST_ID = 250
    SCROLLBAR_ID = 1152

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.options = kwargs.get('options')
        self.pos = kwargs.get('pos')
        self.lastSelectedItem = None
        self.optionsList = None
        self.roundRobin = kwargs.get('round_robin', True)
        self.posIsBottom = kwargs.get('pos_is_bottom')
        self.closeDirection = kwargs.get('close_direction')
        self.setDropdownProp = kwargs.get('set_dropdown_prop', False)
        self.withIndicator = kwargs.get('with_indicator', False)
        self.suboptionCallback = kwargs.get('suboption_callback')
        self.closeOnPlaybackEnded = kwargs.get('close_on_playback_ended', False)
        self.closeOnlyWithBack = kwargs.get('close_only_with_back', False)
        self.alignItems = kwargs.get('align_items', 'center')
        self.optionsCallback = kwargs.get('options_callback', None)
        self.header = kwargs.get('header')
        self.selectIndex = kwargs.get('select_index')
        self.selectItem = kwargs.get('select_item')
        self.isSubList = kwargs.get('is_sub_list')
        self.openSubLists = kwargs.get('open_sublists')
        self.onCloseCallback = kwargs.get('onclose_callback')
        self.choice = None

        # Moving mode support
        self.movingItem = None  # ManagedListItem being moved
        self.initialMovingPos = None  # Original position for cancel/restore
        self.moveModeCallback = kwargs.get('move_mode_callback')  # Callback for move operations
        self.moveUpperBound = None  # First position that can't be moved to (separator boundary)
        self._justEnteredMoveMode = False  # Flag to skip the SELECT that entered move mode
        self._adjustedY = None  # Actual y position used after overflow adjustment (set in onFirstInit)
        self._lastMoveTime = 0  # Timestamp of last UP/DOWN action for wrap debounce

    @property
    def x(self):
        return min(self.width - self.dropWidth - self.borderOff, self.pos[0])

    @property
    def y(self):
        y = self.pos[1]
        if self.posIsBottom:
            y -= (len(self.options) * self.optionHeight) + 80
        return y

    def onFirstInit(self):
        self.setProperty('dropdown', self.setDropdownProp and '1' or '')
        self.setProperty('header', self.header)
        optLen = len(list(filter(lambda x: x != SEPARATOR, self.options)))
        separators = len(list(filter(lambda x: x == SEPARATOR, self.options)))
        self.setBoolProperty('scroll', optLen > 14)
        self.optionsList = kodigui.ManagedControlList(self, self.OPTIONS_LIST_ID, 14)
        openSubList = self.showOptions()
        height = min(self.optionHeight * 14, optLen * self.optionHeight + separators * self.separatorHeight) + util.vscalei(86)
        ol_height = height - util.vscalei(86)
        y = self.y

        if isinstance(y, int) and y + height > self.height:
            while y + height > self.height and y > 0:
                y -= self.optionHeight
            y = max(0, y)

        shadowControl = self.getControl(110)
        if self.header:
            shadowControl.setHeight(height + util.vscalei(86))
            self.getControl(111).setHeight(height + 6)
        else:
            shadowControl.setHeight(height)
        self.optionsList.setHeight(ol_height)
        if self.getBoolProperty('scroll'):
            try:
                self.getControl(self.SCROLLBAR_ID).setHeight(ol_height)
            except:
                pass

        if y == "middle":
            y = util.vperci(util.vscale(ol_height))

        self._adjustedY = int(y)
        self.getControl(100).setPosition(self.x, int(y))
        if self.header:
            shadowControl.setPosition(-60, util.vscalei(-106))

        self.setProperty('show', '1')
        self.setProperty('close.direction', self.closeDirection)
        if self.closeOnPlaybackEnded:
            from lib import player
            player.PLAYER.on('session.ended', self.playbackSessionEnded)

        if openSubList and self.openSubLists:
            # once the item is selected, open its sublist if wanted
            self.setChoice()

    def onAction(self, action):
        try:
            pass
        except:
            util.ERROR()

        controlID = self.getFocusId()

        # Handle moving mode actions
        if self.movingItem is not None:
            if action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
                self._handleMoveAction(action)
                return
            elif action == xbmcgui.ACTION_SELECT_ITEM:
                # Skip the SELECT that triggered entering move mode (onClick and onAction both fire)
                if self._justEnteredMoveMode:
                    self._justEnteredMoveMode = False
                    return
                self._confirmMove()
                return
            elif action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
                self._cancelMove()
                return
            # Ignore other actions while moving
            return

        if action == xbmcgui.ACTION_CONTEXT_MENU:
            # Kodi turns an Enter held for 500ms into ContextMenu, and a dropdown opened by
            # long-pressing Enter is usually followed by more of the same. Ignoring it left
            # the menu sitting there, unresponsive to the very key that opened it, so treat
            # it as a dismissal like Back: no choice, dialog closed.
            self.doClose()
            return

        if self.roundRobin and action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN) and \
                controlID == self.OPTIONS_LIST_ID:
            now = time.time()
            key_held = (now - self._lastMoveTime) < 0.3
            self._lastMoveTime = now

            to_pos = None
            last_index = self.optionsList.size() - 1

            if last_index > 0:
                if action == xbmcgui.ACTION_MOVE_UP and self.lastSelectedItem in (0, None) \
                        and self.optionsList.topHasFocus():
                    to_pos = last_index

                elif action == xbmcgui.ACTION_MOVE_DOWN and self.lastSelectedItem == last_index \
                        and self.optionsList.bottomHasFocus():
                    to_pos = 0

                if to_pos is not None:
                    if key_held:
                        # Key is being held — don't wrap
                        return
                    self.optionsList.setSelectedItemByPos(to_pos)
                    self.lastSelectedItem = to_pos
                    return

                self.lastSelectedItem = self.optionsList.control.getSelectedPosition()
        elif self.suboptionCallback and action == xbmcgui.ACTION_MOVE_RIGHT:
            if self.optionsList.getSelectedItem().dataSource.get("is_sub_list"):
                self.setChoice()
                return
            elif self.getBoolProperty('scroll'):
                self.setFocusId(self.SCROLLBAR_ID)
                return

        elif controlID == self.SCROLLBAR_ID and action == xbmcgui.ACTION_SELECT_ITEM:
            self.setChoice()
            return

        kodigui.BaseDialog.onAction(self, action)

    def enterMoveMode(self, mli, skip_first_select=True):
        """Enter moving mode for the given list item."""
        if not mli:
            return False

        pos = self.optionsList.getManagedItemPosition(mli)
        if pos is None:
            return False

        # Only allow entering move mode for items within the movable range
        if self.moveUpperBound is not None and pos >= self.moveUpperBound:
            return False

        # Don't allow move mode if there's only one movable item
        if self.moveUpperBound is not None and self.moveUpperBound <= 1:
            return False

        self.movingItem = mli
        self.initialMovingPos = pos
        self._justEnteredMoveMode = skip_first_select  # Skip SELECT only for direct clicks (not sub-menu)
        mli.setProperty('moving', '1')
        self.setProperty('moving', '1')
        return True

    def _handleMoveAction(self, action):
        """Handle Up/Down arrow keys while in moving mode."""
        if not self.movingItem:
            return

        current_pos = self.optionsList.getManagedItemPosition(self.movingItem)
        if current_pos is None:
            return

        # Calculate target position
        if action == xbmcgui.ACTION_MOVE_UP:
            target_pos = current_pos - 1
        else:  # ACTION_MOVE_DOWN
            target_pos = current_pos + 1

        # Find valid position (skip separators)
        target_pos = self._findValidMovePosition(current_pos, target_pos, action)
        if target_pos is None or target_pos == current_pos:
            return

        # Move the item
        self.optionsList.moveItem(self.movingItem, target_pos)
        self.optionsList.selectItem(target_pos)

        # Notify callback of move (for live position updates)
        if self.moveModeCallback:
            self.moveModeCallback('move', self.movingItem, current_pos, target_pos)

    def _findValidMovePosition(self, current_pos, target_pos, action):
        """Find a valid position to move to, staying within movable bounds."""
        # Determine the valid range for moving
        # Items can only move within positions 0 to (moveUpperBound - 1)
        upper_bound = self.moveUpperBound if self.moveUpperBound is not None else self.optionsList.size()

        # Check bounds and handle wrapping
        if target_pos < 0:
            # Wrap to last movable position
            target_pos = upper_bound - 1
        elif target_pos >= upper_bound:
            # Wrap to first position
            target_pos = 0

        return target_pos

    def _confirmMove(self):
        """Confirm the move and exit moving mode."""
        if not self.movingItem:
            return

        mli = self.movingItem
        old_pos = self.initialMovingPos
        new_pos = self.optionsList.getManagedItemPosition(mli)

        # Clear moving state
        mli.setProperty('moving', '')
        self.setProperty('moving', '')
        self.movingItem = None
        self.initialMovingPos = None

        # Notify callback of confirmed move
        if self.moveModeCallback:
            self.moveModeCallback('confirm', mli, old_pos, new_pos)

    def _cancelMove(self):
        """Cancel the move and restore original position."""
        if not self.movingItem:
            return

        mli = self.movingItem
        old_pos = self.initialMovingPos

        # Restore original position
        if old_pos is not None:
            self.optionsList.moveItem(mli, old_pos)
            self.optionsList.selectItem(old_pos)

        # Clear moving state
        mli.setProperty('moving', '')
        self.setProperty('moving', '')
        self.movingItem = None
        self.initialMovingPos = None

        # Notify callback of cancelled move
        if self.moveModeCallback:
            self.moveModeCallback('cancel', mli, old_pos, old_pos)

    def isMoving(self):
        """Return True if currently in moving mode."""
        return self.movingItem is not None

    def onClick(self, controlID):
        # If in move mode, let onAction handle it (onClick and onAction both fire for Enter)
        if self.movingItem is not None:
            return
        if controlID == self.OPTIONS_LIST_ID:
            self.setChoice()
        else:
            self.doClose()

    def playbackSessionEnded(self, **kwargs):
        self.doClose()

    def doClose(self, **kw):
        if self.closeOnPlaybackEnded:
            from lib import player
            player.PLAYER.off('session.ended', self.playbackSessionEnded)

        self.optionsList.reset()
        self.optionsList = None

        self.setProperty('show', '')

        super(DropdownDialog, self).doClose()

    def onClosed(self):
        if self.onCloseCallback:
            self.onCloseCallback(self.choice)

    def setChoice(self):
        mli = self.optionsList.getSelectedItem()
        if not mli:
            return

        choice = self.options[self.optionsList.getSelectedPos()]

        if choice.get('ignore'):
            return

        if self.suboptionCallback:
            options = self.suboptionCallback(mli.dataSource)
            if options:
                sub_select = None
                if self.selectItem and self.selectItem.get("sub"):
                    sub_select = self.selectItem["sub"]

                # Position sub-menu to the right of the main list, aligned with the selected item.
                # Container(id).Position returns the cursor row within the VISIBLE area (0 = top
                # visible item), which correctly accounts for scroll — unlike getSelectedPos()
                # which returns the absolute index.
                try:
                    visual_row = int(xbmc.getInfoLabel('Container({}).Position'.format(self.OPTIONS_LIST_ID)))
                    if visual_row < 0:
                        raise ValueError('negative')
                except (ValueError, TypeError):
                    visual_row = self.optionsList.getSelectedPos()
                list_y = self._adjustedY if self._adjustedY is not None else int(self.y)
                sub_x = self.x + self.dropWidth - 40  # between content edge and shadow edge of main list
                sub_y = list_y + visual_row * self.optionHeight

                # disable scrollbar temporarily
                oldprop = self.getBoolProperty('scroll')
                self.setBoolProperty('scroll', False)
                sub = showDropdown(options, (sub_x, sub_y), close_direction='left',
                                   with_indicator=True, select_item=sub_select, is_sub_list=True,
                                   dialog_props=self.dialogProps)
                if self.dialogProps:
                    win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
                    for key, value in self.dialogProps.items():
                        win.setProperty(key, value)
                self.setBoolProperty('scroll', oldprop)
                if not sub:
                    return

                choice['sub'] = sub
                mli.dataSource['sub'] = sub  # Propagate to dataSource so optionsCallback can read it

        self.choice = choice
        if self.optionsCallback:
            result = self.optionsCallback(self.optionsList, mli)
            # Check if callback wants to enter move mode
            if result == 'enter_move_mode':
                self.enterMoveMode(mli)  # skip_first_select=True (direct click)
                return
            elif result == 'enter_move_mode_sub':
                self.enterMoveMode(mli, skip_first_select=False)  # came via sub-menu
                return
            # Check if callback wants to close and reopen the dialog
            if result == 'close_and_reopen':
                self.choice = {'reopen': True}
                self.doClose()
                return
            # Check if callback wants to rebuild the list in place
            elif isinstance(result, tuple) and result[0] == 'rebuild':
                _, new_options, focus_pos = result
                self.options = new_options
                prev_select_index = self.selectIndex
                self.selectIndex = focus_pos
                self.selectItem = None
                self.showOptions()
                self.selectIndex = prev_select_index
                return

        del mli

        if not self.closeOnlyWithBack:
            self.doClose()

    def showOptions(self):
        items = []
        options = []
        sids = None
        hadSub = False
        self.moveUpperBound = None  # Reset move boundary tracking
        first_separator_seen = False

        if self.selectItem:
            sids = self.selectItem.copy()
            sids["indicator"] = ''
            if "sub" in sids:
                sids.pop("sub")
                hadSub = True

        for oo in self.options:
            if oo:
                o = oo.copy()
                ds = o.copy()
                # clear indicator for the dataSource so we can find it later
                ds["indicator"] = ''
                item = kodigui.ManagedListItem(o['display'], thumbnailImage=o.get('indicator', ''), data_source=ds)
                item.setProperty('with.indicator', self.withIndicator and '1' or '')
                item.setProperty('has.submenu', '1' if o.get('has_submenu') else '')
                item.setProperty('align', self.alignItems)
                items.append(item)
                options.append(o)
            else:
                if items:
                    items[-1].setProperty('separator', '1')
                    # Track the first separator as the move boundary
                    # Items before this can be moved, items at/after cannot
                    if not first_separator_seen:
                        self.moveUpperBound = len(items)
                        first_separator_seen = True

        self.options = options

        if len(items) > 1:
            items[0].setProperty('first', '1')
            items[-1].setProperty('last', '1')
        elif items:
            items[0].setProperty('only', '1')

        self.optionsList.reset()
        self.optionsList.addItems(items)

        self.setFocusId(self.OPTIONS_LIST_ID)

        if self.selectIndex is not None:
            self.optionsList.setSelectedItemByPos(self.selectIndex)
            self.lastSelectedItem = self.selectIndex
        elif sids is not None:
            # select the wanted item and wait for it to actually be selected
            mli = self.optionsList.getListItemByDataSource(sids)
            if not mli:
                util.DEBUG_LOG("Dropdown: item not found: {}", sids)
                return False

            pos = self.optionsList.getManagedItemPosition(mli)
            self.optionsList.setSelectedItemByPos(pos)
            while self.optionsList and self.optionsList.getSelectedPos() != pos:
                util.MONITOR.waitFor()

            if not self.optionsList:
                util.DEBUG_LOG("Dropdown: something went wrong")
                return False

            self.lastSelectedItem = pos

            # we expect further sub-dropdowns
            if hadSub and self.suboptionCallback:
                return True
        return False


class DropdownHeaderDialog(DropdownDialog):
    xmlFile = 'script-plex-dropdown_header.xml'
    dropWidth = 660


def showDropdown(
    options, pos=None,
    pos_is_bottom=False,
    close_direction='left',
    set_dropdown_prop=True,
    with_indicator=False,
    suboption_callback=None,
    close_on_playback_ended=False,
    close_only_with_back=False,
    align_items='center',
    options_callback=None,
    header=None,
    select_index=None,
    select_item=None,
    open_sublists=False,
    is_sub_list=False,
    onclose_callback=None,
    dialog_props=None,
    move_mode_callback=None
):

    if header:
        pos = pos or (660, 400)
        w = DropdownHeaderDialog.open(
            options=options, pos=pos,
            pos_is_bottom=pos_is_bottom,
            close_direction=close_direction,
            set_dropdown_prop=set_dropdown_prop,
            with_indicator=with_indicator,
            suboption_callback=suboption_callback,
            close_on_playback_ended=close_on_playback_ended,
            close_only_with_back=close_only_with_back,
            align_items=align_items,
            options_callback=options_callback,
            header=header,
            select_index=select_index,
            select_item=select_item,
            open_sublists=open_sublists,
            is_sub_list=is_sub_list,
            onclose_callback=onclose_callback,
            dialog_props=dialog_props,
            move_mode_callback=move_mode_callback,
        )
    else:
        pos = pos or (810, 400)
        w = DropdownDialog.open(
            options=options, pos=pos,
            pos_is_bottom=pos_is_bottom,
            close_direction=close_direction,
            set_dropdown_prop=set_dropdown_prop,
            with_indicator=with_indicator,
            suboption_callback=suboption_callback,
            close_on_playback_ended=close_on_playback_ended,
            close_only_with_back=close_only_with_back,
            align_items=align_items,
            options_callback=options_callback,
            header=header,
            select_index=select_index,
            select_item=select_item,
            open_sublists=open_sublists,
            is_sub_list=is_sub_list,
            onclose_callback=onclose_callback,
            dialog_props=dialog_props,
            move_mode_callback=move_mode_callback,
        )
    choice = w.choice
    w = None
    del w
    util.garbageCollect()
    return choice
