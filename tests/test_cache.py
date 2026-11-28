# coding=utf-8
"""
lib/cache.py and lib/data_cache.py - Kodi buffer sizing and the on-disk JSON cache.

The cache manager has two completely different backends depending on the Kodi
build (JSON-RPC on 21+, advancedsettings.xml rewriting before that), and the
data cache silently migrates and prunes itself. Both are easy to break without
noticing.
"""

from __future__ import absolute_import, unicode_literals

from io import open

import json
import os
import time

from kodienv import ENV

from lib import util
from lib.cache import KodiCacheManager
from lib.data_cache import DataCacheManager

from .base import KodiTestCase
from . import REPO_ROOT

ADV_PATH = "advancedsettings.xml"


def cache_manager(build_number=None):
    """
    A manager built without touching the module singleton.

    KODI_BUILD_NUMBER decides the whole strategy, and it is read from
    lib.util at construction time, so it is patched around the call.
    """
    from lib import cache as cache_module
    orig = cache_module.KODI_BUILD_NUMBER
    try:
        if build_number is not None:
            cache_module.KODI_BUILD_NUMBER = build_number
        return KodiCacheManager()
    finally:
        cache_module.KODI_BUILD_NUMBER = orig


class ModernApiTest(KodiTestCase):
    """Kodi 21.0-BETA2 (build 2090821) and later: settings live in JSON-RPC."""

    def test_values_come_from_kodi_settings(self):
        ENV.kodi_settings["filecache.memorysize"] = 64
        ENV.kodi_settings["filecache.readfactor"] = 400
        mgr = cache_manager(2090821)
        self.assertTrue(mgr.useModernAPI)
        self.assertEqual(64, mgr.memorySize)
        self.assertEqual(4, mgr.readFactor)

    def test_a_whole_read_factor_is_kept_as_an_int(self):
        ENV.kodi_settings["filecache.readfactor"] = 400
        self.assertIsInstance(cache_manager(2090821).readFactor, int)

    def test_a_fractional_read_factor_stays_a_float(self):
        ENV.kodi_settings["filecache.readfactor"] = 250
        mgr = cache_manager(2090821)
        self.assertEqual(2.5, mgr.readFactor)
        self.assertIsInstance(mgr.readFactor, float)

    def test_write_goes_back_through_json_rpc(self):
        mgr = cache_manager(2090821)
        mgr.write(memorySize=128, readFactor=2.5)
        self.assertEqual(128, ENV.kodi_settings["filecache.memorysize"])
        self.assertEqual(250, ENV.kodi_settings["filecache.readfactor"],
                         "read factor is stored as a percentage")

    def test_write_does_not_touch_advancedsettings(self):
        mgr = cache_manager(2090821)
        mgr.write(memorySize=128)
        self.assertFalse(os.path.exists(os.path.join(ENV.profile_root, ADV_PATH)))

    def test_the_recommended_range_string_is_the_modern_one(self):
        mgr = cache_manager(2090821)
        self.assertEqual("1.5-4", mgr.recRFRange)
        self.assertEqual(7, mgr.defRFSM)

    def test_newer_builds_take_the_range_from_the_translation(self):
        mgr = cache_manager(2090830)
        self.assertEqual(util.ADDON.getLocalizedString(32976), mgr.recRFRange)


