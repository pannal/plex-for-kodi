"""Weak bound-method reference for the Python 2 Kodi runtime.

Keep both the instance and function weak, as weakref.WeakMethod does on
Python 3. Holding the bound method itself would retain its owner.
"""
from __future__ import absolute_import

import weakref
from six import create_bound_method


class WeakMethod(weakref.ref):
    def __new__(cls, method):
        instance = weakref.ref.__new__(cls, method.__self__)
        instance._function = weakref.ref(method.__func__)
        return instance

    def __init__(self, method):
        # weakref.ref.__init__ must not receive the temporary bound method.
        pass

    def __call__(self):
        owner = weakref.ref.__call__(self)
        function = self._function()
        if owner is None or function is None:
            return None
        return create_bound_method(function, owner)
