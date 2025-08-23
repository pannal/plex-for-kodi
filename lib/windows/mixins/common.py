# coding=utf-8

from kodi_six import xbmcgui
from lib import util
from .. import optionsdialog
from lib.i18n import T


class CommonMixin(object):
    @classmethod
    def isWatchedAction(cls, action):
        return action == xbmcgui.ACTION_NONE and action.getButtonCode() == 61527

    def toggleWatched(self, item, state=None, **kw):
        """

        :param item:
        :param state: the state we want to set watched to
        :param kw:
        :return:
        """
        if state is None:
            state = not item.isFullyWatched

        if util.getSetting('home_confirm_actions') and item.TYPE in ('season', 'show'):
            if item.TYPE == 'season':
                title = u"{} - {}".format(item.parentTitle, item.title)
            else:
                title = item.title
            button = optionsdialog.show(
                T(32319, "Mark Played") if state else T(32318, "Mark Unplayed"),  title,
                T(32328, 'Yes'),
                T(32329, 'No'),
                dialog_props=getattr(self, "carriedProps", getattr(self, "dialogProps", None))
            )

            if button != 0:
                return

        util.DEBUG_LOG("Toggling watched for {} to: {}", item, state)

        if state:
            item.markWatched(**kw)
            return False
        else:
            item.markUnwatched(**kw)
            return True
