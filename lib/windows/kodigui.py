# -*- coding: utf-8 -*-
from __future__ import absolute_import

import threading
import time
import traceback

from kodi_six import xbmc
from kodi_six import xbmcgui
from six.moves import range
from six.moves import zip

from .. import util

from plexnet import plexapp

MONITOR = None


class BaseFunctions(object):
    xmlFile = ''
    path = ''
    theme = ''
    res = '720p'
    width = 1280
    height = 720

    usesGenerate = False
    lastWinID = None
    lastDialogID = None

    def __init__(self):
        self.isOpen = True

    def onWindowFocus(self):
        # Not automatically called. Can be used by an external window manager
        pass

    def onClosed(self):
        pass

    @classmethod
    def open(cls, **kwargs):
        window = cls(cls.xmlFile, cls.path, cls.theme, cls.res, **kwargs)
        window.modal()
        return window

    @classmethod
    def create(cls, show=True, **kwargs):
        window = cls(cls.xmlFile, cls.path, cls.theme, cls.res, **kwargs)
        if show:
            window.show()
            if xbmcgui.getCurrentWindowId() < 13000:
                window.isOpen = False
                return window

        window.isOpen = xbmcgui.getCurrentWindowId() >= 13000
        return window

    def modal(self):
        self.isOpen = True
        try:
            self.doModal()
        except SystemExit:
            pass
        self.onClosed()
        self.isOpen = False

    def activate(self):
        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()
        xbmc.executebuiltin('ReplaceWindow({0})'.format(self._winID))

    def mouseXTrans(self, val):
        return int((val / self.getWidth()) * self.width)

    def mouseYTrans(self, val):
        return int((val / self.getHeight()) * self.height)

    def closing(self):
        return self._closing

    @classmethod
    def generate(self):
        return None

    def setProperties(self, prop_list, val_list_or_val):
        if isinstance(val_list_or_val, list) or isinstance(val_list_or_val, tuple):
            val_list = val_list_or_val
        else:
            val_list = [val_list_or_val] * len(prop_list)

        for prop, val in zip(prop_list, val_list):
            self.setProperty(prop, val)

    def propertyContext(self, prop, val='1'):
        return WindowProperty(self, prop, val)

    def setBoolProperty(self, key, boolean):
        self.setProperty(key, boolean and '1' or '')

    def waitForVisibility(self, control):
        return waitForVisibility(control)

    def waitAndSetFocus(self, control):
        self.waitForVisibility(control)
        self.setFocusId(control)


LAST_BG_URL = None
BG_NA = "script.plex/home/background-fallback_black.png"


class XMLBase(object):
    def onInit(self, count=0):
        try:
            self.getControl(666)
        except RuntimeError as e:
            if e.args and "Non-Existent Control" in e.args[0]:
                if count < 8:
                    # retry
                    xbmc.sleep(250)
                    return self.onInit(count=count+1)

                util.ERROR("Possibly broken XML file: {}, triggering recompilation.".format(self.xmlFile))
                util.showNotification("Recompiling templates", time_ms=1000,
                                      header="Possibly broken XML file(s)")

                try:
                    if xbmc.Player().isPlaying():
                        try:
                            xbmc.Player().stop()
                        except:
                            pass

                    tries = 0
                    while xbmc.Player().isPlaying() and tries < 50:
                        util.MONITOR.waitForAbort(0.1)
                        tries += 1
                except:
                    pass

                xbmc.sleep(1000)

                if self.__class__.__name__ == "HomeWindow":
                    try:
                        self._errored = True
                        self.closeWRecompileTpls()
                    finally:
                        return
                elif self.__class__.__name__ == "BackgroundWindow":
                    try:
                        self._errored = True
                        self.doClose()
                    finally:
                        return

                try:
                    self._errored = True
                    self.doClose()
                finally:
                    from . import windowutils
                    windowutils.HOME.closeWRecompileTpls()
                    return
            raise
        self._onInit()

    def goHomeAction(self, action):
        if (util.HOME_BUTTON_MAPPED is not None
                and action.getButtonCode() == int(util.HOME_BUTTON_MAPPED) and hasattr(self, "goHome")):
            util.DEBUG_LOG("Kodigui: Going home action")
            self.goHome(with_root=True)
            return True
        return


