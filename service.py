# -*- coding: utf-8 -*-
from __future__ import absolute_import
try:
    from importlib import reload
except ImportError:
    try:
        from imp import reload
    except ImportError:
        pass
        # python 2.7 has "reload" natively

import lib.service_runner as runner


if __name__ == '__main__':
    restarting_service = False
    while 1:
        if runner.main(restarting_service=restarting_service):
            reload(runner)
            restarting_service = True
        else:
            break
