# coding=utf-8
"""
Tests for the test harness itself.

Everything else in this suite is only as trustworthy as the Kodi stubs, so
these guard the stubs: that `import xbmc` really resolves to the fake, that
ENV.reset() actually isolates tests, and that the pieces PM4K reads at import
time answer plausibly.
"""

from __future__ import absolute_import

import collections
import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from kodi_six import xbmc as six_xbmc
from kodienv import ENV, LOGERROR, LOGINFO

from .base import KodiTestCase
from . import REPO_ROOT, STUBS_ROOT


class StubResolutionTest(KodiTestCase):
    def test_the_kodi_modules_resolve_to_the_stubs(self):
        for module in (xbmc, xbmcgui, xbmcvfs, xbmcaddon):
            with self.subTest(module=module.__name__):
                self.assertTrue(module.__file__.startswith(STUBS_ROOT),
                                "{0} came from {1}".format(module.__name__, module.__file__))

    def test_kodi_six_re_exports_the_same_module_objects(self):
        self.assertIs(xbmc, six_xbmc)
        self.assertIs(xbmc, sys.modules["kodi_six.xbmc"])

    def test_the_addon_package_is_importable(self):
        import lib.util
        self.assertTrue(lib.util.__file__.startswith(REPO_ROOT))

    def test_the_vendored_packages_are_importable_by_bare_name(self):
        import ibis
        import plexnet
        self.assertIn("_included_packages", plexnet.__file__)
        self.assertIn("_included_packages", ibis.__file__)


class EnvIsolationTest(KodiTestCase):
    """setUp calls ENV.reset(); these two tests must not see each other's state."""

    def test_a_writes_state(self):
        ENV.settings["leak_check"] = "written"
        ENV.log("leaked", LOGINFO)
        ENV.builtins.append("Leaked()")
        self.assertEqual("written", ENV.settings["leak_check"])

    def test_b_sees_none_of_it(self):
        self.assertNotIn("leak_check", ENV.settings)
        self.assertFalse(ENV.logged("leaked"))
        self.assertFalse(ENV.builtin_called("Leaked()"))

    def test_player_state_is_reset_between_tests(self):
        self.assertFalse(xbmc.Player().isPlayingVideo())
        self.assertEqual([], xbmc.Player.calls)


class LoggingTest(KodiTestCase):
    def test_log_lines_are_captured_with_their_level(self):
        xbmc.log("hello", LOGERROR)
        self.assertEqual(("hello", LOGERROR), ENV.log_lines[-1])
        self.assertTrue(ENV.logged("hello"))
        self.assertTrue(ENV.logged("hello", level=LOGERROR))
        self.assertFalse(ENV.logged("hello", level=LOGINFO))

    def test_the_addons_own_logger_reaches_the_capture(self):
        from lib.logging import LOG
        LOG("a message with {0}", "args")
        self.assertTrue(ENV.logged("a message with args"))

    def test_builtins_are_recorded(self):
        xbmc.executebuiltin("Notification(a,b,1000,icon)")
        self.assertTrue(ENV.builtin_called("Notification("))


class JsonRpcTest(KodiTestCase):
    def test_a_known_setting_is_answered(self):
        from lib.kodijsonrpc import rpc
        self.assertEqual("HH:mm:ss",
                         rpc.Settings.GetSettingValue(setting="locale.timeformat")["value"])

    def test_an_unknown_setting_raises_the_way_kodi_would(self):
        from lib.kodijsonrpc import rpc
        with self.assertRaises(Exception):
            rpc.Settings.GetSettingValue(setting="no.such.setting")

    def test_an_unknown_method_raises(self):
        from lib.kodijsonrpc import rpc
        with self.assertRaises(Exception):
            rpc.Nonsense.DoThing()

    def test_calls_are_recorded(self):
        from lib.kodijsonrpc import rpc
        rpc.Settings.GetSettingValue(setting="locale.timeformat")
        self.assertIn(("Settings.GetSettingValue", {"setting": "locale.timeformat"}),
                      ENV.jsonrpc_calls)

    def test_setting_a_kodi_setting_round_trips(self):
        from lib.kodijsonrpc import rpc
        rpc.Settings.SetSettingValue(setting="filecache.memorysize", value=99)
        self.assertEqual(99, rpc.Settings.GetSettingValue(
            setting="filecache.memorysize")["value"])


