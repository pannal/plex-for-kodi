from __future__ import absolute_import
import random
import socket

from . import http
from . import callback
from . import util

try:
    from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
except ImportError:
    from _ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

HAS_ICMPLIB = False
try:
    from icmplib import ping, resolve, ICMPLibError
except:
    from urlparse import urlparse
else:
    HAS_ICMPLIB = True
    from urllib.parse import urlparse

# local networks
DOCKER_NETWORK = IPv4Network(u'172.16.0.0/12')
LOCAL_NETWORKS = {
    4: [IPv4Network(u'10.0.0.0/8'), IPv4Network(u'192.168.0.0/16'), DOCKER_NETWORK,
        IPv4Network(u'127.0.0.0/8')],
    6: [IPv6Network(u'fd00::/8')]
}

LOCALS_SEEN = {}


class ConnectionSource(int):
    def init(self, name):
        self.name = name
        return self

    def __repr__(self):
        return self.name


class PlexConnection(object):
    # Constants
    STATE_UNKNOWN = "unknown"
    STATE_UNREACHABLE = "unreachable"
    STATE_REACHABLE = "reachable"
    STATE_UNAUTHORIZED = "unauthorized"
    STATE_INSECURE = "insecure_untested"

    SOURCE_MANUAL = ConnectionSource(1).init('MANUAL')
    SOURCE_DISCOVERED = ConnectionSource(2).init('DISCOVERED')
    SOURCE_MANUAL_AND_DISCOVERED = ConnectionSource(3).init('MANUAL, DISCOVERED')
    SOURCE_MYPLEX = ConnectionSource(4).init('MYPLEX')
    SOURCE_MANUAL_AND_MYPLEX = ConnectionSource(5).init('MANUAL, MYPLEX')
    SOURCE_DISCOVERED_AND_MYPLEX = ConnectionSource(6).init('DISCOVERED, MYPLEX')
    SOURCE_ALL = ConnectionSource(7).init('ALL')

    SCORE_REACHABLE = 4
    SCORE_LOCAL = 2
    SCORE_SECURE = 1

    SOURCE_BY_VAL = {
        1: SOURCE_MANUAL,
        2: SOURCE_DISCOVERED,
        3: SOURCE_MANUAL_AND_DISCOVERED,
        4: SOURCE_MYPLEX,
        5: SOURCE_MANUAL_AND_MYPLEX,
        6: SOURCE_DISCOVERED_AND_MYPLEX,
        7: SOURCE_ALL
    }

    def __init__(self, source, address, isLocal, token, isFallback=False, skipLocalCheck=False):
        self.state = self.STATE_UNKNOWN
        self.sources = source
        self.address = address
        self.isLocal = isLocal
        self.localVerified = False
        self.isSecure = address[:5] == 'https'
        self.isFallback = isFallback
        self.token = token
        self.refreshed = True
        self.score = 0
        self.request = None
        self.pdHostnameResolved = False

        self.lastTestedAt = 0
        self.hasPendingRequest = False

        self.isSecureButLocal = False

        if not HAS_ICMPLIB:
            util.WARN_LOG("icmplib not found, can't check local connectivity")

        # check whether hostname is on LAN
        if HAS_ICMPLIB and util.CHECK_LOCAL and not skipLocalCheck:
            self.checkLocal()

        if not util.NO_HOST_CHECK:
            self.checkNativeResolve()

        self.getScore(True)

    def __eq__(self, other):
        if not other:
            return False
        if self.__class__ != other.__class__:
            return False
        return self.address == other.address

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return "Connection: {0} local: {1} token: {2} sources: {3} state: {4} score: {5}".format(
            self.address,
            self.isLocal,
            util.hideToken(self.token),
            repr(self.sources),
            self.state,
            self.getScore()
        )

    def __repr__(self):
        return self.__str__()

    def ipInLocalNet(self, ip):
        key = ":" in ip and 6 or 4
        addr = key == 4 and IPv4Address(ip) or IPv6Address(ip)
        for network in LOCAL_NETWORKS[key]:
            if addr in network:
                return network
        return False

    def checkNativeResolve(self):
        pUrl = urlparse(self.address)
        hostname = pUrl.hostname
        if hostname.endswith("plex.direct") and hostname not in util.SKIP_HOST_CHECK:
            try:
                ips = util.resolve(hostname, use_orig=True)
                self.pdHostnameResolved = ips[0] != "0.0.0.0"
                util.DEBUG_LOG("Natively resolved hostname: {} to {}", hostname, ips)
            except Exception as e:
                util.DEBUG_LOG("Couldn't resolve hostname: {}, {}", hostname, e)
                self.pdHostnameResolved = False

    def checkLocal(self):
        pUrl = urlparse(self.address)
        hostname = pUrl.hostname

        if hostname.endswith("plex.direct"):
            util.DEBUG_LOG("Using shortcut for hostname IP detection due to plex.direct host: {}", hostname)
            ips = [util.parsePlexDirectHost(hostname)]

        else:
            try:
                ips = resolve(hostname)
            except (socket.gaierror, ICMPLibError):
                util.DEBUG_LOG("Couldn't resolve hostname: {}", hostname)
                return False

        for ip in ips:
            local_and_alive = False
            if ip in LOCALS_SEEN:
                local, network, host = LOCALS_SEEN[ip]
                if local:
                    util.DEBUG_LOG("We've already verified {} ({}) as local, skipping", hostname, ip)
                else:
                    util.DEBUG_LOG("We've already verified {} ({}) as remote, skipping", hostname, ip)
                    continue
                local_and_alive = True

            else:
                network = self.ipInLocalNet(ip)
                if not network:
                    LOCALS_SEEN[ip] = (False, network, None)
                    continue

                try:
                    host = ping(ip, count=1, interval=1, timeout=util.LAN_REACHABILITY_TIMEOUT, privileged=False)
                except:
                    util.DEBUG_LOG("IP {} didn't answer in time ({}s)", ip, util.LAN_REACHABILITY_TIMEOUT)
                    LOCALS_SEEN[ip] = (False, network, None)
                    continue

            if local_and_alive or host.is_alive:
                self.isLocal = True
                self.localVerified = True
                if not local_and_alive:
                    util.LOG("Found IP {0} in local network ({1}) when checking {2}. Ping: {3}ms (max: {4}s)"
                             .format(ip, network, self.address, host.max_rtt, util.LAN_REACHABILITY_TIMEOUT))
                    LOCALS_SEEN[ip] = (True, network, host)

                if self.isSecure:
                    # alert the server that we've found the IP locally, so we can test non-secure connectivity
                    self.isSecureButLocal = (ip, pUrl.port)
                return True

        return False

    def merge(self, other):
        # plex.tv trumps all, otherwise assume newer is better
        # ROKU: if (other.sources and self.SOURCE_MYPLEX) <> 0 then
        if other.sources == self.SOURCE_MYPLEX:
            self.token = other.token
        else:
            self.token = self.token or other.token

        self.address = other.address
        self.sources = self.SOURCE_BY_VAL[self.sources | other.sources]
        self.isLocal = self.isLocal | other.isLocal
        self.isSecure = other.isSecure
        self.isFallback = self.isFallback or other.isFallback
        self.refreshed = True

        self.getScore(True)

    def testReachability(self, server, allowFallback=False):
        # Check if we will allow the connection test. If this is a fallback connection,
        # then we will defer it until we "allowFallback" (test insecure connections
        # after secure tests have completed and failed). Insecure connections will be
        # tested if the policy "always" allows them, or if set to "same_network" and
        # the current connection is local and server has (publicAddressMatches=1).
        insecurePolicy = util.INTERFACE.getPreference("allow_insecure")
        insecureAllowed = insecurePolicy == "always" or (insecurePolicy == "same_network" and
                                                         server.sameNetwork and self.isLocal)

        allowConnectionTest = not self.isFallback or (util.LOCAL_OVER_SECURE and insecureAllowed)
        if not allowConnectionTest:
            if insecureAllowed:
                allowConnectionTest = allowFallback
                server.hasFallback = not allowConnectionTest
                util.LOG(
                    '{0} for {1}'.format(
                        allowConnectionTest and "Continuing with insecure connection testing" or "Insecure connection testing is deferred", server
                    )
                )
            else:
                util.LOG("Insecure connections not allowed. Ignore insecure connection test for {0}", server)
                self.state = self.STATE_INSECURE
                callable = callback.Callable(server.onReachabilityResult, [self], random.randint(0, 256))
                callable.deferCall()
                return True

        if allowConnectionTest:
            if not self.isSecure and not util.LOCAL_OVER_SECURE and (
                not allowFallback and
                server.hasSecureConnections() or
                server.activeConnection and
                server.activeConnection.state != self.STATE_REACHABLE and
                server.activeConnection.isSecure
            ):
                util.DEBUG_LOG("Invalid insecure connection test in progress")
            self.request = http.HttpRequest(self.buildUrl(server, "/"))
            context = self.request.createRequestContext("reachability", callback.Callable(self.onReachabilityResponse),
                                                        timeout=util.CONN_CHECK_TIMEOUT)
            context.server = server
            util.addPlexHeaders(self.request, server.getToken())
            self.hasPendingRequest = util.APP.startRequest(self.request, context)
            util.DEBUG_LOG("Testing insecure connection for: {0}", server)
            return True

        return False

    def cancelReachability(self):
        if self.request:
            self.request.ignoreResponse = True
            self.request.cancel()

    def onReachabilityResponse(self, request, response, context):
        self.hasPendingRequest = False
        # It's possible we may have a result pending before we were able
        # to cancel it, so we'll just ignore it.

        # if request.ignoreResponse:
        #     return

        if response.isSuccess():
            data = response.getBodyXml()
            if data is not None and context.server.collectDataFromRoot(data):
                self.state = self.STATE_REACHABLE
            else:
                # This is unexpected, but treat it as unreachable
                util.ERROR_LOG("Unable to parse root response from {0}".format(context.server))
                self.state = self.STATE_UNREACHABLE
        elif response.getStatus() == 401:
            self.state = self.STATE_UNAUTHORIZED
        else:
            self.state = self.STATE_UNREACHABLE

        self.getScore(True)

        context.server.onReachabilityResult(self)

    def buildUrl(self, server, path, includeToken=False):
        if '://' in path:
            url = path
        else:
            url = self.address + path

        if includeToken:
            # If we have a token, use it. Otherwise see if any other connections
            # for this server have one. That will let us use a plex.tv token for
            # something like a manually configured connection.

            token = self.token or server.getToken()

            if token:
                url = http.addUrlParam(url, "X-Plex-Token=" + token)

        return url

    def simpleBuildUrl(self, server, path):
        token = (self.token or server.getToken())
        param = ''
        if token:
            param = '&X-Plex-Token={0}'.format(token)

        return '{0}{1}{2}'.format(self.address, path, param)

    def getScore(self, recalc=False):
        if recalc:
            self.score = 0
            if self.state == self.STATE_REACHABLE:
                self.score += self.SCORE_REACHABLE
            if self.isSecure:
                self.score += self.SCORE_SECURE
            if self.isLocal:
                self.score += self.SCORE_LOCAL + (not self.isSecure and util.LOCAL_OVER_SECURE and 2 or 0)

        return self.score
