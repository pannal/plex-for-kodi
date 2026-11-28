# coding=utf-8
"""
lib/advancedsettings.py and lib/plex_hosts.py - PM4K's edits to Kodi's
advancedsettings.xml.

PM4K rewrites a file Kodi owns, so the tests care mostly about *not* eating
unrelated sections: a user's <network> block has to survive a <hosts> or
<cache> update.
"""

from __future__ import absolute_import, unicode_literals

from io import open

import os

from kodienv import ENV

from lib.advancedsettings import AdvancedSettings, adv
from lib.plex_hosts import PlexHostsManager

from .base import KodiTestCase

ADV_PATH = "advancedsettings.xml"


def write_adv(content):
    """Write advancedsettings.xml and refresh the module singleton from it.

    `adv` reads the file once, at addon start, and every consumer
    (lib.cache, lib.plex_hosts) works off that one cached copy - so a test
    that writes the file has to re-load it explicitly, exactly like the addon
    would only see the new content on its next run.
    """
    path = os.path.join(ENV.profile_root, ADV_PATH)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(content)
    reload_adv()
    return path


def reload_adv():
    adv._data = None
    adv.load()


def read_adv():
    with open(os.path.join(ENV.profile_root, ADV_PATH), "r", encoding="utf-8") as fp:
        return fp.read()


def hosts_manager():
    mgr = PlexHostsManager.__new__(PlexHostsManager)
    mgr.load()
    return mgr


class AdvSingletonMixin(object):
    """Keeps the shared `adv` singleton and the file on disk in step."""

    def setUp(self):
        KodiTestCase.setUp(self)
        self._adv_path = os.path.join(ENV.profile_root, ADV_PATH)
        if os.path.exists(self._adv_path):
            os.remove(self._adv_path)
        reload_adv()

    def tearDown(self):
        if os.path.exists(self._adv_path):
            os.remove(self._adv_path)
        reload_adv()
        KodiTestCase.tearDown(self)


class AdvancedSettingsTest(AdvSingletonMixin, KodiTestCase):
    def test_no_file_means_no_data(self):
        adv = AdvancedSettings()
        self.assertIsNone(adv.getData())
        self.assertFalse(adv)

    def test_an_existing_file_is_read(self):
        write_adv("<advancedsettings>\n</advancedsettings>")
        adv = AdvancedSettings()
        self.assertIn("<advancedsettings>", adv.getData())
        self.assertTrue(adv)

    def test_write_persists_and_updates_the_cached_copy(self):
        adv = AdvancedSettings()
        adv.write("<advancedsettings><network/></advancedsettings>")
        self.assertIn("<network/>", read_adv())
        self.assertIn("<network/>", adv.getData())

    def test_write_without_data_is_a_no_op(self):
        adv = AdvancedSettings()
        adv.write()
        self.assertFalse(os.path.exists(os.path.join(ENV.profile_root, ADV_PATH)))