class PathTranslationTest(KodiTestCase):
    def test_special_paths_land_under_the_temp_root(self):
        for special in ("special://temp/", "special://profile/", "special://home/"):
            with self.subTest(path=special):
                translated = xbmcvfs.translatePath(special)
                self.assertTrue(translated.startswith(ENV.tmp_root), translated)

    def test_nothing_resolves_into_the_working_tree(self):
        """The single most important property: tests must not write to the repo."""
        for special in ("special://temp/x", "special://profile/y",
                        "special://home/addons/z"):
            with self.subTest(path=special):
                self.assertFalse(xbmcvfs.translatePath(special).startswith(REPO_ROOT + os.sep))

    def test_a_plain_path_is_passed_through(self):
        self.assertEqual("/mnt/media/a.mkv", xbmcvfs.translatePath("/mnt/media/a.mkv"))

    def test_the_addon_profile_is_writable(self):
        path = os.path.join(ENV.addon_data_dir, "probe.txt")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write("ok")
        self.assertTrue(os.path.exists(path))
        os.remove(path)


class VfsTest(KodiTestCase):
    def test_write_read_stat_and_delete(self):
        path = os.path.join(self.mktemp(), "a.txt")
        handle = xbmcvfs.File(path, "w")
        self.assertTrue(handle.write("hello"))
        handle.close()

        self.assertTrue(xbmcvfs.exists(path))
        self.assertEqual(5, xbmcvfs.Stat(path).st_size())

        handle = xbmcvfs.File(path)
        self.assertEqual("hello", handle.read())
        handle.close()

        self.assertTrue(xbmcvfs.delete(path))
        self.assertFalse(xbmcvfs.exists(path))

    def test_unicode_survives_a_round_trip(self):
        path = os.path.join(self.mktemp(), "u.txt")
        with xbmcvfs.File(path, "w") as handle:
            handle.write(u"Amélie – 日本語")
        with xbmcvfs.File(path) as handle:
            self.assertEqual(u"Amélie – 日本語", handle.read())

    def test_listdir_splits_dirs_from_files(self):
        base = self.mktemp()
        os.makedirs(os.path.join(base, "sub"))
        with open(os.path.join(base, "f.txt"), "w", encoding="utf-8") as fp:
            fp.write("x")
        self.assertEqual((["sub"], ["f.txt"]), xbmcvfs.listdir(base))

    def test_listdir_of_a_missing_path_is_empty(self):
        self.assertEqual(([], []), xbmcvfs.listdir(os.path.join(self.mktemp(), "gone")))

    def test_deleting_a_missing_file_reports_failure(self):
        self.assertFalse(xbmcvfs.delete(os.path.join(self.mktemp(), "gone")))


class AddonSettingsTest(KodiTestCase):
    def test_every_addon_instance_shares_one_store(self):
        """Kodi's settings store is global; two Addon() objects must agree."""
        xbmcaddon.Addon().setSetting("shared", "value")
        self.assertEqual("value", xbmcaddon.Addon().getSetting("shared"))

    def test_addon_info_comes_from_the_working_tree(self):
        info = xbmcaddon.Addon()
        self.assertEqual("script.plexmod", info.getAddonInfo("id"))
        self.assertEqual(REPO_ROOT, info.getAddonInfo("path"))
        self.assertNotEqual("0.0.0", info.getAddonInfo("version"))

    def test_the_addon_name_matches_addon_xml(self):
        """
        lib.kodi_util derives FROM_KODI_REPOSITORY from this name, which gates
        whether advancedsettings.xml may be written - so it has to reflect the
        checked-out variant rather than a hardcoded guess.
        """
        with open(os.path.join(REPO_ROOT, "addon.xml"), "r", encoding="utf-8") as fp:
            head = fp.read(2048)
        self.assertIn('name="{0}"'.format(xbmcaddon.Addon().getAddonInfo("name")), head)

    def test_localised_strings_come_from_the_real_po_file(self):
        self.assertEqual("Main", xbmcaddon.Addon().getLocalizedString(32000))

    def test_typed_setting_accessors(self):
        addon = xbmcaddon.Addon()
        addon.setSettingBool("b", True)
        addon.setSettingInt("i", 5)
        addon.setSettingNumber("f", 2.5)
        self.assertTrue(addon.getSettingBool("b"))
        self.assertEqual(5, addon.getSettingInt("i"))
        self.assertEqual(2.5, addon.getSettingNumber("f"))


