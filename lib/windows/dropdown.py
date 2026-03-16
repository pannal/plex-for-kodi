from __future__ import absolute_import

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

        if y == "middle":
            y = util.vperci(util.vscale(ol_height))

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

        if self.roundRobin and action in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN) and \
                controlID == self.OPTIONS_LIST_ID:
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
                    self.optionsList.setSelectedItemByPos(to_pos)
                    self.lastSelectedItem = to_pos
                    return

                self.lastSelectedItem = self.optionsList.control.getSelectedPosition()
        elif self.suboptionCallback and action == xbmcgui.ACTION_MOVE_RIGHT:
            if self.optionsList.getSelectedItem().dataSource.get("is_sub_list"):
                self.setChoice()

        elif controlID == self.SCROLLBAR_ID and action == xbmcgui.ACTION_SELECT_ITEM:
            self.setChoice()
            return

        kodigui.BaseDialog.onAction(self, action)

    def onClick(self, controlID):
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
            options = self.suboptionCallback(choice)
            if options:
                sub_select = None
                if self.selectItem and self.selectItem.get("sub"):
                    sub_select = self.selectItem["sub"]

                # disable scrollbar temporarily
                oldprop = self.getBoolProperty('scroll')
                self.setBoolProperty('scroll', False)
                sub = showDropdown(options, (self.x + 290, self.y + 10), close_direction='left',
                                   with_indicator=True, select_item=sub_select, is_sub_list=True)
                self.setBoolProperty('scroll', oldprop)
                if not sub:
                    return

                choice['sub'] = sub

        self.choice = choice
        if self.optionsCallback:
            self.optionsCallback(self.optionsList, mli)

        del mli

        if not self.closeOnlyWithBack:
            self.doClose()

    def showOptions(self):
        items = []
        options = []
        sids = None
        hadSub = False
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
                item.setProperty('align', self.alignItems)
                items.append(item)
                options.append(o)
            else:
                if items:
                    items[-1].setProperty('separator', '1')

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
    dialog_props=None
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
        )
    choice = w.choice
    w = None
    del w
    util.garbageCollect()
    return choice
