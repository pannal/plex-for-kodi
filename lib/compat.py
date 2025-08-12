from __future__ import absolute_import
import time
import datetime

try:
    datetime.datetime.strptime('0', '%H')
    new_datetime = datetime.datetime
except TypeError:
    # Fix for datetime issues with XBMC/Kodi
    class new_datetime(datetime.datetime):
        @classmethod
        def strptime(cls, dstring, dformat):
            return datetime.datetime(*(time.strptime(dstring, dformat)[0:6]))

    datetime.datetime = new_datetime


def timedelta_total_seconds(td):
    try:
        return td.total_seconds()
    except:
        return ((float(td.seconds) + float(td.days) * 24 * 3600) * 10**6) / 10**6
