# coding=utf-8
"""
plexnet.verlib - PEP 386 style version handling, used to gate PMS features.

PM4K compares the connected server's version against feature thresholds, so an
ordering mistake here silently enables or hides server features.
"""

from __future__ import absolute_import

from plexnet.verlib import (HugeMajorVersionNumError, IrrationalVersionError,
                            NormalizedVersion, suggest_normalized_version)

from .base import KodiTestCase


class ParsingTest(KodiTestCase):
    def test_a_two_part_version_is_padded(self):
        self.assertEqual("1.2", str(NormalizedVersion("1.2")))

    def test_a_four_part_version(self):
        self.assertEqual("1.2.3.4", str(NormalizedVersion("1.2.3.4")))

    def test_prerelease_markers(self):
        for value in ("1.2a1", "1.2.3a2", "1.2.3b1", "1.2.3c1"):
            with self.subTest(value=value):
                self.assertEqual(value, str(NormalizedVersion(value)))

    def test_a_single_number_is_irrational(self):
        with self.assertRaises(IrrationalVersionError):
            NormalizedVersion("1")

    def test_a_release_level_without_a_serial_is_irrational(self):
        with self.assertRaises(IrrationalVersionError):
            NormalizedVersion("1.2a")

    def test_nonsense_is_irrational(self):
        with self.assertRaises(IrrationalVersionError):
            NormalizedVersion("not a version")

    def test_a_year_as_the_major_number_is_rejected_by_default(self):
        """
        A version like 2009.1.3 permanently locks out ever using 1.0, so it is
        refused unless the caller opts in.
        """
        with self.assertRaises(HugeMajorVersionNumError):
            NormalizedVersion("2009.1.3")

    def test_a_year_major_number_can_be_allowed_explicitly(self):
        self.assertEqual("2009.1.3",
                         str(NormalizedVersion("2009.1.3", error_on_huge_major_num=False)))

    def test_the_year_guard_only_trips_above_1980(self):
        self.assertEqual("1979.1", str(NormalizedVersion("1979.1")))

    def test_zero_padded_segments_are_rejected_outright(self):
        """
        The leading-zero check runs before the year guard, so a real date-shaped
        version raises IrrationalVersionError rather than HugeMajorVersionNumError
        and cannot be opted into at all.
        """
        for flag in (True, False):
            with self.subTest(error_on_huge_major_num=flag):
                with self.assertRaises(IrrationalVersionError):
                    NormalizedVersion("2009.01.03", error_on_huge_major_num=flag)


class OrderingTest(KodiTestCase):
    def assertOrder(self, lower, higher):
        self.assertLess(NormalizedVersion(lower), NormalizedVersion(higher),
                        "{0} should sort below {1}".format(lower, higher))
        self.assertGreater(NormalizedVersion(higher), NormalizedVersion(lower))

    def test_equality(self):
        self.assertEqual(NormalizedVersion("1.2"), NormalizedVersion("1.2"))
        self.assertEqual(NormalizedVersion("1.2"), NormalizedVersion("1.2.0"))

    def test_numeric_ordering(self):
        self.assertOrder("1.2", "1.3")
        self.assertOrder("1.9", "1.10")
        self.assertOrder("1.2.3", "1.2.4")

    def test_a_prerelease_sorts_below_its_release(self):
        self.assertOrder("1.2a1", "1.2")
        self.assertOrder("1.2b1", "1.2")
        self.assertOrder("1.2c1", "1.2")

    def test_prerelease_levels_are_ordered(self):
        self.assertOrder("1.2a1", "1.2b1")
        self.assertOrder("1.2b1", "1.2c1")

    def test_prerelease_serials_are_ordered(self):
        self.assertOrder("1.2a1", "1.2a2")

    def test_versions_are_hashable(self):
        """
        Defining __eq__ drops the inherited __hash__ on Python 3, so this
        needed an explicit __hash__ to be usable as a dict key or set member.
        """
        self.assertEqual({NormalizedVersion("1.2"), NormalizedVersion("1.2")},
                         {NormalizedVersion("1.2")})
        self.assertEqual(1, len({NormalizedVersion("1.2"): 1,
                                 NormalizedVersion("1.2.0"): 2}))

    def test_equal_versions_hash_alike(self):
        self.assertEqual(hash(NormalizedVersion("1.2")), hash(NormalizedVersion("1.2.0")))

    def test_sorting_a_list(self):
        versions = [NormalizedVersion(v) for v in ("1.10", "1.2", "1.2a1", "1.9")]
        self.assertEqual(["1.2a1", "1.2", "1.9", "1.10"],
                         [str(v) for v in sorted(versions)])


class SuggestionTest(KodiTestCase):
    def test_an_already_normal_version_is_returned_unchanged(self):
        self.assertEqual("1.2.3", suggest_normalized_version("1.2.3"))

    def test_common_prerelease_spellings_are_normalised(self):
        for raw, expected in (("1.0beta1", "1.0b1"),
                              ("1.0.beta1", "1.0b1"),
                              ("1.0alpha1", "1.0a1"),
                              ("1.0-rc1", "1.0c1"),
                              ("1.0pre1", "1.0c1")):
            with self.subTest(raw=raw):
                self.assertEqual(expected, suggest_normalized_version(raw))

    def test_an_unseparated_rc_sorts_as_a_release_candidate(self):
        """
        VERSION_RE documents "rc" as an alias for "c", but the parser used to
        store the raw letters - and "rc" sorts above the final marker "f", so
        1.0rc1 compared as NEWER than 1.0, the opposite of what a release
        candidate means.
        """
        self.assertLess(NormalizedVersion("1.0rc1"), NormalizedVersion("1.0"))
        self.assertEqual(NormalizedVersion("1.0rc1"), NormalizedVersion("1.0c1"))

    def test_rc_is_normalised_in_the_string_form_too(self):
        self.assertEqual("1.0c1", str(NormalizedVersion("1.0rc1")))

    def test_rc_serials_still_order_among_themselves(self):
        self.assertLess(NormalizedVersion("1.0rc1"), NormalizedVersion("1.0rc2"))
        self.assertLess(NormalizedVersion("1.0b9"), NormalizedVersion("1.0rc1"))

    def test_a_leading_v_is_stripped(self):
        self.assertEqual("1.0", suggest_normalized_version("v1.0"))

    def test_a_hopeless_string_yields_nothing(self):
        self.assertIsNone(suggest_normalized_version("not a version at all"))

    def test_suggestions_for_the_spellings_it_understands_are_parseable(self):
        for raw in ("1.0beta1", "v1.0", "1.0-rc1", "1.0alpha1", "1.0pre1"):
            with self.subTest(raw=raw):
                NormalizedVersion(suggest_normalized_version(raw))


class PmsVersionTest(KodiTestCase):
    """
    Real PMS version strings, which is what this is used on in practice. They
    carry a build suffix that has to be trimmed before comparison.
    """

    def test_pms_versions_compare_by_their_numeric_part(self):
        older = NormalizedVersion("1.32.8")
        newer = NormalizedVersion("1.40.1")
        self.assertLess(older, newer)

    def test_a_pms_build_suffix_is_not_a_normal_version(self):
        with self.assertRaises(IrrationalVersionError):
            NormalizedVersion("1.40.1.8227-c0dd5a73e")

    def test_the_numeric_prefix_of_a_pms_version_is_usable(self):
        raw = "1.40.1.8227-c0dd5a73e"
        numeric = ".".join(raw.split("-")[0].split(".")[:3])
        self.assertEqual("1.40.1", str(NormalizedVersion(numeric)))
