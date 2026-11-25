# coding=utf-8
from __future__ import absolute_import

RT_PREFIX = 'rottentomatoes:'


def sanitize(image):
    return image.replace('themoviedb', 'tmdb').replace('://', '/')


def format_value(image, value):
    if image.startswith(RT_PREFIX):
        return '{0}%'.format(int(float(value) * 10))
    return str(value)


def image_path(image):
    if not image:
        return ''
    return 'script.plex/ratings/{0}.png'.format(sanitize(image))


def slot_name(i):
    return 'rating' if i == 1 else 'rating{0}'.format(i)


def build_rating_properties(entries):
    """Transform (image, value) pairs into numbered display properties.

    Returns an ordered list of (property_name, property_value) tuples,
    always ending with ('rating.count', str(count)). Entries with an empty
    value are skipped; entries with an empty image set the value only.
    """
    props = []
    count = 0
    for image, value in entries:
        if value in (None, ''):
            continue
        count += 1
        name = slot_name(count)
        props.append((name, format_value(image, value)))
        path = image_path(image)
        if path:
            props.append((name + '.image', path))
    props.append(('rating.count', str(count)))
    return props
