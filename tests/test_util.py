# coding=utf-8
"""
lib/util.py - the formatting and platform-probing helpers the whole UI leans on.

Several of these have quirks that are load-bearing (durationToText takes
milliseconds despite its parameter being called `seconds`, sub-minute
durations render as floats). The tests below pin the behaviour as it is; where
it looks like a bug rather than a choice, the test says so in a comment
instead of quietly asserting something nicer.
"""

from __future__ import absolute_import

import os
import datetime
import sys
from unittest import mock

from kodienv import ENV

from lib import util

from .base import KodiTestCase, MEDIA_DIR


class FakeValue(object):
    """Stand-in for a plexnet PlexValue."""

    def __init__(self, value):
        self.value = value

    def asInt(self):
        return int(self.value)

    def asFloat(self):
        return float(self.value)

    def __bool__(self):
        return bool(self.value)

    __nonzero__ = __bool__


class FakeItem(object):
    def __init__(self, **attrs):
        self._attrs = {k: FakeValue(v) for k, v in attrs.items()}

    def get(self, key, default=None):
        return self._attrs.get(key, default)

    def __getattr__(self, item):
        try:
            return self._attrs[item]
        except KeyError:
            raise AttributeError(item)

    def __bool__(self):
        return True

    __nonzero__ = __bool__


class SortTitleTest(KodiTestCase):
    def test_leading_the_is_dropped(self):
        self.assertEqual("Matrix", util.sortTitle("The Matrix"))

    def test_other_articles_are_kept(self):
        self.assertEqual("A Movie", util.sortTitle("A Movie"))
        self.assertEqual("Theodore", util.sortTitle("Theodore"))
        self.assertEqual("The", util.sortTitle("The"))


class DurationToTextTest(KodiTestCase):
    """Despite the parameter name, the input is milliseconds."""

    def test_days_win_over_everything(self):
        self.assertEqual("1 day", util.durationToText(86400000))
        self.assertEqual("2 days", util.durationToText(2 * 86400000))

    def test_hours_and_minutes(self):
        self.assertEqual("1 hr 30 mins", util.durationToText(90 * 60 * 1000))
        self.assertEqual("2 hrs 1 min", util.durationToText(121 * 60 * 1000))

    def test_whole_hours_have_no_trailing_space(self):
        self.assertEqual("1 hr", util.durationToText(3600000))

    def test_sub_minute_durations_render_as_floats(self):
        # inherited quirk: secs is divided by 1000 *after* being taken as ms,
        # so this reads "5.0 secs" rather than "5 secs"
        self.assertEqual("5.0 secs", util.durationToText(5000))
        self.assertEqual("1.0 sec", util.durationToText(1000))

    def test_zero(self):
        self.assertEqual("0 seconds", util.durationToText(0))


class DurationToShortTextTest(KodiTestCase):
    def test_default_form(self):
        self.assertEqual("1 h 30 m", util.durationToShortText(90 * 60 * 1000))
        self.assertEqual("2 d", util.durationToShortText(2 * 86400000))
        self.assertEqual("1 h", util.durationToShortText(3600000))

    def test_no_spaces(self):
        self.assertEqual("1h 30m", util.durationToShortText(90 * 60 * 1000, noSpaces=True))
        self.assertEqual("2d", util.durationToShortText(2 * 86400000, noSpaces=True))

    def test_short_hour_mins_collapses_to_a_clock(self):
        self.assertEqual("1:30 h", util.durationToShortText(90 * 60 * 1000, shortHourMins=True))
        self.assertEqual("1:30h", util.durationToShortText(90 * 60 * 1000, shortHourMins=True,
                                                           noSpaces=True))

    def test_short_seconds_drops_the_decimal(self):
        self.assertEqual("5.0 s", util.durationToShortText(5000))
        self.assertEqual("5 s", util.durationToShortText(5000, shortSeconds=True))

    def test_zero(self):
        self.assertEqual("0 s", util.durationToShortText(0))
        self.assertEqual("0s", util.durationToShortText(0, noSpaces=True))


