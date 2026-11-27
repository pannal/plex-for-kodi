# coding=utf-8
"""Local playback state and owner-thread delivery of asynchronous return refreshes."""
from __future__ import absolute_import

import threading
from six.moves.queue import Queue, Empty

from lib import playback_sync, util
from plexnet import plexapp


class PlaybackReturnMixin(object):
    def __init__(self):
        self._returnOwner = threading.current_thread().ident
        self._returnLock = threading.RLock()
        self._returnResults = Queue()
        self._returnGeneration = 0
        self._returnJob = None
        self._returnClosed = False
        self._returnProgress = {}
        self._returnProgressVersions = {}
        self._returnTargets = {}
        self._returnDiscardReported = False

    def invalidatePlaybackReturn(self, clear_progress=False, closed=False):
        with self._returnLock:
            self._returnGeneration += 1
            self._returnClosed = self._returnClosed or closed
            if self._returnJob:
                self._returnJob.discard.set()
                self._returnJob = None
            if clear_progress:
                self._returnProgress.clear()
                self._returnProgressVersions.clear()
            self._returnTargets = {}

    def storePlaybackProgress(self, item, state):
        # Signal handlers store Python data only; native UI updates happen on return.
        with self._returnLock:
            self._returnProgress[str(item.ratingKey)] = state
            self._returnProgressVersions[str(item.ratingKey)] = playback_sync.progressRevision(item)

    def beginManualPlaybackChange(self, item=None, cancel_pending=True):
        item = item or getattr(self, 'video', None) or self.show_
        self.invalidatePlaybackReturn()
        key = str(item.ratingKey)
        with self._returnLock:
            for recorded in list(self._returnProgress):
                if (recorded == key or (item.TYPE in ('show', 'season')
                                       and key in getattr(self, '_returnParents', {}).get(recorded, ()))):
                    del self._returnProgress[recorded]
                    self._returnProgressVersions.pop(recorded, None)
        return playback_sync.supersedeWrites(item) if cancel_pending else None

    def beforeWatchedChange(self, item, state):
        self.beginManualPlaybackChange(item, cancel_pending=False)

    def finishManualPlaybackChange(self, item, watched, scope):
        if watched is None:
            return
        # An old scrobble may already be on the wire. Reassert the user's newer
        # explicit choice after it finishes on the same serialized request queue.
        playback_sync.finishWatchChange(item, watched, scope)

    def applyPlaybackProgress(self, item):
        with self._returnLock:
            key = str(item.ratingKey)
            if self._returnProgressVersions.get(key) != playback_sync.progressRevision(item):
                self._returnProgress.pop(key, None)
                return
            state = self._returnProgress.get(key)
        if state is True:
            item.set('viewCount', max(1, item.get('viewCount', 0).asInt()))
            item.set('viewOffset', 0)
        elif state is not None:
            item.set('viewOffset', state if state > 60000 else 0)

    def startPlaybackReturn(self, items, completed=(), watchlist_ref=None, seasons=None):
        self.invalidatePlaybackReturn()
        self._returnTargets = {str(item.ratingKey): item for item, _ in items}
        reference = watchlist_ref or items[0][0]
        self._returnView = (str(reference.server.uuid), str(reference.ratingKey))
        self._returnReadRevision = playback_sync.readRevision(reference.server)
        self._returnDiscardReported = False
        watchlist = None
        if self.wl_enabled:
            watchlist = dict(server=plexapp.SERVERMANAGER.getDiscoverServer(), key=str(reference.ratingKey),
                             guid=str(reference.guid).rsplit('/', 1)[-1], type=reference.TYPE,
                             watched=bool(reference.isFullyWatched),
                             remove=self.is_watchlisted and util.getUserSetting('watchlist_auto_remove', True))
        scope = playback_sync.accountScope()
        self._returnJob = playback_sync.PlaybackReturnJob(
            reference.server, [(str(item.ratingKey), dict(params)) for item, params in items],
            tuple(completed), playback_sync.cacheURLs(self._returnTargets.values(),
                                                      getattr(self, '_returnCacheKeys', ())), scope,
            self._returnGeneration, self._returnResults, watchlist=watchlist, seasons=seasons)
        self._returnJob.parents = dict(getattr(self, '_returnParents', {}))
        self._returnJob.start()

    def playbackReturnCurrent(self, generation, scope, check_revision=True):
        reference = getattr(self, 'video', None) or getattr(self, 'show_', None)
        return (not self._returnClosed and not self._closing and self.isOpen
                and self._returnGeneration == generation and playback_sync.accountScope() == scope
                and reference is not None
                and (not check_revision or playback_sync.readRevision(reference.server) == self._returnReadRevision)
                and (str(reference.server.uuid), str(reference.ratingKey)) == self._returnView)

    def processPendingPlaybackReturn(self):
        # Called only from ControlledBase.wait(), between native callbacks, on the
        # window's Python owner thread. Child windows suspend this modal loop.
        if threading.current_thread().ident != self._returnOwner or not self.is_current_window:
            return
        job = self._returnJob
        if (job and not self._returnDiscardReported
                and self.playbackReturnCurrent(job.generation, job.scope, check_revision=False)
                and not self.playbackReturnCurrent(job.generation, job.scope)):
            # A manual action in another view may have invalidated this job even
            # before it could publish. Settle any waiting Play control on owner.
            self._returnDiscardReported = True
            job.discard.set()
            self.onPlaybackReturnDiscarded()
        while True:
            try:
                generation, scope, kind, data = self._returnResults.get_nowait()
            except Empty:
                return
            if not self.playbackReturnCurrent(generation, scope):
                continue
            if kind == 'metadata':
                for key, snapshot in data.items():
                    if not self.playbackReturnCurrent(generation, scope):
                        return
                    item = self._returnTargets.get(key)
                    if item is not None:
                        try:
                            item.reload(data=snapshot, fromMediaChoice=item.mediaChoice is not None)
                        except Exception:
                            util.ERROR('Playback return: could not apply metadata')
                        finally:
                            self.applyPlaybackProgress(item)
                if self.playbackReturnCurrent(generation, scope):
                    self.onPlaybackReturnMetadata(data)
            elif kind == 'seasons':
                self.onPlaybackReturnSeasons(data)
            elif kind == 'watchlist':
                state, removed = data
                if state is not None:
                    self.is_watchlisted = state
                    self.setBoolProperty('is_watchlisted', state)
                if removed and self.playbackReturnCurrent(generation, scope):
                    plexapp.util.APP.trigger('watchlist:modified')
                    if self.playbackReturnCurrent(generation, scope):
                        reference = getattr(self, 'video', None) or self.show_
                        util.showNotification(util.T(34077, '{} successfully removed from Watchlist').format(reference.defaultTitle),
                                              time_ms=3000, header=util.T(34000, 'Watchlist'))

    def onPlaybackReturnSeasons(self, data):
        pass

    def onPlaybackReturnDiscarded(self):
        pass
