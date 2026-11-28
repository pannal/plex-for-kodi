# coding=utf-8
"""
lib/language_util.py - which languages count as "native" for subtitle suppression.

This is the code behind "don't show subtitles when the audio is already in my
language", so getting it wrong either buries wanted subtitles or leaves
unwanted ones on screen.
"""

from __future__ import absolute_import

from plexnet import util as pnUtil

from lib import language_util

from .base import KodiTestCase


class FakeAccount(object):
    def __init__(self, autoSelectSubtitle=0, audioLanguage=""):
        self.autoSelectSubtitle = autoSelectSubtitle
        self.audioLanguage = audioLanguage


class NormalizeLanguageTest(KodiTestCase):
    def test_two_letter_codes_become_part2t(self):
        self.assertEqual("eng", language_util.normalizeLanguagePart2t("en"))
        self.assertEqual("deu", language_util.normalizeLanguagePart2t("de"))

    def test_three_letter_codes_pass_through(self):
        self.assertEqual("eng", language_util.normalizeLanguagePart2t("eng"))

    def test_region_suffixes_are_stripped(self):
        self.assertEqual("por", language_util.normalizeLanguagePart2t("pt-BR"))
        self.assertEqual("por", language_util.normalizeLanguagePart2t("pt_br"))

    def test_case_and_whitespace_are_normalised(self):
        self.assertEqual("por", language_util.normalizeLanguagePart2t("  PT_br "))

    def test_unresolvable_input_is_none(self):
        for value in ("", None, "zz", "x", "abcd"):
            with self.subTest(value=value):
                self.assertIsNone(language_util.normalizeLanguagePart2t(value))

    def test_plex_style_pob_resolves_to_portuguese(self):
        """
        "pob" is Plex's Brazilian Portuguese and is not an ISO-639 code at all,
        so iso639 raises on it. Without the alias, a user whose Plex preferred
        audio is "pob" derived no native language at all.
        """
        self.assertEqual("por", language_util.normalizeLanguagePart2t("pob"))
        self.assertEqual("por", language_util.normalizeLanguagePart2t("pob-BR"))
        self.assertEqual("por", language_util.normalizeLanguagePart2t("POB"))


class ResolveLanguageTest(KodiTestCase):
    """
    The shared resolver. It exists because iso639 signals "unknown" by raising,
    and the playback-path callers (lib/player.py:1516, :1537) cannot afford a
    KeyError mid-seek.
    """

    def test_it_returns_an_iso639_language(self):
        self.assertEqual("English", language_util.resolveLanguage("en").name)
        self.assertEqual("German", language_util.resolveLanguage("deu").name)

    def test_two_letter_codes_are_looked_up_as_part1(self):
        self.assertEqual("por", language_util.resolveLanguage("pt").part2t)

    def test_the_bibliographic_part_can_be_requested(self):
        """Kodi reports part2b ("ger"), Plex reports part2t ("deu")."""
        self.assertEqual("German", language_util.resolveLanguage("ger", part="part2b").name)
        self.assertIsNone(language_util.resolveLanguage("ger"))

    def test_plex_aliases_are_applied(self):
        self.assertEqual("Portuguese", language_util.resolveLanguage("pob").name)

    def test_an_unknown_code_is_none_rather_than_a_keyerror(self):
        for value in ("zzz", "zz", "", None, "nonsense"):
            with self.subTest(value=value):
                self.assertIsNone(language_util.resolveLanguage(value))

    def test_an_unknown_code_in_part2b_is_also_none(self):
        self.assertIsNone(language_util.resolveLanguage("zzz", part="part2b"))


class NativeLanguagesTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_account = pnUtil.ACCOUNT

    def tearDown(self):
        pnUtil.ACCOUNT = self._orig_account
        KodiTestCase.tearDown(self)

    def test_configured_languages_are_authoritative(self):
        pnUtil.ACCOUNT = None
        self.assertEqual({"eng", "deu"}, language_util.getNativeLanguages(["eng", "deu"]))

    def test_no_configuration_and_no_account_is_empty(self):
        pnUtil.ACCOUNT = None
        self.assertEqual(set(), language_util.getNativeLanguages(None))
        self.assertEqual(set(), language_util.getNativeLanguages([]))

    def test_preferred_audio_is_added_in_foreign_audio_mode(self):
        """autoSelectSubtitle == 1 is the "shown with foreign audio" mode."""
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=1, audioLanguage="de")
        self.assertEqual({"eng", "deu"}, language_util.getNativeLanguages(["eng"]))

    def test_manual_subtitle_mode_derives_nothing(self):
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=0, audioLanguage="de")
        self.assertEqual({"eng"}, language_util.getNativeLanguages(["eng"]))

    def test_always_show_subtitle_mode_derives_nothing(self):
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=2, audioLanguage="de")
        self.assertEqual({"eng"}, language_util.getNativeLanguages(["eng"]))

    def test_unresolvable_preferred_audio_is_ignored(self):
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=1, audioLanguage="zz")
        self.assertEqual({"eng"}, language_util.getNativeLanguages(["eng"]))

    def test_empty_preferred_audio_is_ignored(self):
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=1, audioLanguage="")
        self.assertEqual({"eng"}, language_util.getNativeLanguages(["eng"]))

    def test_account_without_the_attributes_does_not_raise(self):
        pnUtil.ACCOUNT = object()
        self.assertEqual({"eng"}, language_util.getNativeLanguages(["eng"]))

    def test_the_caller_s_list_is_not_mutated(self):
        pnUtil.ACCOUNT = FakeAccount(autoSelectSubtitle=1, audioLanguage="de")
        configured = ["eng"]
        language_util.getNativeLanguages(configured)
        self.assertEqual(["eng"], configured)
