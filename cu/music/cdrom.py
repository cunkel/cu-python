"""manipulate CDROM devices (on linux)"""

import argparse
from enum import Enum
import fcntl
import os
import sys

from cu.util.file import open_fd


DEFAULT_CDROM_DEVICE = '/dev/cdrom'


class Constants:
    CDROM_EJECT = 0x5309
    CDROM_DRIVE_STATUS = 0x5326
    CDROM_LOCK_DOOR = 0x5329
    CDSL_CURRENT = 0x7FFFFFFF


class DriveStatus(Enum):
    NO_INFO = 0
    NO_DISC = 1
    TRAY_OPEN = 2
    DRIVE_NOT_READY = 3
    DISC_OK = 4


def drive_status(device):
    """return status of a CDROM device as a DriveStatus enum"""
    with open_fd(device, os.O_RDONLY | os.O_NONBLOCK) as fd:
        status = fcntl.ioctl(fd, Constants.CDROM_DRIVE_STATUS,
                             Constants.CDSL_CURRENT)
    return DriveStatus(status)


def drive_is_loaded(device):
    """true if device is loaded and ready"""
    return drive_status(device) is DriveStatus.DISC_OK


def eject(device):
    """open tray of and/or eject disc in device"""
    with open_fd(device, os.O_RDONLY | os.O_NONBLOCK) as fd:
        fcntl.ioctl(fd, Constants.CDROM_LOCK_DOOR, 0)
        fcntl.ioctl(fd, Constants.CDROM_EJECT, 0)


def main():
    """eject or report status of cdrom device"""
    ap = argparse.ArgumentParser()
    ap.add_argument('--quiet', '-q', action='store_true',
                    help='do not print status to standard out')
    ap.add_argument('--eject', action='store_true',
                    help='eject disk instead of printing status')
    ap.add_argument('device', nargs='?', default=DEFAULT_CDROM_DEVICE,
                    help=f'cdrom device (default {DEFAULT_CDROM_DEVICE})')

    args = ap.parse_args()

    if args.eject:
        try:
            eject(args.device)
        except Exception as e:
            if not args.quiet:
                print(f'error ejecting {args.device}: {e}', file=sys.stderr)
            return 1
        return 0

    try:
        status = drive_status(args.device)
    except Exception as e:
        if not args.quiet:
            print(f'error getting drive status for {args.device}: {e}',
                  file=sys.stderr)
            print('ERROR')
        return 1

    if not args.quiet:
        print(status.name)

    if status is DriveStatus.DISC_OK:
        return 0

    return status.value + 100


if __name__ == '__main__':
    sys.exit(main() or 0)