class BaseWindow(XMLBase, xbmcgui.WindowXML, BaseFunctions):
    __slots__ = ("_closing", "_winID", "started", "finishedInit", "dialogProps", "isOpen", "_errored",
                 "_closeSignalled")

    def __init__(self, *args, **kwargs):
        BaseFunctions.__init__(self)
        self._closing = False
        self._errored = False
        self._closeSignalled = False
        self._winID = None
        self.started = False
        self.finishedInit = False
        self.dialogProps = kwargs.get("dialog_props", None)

        carryProps = kwargs.get("window_props", None)
        if carryProps:
            self.setProperties(list(carryProps.keys()), list(carryProps.values()))
        self.setBoolProperty('is_plextuary', util.SKIN_PLEXTUARY)

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose()

    def _onInit(self):
        global LAST_BG_URL
        self._winID = xbmcgui.getCurrentWindowId()
        BaseFunctions.lastWinID = self._winID
        self.setProperty('use_solid_background', util.hasCustomBGColour and '1' or '')
        if util.hasCustomBGColour:
            bgColour = util.addonSettings.backgroundColour if util.addonSettings.backgroundColour != "-" \
                else "ff000000"
            self.setProperty('background_colour', "0x%s" % bgColour.lower())
            self.setProperty('background_colour_opaque', "0x%s" % bgColour.lower())
        else:
            # set background color to 0 to avoid kodi UI BG clearing, improves performance
            if util.addonSettings.dbgCrossfade:
                self.setProperty('background_colour', "0x00000000")
            else:
                self.setProperty('background_colour', "0xff111111")
            self.setProperty('background_colour_opaque', "0xff111111")

        self.setBoolProperty('use_bg_fallback', util.addonSettings.useBgFallback)
        self.setBoolProperty('dynamic_backgrounds', util.addonSettings.dynamicBackgrounds)

        try:
            if self.started:
                if hasattr(self, "onReInit"):
                    self.onReInit()
            else:
                self.started = True
                if LAST_BG_URL:
                    self.windowSetBackground(LAST_BG_URL)

                if self.__class__.__name__ not in ("HomeWindow", "BackgroundWindow"):
                    plexapp.util.APP.on('close.windows', self.onCloseSignal)

                if hasattr(self, "onFirstInit"):
                    self.onFirstInit()
                self.finishedInit = True
            util.setGlobalProperty('active_window', self.__class__.__name__)

        except util.NoDataException:
            self.exitCommand = "NODATA"
            self.doClose()

    def onAction(self, action):
        if XMLBase.goHomeAction(self, action):
            return
        xbmcgui.WindowXML.onAction(self, action)

    def onReInit(self):
        pass

    def waitForOpen(self, base_win_id=None):
        tries = 0
        while ((not base_win_id and not self.isOpen) or
               (base_win_id and xbmcgui.getCurrentWindowId() <= base_win_id)) \
                and not util.MONITOR.waitForAbort(1) and tries < 120:
            if tries == 0:
                util.LOG("Couldn't open window {}, other dialog open? Retrying for 120s.", self)
            self.show()
            tries += 1

        util.DEBUG_LOG("Window {} opened: {}", self, self.isOpen)

        return self.isOpen

    def setProperty(self, key, value):
        if self._closing:
            return

        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()

        try:
            xbmcgui.Window(self._winID).setProperty(key, value)
            xbmcgui.WindowXML.setProperty(self, key, value)
        except RuntimeError:
            util.DEBUG_LOG('kodigui.BaseWindow.setProperty: Missing window ({}) ({})', self._winID, key)

    def setCondFocusId(self, focus):
        if self.getFocusId() != focus:
            self.setFocusId(focus)

    def updateBackgroundFrom(self, ds):
        if util.addonSettings.dynamicBackgrounds:
            return self.windowSetBackground(util.backgroundFromArt(ds.get('art', ds.get('parentArt', ds.get('grandparentArt', None))), width=self.width, height=self.height))

    def windowSetBackground(self, value):
        if not util.addonSettings.dbgCrossfade:
            if not value:
                return
            self.setProperty("background_static", value)
            return value

        global LAST_BG_URL

        if not value:
            bg = LAST_BG_URL or BG_NA
            self.setProperty("background_static", bg)
            self.setProperty("background", BG_NA)
            LAST_BG_URL = BG_NA
            return BG_NA

        cur1 = self.getProperty('background')
        if not cur1:
            self.setProperty("background_static", value)
            self.setProperty("background", value)

        elif LAST_BG_URL != value:
            self.setProperty("background_static", LAST_BG_URL)
            self.setProperty("background", value)

        LAST_BG_URL = value
        return value

    def doClose(self):
        plexapp.util.APP.off('close.windows', self.onCloseSignal)
        if not self.isOpen:
            return
        self._closing = True
        self.isOpen = False
        self.close()

    def show(self):
        self._closing = False
        #self.isOpen = True
        xbmcgui.WindowXML.show(self)
        self.isOpen = xbmcgui.getCurrentWindowId() >= 13000

    @property
    def is_active(self):
        return self._winID and BaseFunctions.lastWinID == self._winID

    @property
    def is_current_window(self):
        return self._winID and xbmcgui.getCurrentWindowId() == self._winID

    def onClosed(self):
        pass


