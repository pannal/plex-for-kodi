from __future__ import absolute_import

import json
import threading
from kodi_six import xbmc

# Optional p3i admission support. Stock Kodi is probed only once, and a missing
# extension never changes ordinary playback or emits unsupported-call loops.
_supported = None
_lock = threading.Lock()


def _rpc(method, params=None):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'P3I.Detector.' + method}
    if params is not None:
        request['params'] = params
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        result = response.get('result')
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def supported():
    global _supported
    with _lock:
        if _supported is None:
            result = _rpc('GetCapabilities') or {}
            _supported = bool(result.get('version') == 1 and result.get('supported') and
                              result.get('ownedskip'))
        return _supported


def arm_skip():
    if not supported():
        return None
    result = _rpc('SetSkipNext') or {}
    return result.get('token') if result.get('status') == 'armed' else None


def clear_skip(token):
    if token is not None:
        # Kodi compares this publication token atomically. Old failure/Stop
        # callbacks cannot clear another request's newer Home-property signal.
        _rpc('ClearSkipNext', {'token': token})
