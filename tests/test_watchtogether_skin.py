# coding=utf-8
"""
Watch Together dialog templates - button geometry and focus navigation.

Kodi's grouplist hard-clips its children to the grouplist's own height (see the
comment in pre_play.xml.tpl), and the button texture
script.plex/buttons/blank.png is 180x145 sliced with border="50". A button
shorter than twice its border cannot be sliced at all, and a button taller than
its grouplist is clipped by the container.

Both WT dialogs shipped a vscale(90) button in a vscale(90) grouplist: the
Start/Cancel row was cut in half on a real TV, and (with no list<->button
navigation) the invite picker's OK/Cancel could not be reached with a remote.
"""

from __future__ import absolute_import

import os
import re
import struct

from .base import KodiTestCase
from . import REPO_ROOT

TEMPLATE_DIR = os.path.join(REPO_ROOT, "resources", "skins", "Main", "1080i", "templates")
BUTTON_TEXTURE = os.path.join(REPO_ROOT, "resources", "skins", "Main", "media",
                              "script.plex", "buttons", "blank.png")

BUTTON_RE = re.compile(r'<control type="button"[^>]*>(.*?)</control>', re.S)
# a grouplist's own properties live before its first child control
GROUPLIST_RE = re.compile(r'<control type="grouplist"[^>]*>(.*?)<control type="button"', re.S)
LIST_RE = re.compile(r'<control type="list"[^>]*>(.*?)</control>', re.S)
HEIGHT_RE = re.compile(r'<height>\{\{\s*vscale\((\d+)')
BORDER_RE = re.compile(r'border="(\d+)"')


def wt_templates():
    return sorted(os.path.join(TEMPLATE_DIR, fn)
                  for fn in os.listdir(TEMPLATE_DIR)
                  if fn.startswith("script-plex-watchtogether_") and fn.endswith(".xml.tpl"))


def png_height(path):
    with open(path, "rb") as fp:
        head = fp.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: {0}".format(path)
    return struct.unpack(">I", head[20:24])[0]


def read(path):
    with open(path, "r", encoding="utf-8") as fp:
        return fp.read()


class WatchTogetherButtonGeometryTest(KodiTestCase):
    def test_the_templates_are_actually_found(self):
        """A glob that matched nothing would make every test below vacuous."""
        self.assertEqual(4, len(wt_templates()))

    def test_buttons_fit_their_nine_slice(self):
        """A button shorter than 2x its texture border cannot be sliced."""
        for path in wt_templates():
            for block in BUTTON_RE.findall(read(path)):
                border = BORDER_RE.search(block)
                height = HEIGHT_RE.search(block)
                if not border or not height:
                    continue
                with self.subTest(template=os.path.basename(path), border=border.group(1)):
                    self.assertGreaterEqual(
                        int(height.group(1)), 2 * int(border.group(1)),
                        "button is shorter than twice its border - Kodi cannot "
                        "slice the texture and the row renders clipped")

    def test_the_row_is_not_shorter_than_its_buttons(self):
        """A grouplist hard-clips its children to its own height."""
        for path in wt_templates():
            text = read(path)
            group = GROUPLIST_RE.search(text)
            if not group:
                continue
            group_height = HEIGHT_RE.search(group.group(1))
            button_heights = [int(m.group(1)) for m in
                              (HEIGHT_RE.search(b) for b in BUTTON_RE.findall(text)) if m]
            if not group_height or not button_heights:
                continue
            with self.subTest(template=os.path.basename(path)):
                self.assertGreaterEqual(
                    int(group_height.group(1)), max(button_heights),
                    "the grouplist is shorter than its buttons, so it clips them")

    def test_buttons_are_tall_enough_for_the_real_texture(self):
        """Guards the numbers above against the actual asset."""
        self.assertGreaterEqual(png_height(BUTTON_TEXTURE), 100)

    def test_the_row_fits_three_buttons_at_their_minimum(self):
        """The widest row in these dialogs is Invite/Start/Cancel. Kodi sizes an
        auto button from its label and renders the text at textoffsetx inside
        that width, so a row that cannot hold three buttons at their minimum
        width squeezes them and the labels truncate to a couple of characters."""
        for path in wt_templates():
            text = read(path)
            group = GROUPLIST_RE.search(text)
            if not group:
                continue
            row = re.search(r"<width>(\d+)</width>", group.group(1))
            gap = re.search(r"<itemgap>(-?\d+)</itemgap>", group.group(1))
            mins = [int(m.group(1)) for m in
                    (re.search(r'<width min="(\d+)"', b) for b in BUTTON_RE.findall(text)) if m]
            if not (row and gap and mins):
                continue
            with self.subTest(template=os.path.basename(path)):
                self.assertGreaterEqual(
                    int(row.group(1)), 3 * max(mins) + 2 * int(gap.group(1)),
                    "the button row cannot hold three buttons at their minimum "
                    "width, so the grouplist squeezes them and labels truncate")

    def test_the_list_and_the_button_row_are_wired_together(self):
        """Every dialog with both a list and a button row must let a remote
        leave the list downwards, and come back up."""
        for path in wt_templates():
            text = read(path)
            listing = LIST_RE.search(text)
            group = GROUPLIST_RE.search(text)
            if not listing or not group:
                continue
            with self.subTest(template=os.path.basename(path)):
                self.assertIn("<ondown>", listing.group(1),
                              "the list has no <ondown>: its button row is unreachable")
                self.assertIn("<onup>", group.group(1),
                              "the button row has no <onup>: focus cannot return to the list")
