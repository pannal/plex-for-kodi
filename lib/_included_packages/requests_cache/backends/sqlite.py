#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    requests_cache.backends.sqlite
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    ``sqlite3`` cache backend
"""
import os

from .base import BaseCache
from .storage.dbdict import DbDict, DbPickleDict, sqlite, DbJSONDict


class DbCache(BaseCache):
    """ sqlite cache backend.

    Reading is fast, saving is a bit slower. It can store big amount of data
    with low memory usage.
    """
    def __init__(self, location='cache',
                 fast_save=False, extension='.sqlite', **options):
        """
        :param location: database filename prefix (default: ``'cache'``)
        :param fast_save: Speedup cache saving up to 50 times but with possibility of data loss.
                          See :ref:`backends.DbDict <backends_dbdict>` for more info
        :param extension: extension for filename (default: ``'.sqlite'``)
        """
        super(DbCache, self).__init__(**options)
        tries = 0
        while tries < 2:
            try:
                self.responses = DbPickleDict(location + extension, 'responses', fast_save=fast_save)
                break
            except sqlite.DatabaseError:
                tries += 1
                # DB corrupted
                try:
                    os.remove(location + extension)
                except OSError:
                    pass
        self.keys_map = DbDict(location + extension, 'urls', fast_save=fast_save)
        self.other = DbJSONDict(location + extension, 'other', fast_save=fast_save)

    def vacuum(self):
        self.responses.vacuum()

    def clear(self):
        super(DbCache, self).clear()
        self.other.clear()
