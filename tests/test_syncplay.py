# coding=utf-8
"""Tests for lib/syncplay.py — identity, builders, drift math, session.

Protocol references are docs/watch-together.md sections (§5.1 etc.)."""

from __future__ import absolute_import

import json
import unittest

from lib import syncplay


class IdentityTest(unittest.TestCase):
    def test_builds_compact_double_encodable_string(self):
        ident = syncplay.build_identity("dev-1234", "Kodi", 1000002)
        parsed = json.loads(ident)                 # the string itself is JSON
        self.assertEqual(parsed["deviceIdentifier"], "dev-1234")
        self.assertEqual(parsed["deviceName"], "Kodi")
        self.assertEqual(parsed["userID"], "1000002")

    def test_compact_separators(self):
        ident = syncplay.build_identity("d", "K", 1)
        self.assertNotIn(" ", ident, "relay echoes bytes as-is; stay compact (§5.1)")

    def test_numeric_user_id_becomes_string(self):
        ident = syncplay.build_identity("d", "K", 1000001)
        self.assertIn('"userID":"1000001"', ident)

    def test_rejects_identity_at_150_bytes(self):
        # 150+ bytes get blind-truncated mid-string by the relay (§5.1)
        with self.assertRaises(ValueError):
            syncplay.build_identity("device-identifier-1234567890",
                                    "way-too-long-device-name-for-the-150-byte"
                                    "-identity-cap-limit-pad",
                                    1000001)

    def test_short_device_name_fits(self):
        ident = syncplay.build_identity("device-identifier-1234567890", "Kodi", 1000001)
        self.assertLessEqual(len(ident.encode()), 149)

    def test_strip_identity_removes_collision_ladder_underscores(self):
        self.assertEqual(syncplay.strip_identity("abc_"), "abc")
        self.assertEqual(syncplay.strip_identity("abc___"), "abc")
        self.assertEqual(syncplay.strip_identity("abc"), "abc")
        self.assertEqual(syncplay.strip_identity(None), None)

    def test_is_self_matches_own_identity(self):
        ident = syncplay.build_identity("d", "Kodi", 1000001)
        self.assertTrue(syncplay.is_self(ident, ident))

    def test_is_self_survives_relay_appended_underscores(self):
        ident = syncplay.build_identity("d", "Kodi", 1000001)
        self.assertTrue(syncplay.is_self(ident + "__", ident))

    def test_is_self_survives_reordered_or_extended_setby(self):
        # twoclientprobe.py proved subset matching is what keeps self-ignore
        # alive across key reorder / extra fields / int-vs-str ids (§5.5)
        mine = json.dumps({"deviceIdentifier": "d", "deviceName": "Kodi",
                           "userID": "1000001"}, separators=(",", ":"))
        theirs = json.dumps({"userID": 1000001, "deviceIdentifier": "d",
                             "deviceName": "Kodi", "extra": "field"},
                            separators=(",", ":"))
        self.assertTrue(syncplay.is_self(theirs, mine))

    def test_is_self_rejects_other_identity(self):
        mine = syncplay.build_identity("d", "Kodi", 1000001)
        theirs = syncplay.build_identity("d", "Safari", 1000002)
        self.assertFalse(syncplay.is_self(theirs, mine))

    def test_is_self_rejects_none_and_garbage(self):
        ident = syncplay.build_identity("d", "K", 1)
        self.assertFalse(syncplay.is_self(None, ident))
        self.assertFalse(syncplay.is_self("not json", ident))
        self.assertFalse(syncplay.is_self(json.dumps(["list"]), ident))


