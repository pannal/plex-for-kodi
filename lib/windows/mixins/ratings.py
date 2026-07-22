# coding=utf-8
from lib import util
from lib import ratings as ratings_logic

# Upper bound on rating slots we clear each render (must be >= the max the
# preplay template loops over) so stale badges from a previous item never linger.
MAX_SLOTS = 8


class RatingsMixin(object):
    def populateRatings(self, video, ref, hide_ratings=False):
        setProperty = getattr(ref, "setProperty")

        clear_names = ('rating.stars', 'rating.count', 'rating', 'rating.image')
        for i in range(2, MAX_SLOTS + 1):
            clear_names += ('rating{0}'.format(i), 'rating{0}.image'.format(i))
        getattr(ref, "setProperties")(clear_names, '')

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

        # Prefer the full <Rating> list; fall back to the two flattened
        # attributes for items/servers that don't provide it.
        entries = []
        video_ratings = getattr(video, "ratings", None)
        if video_ratings:
            for r in video_ratings:
                entries.append((str(r.image or ''), r.value))
        else:
            if video.rating:
                entries.append((str(video.ratingImage or ''), video.rating))
            if video.audienceRating:
                entries.append((str(video.audienceRatingImage or ''), video.audienceRating))

        for name, value in ratings_logic.build_rating_properties(entries):
            setProperty(name, value)
