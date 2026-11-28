# coding=utf-8
"""
lib/updater.py - the self-update path.

This is the riskiest code in the addon: it downloads a zip, unpacks it over the
installed addon directory and restarts. The tests here cover the decision
("is this actually newer?"), the archive sanitising, and the major-change
detection that decides whether a Kodi restart has to be asked for.

Nothing here touches the network - requests is swapped for a fake.
"""

from __future__ import absolute_import

import os
import shutil
from zipfile import ZipFile

from kodienv import ENV

from lib import updater as updater_module
from lib.updater import (StableUpdater, Updater, UpdateCheckFailed, UpdateDownloadFailed,
                         UpdateUnpackFailed, get_digest, get_updater)

from .base import KodiTestCase

ADDON_XML_TPL = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<addon id="script.plexmod" name="Plex" version="{version}"\n'
                 '       provider-name="pannal">\n'
                 '    <requires>\n'
                 '        <import addon="xbmc.python" version="3.0.0"/>\n'
                 '    </requires>\n'
                 '    <news>{news}</news>\n'
                 '</addon>\n')


class FakeResponse(object):
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class FakeRequests(object):
    def __init__(self, response=None, raises=False):
        self.response = response
        self.raises = raises
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.raises:
            raise IOError("no network")
        return self.response


class RegistryTest(KodiTestCase):
    def test_the_three_update_sources_are_registered(self):
        self.assertIs(Updater, get_updater("beta"))
        self.assertIs(StableUpdater, get_updater("stable"))
        self.assertEqual("repository", get_updater("repository").mode)

    def test_an_unknown_mode_raises(self):
        with self.assertRaises(KeyError):
            get_updater("nonsense")

    def test_the_repository_updater_never_self_updates(self):
        """
        On a Kodi-repo install the addon must let Kodi do the updating; check()
        only nudges Kodi's own repo refresh and reports "nothing to do".
        """
        upd = get_updater("repository")(branch="develop_kodi21")
        self.assertFalse(upd.check("1.0.0"))
        self.assertTrue(ENV.builtin_called("UpdateAddonRepos"))
        self.assertTrue(ENV.builtin_called("UpdateLocalAddons"))


class UrlTest(KodiTestCase):
    def test_beta_urls_point_at_the_branch(self):
        upd = Updater(branch="develop_kodi21")
        self.assertIn("/develop_kodi21/addon.xml", upd.info_url)
        self.assertIn("pannal/plex-for-kodi", upd.info_url)

    def test_the_download_url_uses_a_pinned_ref_when_one_is_known(self):
        upd = Updater(branch="develop_kodi21")
        self.assertIn("refs/heads/develop_kodi21", upd.download_url)
        upd.remote_ref = "deadbeef"
        self.assertIn("archive/deadbeef.zip", upd.download_url)

    def test_stable_urls_are_versioned_and_kodi_named(self):
        upd = StableUpdater(branch="develop_kodi21")
        self.assertIn("/matrix/", upd.info_url)
        upd.remote_version = "2.0.0"
        self.assertIn("script.plexmod-2.0.0.zip", upd.download_url)

    def test_the_kodi18_branch_maps_to_leia(self):
        self.assertEqual("leia", StableUpdater(branch="addon_kodi18").kodi_ver_name)

    def test_the_archive_name_carries_the_remote_version(self):
        upd = Updater(branch="develop_kodi21")
        upd.remote_version = "2.0.1"
        self.assertEqual("script.plexmod-2.0.1.zip", upd.archive_name)
        self.assertTrue(upd.archive_path.endswith("script.plexmod-2.0.1.zip"))


class CheckTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_requests = updater_module.requests
        self.upd = Updater(branch="develop_kodi21")

    def tearDown(self):
        updater_module.requests = self._orig_requests
        KodiTestCase.tearDown(self)

    def remote(self, version, news="what's new"):
        updater_module.requests = FakeRequests(
            FakeResponse(ADDON_XML_TPL.format(version=version, news=news)))

    def test_a_newer_remote_version_is_offered(self):
        self.remote("2.0.1")
        self.assertEqual("2.0.1", self.upd.check("2.0.0"))
        self.assertEqual("2.0.1", self.upd.remote_version)
        self.assertFalse(self.upd.is_downgrade)

    def test_the_same_version_is_not_offered(self):
        self.remote("2.0.0")
        self.assertFalse(self.upd.check("2.0.0"))

    def test_an_older_remote_version_is_not_offered_by_default(self):
        self.remote("1.9.0")
        self.assertFalse(self.upd.check("2.0.0"))
        self.assertFalse(self.upd.is_downgrade)

    def test_an_older_remote_version_is_offered_when_downgrades_are_allowed(self):
        """Switching update source has to be able to move backwards."""
        self.remote("1.9.0")
        self.assertEqual("1.9.0", self.upd.check("2.0.0", allow_downgrade=True))
        self.assertTrue(self.upd.is_downgrade)

    def test_allow_downgrade_still_does_not_re_offer_the_same_version(self):
        self.remote("2.0.0")
        self.assertFalse(self.upd.check("2.0.0", allow_downgrade=True))

    def test_a_prerelease_remote_is_older_than_the_release(self):
        self.remote("2.0.0~beta1")
        self.assertFalse(self.upd.check("2.0.0"))

    def test_moving_from_a_prerelease_to_the_release_is_an_update(self):
        self.remote("2.0.0")
        self.assertEqual("2.0.0", self.upd.check("2.0.0~beta1"))

    def test_the_changelog_is_captured(self):
        self.remote("2.0.1", news="  fixed things  ")
        self.upd.check("2.0.0")
        self.assertEqual("fixed things", self.upd.remote_changelog)

    def test_the_downgrade_flag_is_cleared_at_the_start_of_every_check(self):
        self.remote("1.9.0")
        self.upd.check("2.0.0", allow_downgrade=True)
        self.assertTrue(self.upd.is_downgrade)
        self.remote("2.0.1")
        self.upd.check("2.0.0")
        self.assertFalse(self.upd.is_downgrade)

    def test_a_network_failure_is_reported_as_a_check_failure(self):
        updater_module.requests = FakeRequests(raises=True)
        with self.assertRaises(UpdateCheckFailed):
            self.upd.check("2.0.0")

    def test_an_unparseable_response_is_reported_as_a_check_failure(self):
        updater_module.requests = FakeRequests(FakeResponse("<html>404</html>"))
        with self.assertRaises(UpdateCheckFailed):
            self.upd.check("2.0.0")

    def test_the_version_regex_needs_the_requires_block(self):
        """
        VERSION_RE anchors on <requires>, so a truncated or mangled addon.xml
        is treated as "no data" rather than yielding a bogus version.
        """
        updater_module.requests = FakeRequests(FakeResponse(
            '<addon id="script.plexmod" version="9.9.9"></addon>'))
        with self.assertRaises(UpdateCheckFailed):
            self.upd.check("2.0.0")

    def test_a_user_agent_is_sent(self):
        self.remote("2.0.1")
        self.upd.check("2.0.0")
        self.assertIn("User-Agent", updater_module.requests.calls[0][1]["headers"])


class DownloadTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_requests = updater_module.requests
        self.upd = Updater(branch="develop_kodi21")
        self.upd.remote_version = "2.0.1"

    def tearDown(self):
        updater_module.requests = self._orig_requests
        if os.path.exists(self.upd.archive_path):
            os.remove(self.upd.archive_path)
        KodiTestCase.tearDown(self)

    def test_an_already_downloaded_archive_is_reused(self):
        with open(self.upd.archive_path, "wb") as fp:
            fp.write(b"cached")
        updater_module.requests = FakeRequests(raises=True)
        self.assertEqual(self.upd.archive_path, self.upd.download())

    def test_a_network_failure_is_reported_as_a_download_failure(self):
        updater_module.requests = FakeRequests(raises=True)
        with self.assertRaises(UpdateDownloadFailed):
            self.upd.download()

    def test_a_non_200_carries_the_status_code(self):
        updater_module.requests = FakeRequests(FakeResponse(status_code=404))
        with self.assertRaises(UpdateDownloadFailed) as caught:
            self.upd.download()
        self.assertEqual(404, caught.exception.status_code)