class BuildersTest(unittest.TestCase):
    def test_hello_matches_wire_shape(self):
        ident = syncplay.build_identity("d", "K", 1)
        self.assertEqual(
            syncplay.hello("ca8cfezmke4", ident),
            {"Hello": {"room": {"name": "ca8cfezmke4"},
                       "username": ident,
                       "version": "1.6.4"}})

    def test_list_request(self):
        self.assertEqual(syncplay.list_request(), {"List": {}})

    def test_set_ready(self):
        self.assertEqual(
            syncplay.set_ready(True, manually_initiated=True),
            {"Set": {"ready": {"isReady": True, "manuallyInitiated": True}}})

    def test_set_file_double_encodes_uri(self):
        msg = syncplay.set_file("server://aaaa/com.plexapp.plugins.library/"
                                "library/metadata/227117")
        inner = json.loads(msg["Set"]["file"]["name"])   # name is a JSON string
        self.assertEqual(inner["uri"],
                         "server://aaaa/com.plexapp.plugins.library/"
                         "library/metadata/227117")
        self.assertEqual(inner["ads"], {"playing": False})

    def test_set_file_compact_inner(self):
        msg = syncplay.set_file("x")
        self.assertNotIn(" ", msg["Set"]["file"]["name"])

class LatencyTest(unittest.TestCase):
    def bootstrap(self, sr, lc, now):
        lat = syncplay.Latency()
        lat.on_state({"serverRtt": sr, "clientLatencyCalculation": lc}, now)
        return lat

    def test_first_sample_seeds_from_server_rtt(self):
        # §6.1: if averageRtt == 0: averageRtt = ping.serverRtt
        lat = self.bootstrap(sr=0.057, lc=100.0, now=100.1)
        expected_avg = 0.85 * 0.057 + 0.15 * 0.1
        self.assertAlmostEqual(lat.avg_rtt, expected_avg, places=6)
        expected = expected_avg / 2 + (0.1 - 0.057)   # sr < clientRtt -> skew add
        self.assertAlmostEqual(lat.forward_delay, expected, places=6)

    def test_no_skew_add_when_server_rtt_is_larger(self):
        lat = self.bootstrap(sr=3600.06, lc=100.0, now=100.1)
        self.assertAlmostEqual(lat.forward_delay, lat.avg_rtt / 2, places=6)

    def test_negative_client_rtt_sample_is_skipped(self):
        lat = syncplay.Latency()
        lat.on_state({"serverRtt": 0.05, "clientLatencyCalculation": 200.0}, 100.0)
        self.assertEqual(lat.client_rtt, 0.0, "clock ahead of sample: skip")
        self.assertEqual(lat.avg_rtt, 0.0)

    def test_negative_server_rtt_sample_is_skipped(self):
        lat = syncplay.Latency()
        lat.on_state({"serverRtt": -3599.94, "clientLatencyCalculation": 100.0},
                     100.1)
        self.assertEqual(lat.client_rtt, 0.0)

    def test_server_rtt_stored_for_outbound_echo_even_when_sample_skipped(self):
        lat = syncplay.Latency()
        lat.on_state({"serverRtt": -3599.94, "clientLatencyCalculation": 100.0},
                     100.1)
        self.assertEqual(lat.server_rtt, -3599.94)

    def test_missing_client_latency_calculation_updates_nothing(self):
        lat = syncplay.Latency()
        lat.on_state({"serverRtt": 0.2}, 100.0)
        self.assertEqual(lat.client_rtt, 0.0)
        self.assertEqual(lat.server_rtt, 0.2, "serverRtt is echoed back out (§5.5)")

    def test_ema_walk(self):
        lat = syncplay.Latency()
        lat.avg_rtt = 1.0
        lat.on_state({"serverRtt": 1.0, "clientLatencyCalculation": 0.0}, 2.0)
        self.assertAlmostEqual(lat.avg_rtt, 0.85 * 1.0 + 0.15 * 2.0, places=6)


