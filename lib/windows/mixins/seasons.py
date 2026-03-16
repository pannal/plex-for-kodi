# coding=utf-8
import math

from lib import util
from lib.windows import kodigui


class SeasonsMixin(object):
    SEASONS_CONTROL_ATTR = "subItemListControl"

    THUMB_DIMS = {
        'show': {
            'main.thumb': util.scaleResolution(347, 518),
            'item.thumb': util.scaleResolution(174, 260)
        },
        'episode': {
            'main.thumb': util.scaleResolution(347, 518),
            'item.thumb': util.scaleResolution(198, 295)
        },
        'artist': {
            'main.thumb': util.scaleResolution(519, 519),
            'item.thumb': util.scaleResolution(215, 215)
        }
    }

    def _createListItem(self, mediaItem, obj):
        mli = kodigui.ManagedListItem(
            obj.title or '',
            thumbnailImage=obj.defaultThumb.asTranscodedImageURL(*self.THUMB_DIMS[mediaItem.type]['item.thumb']),
            data_source=obj
        )
        return mli

    def getSeasonProgress(self, show, season):
        """
        calculates the season progress based on how many episodes are watched and, optionally, if there's an episode
        in progress, take that into account as well
        """
        viewed = season.viewedLeafCount.asInt()
        has_ondeck_progress = False
        for v in show.onDeck:
            if v.parentRatingKey == season.ratingKey and v.viewOffset.asInt():
                has_ondeck_progress = True
                break
        if has_ondeck_progress and viewed == season.leafCount.asInt():
            viewed -= 1
        watchedPerc = viewed / season.leafCount.asInt() * 100
        for v in show.onDeck:
            if v.parentRatingKey == season.ratingKey and v.viewOffset:
                vPerc = int((v.viewOffset.asInt() / v.duration.asFloat()) * 100)
                watchedPerc += vPerc / season.leafCount.asFloat()
        return watchedPerc > 0 and math.ceil(watchedPerc) or 0

    def fillSeasons(self, show, update=False, seasonsFilter=None, selectSeason=None, do_focus=True):
        try:
            seasons = show.seasons()
        except:
            raise util.NoDataException

        if not seasons or (seasonsFilter and not seasonsFilter(seasons)):
            return False

        items = []
        idx = 0
        focus = None
        for season in seasons:
            if selectSeason and season == selectSeason:
                continue

            mli = self._createListItem(show, season)
            if mli:
                mli.setProperty('index', str(idx))
                mli.setProperty('thumb.fallback', 'script.plex/thumb_fallbacks/show.png')
                seasonWatched = season.isWatched
                has_ondeck_progress = False
                for v in show.onDeck:
                    if v.parentRatingKey == season.ratingKey and v.viewOffset.asInt():
                        has_ondeck_progress = True
                        break
                if has_ondeck_progress and season.viewedLeafCount == season.leafCount:
                    seasonWatched = False
                mli.setProperty('unwatched.count', not seasonWatched and str(season.unViewedLeafCount) or '')
                mli.setBoolProperty('unwatched.count.large', not seasonWatched and season.unViewedLeafCount > 999)
                mli.setBoolProperty('watched', seasonWatched)
                if not seasonWatched and focus is None and season.index.asInt() > 0:
                    focus = idx
                    mli.setProperty('progress', util.getProgressImage(None, self.getSeasonProgress(show, season)))
                items.append(mli)
                idx += 1

        subItemListControl = getattr(self, self.SEASONS_CONTROL_ATTR)
        if update:
            subItemListControl.replaceItems(items)
        else:
            subItemListControl.reset()
            subItemListControl.addItems(items)

        if focus is not None and do_focus:
            subItemListControl.setSelectedItemByPos(focus)

        return True