class BaseDialog(XMLBase, xbmcgui.WindowXMLDialog, BaseFunctions):
    __slots__ = ("_closing", "_winID", "started", "isOpen", "_errored", "_closeSignalled")

    def __init__(self, *args, **kwargs):
        BaseFunctions.__init__(self)
        self._closing = False
        self._errored = False
        self._closeSignalled = False
        self._winID = ''
        self.started = False

        carryProps = kwargs.get("dialog_props", None)
        if carryProps:
            self.setProperties(list(carryProps.keys()), list(carryProps.values()))
        self.setBoolProperty('is_plextuary', util.SKIN_PLEXTUARY)

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose()

    def _onInit(self):
        self._winID = xbmcgui.getCurrentWindowDialogId()
        BaseFunctions.lastDialogID = self._winID
        if self.started:
            self.onReInit()
        else:
            self.started = True
            plexapp.util.APP.on('close.dialogs', self.onCloseSignal)
            self.onFirstInit()

    def onAction(self, action):
        if XMLBase.goHomeAction(self, action):
            return
        xbmcgui.WindowXMLDialog.onAction(self, action)

    def onFirstInit(self):
        pass

    def onReInit(self):
        pass

    def setProperty(self, key, value):
        if self._closing:
            return

        if not self._winID:
            self._winID = xbmcgui.getCurrentWindowId()

        try:
            xbmcgui.Window(self._winID).setProperty(key, value)
            xbmcgui.WindowXMLDialog.setProperty(self, key, value)
        except RuntimeError:
            xbmc.log('kodigui.BaseDialog.setProperty: Missing window', xbmc.LOGDEBUG)

    def doClose(self):
        plexapp.util.APP.off('close.dialogs', self.onCloseSignal)
        self._closing = True
        self.close()
        self.isOpen = False

    def show(self):
        self._closing = False
        xbmcgui.WindowXMLDialog.show(self)
        self.isOpen = True

    def onClosed(self):
        pass


class ControlledBase:
    def doModal(self):
        self.show()
        self.wait()

    def wait(self):
        while not self._closing and not MONITOR.waitForAbort(0.1):
            pass

    def close(self):
        self._closing = True


class ControlledWindow(ControlledBase, BaseWindow):
    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                self.doClose()
                return
        except:
            traceback.print_exc()

        BaseWindow.onAction(self, action)


class ControlledDialog(ControlledBase, BaseDialog):
    def onAction(self, action):
        try:
            if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
                self.doClose()
                return
        except:
            traceback.print_exc()

        BaseDialog.onAction(self, action)


DUMMY_LIST_ITEM = xbmcgui.ListItem()


class DummyDataSource(object):
    def __nonzero__(self):
        return False

    __bool__ = __nonzero__

    def exists(self, *args, **kwargs):
        return False


class EmptyDataSource(DummyDataSource):
    def __getattr__(self, item):
        return None

    def __setattr__(self, key, value):
        raise NotImplementedError


DUMMY_DATA_SOURCE = DummyDataSource()


