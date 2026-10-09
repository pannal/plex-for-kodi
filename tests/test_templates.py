# coding=utf-8
"""
The .xml.tpl skin templates.

These are the highest-value tests in the suite: the generated
resources/skins/Main/1080i/*.xml files are gitignored and only produced on a
real device at addon start, so a template that renders to broken XML - or not
at all - currently shows up as a blank or missing window on someone's TV
rather than as a failure here.

Everything renders into a temp directory. Nothing in the working tree is
written to.
"""

from __future__ import absolute_import

import copy
import os
import re
import xml.etree.ElementTree as ET

from lib.templating.context import TEMPLATE_CONTEXTS
from lib.templating.core import prepare_template_data

from .base import KodiTestCase, MEDIA_DIR, TEMPLATE_DIR, make_engine
from . import REPO_ROOT

THEMES = sorted(TEMPLATE_CONTEXTS["themes"])
INDICATOR_STYLES = sorted(TEMPLATE_CONTEXTS["indicators"])

# ibis syntax that must never survive into the generated XML
LEFTOVER_SYNTAX_RE = re.compile(r"\{\{|\{%|\{#")
# Assets PM4K ships itself, as referenced from the skin. Anchored on a real
# image extension so that Kodi's dynamic textures - e.g.
# script.plex/home/device/focus-$INFO[ListItem.Property(status)] - are left
# alone; their filename only exists at runtime.
OWN_ASSET_RE = re.compile(r"script\.plex/[A-Za-z0-9_./-]+\.(?:png|gif|jpe?g|bmp)\b")
WINDOW_XML_REF_RE = re.compile(r"['\"](script-plex-[A-Za-z0-9_.-]+)\.xml['\"]")

# Templates that ship but that no window loads. Every one of these is still
# compiled and written on each theme change, so the list should shrink, not
# grow. track_context has had no reference since it was added in 7e7156fa;
# every xmlFile in lib/windows is a static literal, so nothing loads it
# dynamically either.
UNREFERENCED_TEMPLATES = {"script-plex-track_context"}


def render_theme(engine, theme):
    """Render every template for `theme` and return {template name: xml text}."""
    engine.apply(theme, lambda at, steps, message: None)
    out = {}
    for name in engine.TEMPLATES:
        path = os.path.join(engine.target_dir, "script-plex-{0}.xml".format(name))
        with open(path, "r", encoding="utf-8") as fp:
            out[name] = fp.read()
    return out


class TemplateInventoryTest(KodiTestCase):
    def test_engine_finds_every_template_on_disk(self):
        engine = make_engine(self.mktemp())
        on_disk = {fn[len("script-plex-"):-len(".xml.tpl")]
                   for fn in os.listdir(TEMPLATE_DIR)
                   if fn.startswith("script-plex-") and fn.endswith(".xml.tpl")}
        self.assertEqual(on_disk, set(engine.TEMPLATES))
        self.assertTrue(on_disk, "no templates found at all - wrong TEMPLATE_DIR?")

    def test_every_window_xml_referenced_in_code_has_a_template(self):
        """
        lib/windows/*.py names its skin file as a plain string. If a rename
        touches only one side, Kodi silently fails to load the window.
        """
        referenced = set()
        windows_dir = os.path.join(REPO_ROOT, "lib", "windows")
        for root, _, files in os.walk(windows_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(root, fn), "r", encoding="utf-8") as fp:
                    referenced.update(WINDOW_XML_REF_RE.findall(fp.read()))

        self.assertTrue(referenced, "found no script-plex-*.xml references in lib/windows")
        missing = sorted(name for name in referenced
                         if not os.path.exists(os.path.join(TEMPLATE_DIR, name + ".xml.tpl")))
        self.assertEqual([], missing, "windows reference templates that do not exist")

    def test_every_template_is_referenced_by_a_window(self):
        """
        The other direction: a template nothing loads is dead weight that still
        gets compiled on every theme change.
        """
        referenced = set()
        windows_dir = os.path.join(REPO_ROOT, "lib", "windows")
        for root, _, files in os.walk(windows_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(root, fn), "r", encoding="utf-8") as fp:
                    referenced.update(WINDOW_XML_REF_RE.findall(fp.read()))

        on_disk = {"script-plex-" + name for name in make_engine(self.mktemp()).TEMPLATES}
        self.assertEqual(set(), on_disk - referenced - UNREFERENCED_TEMPLATES,
                         "templates that no window loads")

    def test_the_unreferenced_template_list_is_not_stale(self):
        """Fails once one of them gets wired up, so the exemption has to shrink."""
        referenced = set()
        windows_dir = os.path.join(REPO_ROOT, "lib", "windows")
        for root, _, files in os.walk(windows_dir):
            for fn in files:
                if fn.endswith(".py"):
                    with open(os.path.join(root, fn), "r", encoding="utf-8") as fp:
                        referenced.update(WINDOW_XML_REF_RE.findall(fp.read()))
        self.assertEqual(set(), UNREFERENCED_TEMPLATES & referenced,
                         "now referenced - drop it from UNREFERENCED_TEMPLATES")

    def test_search_hub_count_matches_the_search_window(self):
        """
        Both sides carry a comment saying they must agree; nothing enforced it.
        Read the constant out of the source rather than importing the window,
        which would drag in the whole GUI stack.
        """
        path = os.path.join(REPO_ROOT, "lib", "windows", "search.py")
        with open(path, "r", encoding="utf-8") as fp:
            match = re.search(r"^\s*SEARCH_HUB_COUNT\s*=\s*(\d+)", fp.read(), re.M)
        self.assertIsNotNone(match, "SEARCH_HUB_COUNT not found in lib/windows/search.py")
        self.assertEqual(int(match.group(1)), TEMPLATE_CONTEXTS["core"]["search_hub_count"])


