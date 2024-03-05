# module gettags

from datetime import date
import json
import subprocess
import time

import cu.music.brainz
import cu.music.config
import cu.music.flac

class NoMatchingDiscId(Exception):
    def __init__(self, release_id, discid):
        self.release_id = release_id
        self.disc_id = discid

    def __str__(self):
        return (f'no association for disc {self.disc_id} '
                'to release {self._releaseid}')


def get_artist(r):
    credits = r['artist-credit']
    creditphrase = r['artist-credit-phrase']
    if False and len(credits) > 1:
        return (creditphrase, creditphrase, None)
    else:
        artist = credits[0]['artist']
        if artist['id'] == cu.music.brainz.VARIOUS_ARTISTS_ID:
            return ('Various', 'Various', artist['id'])
        else:
            artist = cu.music.brainz.get_artist_by_id(artist['id'])
            return (artist['name'], artist['sort-name'], artist['id'])


def get_tags(release, discid):
    album_tags = {}
    track_tags = {}

    if isinstance(release, str):
        release = cu.music.brainz.get_release_by_id(release)

    medium = cu.music.brainz.release_media_by_discid(release, discid)
    if medium is None:
        raise NoMatchingDiscId(release['id'], discid)

    album_tags["MUSICBRAINZ_ALBUMID"] = release['id']

    title = release['title']
    if release['medium-count'] > 1:
        # I don't like "Some Album Title (Enhanced CD 1)", especially if disc 2
        # isn't enhanced and so is "Some Album Title (CD 2)" and the two sort
        # incorrectly ('C' < 'E').  Maybe this should just be "... (Disc 1)"
        # instead.
        #
        # Also note that cu.music.output.truncate has 'CD' hardcoded into its
        # logic.
        #
        # medium_format = medium.get('format', 'CD')
        medium_format = 'CD'

        medium_position = medium['position']
        title = f'{title} ({medium_format} {medium_position})'

        album_tags["DISC"] = str(medium_position)
        album_tags["DISCC"] = str(release['medium-count'])

    album_tags["ALBUM"] = title

    albumartist, albumartistsort, albumartistid = get_artist(release)

    if albumartistid is not None:
        album_tags["MUSICBRAINZ_ALBUMARTISTID"] = albumartistid
        album_tags["MUSICBRAINZ_ARTISTID"] = albumartistid

    compilation = albumartistid == cu.music.brainz.VARIOUS_ARTISTS_ID

    if compilation:
        album_tags["COMPILATION"] = "1"

    album_tags["ARTIST"] = albumartist
    album_tags["ARTISTSORT"] = albumartistsort

    if release.get('asin') is not None:
        album_tags["ASIN"] = release['asin']

    if 'date' in release:
        when = None

        for format in ('%Y-%m-%d', '%Y-%m', '%Y'):
            try:
                when = time.strptime(release['date'], format)
                break
            except ValueError:
                pass

        if when is not None:
            album_tags["DATE"] = date(*when[0:3]).strftime("%Y-%m-%d")

    album_tags["MUSICBRAINZ_DISCID"] = discid

    albumartist, albumartistsort, albumartistid = get_artist(release)

    if medium is None:
        print(json.dumps(release, sort_keys=True, indent=4))
        print(discid)

    for track in medium['track-list']:
        recording = track['recording']
        recording = cu.music.brainz.get_recording_by_id(recording['id'])

        tags = {}

        tags["MUSICBRAINZ_TRACKID"] = recording['id']
        tags["TITLE"] = recording['title']
        tags["TRACKNUMBER"] = track['position']

        if 'artist-credit' in recording:
            trackartist, trackartistsort, trackartistid = get_artist(recording)

            # Sadly, do this only for Various Artists album.  It makes
            # slimserver turn "Greatest Hits" by Linda Ronstadt into a
            # "Various Artists" album because the artist for
            # "Different Drum" is the Stone Poneys.  Better to lose that
            # track metadata than to miscategorize the album.
            if compilation:
                tags["ARTIST"] = trackartist
                tags["ARTISTSORT"] = trackartistsort

            if trackartistid is not None and trackartistid != albumartistid:
                tags["MUSICBRAINZ_ARTISTID"] = trackartistid

        track_tags[int(track['position'])] = tags

    return (album_tags, track_tags)


def flac_combined_tags(album_tags, track_tags):
    combined_tags = {
        f'{tag}[{track:02d}]': value
        for track, tags in track_tags.items()
        for tag, value in tags.items()
    }
    combined_tags.update(album_tags)
    return combined_tags


def flac_separate_tags(combined_tags):
    album_tags = {}
    track_tags = {}

    for tag, value in combined_tags.items():
        if '[' in tag:
            if not tag.endswith(']'):
                continue
            tag, _, track_str = tag[:-1].partition('[')
            try:
                track = int(track_str)
            except ValueError:
                pass
            track_tags.setdefault(track, {})[tag] = value
        else:
            album_tags[tag] = value

    return album_tags, track_tags


def get_flac_tags(flacfile):
    args = [cu.music.config.metaflac_program, "--export-tags-to=-", flacfile]
    subp = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL,
                          check=True)

    tags = {}
    for line in subp.stdout.decode('utf8').splitlines():
        tag, equals, value = line.partition('=')
        if equals:
            tags[tag] = value

    return tags


def flac_tag_args(album_tags, track_tags, tag_option='tag'):
    combined_tags = flac_combined_tags(album_tags, track_tags)
    tags = sorted(combined_tags.keys())
    return [f'--{tag_option}={tag}={combined_tags[tag]}' for tag in tags]


def flac_track_tag(combined_tags, track, tag):
    return combined_tags.get(f'{tag}[{track:02d}]', combined_tags.get(tag))


def year_tag(album_tags):
    year = album_tags.get(cu.music.flac.FlacTags.YEAR,
                          album_tags.get(cu.music.flac.FlacTags.DATE))
    if year is None:
        return None
    year = year[:4]
    if not year:
        return None
    return year


def track_count(track_tags, default=None):
    if not track_tags:
        return default
    return max(track_tags.keys())