def make_addon_zip(path, top="script.plexmod-develop_kodi21", extra=None,
                   service_body="pass\n"):
    """A GitHub-style source archive: everything under one top-level directory."""
    files = {
        "addon.xml": ADDON_XML_TPL.format(version="2.0.1", news="x"),
        "lib/service_runner.py": service_body,
        "lib/update_checker.py": "pass\n",
        "lib/updater.py": "pass\n",
        "lib/kodi_util.py": "pass\n",
        "lib/logging.py": "pass\n",
    }
    files.update(extra or {})
    with ZipFile(path, "w") as zf:
        for name, body in files.items():
            zf.writestr("{0}/{1}".format(top, name), body)
    return path


class UnpackTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.upd = Updater(branch="develop_kodi21")
        self.upd.remote_version = "2.0.1"
        make_addon_zip(self.upd.archive_path)

    def tearDown(self):
        self.upd.cleanup()
        KodiTestCase.tearDown(self)

    def test_the_top_level_directory_is_renamed_to_the_addon_id(self):
        dest = self.upd.unpack()
        self.assertTrue(dest.endswith("script.plexmod"))
        self.assertTrue(os.path.isdir(dest))
        self.assertTrue(os.path.exists(os.path.join(dest, "addon.xml")))

    def test_repository_metadata_is_stripped(self):
        """.github, .gitignore and .gitattributes must not land in an install."""
        make_addon_zip(self.upd.archive_path, extra={
            ".github/workflows/ci.yml": "on: push\n",
            ".gitignore": "*.pyc\n",
            ".gitattributes": "* text\n",
        })
        dest = self.upd.unpack()
        for name in (".github", ".gitignore", ".gitattributes"):
            with self.subTest(name=name):
                self.assertFalse(os.path.exists(os.path.join(dest, name)))
        self.assertTrue(os.path.exists(os.path.join(dest, "addon.xml")))

    def test_unpacking_twice_replaces_the_previous_extraction(self):
        first = self.upd.unpack()
        marker = os.path.join(first, "leftover.txt")
        with open(marker, "w", encoding="utf-8") as fp:
            fp.write("x")
        self.upd.unpack()
        self.assertFalse(os.path.exists(marker))

    def test_a_corrupt_archive_is_reported_as_an_unpack_failure(self):
        with open(self.upd.archive_path, "wb") as fp:
            fp.write(b"not a zip")
        with self.assertRaises(UpdateUnpackFailed):
            self.upd.unpack()

    def test_cleanup_removes_both_the_zip_and_the_extraction(self):
        extracted = self.upd.unpack()
        self.assertTrue(os.path.exists(self.upd.archive_path))
        self.upd.cleanup()
        self.assertFalse(os.path.exists(self.upd.archive_path))
        self.assertFalse(os.path.exists(os.path.dirname(extracted)))

    def test_cleanup_is_safe_to_call_twice(self):
        self.upd.unpack()
        self.upd.cleanup()
        self.upd.cleanup()


