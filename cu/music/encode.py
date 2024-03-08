from argparse import ArgumentParser
import os
import subprocess
from urllib.error import HTTPError

import musicbrainzngs.musicbrainz as mb

import cu.music.config
import cu.music.brainz
from cu.music.brainz import extract_uuid, VARIOUS_ARTISTS_ID
import cu.music.paths
from cu.music.paths import (done_discids_by_mtime, cue_path, CUE_SUFFIX,
                            flac_path, wav_path, WAV_SUFFIX, url_path,
                            URL_SUFFIX)
from cu.music.tags import flac_tag_args, get_tags, get_artist
from cu.util.file import file_contents


def get_ready_wavs():
    return [d for d in done_discids_by_mtime()
            if os.path.exists(wav_path(d)) and os.path.exists(wav_path(d))]


def get_previous_and_next():
    done = done_discids_by_mtime()

    previous_disc = {}
    next_disc = {}

    for p, n in zip(done[:-1], done[1:]):
        previous_disc[n] = p
        next_disc[p] = n

    return previous_disc, next_disc


def make_flac_from_wav(release_id, discid, sequence,
                       album_tags, track_tags,
                       delete_wav=False):
    output = flac_path(release_id, sequence)
    flac_args = [cu.music.config.flac_program,
                 "--best",
                 # "-l", "12", "-b", "4608", "-m", "-r", "6",
                 f"--output-name={output}",
                 f"--cuesheet={cue_path(discid)}"]

    if delete_wav:
        flac_args.append("--delete-input-file")
    flac_args += flac_tag_args(album_tags, track_tags, 'tag')
    flac_args += [wav_path(discid)]

    os.makedirs(os.path.dirname(output), exist_ok=True)
    subp = subprocess.run(flac_args)
    return subp.returncode == 0


def long_artist_string(r):
    name, sortname, artistid = get_artist(r)
    res = name
    if name != sortname:
        res = res + " (" + sortname + ")"
    return res


def get_full_recording_info(medium):
    for track in medium['track-list']:
        recording = track['recording']
        if 'artist-credit' not in recording:
            fullrecording = cu.music.brainz.get_recording_by_id(
                recording['id'])
            track['recording'] = fullrecording


class NoSuchDisc(Exception):
    pass


class NoMatchingRelease(Exception):
    pass


class MultipleMatchingReleases(Exception):
    pass


class RetryPrompt(Exception):
    pass


def repeat_prompt(prompt, convert_or_reject=lambda x: x):
    while True:
        try:
            return convert_or_reject(input(prompt))
        except RetryPrompt:
            pass


def choose_release_for_discid(discid, prompt=False):
    try:
        disc = cu.music.brainz.get_releases_by_discid(discid)
    except mb.ResponseError as e:
        if isinstance(e.cause, HTTPError) and e.cause.code == 404:
            raise NoSuchDisc()
        raise

    releases = [cu.music.brainz.get_release_by_id(release['id'])
                for release in disc['release-list']]

    if not releases:
        raise NoMatchingRelease()
    elif len(releases) == 1:
        return releases[0]

    print(f"Multiple matches for {discid}:")
    for i, r in enumerate(releases):
        medium = cu.music.brainz.release_media_by_discid(r, discid)
        print("   ", i, "http://musicbrainz.org/release/%s" % r['id'])
        print("       ", r['artist-credit-phrase'], "/", r['title'])
        print("       ", medium['position'], "/", r['medium-count'])
        print("       ", r.get('country', '(No country)'),
              r.get('date', '(No date)'))

    if not prompt:
        raise MultipleMatchingReleases()

    def convert_response(resp):
        if not resp.strip():
            return None
        try:
            return releases[int(resp)]
        except (ValueError, IndexError):
            raise RetryPrompt()

    return repeat_prompt(f'0-{len(releases)-1} or empty to skip> ',
                         convert_response)


def print_release_info(r, discid):
    print("Disc ID: " + discid)
    print("Album ID: " + r['id'])

    print("    " + r['title'])

    medium = cu.music.brainz.release_media_by_discid(r, discid)
    mediacount = r['medium-count']
    if mediacount > 1:
        print(medium.get('format', 'CD'),
              medium['position'],
              '(of %d)' % mediacount)

    print("    " + long_artist_string(r))

    if 'date' in r:
        print("    " + r['date'])

    albumartist, albumartistsort, albumartistid = get_artist(r)

    if albumartistid == VARIOUS_ARTISTS_ID:
        get_full_recording_info(medium)
    for track in medium['track-list']:
        recording = track['recording']

        print("    %s %s" % (track['number'], recording['title']))
        if albumartistid == VARIOUS_ARTISTS_ID:
            trackartist, trackartistsort, trackartistid = get_artist(recording)
            if trackartistid != albumartistid or trackartist != albumartist:
                print("       " + long_artist_string(recording))


def main():
    ap = ArgumentParser()
    ap.add_argument("-d", "--delete-wavs", action="store_true",
                    help="delete WAV files on successful encode")
    ap.add_argument("-p", "--prompt", action="store_true",
                    help="prompt to resolve discid collisions")
    args = ap.parse_args()

    if args.delete_wavs:
        print("Deleting WAV files on encode completion.")

    cu.music.brainz.ensure_musicbrainz_init()

    ready = get_ready_wavs()

    nomatch = []
    multiple = []
    skipped = []
    success = []
    donealready = []
    failed = []

    print("%d ready files." % len(ready))

    for discid in ready:
        try:
            release = choose_release_for_discid(discid, prompt=args.prompt)
        except (NoSuchDisc, NoMatchingRelease):
            nomatch.append(discid)
            continue
        except MultipleMatchingReleases:
            multiple.append(discid)
            continue

        if release is None:
            skipped.append(discid)
        elif release.get('id') is None:
            # Happens for "CD stubs" (currently not fetched by
            # brainz.choose_release_for_discid).
            nomatch.append(discid)
            continue

        release_id = extract_uuid(release['id'])
        sequence = cu.music.brainz.release_discid_sequence(release, discid)
        output = flac_path(release_id, sequence)

        if os.path.exists(output):
            print("Skipping already completed "+discid+".")
            donealready.append(discid)
            continue

        print_release_info(release, discid)

        album_tags, track_tags = get_tags(release, discid)

        if make_flac_from_wav(release_id, discid, sequence,
                              album_tags, track_tags,
                              delete_wav=args.delete_wavs):
            print("Encode successful.")
            success.append(discid)
        else:
            failed.append(discid)

        print()
        print()

    print("Summmary:")
    print("  %d successfully encoded." % len(success))
    print("  %d skipped (FLAC already exists)." % len(donealready))

    print("  %d failed compression:" % len(failed))
    for d in failed:
        print("   ", d)

    print("  %d have multiple releases matching discid:" % len(multiple))
    for d in multiple:
        print("   ", d)

    previous, next = get_previous_and_next()

    print("  %d have no release matching discid:" % len(nomatch))
    for d in nomatch:
        print("   ", d)

        for name, discid in (("Previous", previous.get(d, None)),
                             ("Following", next.get(d, None))):
            if discid is None:
                continue

            print("     ", name, discid)
            try:
                disc = get_releases_by_discid(discid)
            except mb.ResponseError as e:
                if isinstance(e.cause, HTTPError) and e.cause.code == 404:
                    print("        (No match)")
                    continue

            releases = [release
                        for disc in discs
                        for release in disc['disc']['release-list']
                        ]

            for r in releases:
                print("       ", r['title'])

        print("    URL to submit this disc to MusicBrainz:")
        print("      ", file_contents(url_path(d)))


if __name__ == '__main__':
    main()
