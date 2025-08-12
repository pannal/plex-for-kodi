from __future__ import absolute_import

from . import plexapp
from . import plexconnection
from . import plexserver
from . import plexresource
from . import plexservermanager
from . import plexobjects
from . import plexlibrary
from . import compat
from . import util

from lib.i18n import T


class MyPlexServer(plexserver.PlexServer):
    TYPE = 'MYPLEXSERVER'

    def __init__(self):
        plexserver.PlexServer.__init__(self)
        self.uuid = 'myplex'
        self.name = 'plex.tv'
        conn = plexconnection.PlexConnection(plexresource.ResourceConnection.SOURCE_MYPLEX, "https://plex.tv", False,
                                             None, skipLocalCheck=True)
        self.connections.append(conn)
        self.activeConnection = conn

    def getToken(self):
        return plexapp.ACCOUNT.authToken

    def buildUrl(self, path, includeToken=False):
        if "://node.plexapp.com" in path:
            # Locate the best fit server that supports channels, otherwise we'll
            # continue to use the node urls. Service code between the node and
            # PMS differs sometimes, so it's a toss up which one is actually
            # more accurate. Either way, we try to offload work from the node.

            server = plexservermanager.MANAGER.getChannelServer()
            if server:
                url = server.swizzleUrl(path, includeToken)
                if url:
                    return url

        return plexserver.PlexServer.buildUrl(self, path, includeToken)


class PlexDiscoverServer(MyPlexServer):
    TYPE = 'PLEXDISCOVERSERVER'
    DEFER_HUBS = True

    def __init__(self):
        MyPlexServer.__init__(self)
        self.uuid = 'plexdiscover'
        self.name = 'discover.plex.tv'

        # tell the server manager we're a synced server and it should try to use a more fitting server for photo
        # encoding
        self.synced = True
        conn = plexconnection.PlexConnection(plexresource.ResourceConnection.SOURCE_MYPLEX,
                                             "https://discover.provider.plex.tv", False,
                                             None, skipLocalCheck=True)
        self.connections.append(conn)
        self.activeConnection = conn

        # inject our plextv timeout
        #self.session.request = functools.partial(self.session.request, timeout=plexserver.util.PLEXTV_TIMEOUT)


    def hubs(self, section=None, count=None, search_query=None, section_ids=None, ignore_hubs=None):
        hubs = []

        self.currentHubs = {} if self.currentHubs is None else self.currentHubs

        wanted_hubs = [
            ("/hubs/sections/watchlist/continueWatching", {'contentDirectoryID': 'watchlist'}),
            ("/hubs/sections/watchlist/recently-added", {'contentDirectoryID': 'watchlist'}),
            ("/hubs/sections/watchlist/coming-soon", {'contentDirectoryID': 'watchlist'}),
            ("/hubs/sections/home/top_watchlisted", {'contentDirectoryID': 'home'}),
            ("/hubs/sections/home/coming-soon", {'contentDirectoryID': 'home'}),
            ("/hubs/sections/home/trending-friends", {'contentDirectoryID': 'home'}),
            ("/hubs/sections/home/trending-for-you", {'contentDirectoryID': 'home'}),
            ("/hubs/sections/home/new-for-you", {'contentDirectoryID': 'home'}),
        ]
        wanted_hubs_dict = dict(wanted_hubs)

        # discover hubs
        params = {
            'includeMeta': "1",
            'includeExternalMetadata': '1',
            'excludeFields': 'summary'
        }

        for q in ('/hubs/sections/watchlist', '/hubs/sections/home'):
            data = self.query(q, params=params)
            container = plexobjects.PlexContainer(data, initpath=q, server=self, address=q)

            if data:
                for elem in data:
                    if elem.attrib.get('key') not in wanted_hubs_dict:
                        continue
                    hubIdent = elem.attrib.get('hubIdentifier')
                    hubTitle = T(34019, "Discover {}").format(elem.attrib.get('title')) if q == '/hubs/sections/home' else elem.attrib.get('title')
                    self.currentHubs["{}:{}".format(section, hubIdent)] = hubTitle

                    if ignore_hubs and "{}:{}".format(section, hubIdent) in ignore_hubs:
                        continue

                    hub = plexlibrary.WatchlistHub(elem, server=self, container=container)
                    hub.title = hubTitle
                    hubs.append(hub)

        base_params = {
            'includeMeta': "1",
            'includeExternalMetadata': '1',
        }

        # fetch hub data
        for hub in hubs:
            params = base_params.copy()
            params.update(wanted_hubs_dict[hub.key])
            data = self.query(hub.key, params=params)
#
            if data:
                hubTitle = hub.title
                hub.init(data)
                # re-inject our modified hubtitle
                hub.title = hubTitle

        return hubs