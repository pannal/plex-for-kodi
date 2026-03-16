# coding=utf-8
from __future__ import absolute_import

from lib import util
from . import kodigui


class BlackoutDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-blackout_dialog.xml'
    path = util.ADDON.getAddonInfo('path')
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080
