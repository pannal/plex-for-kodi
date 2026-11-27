# coding=utf-8

from kodi_six import xbmcgui
from lib import util
from .. import optionsdialog
from lib.i18n import T


class CommonMixin(object):
    @classmethod
    def isWatchedAction(cls, action):
        return action == xbmcgui.ACTION_NONE and action.getButtonCode() == 61527

    def toggleWatched(self, item, state=None, confirmed=False, **kw):
        """

        :param item:
        :param state: the state we want to set watched to
        :param kw:
        :return:
        """
        if state is None:
            state = not item.isFullyWatched

        if not confirmed and util.getSetting('home_confirm_actions') and item.TYPE in ('season', 'show'):
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
        state = bool(state)

        before = getattr(self, 'beforeWatchedChange', None)
        if before:
            before(item, state)
        is_video = item.TYPE in ('movie', 'episode', 'season', 'show')
        if is_video:
            from lib import playback_sync
            context = playback_sync.supersedeWrites(item)

        if state:
            item.markWatched(**kw)
        else:
            item.markUnwatched(**kw)
        if is_video:
            playback_sync.finishWatchChange(item, state, context)
        return state
