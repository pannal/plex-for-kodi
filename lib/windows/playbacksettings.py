# coding=utf-8
from plexnet.util import INTERFACE

from lib import util
from lib.util import T
from . import dropdown


class PlaybackSettingsMixin(object):
    def playbackSettings(self, show, pos, bottom):
        pbs = INTERFACE.playbackManager(show)
        pbOpts = []
        transEnabled = T(33507)
        transDisabled = T(33508)

        currentSettings = {}
        for key, transID in INTERFACE.playbackManager.transMap.items():
            state = getattr(pbs, key)
            stateTrans = state and transEnabled or transDisabled
            pbOpts.append({'key': key, 'display': "{}: {}".format(stateTrans, T(transID))})
            currentSettings[key] = state

        # create a new dict which we can freely change while the dropdown is open
        newSettings = currentSettings.copy()

        # fixme: not sure if garbage collection is necessary here

        def callback(opts, mli, force_off=False):
            choice = mli.dataSource
            oc = newSettings[choice["key"]]
            ic = (not oc) if not force_off else False

            # invalidate any other setting if bingemode enabled
            if choice["key"] == "binge_mode" and ic:
                for m in opts.items:
                    if m.dataSource["key"] not in ("binge_mode", "auto_sync"):
                        callback(opts, m, force_off=True)
                del m

            # disable bingeMode if any other setting is enabled
            elif choice["key"] not in ("binge_mode", "auto_sync") and newSettings["binge_mode"]:
                m = opts.getListItem(0)
                callback(opts, m, force_off=True)
                del m

            newSettings[choice["key"]] = ic
            label = choice["display"].replace("{}: ".format(oc and transEnabled or transDisabled),
                                              "{}: ".format(ic and transEnabled or transDisabled))
            mli.setLabel(label)
            mli.dataSource["display"] = label
            del mli

        # fixme: not sure if garbage collection is necessary here
        util.garbageCollect()
        pbChoice = dropdown.showDropdown(pbOpts, pos, pos_is_bottom=bottom, close_direction='left',
                                         set_dropdown_prop=True,
                                         header="{}: {}".format(T(32925, 'Playback Settings'), show.defaultTitle),
                                         close_only_with_back=True, align_items='left',
                                         options_callback=callback)

        # write new settings for item if necessary
        if newSettings != currentSettings:
            INTERFACE.playbackManager(show, kv_dict=newSettings)