class SyncActionTest(unittest.TestCase):
    def test_seeks_when_ahead_by_4_or_more(self):
        action = syncplay.sync_action(local_position=104.0,
                                      remote_position=100.0, paused=True,
                                      forward_delay=0.0)
        self.assertEqual(action, ("seek", 100.0))

    def test_seeks_when_behind_by_more_than_1_75(self):
        action = syncplay.sync_action(local_position=98.0,
                                      remote_position=100.0, paused=True,
                                      forward_delay=0.0)
        self.assertEqual(action, ("seek", 100.0))

    def test_boundary_1_75_exactly_seeks(self):
        action = syncplay.sync_action(local_position=98.25,
                                      remote_position=100.0, paused=True,
                                      forward_delay=0.0)
        self.assertEqual(action, ("seek", 100.0),
                         "diff == -1.75 hits the inclusive seek bound (§6.2)")

    def test_tempo_between_1_5_and_4(self):
        action = syncplay.sync_action(local_position=102.0,
                                      remote_position=100.0, paused=True,
                                      forward_delay=0.0)
        self.assertEqual(action, ("tempo", 0.95))

    def test_no_action_inside_drift_band(self):
        for local in (98.3, 99.0, 100.0, 101.4, 101.5):
            self.assertIsNone(
                syncplay.sync_action(local_position=local, remote_position=100.0,
                                     paused=True, forward_delay=0.0),
                "local=%r should be inside the band" % local)

    def test_playing_target_includes_forward_delay(self):
        # target = position + lastForwardDelay when not paused (§6.2)
        action = syncplay.sync_action(local_position=100.0,
                                      remote_position=100.0, paused=False,
                                      forward_delay=3.0)
        self.assertEqual(action, ("seek", 103.0),
                         "local - (remote+delay) = -3 -> seek to 103; "
                         "proves delay is in target")
        action = syncplay.sync_action(local_position=98.0,
                                      remote_position=100.0, paused=False,
                                      forward_delay=3.0)
        self.assertEqual(action, ("seek", 103.0),
                         "local - 103 = -5 -> seek to target 103")

    def test_paused_target_ignores_forward_delay(self):
        self.assertIsNone(syncplay.sync_action(local_position=100.0,
                                               remote_position=100.0, paused=True,
                                               forward_delay=3.0),
                          "paused target must ignore forward_delay")

