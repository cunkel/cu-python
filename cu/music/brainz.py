import functools
import os
from urllib.parse import urlparse
import sys

import musicbrainzngs
import musicbrainzngs.musicbrainz as mb

import cu.music.cache
import cu.music.paths
import cu.util.func


VARIOUS_ARTISTS_ID = '89ad4ac3-39f7-470e-963a-56509c546377'
VARIOUS_ARTISTS_URL = ('http://musicbrainz.org/artist/' + VARIOUS_ARTISTS_ID)


_mb_cache = cu.music.cache.Cache(
    os.path.join(cu.music.paths.cache_dir(), 'musicbrainz.sqlite3'))


def init_musicbrainz():
    musicbrainzngs.set_useragent(
        'Python FLAC Manager/0.2',
        'http://suif.stanford.edu/cunkel/music'
    )


ensure_musicbrainz_init = cu.util.func.Once(init_musicbrainz)


# Used to be musicbrainz2.utils.extractUuid.
def extract_uuid(uri):
    """id from musicbrainz uri"""
    parse = urlparse(uri)

    if not parse.scheme:
        return uri

    if parse.scheme != 'http' or parse.netloc != 'musicbrainz.org':
        raise ValueError(f'{uri} is not a valid MusicBrainz ID')

    parts = parse.path.split('/')
    if len(parts) != 3 or parts[0] != '':
        raise ValueError(f'{uri} is not a valid MusicBrainz ID')

    return parts[2]


def release_media_by_discid(release, discid):
    for m in release['medium-list']:
        if any(d['id'] == discid for d in m['disc-list']):
            return m
    return None


def release_discid_media_position(release, discid):
    media = release_media_by_discid(release, discid)
    return int(media['position'])


def release_discid_sequence(release, discid):
    position = release_discid_media_position(release, discid)
    if release['medium-count'] > 1 or position > 1:
        return position

    return None


def uses_musicbrainz(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        ensure_musicbrainz_init()

        return f(*args, **kwargs)

    return wrapped


def _get_cached(get_func, type_, id_, includes):
    obj = _mb_cache.get(type_, id_, includes)
    if obj is None:
        print('fetch', type_, id_, file=sys.stderr)
        obj = get_func(id_, includes)[type_]
        _mb_cache.put(type_, id_, includes, obj)
    return obj


@uses_musicbrainz
def get_recording_by_id(recording_id):
    includes = ['artists']
    return _get_cached(mb.get_recording_by_id,
                       'recording', recording_id, includes)


@uses_musicbrainz
def get_release_by_id(release_id):
    includes = ['artists', 'discids', 'media', 'recordings', 'release-groups']
    return _get_cached(mb.get_release_by_id,
                       'release', release_id, includes)


@uses_musicbrainz
def get_artist_by_id(artist_id):
    includes = []
    return _get_cached(mb.get_artist_by_id,
                       'artist', artist_id, includes)


# Uncached, but if we changed the includes to match those in get_release_by_id,
# we could cache the returned releases themselves?
@uses_musicbrainz
def get_releases_by_discid(discid):
    # It seems like mb.get_releases_by_discid should return a list of releases
    # at the top, but it actually returns a single disc object (in the usual
    # way as {'disc': {...}}) with 'release-list' populated.
    return mb.get_releases_by_discid(discid, includes=[],
                                     cdstubs=False)['disc']


def _get_paginated_browse(browse_func, prefix, limit=50,
                          /, *args, **kwargs):
    offset = 0
    count = None

    result = []

    while count is None or offset < count:
        page = browse_func(*args, **kwargs, limit=limit, offset=offset)
        count = page[f'{prefix}-count']
        result += page[f'{prefix}-list']
        offset += limit

        if len(page[f'{prefix}-list']) < limit:
            break  # we also expect offset < count next time around

    return result


@uses_musicbrainz
def release_groups_by_artist(artist_id):
    return _get_paginated_browse(mb.browse_release_groups, 'release-group',
                                 artist=artist_id)
