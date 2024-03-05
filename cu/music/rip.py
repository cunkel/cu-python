#!/usr/bin/env python3

import subprocess
import os
import time

import libdiscid

import cu.music.cdrom
import cu.music.config
import cu.music.cuesheet
from cu.music.paths import cue_path, toc_path, url_path, wav_path
from cu.util.file import write_contents_to


def wait_until_disc_is_loaded():
    while not cu.music.cdrom.drive_is_loaded('/dev/cdrom'):
        time.sleep(5)


def run_zero_return(args):
    return subprocess.run(args).returncode == 0


def read_toc(dest):
    return run_zero_return([cu.music.config.cdrdao_program,
                            'read-toc', '--device', '/dev/cdrom', dest])


def rip_disc(dest):
    return run_zero_return([cu.music.config.cdparanoia_program,
                            '-d', '/dev/cdrom', '[00:00:00.00]-', dest])


def rip_one_disc():
    d = libdiscid.read('/dev/cdrom')
    mbid = d.id
    print("Found disc: " + mbid)

    toc = toc_path(mbid)
    url = url_path(mbid)
    wav = wav_path(mbid)

    if os.path.exists(url):
        print('  Appears to be done; skipping.')
        return

    print('TOC:')
    if not read_toc(toc):
        print('Failed to read TOC')
        return

    print('Cuesheet:')
    write_contents_to(cue_path(mbid), cu.music.cuesheet.toc_to_cuesheet(toc))

    print('Rip:')
    if rip_disc(wav):
        write_contents_to(url, [d.submission_url, '\n'])
        print('Successful copy.')
    else:
        print('Copy failed for', d.submission_url)


def main():
    while True:
        wait_until_disc_is_loaded()
        rip_one_disc()

        print('Eject:')
        cu.music.cdrom.eject('/dev/cdrom')
        print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        # Suppress the traceback as this is the usual exit path.
        pass
