# coding=utf-8
"""lib/shuffle.py - which shows and movies a shuffle mode is allowed to pick."""

from __future__ import absolute_import

import random

from lib import shuffle

from .base import KodiTestCase


class FakeCount(object):
    """Mimics a plexnet PlexValue, which exposes asInt() rather than being one."""

    def __init__(self, value):
        self.value = value

    def asInt(self):
        return int(self.value)


class FakeShow(object):
    def __init__(self, name, leaf, viewed, as_plex_value=True):
        self.name = name
        wrap = FakeCount if as_plex_value else (lambda v: v)
        self.leafCount = wrap(leaf)
        self.viewedLeafCount = wrap(viewed)

    def __repr__(self):
        return "<FakeShow {0}>".format(self.name)


class FakeMovie(object):
    def __init__(self, name, watched):
        self.name = name
        self.isWatched = watched


class FakeEpisode(object):
    def __init__(self, watched=False, parentIndex=1):
        self.isWatched = watched
        self.parentIndex = FakeCount(parentIndex)


def names(shows):
    return [s.name for s in shows]


class EligibleShowsTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.shows = [
            FakeShow("fresh", leaf=10, viewed=0),
            FakeShow("started", leaf=10, viewed=7),
            FakeShow("nearly-done", leaf=10, viewed=9),
            FakeShow("done", leaf=10, viewed=10),
            FakeShow("empty", leaf=0, viewed=0),
        ]

    def test_unwatched_mode_takes_never_started_shows(self):
        self.assertEqual(["fresh"], names(shuffle.eligible_shows(self.shows,
                                                                 shuffle.MODE_UNWATCHED)))

    def test_rewatch_mode_takes_fully_watched_shows(self):
        self.assertEqual(["done"], names(shuffle.eligible_shows(self.shows,
                                                                shuffle.MODE_REWATCH)))

    def test_catchup_mode_takes_started_shows_within_the_threshold(self):
        self.assertEqual(["nearly-done"],
                         names(shuffle.eligible_shows(self.shows, shuffle.MODE_CATCHUP,
                                                      threshold=1)))
        self.assertEqual(["started", "nearly-done"],
                         names(shuffle.eligible_shows(self.shows, shuffle.MODE_CATCHUP,
                                                      threshold=3)))

    def test_catchup_never_includes_finished_or_untouched_shows(self):
        picked = names(shuffle.eligible_shows(self.shows, shuffle.MODE_CATCHUP, threshold=99))
        self.assertNotIn("done", picked)
        self.assertNotIn("fresh", picked)

    def test_shows_with_no_episodes_are_never_eligible(self):
        for mode in (shuffle.MODE_UNWATCHED, shuffle.MODE_REWATCH, shuffle.MODE_CATCHUP):
            with self.subTest(mode=mode):
                self.assertNotIn("empty", names(shuffle.eligible_shows(self.shows, mode,
                                                                       threshold=99)))

    def test_plain_ints_work_as_well_as_plex_values(self):
        shows = [FakeShow("fresh", leaf=10, viewed=0, as_plex_value=False)]
        self.assertEqual(["fresh"], names(shuffle.eligible_shows(shows,
                                                                 shuffle.MODE_UNWATCHED)))

    def test_an_unknown_mode_selects_nothing(self):
        self.assertEqual([], shuffle.eligible_shows(self.shows, "nonsense"))


class EligibleMoviesTest(KodiTestCase):
    def setUp(self):
        KodiTestCase.setUp(self)
        self.movies = [FakeMovie("seen", True), FakeMovie("unseen", False)]

    def test_unwatched(self):
        self.assertEqual(["unseen"],
                         names(shuffle.eligible_movies(self.movies, shuffle.MODE_UNWATCHED)))

    def test_rewatch(self):
        self.assertEqual(["seen"],
                         names(shuffle.eligible_movies(self.movies, shuffle.MODE_REWATCH)))

    def test_any_other_mode_keeps_everything(self):
        result = shuffle.eligible_movies(self.movies, shuffle.MODE_CATCHUP)
        self.assertEqual(["seen", "unseen"], names(result))
        self.assertIsNot(self.movies, result, "should return a copy, not the caller's list")


class PickTest(KodiTestCase):
    def test_pick_returns_the_requested_count(self):
        pool = list(range(10))
        picked = shuffle.pick(pool, 3, rng=random.Random(1))
        self.assertEqual(3, len(picked))
        self.assertEqual(3, len(set(picked)), "picks must be distinct")
        self.assertTrue(set(picked).issubset(set(pool)))

    def test_asking_for_more_than_the_pool_returns_the_whole_pool(self):
        pool = list(range(4))
        picked = shuffle.pick(pool, 10, rng=random.Random(1))
        self.assertEqual(sorted(pool), sorted(picked))

    def test_pick_does_not_mutate_the_caller_s_pool(self):
        pool = list(range(6))
        original = list(pool)
        shuffle.pick(pool, 6, rng=random.Random(2))
        self.assertEqual(original, pool)

    def test_pick_is_seedable_and_shuffles(self):
        pool = list(range(20))
        first = shuffle.pick(pool, 20, rng=random.Random(7))
        second = shuffle.pick(pool, 20, rng=random.Random(7))
        self.assertEqual(first, second)
        self.assertNotEqual(pool, first, "a 20-item shuffle should not come back in order")

    def test_empty_pool(self):
        self.assertEqual([], shuffle.pick([], 5, rng=random.Random(1)))


class EpisodeHelpersTest(KodiTestCase):
    def test_unwatched_episodes_filters_watched_ones(self):
        episodes = [FakeEpisode(watched=True), FakeEpisode(watched=False)]
        self.assertEqual([episodes[1]], shuffle.unwatched_episodes(episodes))

    def test_unwatched_episodes_of_an_empty_list(self):
        self.assertEqual([], shuffle.unwatched_episodes([]))

    def test_first_regular_index_skips_leading_specials(self):
        episodes = [FakeEpisode(parentIndex=0), FakeEpisode(parentIndex=0),
                    FakeEpisode(parentIndex=1)]
        self.assertEqual(2, shuffle.first_regular_index(episodes))

    def test_first_regular_index_is_zero_when_the_first_is_already_regular(self):
        self.assertEqual(0, shuffle.first_regular_index([FakeEpisode(parentIndex=1)]))

    def test_first_regular_index_falls_back_to_zero_for_all_specials(self):
        episodes = [FakeEpisode(parentIndex=0), FakeEpisode(parentIndex=0)]
        self.assertEqual(0, shuffle.first_regular_index(episodes))

    def test_first_regular_index_of_an_empty_list(self):
        self.assertEqual(0, shuffle.first_regular_index([]))
