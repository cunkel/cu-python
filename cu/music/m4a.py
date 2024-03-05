import os
import sys
import subprocess

import mutagen.mp4

import cu.music.config
from cu.music.brainz import VARIOUS_ARTISTS_ID
from cu.music.flac import FlacTags
from cu.music.tags import (get_flac_tags, flac_separate_tags, track_count,
                           year_tag)
from cu.util.file import remove_if_exists


class M4aTags:
    ALBUM_TITLE = '\xa9alb'
    ALBUM_ARTIST = 'aART'
    ALBUM_ARTIST_SORT = 'soaa'

    DISC_INDEX_AND_COUNT = 'disk'

    YEAR = '\xa9day'
    COMPILATION = 'cpil'

    SHOW_SORT = 'sosn'

    TRACK_TITLE = '\xa9nam'
    TRACK_INDEX_AND_COUNT = 'trkn'

    TRACK_ARTIST = '\xa9ART'
    TRACK_ARTIST_SORT = 'soar'

    COMPOSER = '\xa9wrt'
    COMPOSER_SORT = 'soco'

    WORK = '\xa9wrk'
    MOVEMENT = '\xa9'

    MOVEMENT_INDEX = '\xa9mvi'
    MOVEMENT_COUNT = '\xa9mvc'

    COVER_ART = 'covr'
    ENCODED_BY = '\xa9too'


def disc_count_and_index(album_tags):
    index = album_tags.get(FlacTags.DISC_INDEX)
    count = album_tags.get(FlacTags.DISC_COUNT)

    if index is None or count is None:
        return None

    return (int(index), int(count))


def track_count_and_index(track_tags, index):
    count = track_count(track_tags)

    if count is None:
        return None

    return (index, count)


def m4a_track_tags(flac_tags, track):
    # Top-level note: we produce the m4a tags from the FLAC tags.  This means
    # that if we need to do some contortion in the FLAC tags to get the right
    # behavior out of SlimServer/Roon/whatever, that contortion affects this
    # logic.  Another approach would be to compute the m4a tags directly from
    # the (cached) MusicBrainz metadata.
    album_tags, track_tags = flac_separate_tags(flac_tags)

    def album_tag(tag):
        return album_tags.get(tag)

    def track_tag(tag):
        return track_tags.get(track, {}).get(tag, album_tags.get(tag))

    is_various_artists = (album_tags.get(FlacTags.MB_ARTIST_ID)
                          == VARIOUS_ARTISTS_ID)

    tags = {
        M4aTags.ALBUM_TITLE: album_tag(FlacTags.ALBUM_TITLE),
        M4aTags.ALBUM_ARTIST: album_tag(FlacTags.ARTIST),
        M4aTags.ALBUM_ARTIST_SORT: album_tag(FlacTags.ARTIST_SORT),

        M4aTags.DISC_INDEX_AND_COUNT: disc_count_and_index(album_tags),

        M4aTags.YEAR: year_tag(album_tags),
        M4aTags.COMPILATION: (FlacTags.COMPILATION in album_tags
                              or is_various_artists),

        M4aTags.TRACK_TITLE: track_tag(FlacTags.TRACK_TITLE),
        M4aTags.TRACK_INDEX_AND_COUNT: track_count_and_index(
            track_tags, track),

        M4aTags.TRACK_ARTIST: track_tag(FlacTags.ARTIST),
        M4aTags.TRACK_ARTIST_SORT: track_tag(FlacTags.ARTIST_SORT),
    }

    # We used to do this because we didn't set the compilation flag--or the
    # album artist.  But now we do, and compilations show up in the
    # "Compilations" section in Music, with the correct artist at the track,
    # and everything is happy.
    if False and is_various_artists:
        title = tags.get(M4aTags.TRACK_TITLE)
        artist = tags.get(M4aTags.TRACK_ARTIST)

        M4aTags.ALBUM_ARTIST = 'Various'
        M4aTags.ALBUM_ARTIST_SORT = 'Various'
        M4aTags.TRACK_ARTIST = 'Various'
        M4aTags.TRACK_ARTIST_SORT = 'Various'

        if prior_title and prior_artist:
            tags[M4aTags.TRACK_TITLE] = f'{prior_artist} - {prior_title}'

    for tag in [tag for tag, value in tags.items() if value is None]:
        del tags[tag]

    return tags


