# coding=utf-8
from .kodi_util import ADDON


def T(ID, eng=''):
    s = ADDON.getLocalizedString(ID)
    return s if s != "" else eng


TRANSLATED_ROLES = {
    'Director': T(32383, 'Director'),
    'Writer': T(32402, 'Writer'),
    'Producer': 'Producer',
    '': T(32441, 'Unknown')
}
