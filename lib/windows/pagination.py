from __future__ import absolute_import

from kodi_six import xbmcgui

from lib import util
from . import kodigui


class MCLPaginator(object):
    """
    A paginator for ManagedControlList instances
    """
    control = None
    pageSize = 8
    initialPageSize = 18  # + orphans = 26

    # the amount of overhang allowed for both sides; don't show pagination when the overhang fits the current item count
    orphans = pageSize
    offset = 0
    leafCount = None
    parentWindow = None
    thumbFallback = None

    _direction = None
    _currentAmount = None
    _lastAmount = None
    _boundaryHit = False

    def __init__(self, control, parent_window, page_size=None, orphans=None, leaf_count=None):
        self.control = control
        self.pageSize = page_size if page_size is not None else self.pageSize
        self.orphans = orphans if orphans is not None else self.pageSize
        self.leafCount = leaf_count
        self.parentWindow = parent_window

        self.reset()

    def reset(self):
        self.offset = 0
        self._currentAmount = 0
        self._lastAmount = None
        self._boundaryHit = False
        self._direction = None

    def getData(self, offset, amount):
        raise NotImplementedError

    def createListItem(self, data):
        return self.parentWindow.createListItem(data)

    def prepareListItem(self, data, mli):
        pass

    def readyForPaging(self):
        return self.parentWindow.initialized

    @property
    def _readyForPaging(self):
        return self.readyForPaging()

    @property
    def boundaryHit(self):
        self._boundaryHit = False

        if not self._readyForPaging:
            return

        mli = self.control.getSelectedItem()
        if mli and mli.getProperty("is.boundary") and not mli.getProperty("is.updating"):
            direction = "left" if mli.getProperty("left.boundary") else "right"
            mli.setBoolProperty("is.updating", True)
            self.offset = int(mli.getProperty("orig.index"))
            self._direction = direction
            self._boundaryHit = True

        return self._boundaryHit

    @property
    def nextPage(self):
        leafCount = self.leafCount
        offset = self.offset
        amount = self.pageSize

        if self._direction == "left":
            if offset <= self.initialPageSize:
                # return to initial page
                offset = 0
                amount = self.initialPageSize
            else:
                # move the slice to the left by :amount: based on :offset:
                amount = min(offset, self.pageSize)
                offset -= amount

            # avoid short pages on the left end
            if 0 < offset < self.orphans:
                amount += offset
                offset = 0

        else:
            # move the slice to the right
            itemsLeft = leafCount - offset
            # avoid short pages on the right end
            if itemsLeft <= self.pageSize + self.orphans:
                amount = self.pageSize + self.orphans

        self.offset = offset
        data = self.getData(offset, amount)
        self._lastAmount = self._currentAmount
        self._currentAmount = len(data)
        return data

    @property
    def initialPage(self):
        amount = self.initialPageSize
        if self.initialPageSize + self.orphans >= self.leafCount:
            amount = self.initialPageSize + self.orphans

        data = self.getData(self.offset, amount)
        if data:
            self._lastAmount = self._currentAmount
            self._currentAmount = len(data)
            return data

    def populate(self, items):
        """
        Populates the current page to the bound Control List. Adds prev/next MLIs and selects the correct control
        after doing so.
        :param items:
        :return:
        """
        idx = 0
        moreLeft = self.offset > 0
        moreRight = self.offset + self._currentAmount < self.leafCount

        finalItems = []
        thumbFallback = self.thumbFallback

        if items:
            for item in items:
                mli = self.createListItem(item)

                if mli:
                    mli.setProperty('index', str(idx))
                    self.prepareListItem(item, mli)
                    if thumbFallback:
                        if callable(thumbFallback):
                            mli.setProperty('thumb.fallback', thumbFallback(item))
                        else:
                            mli.setProperty('thumb.fallback', thumbFallback)

                    finalItems.append(mli)
                    idx += 1

            if moreRight:
                end = kodigui.ManagedListItem('')
                end.setBoolProperty('is.boundary', True)
                end.setBoolProperty('right.boundary', True)
                end.setProperty("orig.index", str(int(self.offset + self._currentAmount)))
                finalItems.append(end)
            else:
                # no boundary, rightmost item
                finalItems[-1].setBoolProperty('last.item', True)

            if moreLeft:
                start = kodigui.ManagedListItem('')
                start.setBoolProperty('is.boundary', True)
                start.setBoolProperty('left.boundary', True)
                start.setProperty("orig.index", str(int(self.offset)))
                finalItems.insert(0, start)

            self.control.replaceItems(finalItems)
            self.selectItem(self._currentAmount, more_left=moreLeft, more_right=moreRight, items=items)

        return finalItems

    def selectItem(self, amount, more_left=False, more_right=False, items=None):
        if self._direction:
            if self._direction == "left":
                self.control.selectItem(amount - (1 if not more_left else 0))
                return True

            elif self._direction == "right":
                self.control.selectItem(1)
                return True

    def paginate(self, force_page=False):
        """
        Triggers the pagination for the currently selected view. In case of a hit boundary, show the next or previous
        page, otherwise show the initial page.
        :return:
        """
        if self._boundaryHit or force_page:
            items = self.nextPage

        else:
            items = self.initialPage

        return self.populate(items)

    @property
    def canSimpleWrap(self):
        return self.initialPageSize + self.orphans >= self.leafCount

    def wrap(self, mli, last_mli, action):
        """
        Wraps around the list if the first or last item is currently selected and the user requests to round robin.
        :param mli: current item
        :param last_mli: previous item
        :param action: xbmcgui action
        :return:
        """

        index = int(mli.getProperty("index"))
        last_mli_index = int(last_mli.getProperty("index"))

        # special case for our absolute last item
        is_rightmost = action == xbmcgui.ACTION_MOVE_RIGHT \
            and mli.getProperty('last.item') \
            and last_mli.getProperty('last.item')

        # _lastAmount is used to immediately wrap again after a wrap has happened; potentially an issue
        if not is_rightmost and last_mli_index not in \
                (0, self._currentAmount - 1, (self._lastAmount - 1) if self._lastAmount else None) \
                or self._currentAmount < 2:
            return

        onlyTwo = self._currentAmount == 2

        items = None
        if action == xbmcgui.ACTION_MOVE_LEFT and index == 0 and last_mli_index == 0:
            if onlyTwo and last_mli_index == self._currentAmount - 1:
                return

            if not self.canSimpleWrap:
                self._direction = "right"
                self.offset = self.leafCount - self.orphans - self.pageSize
                items = self.paginate(force_page=True)
                self.control.selectItem(self._currentAmount)
            else:
                self.control.selectItem(self.leafCount - 1)
        elif action == xbmcgui.ACTION_MOVE_RIGHT and (index == self._currentAmount - 1 or is_rightmost):
            if onlyTwo and last_mli_index == 0:
                return

            if not self.canSimpleWrap:
                self._direction = "left"
                self.offset = 0
                items = self.paginate()
            self.control.selectItem(0)

        if items:
            return items


class BaseRelatedPaginator(MCLPaginator):
    initialPageSize = 8
    pageSize = initialPageSize
    orphans = initialPageSize // 2

    thumbFallback = lambda self, rel: 'script.plex/thumb_fallbacks/{0}.png'.format(
        rel.type in ('show', 'season', 'episode') and 'show' or 'movie')

    def createListItem(self, rel):
        return kodigui.ManagedListItem(
            rel.title or '',
            thumbnailImage=rel.defaultThumb.asTranscodedImageURL(*self.parentWindow.RELATED_DIM),
            data_source=rel
        )

    def prepareListItem(self, data, mli):
        if data.type in ('season', 'show'):
            if not mli.dataSource.isWatched:
                mli.setProperty('unwatched.count', str(mli.dataSource.unViewedLeafCount) or '')
                mli.setBoolProperty('unwatched.count.large', mli.dataSource.unViewedLeafCount > 999)
            else:
                mli.setBoolProperty('watched', mli.dataSource.isWatched)
        else:
            mli.setProperty('unwatched', not mli.dataSource.isWatched and '1' or '')
            mli.setBoolProperty('watched', mli.dataSource.isFullyWatched)
            mli.setProperty('progress', util.getProgressImage(mli.dataSource))