class ManagedListItem(object):
    __slots__ = ("_listItem", "dataSource", "properties", "label", "label2", "iconImage", "thumbnailImage", "path",
                 "_ID", "_manager", "_valid")

    def __init__(self, label='', label2='', iconImage='', thumbnailImage='', path='', data_source=None,
                 properties=None):
        self._listItem = xbmcgui.ListItem(label, label2, path=path)
        self._listItem.setArt({"thumb": thumbnailImage, "icon": iconImage})
        self.dataSource = data_source
        self.properties = {}
        self.label = label
        self.label2 = label2
        self.iconImage = iconImage
        self.thumbnailImage = thumbnailImage
        self.path = path
        self._ID = None
        self._manager = None
        self._valid = True

        if properties:
            for k, v in properties.items():
                self.setProperty(k, v)

    def __nonzero__(self):
        return self._valid

    @property
    def listItem(self):
        if not self._listItem:
            if not self._manager:
                return None

            try:
                self._listItem = self._manager.getListItemFromManagedItem(self)
            except RuntimeError:
                return None

        return self._listItem

    def invalidate(self):
        self._valid = False
        self._listItem = DUMMY_LIST_ITEM
        self.dataSource = DUMMY_DATA_SOURCE

    def _takeListItem(self, manager, lid):
        self._manager = manager
        self._ID = lid
        self._listItem.setProperty('__ID__', lid)
        li = self._listItem
        self._listItem = None
        self._manager._properties.update(self.properties)
        return li

    def _updateListItem(self):
        self.listItem.setProperty('__ID__', self._ID)
        self.listItem.setLabel(self.label)
        self.listItem.setLabel2(self.label2)
        self.listItem.setArt({"thumb": self.thumbnailImage, "icon": self.iconImage})
        self.listItem.setPath(self.path)
        for k in self._manager._properties.keys():
            self.listItem.setProperty(k, self.properties.get(k) or '')

    def clear(self):
        self.label = ''
        self.label2 = ''
        self.iconImage = ''
        self.thumbnailImage = ''
        self.path = ''
        for k in self.properties:
            self.properties[k] = ''
        self._updateListItem()

    def pos(self):
        if not self._manager:
            return None
        return self._manager.getManagedItemPosition(self)

    def addContextMenuItems(self, items, replaceItems=False):
        self.listItem.addContextMenuItems(items, replaceItems)

    def addStreamInfo(self, stype, values):
        self.listItem.addStreamInfo(stype, values)

    def getLabel(self):
        return self.label

    def getLabel2(self):
        return self.label2

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getdescription(self):
        return self.listItem.getdescription()

    def getduration(self):
        return self.listItem.getduration()

    def getfilename(self):
        return self.listItem.getfilename()

    def isSelected(self):
        return self.listItem.isSelected()

    def select(self, selected):
        return self.listItem.select(selected)

    def setArt(self, values):
        return self.listItem.setArt(values)

    def setIconImage(self, icon):
        self.iconImage = icon
        return self.listItem.setArt({"icon": self.iconImage})

    def setInfo(self, itype, infoLabels):
        return self.listItem.setInfo(itype, infoLabels)

    def setLabel(self, label):
        self.label = label
        return self.listItem.setLabel(label)

    def setLabel2(self, label):
        self.label2 = label
        return self.listItem.setLabel2(label)

    def setMimeType(self, mimetype):
        return self.listItem.setMimeType(mimetype)

    def setPath(self, path):
        self.path = path
        return self.listItem.setPath(path)

    def setProperty(self, key, value):
        if self._manager:
            self._manager._properties[key] = 1
        self.properties[key] = value
        self.listItem.setProperty(key, value)
        return self

    def setProperties(self, prop_list, val_list_or_val):
        if isinstance(val_list_or_val, list) or isinstance(val_list_or_val, tuple):
            val_list = val_list_or_val
        else:
            val_list = [val_list_or_val] * len(prop_list)

        for prop, val in zip(prop_list, val_list):
            self.setProperty(prop, val)

    def setBoolProperty(self, key, boolean):
        return self.setProperty(key, boolean and '1' or '')

    def setSubtitles(self, subtitles):
        return self.listItem.setSubtitles(subtitles)  # List of strings - HELIX

    def setThumbnailImage(self, thumb):
        self.thumbnailImage = thumb
        return self.listItem.setArt({"thumb": self.thumbnailImage})

    def onDestroy(self):
        pass


