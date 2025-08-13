# coding=utf-8
from lib import util
from lib.data_cache import dcm
from lib.genres import GENRES_TV_BY_SYN
from plexnet import util as pnUtil


class SpoilersMixin(object):
    def __init__(self, *args, **kwargs):
        self._noSpoilers = None
        self.spoilerSetting = ["unwatched"]
        self.noTitles = False
        self.noRatings = False
        self.noImages = False
        self.noResumeImages = False
        self.noSummaries = False
        self.spoilersAllowedFor = True
        self.cacheSpoilerSettings()

    def cacheSpoilerSettings(self):
        self.spoilerSetting = util.getSetting('no_episode_spoilers4')
        self.noTitles = 'no_unwatched_episode_titles' in self.spoilerSetting
        self.noRatings = 'hide_ratings' in self.spoilerSetting
        self.noImages = 'blur_images' in self.spoilerSetting
        self.noResumeImages = 'blur_resume_images' in self.spoilerSetting
        self.noSummaries = 'hide_summary' in self.spoilerSetting
        self.spoilersAllowedFor = util.getSetting('spoilers_allowed_genres2')

    @property
    def noSpoilers(self):
        return self.getNoSpoilers()

    def getCachedGenres(self, rating_key):
        genres = dcm.getCacheData("show_genres", rating_key)
        if genres:
            return [pnUtil.AttributeDict(tag=g) for g in genres]

    def getNoSpoilers(self, item=None, show=None):
        """
        when called without item or show, retains a global noSpoilers value, otherwise return dynamically based on item
        or show
        returns: "off" if spoilers unnecessary, otherwise "unwatched" or "funwatched"
        """
        if not item and not show and self._noSpoilers is not None:
            return self._noSpoilers

        if item and item.type != "episode":
            return "off"

        nope = "funwatched" if "in_progress" in self.spoilerSetting else "unwatched" \
            if "unwatched" in self.spoilerSetting else "off"

        if nope != "off" and self.spoilersAllowedFor:
            # instead of making possibly multiple separate API calls to find genres for episode's shows, try to get
            # a cached value instead
            genres = []
            if item or show:
                genres = self.getCachedGenres(item and item.grandparentRatingKey or show.ratingKey)

            if not genres:
                show = getattr(self, "show_", show or (item and item.show()) or None)
                if not show:
                    return "off"

            if not genres and show:
                genres = show.genres()

            for g in genres:
                main_tag = GENRES_TV_BY_SYN.get(g.tag)
                if main_tag and main_tag in self.spoilersAllowedFor:
                    nope = "off"
                    break

        if item or show:
            self._noSpoilers = nope
            return self._noSpoilers
        return nope

    def hideSpoilers(self, ep, fully_watched=None, watched=None, use_cache=True):
        """
        returns boolean on whether we should hide spoilers for the given episode
        """
        watched = watched if watched is not None else ep.isWatched
        fullyWatched = fully_watched if fully_watched is not None else ep.isFullyWatched
        nspoil = self.getNoSpoilers(item=ep if not use_cache else None)
        return ((nspoil == 'funwatched' and not fullyWatched) or
                (nspoil == 'unwatched' and not watched))

    def getThumbnailOpts(self, ep, fully_watched=None, watched=None, hide_spoilers=None):
        if not self.noImages or self.getNoSpoilers(item=ep) == "off":
            return {}
        return (hide_spoilers if hide_spoilers is not None else
                self.hideSpoilers(ep, fully_watched=fully_watched, watched=watched)) \
            and {"blur": util.addonSettings.episodeNoSpoilerBlur} or {}
