# coding=utf-8
"""p3i snapshots are optional; unavailable geometry retains marker protection."""
from __future__ import absolute_import

import json
from unittest.mock import patch

from kodienv import ENV
from lib import osd
from tests.base import KodiTestCase


WINDOW_ID = 0x10000 + 13001
CONTROL_ID = 791
PICTURE_LABEL = 'Player.Process(video.active.picture)'
BUTTON_LABEL = 'Control.GetRenderBounds({},{})'.format(WINDOW_ID, CONTROL_ID)


def picture(**changes):
    data = dict(version=1, valid=True, coordinate_system='gui-1080', width=1920, height=1080,
                left=0, top=140, right=1920, bottom=940)
    data.update(changes)
    return data


def button(**changes):
    data = picture(left=1500, top=800, right=1890, bottom=930)
    data.update(window_id=WINDOW_ID, control_id=CONTROL_ID, instance=42, visible=True)
    data.update(changes)
    return data


class MarkerGeometryTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.setSnapshots()

    def setSnapshots(self, active=None, rendered=None):
        ENV.infolabels[PICTURE_LABEL] = json.dumps(picture() if active is None else active)
        ENV.infolabels[BUTTON_LABEL] = json.dumps(button() if rendered is None else rendered)

    def needsOSD(self):
        return osd.markerNeedsOSD(WINDOW_ID, CONTROL_ID)

    def test_contained_and_equal_outer_edges_do_not_signal(self):
        self.assertFalse(self.needsOSD())
        self.setSnapshots(rendered=button(left=0, top=140, right=1920, bottom=940))
        self.assertFalse(self.needsOSD())

    def test_each_protruding_edge_signals_even_for_partial_overlap(self):
        for changes in ({'left': -0.01}, {'top': 139.99},
                        {'right': 1920.01}, {'bottom': 940.01}):
            with self.subTest(changes=changes):
                self.setSnapshots(rendered=button(**changes))
                self.assertTrue(self.needsOSD())

    def test_calibrated_bounds_outside_reference_canvas_are_not_clamped(self):
        self.setSnapshots(active=picture(left=-20, top=-10, right=1940, bottom=1090),
                          rendered=button(left=-15, top=-5, right=1930, bottom=1085))
        self.assertFalse(self.needsOSD())

    def test_missing_malformed_and_nonobject_labels_fall_back(self):
        for label in (PICTURE_LABEL, BUTTON_LABEL):
            for raw in ('', label, '{', 'null', '[]', 'true', '1'):
                with self.subTest(label=label, raw=raw):
                    self.setSnapshots()
                    ENV.infolabels[label] = raw
                    self.assertTrue(self.needsOSD())

    def test_invalid_schema_and_bounds_fall_back_for_either_snapshot(self):
        cases = [dict(version=2), dict(version=True), dict(version=1.0),
                 dict(coordinate_system='screen'), dict(width=3840), dict(height=2160),
                 dict(valid=False), dict(valid=1), dict(left=None), dict(left='0'),
                 dict(left=True), dict(top=float('nan')), dict(right=float('inf')),
                 dict(bottom=float('-inf')), dict(left=2000), dict(top=1000),
                 dict(left=1920, right=1920), dict(left=10 ** 400)]
        for label, build in ((PICTURE_LABEL, picture), (BUTTON_LABEL, button)):
            for changes in cases:
                with self.subTest(label=label, changes=changes):
                    self.setSnapshots()
                    ENV.infolabels[label] = json.dumps(build(**changes))
                    self.assertTrue(self.needsOSD())
            for field in picture():
                with self.subTest(label=label, missing=field):
                    self.setSnapshots()
                    data = build()
                    del data[field]
                    ENV.infolabels[label] = json.dumps(data)
                    self.assertTrue(self.needsOSD())

    def test_control_identity_and_visibility_must_match(self):
        cases = [dict(window_id=13001), dict(window_id=True), dict(control_id=792),
                 dict(control_id='791'), dict(instance=0), dict(instance=-1),
                 dict(instance=True), dict(visible=False), dict(visible=1)]
        for changes in cases:
            with self.subTest(changes=changes):
                self.setSnapshots(rendered=button(**changes))
                self.assertTrue(self.needsOSD())
        for field in ('window_id', 'control_id', 'instance', 'visible'):
            with self.subTest(missing=field):
                data = button()
                del data[field]
                self.setSnapshots(rendered=data)
                self.assertTrue(self.needsOSD())

    def test_fresh_reads_follow_geometry_invalidation_and_replacement(self):
        self.assertFalse(self.needsOSD())
        self.setSnapshots(rendered=button(bottom=960))
        self.assertTrue(self.needsOSD())
        self.setSnapshots(rendered=button(valid=False, left=None, top=None, right=None, bottom=None))
        self.assertTrue(self.needsOSD())
        self.setSnapshots(rendered=button(instance=43))
        self.assertFalse(self.needsOSD())
        ENV.infolabels[PICTURE_LABEL] = ''
        self.assertTrue(self.needsOSD(), 'never reuse the previous item\'s active bounds')

    def test_invalid_query_ids_and_getter_failure_fall_back(self):
        for window_id, control_id in ((None, 791), ('', 791), (True, 791), (0, 791),
                                     (0x80000000, 791), (WINDOW_ID, 0),
                                     (WINDOW_ID, 0x1000000), (WINDOW_ID, '791')):
            with self.subTest(window_id=window_id, control_id=control_id):
                self.assertTrue(osd.markerNeedsOSD(window_id, control_id))
        with patch.object(osd.xbmc, 'getInfoLabel', side_effect=RuntimeError('unavailable')):
            self.assertTrue(self.needsOSD())
