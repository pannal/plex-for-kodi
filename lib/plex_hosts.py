# coding=utf-8
import re
try:
    from urllib.parse import urlparse
except ImportError:
    from requests.compat import urlparse

import plexnet.http

from six import text_type

from lib import util
from lib.advancedsettings import adv

from plexnet.util import parsePlexDirectHost
from plexnet.plexconnection import DOCKER_NETWORK, IPv4Address

HOSTS_RE = re.compile(r'\s*<hosts>.*</hosts>', re.S | re.I)
HOST_RE = re.compile(r'<entry name="(?P<hostname>.+)">(?P<ip>.+)</entry>')


class PlexHostsManager(object):
    _hosts = None
    _orig_hosts = None

    HOSTS_TPL = """\
  <hosts><!-- managed by PM4K -->
{}
  </hosts>"""
    ENTRY_TPL = '    <entry name="{}">{}</entry>'

    def __init__(self):
        self.load()

    def __bool__(self):
        return bool(self._hosts)

    def __len__(self):
        return self and len(self._hosts) or 0

    def getHosts(self):
        return self._hosts or {}

    @property
    def hadHosts(self):
        return bool(self._orig_hosts)

    def getOrigHosts(self):
        return self._orig_hosts or {}

    def newHosts(self, hosts, source="stored", force_mapping=None):
        """
        hosts should be a list of plex.direct connection uri's
        """
        force_mapping = force_mapping or []
        util.DEBUG_LOG("PlexHostsManager: Force Mapping: {}", force_mapping)
        for address in hosts:
            parsed = urlparse(address)
            ip = parsePlexDirectHost(parsed.hostname)
            # ignore docker V4 hosts
            if (util.addonSettings.ignoreDockerV4 and ":" not in ip and IPv4Address(text_type(ip)) in DOCKER_NETWORK
                    and (not force_mapping or address not in force_mapping)):
                util.DEBUG_LOG("Ignoring plex.direct local {} Docker IPv4 address: {}", source, parsed.hostname)
                continue

            if parsed.hostname not in self._hosts:
                self._hosts[parsed.hostname] = plexnet.http.RESOLVED_PD_HOSTS.get(parsed.hostname, ip)
                util.LOG("Found new unmapped {} plex.direct host: {}, IP: {}", source, parsed.hostname, ip)

    def resetHosts(self):
        self._hosts = self._orig_hosts.copy()

    @property
    def differs(self):
        return self._hosts != self._orig_hosts

    @property
    def diff(self):
        return set(self._hosts) - set(self._orig_hosts)

    def load(self):
        data = adv.getData()
        self._hosts = {}
        self._orig_hosts = {}
        if not data:
            return

        hosts_match = HOSTS_RE.search(data)
        if hosts_match:
            hosts_xml = hosts_match.group(0)

            hosts = HOST_RE.findall(hosts_xml)
            if hosts:
                self._hosts = dict(hosts)
                self._orig_hosts = dict(hosts)
                util.DEBUG_LOG("Found {} hosts in advancedsettings.xml", lambda: len(self._hosts))

    def write(self, hosts=None):
        self._hosts = hosts or self._hosts
        if not self._hosts:
            return
        data = adv.getData()
        cd = "<advancedsettings>\n</advancedsettings>"
        if data:
            hosts_match = HOSTS_RE.search(data)
            if hosts_match:
                hosts_xml = hosts_match.group(0)
                cd = data.replace(hosts_xml, "")
            else:
                cd = data

        finalxml = "{}\n</advancedsettings>".format(
            cd.replace("</advancedsettings>", self.HOSTS_TPL.format("\n".join(self.ENTRY_TPL.format(hostname, ip)
                                                                              for hostname, ip in self._hosts.items())))
        )

        adv.write(finalxml)
        self._orig_hosts = dict(self._hosts)


pdm = PlexHostsManager()
