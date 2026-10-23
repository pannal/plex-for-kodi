# coding=utf-8
"""Run the Session over a recorded relay transcript (spec §testing strategy 1)."""

from __future__ import absolute_import

import json
import os
import unittest

from lib import syncplay

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "syncplay",
                       "transcript.json")


class TranscriptTest(unittest.TestCase):
    def test_session_conforms_to_recorded_relay_transcript(self):
        with open(FIXTURE, "r", encoding="utf-8") as fp:
            steps = json.load(fp)
        ident = syncplay.build_identity("zzzzzzzzzzzzzzzzzzzzzz", "Kodi", 1000001)
        room = "ca8cfezmke4"
        events = []
        sess = syncplay.Session(room, ident,
                                on_event=lambda kind, key: events.append((kind, key)))
        now = 100.0
        for i, step in enumerate(steps):
            now += 1.0
            raw = json.dumps(step["in"])
            raw = raw.replace("<IDENTITY>", json.dumps(ident)[1:-1]).replace("<ROOM>", room)
            sess.on_message(raw, now_mono=now)
            expect = step["expect"]
            if "remote_position" in expect:
                self.assertEqual(sess.remote["position"], expect["remote_position"],
                                 "step %d (%s): position" % (i, step["note"]))
                if isinstance(expect["remote_position"], float):
                    self.assertIsInstance(sess.remote["position"], float,
                                          "step %d: inbound position must be float" % i)
            if "remote_paused" in expect:
                self.assertEqual(sess.remote["paused"], expect["remote_paused"],
                                 "step %d: paused" % i)
            if "remote_do_seek" in expect:
                self.assertEqual(sess.remote["doSeek"], expect["remote_do_seek"],
                                 "step %d: doSeek" % i)
            if "relay_ignore" in expect:
                self.assertEqual(sess.relay_ignore, expect["relay_ignore"],
                                 "step %d (%s): relay_ignore" % (i, step["note"]))
            if "self_echo" in expect:
                self.assertEqual(sess.self_echo, expect["self_echo"],
                                 "step %d: self_echo" % i)
            if "roster_len" in expect:
                self.assertEqual(len(sess.roster), expect["roster_len"],
                                 "step %d: roster" % i)
            if "set_by_name" in expect:
                set_by = json.loads(syncplay.strip_identity(sess.remote["setBy"]))
                self.assertEqual(set_by["deviceName"], expect["set_by_name"])
            if "last_event" in expect:
                kind, key = events[-1]
                self.assertEqual(kind, expect["last_event"][0])
                parsed = json.loads(syncplay.strip_identity(key))
                self.assertEqual(parsed["deviceName"], expect["last_event"][1])

    def test_outbound_after_transcript_mirrors_counter(self):
        # §5.9: the stall killer is a client that keeps sending server: 0
        with open(FIXTURE, "r", encoding="utf-8") as fp:
            steps = json.load(fp)
        ident = syncplay.build_identity("dev", "K", 1)
        sess = syncplay.Session("ca8cfezmke4", ident)
        for step in steps:
            now = 100.0
            sess.on_message(json.dumps(step["in"])
                            .replace("<IDENTITY>", json.dumps(ident)[1:-1])
                            .replace("<ROOM>", "ca8cfezmke4"), now_mono=now)
        outbound = sess.outbound_state({"position": 100, "paused": True},
                                       now_mono=1.0, now_epoch=2.0)
        # last frame in the transcript sets no counter; the apply-ack step did
        self.assertEqual(outbound["State"]["ignoringOnTheFly"]["server"], 1)
