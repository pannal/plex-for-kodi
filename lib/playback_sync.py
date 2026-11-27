# coding=utf-8
"""Playback-return I/O. Workers own their sessions and never receive GUI objects."""
from __future__ import absolute_import

import copy
import threading
from six.moves.queue import Queue, Empty

from plexnet import http, plexapp, util as pnUtil
from lib import util

_JOBS = Queue()
_WORKER = None
_WORKER_LOCK = threading.Lock()
_PENDING = []
_PENDING_LOCK = threading.RLock()
_READ_REVISIONS = {}
_PROGRESS_REVISIONS = {}


def readRevision(server):
    with _PENDING_LOCK:
        return _READ_REVISIONS.get((accountScope(), str(server.uuid)), 0)


def progressRevision(item):
    prefix = (accountScope(), str(item.server.uuid))
    keys = (str(item.ratingKey), str(item.get('parentRatingKey')), str(item.get('grandparentRatingKey')))
    with _PENDING_LOCK:
        return tuple(_PROGRESS_REVISIONS.get((prefix, key), 0) for key in keys)


def _work():
    while not util.MONITOR.abortRequested():
        try:
            job = _JOBS.get(timeout=0.2)
        except Empty:
            continue
        try:
            job.run()
        except Exception:
            util.ERROR('Playback return: request worker failed')
        finally:
            with _PENDING_LOCK:
                if job in _PENDING:
                    _PENDING.remove(job)
            _JOBS.task_done()


def submit(job):
    """One dedicated worker, independent of window task cancellation and teardown."""
    global _WORKER
    with _WORKER_LOCK:
        with _PENDING_LOCK:
            _PENDING.append(job)
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_work, name='PM4K-playback-return')
            _WORKER.daemon = True
            _WORKER.start()
        _JOBS.put(job)


def supersedeWrites(item):
    """A manual choice supersedes matching writes, including those from closed views."""
    scope = accountScope()
    pending = False
    with _PENDING_LOCK:
        prefix = (scope, str(item.server.uuid))
        _READ_REVISIONS[prefix] = _READ_REVISIONS.get(prefix, 0) + 1
        key = (prefix, str(item.ratingKey))
        _PROGRESS_REVISIONS[key] = _PROGRESS_REVISIONS.get(key, 0) + 1
        for job in _PENDING:
            if (job.scope == scope and str(job.server.uuid) == str(item.server.uuid)
                    and job.supersede(str(item.ratingKey), item.TYPE)):
                pending = True
    return scope if pending else None


def finishWatchChange(item, watched, scope):
    item.set('viewOffset', 0)
    item.set('viewCount', max(1, item.get('viewCount', 0).asInt()) if watched else 0)
    if item.TYPE in ('show', 'season'):
        item.set('viewedLeafCount', item.get('leafCount', 0).asInt() if watched else 0)
        if item.TYPE == 'show':
            for entry in item.onDeck:
                entry.set('viewOffset', 0)
    if item.TYPE in ('episode', 'season', 'show'):
        from lib.windows.episodes import clearVideoProgress
        clearVideoProgress(item)
    if scope is None or scope != accountScope():
        return
    key = str(item.ratingKey)
    job = PlaybackReturnJob(item.server, (), (key,) if watched else (), cacheURLs([item]),
                            scope, None, Queue(), unwatched=() if watched else (key,),
                            parents={key: tuple(str(item.get(parent)) for parent in
                                                ('parentRatingKey', 'grandparentRatingKey') if item.get(parent))})
    job.discard.set()
    job.start()


def accountScope():
    account = plexapp.ACCOUNT
    return (id(account), str(account.ID), str(account.authToken), pnUtil.LOCAL_MODE)


def cacheURLs(items, extra_keys=()):
    """Snapshot invalidation URLs without doing disk I/O or modifying cache lists."""
    base = pnUtil.CACHED_PLEX_URLS.get(pnUtil.INTERFACE.getRCBaseKey(), {})
    keys = set(extra_keys)
    for item in items:
        key = item.getCacheRef(always_return=True)
        if key:
            keys.add(key)
        section = item.getLibrarySectionId()
        if section:
            keys.add('section_{}'.format(section))
        if item.TYPE == 'episode':
            keys.update(('season_{}'.format(item.parentRatingKey), 'show_{}'.format(item.grandparentRatingKey)))
    return tuple(set(url for key in keys for url in base.get(key, ())))


