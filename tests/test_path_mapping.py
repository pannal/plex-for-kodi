# coding=utf-8
"""
lib/path_mapping.py - rewriting PMS-side paths to Kodi-side ones.

Two behaviours here are easy to regress and expensive when they go wrong:
longest-prefix wins (a short mapping must never shadow a more specific one),
and the notify-once bookkeeping that stops a multi-part title from producing a
burst of identical 5-second popups.
"""

from __future__ import absolute_import

import json
import os

from kodienv import ENV

from lib.path_mapping import PathMappingManager, norm_sep

from .base import KodiTestCase


class FakeServer(object):
    def __init__(self, name="Tower"):
        self.name = name


def manager(mapping=None):
    """A manager with class-level state isolated from the module singleton."""
    mgr = PathMappingManager.__new__(PathMappingManager)
    mgr.PATH_MAP = mapping if mapping is not None else {}
    mgr.BROKEN_MAP = {}
    mgr.NOTIFIED = set()
    mgr.mapfile = os.path.join(ENV.addon_data_dir, "path_mapping.json")
    return mgr


class NormSepTest(KodiTestCase):
    def test_a_backslash_anywhere_means_windows(self):
        self.assertEqual("\\", norm_sep(r"D:\media"))
        self.assertEqual("/", norm_sep("/mnt/media"))
        self.assertEqual("/", norm_sep(""))


class MappedPathTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        ENV.settings["path_mapping"] = "true"
        self.server = FakeServer()

    def test_no_mapping_configured(self):
        mgr = manager({})
        self.assertEqual((None, None, None),
                         mgr.getMappedPathFor("/data/Movies/a.mkv", self.server))

    def test_simple_mapping(self):
        mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})
        self.assertEqual(("/mnt/nas/", "/data/"),
                         mgr.getMappedPathFor("/data/Movies/a.mkv", self.server)[:2])

    def test_the_longest_matching_pms_prefix_wins(self):
        mgr = manager({"Tower": {
            "/mnt/all/": "/data/",
            "/mnt/movies/": "/data/Movies/",
        }})
        map_path, pms_path, _ = mgr.getMappedPathFor("/data/Movies/a.mkv", self.server)
        self.assertEqual("/mnt/movies/", map_path)
        self.assertEqual("/data/Movies/", pms_path)

    def test_a_non_matching_path_is_left_alone(self):
        mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})
        self.assertEqual((None, None, None),
                         mgr.getMappedPathFor("/elsewhere/a.mkv", self.server))

    def test_mappings_are_per_server(self):
        mgr = manager({"Other": {"/mnt/nas/": "/data/"}})
        self.assertEqual((None, None, None),
                         mgr.getMappedPathFor("/data/a.mkv", self.server))

    def test_return_rep_rewrites_the_whole_path(self):
        mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})
        url, pms_path, sep = mgr.getMappedPathFor("/data/Movies/a.mkv", self.server,
                                                  return_rep=True)
        self.assertEqual("/mnt/nas/Movies/a.mkv", url)
        self.assertEqual("/data/", pms_path)
        self.assertEqual("/", sep)

    def test_return_rep_normalises_separators_to_the_kodi_side(self):
        """A Linux PMS mapped onto a Windows Kodi has to flip the slashes."""
        mgr = manager({"Tower": {"D:\\media\\": "/data/"}})
        url, _, sep = mgr.getMappedPathFor("/data/Movies/a.mkv", self.server, return_rep=True)
        self.assertEqual("\\", sep)
        self.assertEqual("D:\\media\\Movies\\a.mkv", url)

    def test_windows_pms_onto_a_linux_kodi(self):
        mgr = manager({"Tower": {"/mnt/nas/": "D:\\media\\"}})
        url, _, sep = mgr.getMappedPathFor("D:\\media\\Movies\\a.mkv", self.server,
                                           return_rep=True)
        self.assertEqual("/", sep)
        self.assertEqual("/mnt/nas/Movies/a.mkv", url)

    def test_the_setting_switches_mapping_off_without_losing_the_map(self):
        mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})
        ENV.settings["path_mapping"] = "false"
        self.assertEqual((None, None, None),
                         mgr.getMappedPathFor("/data/a.mkv", self.server))
        self.assertTrue(mgr.PATH_MAP, "the map itself must survive the toggle")


class BrokenMappingTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})

    def test_state_changes_are_reported_only_on_transition(self):
        self.assertTrue(self.mgr.markMappingState("Tower", "/mnt/nas/", works=False))
        self.assertFalse(self.mgr.markMappingState("Tower", "/mnt/nas/", works=False))
        self.assertTrue(self.mgr.markMappingState("Tower", "/mnt/nas/", works=True))
        self.assertFalse(self.mgr.markMappingState("Tower", "/mnt/nas/", works=True))

    def test_a_fresh_working_mapping_is_not_a_change(self):
        self.assertFalse(self.mgr.markMappingState("Tower", "/mnt/nas/", works=True))

    def test_is_mapping_broken_tracks_the_state(self):
        self.assertFalse(self.mgr.isMappingBroken("Tower", "/mnt/nas/"))
        self.mgr.markMappingState("Tower", "/mnt/nas/", works=False)
        self.assertTrue(self.mgr.isMappingBroken("Tower", "/mnt/nas/"))
        self.mgr.markMappingState("Tower", "/mnt/nas/", works=True)
        self.assertFalse(self.mgr.isMappingBroken("Tower", "/mnt/nas/"))

    def test_recovery_rearms_notifications(self):
        self.mgr.markMappingState("Tower", "/mnt/nas/", works=False)
        self.assertTrue(self.mgr.claimNotification("Tower", "/mnt/nas/", "root"))
        self.assertFalse(self.mgr.claimNotification("Tower", "/mnt/nas/", "root"))
        # a remount clears the record so the next failure speaks up again
        self.mgr.markMappingState("Tower", "/mnt/nas/", works=True)
        self.assertTrue(self.mgr.claimNotification("Tower", "/mnt/nas/", "root"))

    def test_notification_kinds_are_claimed_independently(self):
        self.assertTrue(self.mgr.claimNotification("Tower", "/mnt/nas/", "root"))
        self.assertTrue(self.mgr.claimNotification("Tower", "/mnt/nas/", "file"))
        self.assertFalse(self.mgr.claimNotification("Tower", "/mnt/nas/", "file"))

    def test_notify_once_emits_a_single_popup_per_cause(self):
        self.mgr.notifyOnce("Tower", "/mnt/nas/", "root", "gone")
        self.mgr.notifyOnce("Tower", "/mnt/nas/", "root", "gone")
        notifications = [call for call in ENV.builtins if call.startswith("Notification(")]
        self.assertEqual(1, len(notifications), notifications)

    def test_verify_mapping_stats_the_root(self):
        present = self.mktemp()
        self.assertFalse(self.mgr.verifyMapping("Tower", present))
        self.assertFalse(self.mgr.isMappingBroken("Tower", present))

        self.assertTrue(self.mgr.verifyMapping("Tower", os.path.join(present, "gone")))
        self.assertTrue(self.mgr.isMappingBroken("Tower", os.path.join(present, "gone")))

    def test_a_root_without_a_trailing_separator_still_verifies(self):
        """
        path_mapping.json is hand written and every example in
        path_mapping.example.json omits the trailing separator
        ("smb://serverip/mountname"). xbmcvfs.exists() stats a separator-less
        path as a *file*, so probing the root verbatim reported a perfectly
        mounted share as unreachable - a permanent red dot that only cleared
        once playback happened to mark the mapping working.
        """
        root = self.mktemp().rstrip("/")
        self.assertFalse(self.mgr.verifyMapping("Tower", root))
        self.assertFalse(self.mgr.isMappingBroken("Tower", root))

    def test_an_already_terminated_root_is_not_doubled(self):
        asked = self._recordProbe("/mnt/nas/")
        self.assertEqual(["/mnt/nas/"], asked)

    def test_a_windows_root_is_probed_with_a_backslash(self):
        asked = self._recordProbe("\\\\server\\share")
        self.assertEqual(["\\\\server\\share\\"], asked)

    def _recordProbe(self, map_path):
        """The path verifyMapping() actually hands to xbmcvfs.exists()."""
        from lib import path_mapping
        asked = []
        original = path_mapping.xbmcvfs.exists
        path_mapping.xbmcvfs.exists = lambda p: asked.append(p) or True
        try:
            self.mgr.verifyMapping("Tower", map_path)
        finally:
            path_mapping.xbmcvfs.exists = original
        return asked

    def test_verify_mapping_can_notify_on_failure(self):
        self.mgr.verifyMapping("Tower", "/definitely/not/here", notify=True)
        self.assertTrue(any("Notification(" in call for call in ENV.builtins))

    def test_missing_file_on_a_healthy_root_reports_a_stream_fallback(self):
        root = self.mktemp()
        self.mgr.reportMappedFileMissing("Tower", root)
        self.assertFalse(self.mgr.isMappingBroken("Tower", root))
        self.assertIn(("Tower", root, "file"), self.mgr.NOTIFIED)

    def test_missing_file_on_a_dead_root_flags_the_root(self):
        dead = os.path.join(self.mktemp(), "gone")
        self.assertTrue(self.mgr.reportMappedFileMissing("Tower", dead))
        self.assertTrue(self.mgr.isMappingBroken("Tower", dead))

    def test_a_known_dead_root_is_not_re_statted(self):
        """
        Re-statting costs another full mount timeout on the playback thread,
        so a root already known to be dead must short-circuit.
        """
        dead = os.path.join(self.mktemp(), "gone")
        self.mgr.markMappingState("Tower", dead, works=False)
        before = len(ENV.builtins)
        self.assertFalse(self.mgr.reportMappedFileMissing("Tower", dead))
        self.assertEqual(before, len(ENV.builtins), "should not have notified again")


class AddDeleteMappingTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.mgr = manager({})
        self.server = FakeServer()

    def test_add_appends_a_trailing_separator_to_both_sides(self):
        self.mgr.addPathMapping("/mnt/nas", "/data", server=self.server, save=False)
        self.assertEqual({"Tower": {"/mnt/nas/": "/data/"}}, self.mgr.PATH_MAP)

    def test_add_respects_a_windows_separator(self):
        self.mgr.addPathMapping("D:\\media", "/data", server=self.server, save=False)
        self.assertEqual({"Tower": {"D:\\media\\": "/data/"}}, self.mgr.PATH_MAP)

    def test_add_does_not_double_a_separator(self):
        self.mgr.addPathMapping("/mnt/nas/", "/data/", server=self.server, save=False)
        self.assertEqual({"Tower": {"/mnt/nas/": "/data/"}}, self.mgr.PATH_MAP)

    def test_delete_removes_by_pms_side_target(self):
        self.mgr.addPathMapping("/mnt/nas", "/data", server=self.server, save=False)
        self.mgr.deletePathMapping("/data/", server=self.server, save=False)
        self.assertEqual({}, self.mgr.PATH_MAP["Tower"])

    def test_delete_clears_the_broken_flag_and_notification_record(self):
        self.mgr.addPathMapping("/mnt/nas", "/data", server=self.server, save=False)
        self.mgr.markMappingState("Tower", "/mnt/nas/", works=False)
        self.mgr.claimNotification("Tower", "/mnt/nas/", "root")

        self.mgr.deletePathMapping("/data/", server=self.server, save=False)
        self.assertFalse(self.mgr.isMappingBroken("Tower", "/mnt/nas/"))
        self.assertEqual(set(), self.mgr.NOTIFIED)

    def test_delete_of_an_unknown_target_is_a_no_op(self):
        self.mgr.addPathMapping("/mnt/nas", "/data", server=self.server, save=False)
        self.mgr.deletePathMapping("/nothing/", server=self.server, save=False)
        self.assertEqual({"/mnt/nas/": "/data/"}, self.mgr.PATH_MAP["Tower"])

    def test_delete_for_an_unknown_server_is_a_no_op(self):
        self.mgr.deletePathMapping("/data/", server=FakeServer("Nope"), save=False)
        self.assertEqual({}, self.mgr.PATH_MAP)


class PersistenceTest(KodiTestCase):
    def test_save_then_load_round_trips(self):
        mgr = manager({"Tower": {"/mnt/nas/": "/data/"}})
        self.assertTrue(mgr.save())

        reloaded = manager({})
        reloaded.mapfile = mgr.mapfile
        reloaded.load()
        self.assertEqual({"Tower": {"/mnt/nas/": "/data/"}}, reloaded.PATH_MAP)

    def test_load_tolerates_comments_and_a_trailing_comma(self):
        """
        The mapfile is hand-edited by users, so it is sanitised before being
        parsed as JSON: /* ... */ blocks, // line comments and one trailing
        comma before the closing braces.
        """
        mgr = manager({})
        with open(mgr.mapfile, "w", encoding="utf-8") as fp:
            fp.write('/* my mappings */\n'
                     '{\n'
                     '  "Tower": {\n'
                     '    "/mnt/nas/": "/data/",  // the big share\n'
                     '  }\n'
                     '}\n')
        mgr.load()
        self.assertEqual({"Tower": {"/mnt/nas/": "/data/"}}, mgr.PATH_MAP)

    def test_load_of_unsalvageable_json_leaves_the_map_alone(self):
        mgr = manager({"Tower": {"/keep/": "/data/"}})
        with open(mgr.mapfile, "w", encoding="utf-8") as fp:
            fp.write("{ this is not json at all ")
        mgr.load()
        self.assertEqual({"Tower": {"/keep/": "/data/"}}, mgr.PATH_MAP)

    def test_load_without_a_file_is_a_no_op(self):
        mgr = manager({})
        mgr.mapfile = os.path.join(self.mktemp(), "absent.json")
        mgr.load()
        self.assertEqual({}, mgr.PATH_MAP)

    def test_the_shipped_example_file_parses(self):
        """path_mapping.example.json is what users copy; it has to be valid."""
        from . import REPO_ROOT
        example = os.path.join(REPO_ROOT, "path_mapping.example.json")
        mgr = manager({})
        mgr.mapfile = example
        mgr.load()
        self.assertTrue(mgr.PATH_MAP, "example mapping file did not parse")
        for server, mappings in mgr.PATH_MAP.items():
            with self.subTest(server=server):
                self.assertIsInstance(mappings, dict)

    def tearDown(self):
        for name in ("path_mapping.json",):
            path = os.path.join(ENV.addon_data_dir, name)
            if os.path.exists(path):
                os.remove(path)
        KodiTestCase.tearDown(self)


class ExampleFileShapeTest(KodiTestCase):
    def test_example_is_json_after_comment_stripping(self):
        from lib import path_mapping
        from . import REPO_ROOT
        with open(os.path.join(REPO_ROOT, "path_mapping.example.json"), "r",
                  encoding="utf-8") as fp:
            data = fp.read()
        data = path_mapping.PM_MCMT_RE.sub("", data)
        data = path_mapping.PM_CMT_RE.sub("", data)
        data = path_mapping.PM_COMMA_RE.sub("}}", data)
        self.assertIsInstance(json.loads(data), dict)
