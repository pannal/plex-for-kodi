# coding=utf-8
"""
lib/i18n.py and resources/language - translation lookups and .po integrity.

Kodi matches a translation by *msgid*, not by numeric id alone: if a
translation file's msgid no longer matches en_gb's for the same id, Kodi
silently drops that translation and shows English. Nothing in the addon
notices, which is exactly why it is worth a test.

Note the parser below reads multi-line entries. A .po string can be split over
several quoted continuation lines, and comparing only the first line reports
drift on entries that are in fact identical.
"""

from __future__ import absolute_import

import os
import re

from kodienv import ENV, parse_strings_po

from lib.i18n import T, TRANSLATED_ROLES

from .base import KodiTestCase, LANGUAGE_DIR
from . import REPO_ROOT

CTXT_RE = re.compile(r'^msgctxt\s+"#(\d+)"\s*$')
MSGID_RE = re.compile(r'^msgid\s+"(.*)"\s*$')
T_CALL_RE = re.compile(r"\bT\(\s*(\d{5})\b")

EN_GB = "resource.language.en_gb"

# Translations whose msgid has drifted from en_gb. Each of these strings shows
# English at runtime, because Kodi matches on the msgid text.
#
# These are deliberately NOT fixed by a mechanical resync (see 0c93659c): just
# rewriting the msgid would re-enable a translation of text that no longer says
# the same thing - 33650 still names the old 500ms default in seven languages,
# and cs_cz is stale enough that 32456 pairs English "Show" with a Czech msgid
# of "Offline Mode". They need a translator round.
#
# de_de is held at zero: it was resynced by hand in 0c93659c and must stay that
# way. Every other number must not grow.
#
# Counted with msgids() below, where a duplicated id resolves to its last block
# (the KNOWN_DUPLICATE_IDS entries therefore contribute at most once).
KNOWN_MSGID_DRIFT = {
    "resource.language.cs_cz": 17,
    "resource.language.de_de": 0,
    "resource.language.es_es": 4,
    "resource.language.fr_fr": 4,
    "resource.language.hu_hu": 4,
    "resource.language.it_it": 4,
    "resource.language.pl_pl": 4,
    "resource.language.pt_br": 4,
    "resource.language.pt_pt": 4,
    "resource.language.ru_ru": 4,
    "resource.language.zh_cn": 4,
}

# Ids appearing twice in one file, from a reworded en_gb entry being appended
# rather than replaced. One of the two blocks is dead weight.
KNOWN_DUPLICATE_IDS = {
    "resource.language.es_es": {32973, 33650, 34045},
    "resource.language.fr_fr": {32973},
    "resource.language.hu_hu": {32973, 33650, 34045},
    "resource.language.it_it": {32973},
    "resource.language.pl_pl": {32973},
    "resource.language.pt_br": {32973},
    "resource.language.pt_pt": {32973},
    "resource.language.ru_ru": {32973},
    "resource.language.zh_cn": {32973},
}


def language_dirs():
    return sorted(d for d in os.listdir(LANGUAGE_DIR)
                  if os.path.exists(os.path.join(LANGUAGE_DIR, d, "strings.po")))


def po_path(language):
    return os.path.join(LANGUAGE_DIR, language, "strings.po")


def msgids(language):
    """{numeric id: raw msgid} - the key Kodi actually matches on.

    Joins continuation lines: a long msgid is written as several quoted lines,
    and comparing only the first one reports drift where there is none.
    """
    with open(po_path(language), "r", encoding="utf-8") as fp:
        lines = fp.read().split("\n")

    out, i = {}, 0
    while i < len(lines):
        match = CTXT_RE.match(lines[i])
        if not match:
            i += 1
            continue
        ident = int(match.group(1))
        i += 1
        if i < len(lines) and MSGID_RE.match(lines[i]):
            text = MSGID_RE.match(lines[i]).group(1)
            i += 1
            while i < len(lines) and lines[i].startswith('"'):
                text += lines[i][1:-1]
                i += 1
            out[ident] = text
    return out


def all_ids(language):
    """Every msgctxt id in file order, duplicates included."""
    with open(po_path(language), "r", encoding="utf-8") as fp:
        return [int(m.group(1)) for m in
                (CTXT_RE.match(line.rstrip("\n")) for line in fp) if m]


class TranslationLookupTest(KodiTestCase):
    def test_a_known_id_resolves_to_the_english_string(self):
        self.assertEqual("Main", T(32000, "fallback"))

    def test_an_unknown_id_falls_back_to_the_inline_english(self):
        self.assertEqual("fallback", T(99999, "fallback"))

    def test_an_unknown_id_without_a_fallback_is_empty(self):
        self.assertEqual("", T(99999))

    def test_translated_roles_are_populated(self):
        self.assertTrue(TRANSLATED_ROLES)
        for key in ("Director", "Writer", "Producer", ""):
            with self.subTest(role=key):
                self.assertTrue(TRANSLATED_ROLES[key],
                                "role {0!r} resolved to an empty string".format(key))

    def test_the_stub_reads_the_real_po_file(self):
        """Guards the harness: a broken parser would make every T() test vacuous."""
        self.assertGreater(len(ENV.strings("en_gb")), 500)