class SmallHelpersTest(KodiTestCase):
    def test_clean_leading_zeros_only_after_a_space(self):
        self.assertEqual("Mon 9 Jul", util.cleanLeadingZeros("Mon 09 Jul"))
        # no preceding space, so a clock stays intact
        self.assertEqual("01:05", util.cleanLeadingZeros("01:05"))
        self.assertEqual("", util.cleanLeadingZeros(""))
        self.assertEqual("", util.cleanLeadingZeros(None))

    def test_remove_dups_keeps_first_occurrence_order(self):
        self.assertEqual([1, 2, 3], util.removeDups([1, 2, 1, 3, 2]))
        self.assertEqual([], util.removeDups([]))
        self.assertEqual(["a", "b"], util.removeDups(["a", "a", "b", "a"]))

    def test_simple_size(self):
        self.assertEqual("0B", util.simpleSize(0))
        self.assertEqual("1.0 B", util.simpleSize(1))
        self.assertEqual("1.0 KB", util.simpleSize(1024))
        self.assertEqual("12.06 KB", util.simpleSize(12345))
        self.assertEqual("1.0 GB", util.simpleSize(1024 ** 3))

    def test_simple_size_of_a_negative_is_zero_not_a_crash(self):
        self.assertEqual("0B", util.simpleSize(-5))

    def test_time_display(self):
        self.assertEqual("00:00:00", util.timeDisplay(0))
        self.assertEqual("00:01:01", util.timeDisplay(61000))
        self.assertEqual("01:01:01", util.timeDisplay(3661000))

    def test_time_display_can_drop_a_zero_hour(self):
        self.assertEqual("01:01", util.timeDisplay(61000, cutHour=True))
        # ... but keeps it once there is an hour to show
        self.assertEqual("01:01:01", util.timeDisplay(3661000, cutHour=True))

    def test_simplified_time_display_strips_leading_zero_groups(self):
        self.assertEqual("0:00", util.simplifiedTimeDisplay(0))
        self.assertEqual("1:01", util.simplifiedTimeDisplay(61000))
        self.assertEqual("1:01:01", util.simplifiedTimeDisplay(3661000))

    def test_shorten_text_appends_an_ellipsis(self):
        self.assertEqual("hello", util.shortenText("hello", 10))
        self.assertEqual(u"hell…", util.shortenText("hello world", 5))
        # exactly `size` still gets shortened - the check is `<`, not `<=`
        self.assertEqual(u"hell…", util.shortenText("hello", 5))

    def test_slugify(self):
        self.assertEqual("the-matrix", util.slugify("The Matrix"))
        self.assertEqual("amelie", util.slugify(u"Amélie"))
        self.assertEqual("a-b-c", util.slugify("  a  b   c  "))
        self.assertEqual("its-a-test", util.slugify("It's a test!"))

    def test_add_url_params(self):
        self.assertEqual("http://h/p?a=1", util.addURLParams("http://h/p", {"a": 1}))
        self.assertEqual("http://h/p?x=1&a=2", util.addURLParams("http://h/p?x=1", {"a": 2}))

    def test_add_url_params_encodes_values(self):
        self.assertEqual("http://h/p?q=a+b", util.addURLParams("http://h/p", {"q": "a b"}))


