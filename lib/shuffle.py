from __future__ import absolute_import
import random

# Shuffle Mode identifiers (also used as dropdown choice keys in library.py)
MODE_UNWATCHED = 'unwatched'   # never-started shows, play from the start
MODE_REWATCH = 'rewatch'       # fully-watched shows, play from the start
MODE_CATCHUP = 'catchup'       # started shows with few unwatched episodes left


def _as_int(value):
    """Accept plexnet PlexValue (has .asInt()) or a plain int/str."""
    as_int = getattr(value, 'asInt', None)
    if callable(as_int):
        return as_int()
    return int(value)


def eligible_shows(shows, mode, threshold=None):
    """Filter `shows` (objects exposing leafCount/viewedLeafCount) to those
    eligible for `mode`. Shows with no episodes are always skipped."""
    result = []
    for show in shows:
        total = _as_int(show.leafCount)
        if total <= 0:
            continue
        viewed = _as_int(show.viewedLeafCount)
        unviewed = total - viewed

        if mode == MODE_UNWATCHED:
            if viewed == 0:
                result.append(show)
        elif mode == MODE_REWATCH:
            if unviewed == 0:
                result.append(show)
        elif mode == MODE_CATCHUP:
            if viewed > 0 and 0 < unviewed <= threshold:
                result.append(show)
    return result


def pick(shows, count, rng=random):
    """Return up to `count` shows chosen at random (shuffled). If the pool is
    smaller than `count`, return the whole pool shuffled."""
    pool = list(shows)
    if count >= len(pool):
        rng.shuffle(pool)
        return pool
    return rng.sample(pool, count)


def unwatched_episodes(episodes):
    """Keep only episodes that have not been watched."""
    return [ep for ep in episodes if not bool(ep.isWatched)]


def first_regular_index(episodes):
    """Index of the first non-special episode (parentIndex != 0), else 0.
    Used to start playback on a real episode rather than a leading special."""
    for i, ep in enumerate(episodes):
        if _as_int(ep.parentIndex) != 0:
            return i
    return 0


def eligible_movies(movies, mode):
    """Filter `movies` (objects exposing isWatched) for a movie shuffle mode:
    MODE_UNWATCHED -> unseen movies; MODE_REWATCH -> already-watched movies."""
    if mode == MODE_REWATCH:
        return [m for m in movies if bool(m.isWatched)]
    if mode == MODE_UNWATCHED:
        return [m for m in movies if not bool(m.isWatched)]
    return list(movies)
