# coding=utf-8
"""
lib/settings_util.py - typed reads and writes over Kodi's string-only settings.

Kodi stores every setting as a string; the type of the *default* is what
decides how the stored string is interpreted. Getting that coercion wrong
turns "false" into a truthy value or a stored list into a crash, so the
mapping is worth pinning down.
"""

from __future__ import absolute_import

import binascii
import datetime
import json

from kodienv import ENV

from lib import settings_util
from lib.settings_util import UNDEF, getSetting, getUserSetting, setSetting
from plexnet import util as pnUtil

from .base import KodiTestCase


class FakeAccount(object):
    ID = "acct1"


class GetSettingTest(KodiTestCase):
    def test_missing_setting_returns_the_default(self):
        self.assertEqual("fallback", getSetting("nope", "fallback"))
        self.assertEqual(7, getSetting("nope", 7))

    def test_booleans_are_read_case_insensitively(self):
        ENV.settings["flag"] = "true"
        self.assertIs(True, getSetting("flag", False))
        ENV.settings["flag"] = "True"
        self.assertIs(True, getSetting("flag", False))
        ENV.settings["flag"] = "false"
        self.assertIs(False, getSetting("flag", False))

    def test_any_non_true_string_is_false(self):
        ENV.settings["flag"] = "yes"
        self.assertIs(False, getSetting("flag", False))

    def test_ints_tolerate_a_stored_float(self):
        ENV.settings["num"] = "12"
        self.assertEqual(12, getSetting("num", 0))
        ENV.settings["num"] = "12.9"
        self.assertEqual(12, getSetting("num", 0), "truncates rather than rounds")

    def test_floats(self):
        ENV.settings["f"] = "2.5"
        self.assertEqual(2.5, getSetting("f", 0.0))

    def test_lists_are_hex_encoded_json_by_default(self):
        raw = binascii.hexlify(json.dumps(["a", "b"]).encode("utf-8")).decode("ascii")
        ENV.settings["lst"] = raw
        self.assertEqual(["a", "b"], getSetting("lst", []))

    def test_lists_registered_as_json_are_read_as_plain_json(self):
        settings_util.JSON_SETTINGS.append("plain")
        try:
            ENV.settings["plain"] = '["a", "b"]'
            self.assertEqual(["a", "b"], getSetting("plain", []))
        finally:
            settings_util.JSON_SETTINGS.remove("plain")

    def test_an_empty_list_setting_returns_the_default(self):
        ENV.settings["lst"] = ""
        self.assertEqual(["d"], getSetting("lst", ["d"]))

    def test_datetimes_round_trip(self):
        when = datetime.datetime(2026, 7, 25, 13, 45, 30, 123456)
        setSetting("stamp", when)
        self.assertEqual(when, getSetting("stamp", datetime.datetime.fromtimestamp(0)))

    def test_strings_pass_through_untouched(self):
        ENV.settings["s"] = "  spaced  "
        self.assertEqual("  spaced  ", getSetting("s", ""))

    def test_undef_default_falls_back_to_the_registered_default(self):
        settings_util.DEFAULT_SETTINGS["registered"] = 42
        try:
            self.assertEqual(42, getSetting("registered", UNDEF))
            self.assertEqual(42, getSetting("registered"))
        finally:
            del settings_util.DEFAULT_SETTINGS["registered"]

    def test_undef_default_for_an_unregistered_key_is_none(self):
        self.assertIsNone(getSetting("never-registered"))


class SetSettingTest(KodiTestCase):
    def test_booleans_are_written_as_kodi_strings(self):
        setSetting("flag", True)
        self.assertEqual("true", ENV.settings["flag"])
        setSetting("flag", False)
        self.assertEqual("false", ENV.settings["flag"])

    def test_numbers_are_stringified(self):
        setSetting("num", 12)
        self.assertEqual("12", ENV.settings["num"])
        setSetting("f", 2.5)
        self.assertEqual("2.5", ENV.settings["f"])

    def test_a_written_bool_reads_back_as_a_bool(self):
        setSetting("flag", True)
        self.assertIs(True, getSetting("flag", False))

    def test_a_list_setting_round_trips(self):
        """
        The write half used to raise: hexlify needs bytes and it was handed the
        str from json.dumps. Reading was always fine, so only writing was
        broken - and no caller hit it because they all json.dumps() first.
        """
        setSetting("lst", ["a", "b"])
        self.assertEqual(["a", "b"], getSetting("lst", []))

    def test_a_written_list_is_stored_as_plain_hex(self):
        """Not as the repr of a bytes object, which is what hexlify would give."""
        setSetting("lst", ["a"])
        stored = ENV.settings["lst"]
        self.assertFalse(stored.startswith("b'"), stored)
        self.assertEqual(["a"], json.loads(binascii.unhexlify(stored)))

    def test_a_stored_empty_list_reads_back_as_an_empty_list(self):
        """
        Not as the default: "[]" hexlifies to a non-empty string, so the
        distinction between "never set" and "deliberately emptied" survives.
        """
        setSetting("lst", [])
        self.assertEqual([], getSetting("lst", ["fallback"]))
        self.assertEqual(["fallback"], getSetting("never_set", ["fallback"]))

    def test_a_list_with_unicode_round_trips(self):
        setSetting("lst", [u"Amélie", u"日本語"])
        self.assertEqual([u"Amélie", u"日本語"], getSetting("lst", []))

    def test_reading_a_legacy_hex_encoded_list_still_works(self):
        """The read half of the pair is fine, so values written under Py2 load."""
        raw = binascii.hexlify(json.dumps(["a", "b"]).encode("utf-8")).decode("ascii")
        ENV.settings["legacy"] = raw
        self.assertEqual(["a", "b"], getSetting("legacy", []))


class UserSettingTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_account = pnUtil.ACCOUNT

    def tearDown(self):
        pnUtil.ACCOUNT = self._orig_account
        KodiTestCase.tearDown(self)

    def test_without_an_account_the_default_is_returned(self):
        pnUtil.ACCOUNT = None
        ENV.settings["pref"] = "stored"
        self.assertEqual("fallback", getUserSetting("pref", "fallback"))

    def test_with_an_account_the_key_is_namespaced(self):
        pnUtil.ACCOUNT = FakeAccount()
        ENV.settings["pref.acct1"] = "mine"
        ENV.settings["pref"] = "global"
        self.assertEqual("mine", getUserSetting("pref", "fallback"))

    def test_a_namespaced_key_that_is_unset_returns_the_default(self):
        pnUtil.ACCOUNT = FakeAccount()
        ENV.settings["pref"] = "global"
        self.assertEqual("fallback", getUserSetting("pref", "fallback"))

    def test_typed_coercion_applies_to_user_settings_too(self):
        pnUtil.ACCOUNT = FakeAccount()
        ENV.settings["flag.acct1"] = "true"
        self.assertIs(True, getUserSetting("flag", False))
