# coding=utf-8
"""
lib/localmode.py - "Go local": running against a LAN PMS with no plex.tv.

The dialog flow is the interesting part: a failed probe has to re-offer the
entry dialogs with the values prefilled, and "Add anyway" has to store the
server despite the failure. Those paths are hard to exercise by hand.
"""

from __future__ import absolute_import

import collections
import json

from kodienv import ENV

from lib import localmode
from lib import util

from .base import KodiTestCase


class FakeResponse(object):
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class FakeRequests(object):
    """Records every GET and answers from a scripted map of path -> response."""

    def __init__(self, responses=None, raise_on=()):
        self.responses = responses or {}
        self.raise_on = raise_on
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers or {}, timeout))
        for needle in self.raise_on:
            if needle in url:
                raise IOError("boom")
        for needle, response in self.responses.items():
            if url.endswith(needle):
                return response
        return FakeResponse(404)


class StoredServersTest(KodiTestCase):
    def test_nothing_stored(self):
        self.assertEqual([], localmode.getStoredServers())

    def test_round_trip(self):
        servers = [{"connection": "10.0.0.5", "port": 32400, "token": None, "name": "Tower"}]
        localmode.saveStoredServers(servers)
        self.assertEqual(servers, localmode.getStoredServers())

    def test_malformed_json_is_ignored(self):
        ENV.settings["local_servers_json"] = "{not json"
        self.assertEqual([], localmode.getStoredServers())

    def test_entries_without_a_connection_are_dropped(self):
        ENV.settings["local_servers_json"] = json.dumps([
            {"connection": "10.0.0.5"},
            {"name": "no connection"},
            "not even a dict",
            {},
        ])
        self.assertEqual([{"connection": "10.0.0.5"}], localmode.getStoredServers())

    def test_an_empty_setting_is_treated_as_an_empty_list(self):
        ENV.settings["local_servers_json"] = ""
        self.assertEqual([], localmode.getStoredServers())


class ProbeTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_requests = localmode.requests

    def tearDown(self):
        localmode.requests = self._orig_requests
        KodiTestCase.tearDown(self)

    def test_a_reachable_server_reports_its_friendly_name(self):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(200, b'<MediaContainer friendlyName="Tower"/>'),
        })
        self.assertEqual((True, "Tower", False), localmode.probe("10.0.0.5", 32400))

    def test_an_unreachable_server(self):
        localmode.requests = FakeRequests(raise_on=("/identity",))
        self.assertEqual((False, None, False), localmode.probe("10.0.0.5", 32400))

    def test_a_non_200_identity_means_not_a_pms(self):
        localmode.requests = FakeRequests({"/identity": FakeResponse(500)})
        self.assertEqual((False, None, False), localmode.probe("10.0.0.5", 32400))

    def test_a_401_on_the_root_flags_that_auth_is_needed(self):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(401),
        })
        self.assertEqual((True, None, True), localmode.probe("10.0.0.5", 32400))

    def test_a_403_on_the_root_also_flags_auth(self):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(403),
        })
        self.assertEqual((True, None, True), localmode.probe("10.0.0.5", 32400))

    def test_the_token_is_sent_as_a_plex_header(self):
        fake = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(200, b'<MediaContainer friendlyName="Tower"/>'),
        })
        localmode.requests = fake
        localmode.probe("10.0.0.5", 32400, token="secret")
        root_call = [call for call in fake.calls if call[0].endswith(":32400/")][0]
        self.assertEqual("secret", root_call[1].get("X-Plex-Token"))

    def test_no_token_means_no_token_header(self):
        fake = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(200, b'<MediaContainer friendlyName="Tower"/>'),
        })
        localmode.requests = fake
        localmode.probe("10.0.0.5", 32400)
        root_call = [call for call in fake.calls if call[0].endswith(":32400/")][0]
        self.assertNotIn("X-Plex-Token", root_call[1])

    def test_identity_ok_but_unparseable_root_still_counts_as_reachable(self):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(200, b"not xml at all"),
        })
        self.assertEqual((True, None, False), localmode.probe("10.0.0.5", 32400))

    def test_the_probe_timeout_is_applied(self):
        fake = FakeRequests({"/identity": FakeResponse(200)})
        localmode.requests = fake
        localmode.probe("10.0.0.5", 32400)
        self.assertEqual(localmode.PROBE_TIMEOUT, fake.calls[0][2])


class AddServerDialogTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_requests = localmode.requests

    def tearDown(self):
        localmode.requests = self._orig_requests
        KodiTestCase.tearDown(self)

    def reachable(self, name="Tower"):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(
                200, '<MediaContainer friendlyName="{0}"/>'.format(name).encode("utf-8")),
        })

    def answer(self, *values):
        ENV.dialog_answers = collections.deque(values)

    def test_a_successful_entry_stores_the_server(self):
        self.reachable()
        self.answer("10.0.0.5", "32400", "")
        self.assertTrue(localmode.addServerDialog())
        self.assertEqual([{"connection": "10.0.0.5", "port": 32400, "token": None,
                           "name": "Tower"}], localmode.getStoredServers())

    def test_an_empty_ip_cancels(self):
        self.answer("")
        self.assertFalse(localmode.addServerDialog())
        self.assertEqual([], localmode.getStoredServers())

    def test_an_empty_port_cancels(self):
        self.answer("10.0.0.5", "")
        self.assertFalse(localmode.addServerDialog())
        self.assertEqual([], localmode.getStoredServers())

    def test_an_entered_token_is_stored(self):
        self.reachable()
        self.answer("10.0.0.5", "32400", "sekrit")
        self.assertTrue(localmode.addServerDialog())
        self.assertEqual("sekrit", localmode.getStoredServers()[0]["token"])

    def test_a_failed_probe_offers_a_retry_that_can_succeed(self):
        localmode.requests = FakeRequests(raise_on=("/identity",))
        # first attempt fails -> "Try again" (1) -> second attempt succeeds
        self.answer("10.0.0.5", "32400", "", 1)

        original_probe = localmode.probe
        attempts = {"n": 0}

        def probe(ip, port, token=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return False, None, False
            return True, "Tower", False

        localmode.probe = probe
        try:
            ENV.dialog_answers = collections.deque(["10.0.0.5", "32400", "", 1,
                                                    "10.0.0.5", "32400", ""])
            self.assertTrue(localmode.addServerDialog())
        finally:
            localmode.probe = original_probe

        self.assertEqual(2, attempts["n"])
        self.assertEqual("Tower", localmode.getStoredServers()[0]["name"])

    def test_add_anyway_stores_an_unreachable_server(self):
        localmode.requests = FakeRequests(raise_on=("/identity",))
        # ip, port, token, then the custom button (2) == "Add anyway"
        self.answer("10.0.0.5", "32400", "", 2)
        self.assertTrue(localmode.addServerDialog())
        stored = localmode.getStoredServers()
        self.assertEqual(1, len(stored))
        self.assertIsNone(stored[0]["name"], "an unreachable server has no friendly name")

    def test_cancelling_the_failure_dialog_stores_nothing(self):
        localmode.requests = FakeRequests(raise_on=("/identity",))
        self.answer("10.0.0.5", "32400", "", 0)
        self.assertFalse(localmode.addServerDialog())
        self.assertEqual([], localmode.getStoredServers())

    def test_re_adding_the_same_host_replaces_rather_than_duplicates(self):
        self.reachable("First")
        self.answer("10.0.0.5", "32400", "")
        localmode.addServerDialog()

        self.reachable("Second")
        self.answer("10.0.0.5", "32400", "")
        localmode.addServerDialog()

        stored = localmode.getStoredServers()
        self.assertEqual(1, len(stored))
        self.assertEqual("Second", stored[0]["name"])

    def test_a_different_host_is_appended(self):
        self.reachable("First")
        self.answer("10.0.0.5", "32400", "")
        localmode.addServerDialog()

        self.reachable("Second")
        self.answer("10.0.0.6", "32400", "")
        localmode.addServerDialog()

        self.assertEqual(["10.0.0.5", "10.0.0.6"],
                         [s["connection"] for s in localmode.getStoredServers()])

    def test_an_auth_required_server_gets_an_explanation_dialog(self):
        localmode.requests = FakeRequests({
            "/identity": FakeResponse(200),
            ":32400/": FakeResponse(401),
        })
        self.answer("10.0.0.5", "32400", "")
        self.assertTrue(localmode.addServerDialog())
        self.assertIn("ok", [call[0] for call in ENV.dialog_calls])

    def test_the_port_is_stored_as_an_int(self):
        self.reachable()
        self.answer("10.0.0.5", "32400", "")
        localmode.addServerDialog()
        self.assertIsInstance(localmode.getStoredServers()[0]["port"], int)


class OfferAndBootstrapTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_add = localmode.addServerDialog

    def tearDown(self):
        localmode.addServerDialog = self._orig_add
        KodiTestCase.tearDown(self)

    def test_declining_the_offer_does_not_open_the_entry_dialog(self):
        called = []
        localmode.addServerDialog = lambda: called.append(True) or True
        ENV.dialog_answers = collections.deque([False])
        self.assertFalse(localmode.offerServerIfNoneFound())
        self.assertEqual([], called)

    def test_accepting_the_offer_opens_the_entry_dialog(self):
        localmode.addServerDialog = lambda: True
        ENV.dialog_answers = collections.deque([True])
        self.assertTrue(localmode.offerServerIfNoneFound())

    def test_bootstrap_sets_the_local_mode_setting_on_success(self):
        localmode.addServerDialog = lambda: True
        self.assertTrue(localmode.bootstrap())
        self.assertIs(True, util.getSetting("local_mode", False))

    def test_bootstrap_leaves_local_mode_off_when_entry_is_cancelled(self):
        localmode.addServerDialog = lambda: False
        self.assertFalse(localmode.bootstrap())
        self.assertIs(False, util.getSetting("local_mode", False))


class FakeConnection(object):
    def __init__(self, address="http://10.0.0.5:32400"):
        self.address = address


class FakeServer(object):
    def __init__(self, uuid="uuid-1", name="Tower", address="http://10.0.0.5:32400"):
        self.uuid = uuid
        self.name = name
        self.activeConnection = FakeConnection(address)


class FakeServerManager(object):
    def __init__(self, server=None):
        self.selectedServer = server


class SelectedProfilesTest(KodiTestCase):
    def test_nothing_stored_is_none_rather_than_empty(self):
        # None means "never asked"; [] means "asked, user picked nobody"
        self.assertIsNone(localmode.getSelectedProfiles())

    def test_round_trip(self):
        localmode.saveSelectedProfiles(["1", "7"])
        self.assertEqual(["1", "7"], localmode.getSelectedProfiles())

    def test_an_empty_selection_is_remembered_as_empty(self):
        localmode.saveSelectedProfiles([])
        self.assertEqual([], localmode.getSelectedProfiles())

    def test_malformed_json_is_treated_as_never_asked(self):
        ENV.settings["local_profiles_json"] = "{not json"
        self.assertIsNone(localmode.getSelectedProfiles())

    def test_a_non_list_is_treated_as_never_asked(self):
        ENV.settings["local_profiles_json"] = '"nope"'
        self.assertIsNone(localmode.getSelectedProfiles())


class ValidateProfileTokenTest(KodiTestCase):
    """
    A LAN-trusting PMS ignores unknown tokens instead of rejecting them, so the
    owner-only /myplex/account endpoint is what actually discriminates: real
    managed-user tokens get a 403 there, bogus and owner tokens get a 200.
    """

    def setUp(self):
        KodiTestCase.setUp(self)
        self._orig_requests = localmode.requests

    def tearDown(self):
        localmode.requests = self._orig_requests
        KodiTestCase.tearDown(self)

    def respond(self, root=200, myplex=200):
        localmode.requests = FakeRequests({
            "/myplex/account": FakeResponse(myplex),
            ":32400/": FakeResponse(root),
        })

    def test_a_managed_token_for_a_managed_profile_is_accepted(self):
        self.respond(root=200, myplex=403)
        self.assertEqual((True, False),
                         localmode.validateProfileToken(FakeServer(), "tok", False))

    def test_an_owner_token_for_the_owner_profile_is_accepted(self):
        self.respond(root=200, myplex=200)
        self.assertEqual((True, False),
                         localmode.validateProfileToken(FakeServer(), "tok", True))

    def test_an_owner_or_bogus_token_for_a_managed_profile_is_a_mismatch(self):
        self.respond(root=200, myplex=200)
        self.assertEqual((True, True),
                         localmode.validateProfileToken(FakeServer(), "tok", False))

    def test_a_managed_token_for_the_owner_profile_is_a_mismatch(self):
        self.respond(root=200, myplex=403)
        self.assertEqual((True, True),
                         localmode.validateProfileToken(FakeServer(), "tok", True))

    def test_a_rejected_token_is_not_reachable(self):
        self.respond(root=401)
        self.assertEqual((False, False),
                         localmode.validateProfileToken(FakeServer(), "tok", False))

    def test_a_dead_server_is_not_reachable(self):
        localmode.requests = FakeRequests(raise_on=(":32400/",))
        self.assertEqual((False, False),
                         localmode.validateProfileToken(FakeServer(), "tok", False))

    def test_a_server_without_an_active_connection_is_not_reachable(self):
        server = FakeServer()
        server.activeConnection = None
        self.assertEqual((False, False),
                         localmode.validateProfileToken(server, "tok", False))

    def test_the_token_is_sent_as_a_header(self):
        self.respond(root=200, myplex=403)
        localmode.validateProfileToken(FakeServer(), "sekrit", False)
        self.assertTrue(all(call[1].get("X-Plex-Token") == "sekrit"
                            for call in localmode.requests.calls))


class ChooseProfilesTest(KodiTestCase):
    ACCOUNTS = [{"id": "1", "name": "owner", "thumb": ""},
                {"id": "7", "name": "kid", "thumb": ""},
                {"id": "9", "name": "friend", "thumb": ""}]

    def test_the_picked_ids_are_stored(self):
        ENV.dialog_answers = collections.deque([[0, 1]])
        self.assertEqual(["1", "7"], localmode.chooseProfiles(FakeServer(), self.ACCOUNTS))
        self.assertEqual(["1", "7"], localmode.getSelectedProfiles())

    def test_cancelling_stores_nothing(self):
        ENV.dialog_answers = collections.deque([None])
        self.assertIsNone(localmode.chooseProfiles(FakeServer(), self.ACCOUNTS))
        self.assertIsNone(localmode.getSelectedProfiles())

    def test_picking_nobody_is_stored_as_an_empty_selection(self):
        ENV.dialog_answers = collections.deque([[]])
        self.assertEqual([], localmode.chooseProfiles(FakeServer(), self.ACCOUNTS))
        self.assertEqual([], localmode.getSelectedProfiles())

    def test_every_account_is_offered_with_the_previous_selection_preselected(self):
        localmode.saveSelectedProfiles(["9"])
        ENV.dialog_answers = collections.deque([[2]])
        localmode.chooseProfiles(FakeServer(), self.ACCOUNTS)
        call = [c for c in ENV.dialog_calls if c[0] == "multiselect"][0]
        self.assertEqual(["owner", "kid", "friend"], call[1][1])
        self.assertEqual([2], call[2]["preselect"], "the stored id maps back to its index")

    def test_no_accounts_means_no_dialog(self):
        self.assertIsNone(localmode.chooseProfiles(FakeServer(), []))
        self.assertEqual([], ENV.dialog_calls)


class ProfileTokenPromptTest(KodiTestCase):
    """
    Account-less local mode: a profile only becomes a real identity once a server
    token is stored for it, so the prompt has to persist both the token and the
    fact that it already asked.
    """

    def setUp(self):
        KodiTestCase.setUp(self)
        from .base import ensure_plex_interface
        ensure_plex_interface()
        from plexnet import plexapp, myplexaccount
        self.plexapp = plexapp
        self._orig = (plexapp.ACCOUNT, plexapp.SERVERMANAGER, plexapp.util.ACCOUNT,
                      plexapp.util.LOCAL_MODE, localmode.requests)
        self.account = myplexaccount.MyPlexAccount()
        self.account.isSignedIn = False
        self.account.authToken = None
        plexapp.ACCOUNT = self.account
        plexapp.util.ACCOUNT = self.account
        plexapp.util.LOCAL_MODE = True
        self.server = FakeServer()
        plexapp.SERVERMANAGER = FakeServerManager(self.server)
        self.user = myplexaccount.HomeUser({"id": "7", "title": "kid"})

    def tearDown(self):
        (self.plexapp.ACCOUNT, self.plexapp.SERVERMANAGER, self.plexapp.util.ACCOUNT,
         self.plexapp.util.LOCAL_MODE, localmode.requests) = self._orig
        KodiTestCase.tearDown(self)

    def accept(self):
        localmode.requests = FakeRequests({"/myplex/account": FakeResponse(403),
                                           ":32400/": FakeResponse(200)})

    def test_a_profile_without_a_token_needs_one(self):
        self.assertTrue(localmode.needsProfileToken(self.user))

    def test_a_signed_in_account_never_prompts(self):
        self.account.isSignedIn = True
        self.assertFalse(localmode.needsProfileToken(self.user))

    def test_a_local_mode_account_with_a_plex_tv_token_never_prompts(self):
        self.account.authToken = "harvested"
        self.assertFalse(localmode.needsProfileToken(self.user))

    def test_an_accepted_token_is_stored_for_this_server(self):
        self.accept()
        ENV.dialog_answers = collections.deque(["sekrit"])
        self.assertEqual("sekrit", localmode.promptProfileToken(self.user))
        stored = self.account.loadLocalUsers()["7"]
        self.assertEqual({self.server.uuid: "sekrit"}, stored["serverTokens"])

    def test_a_stored_token_means_no_further_prompting(self):
        self.accept()
        ENV.dialog_answers = collections.deque(["sekrit"])
        localmode.promptProfileToken(self.user)
        self.assertFalse(localmode.needsProfileToken(self.user))

    def test_skipping_the_prompt_is_remembered_so_it_does_not_nag(self):
        ENV.dialog_answers = collections.deque([""])
        self.assertIsNone(localmode.promptProfileToken(self.user))
        self.assertFalse(localmode.needsProfileToken(self.user))
        self.assertNotIn("serverTokens", self.account.loadLocalUsers()["7"])

    def test_a_mismatched_token_can_be_retried(self):
        # owner token offered for a managed profile -> mismatch -> "Try again" -> accepted
        localmode.requests = FakeRequests({"/myplex/account": FakeResponse(200),
                                           ":32400/": FakeResponse(200)})
        calls = {"n": 0}
        original = localmode.validateProfileToken

        def validate(server, token, isOwnerProfile):
            calls["n"] += 1
            return (True, True) if calls["n"] == 1 else (True, False)

        localmode.validateProfileToken = validate
        try:
            ENV.dialog_answers = collections.deque(["wrong", True, "right"])
            self.assertEqual("right", localmode.promptProfileToken(self.user))
        finally:
            localmode.validateProfileToken = original
        self.assertEqual(2, calls["n"])

    def test_giving_up_after_a_failure_stores_no_token(self):
        localmode.requests = FakeRequests({"/myplex/account": FakeResponse(200),
                                           ":32400/": FakeResponse(200)})
        ENV.dialog_answers = collections.deque(["wrong", False])
        self.assertIsNone(localmode.promptProfileToken(self.user))
        self.assertNotIn("serverTokens", self.account.loadLocalUsers()["7"])

    def test_tokens_for_other_servers_survive(self):
        self.account.cacheLocalUser("7", serverTokens={"other-uuid": "keep-me"})
        self.accept()
        ENV.dialog_answers = collections.deque(["sekrit"])
        localmode.promptProfileToken(self.user)
        self.assertEqual({"other-uuid": "keep-me", self.server.uuid: "sekrit"},
                         self.account.loadLocalUsers()["7"]["serverTokens"])


class SeedUsersFromServerTest(KodiTestCase):
    """
    /accounts lists every account the PMS ever tracked - home users and shared
    users alike, with nothing in the payload telling them apart - so the user
    curates the list once and the choice is remembered.
    """

    ACCOUNTS_XML = (b'<MediaContainer size="4">'
                    b'<Account id="0" name=""/>'
                    b'<Account id="1" name="owner"/>'
                    b'<Account id="7" name="kid"/>'
                    b'<Account id="9" name="friend"/>'
                    b'</MediaContainer>')

    def setUp(self):
        KodiTestCase.setUp(self)
        from .base import ensure_plex_interface
        ensure_plex_interface()
        from plexnet import plexapp, myplexaccount
        self.plexapp = plexapp
        self._orig = (plexapp.ACCOUNT, plexapp.SERVERMANAGER, plexapp.util.ACCOUNT,
                      plexapp.util.LOCAL_MODE, localmode.fetchAccounts)
        self.account = myplexaccount.MyPlexAccount()
        self.account.isSignedIn = False
        self.account.authToken = None
        self.account.homeUsers = []
        self.account.ID = None
        plexapp.ACCOUNT = self.account
        plexapp.util.ACCOUNT = self.account
        plexapp.util.LOCAL_MODE = True
        self.server = FakeServer()
        plexapp.SERVERMANAGER = FakeServerManager(self.server)
        localmode.fetchAccounts = lambda server: [
            {"id": "1", "name": "owner", "thumb": ""},
            {"id": "7", "name": "kid", "thumb": ""},
            {"id": "9", "name": "friend", "thumb": ""}]

    def tearDown(self):
        (self.plexapp.ACCOUNT, self.plexapp.SERVERMANAGER, self.plexapp.util.ACCOUNT,
         self.plexapp.util.LOCAL_MODE, localmode.fetchAccounts) = self._orig
        KodiTestCase.tearDown(self)

    def test_the_pseudo_account_is_dropped_when_parsing(self):
        from plexnet import plexrequest
        localmode.fetchAccounts = self._orig[4]

        class FakeRequest(object):
            def __init__(self, server, path):
                pass

            def getToStringWithTimeout(self, timeout):
                return SeedUsersFromServerTest.ACCOUNTS_XML

        original = plexrequest.PlexRequest
        plexrequest.PlexRequest = FakeRequest
        try:
            accounts = localmode.fetchAccounts(self.server)
        finally:
            plexrequest.PlexRequest = original
        self.assertEqual(["1", "7", "9"], [a["id"] for a in accounts])

    def test_the_first_run_asks_which_users_to_keep(self):
        ENV.dialog_answers = collections.deque([[0, 1]])
        localmode.seedUsersFromServer(self.server)
        self.assertEqual(["owner", "kid"], [u.title for u in self.account.homeUsers])

    def test_the_stored_selection_is_reused_without_asking_again(self):
        localmode.saveSelectedProfiles(["9"])
        localmode.seedUsersFromServer(self.server)
        self.assertEqual(["friend"], [u.title for u in self.account.homeUsers])
        self.assertEqual([], ENV.dialog_calls, "no dialog on subsequent starts")

    def test_declining_the_first_run_is_remembered_as_no_profiles(self):
        ENV.dialog_answers = collections.deque([None])
        localmode.seedUsersFromServer(self.server)
        self.assertEqual([], self.account.homeUsers)
        self.assertEqual([], localmode.getSelectedProfiles(),
                         "so the picker does not reappear on every start")

    def test_reselect_reopens_the_picker_even_with_users_present(self):
        localmode.saveSelectedProfiles(["1"])
        localmode.seedUsersFromServer(self.server)
        ENV.dialog_answers = collections.deque([[1, 2]])
        localmode.seedUsersFromServer(self.server, reselect=True)
        self.assertEqual(["kid", "friend"], [u.title for u in self.account.homeUsers])

    def test_cancelling_a_reselect_keeps_the_previous_selection(self):
        localmode.saveSelectedProfiles(["1"])
        ENV.dialog_answers = collections.deque([None])
        localmode.seedUsersFromServer(self.server, reselect=True)
        self.assertEqual(["1"], localmode.getSelectedProfiles())

    def test_a_signed_in_account_is_never_seeded(self):
        self.account.isSignedIn = True
        localmode.seedUsersFromServer(self.server)
        self.assertEqual([], self.account.homeUsers)

    def test_the_owner_profile_is_marked_admin(self):
        localmode.saveSelectedProfiles(["1", "7"])
        localmode.seedUsersFromServer(self.server)
        byName = dict((u.title, u) for u in self.account.homeUsers)
        self.assertTrue(byName["owner"].isAdmin)
        self.assertFalse(byName["kid"].isAdmin)

    def test_the_current_id_follows_the_seeded_users(self):
        localmode.saveSelectedProfiles(["7"])
        localmode.seedUsersFromServer(self.server)
        self.assertEqual("7", self.account.ID)
        self.assertEqual("kid", self.account.title)

    def test_a_still_valid_id_is_kept(self):
        localmode.saveSelectedProfiles(["1", "7"])
        self.account.ID = "7"
        self.account.title = "kid"
        localmode.seedUsersFromServer(self.server)
        self.assertEqual("7", self.account.ID)


class AccountLessSwitchTest(KodiTestCase):
    """
    Switching in account-less local mode: there is no plex.tv token to validate,
    so the switch has to adopt the profile and announce itself.
    """

    def setUp(self):
        KodiTestCase.setUp(self)
        from .base import ensure_plex_interface
        ensure_plex_interface()
        from plexnet import plexapp, myplexaccount
        self.plexapp = plexapp
        self.myplexaccount = myplexaccount
        self._orig = (plexapp.ACCOUNT, plexapp.util.ACCOUNT, plexapp.util.LOCAL_MODE,
                      plexapp.refreshResources)
        plexapp.refreshResources = lambda force=False: None
        self.account = myplexaccount.MyPlexAccount()
        self.account.isSignedIn = False
        self.account.isOffline = True
        self.account.authToken = None
        self.account.ID = "1"
        self.account.title = "owner"
        self.account.homeUsers = [
            myplexaccount.HomeUser({"id": "1", "title": "owner"}),
            myplexaccount.HomeUser({"id": "7", "title": "kid"})]
        for user in self.account.homeUsers:
            user.isAdmin = user.id == "1"
            user.isManaged = False
            user.isProtected = False
        plexapp.ACCOUNT = self.account
        plexapp.util.ACCOUNT = self.account
        plexapp.util.LOCAL_MODE = True

    def tearDown(self):
        (self.plexapp.ACCOUNT, self.plexapp.util.ACCOUNT, self.plexapp.util.LOCAL_MODE,
         self.plexapp.refreshResources) = self._orig
        KodiTestCase.tearDown(self)

    def test_switching_adopts_the_profile_without_a_plex_tv_token(self):
        self.assertTrue(self.account.switchHomeUser("7"))
        self.assertEqual("7", self.account.ID)
        self.assertEqual("kid", self.account.title)

    def test_the_switch_flag_is_set_so_callers_see_a_real_switch(self):
        self.account.switchHomeUser("7")
        self.assertTrue(self.account.switchUser)

    def test_the_profiles_server_token_becomes_the_identity(self):
        self.account.cacheLocalUser("7", serverTokens={"uuid-1": "kid-token"})
        self.account.switchHomeUser("7")
        self.assertEqual({"uuid-1": "kid-token"}, self.account.serverTokens)

    def test_switching_to_a_profile_without_a_token_clears_the_previous_one(self):
        self.account.cacheLocalUser("1", serverTokens={"uuid-1": "owner-token"})
        self.account.switchHomeUser("1")
        self.account.switchHomeUser("7")
        self.assertEqual({}, self.account.serverTokens,
                         "otherwise the new user would keep browsing as the old one")

    def test_a_user_change_is_announced(self):
        seen = []

        def listener(account=None, reallyChanged=False, **kwargs):
            seen.append(reallyChanged)

        self.plexapp.util.APP.on("change:user", listener)
        try:
            self.account.switchHomeUser("7")
        finally:
            self.plexapp.util.APP.off("change:user", listener)
        self.assertEqual([True], seen, "so the server manager re-selects for the new user")


class FreshAccountTest(KodiTestCase):
    """
    A brand new install that goes straight into account-less local mode has no
    saved account state at all - every attribute the offline paths touch has to
    exist without plex.tv ever having answered.
    """

    def test_setLocal_works_on_an_account_that_never_saw_plex_tv(self):
        from .base import ensure_plex_interface
        ensure_plex_interface()
        from plexnet import myplexaccount

        account = myplexaccount.MyPlexAccount()
        account.setLocal()

        self.assertTrue(account.isOffline)
        self.assertFalse(account.isSignedIn)
        self.assertTrue(account.isAuthenticated, "an unprotected lone user is authenticated")

    def test_an_unprotected_account_is_the_default(self):
        from .base import ensure_plex_interface
        ensure_plex_interface()
        from plexnet import myplexaccount

        self.assertFalse(myplexaccount.MyPlexAccount().isProtected)


class InsecureConnectionsTest(KodiTestCase):
    """
    Local mode reaches the server over plain HTTP. With "allow insecure connections"
    at its default of never those connections are parked as STATE_INSECURE and the
    fallback round never runs, which presents as "no server found".
    """

    def setUp(self):
        KodiTestCase.setUp(self)
        from .base import ensure_plex_interface
        ensure_plex_interface()

    def test_going_local_allows_insecure_connections(self):
        self.assertTrue(localmode.ensureInsecureConnectionsAllowed(warn=False))
        self.assertEqual("always", util.getSetting("allow_insecure", "never"))

    def test_the_user_is_told_the_server_needs_the_same_treatment(self):
        localmode.ensureInsecureConnectionsAllowed()
        self.assertIn("ok", [call[0] for call in ENV.dialog_calls])

    def test_an_already_permissive_setting_is_left_alone_and_does_not_warn(self):
        ENV.settings["allow_insecure"] = "always"
        self.assertFalse(localmode.ensureInsecureConnectionsAllowed())
        self.assertEqual([], ENV.dialog_calls)

    def test_same_network_is_not_enough_and_gets_upgraded(self):
        # same_network leans on plex.tv's sameNetwork flag, which local mode never has
        ENV.settings["allow_insecure"] = "same_network"
        self.assertTrue(localmode.ensureInsecureConnectionsAllowed(warn=False))
        self.assertEqual("always", util.getSetting("allow_insecure", "never"))

    def test_the_change_is_announced_so_the_server_manager_retests(self):
        from plexnet import util as pnUtil
        seen = []

        def listener(value=None, **kwargs):
            seen.append(value)

        pnUtil.APP.on("change:allow_insecure", listener)
        try:
            localmode.ensureInsecureConnectionsAllowed(warn=False)
        finally:
            pnUtil.APP.off("change:allow_insecure", listener)
        self.assertEqual(["always"], seen)

    def test_the_bootstrap_allows_them_too(self):
        original = localmode.addServerDialog
        localmode.addServerDialog = lambda: True
        try:
            localmode.bootstrap()
        finally:
            localmode.addServerDialog = original
        self.assertEqual("always", util.getSetting("allow_insecure", "never"))
