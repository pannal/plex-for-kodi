from unittest.mock import patch
from xml.etree import ElementTree as ET

from lib import util
from lib.windows.kodigui import ManagedListItem
from lib.windows.mixins.ratings import RatingsMixin
from plexnet.video import Episode, Movie, Show

from .base import KodiTestCase, ensure_plex_interface


class RatingsTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        ensure_plex_interface()
        self.item = ManagedListItem()
        self.mixin = RatingsMixin()
        settings = patch.object(util, "getSetting", return_value=["movies", "series"])
        settings.start()
        self.addCleanup(settings.stop)

    def test_full_metadata_uses_each_rating_in_source_order(self):
        for cls in (Movie, Show, Episode):
            with self.subTest(kind=cls.TYPE):
                data = ET.fromstring("""
                    <Video rating="5.0">
                        <Rating image="imdb://image.rating" value="8.3" />
                        <Rating image="rottentomatoes://image.rating.ripe" value="9.1" />
                        <Rating image="themoviedb://image.rating" value="7.7" />
                    </Video>""")
                self.mixin.populateRatings(cls(data), self.item)
                props = self.item.properties
                self.assertEqual(["8.3", "91%", "7.7"], [props[k] for k in ("rating", "rating2", "rating3")])
                self.assertEqual("script.plex/ratings/tmdb/image.rating.png", props["rating3.image"])
                self.assertEqual("3", props["rating.count"])

    def test_flattened_ratings_and_spoiler_hide_on_reused_item(self):
        video = Episode(ET.fromstring("""
            <Video rating="7.2" ratingImage="imdb://image.rating" audienceRating="8.8"
                   audienceRatingImage="rottentomatoes://image.rating.upright" />"""))
        self.mixin.populateRatings(video, self.item)
        self.assertEqual("7.2", self.item.properties["rating"])
        self.assertEqual("88%", self.item.properties["rating2"])

        self.mixin.populateRatings(video, self.item, hide_ratings=True)
        for name in ("rating", "rating.image", "rating2", "rating2.image", "rating.count"):
            self.assertFalse(self.item.properties.get(name))
