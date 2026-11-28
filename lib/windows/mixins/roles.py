# coding=utf-8

from kodi_six import xbmc

from lib import util
from .. import busy
from .. import dropdown
from .. import opener


class RolesMixin(object):
    def getRoleItemDDPosition(self, y=None, container_id='400'):
        y = util.vscale(600 if y is None else y)

        tries = 0
        focus = xbmc.getInfoLabel('Container({}).Position'.format(container_id))
        while tries < util.MONITOR.waitAmount(2) and focus == '':
            focus = xbmc.getInfoLabel('Container({}).Position'.format(container_id))
            util.MONITOR.waitFor()
            tries += 1

        try:
            focus = int(focus)
        except ValueError:
            return -1, -1

        x = ((focus + 1) * 304) - 100
        return x, y

    def roleClicked(self):
        mli = self.rolesListControl.getSelectedItem()
        if not mli:
            return

        role = mli.dataSource
        if not role:
            return

        # Open the actor detail window directly
        self.processCommand(opener.open(role))
