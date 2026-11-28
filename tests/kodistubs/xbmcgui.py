# coding=utf-8
"""
Stand-in for Kodi's `xbmcgui`.

Only the parts PM4K touches outside of lib/windows are modelled with real
behaviour: window properties (PM4K's cross-process signalling channel) and
Dialog. The control classes exist so imports resolve, but they are inert -
GUI windows are out of scope for this suite.
"""

from __future__ import absolute_import

from kodienv import ENV

INPUT_ALPHANUM = 0
INPUT_NUMERIC = 1
INPUT_DATE = 2
INPUT_TIME = 3
INPUT_IPADDRESS = 4
INPUT_PASSWORD = 5

ALPHANUM_HIDE_INPUT = 1
PASSWORD_VERIFY = 1

DLG_YESNO_NO_BTN = 0
DLG_YESNO_YES_BTN = 1
DLG_YESNO_CUSTOM_BTN = 2

NOTIFICATION_INFO = "info"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_ERROR = "error"

INPUT_STRING = 0

# Kodi action ids, as used by lib/windows. The values match Kodi's own
# key.h so that a test comparing against a literal still lines up.
ACTION_NONE = 0
ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_PAGE_UP = 5
ACTION_PAGE_DOWN = 6
ACTION_SELECT_ITEM = 7
ACTION_BACKSPACE = 110
ACTION_PAUSE = 12
ACTION_STOP = 13
ACTION_NEXT_ITEM = 14
ACTION_PREV_ITEM = 15
ACTION_STEP_FORWARD = 17
ACTION_STEP_BACK = 18
ACTION_BIG_STEP_FORWARD = 19
ACTION_BIG_STEP_BACK = 20
ACTION_PREVIOUS_MENU = 10
ACTION_CONTEXT_MENU = 117
ACTION_NAV_BACK = 92
ACTION_PLAYER_PLAY = 79
ACTION_PLAYER_PLAYPAUSE = 229
ACTION_FIRST_PAGE = 159
ACTION_LAST_PAGE = 160
ACTION_MOUSE_MOVE = 107
ACTION_MOUSE_DRAG = 106
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_MOUSE_WHEEL_UP = 104
ACTION_MOUSE_WHEEL_DOWN = 105

CONTROL_TEXT_OFFSET_X = 10
CONTROL_TEXT_OFFSET_Y = 2


def getCurrentWindowId():
    return ENV.current_window_id


def getCurrentWindowDialogId():
    return ENV.current_dialog_id


def getScreenWidth():
    return ENV.screen[0]


def getScreenHeight():
    return ENV.screen[1]


class Window(object):
    def __init__(self, existingWindowId=-1):
        self.windowId = existingWindowId

    def getProperty(self, key):
        return ENV.window_props[self.windowId].get(key, "")

    def setProperty(self, key, value):
        ENV.window_props[self.windowId][key] = value

    def clearProperty(self, key):
        ENV.window_props[self.windowId].pop(key, None)

    def clearProperties(self):
        ENV.window_props[self.windowId].clear()

    def getFocusId(self):
        return 0

    def setFocusId(self, pControlId):
        pass

    def show(self):
        pass

    def close(self):
        pass

    def doModal(self):
        pass


class WindowXML(Window):
    def __init__(self, *args, **kwargs):
        Window.__init__(self, -1)


class WindowXMLDialog(WindowXML):
    pass


class WindowDialog(Window):
    pass


class ListItem(object):
    def __init__(self, label="", label2="", path="", offscreen=False):
        self.label = label
        self.label2 = label2
        self.path = path
        self._props = {}
        self._art = {}

    def getLabel(self):
        return self.label

    def setLabel(self, label):
        self.label = label

    def getLabel2(self):
        return self.label2

    def setLabel2(self, label):
        self.label2 = label

    def getPath(self):
        return self.path

    def setPath(self, path):
        self.path = path

    def getProperty(self, key):
        return self._props.get(key, "")

    def setProperty(self, key, value):
        self._props[key] = value

    def setProperties(self, values):
        self._props.update(values)

    def setArt(self, dictionary):
        self._art.update(dictionary)

    def getArt(self, key):
        return self._art.get(key, "")

    def setInfo(self, type, infoLabels):
        pass

    def select(self, selected):
        pass


class Dialog(object):
    """
    Answers come from ENV.dialog_answers (a deque). Each call pops the next
    answer; an empty deque falls back to a neutral default (cancel/no/-1) so a
    test that forgets to script one gets "user dismissed it" rather than a
    surprise confirmation.
    """

    def _answer(self, method, args, kwargs, default):
        ENV.dialog_calls.append((method, args, kwargs))
        if ENV.dialog_answers:
            return ENV.dialog_answers.popleft()
        return default

    def ok(self, heading, message):
        return self._answer("ok", (heading, message), {}, True)

    def yesno(self, heading, message, *args, **kwargs):
        return self._answer("yesno", (heading, message) + args, kwargs, False)

    def yesnocustom(self, heading, message, customlabel, *args, **kwargs):
        return self._answer("yesnocustom", (heading, message, customlabel) + args, kwargs,
                            DLG_YESNO_NO_BTN)

    def select(self, heading, list, autoclose=0, preselect=-1, useDetails=False):
        return self._answer("select", (heading, list), {"preselect": preselect}, -1)

    def multiselect(self, heading, options, autoclose=0, preselect=None, useDetails=False):
        return self._answer("multiselect", (heading, options), {"preselect": preselect}, None)

    def contextmenu(self, list):
        return self._answer("contextmenu", (list,), {}, -1)

    def notification(self, heading, message, icon="", time=5000, sound=True):
        return self._answer("notification", (heading, message), {"time": time}, None)

    def input(self, heading, defaultt="", type=INPUT_ALPHANUM, option=0, autoclose=0):
        return self._answer("input", (heading, defaultt), {"type": type}, "")

    def numeric(self, type, heading, defaultt="", bHiddenInput=False):
        return self._answer("numeric", (type, heading, defaultt), {}, "")

    def browse(self, type, heading, shares, *args, **kwargs):
        return self._answer("browse", (type, heading, shares), kwargs, "")

    def textviewer(self, heading, text, usemono=False):
        return self._answer("textviewer", (heading, text), {}, None)


class DialogProgress(object):
    def __init__(self):
        self.percent = 0
        self.closed = False
        self.canceled = False

    def create(self, heading, message=""):
        ENV.dialog_calls.append(("progress.create", (heading, message), {}))

    def update(self, percent, message=""):
        self.percent = percent

    def iscanceled(self):
        return self.canceled

    def close(self):
        self.closed = True


class DialogProgressBG(DialogProgress):
    pass


class DialogBusy(object):
    def create(self):
        pass

    def close(self):
        pass

    def update(self, percent):
        pass

    def iscanceled(self):
        return False


class _Control(object):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, item):
        def _noop(*args, **kwargs):
            return None
        return _noop


ControlLabel = ControlImage = ControlButton = ControlList = ControlGroup = _Control
ControlFadeLabel = ControlTextBox = ControlProgress = ControlSlider = _Control
ControlEdit = ControlSpin = ControlRadioButton = _Control
