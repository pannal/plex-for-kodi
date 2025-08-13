# coding=utf-8
class PlaybackBtnMixin(object):
    def __init__(self, *args, **kwargs):
        self.playBtnClicked = False

    def reset(self, *args, **kwargs):
        self.playBtnClicked = False

    def onReInit(self):
        self.playBtnClicked = False
