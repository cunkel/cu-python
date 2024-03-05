import argparse
import concurrent.futures
import os
import re
import sys
import unicodedata

from cu.music.flac import FlacTags
import cu.music.m4a
import cu.music.mp3
import cu.music.paths
from cu.music.tags import get_flac_tags, flac_separate_tags
from cu.util.file import find_recursive_with_extension, prune_directory


disc_re = re.compile(r'\(CD(?P<fill>[ _])\d+\)$')
forbidden_specials = set(' \t\r\n:"/\\;?<>*|^#')

# TODO: The unidecode package does this better--which is not hard.
ascii_substitutions = {
    '\u0101': 'a',
    '\u0144': 'n',
    '\xd3': 'O',
    '\u0159': 'r',
    '\xc1': 'A',
    '\xdf': 'sz',  # Eszett -- why isn't this 'ss'?
    '\xea': 'e',
    '\xe1': 'a',
    '\xe0': 'a',
    '\xe4': 'a',
    '\xe7': 'c',
    '\xe6': 'ae',
    '\xe9': 'e',
    '\xe8': 'e',
    '\xeb': 'e',
    '\xed': 'i',
    '\xec': 'i',
    '\xf0': 'd',
    '\xf1': 'n',
    '\xf3': 'o',
    '\xf4': 'o',
    '\xf6': 'o',
    '\xf9': 'u',
    '\xfa': 'u',
    '\xfc': 'u',
    '\u0175': 'w',
    '\u2010': '-',
    '\u2013': '-',
    '\u2014': '--',
    '\u2019': '\'',
    '\u2026': '...',
}


def truncate(s, max_length=64, suffix=''):
    if suffix and s.endswith(suffix):
        s = s[:-len(suffix)]
    else:
        suffix = ''

    m = disc_re.search(s)

    if m is not None:
        disc = m.group()
        fill = m.group('fill')
        s = s[:m.start()]
        s = s[:max_length - len(disc)]
        # s = s.rstrip(' _.')
        return f'{s}{disc}{suffix}'

    return s[:max_length] + suffix
    return s[:max_length].rstrip(' _.') + suffix


def auto_suffix_truncate(s, max_length=64):
    base, dot, suffix = s.rpartition('.')
    return truncate(s, max_length=64, suffix=f'{dot}{suffix}')


def no_specials(s):
    return ''.join('_' if x in forbidden_specials else x
                   for x in s)


def asciiify_character(c, default_substitute=''):
    if c.isascii():
        return c
    else:
        return ascii_substitutions.get(c, default_substitute)


def asciiify(s):
    return ''.join(asciiify_character(x) for x in s)


def no_trailing_dot_or_underscore(s):
    return s.rstrip('._')


def no_dot_or_underscore_before_suffix(s):
    prefix, dot, suffix = s.rpartition('.')
    prefix = prefix.rstrip('._')
    return f'{prefix}{dot}{suffix}'


def whitespace_to_underscores(s):
    return ''.join('_' if c.isspace() else c for c in s)


def no_consecutive_underscores(s):
    return re.sub('__+', '_', s)


def apply_string_policy(policy, s):
    for func in policy:
        s = func(s)
    return s


dirname_string_policy = [
    asciiify,
    no_specials,
    whitespace_to_underscores,
    no_consecutive_underscores,
    truncate,
    no_trailing_dot_or_underscore,
]
basename_string_policy = [
    asciiify,
    no_specials,
    whitespace_to_underscores,
    no_consecutive_underscores,
    auto_suffix_truncate,
    no_dot_or_underscore_before_suffix,
]


def normalize_dirname(s):
    return apply_string_policy(dirname_string_policy, s)


def normalize_basename(s):
    return apply_string_policy(basename_string_policy, s)


def output_encoded_files(dest_dir, encode_func, suffix, jobs=1):
    target_result = {}
    all_chars = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        future_to_target = {}

        for flac_file in sorted(cu.music.paths.all_flac_files()):
            flac_tags = get_flac_tags(flac_file)
            album_tags, track_tags = flac_separate_tags(flac_tags)

            artist_dir = normalize_dirname(album_tags[FlacTags.ARTIST_SORT])
            album_dir = normalize_dirname(album_tags[FlacTags.ALBUM_TITLE])

            all_chars.update(album_tags[FlacTags.ARTIST_SORT])
            all_chars.update(album_tags[FlacTags.ALBUM_TITLE])

            for track, tags in track_tags.items():
                track_index = int(tags[FlacTags.TRACK_INDEX])
                track_title = tags[FlacTags.TRACK_TITLE]
                all_chars.update(track_title)
                sep = ' ' if track_title else ''
                encoded_file = normalize_basename(
                    f'{track_index:02d}{sep}{track_title}{suffix}'
                )

                relative_target = os.path.join(
                    artist_dir, album_dir, encoded_file)
                target = os.path.join(dest_dir, relative_target)
                future = executor.submit(encode_func, flac_file, track, target)
                future_to_target[future] = target

                # This is mostly for debugging, where running things
                # synchronously makes things much easier.  It implicitly makes
                # jobs=1 stop on first error while others continue (sort of
                # like if make -j also set -k automatically).  Unsure if this
                # is right.
                if jobs == 1:
                    future.result()

        # The CTRL-C behavior here sucks.
        for future in concurrent.futures.as_completed(future_to_target):
            target = future_to_target[future]
            try:
                future.result()
            except Exception as exc:
                print(f'generating {target}: {exc}')
                raise
                target_result[target] = False
            else:
                target_result[target] = True

    all_chars.difference_update(ascii_substitutions.keys())
    all_chars.difference_update(chr(x) for x in range(128))
    if all_chars:
        print('Non-ASCII characters without substitutions:')
        for c in sorted(all_chars):
            print("    %s: '%s', # %s"
                  % (ascii(c), c, unicodedata.name(c, '<UNKNOWN>')))

    return target_result


FORMATS = {
    'aac': {
        'func': cu.music.m4a.create_or_update_m4a,
        'suffix': '.m4a',
    },
    'mp3': {
        'func': cu.music.mp3.create_or_update_mp3,
        'suffix': '.mp3',
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--format', choices=list(FORMATS.keys()), default='aac')
    ap.add_argument('dest_dir')

    ap.add_argument('--jobs', '-j', type=int, default=1)
    ap.add_argument('--delete', '-d', action='store_true')
    ap.add_argument('--prune', '-p', action='store_true')
    args = ap.parse_args()

    format_properties = FORMATS[args.format]
    output_function = format_properties['func']
    suffix = format_properties['suffix']

    desired_files = output_encoded_files(args.dest_dir, output_function,
                                         suffix, jobs=args.jobs)

    if args.delete:
        for filename in find_recursive_with_extension(args.dest_dir, suffix):
            if filename not in desired_files:
                print('remove', filename)
                os.remove(filename)

    if args.prune:
        prune_directory(args.dest_dir)


if __name__ == '__main__':
    sys.exit(main() or 0)