class PlaybackReturnJob(object):
    def __init__(self, server, requests, completed, urls, scope, generation, results,
                 watchlist=None, seasons=None, unwatched=(), parents=None):
        self.server = server
        self.requests = requests
        self.completed = completed
        self.urls = urls
        self.scope = scope
        self.generation = generation
        self.results = results
        self.watchlist = watchlist
        self.seasons = seasons
        self.unwatched = unwatched
        self.discard = threading.Event()
        self.parents = parents or {}
        self.cancelledKeys = set()
        self.writeLock = threading.Lock()
        self.writesFinished = threading.Event()

    def supersede(self, key, kind):
        keys = {k for k in self.completed + self.unwatched
                if k == key or (kind in ('show', 'season') and key in self.parents.get(k, ()))}
        if keys or any(k == key or (kind in ('show', 'season') and key in self.parents.get(k, ()))
                       for k, _ in self.requests):
            self.discard.set()
        if not keys or self.writesFinished.is_set():
            return False
        with self.writeLock:
            self.cancelledKeys.update(keys)
        return True

    def start(self):
        submit(self)

    def current(self):
        return accountScope() == self.scope and not util.MONITOR.abortRequested()

    def reading(self):
        return self.current() and not self.discard.is_set()

    def publish(self, kind, data):
        if self.reading():
            self.results.put((self.generation, self.scope, kind, data))

    def client(self, server):
        # Copy only the server connection configuration, never media/model graphs.
        client = copy.copy(server)
        client.session = http.Session()
        for scheme, adapter in server.session.adapters.items():
            client.session.adapters[scheme].max_retries = copy.copy(adapter.max_retries)
        return client

    def fetch(self, client, path, params):
        if not self.reading():
            return None
        try:
            return client.query(path, params=params)
        except Exception:
            util.ERROR('Playback return: metadata refresh failed')
            return None

    def run(self):
        client = None
        metadata_sent = False
        try:
            if not self.current():
                return
            client = self.client(self.server)
            confirmed = set()
            # Completion must still be persisted if the user leaves the screen.
            # A successful empty-body scrobble returns b'', transport failure None.
            try:
                actions = [('scrobble', key) for key in self.completed]
                actions += [('unscrobble', key) for key in self.unwatched]
                for action, key in actions:
                    if not self.current():
                        break
                    with self.writeLock:
                        cancelled = key in self.cancelledKeys
                    if cancelled:
                        continue
                    try:
                        result = client.query('/:/{}'.format(action), key=key,
                                              identifier='com.plexapp.plugins.library', raw=True)
                        if result is not None:
                            confirmed.add(key)
                        else:
                            util.LOG('Playback return: watched-state update for {} was not confirmed', key)
                    except Exception:
                        util.ERROR('Playback return: could not persist watched state')
            finally:
                self.writesFinished.set()

            if self.urls and self.current():
                try:
                    for url in self.urls:
                        client.session.cache.delete_url(url)
                    client.session.cache.vacuum()
                except Exception:
                    util.ERROR('Playback return: cache invalidation failed')

            snapshots = {}
            for key, params in self.requests:
                data = self.fetch(client, '/library/metadata/{}'.format(key), params)
                if data is not None and len(data):
                    child = data[0]
                    if child.get('ratingKey') == key:
                        snapshots[key] = child
            self.publish('metadata', snapshots)
            metadata_sent = True

            if self.seasons:
                data = self.fetch(client, self.seasons, {})
                if data is not None:
                    self.publish('seasons', list(data))

            if self.watchlist and self.reading():
                self.syncWatchlist(snapshots, confirmed)
        except Exception:
            util.ERROR('Playback return: background synchronization failed')
        finally:
            self.writesFinished.set()
            if not metadata_sent:
                self.publish('metadata', {})
            if client is not None:
                client.session.close()

    def syncWatchlist(self, snapshots, confirmed):
        from lib.windows.mixins.watchlist import is_watchlisted
        spec = self.watchlist
        key = spec['key']
        data = snapshots.get(key)
        fully_watched = spec['watched']
        if spec['type'] == 'show':
            fully_watched = (data is not None and int(data.get('leafCount', '0')) > 0
                             and data.get('leafCount') == data.get('viewedLeafCount')
                             and not any(int(v.get('viewOffset', '0')) for v in data.findall('OnDeck/Video')))
        # Don't remove from Watchlist when our explicit completion couldn't be sent.
        remove = (spec['remove'] and fully_watched and set(self.completed) <= confirmed)
        client = self.client(spec['server'])
        try:
            state = None
            if remove:
                for _ in range(3):
                    if not self.reading():
                        return
                    client.query('/actions/removeFromWatchlist', ratingKey=spec['guid'], method='put')
                    state = is_watchlisted(spec['guid'], client)
                    if state is not True:
                        break
                    if util.MONITOR.waitForAbort(0.1):
                        return
            elif self.reading():
                state = is_watchlisted(spec['guid'], client)
            self.publish('watchlist', (state, remove and state is False))
        except Exception:
            util.ERROR('Playback return: Watchlist synchronization failed')
        finally:
            client.session.close()