class ScalingTest(KodiTestCase):
    def test_scale_resolution_is_identity_at_100_percent(self):
        self.assertEqual((1920, 1080), util.scaleResolution(1920, 1080, by=100))

    def test_scale_resolution_halves_the_pixel_count_at_50_percent(self):
        w, h = util.scaleResolution(1920, 1080, by=50)
        self.assertLess(w, 1920)
        self.assertAlmostEqual(1920 / 1080.0, w / float(h), places=2)
        # area within rounding distance of half
        self.assertAlmostEqual(0.5, (w * h) / float(1920 * 1080), places=2)

    def test_vscale_is_a_no_op_without_scaling(self):
        # NEEDS_SCALING is computed at import from a 1920x1080 stub screen
        self.assertFalse(util.NEEDS_SCALING)
        self.assertEqual(100, util.vscale(100))

    def test_vscale_applies_the_aspect_ratio_on_a_narrow_panel(self):
        from lib import aspectratio
        orig_needs, orig_ratio = util.NEEDS_SCALING, aspectratio.V_AR_RATIO
        try:
            util.NEEDS_SCALING = True
            aspectratio.V_AR_RATIO = None
            util.DISPLAY_RESOLUTION = [1280, 1024]
            # A 5:4 panel devotes a larger fraction of itself to height than
            # 16:9 does, so a size authored against 1080 has to shrink.
            self.assertLess(util.vscale(100), 100)
            self.assertIsInstance(util.vscalei(100), int)
        finally:
            util.NEEDS_SCALING = orig_needs
            aspectratio.V_AR_RATIO = orig_ratio
            util.DISPLAY_RESOLUTION = [1920, 1080]

    def test_vperc(self):
        self.assertEqual(490.0, util.vperc(100))
        self.assertEqual(490, util.vperci(100))
        self.assertIsInstance(util.vperci(100), int)

    def test_v_ar_ratio_is_one_for_16_9(self):
        from lib import aspectratio
        self.assertAlmostEqual(1.0, aspectratio.v_ar_ratio(1920, 1080))
        # taller than 16:9 -> shrink; wider (ultrawide) -> grow
        self.assertLess(aspectratio.v_ar_ratio(1280, 1024), 1.0)
        self.assertGreater(aspectratio.v_ar_ratio(2560, 1080), 1.0)


class ProgressImageTest(KodiTestCase):
    def test_percentage_is_rounded_down_to_an_even_number(self):
        self.assertEqual("script.plex/progress/50.png", util.getProgressImage(None, perc=50))
        self.assertEqual("script.plex/progress/98.png", util.getProgressImage(None, perc=99))

    def test_zero_progress_still_shows_the_smallest_sliver(self):
        self.assertEqual("script.plex/progress/2.png", util.getProgressImage(None, perc=1))

    def test_nothing_to_show(self):
        self.assertEqual("", util.getProgressImage(None, perc=None))

    def test_view_offset_and_duration_from_the_item(self):
        item = FakeItem(viewOffset=30000, duration=120000)
        self.assertEqual("script.plex/progress/24.png", util.getProgressImage(item))

    def test_item_without_progress_yields_nothing(self):
        self.assertEqual("", util.getProgressImage(FakeItem(duration=120000)))
        self.assertEqual("", util.getProgressImage(FakeItem(viewOffset=30000)))

    def test_explicit_view_offset_overrides_the_item(self):
        item = FakeItem(viewOffset=30000, duration=120000)
        self.assertEqual("script.plex/progress/24.png", util.getProgressImage(item))
        self.assertEqual("script.plex/progress/50.png",
                         util.getProgressImage(item, view_offset=60000))

    def test_every_reachable_progress_asset_is_shipped(self):
        """getProgressImage can only emit even 2..100; all of those must exist."""
        missing = []
        for perc in range(0, 101):
            asset = util.getProgressImage(None, perc=perc) if perc else \
                util.getProgressImage(None, perc=1)
            if not os.path.exists(os.path.join(MEDIA_DIR, asset)):
                missing.append(asset)
        self.assertEqual([], sorted(set(missing)))