class WindowPropertyTest(KodiTestCase):
    def test_properties_round_trip(self):
        window = xbmcgui.Window(10000)
        window.setProperty("script.plex.probe", "1")
        self.assertEqual("1", window.getProperty("script.plex.probe"))
        self.assertEqual("1", xbmcgui.Window(10000).getProperty("script.plex.probe"))

    def test_the_infolabel_route_reads_the_same_store(self):
        """PM4K reads its own properties back through Window(10000).Property(...)."""
        xbmcgui.Window(10000).setProperty("script.plex.probe", "42")
        self.assertEqual("42",
                         xbmc.getInfoLabel("Window(10000).Property(script.plex.probe)"))

    def test_the_addons_property_helpers_work_end_to_end(self):
        from lib.properties import getGlobalProperty, setGlobalProperty
        setGlobalProperty("harness_probe", "yes")
        self.assertEqual("yes", getGlobalProperty("harness_probe"))

    def test_clearing_a_property(self):
        window = xbmcgui.Window(10000)
        window.setProperty("gone", "1")
        window.clearProperty("gone")
        self.assertEqual("", window.getProperty("gone"))


class DialogTest(KodiTestCase):
    def test_scripted_answers_are_consumed_in_order(self):
        ENV.dialog_answers = collections.deque(["first", "second"])
        dialog = xbmcgui.Dialog()
        self.assertEqual("first", dialog.input("a"))
        self.assertEqual("second", dialog.input("b"))

    def test_an_unscripted_dialog_reads_as_dismissed(self):
        """
        The neutral default matters: a test that forgets to script an answer
        must not accidentally confirm a destructive prompt.
        """
        dialog = xbmcgui.Dialog()
        self.assertFalse(dialog.yesno("h", "m"))
        self.assertEqual(-1, dialog.select("h", ["a"]))
        self.assertEqual("", dialog.input("h"))

    def test_dialog_calls_are_recorded(self):
        xbmcgui.Dialog().notification("head", "body")
        self.assertEqual("notification", ENV.dialog_calls[-1][0])


class InfoLabelTest(KodiTestCase):
    def test_a_known_label(self):
        self.assertIn("21.2", xbmc.getInfoLabel("System.BuildVersion"))

    def test_an_unknown_label_is_empty(self):
        self.assertEqual("", xbmc.getInfoLabel("No.Such.Label"))

    def test_cond_visibility_defaults_to_false_and_is_steerable(self):
        self.assertFalse(xbmc.getCondVisibility("System.Platform.Android"))
        ENV.cond_visibility["System.Platform.Android"] = True
        self.assertTrue(xbmc.getCondVisibility("System.Platform.Android"))

    def test_cond_visibility_accepts_a_callable(self):
        ENV.cond_visibility["System.HasAddon(x)"] = lambda cond: "x" in cond
        self.assertTrue(xbmc.getCondVisibility("System.HasAddon(x)"))

    def test_the_kodi_version_was_parsed_from_the_build_version_label(self):
        from lib import kodi_util
        self.assertEqual(21, kodi_util.KODI_VERSION_MAJOR)
        self.assertEqual(2, kodi_util.KODI_VERSION_MINOR)
        self.assertEqual(2102000, kodi_util.KODI_BUILD_NUMBER)


class MonitorTest(KodiTestCase):
    def test_wait_for_abort_returns_false_until_told_otherwise(self):
        monitor = xbmc.Monitor()
        self.assertFalse(monitor.waitForAbort(0.1))
        ENV.abort_on_wait = True
        self.assertTrue(monitor.waitForAbort(0.1))

    def test_abort_requested_is_steerable(self):
        monitor = xbmc.Monitor()
        self.assertFalse(monitor.abortRequested())
        ENV.abort_requested = True
        self.assertTrue(monitor.abortRequested())

    def test_the_addons_monitor_subclass_is_constructible(self):
        from lib.monitor import MONITOR
        self.assertFalse(MONITOR.abortRequested())
        self.assertEqual(20.0, MONITOR.waitAmount(2, interval=0.1))

    def test_waits_are_recorded_rather_than_slept(self):
        before = len(ENV.waits)
        xbmc.Monitor().waitForAbort(30)
        self.assertEqual(before + 1, len(ENV.waits))
        self.assertEqual(30, ENV.waits[-1])


class StringsParserTest(KodiTestCase):
    def test_english_msgstr_falls_back_to_msgid(self):
        """
        The en_gb file leaves every msgstr empty and relies on Kodi falling
        back to the msgid; the parser has to do the same or every en_gb lookup
        would come back blank.
        """
        strings = ENV.strings("en_gb")
        self.assertEqual("Main", strings[32000])
        self.assertTrue(all(isinstance(v, str) for v in strings.values()))

    def test_a_translated_language_uses_its_msgstr(self):
        german = ENV.strings("de_de")
        self.assertTrue(german)
        self.assertNotEqual(ENV.strings("en_gb")[32000], german.get(32000, ""))

    def test_an_unknown_language_is_empty_rather_than_an_error(self):
        self.assertEqual({}, ENV.strings("xx_yy"))
