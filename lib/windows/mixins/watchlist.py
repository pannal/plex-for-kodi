# coding=utf-8
from lib import backgroundthread, util
from lib.i18n import T
from lib.windows import kodigui
from lib.windows import dropdown
from plexnet import plexapp, plexobjects, util as pnUtil, exceptions


class WatchlistCheckBaseTask(backgroundthread.Task):
    def setup(self, server_uuid, guid, callback):
        self.server_uuid = server_uuid
        self.guid = guid
        self.callback = callback
        return self

    def getServer(self):
        return plexapp.SERVERMANAGER.getServer(self.server_uuid)


class AvailabilityCheckTask(WatchlistCheckBaseTask):
    def setup(self, *args, **kwargs):
        media_type = kwargs.pop('media_type', None)
        WatchlistCheckBaseTask.setup(self, *args)
        self.media_type = media_type
        return self

    def run(self):
        if self.isCanceled():
            return

        server = None
        try:
            if self.isCanceled():
                return

            server = self.getServer()
            res = server.query("/library/all", guid=self.guid, type=plexobjects.searchType(self.media_type))
            if res and res.get("size", 0):
                # find ratingKey
                found = []
                for child in res:
                    if child.tag in ("Directory", "Video"):
                        rk = child.get("ratingKey")
                        if rk:
                            metadata = {"rating_key": rk, "resolution": None, "bitrate": None, "season_count": None,
                                        "available": None, "server_uuid": str(self.server_uuid), "type": self.media_type}

                            # find resolution for movies
                            if self.media_type == "movie":
                                for _child in child:
                                    if _child.tag == "Media":
                                        metadata["resolution"] = _child.get("videoResolution")
                                        metadata["bitrate"] = _child.get("bitrate")
                                        break
                            else:
                                metadata["season_count"] = child.get("childCount")
                            metadata["available"] = child.get("originallyAvailableAt")
                            found.append((server.name, metadata))

                if found:
                    # sort by quality
                    if self.media_type == "movie" and len(found) > 1:
                        found.sort(key=lambda item: int(item[1]["bitrate"]), reverse=True)

                self.callback(found)
                return
            self.callback(None)
        except:
            util.ERROR()
        finally:
            del server


class IsWatchlistedTask(WatchlistCheckBaseTask):
    def run(self):
        if self.isCanceled():
            return

        server = None
        try:
            if self.isCanceled():
                return
            server = self.getServer()
            res = server.query("/library/metadata/{}/userState".format(self.guid))
            is_wl = False

            # some etree foo to find the watchlisted state
            if res and res.get("size", 0):
                for child in res:
                    if child.tag == "UserState":
                        if child.get("watchlistedAt", None):
                            is_wl = True
                        break
            self.callback(is_wl)
        except:
            util.ERROR()
        finally:
            del server


def wl_wrap(f):
    def wrapper(cls, item, *args, **kwargs):
        if not cls.wl_enabled:
            return

        # if watchlist not wanted, return

        return f(cls, item, *args, **kwargs)
    return wrapper


def GUIDToRatingKey(guid):
    return guid.rsplit("/")[-1]


def removeFromWatchlistBlind(guid):
    if not util.getUserSetting("use_watchlist", True):
        return

    try:
        if not guid or not guid.startswith("plex://"):
            return

        server = pnUtil.SERVERMANAGER.getDiscoverServer()
        server.query("/actions/removeFromWatchlist", ratingKey=GUIDToRatingKey(guid), method="put")
    except:
        pass


