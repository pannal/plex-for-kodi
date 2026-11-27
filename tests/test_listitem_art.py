# coding=utf-8
"""Missing artwork must reach Kodi as an empty string, including on refresh."""
from __future__ import absolute_import

from types import SimpleNamespace
from unittest.mock import Mock, patch

from kodienv import ENV

ENV.abort_requested = True
from lib.windows import kodigui, seekdialog
from tests.base import KodiTestCase


class ListItemArtworkTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.art_calls = []
        original = kodigui.xbmcgui.ListItem.setArt

        def checked_set_art(item, artwork):
            self.assertNotIn(None, artwork.values(), 'Kodi string artwork cannot be None')
            self.art_calls.append(dict(artwork))
            return original(item, artwork)

        patcher = patch.object(kodigui.xbmcgui.ListItem, 'setArt', checked_set_art)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_constructor_accepts_missing_artwork_and_preserves_urls(self):
        for thumb, icon in ((None, None), ('thumb.jpg', 'icon.png'), (None, 'icon.png')):
            with self.subTest(thumb=thumb, icon=icon):
                item = kodigui.ManagedListItem(thumbnailImage=thumb, iconImage=icon)
                self.assertEqual(item.listItem.getArt('thumb'), thumb or '')
                self.assertEqual(item.listItem.getArt('icon'), icon or '')

    def test_refresh_accepts_missing_cached_artwork(self):
        item = kodigui.ManagedListItem(thumbnailImage='old.jpg', iconImage='old.png')
        item._manager = SimpleNamespace(_properties={})
        item._ID = '1'
        item.thumbnailImage = None
        item.iconImage = None
        item._updateListItem()
        self.assertEqual(item.listItem.getArt('thumb'), '')
        self.assertEqual(item.listItem.getArt('icon'), '')

    def test_artwork_setters_preserve_urls_and_clear_missing_artwork(self):
        item = kodigui.ManagedListItem()
        for setter, key in ((item.setThumbnailImage, 'thumb'), (item.setIconImage, 'icon')):
            for value in ('image.jpg', None, ''):
                with self.subTest(key=key, value=value):
                    setter(value)
                    self.assertEqual(item.listItem.getArt(key), value or '')

    def test_artwork_dictionary_is_normalized_without_mutating_the_caller(self):
        item = kodigui.ManagedListItem()
        artwork = {'thumb': None, 'poster': 'poster.jpg', 'fanart': ''}
        item.setArt(artwork)
        self.assertEqual(self.art_calls[-1], {'thumb': '', 'poster': 'poster.jpg', 'fanart': ''})
        self.assertIsNone(artwork['thumb'])

    def test_chapter_without_thumbnail_builds_a_list_item(self):
        chapters = Mock()
        chapters.getX.return_value = 0
        dialog = SimpleNamespace(
            showChapters=True, no_spoilers=set(), markers=[],
            chapters=[SimpleNamespace(thumb=None, tag='Chapter 1', startTime=lambda: 0)],
            bigSeekControl=chapters, setProperty=Mock())
        with patch.object(seekdialog.util, 'getUserSetting', return_value=False):
            seekdialog.SeekDialog.updateChapters(dialog)
        items = chapters.addItems.call_args[0][0]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].getLabel(), 'Chapter 1')
        self.assertEqual(items[0].listItem.getArt('thumb'), '')