class KodiSettingProbeTest(KodiTestCase):
    def test_skip_steps_come_from_kodi(self):
        self.assertEqual(ENV.KODI_SETTING_DEFAULTS["videoplayer.seeksteps"],
                         util.getKodiSkipSteps())

    def test_skip_steps_are_none_when_kodi_refuses(self):
        del ENV.kodi_settings["videoplayer.seeksteps"]
        self.assertIsNone(util.getKodiSkipSteps())

    def test_slideshow_interval_falls_back_to_three_seconds(self):
        self.assertEqual(5, util.getKodiSlideshowInterval())
        del ENV.kodi_settings["slideshow.staytime"]
        self.assertEqual(3, util.getKodiSlideshowInterval())

    def test_language_code_builds_an_accept_language_header(self):
        ENV.kodi_settings["locale.language"] = "resource.language.en_gb"
        self.assertEqual(("en-GB,en", "en"), util.getLanguageCode())
        self.assertEqual(("en-GB,en,en-US,en", "en"), util.getLanguageCode(add_def="en-US,en"))

    def test_language_code_without_a_region(self):
        ENV.kodi_settings["locale.language"] = "resource.language.de"
        self.assertEqual(("de", "de"), util.getLanguageCode())

    def test_language_code_does_not_duplicate_an_already_present_default(self):
        ENV.kodi_settings["locale.language"] = "resource.language.en_us"
        self.assertEqual(("en-US,en", "en"), util.getLanguageCode(add_def="en-US,en"))


class TimeFormatTest(KodiTestCase):
    def test_explicit_padded_24h_format(self):
        ENV.kodi_settings["locale.timeformat"] = "HH:mm:ss"
        fmt, kodi_fmt, pad = util.getTimeFormat()
        self.assertEqual("%H:%M:%S", fmt)
        self.assertEqual("hh:mm:ss", kodi_fmt)
        self.assertTrue(pad)

    def test_explicit_padded_12h_format(self):
        ENV.kodi_settings["locale.timeformat"] = "hh:mm:ss xx"
        fmt, _, pad = util.getTimeFormat()
        self.assertEqual("%I:%M:%S %p", fmt)
        self.assertTrue(pad)

    def test_unpadded_hour_is_not_reported_as_padded(self):
        ENV.kodi_settings["locale.timeformat"] = "H:mm:ss"
        fmt, _, pad = util.getTimeFormat()
        self.assertIn(fmt.split(":")[0], ("%-H", "%#H"))
        self.assertFalse(pad)

    def test_regional_falls_back_to_getregion_and_sniffs_padding(self):
        """
        Kodi's "regional" answer is unusable directly: it can hand back the
        bogus %H%H notation, and its padded formats sometimes contain a single
        %H. The fallback sniffs the current System.Time instead.
        """
        ENV.kodi_settings["locale.timeformat"] = "regional"
        ENV.regions["time"] = "%H%H:%M:%S"
        fmt, _, pad = util.getTimeFormat()
        self.assertEqual("%H:%M:%S", fmt)
        self.assertTrue(pad)

    def test_regional_unpadded_clock_is_detected_from_system_time(self):
        ENV.kodi_settings["locale.timeformat"] = "regional"
        ENV.regions["time"] = "%H:%M:%S"
        ENV.infolabels["System.Time"] = "9:45:00"
        _, _, pad = util.getTimeFormat()
        self.assertFalse(pad)

    def test_regional_padded_clock_is_detected_from_system_time(self):
        ENV.kodi_settings["locale.timeformat"] = "regional"
        ENV.regions["time"] = "%H:%M:%S"
        ENV.infolabels["System.Time"] = "09:45:00"
        _, _, pad = util.getTimeFormat()
        self.assertTrue(pad)

    def test_android_style_broken_regional_format_is_repaired(self):
        """Kodi Omega on Android can return "%H:mm:ss", which strftime rejects."""
        ENV.kodi_settings["locale.timeformat"] = "regional"
        ENV.regions["time"] = "%H:mm:ss"
        fmt, _, _ = util.getTimeFormat()
        self.assertEqual("%H:%M:%S", fmt)

    def test_populate_time_format_refreshes_the_module_globals(self):
        orig = util.timeFormat
        try:
            ENV.kodi_settings["locale.timeformat"] = "hh:mm:ss xx"
            util.populateTimeFormat()
            self.assertEqual("%I:%M:%S %p", util.timeFormat)
        finally:
            ENV.kodi_settings["locale.timeformat"] = "HH:mm:ss"
            util.populateTimeFormat()
            self.assertEqual(orig, util.timeFormat)