class SourceStringCoverageTest(KodiTestCase):
    def test_every_translated_string_used_in_code_exists_in_en_gb(self):
        """
        A T() call with an id missing from en_gb renders as its inline English
        on every platform, so the string can never be translated at all.
        """
        available = set(msgids(EN_GB))
        missing = {}
        for root, _, files in os.walk(os.path.join(REPO_ROOT, "lib")):
            if "_included_packages" in root:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                with open(path, "r", encoding="utf-8") as fp:
                    for lineno, line in enumerate(fp, 1):
                        for match in T_CALL_RE.finditer(line):
                            ident = int(match.group(1))
                            if ident not in available:
                                missing.setdefault(ident, []).append(
                                    "{0}:{1}".format(os.path.relpath(path, REPO_ROOT),
                                                     lineno))
        self.assertEqual({}, missing, "T() ids not present in en_gb strings.po")

    def test_the_scan_actually_found_call_sites(self):
        """A regex that matched nothing would make the test above vacuous."""
        found = 0
        for root, _, files in os.walk(os.path.join(REPO_ROOT, "lib")):
            if "_included_packages" in root:
                continue
            for fn in files:
                if fn.endswith(".py"):
                    with open(os.path.join(root, fn), "r", encoding="utf-8") as fp:
                        found += len(T_CALL_RE.findall(fp.read()))
        self.assertGreater(found, 100, "T() scan found suspiciously few call sites")


class PoFileIntegrityTest(KodiTestCase):
    def test_english_is_present_and_is_the_largest_catalogue(self):
        self.assertIn(EN_GB, language_dirs())
        english = len(msgids(EN_GB))
        for language in language_dirs():
            if language == EN_GB:
                continue
            with self.subTest(language=language):
                self.assertLessEqual(len(msgids(language)), english,
                                     "translation has ids en_gb does not")

    def test_every_translated_id_exists_in_english(self):
        english = set(msgids(EN_GB))
        for language in language_dirs():
            if language == EN_GB:
                continue
            with self.subTest(language=language):
                orphans = sorted(set(msgids(language)) - english)
                self.assertEqual([], orphans,
                                 "ids present in {0} but not en_gb".format(language))

    def test_every_po_file_parses(self):
        for language in language_dirs():
            with self.subTest(language=language):
                self.assertTrue(parse_strings_po(po_path(language)),
                                "{0} parsed to nothing".format(language))

    def test_msgid_drift_has_not_grown(self):
        """
        Kodi keys translations off the msgid text. Where a translation's msgid
        no longer matches en_gb's, that entry is dead: the string falls back to
        English at runtime no matter what its msgstr says.

        Reword en_gb and you owe the translations a pass - which is a translator
        round, not a mechanical resync, so this guards the count rather than
        demanding zero. See KNOWN_MSGID_DRIFT.
        """
        english = msgids(EN_GB)
        for language in language_dirs():
            if language == EN_GB:
                continue
            with self.subTest(language=language):
                theirs = msgids(language)
                drifted = sorted(i for i in set(english) & set(theirs)
                                 if english[i] != theirs[i])
                allowed = KNOWN_MSGID_DRIFT.get(language, 0)
                self.assertLessEqual(
                    len(drifted), allowed,
                    "msgid drift grew in {0} (allowed {1}): {2}".format(
                        language, allowed, drifted))

    def test_german_stays_fully_resynced(self):
        """de_de was brought to zero drift by hand in 0c93659c; keep it there."""
        english = msgids(EN_GB)
        german = msgids("resource.language.de_de")
        drifted = sorted(i for i in set(english) & set(german)
                         if english[i] != german[i])
        self.assertEqual([], drifted, "German msgids have drifted from en_gb again")

    def test_the_drift_baselines_are_not_stale(self):
        """
        A translator round has to shrink the recorded number with it, or these
        tests quietly stop protecting anything.
        """
        english = msgids(EN_GB)
        for language, allowed in sorted(KNOWN_MSGID_DRIFT.items()):
            with self.subTest(language=language):
                theirs = msgids(language)
                drifted = len([i for i in set(english) & set(theirs)
                               if english[i] != theirs[i]])
                self.assertEqual(allowed, drifted,
                                 "drift in {0} is now {1}, not the recorded {2} - "
                                 "update KNOWN_MSGID_DRIFT".format(
                                     language, drifted, allowed))

    def test_duplicate_ids_have_not_grown(self):
        """A repeated msgctxt id means one of the two entries is dead weight."""
        for language in language_dirs():
            with self.subTest(language=language):
                ids = all_ids(language)
                duplicates = {i for i in set(ids) if ids.count(i) > 1}
                allowed = KNOWN_DUPLICATE_IDS.get(language, set())
                self.assertEqual(set(), duplicates - allowed,
                                 "new duplicate ids in {0}".format(language))

    def test_english_has_no_duplicate_ids(self):
        ids = all_ids(EN_GB)
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_parser_joins_multi_line_entries(self):
        """
        Guards the check above. Reading only the first line of a multi-line
        msgid truncates it, which makes identical entries look drifted - that
        mistake is what originally hid the real state of these files.
        """
        english = msgids(EN_GB)
        multiline = [i for i, text in english.items() if len(text) > 200]
        self.assertTrue(multiline, "expected some long msgids in en_gb")
        for ident in multiline[:5]:
            with self.subTest(ident=ident):
                self.assertFalse(english[ident].endswith('"'))
