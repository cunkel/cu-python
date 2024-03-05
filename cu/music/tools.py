import argparse
import pprint
import sys

try:
    import mutagen
except ImportError:
    mutagen = None

import cu.music.artists
import cu.music.brainz
import cu.music.paths
import cu.music.tags


def flac_artist_id(flac):
    return cu.music.tags.get_flac_tags(flac).get('MUSICBRAINZ_ARTISTID')


def all_album_artist_ids():
    return set(artist_id
               for flac in cu.music.paths.all_flac_files()
               if (artist_id := flac_artist_id(flac)) is not None)


def all_album_artists():
    return [cu.music.brainz.get_artist_by_id(artist_id)
            for artist_id in all_album_artist_ids()]


def list_artists(args):
    sorted_artists = sorted(all_album_artists(),
                            key=lambda x: (x['sort-name'], x['id']))
    for artist in sorted_artists:
        print(artist['id'], artist['name'])


def rg_is_basic_album(release_group):
    return (release_group.get('primary-type') == 'Album'
            and not release_group.get('secondary-type-list'))


def album_ownership(args):
    artists = {}
    albums = {}
    have_release_groups = set()

    for flac in sorted(cu.music.paths.all_flac_files()):
        tags = cu.music.tags.get_flac_tags(flac)
        artist_id = tags.get('MUSICBRAINZ_ARTISTID')
        album_id = tags.get('MUSICBRAINZ_ALBUMID')
        title = tags.get('ALBUM', '')

        if (album_id is None
                or artist_id is None
                or artist_id == cu.music.brainz.VARIOUS_ARTISTS_ID
                or cu.music.artists.is_classical_composer(artist_id)):
            continue

        albums[album_id] = title
        if artist_id not in artists:
            artists[artist_id] = cu.music.brainz.get_artist_by_id(artist_id)

        release = cu.music.brainz.get_release_by_id(album_id)
        release_group_id = release['release-group']['id']
        have_release_groups.add(release_group_id)

    sorted_artists = sorted(artists.values(),
                            key=lambda x: (x['sort-name'], x['id']))

    for artist in sorted_artists:
        artist_id = artist['id']
        print(artist['name'])

        basic_albums = sorted(
            (rg for rg in cu.music.brainz.release_groups_by_artist(artist_id)
             if rg_is_basic_album(rg)),
            key=lambda x: x.get('first-release-date', ''))
        for rg in basic_albums:
            have = '*' if rg['id'] in have_release_groups else ' '
            print(f"{have} {rg['first-release-date']:<10} {rg['title']}")

        print()

        # I like to run this into a tee and still see output promptly.
        sys.stdout.flush()


def extract_coverart(args):
    if mutagen is None:
        print('need mutagen', file=sys.stderr)
        return 1

    flac = mutagen.flac.FLAC(args.flac_file)
    album_id = flac.tags.get('MUSICBRAINZ_ALBUMID')
    if album_id:
        album_id = album_id[0]
    else:
        return 1

    for picture in flac.pictures:
        if picture.type == 3 and picture.mime == 'image/jpeg':
            jpeg = os.path.join(args.dest_dir, f'{album_id}.jpg')
            with open(jpeg, 'wb') as f:
                f.write(picture.data)
            print(album_id, jpeg)


def reset_mtime(args):
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    tags = cu.music.tags.get_flac_tags(args.flac_file)
    discid = tags['MUSICBRAINZ_DISCID']

    flac_stat = os.stat(args.flac_file)

    urlfile = cu.music.paths.url_path(discid)
    cuesheet = cu.music.paths.cue_path(discid)
    flac_dir = os.path.dirname(args.flac_file) or '.'

    for ref in (urlfile, cuesheet, flac_dir):
        try:
            ref_stat = os.stat(ref)
        except NoSuchFileError:
            pass
        break
    else:
        return 1

    os.utime(args.flac_file,
             ns=(flac_stat.st_atime_ns, ref_stat.st_mtime_ns+60000000000))


def main():
    ap = argparse.ArgumentParser()

    subp = ap.add_subparsers()

    parser_list_artists = subp.add_parser('list-artists')
    parser_list_artists.set_defaults(func=list_artists)

    parser_unowned_albums = subp.add_parser('album-ownership')
    parser_unowned_albums.set_defaults(func=album_ownership)

    parser_extract_coverart = subp.add_parser('extract-coverart')
    parser_extract_coverart.set_defaults(func=extract_coverart)
    parser_extract_coverart.add_argument('--dest-dir', default='')
    parser_extract_coverart.add_argument('flac_file')

    parser_reset_mtime = subp.add_parser('reset-mtime')
    parser_reset_mtime.set_defaults(func=reset_mtime)
    parser_reset_mtime.add_argument('flac_file')

    args = ap.parse_args()

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main() or 0)