class ManagedControlList(object):
    __slots__ = ("controlID", "control", "items", "_sortKey", "_idCounter", "_maxViewIndex", "_properties",
                 "dataSource")

    def __init__(self, window, control_id, max_view_index, data_source=None):
        self.controlID = control_id
        self.control = window.getControl(control_id)
        self.items = []
        self._sortKey = None
        self._idCounter = 0
        self._maxViewIndex = max_view_index
        self._properties = {}
        self.dataSource = data_source

    def __getattr__(self, name):
        return getattr(self.control, name)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return self.items[idx]
        else:
            return self.getListItem(idx)

    def __iter__(self):
        for i in self.items:
            yield i

    def __len__(self):
        return self.size()

    def prev(self):
        pos = self.getSelectedPos()-1
        if self.positionIsValid(pos):
            return pos
        return 0

    def _updateItems(self, bottom=None, top=None):
        if bottom is None:
            bottom = 0
            top = self.size()

        try:
            for idx in range(bottom, top):
                try:
                    li = self.control.getListItem(idx)
                except RuntimeError:
                    continue

                mli = self.items[idx]
                self._properties.update(mli.properties)
                mli._manager = self
                mli._listItem = li
                mli._updateListItem()
                mli.setProperty('index', str(idx))
        except RuntimeError:
            #xbmc.log('kodigui.ManagedControlList._updateItems: Runtime error', xbmc.LOGINFO)
            util.ERROR('kodigui.ManagedControlList._updateItems: Runtime error')
            return False

        return True

    def _nextID(self):
        self._idCounter += 1
        return str(self._idCounter)

    def reInit(self, window, control_id):
        self.controlID = control_id
        self.control = window.getControl(control_id)
        self.control.addItems([i._takeListItem(self, self._nextID()) for i in self.items])

    def setSort(self, sort):
        self._sortKey = sort

    def addItem(self, managed_item):
        self.items.append(managed_item)
        self.control.addItem(managed_item._takeListItem(self, self._nextID()))

    def addItems(self, managed_items):
        self.items += managed_items
        self.control.addItems([i._takeListItem(self, self._nextID()) for i in managed_items])

    def replaceItem(self, pos, mli):
        self[pos].onDestroy()
        self[pos].invalidate()
        self.items[pos] = mli
        li = self.control.getListItem(pos)
        mli._manager = self
        mli._listItem = li
        mli._updateListItem()

    def replaceItems(self, managed_items):
        if not self.items:
            self.addItems(managed_items)
            return True

        oldSize = self.size()

        for i in self.items:
            i.onDestroy()
            i.invalidate()

        self.items = managed_items
        size = self.size()
        if size != oldSize:
            pos = self.getSelectedPosition()

            if size > oldSize:
                for i in range(0, size - oldSize):
                    self.control.addItem(xbmcgui.ListItem())
            elif size < oldSize:
                diff = oldSize - size
                idx = oldSize - 1
                while diff:
                    self.control.removeItem(idx)
                    idx -= 1
                    diff -= 1

            if self.positionIsValid(pos):
                self.selectItem(pos)
            elif pos >= size:
                self.selectItem(size - 1)

        return self._updateItems(0, self.size())

    def getListItem(self, pos):
        li = self.control.getListItem(pos)
        mli = self.items[pos]
        mli._listItem = li
        return mli

    def getListItemByDataSource(self, data_source):
        for mli in self:
            if data_source == mli.dataSource:
                return mli
        return None

    def getSelectedItem(self):
        pos = self.control.getSelectedPosition()
        if not self.positionIsValid(pos):
            pos = self.size() - 1

        if pos < 0:
            return None
        return self.getListItem(pos)

    def getSelectedPos(self):
        pos = self.control.getSelectedPosition()
        if not self.positionIsValid(pos):
            pos = self.size() - 1

        if pos < 0:
            return None
        return pos

    def getItemByPos(self, pos):
        if self.positionIsValid(pos):
            return self.getListItem(pos)

    def setSelectedItemByPos(self, pos):
        if self.positionIsValid(pos):
            self.control.selectItem(pos)

    def setSelectedItem(self, item):
        pos = self.getManagedItemPosition(item)
        if self.positionIsValid(pos):
            self.control.selectItem(pos)

    def setSelectedItemByDataSource(self, data_source):
        self.setSelectedItem(self.getListItemByDataSource(data_source))

    def removeItem(self, index):
        old = self.items.pop(index)
        old.onDestroy()
        old.invalidate()

        self.control.removeItem(index)
        top = self.control.size() - 1
        if top < 0:
            return
        if top < index:
            index = top
        self.control.selectItem(index)

    def removeManagedItem(self, mli):
        self.removeItem(mli.pos())

    def insertItem(self, index, managed_item):
        pos = self.getSelectedPosition() + 1

        if index >= self.size() or index < 0:
            self.addItem(managed_item)
        else:
            self.items.insert(index, managed_item)
            self.control.addItem(managed_item._takeListItem(self, self._nextID()))
            self._updateItems(index, self.size())

        if self.positionIsValid(pos):
            self.selectItem(pos)

    def moveItem(self, mli, dest_idx):
        source_idx = mli.pos()
        if source_idx < dest_idx:
            rstart = source_idx
            rend = dest_idx + 1
            # dest_idx-=1
        else:
            rstart = dest_idx
            rend = source_idx + 1
        mli = self.items.pop(source_idx)
        self.items.insert(dest_idx, mli)

        self._updateItems(rstart, rend)

    def swapItems(self, pos1, pos2):
        if not self.positionIsValid(pos1) or not self.positionIsValid(pos2):
            return False

        item1 = self.items[pos1]
        item2 = self.items[pos2]
        li1 = item1._listItem
        li2 = item2._listItem
        item1._listItem = li2
        item2._listItem = li1

        item1._updateListItem()
        item2._updateListItem()
        self.items[pos1] = item2
        self.items[pos2] = item1

        return True

    def shiftView(self, shift, hold_selected=False):
        if not self._maxViewIndex:
            return
        selected = self.getSelectedItem()
        selectedPos = selected.pos()
        viewPos = self.getViewPosition()

        if shift > 0:
            pushPos = selectedPos + (self._maxViewIndex - viewPos) + shift
            if pushPos >= self.size():
                pushPos = self.size() - 1
            self.selectItem(pushPos)
            newViewPos = self._maxViewIndex
        elif shift < 0:
            pushPos = (selectedPos - viewPos) + shift
            if pushPos < 0:
                pushPos = 0
            self.selectItem(pushPos)
            newViewPos = 0

        if hold_selected:
            self.selectItem(selected.pos())
        else:
            diff = newViewPos - viewPos
            fix = pushPos - diff
            # print '{0} {1} {2}'.format(newViewPos, viewPos, fix)
            if self.positionIsValid(fix):
                self.selectItem(fix)

    def reset(self):
        self.dataSource = None
        for i in self.items:
            i.onDestroy()
            i.invalidate()
        self.items = []
        self.control.reset()

    def size(self):
        return len(self.items)

    def getViewPosition(self):
        try:
            return int(xbmc.getInfoLabel('Container({0}).Position'.format(self.controlID)))
        except:
            return 0

    def getViewRange(self):
        viewPosition = self.getViewPosition()
        selected = self.getSelectedPosition()
        return list(range(max(selected - viewPosition, 0), min(selected + (self._maxViewIndex - viewPosition) + 1, self.size() - 1)))

    def positionIsValid(self, pos):
        return 0 <= pos < self.size()

    def sort(self, sort=None, reverse=False):
        sort = sort or self._sortKey

        self.items.sort(key=sort, reverse=reverse)

        self._updateItems(0, self.size())

    def reverse(self):
        self.items.reverse()
        self._updateItems(0, self.size())

    def getManagedItemPosition(self, mli):
        return self.items.index(mli)

    def isLastItem(self, mli=None):
        return self.getManagedItemPosition(mli or self.getSelectedItem()) + 1 == len(self)

    def getListItemFromManagedItem(self, mli):
        pos = self.items.index(mli)
        return self.control.getListItem(pos)

    def topHasFocus(self):
        return self.getSelectedPosition() == 0

    def bottomHasFocus(self):
        return self.getSelectedPosition() == self.size() - 1

    def invalidate(self):
        for item in self.items:
            item._listItem = DUMMY_LIST_ITEM

    def newControl(self, window=None, control_id=None):
        self.controlID = control_id or self.controlID
        self.control = window.getControl(self.controlID)
        self.control.addItems([xbmcgui.ListItem() for i in range(self.size())])
        self._updateItems()


