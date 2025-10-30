from __future__ import absolute_import
from xml.etree import ElementTree
import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error

from . import plexapp
from . import plexconnection
from . import plexserver
from . import myplexrequest
from . import callback
from . import util


class MyPlexManager(object):
    gotResources = False

    def __init__(self):
        self.gotResources = False

    def publish(self):
        util.LOG('MyPlexManager().publish() - NOT IMPLEMENTED')
        return  # TODO: ----------------------------------------------------------------------------------------------------------------------------- IMPLEMENT?
        request = myplexrequest.MyPlexRequest("/devices/" + util.INTERFACE.getGlobal("clientIdentifier"))
        context = request.createRequestContext("publish")

        addrs = util.INTERFACE.getGlobal("roDeviceInfo").getIPAddrs()

        for iface in addrs:
            request.addParam(six.moves.urllib.parse.quote("Connection[][uri]"), "http://{0):8324".format(addrs[iface]))

        util.APP.startRequest(request, context, "_method=PUT")

    def refreshResources(self, force=False):
        util.LOG('MyPlexManager().refreshResources() - Force: {}', force)
        if force:
            plexapp.SERVERMANAGER.resetLastTest()

        request = myplexrequest.MyPlexRequest("/pms/resources")
        context = request.createRequestContext("resources", callback.Callable(self.onResourcesResponse),
                                               timeout=util.PLEXTV_TIMEOUT)

        if plexapp.ACCOUNT.isSecure:
            request.addParam("includeHttps", "1")

        util.APP.startRequest(request, context)

    def onResourcesResponse(self, request, response, context):
        servers = []

        response.parseResponse()

        # Save the last successful response to cache
        if response.isSuccess() and response.event:
            util.INTERFACE.setRegistry("mpaResources", response.event.text.encode('utf-8'), "xml_cache")
            util.DEBUG_LOG("Saved resources response to registry")
        # Load the last successful response from cache
        elif util.INTERFACE.getRegistry("mpaResources", None, "xml_cache"):
            data = ElementTree.fromstring(util.INTERFACE.getRegistry("mpaResources", None, "xml_cache"))
            response.parseFakeXMLResponse(data)
            util.DEBUG_LOG("Using cached resources")

        if response.container:
            for resource in response.container:
                util.DEBUG_LOG(
                    "Parsed resource from plex.tv: type:{0} clientIdentifier:{1} name:{2} product:{3} provides:{4}".format(
                        resource.type,
                        resource.clientIdentifier,
                        resource.name.encode('utf-8'),
                        resource.product.encode('utf-8'),
                        resource.provides.encode('utf-8')
                    )
                )

                for conn in resource.connections:
                    util.DEBUG_LOG('  {0}', conn)

                if 'server' in resource.provides or resource.product == "Plex Media Server":
                    server = plexserver.createPlexServerForResource(resource)
                    util.DEBUG_LOG('  {0}', server)
                    servers.append(server)

            self.gotResources = True
        plexapp.SERVERMANAGER.updateFromConnectionType(servers, plexconnection.PlexConnection.SOURCE_MYPLEX)
        util.APP.trigger("loaded:myplex_servers", servers=servers, source="myplex")


MANAGER = MyPlexManager()
