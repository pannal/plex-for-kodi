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
        while tries < 20 and focus == '':
            focus = xbmc.getInfoLabel('Container({}).Position'.format(container_id))
            util.MONITOR.waitForAbort(0.1)
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

        sectionRoles = busy.widthDialog(mli.dataSource.sectionRoles, '', delay=True)

        if not sectionRoles:
            util.DEBUG_LOG('No sections found for actor')
            return

        if len(sectionRoles) > 1:
            x, y = self.getRoleItemDDPosition()
            if x == -1:
                return

            options = [{'role': r, 'display': r.reasonTitle} for r in sectionRoles]
            choice = dropdown.showDropdown(options, (x, y), pos_is_bottom=False)

            if not choice:
                return

            role = choice['role']
        else:
            role = sectionRoles[0]

        self.processCommand(opener.open(role))
