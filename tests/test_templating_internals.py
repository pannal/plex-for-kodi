# coding=utf-8
"""
lib/templating internals - the context machinery and custom ibis filters that
every skin template is compiled against.

A bug here doesn't break one window, it breaks all 47 of them at once, so the
inheritance rules and the filters get direct tests rather than only being
exercised through a full render.
"""

from __future__ import absolute_import

import copy

import ibis
from ibis.context import Context, ContextDict

from lib.templating import filters
from lib.templating.context import TEMPLATE_CONTEXTS
from lib.templating.core import build_stack, prepare_template_data
from lib.templating.util import deep_update

from .base import KodiTestCase


def render(source, data):
    """Compile a template snippet through the same engine the skin uses."""
    return ibis.Template(source).render(data)


class DeepUpdateTest(KodiTestCase):
    def test_nested_dicts_are_merged_not_replaced(self):
        source = {"a": {"x": 1, "y": 2}, "b": 1}
        deep_update(source, {"a": {"y": 3}})
        self.assertEqual({"a": {"x": 1, "y": 3}, "b": 1}, source)

    def test_it_mutates_the_source_in_place_and_returns_it(self):
        source = {"a": 1}
        returned = deep_update(source, {"b": 2})
        self.assertIs(source, returned)
        self.assertEqual({"a": 1, "b": 2}, source)

    def test_scalars_overwrite(self):
        source = {"a": {"x": 1}}
        deep_update(source, {"a": "flat"})
        self.assertEqual({"a": "flat"}, source)

    def test_an_empty_dict_override_replaces_rather_than_merges(self):
        """
        The `and value` guard means an empty mapping is treated as a scalar, so
        {"a": {}} wipes the subtree instead of leaving it untouched.
        """
        source = {"a": {"x": 1}}
        deep_update(source, {"a": {}})
        self.assertEqual({"a": {}}, source)

    def test_deeply_nested_merge(self):
        source = {"a": {"b": {"c": 1, "d": 2}}}
        deep_update(source, {"a": {"b": {"d": 9, "e": 10}}})
        self.assertEqual({"a": {"b": {"c": 1, "d": 9, "e": 10}}}, source)

    def test_new_keys_are_added(self):
        source = {}
        deep_update(source, {"a": {"b": 1}})
        self.assertEqual({"a": {"b": 1}}, source)


class BuildStackTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.sources = {
            "base": {"colour": "black", "size": 1},
            "mid": {"INHERIT": "base", "size": 2},
            "leaf": {"INHERIT": "mid", "extra": True},
        }

    def test_a_chain_is_returned_leaf_first(self):
        stack = build_stack(ContextDict({"INHERIT": "leaf"}), self.sources)
        # the seed dict, then leaf, mid, base
        self.assertEqual(4, len(stack))
        self.assertEqual({"extra": True}, dict(stack[1]))
        self.assertEqual({"size": 2}, dict(stack[2]))
        self.assertEqual({"colour": "black", "size": 1}, dict(stack[3]))

    def test_the_inherit_key_is_consumed(self):
        stack = build_stack(ContextDict({"INHERIT": "leaf"}), self.sources)
        for entry in stack:
            with self.subTest(entry=dict(entry)):
                self.assertNotIn("INHERIT", entry)

    def test_no_inheritance_yields_just_the_seed(self):
        stack = build_stack(ContextDict({"a": 1}), self.sources)
        self.assertEqual(1, len(stack))

    def test_the_sources_are_not_mutated(self):
        before = copy.deepcopy(self.sources)
        build_stack(ContextDict({"INHERIT": "leaf"}), self.sources)
        self.assertEqual(before, self.sources)

    def test_an_unknown_parent_raises(self):
        with self.assertRaises(KeyError):
            build_stack(ContextDict({"INHERIT": "nope"}), self.sources)


class PrepareTemplateDataTest(KodiTestCase):
    def context(self):
        return copy.deepcopy(TEMPLATE_CONTEXTS)

    def test_the_result_carries_theme_core_and_indicators(self):
        resolved = prepare_template_data("modern-colored", self.context())
        for key in ("theme", "core", "indicators"):
            with self.subTest(key=key):
                self.assertIn(key, resolved)

    def test_core_overrides_survive(self):
        ctx = self.context()
        ctx["core"]["hub_count"] = 3
        self.assertEqual(3, prepare_template_data("modern", ctx)["core"]["hub_count"])

    def test_indicators_without_a_start_key_are_used_flat(self):
        ctx = self.context()
        ctx["indicators"] = {"style": "custom", "show": False}
        resolved = prepare_template_data("modern", ctx)
        self.assertEqual("custom", resolved["indicators"]["style"])
        self.assertFalse(resolved["indicators"]["show"])

    def test_indicators_with_a_start_key_resolve_the_inheritance_chain(self):
        ctx = self.context()
        ctx["indicators"]["START"] = {"INHERIT": "classic", "style": "classic"}
        resolved = prepare_template_data("modern", ctx)
        self.assertEqual("FFCC7B19", resolved["indicators"]["unwatched_count_bg"])
        self.assertTrue(resolved["indicators"]["use_unwatched"])

    def test_the_none_indicator_style_switches_them_off(self):
        ctx = self.context()
        ctx["indicators"]["START"] = {"INHERIT": "none"}
        self.assertFalse(prepare_template_data("modern", ctx)["indicators"]["show"])

    def test_every_shipped_theme_resolves(self):
        for theme in sorted(TEMPLATE_CONTEXTS["themes"]):
            with self.subTest(theme=theme):
                resolved = prepare_template_data(theme, self.context())
                self.assertTrue(resolved["theme"], "theme {0} resolved empty".format(theme))

    def test_every_shipped_indicator_style_resolves(self):
        for style in sorted(TEMPLATE_CONTEXTS["indicators"]):
            with self.subTest(style=style):
                ctx = self.context()
                ctx["indicators"]["START"] = {"INHERIT": style}
                self.assertIn("show", prepare_template_data("modern", ctx)["indicators"])

    def test_themes_is_consumed_from_the_context(self):
        """
        prepare_template_data pops "themes", so the caller's context is spent
        after one call - which is why render_templates deep-copies it first.
        """
        ctx = self.context()
        prepare_template_data("modern", ctx)
        self.assertNotIn("themes", ctx)
        with self.assertRaises(KeyError):
            prepare_template_data("modern", ctx)


