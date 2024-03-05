import argparse
import os
import sys

from cu.music.brainz import extract_uuid
from cu.music.encode import (choose_release_for_discid,
                             MultipleMatchingReleases, NoSuchDisc,
                             NoMatchingRelease)
import cu.music.paths
import cu.music.retag
from cu.music.tags import (get_flac_tags, get_tags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--if-mismatch', action='store_true',
        help='only operate on files without current discid/release match')
    ap.add_argument(
        '--move', action='store_true',
        help='move files to new path')
    ap.add_argument('--preserve-timestamps', '-p',
                    action='store_true', dest='preserve')
    ap.add_argument('flac_files', nargs='+')

    args = ap.parse_args()

    errors = False

    for flac in args.flac_files:
        prior_tags = get_flac_tags(flac)
        prior_stat = os.stat(flac)

        prior_release_id = prior_tags['MUSICBRAINZ_ALBUMID']
        discid = prior_tags['MUSICBRAINZ_DISCID']

        if args.if_mismatch:
            try:
                album_tags, track_tags = get_tags(release_id, discid)
                continue
            except NoMatchingDiscId:
                pass

        try:
            release = choose_release_for_discid(discid, prompt=True)
        except (NoSuchDisc, NoMatchingRelease, MultipleMatchingReleases) as e:
            print('for {flac}: {e}', flac, e)
            errors = False
            continue

        if release is None:
            continue
        elif release.get('id') is None:
            # Happens for "CD stubs" (currently not fetched by
            # brainz.choose_release_for_discid).
            errors = True
            continue

        album_tags, track_tags = get_tags(release, discid)

        try:
            if cu.music.retag.retag(flac, release['id'], discid, album_tags,
                                    track_tags):
                print('retagged', flac)
            else:
                print('failed to retag', flac)
                errors = True
        finally:
            if args.preserve:
                os.utime(flac, ns=(prior_stat.st_atime_ns,
                                   prior_stat.st_mtime_ns))

        if args.move:
            release_id = extract_uuid(release['id'])
            sequence = cu.music.brainz.release_discid_sequence(release, discid)
            new_flac = cu.music.paths.flac_path(release_id, sequence)

            os.makedirs(os.path.dirname(new_flac), exist_ok=True)
            os.rename(flac, new_flac)
            try:
                os.rmdir(os.path.dirname(flac))
            except OSError:  # not empty, probably
                pass


if __name__ == '__main__':
    sys.exit(main() or 0)
