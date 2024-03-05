import argparse
import os
import subprocess
import sys

import cu.music.brainz
import cu.music.config
import cu.music.paths
from cu.music.tags import (get_tags, get_flac_tags, flac_tag_args,
                           NoMatchingDiscId)


def retag(flac, release_id, discid, album_tags, track_tags):
    args = [cu.music.config.metaflac_program, "--remove-all-tags",
            *flac_tag_args(album_tags, track_tags, 'set-tag'),
            flac]

    # print(' '.join(args))
    subp = subprocess.run(args)
    return subp.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preserve-timestamps', '-p',
                    action='store_true', dest='preserve')
    ap.add_argument('flac_files', nargs='+')
    args = ap.parse_args()

    errors = False

    bad_discid = {}

    for flac in args.flac_files:
        try:
            prior_tags = get_flac_tags(flac)
            prior_stat = os.stat(flac)

            release_id = prior_tags['MUSICBRAINZ_ALBUMID']
            discid = prior_tags['MUSICBRAINZ_DISCID']

            album_tags, track_tags = get_tags(release_id, discid)

            if retag(flac, release_id, discid, album_tags, track_tags):
                print('retagged', flac)
            else:
                print('failed to retag', flac)
                errors = True

        except NoMatchingDiscId as exc:
            bad_discid[flac] = exc
            print(f'failed to retag {flac}: {exc}')

        except Exception as exc:
            print(f'failed to retag {flac}: {exc}')
            errors = True
            raise

        finally:
            if args.preserve:
                os.utime(flac, ns=(prior_stat.st_atime_ns,
                                   prior_stat.st_mtime_ns))

        sequence = album_tags.get('DISC')
        if sequence is not None:
            sequence = int(sequence)

        predicted_path = cu.music.paths.flac_path(release_id, sequence)
        if predicted_path != os.path.abspath(flac):
            print(f'path mismatch: {flac} -> {predicted_path}')
            print(f'sudo mkdir -p {os.path.dirname(predicted_path)}')
            print(f'sudo mv {flac} {predicted_path}')

    if bad_discid:
        for flac, e in bad_discid.items():
            print(flac, e.disc_id)

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main() or 0)
