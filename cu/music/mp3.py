import os
import sys
import subprocess

import mutagen.easyid3
import mutagen.mp3

import cu.music.config
from cu.music.brainz import VARIOUS_ARTISTS_ID
from cu.music.flac import FlacTags
from cu.music.tags import (get_flac_tags, flac_separate_tags, track_count,
                           year_tag)
from cu.util.file import remove_if_exists


# Probably this should be called Id3v2 tags or something like that.
class Mp3Tags:
    ALBUM_TITLE = 'TALB'

    # Technically "album sort" not "album title sort"?
    ALBUM_TITLE_SORT = 'TSOA'

    ALBUM_ARTIST = 'TPE2' # '
    ALBUM_ARTIST_SORT = 'TSO2'

    DISC_INDEX_AND_COUNT = 'TPOS'

    DATE = 'TDAT' # In what format?  YYYY-MM-DD?
    YEAR = 'TYER'

    COMPILATION = 'TCMP'  # 0/1

    TRACK_TITLE = 'TIT2'

    TRACK_ARTIST = 'TPE1'
    TRACK_ARTIST_SORT = 'TSOP'

    TRACK_INDEX_AND_COUNT = 'TRCK'

    CONDUCTOR = 'TPE3'

    MOVEMENT_INDEX_AND_COUNT = 'MVIN'
    MOVEMENT_NAME = 'MVNM'

    COMPOSER = 'TCOM'
    COMPOSER_SORT = 'TSOC'

    ENCODED_BY = 'TENC'
    ENCODER_SETTINGS = 'TSSE'

    COVER_ART = 'APIC'  # no easymp3 support?


FRAME_CLASSES = {
    'APIC': mutagen.id3.APIC,
    'MVIN': mutagen.id3.MVIN,
    'MVNM': mutagen.id3.MVNM,
    'TALB': mutagen.id3.TALB,
    'TCMP': mutagen.id3.TCMP,
    'TCOM': mutagen.id3.TCOM,
    'TDAT': mutagen.id3.TDAT,
    'TENC': mutagen.id3.TENC,
    'TIT2': mutagen.id3.TIT2,
    'TPE1': mutagen.id3.TPE1,
    'TPE2': mutagen.id3.TPE2,
    'TPE3': mutagen.id3.TPE3,
    'TPOS': mutagen.id3.TPOS,
    'TRCK': mutagen.id3.TRCK,
    'TSO2': mutagen.id3.TSO2,
    'TSOA': mutagen.id3.TSOA,
    'TSOC': mutagen.id3.TSOC,
    'TSOP': mutagen.id3.TSOP,
    'TSSE': mutagen.id3.TSSE,
    'TYER': mutagen.id3.TYER,
}


def disc_count_and_index(album_tags):
    index = album_tags.get(FlacTags.DISC_INDEX)
    count = album_tags.get(FlacTags.DISC_COUNT)

    if index is None:
        return None
    elif count is None:
        return str(index)
    else:
        return f'{index}/{count}'


def track_count_and_index(track_tags, index):
    count = track_count(track_tags)

    if index is None:
        return None
    elif count is None:
        return str(index)
    else:
        return f'{index}/{count}'


def mp3_track_tags(flac_tags, track):
    album_tags, track_tags = flac_separate_tags(flac_tags)

    def album_tag(tag):
        return album_tags.get(tag)

    def track_tag(tag):
        return track_tags.get(track, {}).get(tag, album_tags.get(tag))

    is_various_artists = (album_tags.get(FlacTags.MB_ARTIST_ID)
                          == VARIOUS_ARTISTS_ID)

    tags = {
        Mp3Tags.ALBUM_TITLE: album_tag(FlacTags.ALBUM_TITLE),
        Mp3Tags.ALBUM_ARTIST: album_tag(FlacTags.ARTIST),
        Mp3Tags.ALBUM_ARTIST_SORT: album_tag(FlacTags.ARTIST_SORT),

        Mp3Tags.DISC_INDEX_AND_COUNT: disc_count_and_index(album_tags),

        Mp3Tags.YEAR: year_tag(album_tags),
        Mp3Tags.COMPILATION: '1' if (FlacTags.COMPILATION in album_tags
                                     or is_various_artists) else '0',

        Mp3Tags.TRACK_TITLE: track_tag(FlacTags.TRACK_TITLE),
        Mp3Tags.TRACK_INDEX_AND_COUNT: track_count_and_index(
            track_tags, track),

        Mp3Tags.TRACK_ARTIST: track_tag(FlacTags.ARTIST),

        # id3v2.4 per mutagen, but we're trying to write id3v2.3
        # Mp3Tags.TRACK_ARTIST_SORT: track_tag(FlacTags.ARTIST_SORT),
    }

    for tag in [tag for tag, value in tags.items() if value is None]:
        del tags[tag]

    return tags


