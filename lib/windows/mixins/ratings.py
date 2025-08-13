# coding=utf-8
from lib import util


class RatingsMixin(object):
    def populateRatings(self, video, ref, hide_ratings=False):
        def sanitize(src):
            return src.replace("themoviedb", "tmdb").replace('://', '/')

        setProperty = getattr(ref, "setProperty")
        getattr(ref, "setProperties")(('rating.stars', 'rating', 'rating.image', 'rating2', 'rating2.image'), '')

        if video.userRating:
            stars = str(int(round((video.userRating.asFloat() / 10) * 5)))
            setProperty('rating.stars', stars)

        if hide_ratings:
            return

        if video.TYPE == "movie" and "movies" not in util.getSetting("show_ratings"):
            return

        if (video.TYPE in ("episode", "show", "season") and
                "series" not in util.getSetting("show_ratings")):
            return

        audienceRating = video.audienceRating

        if video.rating or audienceRating:
            if video.rating:
                rating = video.rating
                if video.ratingImage.startswith('rottentomatoes:'):
                    rating = '{0}%'.format(int(rating.asFloat() * 10))

                setProperty('rating', rating)
                if video.ratingImage:
                    setProperty('rating.image', 'script.plex/ratings/{0}.png'.format(sanitize(video.ratingImage)))
            if audienceRating:
                if video.audienceRatingImage.startswith('rottentomatoes:'):
                    audienceRating = '{0}%'.format(int(audienceRating.asFloat() * 10))
                setProperty('rating2', audienceRating)
                if video.audienceRatingImage:
                    setProperty('rating2.image',
                                'script.plex/ratings/{0}.png'.format(sanitize(video.audienceRatingImage)))
        else:
            setProperty('rating', video.rating)
