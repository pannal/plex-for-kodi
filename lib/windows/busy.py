from __future__ import absolute_import

import threading

from kodi_six import xbmcgui

from lib import util
from . import kodigui


class BusyWindow(kodigui.BaseDialog):
    xmlFile = 'script-plex-busy.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080


class BlockingBusyWindow(BusyWindow):
    def onAction(self, action):
        if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_STOP):
            return False


class BusyClosableWindow(BusyWindow):
    ctx = None

    def onAction(self, action):
        if action in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_STOP):
            self.ctx.shouldClose = True


class BusyClosableMsgWindow(BusyClosableWindow):
    xmlFile = 'script-plex-busy_msg.xml'

    def setMessage(self, msg):
        self.setProperty("message", msg)


def dialog(msg='LOADING', condition=None, delay=True, delay_time=0.5):
    def methodWrap(func):
        def inner(*args, **kwargs):
            timer = None
            w = BusyWindow.create(show=not delay)

            if delay:
                timer = threading.Timer(delay_time, w.show)
                timer.start()

            try:
                return func(*args, **kwargs)
            finally:
                if timer and timer.is_alive():
                    timer.cancel()
                    timer.join()
                del timer
                w.doClose()
                try:
                    del w
                except:
                    pass
                util.garbageCollect()

        if condition is not None:
            return condition() and inner or func
        return inner

    return methodWrap


def busy_property(delay=True, delay_time=0.5):
    def methodWrap(func):
        def inner(win, *args, **kwargs):
            def setProp(w):
                w.setProperty('busy', '1')

            timer = None
            if delay:
                timer = threading.Timer(delay_time, lambda: setProp(win))
                timer.start()
            else:
                setProp(win)
            try:
                return func(win, *args, **kwargs)
            finally:
                if timer and timer.is_alive():
                    timer.cancel()
                    timer.join()
                del timer
                win.setProperty('busy', '')
        return inner
    return methodWrap



def widthDialog(method, msg, *args, **kwargs):
    condition = kwargs.pop("condition", None)
    delay = kwargs.pop("delay", False)
    delay_time = kwargs.pop("delay_time", 0.5)
    return dialog(msg or 'LOADING', condition=condition, delay=delay, delay_time=delay_time)(method)(*args, **kwargs)


class BusyContext(object):
    w = None
    timer = None
    shouldClose = False
    window_cls = BusyWindow
    delay = False

    def __init__(self, delay=False, delay_time=0.5):
        self.delay = delay
        self.delayTime = delay_time

    def __enter__(self):
        self.w = self.window_cls.create(show=not self.delay)
        self.w.ctx = self
        if self.delay:
            self.timer = threading.Timer(self.delayTime, lambda: self.w.show())
            self.timer.start()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            util.ERROR()

        if self.timer and self.timer.is_alive():
            self.timer.cancel()
            self.timer.join()

        self.w.doClose()
        del self.w
        self.w = None
        util.garbageCollect()
        return True


class BusyMsgContext(BusyContext):
    window_cls = BusyClosableMsgWindow

    def setMessage(self, msg):
        self.w.setMessage(msg)


class BusySignalContext(BusyMsgContext):
    """
    Duplicates functionality of plex.CallbackEvent to a certain degree
    """
    window_cls = BusyWindow
    delay = True

    def __init__(self, context, signal, wait_max=10, delay=True, delay_time=0.5, interval=0.1):
        self.wfSignal = signal
        self.signalEmitter = context
        self.waitMax = wait_max
        self.interval = interval
        self.ignoreSignal = False
        self.signalReceived = False

        super(BusySignalContext, self).__init__(delay=delay, delay_time=delay_time)

        context.on(signal, self.onSignal)

    def onSignal(self, *args, **kwargs):
        self.signalReceived = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            util.ERROR()

        try:
            if not self.ignoreSignal:
                waited = 0
                while not self.signalReceived and waited < self.waitMax:
                    util.MONITOR.waitForAbort(self.interval)
                    waited += self.interval
        finally:
            self.signalEmitter.off(self.wfSignal, self.onSignal)

        return super(BusySignalContext, self).__exit__(exc_type, exc_val, exc_tb)


class BusyClosableMsgContext(BusyMsgContext):
    pass


class BusyBlockingContext(BusyContext):
    window_cls = BlockingBusyWindow


class ProgressDialog(object):
    dialog = None
    header = None
    message = None

    def __init__(self, header, message=None, bg=True, raise_hard=False):
        self.header = header
        self.message = message
        self.bg = bg
        self.raise_hard = raise_hard

    def __enter__(self):
        self.dialog = xbmcgui.DialogProgressBG() if self.bg else xbmcgui.DialogProgress()
        self.dialog.create(self.header, self.message)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            util.ERROR()

        self.dialog.close()
        del self.dialog
        self.dialog = None
        util.garbageCollect()
        if exc_type is not None and self.raise_hard:
            raise exc_value
        return True

    def update(self, perc, header=None, message=None):
        if self.bg:
            self.dialog.update(perc, header or self.header, message or self.message)
        else:
            self.dialog.update(perc, message or self.message)

    def isCanceled(self):
        if self.bg:
            return False
        return self.dialog.iscanceled()