class LegacyApiTest(KodiTestCase):
    """Before build 2090821 the values are parsed out of advancedsettings.xml."""

    def setUp(self):
        KodiTestCase.setUp(self)
        from lib.advancedsettings import adv
        self.adv = adv
        self.path = os.path.join(ENV.profile_root, ADV_PATH)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.reload()

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        self.reload()
        KodiTestCase.tearDown(self)

    def reload(self):
        self.adv._data = None
        self.adv.load()

    def write_adv(self, content):
        with open(self.path, "w", encoding="utf-8") as fp:
            fp.write(content)
        self.reload()

    def read_adv(self):
        with open(self.path, "r", encoding="utf-8") as fp:
            return fp.read()

    def test_defaults_without_a_file(self):
        mgr = cache_manager(2000000)
        self.assertFalse(mgr.useModernAPI)
        self.assertEqual(20, mgr.memorySize)
        self.assertEqual(4, mgr.readFactor)

    def test_an_existing_cache_block_is_parsed(self):
        self.write_adv("<advancedsettings>\n"
                       "  <cache>\n"
                       "    <memorysize>104857600</memorysize>\n"
                       "    <readfactor>10</readfactor>\n"
                       "  </cache>\n"
                       "</advancedsettings>")
        mgr = cache_manager(2000000)
        self.assertEqual(100, mgr.memorySize, "memorysize is bytes on disk, MB in memory")
        self.assertEqual(10, mgr.readFactor)

    def test_a_malformed_cache_block_keeps_the_defaults(self):
        self.write_adv("<advancedsettings>\n"
                       "  <cache>\n"
                       "    <memorysize>lots</memorysize>\n"
                       "  </cache>\n"
                       "</advancedsettings>")
        mgr = cache_manager(2000000)
        self.assertEqual(20, mgr.memorySize)

    def test_write_rewrites_the_cache_block_and_keeps_the_rest(self):
        self.write_adv("<advancedsettings>\n"
                       "  <network><curlclienttimeout>30</curlclienttimeout></network>\n"
                       "  <cache>\n    <memorysize>20971520</memorysize>\n"
                       "    <readfactor>4</readfactor>\n  </cache>\n"
                       "</advancedsettings>")
        mgr = cache_manager(2000000)
        mgr.write(memorySize=100, readFactor=8)

        data = self.read_adv()
        self.assertIn("<curlclienttimeout>30</curlclienttimeout>", data)
        self.assertIn("104857600", data, "MB is converted back to bytes")
        self.assertIn("<readfactor>8</readfactor>", data)
        self.assertEqual(1, data.count("<cache>"))

    def test_the_shipped_template_is_where_the_manager_expects_it(self):
        path = os.path.join(REPO_ROOT, "pm4k_cache_template.xml")
        self.assertTrue(os.path.exists(path), path)

    def test_the_shipped_template_has_both_placeholders(self):
        with open(os.path.join(REPO_ROOT, "pm4k_cache_template.xml"), "r",
                  encoding="utf-8") as fp:
            template = fp.read()
        self.assertIn("{memorysize}", template)
        self.assertIn("{readfactor}", template)

    def test_a_kodi_repository_install_never_writes_advancedsettings(self):
        """
        The Kodi repo build is not allowed to edit advancedsettings.xml, so on
        a legacy Kodi it has to leave the file alone entirely.
        """
        from lib import cache as cache_module
        orig = cache_module.FROM_KODI_REPOSITORY
        try:
            cache_module.FROM_KODI_REPOSITORY = True
            mgr = cache_manager(2000000)
            mgr.write(memorySize=100)
            self.assertFalse(os.path.exists(self.path))
        finally:
            cache_module.FROM_KODI_REPOSITORY = orig


class CacheOptionsTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = cache_manager(2090821)

    def test_clamp16_rounds_down_to_a_multiple_of_16(self):
        self.assertEqual(16, self.mgr.clamp16(31))
        self.assertEqual(32, self.mgr.clamp16(32))
        self.assertEqual(0, self.mgr.clamp16(15))

    def test_free_memory_is_read_from_the_infolabel(self):
        ENV.infolabels["System.Memory(free)"] = "1500MB"
        self.assertEqual(1500.0, self.mgr.free)

    def test_the_recommended_max_is_a_fraction_of_free_memory_capped_at_2g(self):
        ENV.infolabels["System.Memory(free)"] = "1000MB"
        self.assertEqual(int(1000 * self.mgr.safeFactor), self.mgr.recMax)

        ENV.infolabels["System.Memory(free)"] = "100000MB"
        self.assertEqual(2048, self.mgr.recMax)

    def test_viable_options_are_sorted_unique_and_bounded(self):
        ENV.infolabels["System.Memory(free)"] = "2000MB"
        options = self.mgr.viableOptions
        self.assertEqual(sorted(set(options)), options)
        self.assertIn(self.mgr.memorySize, options)
        self.assertIn(self.mgr.recMax, options)
        self.assertLessEqual(max(options), 2048)

    def test_read_factor_options_include_the_current_value(self):
        self.mgr.readFactor = 6.5
        self.assertIn(6.5, self.mgr.readFactorOpts)
        self.assertEqual(sorted(set(self.mgr.readFactorOpts)), self.mgr.readFactorOpts)

    def test_adaptive_read_factor_is_offered_on_newer_builds(self):
        from lib import cache as cache_module
        orig = cache_module.KODI_BUILD_NUMBER
        try:
            cache_module.KODI_BUILD_NUMBER = 2090830
            self.mgr.readFactor = 4
            self.assertEqual(0, self.mgr.readFactorOpts[0])
        finally:
            cache_module.KODI_BUILD_NUMBER = orig


def data_cache_manager():
    """A DataCacheManager with its class-level caches isolated per test."""
    mgr = DataCacheManager.__new__(DataCacheManager)
    mgr._currentServerUUID = "server01"
    mgr.DATA_CACHES = {"general": {"updated": time.time(),
                                   "version": DataCacheManager.DATA_CACHES_VERSION},
                       "cache": {}}
    mgr.DC_LAST_UPDATE = None
    return mgr


class DataCacheTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = data_cache_manager()
        self.path = os.path.join(ENV.addon_data_dir, "data_cache_test.json")
        self.mgr.DC_PATH = self.path

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        KodiTestCase.tearDown(self)

    def test_set_then_get(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.assertEqual({"a": 1}, self.mgr.getCacheData("hubs", "movies"))

    def test_an_unknown_identifier_yields_nothing(self):
        self.assertIsNone(self.mgr.getCacheData("hubs", "absent"))

    def test_entries_are_scoped_to_the_server(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.mgr._currentServerUUID = "server02"
        self.assertIsNone(self.mgr.getCacheData("hubs", "movies"))

    def test_entries_are_scoped_to_the_context(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.assertIsNone(self.mgr.getCacheData("other", "movies"))

    def test_writing_bumps_the_general_updated_stamp(self):
        before = self.mgr.DATA_CACHES["general"]["updated"]
        time.sleep(0.01)
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.assertGreater(self.mgr.DATA_CACHES["general"]["updated"], before)

    def test_reading_refreshes_last_access(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        entry = self.mgr.DATA_CACHES["cache"]["server01"]["hubs"]["movies"]
        entry["last_access"] = 0
        self.mgr.getCacheData("hubs", "movies")
        self.assertGreater(entry["last_access"], 0)

    def test_data_older_than_the_purge_window_is_dropped_on_read(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        entry = self.mgr.DATA_CACHES["cache"]["server01"]["hubs"]["movies"]
        entry["updated"] = time.time() - (self.mgr.DC_LRUP_TIMEOUT + 1) * 3600 * 24

        self.assertIsNone(self.mgr.getCacheData("hubs", "movies"))
        self.assertNotIn("movies", self.mgr.DATA_CACHES["cache"]["server01"]["hubs"])

    def test_cleanup_evicts_entries_not_accessed_recently(self):
        self.mgr.setCacheData("hubs", "stale", {"a": 1})
        self.mgr.setCacheData("hubs", "fresh", {"b": 2})
        stale = self.mgr.DATA_CACHES["cache"]["server01"]["hubs"]["stale"]
        stale["last_access"] = time.time() - (self.mgr.DC_LRU_TIMEOUT + 1) * 3600 * 24

        self.mgr.dataCacheCleanup()
        remaining = self.mgr.DATA_CACHES["cache"]["server01"]["hubs"]
        self.assertNotIn("stale", remaining)
        self.assertIn("fresh", remaining)

    def test_store_writes_json_to_disk(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.mgr.storeDataCache()
        with open(self.path, "r", encoding="utf-8") as fp:
            stored = json.load(fp)
        self.assertEqual({"a": 1},
                         stored["cache"]["server01"]["hubs"]["movies"]["data"])

    def test_store_is_skipped_when_nothing_changed_since_the_last_write(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.mgr.DC_LAST_UPDATE = self.mgr.DATA_CACHES["general"]["updated"]
        self.mgr.storeDataCache()
        self.assertFalse(os.path.exists(self.path))

    def test_a_stored_cache_round_trips(self):
        self.mgr.setCacheData("hubs", "movies", {"a": 1})
        self.mgr.storeDataCache()

        with open(self.path, "r", encoding="utf-8") as fp:
            reloaded = json.load(fp)
        other = data_cache_manager()
        other.DATA_CACHES = reloaded
        self.assertEqual({"a": 1}, other.getCacheData("hubs", "movies"))


class DataCacheServerUUIDTest(KodiTestCase):
    class FakeServer(object):
        def __init__(self, uuid="0123456789abcdef"):
            self.uuid = uuid

    class FakeServerManager(object):
        def __init__(self, selected=None):
            self.selectedServer = selected

    def setUp(self):
        KodiTestCase.setUp(self)
        from plexnet import plexapp
        self.plexapp = plexapp
        self._orig_sm = plexapp.SERVERMANAGER

    def tearDown(self):
        self.plexapp.SERVERMANAGER = self._orig_sm
        KodiTestCase.tearDown(self)

    def test_the_uuid_is_truncated_to_its_last_eight_characters(self):
        mgr = data_cache_manager()
        mgr.setServerUUID(self.FakeServer())
        self.assertEqual("89abcdef", mgr._currentServerUUID)

    def test_it_falls_back_to_the_selected_server(self):
        self.plexapp.SERVERMANAGER = self.FakeServerManager(self.FakeServer("aaaabbbbcccc"))
        mgr = data_cache_manager()
        mgr.setServerUUID()
        self.assertEqual("bbbbcccc", mgr._currentServerUUID)

    def test_no_server_and_none_selected_leaves_the_uuid_alone(self):
        self.plexapp.SERVERMANAGER = self.FakeServerManager(None)
        mgr = data_cache_manager()
        mgr._currentServerUUID = "keepme"
        mgr.setServerUUID(None)
        self.assertEqual("keepme", mgr._currentServerUUID)