class ShortDateFormatTest(KodiTestCase):
    def test_explicit_format_is_translated_to_strftime(self):
        ENV.kodi_settings["locale.shortdateformat"] = "DD/MM/YYYY"
        self.assertEqual("%d/%m/%Y", util.getShortDateFormat())

    def test_all_explicit_kodi_short_date_formats_render(self):
        date = datetime.datetime(2022, 7, 9)
        month = date.strftime("%b")
        formats = (
            ("DD/MM/YYYY", "09/07/2022"),
            ("MM/DD/YYYY", "07/09/2022"),
            ("YYYY/MM/DD", "2022/07/09"),
            ("D/M/YYYY", "9/7/2022"),
            ("DD-MM-YYYY", "09-07-2022"),
            ("MM-DD-YYYY", "07-09-2022"),
            ("YYYY-MM-DD", "2022-07-09"),
            ("YYYY-M-D", "2022-7-9"),
            ("DD.MM.YYYY", "09.07.2022"),
            ("DD.M.YYYY", "09.7.2022"),
            ("D.M.YYYY", "9.7.2022"),
            ("D. M. YYYY", "9. 7. 2022"),
            ("YYYY.MM.DD", "2022.07.09"),
            ("D-mmm-YY", "9-{}-22".format(month)),
            ("DD-mmm-YY", "09-{}-22".format(month)),
            ("D mmm YY", "9 {} 22".format(month)),
            ("DD mmm YY", "09 {} 22".format(month)),
        )
        for kodi_format, expected in formats:
            with self.subTest(kodi_format=kodi_format):
                ENV.kodi_settings["locale.shortdateformat"] = kodi_format
                self.assertEqual(expected, date.strftime(util.getShortDateFormat()))

    def test_unpadded_fields_use_platform_specific_modifiers(self):
        ENV.kodi_settings["locale.shortdateformat"] = "D/M/YY"
        for platform, expected in (("win32", "%#d/%#m/%y"), ("linux", "%-d/%-m/%y")):
            with self.subTest(platform=platform), mock.patch.object(sys, "platform", platform):
                self.assertEqual(expected, util.getShortDateFormat())

    def test_regional_comes_from_getregion(self):
        ENV.kodi_settings["locale.shortdateformat"] = "regional"
        ENV.regions["dateshort"] = "%-d/%m/%Y"
        # the unpadded day is normalised away
        self.assertEqual("%d/%m/%Y", util.getShortDateFormat())

    def test_unavailable_setting_falls_back(self):
        del ENV.kodi_settings["locale.shortdateformat"]
        self.assertEqual("%d/%m/%Y", util.getShortDateFormat())


class KodiSourcesTest(KodiTestCase):
    def test_only_file_like_sources_are_kept(self):
        ENV.jsonrpc_responses["Files.GetSources"] = {"sources": [
            {"file": "smb://nas/media/", "label": "NAS"},
            {"file": "nfs://nas/media/", "label": "NFS"},
            {"file": "/mnt/media/", "label": "Local"},
            {"file": "addons://sources/video/", "label": "Add-ons"},
            {"file": "library://video/", "label": "Library"},
        ]}
        del util.KODI_SOURCES[:]
        util.getKodiSources()
        self.assertEqual(["NAS", "NFS", "Local"], [s["label"] for s in util.KODI_SOURCES])

    def test_a_failing_rpc_leaves_the_list_empty(self):
        ENV.jsonrpc_responses.pop("Files.GetSources")
        del util.KODI_SOURCES[:]
        util.getKodiSources()
        self.assertEqual([], util.KODI_SOURCES)

    def tearDown(self):
        del util.KODI_SOURCES[:]
        KodiTestCase.tearDown(self)