class TemplateRenderTest(KodiTestCase):
    def test_every_theme_renders_wellformed_windows(self):
        for theme in THEMES:
            engine = make_engine(self.mktemp())
            rendered = render_theme(engine, theme)
            self.assertEqual(len(engine.TEMPLATES), len(rendered))
            for name, xml in sorted(rendered.items()):
                with self.subTest(theme=theme, template=name):
                    try:
                        root = ET.fromstring(xml)
                    except ET.ParseError as exc:
                        self.fail("{0}/{1} is not well-formed XML: {2}".format(theme, name, exc))
                    self.assertEqual("window", root.tag)
                    self.assertIsNotNone(root.find("controls"),
                                         "{0} has no <controls> block".format(name))

    def test_no_template_syntax_survives_rendering(self):
        engine = make_engine(self.mktemp())
        for name, xml in sorted(render_theme(engine, "modern-colored").items()):
            with self.subTest(template=name):
                leftover = LEFTOVER_SYNTAX_RE.search(xml)
                self.assertIsNone(leftover, "unrendered ibis syntax at offset {0} in {1}".format(
                    leftover.start() if leftover else -1, name))

    def test_every_indicator_style_renders(self):
        """
        Watched/unwatched indicator styles are a separate inheritance axis from
        the theme, and the settings UI lets users pick any of them.
        """
        for style in INDICATOR_STYLES:
            context = copy.deepcopy(TEMPLATE_CONTEXTS)
            context["indicators"]["START"] = {"INHERIT": style, "style": style,
                                              "hide_aw_bg": False, "use_scaling": True}
            engine = make_engine(self.mktemp(), context=context)
            rendered = render_theme(engine, "modern-colored")
            for name, xml in sorted(rendered.items()):
                with self.subTest(indicators=style, template=name):
                    ET.fromstring(xml)

    def test_rendering_is_deterministic(self):
        first = render_theme(make_engine(self.mktemp()), "modern")
        second = render_theme(make_engine(self.mktemp()), "modern")
        self.assertEqual(first, second)

    def test_scaling_context_changes_the_output(self):
        """
        A 5:4 panel takes the vscale()/vperc() path. If needs_scaling stopped
        reaching the filters, every layout would silently render unscaled.
        """
        unscaled = render_theme(make_engine(self.mktemp()), "modern")

        context = copy.deepcopy(TEMPLATE_CONTEXTS)
        context["core"]["resolution"] = (1280, 1024)
        context["core"]["needs_scaling"] = True
        scaled = render_theme(make_engine(self.mktemp(), context=context), "modern")

        self.assertEqual(set(unscaled), set(scaled))
        differing = [name for name in unscaled if unscaled[name] != scaled[name]]
        self.assertTrue(differing, "needs_scaling had no effect on any template")
        for name in sorted(scaled):
            with self.subTest(template=name):
                ET.fromstring(scaled[name])

    def test_hub_count_flows_into_the_home_template(self):
        base = copy.deepcopy(TEMPLATE_CONTEXTS)
        base["core"]["hub_count"] = 4
        few = render_theme(make_engine(self.mktemp(), context=base), "modern")["home"]

        more_ctx = copy.deepcopy(TEMPLATE_CONTEXTS)
        more_ctx["core"]["hub_count"] = 12
        many = render_theme(make_engine(self.mktemp(), context=more_ctx), "modern")["home"]

        self.assertNotEqual(few, many)
        self.assertLess(len(few), len(many), "more hub rows should produce a longer window")

    def test_search_window_defines_a_control_per_search_hub(self):
        xml = render_theme(make_engine(self.mktemp()), "modern")["search"]
        root = ET.fromstring(xml)
        ids = {ctrl.get("id") for ctrl in root.iter("control") if ctrl.get("id")}
        count = TEMPLATE_CONTEXTS["core"]["search_hub_count"]
        missing = [2100 + i for i in range(count) if str(2100 + i) not in ids]
        self.assertEqual([], missing, "search hub group controls missing from the skin")


