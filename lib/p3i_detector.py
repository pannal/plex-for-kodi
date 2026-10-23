from __future__ import absolute_import

import json
import threading
from kodi_six import xbmc

# Optional p3i admission support. Stock Kodi is probed only once, and a missing
# extension never changes ordinary playback or emits unsupported-call loops.
_supported = None
_job_supported = None
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


def job_supported():
    global _job_supported
    with _lock:
        if _job_supported is None:
            result = _rpc('GetCapabilities') or {}
            _job_supported = bool(result.get('version') == 1 and result.get('supported') and
                                  (result.get('resultbinding') or 0) >= 1)
        return _job_supported


def start(path):
    if not job_supported():
        return None
    result = _rpc('Start', {'path': path,
                            'options': {'streamindex': -1, 'allowhttp': True}}) or {}
    return result.get('requestid') if result.get('status') == 'accepted' else None


def status(requestid):
    return _rpc('GetStatus', {'requestid': requestid})


def bind(requestid, path):
    if not job_supported():
        return None
    result = _rpc('Bind', {'requestid': requestid, 'path': path,
                           'options': {'association': 'source', 'streamindex': -1}}) or {}
    if result.get('status') == 'ready' and result.get('bindingid'):
        return {'property': result.get('property', 'p3i.detector.binding'),
                'bindingid': result['bindingid']}
    return None


def release(bindingid):
    if bindingid is not None:
        _rpc('ReleaseBinding', {'bindingid': bindingid})


def cancel(requestid):
    if requestid is not None:
        _rpc('Cancel', {'requestid': requestid})
