import os

import cu.music.config
from cu.util.file import find_recursive_with_extension


TOC_SUFFIX = '.toc'  # from cdrdao read-toc
CUE_SUFFIX = '.cue'  # from us, input to flac creation
WAV_SUFFIX = '.wav'  # from cdparanoia
URL_SUFFIX = '.url'  # from us, url to add disc to musicbrainz
FLAC_SUFFIX = '.flac'


def rip_dir():
    return os.environ.get('MUSIC_RIP_DIR', os.path.expanduser('~music/rip'))


def flac_dir():
    return os.environ.get('MUSIC_FLAC_DIR', os.path.expanduser('~music/flac'))


def cache_dir():
    cache_path = os.environ.get('MUSIC_CACHE_DIR')
    if cache_path is not None:
        return cache_path

    cache_base_home = os.environ.get(
        'XDG_CACHE_HOME',
        os.path.expanduser('~/.cache')
    )

    return os.path.join(cache_base_home, 'cu-music')


def wav_path(disc_id):
    return os.path.join(cu.music.config.rip_dir,
                        disc_id + WAV_SUFFIX)


def toc_path(disc_id):
    return os.path.join(cu.music.config.rip_dir,
                        disc_id + TOC_SUFFIX)


def cue_path(disc_id):
    return os.path.join(cu.music.config.rip_dir,
                        disc_id + CUE_SUFFIX)


def url_path(disc_id):
    return os.path.join(cu.music.config.rip_dir,
                        disc_id + URL_SUFFIX)


def flac_path(release_id, sequence=None):
    # Put each FLAC file in its own directory.  Slimserver will combine tracks
    # with a common album name that are located in the same directory.  If we
    # put all the FLAC files in the same directory, the result is that all the
    # "Greatest Hits" albums are combined.
    if sequence is not None:
        release_id = '%s-%d' % (release_id, sequence)
    return os.path.join(cu.music.config.flac_dir,
                        release_id,
                        release_id + FLAC_SUFFIX)


def all_flac_files():
    return find_recursive_with_extension(cu.music.config.flac_dir, '.flac')


# "done" is defined by having a .url file.
def done_discids_by_mtime():
    return sorted((f[:-len(URL_SUFFIX)]
                   for f in os.listdir(rip_dir())
                   if f.endswith(URL_SUFFIX)),
                  key = lambda d: os.stat(url_path(d)).st_mtime)