class TemplateAssetTest(KodiTestCase):
    def test_referenced_pm4k_assets_exist(self):
        """
        Catches a typo'd or deleted texture. Only PM4K's own script.plex/*
        assets are checked - anything else comes from the Kodi skin.
        """
        missing = {}
        checked = 0
        for theme in THEMES:
            for name, xml in render_theme(make_engine(self.mktemp()), theme).items():
                for asset in set(OWN_ASSET_RE.findall(xml)):
                    checked += 1
                    if not os.path.exists(os.path.join(MEDIA_DIR, asset)):
                        missing.setdefault(asset, set()).add("{0}/{1}".format(theme, name))
        self.assertTrue(checked, "no script.plex/* assets found - has the regex rotted?")
        self.assertEqual({}, {k: sorted(v) for k, v in missing.items()},
                         "skin references assets that are not shipped")


class TemplateContextTest(KodiTestCase):
    def test_theme_inheritance_is_resolved_depth_first(self):
        """
        modern_2024 -> modern -> base: the child's assets win, but the keys it
        does not mention are inherited rather than dropped.
        """
        context = copy.deepcopy(TEMPLATE_CONTEXTS)
        context["indicators"]["START"] = {"INHERIT": "modern_2024"}
        resolved = prepare_template_data("modern-colored", context)

        indicators = resolved["indicators"]
        self.assertEqual("watched_2024.png", indicators["assets"]["watched"])
        # from modern
        self.assertTrue(indicators["use_scaling"])
        self.assertEqual("CC000000", indicators["watched_bg"])
        # from base
        self.assertTrue(indicators["show"])

    def test_unknown_theme_is_a_hard_error(self):
        engine = make_engine(self.mktemp())
        with self.assertRaises(KeyError):
            engine.apply("no-such-theme", lambda *args: None)

    def test_custom_theme_uses_custom_templates(self):
        """
        theme == "custom" swaps in <name>.custom.xml.tpl from the user's
        profile. The theme itself still has to exist in the context, which is
        what a user's context_overrides.json supplies.
        """
        target = self.mktemp()
        custom_dir = os.path.join(target, "custom")
        os.makedirs(custom_dir)
        with open(os.path.join(custom_dir, "script-plex-busy.custom.xml.tpl"), "w",
                  encoding="utf-8") as fp:
            fp.write('{% extends "base.xml.tpl" %}{% block controls %}'
                     '<control type="label" id="4242"><label>CUSTOM MARKER</label></control>'
                     '{% endblock controls %}')

        context = copy.deepcopy(TEMPLATE_CONTEXTS)
        context["themes"]["custom"] = {"INHERIT": "modern-colored"}
        engine = make_engine(target, custom_template_dir=custom_dir, context=context)
        engine.apply("custom", lambda *args: None, templates=["busy", "blank"])

        with open(os.path.join(target, "script-plex-busy.xml"), "r", encoding="utf-8") as fp:
            busy = fp.read()
        self.assertIn("CUSTOM MARKER", busy)
        ET.fromstring(busy)

        # a template without a .custom override falls back to the shipped one
        with open(os.path.join(target, "script-plex-blank.xml"), "r", encoding="utf-8") as fp:
            self.assertNotIn("CUSTOM MARKER", fp.read())


