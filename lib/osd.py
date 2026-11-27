# coding=utf-8
"""Optional p3i geometry for protecting marker overlays from active-area cropping."""
from __future__ import absolute_import

import json
import math

import six
from kodi_six import xbmc


def _integer(value):
    return isinstance(value, six.integer_types) and not isinstance(value, bool)


def _snapshot(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if (not _integer(data.get('version')) or data['version'] != 1 or
                data.get('coordinate_system') != 'gui-1080' or
                data.get('width') != 1920 or data.get('height') != 1080 or
                data.get('valid') is not True):
            return None
        edges = [data.get(key) for key in ('left', 'top', 'right', 'bottom')]
        for edge in edges:
            if (isinstance(edge, bool) or not isinstance(edge, six.integer_types + (float,)) or
                    math.isnan(edge) or math.isinf(edge)):
                return None
        if edges[0] >= edges[2] or edges[1] >= edges[3]:
            return None
        return data
    except (ValueError, TypeError, OverflowError):
        return None


def markerNeedsOSD(window_id, control_id):
    """Signal on any protruding edge, or if either fresh snapshot is unavailable.

    The caller owns marker visibility. Never fall back to a previously read
    rectangle, source L5 offsets or Python control positions.
    """
    if (not _integer(window_id) or not 0 < window_id <= 0x7FFFFFFF or
            not _integer(control_id) or not 0 < control_id <= 0xFFFFFF):
        return True
    try:
        picture = _snapshot(xbmc.getInfoLabel('Player.Process(video.active.picture)'))
        button = _snapshot(xbmc.getInfoLabel(
            'Control.GetRenderBounds({},{})'.format(window_id, control_id)))
    except RuntimeError:
        return True
    if picture is None or button is None:
        return True
    if (not _integer(button.get('window_id')) or button['window_id'] != window_id or
            not _integer(button.get('control_id')) or button['control_id'] != control_id or
            not _integer(button.get('instance')) or button['instance'] <= 0 or
            button.get('visible') is not True):
        return True
    return not (picture['left'] <= button['left'] and picture['top'] <= button['top'] and
                button['right'] <= picture['right'] and button['bottom'] <= picture['bottom'])