def is_latin1(s):
    return s == s.encode('iso8859-1', errors='ignore').decode('iso8859-1')


LAME_COMMAND_TAGS = {
    '--tt': Mp3Tags.TRACK_TITLE,
    '--ta': Mp3Tags.TRACK_ARTIST,
    '--tl': Mp3Tags.ALBUM_ARTIST,
    '--ty': Mp3Tags.YEAR,
    '--tn': Mp3Tags.TRACK_INDEX_AND_COUNT,
}


def lame_tag_options(mp3_tags):
    options = ["--add-id3v2", "--id3v2-only", "--ignore-tag-errors"]

    selected_encoding = None  # maybe starts in latin-1, but unsure

    for option, tag in LAME_COMMAND_TAGS.items():
        value = mp3_tags.get(tag)
        if value is None:
            continue

        if is_latin1(value):
            desired_encoding = 'latin1'
        else:
            desired_encoding = 'utf16'

        if desired_encoding != selected_encoding:
            # This selects the format in the id3v2 tag.  The format on the
            # command line should be per the current locale, probably utf8,
            # and hopefully matching how subprocess.run encodes arguments.
            options.append(f'--id3v2-{desired_encoding}')
            selected_encoding = desired_encoding

        options.append(option)
        options.append(value)

    return options


def create_mp3(flac_file, track, mp3_file, mp3_tags, compress_options=None):
    if compress_options is None:
        compress_options = ['--preset', 'standard', '--quiet']

    wav_file = mp3_file + '.wav'

    tag_options = lame_tag_options(mp3_tags)

    extract_wav = [cu.music.config.flac_program,
                   "-f", "-d", "--cue=%d.1-%d.1" % (track, track+1),
                   "-o", wav_file, flac_file]
    compress = [cu.music.config.lame_program,
                *compress_options, *tag_options,
                wav_file, mp3_file]

    os.makedirs(os.path.dirname(mp3_file), exist_ok=True)

    try:
        subprocess.run(extract_wav, check=True, stdin=subprocess.DEVNULL)
        try:
            subprocess.run(compress, check=True, stdin=subprocess.DEVNULL)
        except Exception:
            remove_if_exists(mp3_file)
            raise
    finally:
        remove_if_exists(wav_file)


IGNORE_TAGS = {Mp3Tags.ENCODED_BY, Mp3Tags.ENCODER_SETTINGS, Mp3Tags.COVER_ART}


def create_text_frame(frame_class, s):
    assert issubclass(frame_class, mutagen.id3.TextFrame)
    if is_latin1(s):
        encoding = mutagen.id3.Encoding.LATIN1
    else:
        encoding = mutagen.id3.Encoding.UTF16
    return frame_class(encoding=encoding, text=s)


def update_mp3_tags(mp3_file, mp3_tags):
    mp3_tags = dict(mp3_tags)

    if mp3_tags.get(Mp3Tags.COMPILATION) == '0':
        del mp3_tags[Mp3Tags.COMPILATION]

    changed = False

    mp3 = mutagen.mp3.MP3(mp3_file, v2_version=3, translate=False)
    if mp3.tags.version[:2] != (2, 3):
        changed = True

    for tag, desired in sorted(mp3_tags.items()):
        frames = mp3.tags.getall(tag)
        if len(frames) == 1:
            if frames[0].text == [desired]:
                # print('ok', tag, repr(desired), repr(frames[0].text))
                continue
        # print('update:', tag, desired, repr(frames), file=sys.stderr)
        mp3.tags.setall(tag, [create_text_frame(FRAME_CLASSES[tag], desired)])
        changed = True

    to_delete = []
    for tag in mp3.tags:
        if tag == Mp3Tags.COMPILATION:
            frames = mp3.tags.getall(tag)
            if len(frames) == 1 and frames[0].text == '0':
                continue
        if tag not in mp3_tags and tag not in IGNORE_TAGS:
            # print('delete:', tag, repr(frames), file=sys.stderr)
            to_delete.append(tag)

    if to_delete:
        for tag in to_delete:
            mp3.tags.delall(tag)
        changed = True

    if changed:
        print('update tags:', mp3_file)
        mp3.tags.update_to_v23()
        mp3.save(v2_version=3)
        sys.stdout.flush()


def create_or_update_mp3(flac_file, track, mp3_file, compress_options=None):
    combined_tags = get_flac_tags(flac_file)
    mp3_tags = mp3_track_tags(combined_tags, track)

    # We don't reencode if the underlying flac file has changed.  Typically
    # that's a metadata update anyway.
    if not os.path.exists(mp3_file):
        create_mp3(flac_file, track, mp3_file, mp3_tags,
                   compress_options=compress_options)

    # FAAC only understands a subset of tags, so even right after creation we
    # need to retag.
    update_mp3_tags(mp3_file, mp3_tags)
