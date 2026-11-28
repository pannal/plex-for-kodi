# coding=utf-8
"""
lib/version.py - Debian-style version comparison, and lib/os_utils.py.

The updater decides "is the remote newer than what's installed" through
version_compare, so an ordering mistake here either offers a downgrade as an
update or hides a real one. The `~` handling in particular is what makes
pre-releases sort *below* their final version.
"""

from __future__ import absolute_import

import os

from lib import os_utils
from lib.version import Version, version_compare

from .base import KodiTestCase
from . import REPO_ROOT


class VersionParsingTest(KodiTestCase):
    def test_a_plain_version(self):
        v = Version("1.2.3")
        self.assertIsNone(v.epoch)
        self.assertEqual("1.2.3", v.upstream_version)
        self.assertIsNone(v.debian_revision)

    def test_an_epoch_and_a_revision(self):
        v = Version("2:1.2.3-4")
        self.assertEqual("2", v.epoch)
        self.assertEqual("1.2.3", v.upstream_version)
        self.assertEqual("4", v.debian_revision)

    def test_str_returns_the_original(self):
        self.assertEqual("1.2.3-1", str(Version("1.2.3-1")))

    def test_a_colon_without_an_epoch_is_rejected(self):
        with self.assertRaises(ValueError):
            Version("1.2:3")

    def test_an_empty_version_is_rejected(self):
        with self.assertRaises(ValueError):
            Version("")

    def test_versions_are_hashable_and_compare_by_value(self):
        self.assertEqual(Version("1.0"), Version("1.0"))
        self.assertEqual({Version("1.0"), Version("1.0")}, {Version("1.0")})


class VersionOrderingTest(KodiTestCase):
    def assertOrder(self, lower, higher):
        self.assertEqual(-1, version_compare(lower, higher),
                         "{0} should sort below {1}".format(lower, higher))
        self.assertEqual(1, version_compare(higher, lower))
        self.assertLess(Version(lower), Version(higher))
        self.assertGreater(Version(higher), Version(lower))

    def test_equal_versions(self):
        self.assertEqual(0, version_compare("1.2.3", "1.2.3"))

    def test_numeric_components_compare_numerically_not_lexically(self):
        self.assertOrder("1.9", "1.10")
        self.assertOrder("1.2.9", "1.2.10")

    def test_more_components_beat_fewer(self):
        self.assertOrder("1.2", "1.2.1")

    def test_major_beats_minor(self):
        self.assertOrder("1.99.99", "2.0.0")

    def test_a_revision_beats_no_revision(self):
        self.assertOrder("1.2.3", "1.2.3-1")
        self.assertOrder("1.2.3-1", "1.2.3-2")

    def test_an_epoch_outranks_everything_else(self):
        self.assertOrder("99.0", "1:1.0")

    def test_a_tilde_sorts_below_the_release_it_precedes(self):
        """This is what makes 2.0.0~beta1 an *older* version than 2.0.0."""
        self.assertOrder("2.0.0~beta1", "2.0.0")
        self.assertOrder("2.0.0~beta1", "2.0.0~beta2")
        self.assertOrder("2.0.0~rc1", "2.0.0~rc2")

    def test_a_tilde_even_sorts_below_the_empty_string(self):
        self.assertOrder("1.0~", "1.0")

    def test_a_suffix_sorts_above_the_bare_version(self):
        self.assertOrder("1.0", "1.0a")

    def test_comparing_against_a_none_object_treats_it_as_missing(self):
        """NativeVersion._compare short-circuits on a literal None operand."""
        self.assertGreater(Version("1.0"), None)

    def test_version_compare_treats_a_missing_version_as_older(self):
        """
        This used to wrap None in Version(), turning it into the literal string
        "None" - which sorts *above* a numeric version, the opposite of what a
        missing version means.
        """
        self.assertEqual(1, version_compare("1.0", None))
        self.assertEqual(-1, version_compare(None, "1.0"))
        self.assertEqual(0, version_compare(None, None))

    def test_a_missing_remote_version_is_never_offered_as_an_update(self):
        """The shape lib/updater.py:134 relies on: vc > 0 means "newer"."""
        self.assertLessEqual(version_compare(None, "2.0.0"), 0)

    def test_pm4k_style_versions_order_correctly(self):
        self.assertOrder("2.0.5", "2.0.6")
        self.assertOrder("2.0.9", "2.0.10")
        self.assertOrder("2.0.10~dev1", "2.0.10")

    def test_the_shipped_addon_version_parses(self):
        from kodienv import ENV
        version = ENV.addon_info["version"]
        self.assertNotEqual("0.0.0", version, "could not read version from addon.xml")
        self.assertEqual(0, version_compare(version, version))
        self.assertEqual(-1, version_compare(version, "9999.0.0"))


class FastGlobTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.dir = self.mktemp()
        for name in ("a.xml", "b.xml", "c.txt"):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fp:
                fp.write("x")

    def test_a_pattern_matches_by_basename(self):
        self.assertEqual(["a.xml", "b.xml"],
                         sorted(os_utils.fast_glob(os.path.join(self.dir, "*.xml"))))

    def test_names_are_returned_bare_not_as_paths(self):
        """
        fast_iglob yields basenames, not full paths - callers that need a path
        have to rejoin it themselves.
        """
        for name in os_utils.fast_glob(os.path.join(self.dir, "*.xml")):
            with self.subTest(name=name):
                self.assertNotIn(os.sep, name)

    def test_a_non_matching_pattern_returns_nothing(self):
        self.assertEqual([], os_utils.fast_glob(os.path.join(self.dir, "*.nope")))

    def test_a_missing_directory_returns_nothing(self):
        self.assertEqual([], os_utils.fast_glob(os.path.join(self.dir, "gone", "*")))

    def test_iglob_is_lazy(self):
        result = os_utils.fast_iglob(os.path.join(self.dir, "*.xml"))
        self.assertFalse(isinstance(result, list))
        self.assertEqual(2, len(list(result)))

    def test_it_descends_into_subdirectories(self):
        """
        os.walk based, so unlike glob it is recursive. The template engine
        relies on this to find templates, and any caller counting matches has
        to know that a nested match is counted too.
        """
        nested = os.path.join(self.dir, "sub")
        os.makedirs(nested)
        with open(os.path.join(nested, "deep.xml"), "w", encoding="utf-8") as fp:
            fp.write("x")
        self.assertEqual(["a.xml", "b.xml", "deep.xml"],
                         sorted(os_utils.fast_glob(os.path.join(self.dir, "*.xml"))))

    def test_it_finds_the_shipped_templates(self):
        pattern = os.path.join(REPO_ROOT, "resources", "skins", "Main", "1080i",
                               "templates", "script-plex-*.xml.tpl")
        self.assertGreater(len(os_utils.fast_glob(pattern)), 40)