class MajorChangesTest(KodiTestCase):
    """
    A change to the service or updater needs a Kodi restart to take effect, and
    a changed language file needs one to reload strings; get_major_changes is
    what decides whether the user is asked.
    """

    def setUp(self):
        KodiTestCase.setUp(self)
        self.upd = Updater(branch="develop_kodi21")
        self.upd.remote_version = "2.0.1"
        self.installed = ENV.addon_info["path"]

    def tearDown(self):
        self.upd.cleanup()
        KodiTestCase.tearDown(self)

    def unpack_with(self, extra=None, service_body=None):
        installed_service = os.path.join(self.installed, "lib", "service_runner.py")
        with open(installed_service, "r", encoding="utf-8") as fp:
            current = fp.read()
        make_addon_zip(self.upd.archive_path,
                       service_body=current if service_body is None else service_body,
                       extra=extra)
        self.upd.unpack()

    def copy_installed(self, *relparts):
        """The installed copy of a file, verbatim, so digests match."""
        with open(os.path.join(self.installed, *relparts), "r", encoding="utf-8") as fp:
            return fp.read()

    def test_an_identical_service_file_is_not_a_major_change(self):
        self.unpack_with(extra={
            "lib/update_checker.py": self.copy_installed("lib", "update_checker.py"),
            "lib/updater.py": self.copy_installed("lib", "updater.py"),
            "lib/kodi_util.py": self.copy_installed("lib", "kodi_util.py"),
            "lib/logging.py": self.copy_installed("lib", "logging.py"),
        })
        self.assertNotIn("service", self.upd.get_major_changes())
        self.assertNotIn("updater", self.upd.get_major_changes())

    def test_a_changed_service_file_is_flagged(self):
        self.unpack_with(service_body="# changed\npass\n")
        self.assertIn("service", self.upd.get_major_changes())

    def test_a_changed_updater_dependency_is_flagged(self):
        self.unpack_with(extra={"lib/kodi_util.py": "# changed\n"})
        self.assertIn("updater", self.upd.get_major_changes())

    def test_a_changed_language_file_is_flagged(self):
        relpath = os.path.join("resources", "language", updater_module.LANGUAGE_RESOURCE,
                               "strings.po")
        if not os.path.exists(os.path.join(self.installed, relpath)):
            self.skipTest("no strings.po for {0}".format(updater_module.LANGUAGE_RESOURCE))
        self.unpack_with(extra={relpath.replace(os.sep, "/"): 'msgctxt "#32000"\n'})
        self.assertIn("language", self.upd.get_major_changes())

    def test_an_identical_language_file_is_not_flagged(self):
        relpath = os.path.join("resources", "language", updater_module.LANGUAGE_RESOURCE,
                               "strings.po")
        if not os.path.exists(os.path.join(self.installed, relpath)):
            self.skipTest("no strings.po for {0}".format(updater_module.LANGUAGE_RESOURCE))
        self.unpack_with(extra={
            relpath.replace(os.sep, "/"): self.copy_installed(relpath),
        })
        self.assertNotIn("language", self.upd.get_major_changes())


class DigestTest(KodiTestCase):
    def test_identical_content_hashes_alike(self):
        directory = self.mktemp()
        paths = []
        for name in ("a", "b"):
            path = os.path.join(directory, name)
            with open(path, "w", encoding="utf-8") as fp:
                fp.write("same content")
            paths.append(path)
        self.assertEqual(get_digest(paths[0]), get_digest(paths[1]))

    def test_different_content_hashes_differently(self):
        directory = self.mktemp()
        first = os.path.join(directory, "a")
        second = os.path.join(directory, "b")
        for path, body in ((first, "one"), (second, "two")):
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(body)
        self.assertNotEqual(get_digest(first), get_digest(second))

    def test_a_missing_file_digests_to_an_empty_string(self):
        """
        get_major_changes compares digests directly, so a missing file on
        either side has to be a *difference*, never an accidental match.
        """
        self.assertEqual("", get_digest(os.path.join(self.mktemp(), "absent")))


class InstallTest(KodiTestCase):
    def test_install_moves_the_tree_into_the_addons_directory(self):
        upd = Updater(branch="develop_kodi21")
        staged = self.mktemp("script.plexmod")
        with open(os.path.join(staged, "addon.xml"), "w", encoding="utf-8") as fp:
            fp.write(ADDON_XML_TPL.format(version="2.0.1", news="x"))

        dest = upd.install(staged)
        try:
            self.assertTrue(os.path.isdir(dest))
            self.assertTrue(os.path.exists(os.path.join(dest, "addon.xml")))
            self.assertFalse(os.path.exists(staged), "the staged copy is moved, not copied")
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def test_install_replaces_whatever_was_there(self):
        upd = Updater(branch="develop_kodi21")
        dest_parent = os.path.join(ENV.home_dir, "addons")
        existing = os.path.join(dest_parent, "script.plexmod")
        os.makedirs(existing)
        with open(os.path.join(existing, "stale.py"), "w", encoding="utf-8") as fp:
            fp.write("old")

        staged = self.mktemp("script.plexmod")
        with open(os.path.join(staged, "addon.xml"), "w", encoding="utf-8") as fp:
            fp.write("x")

        dest = upd.install(staged)
        try:
            self.assertFalse(os.path.exists(os.path.join(dest, "stale.py")))
        finally:
            shutil.rmtree(dest, ignore_errors=True)