class _MWBackground(ControlledWindow):
    __slots__ = ("_multiWindow", "started")

    def __init__(self, *args, **kwargs):
        self._multiWindow = kwargs.get('multi_window')
        self.started = False
        BaseWindow.__init__(self, *args, **kwargs)

    def onInit(self):
        if self.started:
            return
        self.started = True
        self._multiWindow._open()
        self.close()


class MultiWindow(object):
    __slots__ = ("_windows", "_next", "_properties", "_current", "_allClosed", "exitCommand", "_currentOnAction",
                 "_closeSignalled")

    def __init__(self, windows=None, default_window=None, **kwargs):
        self._windows = windows
        self._next = default_window or self._windows[0]
        self._properties = {}
        self._current = None
        self._allClosed = False
        self._closeSignalled = False
        self.exitCommand = None

    def __getattr__(self, name):
        if self._current:
            return getattr(self._current, name)

    def onCloseSignal(self, *args, **kwargs):
        self._closeSignalled = True
        self.doClose()

    def setWindows(self, windows):
        self._windows = windows

    def setDefault(self, default):
        self._next = default or self._windows[0]

    def windowIndex(self, window):
        if hasattr(window, 'MULTI_WINDOW_ID'):
            for i, w in enumerate(self._windows):
                if window.MULTI_WINDOW_ID == w.MULTI_WINDOW_ID:
                    return i
            return 0
        else:
            return self._windows.index(window.__class__)

    def nextWindow(self, window=None):
        if window is False:
            window = self._windows[self.windowIndex(self._current)]

        if window:
            if window.__class__ == self._current.__class__:
                return None
        else:
            idx = self.windowIndex(self._current)
            idx += 1
            if idx >= len(self._windows):
                idx = 0
            window = self._windows[idx]

        self._next = window
        self._current.doClose()
        return self._next

    def _setupCurrent(self, cls):
        self._current = cls(cls.xmlFile, cls.path, cls.theme, cls.res)
        self._current.onFirstInit = self._onFirstInit
        self._current.onReInit = self.onReInit
        self._current.onClick = self.onClick
        self._current.onFocus = self.onFocus

        self._currentOnAction = self._current.onAction
        self._current.onAction = self.onAction

    @classmethod
    def open(cls, **kwargs):
        mw = cls(**kwargs)
        b = _MWBackground(mw.bgXML, mw.path, mw.theme, mw.res, multi_window=mw)
        b.modal()
        del b
        import gc
        gc.collect(2)
        return mw

    def _open(self):
        while not MONITOR.abortRequested() and not self._allClosed:
            self._setupCurrent(self._next)
            self._current.modal()

        self._current.doClose()
        del self._current
        del self._next
        del self._currentOnAction

    def setProperty(self, key, value):
        self._properties[key] = value
        self._current.setProperty(key, value)

    def _onFirstInit(self):
        for k, v in self._properties.items():
            self._current.setProperty(k, v)

        plexapp.util.APP.on('close.windows', self.onCloseSignal)
        self.onFirstInit()

    def doClose(self):
        plexapp.util.APP.off('close.windows', self.onCloseSignal)
        self._allClosed = True
        self._current.doClose()

    def goHomeAction(self, action):
        if (util.HOME_BUTTON_MAPPED is not None
                and action.getButtonCode() == int(util.HOME_BUTTON_MAPPED) and hasattr(self, "goHome")):
            util.DEBUG_LOG("MultiWindow: Going home action")
            self.goHome(with_root=True)
            return True
        return

    def onFirstInit(self):
        pass

    def onReInit(self):
        pass

    def onAction(self, action):
        if action == xbmcgui.ACTION_PREVIOUS_MENU or action == xbmcgui.ACTION_NAV_BACK:
            self.doClose()
        elif self.goHomeAction(action):
            return
        self._currentOnAction(action)

    def onClick(self, controlID):
        pass

    def onFocus(self, controlID):
        pass