class FilterTest(KodiTestCase):
    def test_calc_does_arithmetic(self):
        self.assertEqual(5, filters.calc(2, 3))
        self.assertEqual(6, filters.calc(2, 3, "mul"))
        self.assertEqual(-1, filters.calc(2, 3, "sub"))

    def test_calc_coerces_numeric_strings(self):
        self.assertEqual(5, filters.calc("2", 3))
        self.assertEqual(5.5, filters.calc("2.5", 3))
        self.assertEqual(5, filters.calc(2, "3"))

    def test_calc_reports_a_bad_operation_clearly(self):
        with self.assertRaises(ValueError) as caught:
            filters.calc(2, 3, "nonsense")
        self.assertIn("nonsense", str(caught.exception))

    def test_calc_reports_uncombinable_operands(self):
        with self.assertRaises(ValueError):
            filters.calc(None, 3)

    def test_get_attr_reads_from_a_mapping(self):
        self.assertEqual(1, filters.get_attr({"a": 1}, "a"))
        self.assertIsNone(filters.get_attr({"a": 1}, "b"))
        self.assertEqual("d", filters.get_attr({"a": 1}, "b", default="d"))


class FilterInTemplateTest(KodiTestCase):
    """
    vscale/vperc take the render context, so they are only meaningful inside a
    template - that is also how the skin uses them.
    """

    def data(self, resolution=(1920, 1080), needs_scaling=False):
        return {"core": ContextDict({"resolution": resolution,
                                    "needs_scaling": needs_scaling})}

    def test_vscale_is_a_no_op_when_scaling_is_off(self):
        self.assertEqual("100", render("{{ vscale(100) }}", self.data()))

    def test_vscale_shrinks_on_a_taller_panel(self):
        out = render("{{ vscale(100) }}", self.data((1280, 1024), needs_scaling=True))
        self.assertLess(float(out), 100.0)

    def test_vscale_grows_on_an_ultrawide_panel(self):
        out = render("{{ vscale(100) }}", self.data((2560, 1080), needs_scaling=True))
        self.assertGreater(float(out), 100.0)

    def test_vscale_caches_the_ratio_on_the_context(self):
        """
        The ratio is computed once and stashed as a global on the context; a
        second call in the same render must reuse it rather than recompute.
        """
        out = render("{{ vscale(100) }}|{{ vscale(200) }}",
                     self.data((1280, 1024), needs_scaling=True))
        first, second = (float(v) for v in out.split("|"))
        self.assertAlmostEqual(2.0, second / first, places=6)

    def test_vperc_positions_relative_to_a_1080_reference(self):
        self.assertEqual("490.0", render("{{ vperc(100) }}", self.data()))

    def test_vscale_can_apply_an_extra_factor(self):
        plain = float(render("{{ vscale(100) }}", self.data((1280, 1024), True)))
        boosted = float(render("{{ vscale(100, 2) }}", self.data((1280, 1024), True)))
        self.assertAlmostEqual(plain * 2, boosted, places=6)


class ContextIntegrityTest(KodiTestCase):
    def test_every_indicator_style_inherits_from_a_known_parent(self):
        indicators = TEMPLATE_CONTEXTS["indicators"]
        for name, data in sorted(indicators.items()):
            parent = data.get("INHERIT")
            if parent is None:
                continue
            with self.subTest(style=name):
                self.assertIn(parent, indicators,
                              "{0} inherits from unknown {1}".format(name, parent))

    def test_every_theme_inherits_from_a_known_parent(self):
        themes = TEMPLATE_CONTEXTS["themes"]
        for name, data in sorted(themes.items()):
            parent = data.get("INHERIT")
            if parent is None:
                continue
            with self.subTest(theme=name):
                self.assertIn(parent, themes,
                              "{0} inherits from unknown {1}".format(name, parent))

    def test_no_inheritance_cycles(self):
        for group in ("themes", "indicators"):
            sources = TEMPLATE_CONTEXTS[group]
            for name in sorted(sources):
                with self.subTest(group=group, name=name):
                    seen, current = set(), name
                    while current:
                        self.assertNotIn(current, seen,
                                         "cycle through {0}".format(current))
                        seen.add(current)
                        current = sources[current].get("INHERIT")

    def test_core_defaults_are_sane(self):
        core = TEMPLATE_CONTEXTS["core"]
        self.assertEqual((1920, 1080), tuple(core["resolution"]))
        self.assertFalse(core["needs_scaling"])
        self.assertGreater(core["hub_count"], 0)
        self.assertGreater(core["search_hub_count"], 0)
