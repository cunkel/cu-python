"""convert cdrdao-style table-of-contents files to cue files for flac"""

import argparse
import sys

from cu.util.file import file_contents

__all__ = ['toc_to_cuesheet']

# This all is ugly in many ways.
#
# It is necessary because when we rip CDs with cdparanoia we specify sector 0
# (as LBA [0:0:0.0]) as the start position to rip, and this may not be the same
# as the start sector of track 1.  toc2cue (from cdrdao) doesn't handle this
# correctly.
#
# There is some long-ago discussion on the flac mailing list
# (https://lists.xiph.org/pipermail/flac/2006-September/000615.html) as well as
# a patch to toc2cue.  For years I used that hacked "toc3cue" for cuesheet
# generation, which was an external C++ dependency.  Also toc[23]cue is fussy
# and would occasionally reject toc files, forcing me to edit out the offending
# bits manually.
#
# The parsing is here is obviously not super... rigorous.  On the other hand
# interpreting only the things we care about should prevent it from rejecting
# toc files that are technically illegal but in ways that don't matter to us.
#
# Tested on 578 current toc files and reference output from "toc3cue".


def net_braces(s):
    return s.count('{') - s.count('}')


def read_cdrdao_toc(path):
    joined_parts = []
    with open(path) as f:
        parts = []
        brace_count = 0
        for line in f:
            line = line.rstrip('\n')
            if line.lstrip().startswith('//') or not line.strip():
                continue
            parts.append(line)

            # The point of this is to fold CD_TEXT { .. } into a single string
            # so we can ignore it all and not be distracted by things like ISRC
            # inside it.  There better not be braces inside double-quoted
            # strings inside that.
            brace_count += net_braces(line)
            assert brace_count >= 0

            if brace_count == 0:
                joined_parts.append('\n'.join(parts))
                parts = []

        assert not parts

    return [x.lstrip() for x in joined_parts]


def split_by_track(parts):
    tracks = []

    group = []
    for p in parts:
        if p.startswith('TRACK '):
            if group:
                tracks.append(group)
                group = []
        group.append(p)
    if group:
        tracks.append(group)

    return tracks


def undoublequote(s):
    assert s.startswith('"')
    assert s.endswith('"')
    s = s[1:-1]
    assert '"' not in s
    return s


def only_matching_word(data, key, process=lambda x: x[0], missing_ok=True):
    matches = [x[1:] for x in data if x[0] == key]
    if len(matches) >= 2:
        print(matches)
    assert len(matches) < 2
    if matches:
        return process(matches[0])
    assert missing_ok
    return None


def get_catalog(data):
    return only_matching_word(data, 'CATALOG', lambda x: undoublequote(x[0]))


def get_track_file(data):
    return only_matching_word(data, 'FILE', lambda x: x[1:3], missing_ok=False)


def get_start(data):
    return only_matching_word(data, 'START')


def get_silence(data):
    return only_matching_word(data, 'SILENCE')


def get_isrc(data):
    return only_matching_word(data, 'ISRC', lambda x: undoublequote(x[0]))


def has_copy(data):
    # Most tracks are ['NO', 'COPY'] which is the opposite.
    return any(x == ['COPY'] for x in data)


def track_type(data):
    # TRACK is always first because it initiates a group, except for the disc
    # data, on which is is illegal to use this.
    words = data[0]
    assert words[0] == 'TRACK'
    return words[1]


def to_fracs(x):
    minutes, seconds, fracs = x.split(':')
    return int(minutes)*60*75 + int(seconds)*75 + int(fracs)


def offset_sum(x, y):
    fracs = to_fracs(x) + to_fracs(y)
    seconds, fracs = divmod(fracs, 75)
    minutes, seconds = divmod(seconds, 60)

    return f'{minutes:02d}:{seconds:02d}:{fracs:02d}'


def make_cuesheet(parts):
    cuesheet = []

    def line(indent, *parts):
        cuesheet.append(' '.join(((' ',) * indent) + parts))

    tracks = split_by_track(parts)
    tracks = [[x.split() for x in data] for data in tracks]

    silence_offset = '00:00:00'
    track_1_is_audio = track_type(tracks[1]) == 'AUDIO'

    for track, data in enumerate(tracks):
        if track == 0:  # disc header
            data_file = '"data.wav"' if track_1_is_audio else '"data_1"'
            line(0, 'FILE', data_file, 'BINARY')

            catalog = get_catalog(data)
            if catalog is not None:
                line(0, 'CATALOG', catalog)

        elif track_type(data) == 'AUDIO':
            line(1, 'TRACK', '%02d' % track, 'AUDIO')

            if has_copy(data):
                line(2, 'FLAGS', 'DCP')

            isrc = get_isrc(data)
            if isrc is not None:
                line(2, 'ISRC', isrc)

            track_start, length = get_track_file(data)
            if track_start == '0':
                track_start = '00:00:00'
            track_start = offset_sum(track_start, silence_offset)

            start = get_start(data)
            if start:
                line(2, 'INDEX', '00', track_start)
                line(2, 'INDEX', '01', offset_sum(track_start, start))
            else:
                line(2, 'INDEX', '01', track_start)

            # TODO: INDEX entries in toc file could be expressed as INDEX 02
            # and beyond?

            # This can actually only happen on the first track?
            silence = get_silence(data)
            if silence is not None:
                silence_offset = offset_sum(silence_offset, silence)

        elif track_type(data) == 'MODE1':
            line(1, 'TRACK', '%02d' % track, 'MODE1/2048')
            line(2, 'INDEX', '01', '00:00:00')

        else:
            assert False

    line(0)  # for trailing newline
    return '\n'.join(cuesheet)


def toc_to_cuesheet(toc):
    """read toc file (from cdrdao read-toc) and return cuesheet string"""
    return make_cuesheet(read_cdrdao_toc(toc))


# TODO: most useful test cases
# kizI6EsqM9gOnDB0ArREDowMAGY-.toc has both INDEX 00 and not
# k1C3pVQL4yZN0Fcz1ezhz9hzxNE-.toc has ISRCs
# 4N0wq1Xx4mbiD_nF9ruYR31K1tU-.toc has no CATALOG
# 5fyCdgj9p2rXbp4sMveOp1r5bAo-.toc has SILENCE
# NFrLAj_IhRodKCSeuIFnUiedguc-.toc has COPY flag set
# flplyXqMOiodZEDJeDw5Ci6OD_g-.toc is CD_ROM with MODE1
# pAu91B0sjjwKq35Tmw52jx8VspE-.toc is CD_ROM with AUDIO
# vJ.B_oj26BlZx5LlhfVPQKRsqHU-.toc has empty ISRCs inside CD_TEXT (only)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('toc_file')
    ap.add_argument('--compare')
    args = ap.parse_args()

    cuesheet = toc_to_cuesheet(args.toc_file)

    if args.compare:
        reference = file_contents(args.compare)
        return 0 if reference == cuesheet else 1

    print(cuesheet, end='')


if __name__ == '__main__':
    sys.exit(main() or 0)