class PlexHostsLoadTest(AdvSingletonMixin, KodiTestCase):
    def test_no_advancedsettings_means_no_hosts(self):
        mgr = hosts_manager()
        self.assertEqual({}, mgr.getHosts())
        self.assertFalse(mgr)
        self.assertEqual(0, len(mgr))
        self.assertFalse(mgr.hadHosts)

    def test_existing_hosts_are_parsed(self):
        write_adv("<advancedsettings>\n"
                  "  <hosts>\n"
                  '    <entry name="a.plex.direct">10.0.0.5</entry>\n'
                  '    <entry name="b.plex.direct">10.0.0.6</entry>\n'
                  "  </hosts>\n"
                  "</advancedsettings>")
        mgr = hosts_manager()
        self.assertEqual({"a.plex.direct": "10.0.0.5", "b.plex.direct": "10.0.0.6"},
                         mgr.getHosts())
        self.assertTrue(mgr.hadHosts)
        self.assertEqual(2, len(mgr))
        self.assertFalse(mgr.differs, "a freshly loaded manager has no pending changes")

    def test_differs_and_diff_track_additions(self):
        write_adv("<advancedsettings>\n  <hosts>\n"
                  '    <entry name="a.plex.direct">10.0.0.5</entry>\n'
                  "  </hosts>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr._hosts["c.plex.direct"] = "10.0.0.7"
        self.assertTrue(mgr.differs)
        self.assertEqual({"c.plex.direct"}, mgr.diff)

    def test_reset_discards_pending_changes(self):
        write_adv("<advancedsettings>\n  <hosts>\n"
                  '    <entry name="a.plex.direct">10.0.0.5</entry>\n'
                  "  </hosts>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr._hosts["c.plex.direct"] = "10.0.0.7"
        mgr.resetHosts()
        self.assertFalse(mgr.differs)
        self.assertEqual({"a.plex.direct": "10.0.0.5"}, mgr.getHosts())


class PlexHostsWriteTest(AdvSingletonMixin, KodiTestCase):
    def test_writing_into_a_file_that_had_no_hosts_keeps_the_rest(self):
        write_adv("<advancedsettings>\n"
                  "  <network><curlclienttimeout>30</curlclienttimeout></network>\n"
                  "</advancedsettings>")
        mgr = hosts_manager()
        mgr.write({"a.plex.direct": "10.0.0.5"})

        data = read_adv()
        self.assertIn("<curlclienttimeout>30</curlclienttimeout>", data,
                      "an unrelated user section must survive")
        self.assertIn('<entry name="a.plex.direct">10.0.0.5</entry>', data)
        self.assertIn("managed by PM4K", data)
        self.assertEqual(1, data.count("<advancedsettings>"))
        self.assertEqual(1, data.count("</advancedsettings>"))

    def test_writing_replaces_an_existing_hosts_block_rather_than_appending(self):
        write_adv("<advancedsettings>\n  <hosts>\n"
                  '    <entry name="old.plex.direct">10.0.0.1</entry>\n'
                  "  </hosts>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr.write({"new.plex.direct": "10.0.0.2"})

        data = read_adv()
        self.assertNotIn("old.plex.direct", data)
        self.assertIn("new.plex.direct", data)
        self.assertEqual(1, data.count("<hosts>"))

    def test_write_marks_the_state_as_clean(self):
        write_adv("<advancedsettings>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr.write({"a.plex.direct": "10.0.0.5"})
        self.assertFalse(mgr.differs)
        self.assertTrue(mgr.hadHosts)

    def test_writing_nothing_is_a_no_op(self):
        write_adv("<advancedsettings>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr.write({})
        self.assertNotIn("<hosts>", read_adv())

    def test_a_written_block_round_trips_through_load(self):
        write_adv("<advancedsettings>\n</advancedsettings>")
        mgr = hosts_manager()
        mgr.write({"a.plex.direct": "10.0.0.5", "b.plex.direct": "10.0.0.6"})
        self.assertEqual({"a.plex.direct": "10.0.0.5", "b.plex.direct": "10.0.0.6"},
                         hosts_manager().getHosts())


class NewHostsTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = PlexHostsManager.__new__(PlexHostsManager)
        self.mgr._hosts = {}
        self.mgr._orig_hosts = {}

    def test_a_plex_direct_uri_is_decoded_into_a_host_and_ip(self):
        self.mgr.newHosts(["https://10-0-0-5.abc123.plex.direct:32400"])
        self.assertEqual({"10-0-0-5.abc123.plex.direct": "10.0.0.5"}, self.mgr.getHosts())

    def test_an_already_known_host_is_not_re_added(self):
        self.mgr._hosts = {"10-0-0-5.abc123.plex.direct": "already"}
        self.mgr.newHosts(["https://10-0-0-5.abc123.plex.direct:32400"])
        self.assertEqual("already", self.mgr.getHosts()["10-0-0-5.abc123.plex.direct"])

    def test_docker_bridge_addresses_are_skipped(self):
        """
        172.17.0.0/16 is Docker's default bridge. A PMS advertising it is
        almost always unreachable from the Kodi box, and mapping it hijacks the
        hostname, so it is ignored unless explicitly force-mapped.
        """
        from lib import util
        orig = util.addonSettings.ignoreDockerV4
        try:
            util.addonSettings.ignoreDockerV4 = True
            self.mgr.newHosts(["https://172-17-0-2.abc123.plex.direct:32400"])
            self.assertEqual({}, self.mgr.getHosts())
        finally:
            util.addonSettings.ignoreDockerV4 = orig

    def test_a_force_mapped_docker_address_is_kept(self):
        from lib import util
        orig = util.addonSettings.ignoreDockerV4
        address = "https://172-17-0-2.abc123.plex.direct:32400"
        try:
            util.addonSettings.ignoreDockerV4 = True
            self.mgr.newHosts([address], force_mapping=[address])
            self.assertEqual({"172-17-0-2.abc123.plex.direct": "172.17.0.2"},
                             self.mgr.getHosts())
        finally:
            util.addonSettings.ignoreDockerV4 = orig

    def test_docker_filtering_can_be_switched_off_entirely(self):
        from lib import util
        orig = util.addonSettings.ignoreDockerV4
        try:
            util.addonSettings.ignoreDockerV4 = False
            self.mgr.newHosts(["https://172-17-0-2.abc123.plex.direct:32400"])
            self.assertEqual({"172-17-0-2.abc123.plex.direct": "172.17.0.2"},
                             self.mgr.getHosts())
        finally:
            util.addonSettings.ignoreDockerV4 = orig

    def test_ordinary_private_addresses_are_not_treated_as_docker(self):
        from lib import util
        orig = util.addonSettings.ignoreDockerV4
        try:
            util.addonSettings.ignoreDockerV4 = True
            self.mgr.newHosts(["https://192-168-1-50.abc123.plex.direct:32400"])
            self.assertEqual({"192-168-1-50.abc123.plex.direct": "192.168.1.50"},
                             self.mgr.getHosts())
        finally:
            util.addonSettings.ignoreDockerV4 = orig
