# coding=utf-8
"""
The clear logo gate.

Plex sends no dimensions with the Image element, so whether a logo is wide enough to use has to be measured
off the wire. The rules that matter: too square falls back to the written title, an unmeasurable logo is
still shown, and the measurement is cached against the logo's URL so it happens once per artwork.
"""

from __future__ import absolute_import

import struct

try:
    from unittest import mock
except ImportError:  # py2
    import mock

from lib import util

from .base import KodiTestCase


def png(width, height):
    """The first 24 bytes of a PNG - signature, length, 'IHDR', then the dimensions."""
    return b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\r' + b'IHDR' + struct.pack('>II', width, height)


class FakeLogo(str):
    def asTranscodedImageURL(self, w, h, **kwargs):
        return 'http://server/photo/:/transcode?width=%s&height=%s' % (w, h)


class FakeItem(object):
    ratingKey = '1234'
    clearLogo = FakeLogo('/library/metadata/1234/clearLogo/1600000000')


class ClearLogoGateTest(KodiTestCase):
    def setUp(self):
        super(ClearLogoGateTest, self).setUp()
        self.item = FakeItem()

    def logoFor(self, ratio):
        with mock.patch.object(util, 'clearLogoAspect', return_value=ratio):
            return util.clearLogoFrom(self.item, 380, 68)

    def test_a_wide_wordmark_is_used(self):
        self.assertTrue(self.logoFor(7.0))

    def test_a_squarish_lockup_falls_back_to_the_title(self):
        # "The Mandalorian and Grogu" is about 2:1 and reads badly scaled into a wordmark's slot
        self.assertEqual('', self.logoFor(2.0))

    def test_the_threshold_itself_is_used(self):
        self.assertTrue(self.logoFor(util.CLEAR_LOGO_MIN_RATIO))
        self.assertEqual('', self.logoFor(util.CLEAR_LOGO_MIN_RATIO - 0.1))

    def test_an_unmeasurable_logo_is_still_shown(self):
        # a server that won't answer the probe shouldn't cost every logo
        self.assertTrue(self.logoFor(None))

    def test_the_setting_wins_over_everything(self):
        with mock.patch.object(util, 'getSetting', return_value=False):
            self.assertEqual('', self.logoFor(7.0))

    def test_an_item_without_a_logo_yields_nothing(self):
        class NoLogo(object):
            ratingKey = '1'
        self.assertEqual('', util.clearLogoFrom(NoLogo(), 380, 68))


class ClearLogoMeasureTest(KodiTestCase):
    def measure(self, content):
        from lib import data_cache
        resp = mock.Mock(content=content)
        with mock.patch.object(util.requests, 'get', return_value=resp) as get, \
                mock.patch.object(data_cache.dcm, 'getCacheData', return_value=None), \
                mock.patch.object(data_cache.dcm, 'setCacheData') as put:
            return util.clearLogoAspect(FakeItem(), FakeLogo('/logo/1')), get, put

    def test_dimensions_come_out_of_the_png_header(self):
        ratio, _, _ = self.measure(png(800, 200))
        self.assertEqual(4.0, ratio)

    def test_a_stacked_lockup_measures_near_two(self):
        ratio, _, _ = self.measure(png(1000, 500))
        self.assertEqual(2.0, ratio)

    def test_the_result_is_cached_against_the_logo_url(self):
        _, _, put = self.measure(png(800, 200))
        put.assert_called_once()
        self.assertEqual('clear_logo_aspect', put.call_args[0][0])
        self.assertEqual('/logo/1', put.call_args[0][1])

    def test_a_non_png_response_is_not_measured(self):
        ratio, _, put = self.measure(b'<html>nope</html>' + b'\x00' * 20)
        self.assertIsNone(ratio)
        put.assert_not_called()

    def test_a_failed_request_is_not_fatal(self):
        from lib import data_cache
        with mock.patch.object(util.requests, 'get', side_effect=IOError('down')), \
                mock.patch.object(data_cache.dcm, 'getCacheData', return_value=None):
            self.assertIsNone(util.clearLogoAspect(FakeItem(), FakeLogo('/logo/1')))

    def test_a_cached_measurement_skips_the_request(self):
        from lib import data_cache
        with mock.patch.object(util.requests, 'get') as get, \
                mock.patch.object(data_cache.dcm, 'getCacheData', return_value=6.5):
            self.assertEqual(6.5, util.clearLogoAspect(FakeItem(), FakeLogo('/logo/1')))
        get.assert_not_called()