class WatchlistUtilsMixin(object):
    WL_BTN_WAIT = 2302
    WL_BTN_MULTIPLE = 2303
    WL_BTN_SINGLE = 2304
    WL_BTN_UPCOMING = 2305

    WL_BTN_STATE_NOT_WATCHLISTED = 308
    WL_BTN_STATE_WATCHLISTED = 309

    WL_RELEVANT_BTNS = (302, WL_BTN_WAIT, WL_BTN_MULTIPLE, WL_BTN_SINGLE, WL_BTN_UPCOMING)

    WL_BTN_STATE_BTNS = (WL_BTN_STATE_NOT_WATCHLISTED, WL_BTN_STATE_WATCHLISTED)

    wl_availability = None

    def __init__(self, *args, **kwargs):
        super(WatchlistUtilsMixin, self).__init__()
        self.wl_availability = []
        self.is_watchlisted = False
        self.wl_enabled = False
        self.wl_ref = None
        self.wl_item_children = []

    def watchlist_setup(self, item):
        self.wl_enabled = util.getUserSetting("use_watchlist", True) and item.guid and item.guid.startswith("plex://")
        self.wl_ref = GUIDToRatingKey(item.guid)
        self.setBoolProperty("watchlist_enabled", self.wl_enabled)

    @wl_wrap
    def wl_item_verbose(self, meta):
        if meta["type"] == "movie":
            res = "{}p".format(meta['resolution']) if not "k" in meta['resolution'] else meta['resolution'].upper()
            sub = '{} ({})'.format(res, pnUtil.bitrateToString(int(meta['bitrate']) * 1024))
        else:
            season_str = T(34006, '{} season') if int(meta["season_count"]) == 1 else T(34003, '{} seasons')
            sub = season_str.format(meta['season_count'])
        return sub

    @wl_wrap
    def wl_item_opener(self, ref, item_open_callback, selected_item=None):
        if len(self.wl_availability) > 1 and not selected_item:
            # choose
            options = []
            for idx, tup in enumerate(self.wl_availability):
                server, meta = tup
                verbose = self.wl_item_verbose(meta)
                options.append({'key': idx,
                                'display': '{}, {}'.format(server, verbose)
                              })

            choice = dropdown.showDropdown(
                options=options,
                pos=(660, 441),
                close_direction='none',
                set_dropdown_prop=False,
                header=T(34004, 'Choose server'),
                dialog_props=self.dialogProps,
                align_items="left"
            )

            if not choice:
                return

            return self.wl_item_opener(ref, item_open_callback, selected_item=self.wl_availability[choice['key']][1])

        item_meta = selected_item or self.wl_availability[0][1]
        rk = item_meta.get("rating_key", None)
        if rk:
            server_differs = item_meta["server_uuid"] != plexapp.SERVERMANAGER.selectedServer.uuid
            server = orig_srv = plexapp.SERVERMANAGER.selectedServer

            if server_differs:
                server = plexapp.SERVERMANAGER.getServer(item_meta["server_uuid"])

            try:
                if server_differs:
                    # fire event to temporarily change server
                    util.LOG("Temporarily changing server source to: {}", server.name)
                    plexapp.util.APP.trigger('change:tempServer', server=server)

                item_open_callback(item=rk, inherit_from_watchlist=False, server=server, is_watchlisted=True,
                                   came_from=self.wl_ref)
            finally:
                if server_differs:
                    util.LOG("Reverting to server source: {}", orig_srv.name)
                    plexapp.util.APP.trigger('change:tempServer', server=orig_srv)

            self.checkIsWatchlisted(ref)

    @wl_wrap
    def wl_auto_remove(self, ref):
        if self.is_watchlisted and ref.isFullyWatched and util.getUserSetting('watchlist_auto_remove', True):
            self.removeFromWatchlist(ref)
            util.DEBUG_LOG("Watchlist: Item {} is fully watched, removed from watchlist", ref.ratingKey)
            return True
        elif not ref.isFullyWatched:
            util.DEBUG_LOG("Watchlist: Item {} is not fully watched, skipping", ref.ratingKey)

    @wl_wrap
    def watchlistItemAvailable(self, item, shortcut_watchlisted=False):
        """
        Is a watchlisted item available on any of the user's Plex servers?
        :param item:
        :return:
        """

        if shortcut_watchlisted:
            self.is_watchlisted = True
            self.setBoolProperty("is_watchlisted", True)
        self.setBoolProperty("wl_availability_checking", True)
        self.wl_checking_servers = len(list(pnUtil.SERVERMANAGER.connectedServers))
        self.wl_play_button_id = self.WL_BTN_WAIT

        def wl_set_btn():
            if not self.lastFocusID or self.lastFocusID in self.WL_RELEVANT_BTNS:
                change_to = None
                if self.wl_checking_servers:
                    change_to = self.WL_BTN_WAIT
                elif len(self.wl_availability) > 1:
                    change_to = self.WL_BTN_MULTIPLE
                elif len(self.wl_availability) == 1:
                    change_to = self.WL_BTN_SINGLE
                elif not self.wl_availability:
                    change_to = self.WL_BTN_UPCOMING

                if change_to and self.wl_play_button_id != change_to:
                    self.wl_play_button_id = change_to
                    # wait for visibility
                    kodigui.waitForVisibility(self.wl_play_button_id)
                    self.focusPlayButton(extended=True)

        wl_set_btn()

        def wl_av_callback(data):
            if data:
                self.wl_availability += data
                for server_name, metadata in data:
                    util.DEBUG_LOG("Watchlist availability: {}: {}", server_name, metadata)
                    self.wl_item_children.append(metadata['rating_key'])

            self.setBoolProperty("wl_availability", len(self.wl_availability) == 1)
            self.setBoolProperty("wl_availability_multiple", len(self.wl_availability) > 1)
            self.wl_checking_servers -= 1
            if self.wl_checking_servers == 0:
                self.setBoolProperty("wl_availability_checking", False)
            if self.wl_availability:
                compute = ", ".join("{}: {}".format(sn, self.wl_item_verbose(meta)) for sn, meta in self.wl_availability)
                self.setProperty("wl_server_availability_verbose", compute)

            wl_set_btn()

        for cserver in pnUtil.SERVERMANAGER.connectedServers:
            task = AvailabilityCheckTask().setup(cserver.uuid, item.guid, wl_av_callback, media_type=item.type)
            backgroundthread.BGThreader.addTask(task)

    @wl_wrap
    def checkIsWatchlisted(self, item):
        """
        Is an item on the user's watch list?
        :param item:
        :return:
        """

        def callback(state):
            self.is_watchlisted = state
            self.setBoolProperty("is_watchlisted", state)
            util.DEBUG_LOG("Watchlist state for item {}: {}", item.ratingKey, state)

        wl_rk = GUIDToRatingKey(item.guid)
        task = IsWatchlistedTask().setup('plexdiscover', wl_rk, callback)
        backgroundthread.BGThreader.addTask(task)

    def _modifyWatchlist(self, item, method="addToWatchlist"):
        server = pnUtil.SERVERMANAGER.getDiscoverServer()

        try:
            server.query("/actions/{}".format(method), ratingKey=GUIDToRatingKey(item.guid), method="put")
            util.DEBUG_LOG("Watchlist action {} for {} succeeded", method, item.ratingKey)
            self.is_watchlisted = method == "addToWatchlist"
            self.setBoolProperty("is_watchlisted", method == "addToWatchlist")
            pnUtil.APP.trigger("watchlist:modified")
            return method == "addToWatchlist"
        except exceptions.BadRequest:
            util.DEBUG_LOG("Watchlist action {} for {} failed", method, item.ratingKey)

    @wl_wrap
    def addToWatchlist(self, item):
        return self._modifyWatchlist(item)

    @wl_wrap
    def removeFromWatchlist(self, item):
        return self._modifyWatchlist(item, method="removeFromWatchlist")

    @wl_wrap
    def toggleWatchlist(self, item):
        return self._modifyWatchlist(item, method="removeFromWatchlist" if self.is_watchlisted else "addToWatchlist")