class SafeControlEdit(object):
    CHARS_LOWER = 'abcdefghijklmnopqrstuvwxyz'
    CHARS_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    CHARS_NUMBERS = '0123456789'
    CURSOR = '[COLOR FFCC7B19]|[/COLOR]'

    def __init__(self, control_id, label_id, window, key_callback=None, grab_focus=False):
        self.controlID = control_id
        self.labelID = label_id
        self._win = window
        self._keyCallback = key_callback
        self.grabFocus = grab_focus
        self._text = ''
        self._compatibleMode = False
        self.setup()

    def setup(self):
        self._labelControl = self._win.getControl(self.labelID)
        self._winOnAction = self._win.onAction
        self._win.onAction = self.onAction
        self.updateLabel()

    def setCompatibleMode(self, on):
        self._compatibleMode = on

    def onAction(self, action):
        try:
            controlID = self._win.getFocusId()
            if controlID == self.controlID:
                if self.processAction(action.getId()):
                    return
            elif self.grabFocus:
                if self.processOffControlAction(action.getButtonCode()):
                    self._win.setFocusId(self.controlID)
                    return
        except:
            traceback.print_exc()

        self._winOnAction(action)

    def processAction(self, action_id):
        if not self._compatibleMode:
            oldVal = self._text
            self._text = self._win.getControl(self.controlID).getText()

            if self._keyCallback:
                self._keyCallback(action_id, oldVal, self._text)

            self.updateLabel()

            return True
        oldVal = self.getText()

        if 61793 <= action_id <= 61818:  # Lowercase
            self.processChar(self.CHARS_LOWER[action_id - 61793])
        elif 61761 <= action_id <= 61786:  # Uppercase
            self.processChar(self.CHARS_UPPER[action_id - 61761])
        elif 61744 <= action_id <= 61753:
            self.processChar(self.CHARS_NUMBERS[action_id - 61744])
        elif action_id == 61728:  # Space
            self.processChar(' ')
        elif action_id == 61448:
            self.delete()
        else:
            return False

        if self._keyCallback:
            self._keyCallback(action_id, oldVal, self.getText())

        return True

    def processOffControlAction(self, action_id):
        oldVal = self.getText() if self._compatibleMode else self._text
        if 61505 <= action_id <= 61530:  # Lowercase
            self.processChar(self.CHARS_LOWER[action_id - 61505])
        elif 192577 <= action_id <= 192602:  # Uppercase
            self.processChar(self.CHARS_UPPER[action_id - 192577])
        elif 61488 <= action_id <= 61497:
            self.processChar(self.CHARS_NUMBERS[action_id - 61488])
        elif 61552 <= action_id <= 61561:
            self.processChar(self.CHARS_NUMBERS[action_id - 61552])
        elif action_id == 61472:  # Space
            self.processChar(' ')
        else:
            return False

        if self._keyCallback:
            self._keyCallback(action_id, oldVal, self.getText())

        return True

    def _setText(self, text):
        self._text = text

        if not self._compatibleMode:
            self._win.getControl(self.controlID).setText(text)
        self.updateLabel()

    def _getText(self):
        if not self._compatibleMode and self._win.getFocusId() == self.controlID:
            return self._win.getControl(self.controlID).getText()
        else:
            return self._text

    def updateLabel(self):
        self._labelControl.setLabel(self._getText() + self.CURSOR)

    def processChar(self, char):
        self._setText(self.getText() + char)

    def setText(self, text):
        self._setText(text)

    def getText(self):
        return self._getText()

    def append(self, text):
        self._setText(self.getText() + text)

    def delete(self):
        self._setText(self.getText()[:-1])