class TemplateWriteTest(KodiTestCase):
    def test_write_confirms_the_file_landed_at_full_size(self):
        """
        engine.write() polls Stat().st_size() against the payload length,
        because some Kodi VFS targets return from write() before the bytes are
        on disk. Assert the happy path actually verifies rather than assumes.
        """
        target = self.mktemp()
        engine = make_engine(target)
        payload = "<window><controls/></window>"
        self.assertTrue(engine.write("blank", payload))

        path = os.path.join(target, "script-plex-blank.xml")
        with open(path, "r", encoding="utf-8") as fp:
            self.assertEqual(payload, fp.read())
        self.assertEqual(len(payload), os.path.getsize(path))

    def test_write_target_is_never_the_working_tree(self):
        """Guard against a future refactor pointing tests at the real skin dir."""
        engine = make_engine(self.mktemp())
        real_skin_dir = os.path.join(REPO_ROOT, "resources", "skins", "Main", "1080i")
        self.assertNotEqual(os.path.abspath(real_skin_dir), os.path.abspath(engine.target_dir))


class ClearLogoTest(KodiTestCase):
    """
    The detail screens swap the written title for the server's clear logo. Both controls must exist and their
    visibility must be exact opposites, or an item without a logo ends up with no title at all.
    """

    WINDOWS = ("pre_play", "pre_play-wl", "seasons", "episodes")

    def setUp(self):
        super(ClearLogoTest, self).setUp()
        self.rendered = render_theme(make_engine(self.mktemp()), "modern-colored")

    def controlsFor(self, window):
        root = ET.fromstring(self.rendered[window])
        title, logo = None, None
        for control in root.iter("control"):
            visible = control.findtext("visible") or ""
            if "clear.logo" not in visible:
                continue
            if control.get("type") == "label":
                title = control
            elif control.get("type") == "image":
                logo = control
        return title, logo

    def test_both_windows_carry_a_logo_and_a_title(self):
        for window in self.WINDOWS:
            with self.subTest(window=window):
                title, logo = self.controlsFor(window)
                self.assertIsNotNone(title, "no title label gated on clear.logo")
                self.assertIsNotNone(logo, "no logo image gated on clear.logo")

    def test_the_two_are_mutually_exclusive(self):
        for window in self.WINDOWS:
            with self.subTest(window=window):
                title, logo = self.controlsFor(window)
                self.assertEqual("String.IsEmpty(Window.Property(clear.logo))", title.findtext("visible"))
                self.assertEqual("!String.IsEmpty(Window.Property(clear.logo))", logo.findtext("visible"))

    def test_the_logo_keeps_its_aspect_ratio(self):
        # logos run from near-square to 4:1 wordmarks; scaling one to the box would distort it
        for window in self.WINDOWS:
            with self.subTest(window=window):
                _, logo = self.controlsFor(window)
                self.assertEqual("keep", logo.findtext("aspectratio"))


class TemplateStalenessTest(KodiTestCase):
    """The generated-XML staleness check must be name-based, not count-based."""

    def test_detects_a_missing_generated_file(self):
        from lib.templating.render import templates_need_render
        root = self.mktemp()
        tpl = os.path.join(root, "templates")
        gen = os.path.join(root, "1080i")
        os.makedirs(tpl)
        os.makedirs(gen)
        for name in ("a", "b"):
            open(os.path.join(tpl, "script-plex-{0}.xml.tpl".format(name)), "w").close()
            open(os.path.join(gen, "script-plex-{0}.xml".format(name)), "w").close()
        self.assertFalse(templates_need_render(tpl, gen))

        # remove one template and add another: counts stay equal, but the new
        # template's generated XML is missing, so a render is required
        os.remove(os.path.join(tpl, "script-plex-a.xml.tpl"))
        os.remove(os.path.join(gen, "script-plex-a.xml"))
        open(os.path.join(tpl, "script-plex-c.xml.tpl"), "w").close()
        self.assertTrue(templates_need_render(tpl, gen))