FAAC_COMMAND_TAGS = {
    'artist': M4aTags.ALBUM_ARTIST,
    'composer': M4aTags.COMPOSER,
    'title': M4aTags.TRACK_TITLE,
    'album': M4aTags.ALBUM_TITLE,
    'track': M4aTags.TRACK_INDEX_AND_COUNT,
    'compilation': M4aTags.COMPILATION,
    'disc': M4aTags.DISC_INDEX_AND_COUNT,
    'year': M4aTags.YEAR,
}


def faac_tag_options(m4a_tags):
    options = ['-w']
    for option, tag in FAAC_COMMAND_TAGS.items():
        value = m4a_tags.get(tag)
        if value is None:
            continue
        options.append(f'--{option}')
        if isinstance(value, bool):
            pass  # no value to (compilation) flag
        elif isinstance(value, tuple):
            # Only tuples we know currently are index/total form.
            index, count = value
            options.append(f'{index}/{count}')
        else:
            options.append(str(value))

    return options


def create_m4a(flac_file, track, aac_file, m4a_tags, compress_options=None):
    if compress_options is None:
        compress_options = ['-q', '100']

    wav_file = aac_file + '.wav'

    tag_options = faac_tag_options(m4a_tags)

    extract_wav = [cu.music.config.flac_program,
                   "-f", "-d", "--cue=%d.1-%d.1" % (track, track+1),
                   "-o", wav_file, flac_file]
    compress = [cu.music.config.faac_program,
                *compress_options, *tag_options,
                "-o", aac_file, wav_file]

    os.makedirs(os.path.dirname(aac_file), exist_ok=True)

    try:
        subprocess.run(extract_wav, check=True, stdin=subprocess.DEVNULL)
        try:
            subprocess.run(compress, check=True, stdin=subprocess.DEVNULL)
        except Exception:
            remove_if_exists(aac_file)
            raise
    finally:
        remove_if_exists(wav_file)


IGNORE_TAGS = {M4aTags.ENCODED_BY, M4aTags.COVER_ART}


def update_m4a_tags(m4a_file, m4a_tags):
    m4a_tags = dict(m4a_tags)
    if M4aTags.COMPILATION in m4a_tags and not m4a_tags[M4aTags.COMPILATION]:
        del m4a_tags[M4aTags.COMPILATION]

    m4a = mutagen.mp4.MP4(m4a_file)

    changed = False

    for tag, desired in sorted(m4a_tags.items()):
        if tag != M4aTags.COMPILATION:
            desired = [desired]
        actual = m4a.tags.get(tag)
        match = actual == desired
        if not match:
            # print('update:', tag, desired, actual, file=sys.stderr)
            sys.stdout.flush()
            try:
                m4a.tags[tag] = desired
                # print('update:', tag, desired, actual, file=sys.stderr)
            except Exception as e:
                print('update:', tag, desired, actual, e)
                raise
            changed = True
        else:
            pass
            # print('ok:', tag, desired, actual, file=sys.stderr)
    for tag, actual in m4a.tags.items():
        if tag == M4aTags.COMPILATION and not actual:
            continue
        if tag not in m4a_tags and tag not in IGNORE_TAGS:
            # print('delete:', tag, actual, file=sys.stderr)
            del m4a.tags[tag]
            changed = True
    if changed:
        print('update tags:', m4a_file)
        m4a.save()


def create_or_update_m4a(flac_file, track, m4a_file, compress_options=None):
    combined_tags = get_flac_tags(flac_file)
    m4a_tags = m4a_track_tags(combined_tags, track)

    # We don't reencode if the underlying flac file has changed.  Typically
    # that's a metadata update anyway.
    if not os.path.exists(m4a_file):
        create_m4a(flac_file, track, m4a_file, m4a_tags,
                   compress_options=compress_options)

    # FAAC only understands a subset of tags, so even right after creation we
    # need to retag.
    update_m4a_tags(m4a_file, m4a_tags)