class PropertyTimer():
    def __init__(self, window_id, timeout, property_, value='', init_value='1', addon_id=None, callback=None):
        self._winID = window_id
        self._timeout = timeout
        self._property = property_
        self._value = value
        self._initValue = init_value
        self._endTime = 0
        self._thread = None
        self._addonID = addon_id
        self._closeWin = None
        self._closed = False
        self._callback = callback

    def _onTimeout(self):
        self._endTime = 0
        xbmcgui.Window(self._winID).setProperty(self._property, self._value)
        if self._addonID:
            xbmcgui.Window(10000).setProperty('{0}.{1}'.format(self._addonID, self._property), self._value)
        if self._closeWin:
            self._closeWin.doClose()
        if self._callback:
            self._callback()

    def _wait(self):
        while not MONITOR.abortRequested() and time.time() < self._endTime:
            xbmc.sleep(100)
        if MONITOR.abortRequested():
            return
        if self._endTime == 0:
            return
        self._onTimeout()

    def _stopped(self):
        return not self._thread or not self._thread.is_alive()

    def _reset(self):
        self._endTime = time.time() + self._timeout

    def _start(self):
        self.init(self._initValue)
        self._thread = threading.Thread(target=self._wait)
        self._thread.start()

    def stop(self, trigger=False):
        self._endTime = trigger and 1 or 0
        if not self._stopped():
            self._thread.join()

    def close(self):
        self._closed = True
        self.stop()

    def init(self, val):
        if val is False:
            return
        elif val is None:
            val = self._initValue

        xbmcgui.Window(self._winID).setProperty(self._property, val)
        if self._addonID:
            xbmcgui.Window(10000).setProperty('{0}.{1}'.format(self._addonID, self._property), val)

    def reset(self, close_win=None, init=None):
        self.init(init)

        if self._closed:
            return

        if not self._timeout:
            return

        self._closeWin = close_win
        self._reset()

        if self._stopped:
            self._start()


class WindowProperty():
    __slots__ = ("win", "prop", "val", "end", "old")

    def __init__(self, win, prop, val='1', end=''):
        self.win = win
        self.prop = prop
        self.val = val
        self.end = end
        self.old = self.win.getProperty(self.prop)

    def __enter__(self):
        self.win.setProperty(self.prop, self.val)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.win.setProperty(self.prop, self.end or self.old)


class GlobalProperty():
    __slots__ = ("_addonID", "prop", "val", "end", "old")

    def __init__(self, prop, val='1', end=''):
        self.prop = prop
        self.val = val
        self.end = end
        self.old = xbmc.getInfoLabel('Window(10000).Property(script.plex.{})'.format(prop))

    def __enter__(self):
        xbmcgui.Window(10000).setProperty('script.plex.{}'.format(self.prop), self.val)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        xbmcgui.Window(10000).setProperty('script.plex.{}'.format(self.prop), self.end or self.old)


def waitForVisibility(control):
    tries = 0
    while not xbmc.getCondVisibility('Control.IsVisible({0})'.format(control)) and tries < 50:
        util.MONITOR.waitForAbort(0.1)
        tries += 1