class SessionTest(unittest.TestCase):
    def make(self):
        ident = syncplay.build_identity("dev-a", "Kodi", 1000001)
        self.events = []
        self.states = []
        self.rosters = []
        sess = syncplay.Session(
            room="ca8cfezmke4", identity=ident,
            on_state=self.states.append,
            on_roster=self.rosters.append,
            on_event=lambda kind, key: self.events.append((kind, key)))
        return sess, ident

    def test_outbound_state_shape(self):
        sess, _ = self.make()
        msg = sess.outbound_state({"position": 1804, "paused": False,
                                   "doSeek": True},
                                  now_mono=2755.552, now_epoch=1791143688.11)
        state = msg["State"]
        self.assertEqual(state["playstate"],
                         {"doSeek": True, "paused": False,
                          "position": 1804, "setBy": None})
        self.assertEqual(state["ping"]["clientLatencyCalculation"], 2755.552)
        self.assertEqual(state["ping"]["latencyCalculation"], 1791143688.11)
        self.assertEqual(state["ignoringOnTheFly"], {"client": 0, "server": 0})

    def test_outbound_position_is_int_even_for_float_local(self):
        sess, _ = self.make()
        msg = sess.outbound_state({"position": 1806.0028, "paused": False},
                                  now_mono=1.0, now_epoch=2.0)
        pos = msg["State"]["playstate"]["position"]
        self.assertIsInstance(pos, int)
        self.assertEqual(pos, 1806)

    def test_inbound_state_mirrors_relay_ignore_counter(self):
        # §5.9 — the one field that decides whether the relay keeps relaying
        sess, _ = self.make()
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.16},
            "playstate": {"position": 100.0, "paused": False,
                          "doSeek": False, "setBy": None},
            "ignoringOnTheFly": {"server": 1}}}, now_mono=10.0)
        self.assertEqual(sess.relay_ignore, 1)
        outbound = sess.outbound_state({"position": 100},
                                       now_mono=11.0, now_epoch=2.0)
        self.assertEqual(outbound["State"]["ignoringOnTheFly"]["server"], 1)

    def test_inbound_state_without_counter_leaves_relay_ignore_alone(self):
        sess, _ = self.make()
        sess.relay_ignore = 1
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.16},
            "playstate": {"position": 5.0, "paused": True,
                          "doSeek": False, "setBy": None}}}, now_mono=10.0)
        self.assertEqual(sess.relay_ignore, 1, "pure relay tick has no counter")

    def test_own_echo_is_counted_and_never_applied(self):
        # §5.5: applying your own echo pins you at a stale position
        sess, ident = self.make()
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.1},
            "playstate": {"position": 42.0, "paused": False, "doSeek": False,
                          "setBy": ident + "_"}}}, now_mono=5.0)
        self.assertEqual(sess.self_echo, 1)
        self.assertEqual(sess.remote["position"], 0.0)
        self.assertEqual(self.states, [])

    def test_remote_state_applied_as_float(self):
        sess, _ = self.make()
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.16},
            "playstate": {"position": 1806.0028346305862, "paused": False,
                          "doSeek": False,
                          "setBy": '{"deviceIdentifier":"other"}'}}},
            now_mono=5.0)
        self.assertEqual(sess.remote["position"], 1806.0028346305862)
        self.assertIsInstance(sess.remote["position"], float)
        self.assertEqual(len(self.states), 1)

    def test_doseek_frame_is_reported_to_consumer(self):
        sess, _ = self.make()
        sess.on_message({"State": {
            "ping": {"latencyCalculation": 1.0, "serverRtt": 0.1},
            "playstate": {"position": 900.0, "paused": False, "doSeek": True,
                          "setBy": '{"deviceIdentifier":"other"}'}}},
            now_mono=5.0)
        self.assertTrue(sess.remote["doSeek"])
        self.assertTrue(self.states[0]["doSeek"])

    def test_latency_uses_wall_now_when_not_given(self):
        sess, _ = self.make()
        sess.on_message(json.dumps({"State": {
            "ping": {"serverRtt": 0.2},
            "playstate": {"position": 0.0, "paused": True,
                          "doSeek": False, "setBy": None}}}))
        self.assertEqual(sess.latency.server_rtt, 0.2,
                         "str messages must parse (ws delivers str)")

    def test_list_populates_roster_keyed_by_room(self):
        sess, _ = self.make()
        sess.on_message({"List": {"ca8cfezmke4": {
            '{"deviceIdentifier":"d","deviceName":"K","userID":"1"}': {
                "position": 0, "file": {}, "controller": False,
                "isReady": None}}}})
        self.assertEqual(len(sess.roster), 1)
        self.assertEqual(self.rosters[0], sess.roster)

    def test_list_for_other_room_ignores(self):
        sess, _ = self.make()
        sess.on_message({"List": {"otherroom": {"x": {}}}})
        self.assertEqual(sess.roster, {})

    def test_list_extracts_the_rooms_current_file(self):
        # §5.4a/§5.8: a mid-session joiner reads the file from a peer's entry
        sess, _ = self.make()
        inner = json.dumps({"ads": {"playing": False},
                            "uri": "server://x/metadata/9"}, separators=(",", ":"))
        sess.on_message({"List": {"ca8cfezmke4": {
            "peer": {"position": 0, "file": {"name": inner}}}}})
        self.assertEqual(sess.file["uri"], "server://x/metadata/9")

    def test_non_object_file_payload_keeps_the_current_file(self):
        # §5.4a: a truncated/non-object peer frame must not wipe the room file
        sess, _ = self.make()
        sess.file = {"uri": "old"}
        sess.on_message({"Set": {"file": {"name": "123"}}})
        self.assertEqual(sess.file, {"uri": "old"})

    def test_unparseable_position_drops_the_whole_frame(self):
        # applying pause/seek with a stale position would move every peer to it
        sess, _ = self.make()
        sess.on_message({"State": {"playstate": {
            "position": "not-a-number", "paused": True,
            "setBy": '{"deviceIdentifier":"other"}'}}}, now_mono=5.0)
        self.assertEqual(sess.remote["position"], 0.0)
        self.assertEqual(self.states, [])

    def test_set_ready_updates_roster_entry(self):
        sess, ident = self.make()
        sess.roster[ident] = {"isReady": None}
        sess.on_message({"Set": {"ready": {"username": ident,
                                           "isReady": True,
                                           "manuallyInitiated": True}}})
        self.assertIs(sess.roster[ident]["isReady"], True)

    def test_set_ready_fires_on_ready(self):
        seen = []
        s = syncplay.Session("room", "me", on_ready=lambda k, v: seen.append((k, v)))
        s.on_message({"Set": {"ready": {"username": "u", "isReady": True}}})
        assert seen and seen[-1] == ("u", True)

    def test_ready_member_ids_and_members_ready(self):
        roster = {
            syncplay.build_identity("d", "n", 1): {"isReady": True},
            syncplay.build_identity("d", "n", 2): {"isReady": False},
        }
        assert syncplay.ready_member_ids(roster) == {"1"}
        assert syncplay.members_ready(["1"], roster) is True
        assert syncplay.members_ready(["1", "2"], roster) is False
        assert syncplay.members_ready(["3"], roster) is False

    def test_set_user_event_left_fires_and_drops_roster_entry(self):
        # §5.8 — transport death reaches peers in ~0.2 s as this event
        sess, _ = self.make()
        peer = '{"deviceIdentifier":"other","deviceName":"K","userID":"2"}'
        sess.roster[peer] = {"isReady": True}
        sess.on_message({"Set": {"user": {peer: {
            "room": {"name": "ca8cfezmke4"}, "event": {"left": True}}}}})
        self.assertEqual(self.events, [("left", peer)])
        self.assertNotIn(peer, sess.roster)

    def test_own_left_event_is_advisory_not_a_peer_departure(self):
        # §5.8: left against our own key is also the relay's silence-reap
        # signal — keep reading, do not drop ourselves or treat it as a leave
        sess, ident = self.make()
        sess.roster[ident] = {"isReady": True}
        sess.on_message({"Set": {"user": {ident: {
            "room": {"name": "ca8cfezmke4"}, "event": {"left": True}}}}})
        self.assertEqual(self.events, [])
        self.assertIn(ident, sess.roster)

    def test_set_user_event_joined_fires(self):
        sess, _ = self.make()
        sess.on_message({"Set": {"user": {"someone-else": {
            "room": {"name": "ca8cfezmke4"}, "event": {"joined": True}}}}})
        self.assertEqual(self.events, [("joined", "someone-else")])

    def test_set_user_file_arrives_double_encoded(self):
        # §10.2: a file change arrives as Set.user, not as Set.file
        sess, _ = self.make()
        inner = json.dumps({"ads": {"playing": False},
                            "uri": "server://x/metadata/1"}, separators=(",", ":"))
        sess.on_message({"Set": {"user": {"me": {"file": {"name": inner}}}}})
        self.assertEqual(sess.file["uri"], "server://x/metadata/1")

    def test_set_file_echo_also_updates(self):
        sess, _ = self.make()
        inner = json.dumps({"ads": {"playing": False}, "uri": "u"},
                           separators=(",", ":"))
        sess.on_message({"Set": {"file": {"name": inner}}})
        self.assertEqual(sess.file["uri"], "u")

    def test_hello_response_stored(self):
        sess, _ = self.make()
        sess.on_message({"Hello": {"version": "1.6.4", "realversion": "1.6.5",
                                   "features": {"readiness": True}}})
        self.assertEqual(sess.relay_hello["realversion"], "1.6.5")

    def test_garbage_messages_are_ignored(self):
        sess, _ = self.make()
        sess.on_message("not json at all")
        sess.on_message([1, 2, 3])
        sess.on_message({"unknown": {}})
        self.assertEqual(sess.remote["position"], 0.0)
