"""file-related utilities"""

import contextlib
import errno
import json
import os
import random
import stat


@contextlib.contextmanager
def open_fd(path, *args, **kwargs):
    """context manager for os.open

    example usage:

        with open_fd('/dev/null', os.O_RDONLY) as fd:
            ..."""
    fd = os.open(path, *args, **kwargs)
    try:
        yield fd
    finally:
        os.close(fd)


def file_contents(path, *args, **kwargs):
    with open(path, 'r', *args, **kwargs) as f:
        return f.read()


def file_binary_contents(path, *args, **kwargs):
    with open(path, 'rb', *args, **kwargs) as f:
        return f.read()


_SEQ_CHARS = (
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '0123456789'
)


def remove_if_exists(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _temp_name_to_update(path, max_tries=16):
    """iterable of max_tries paths for a temporary in the same dir as path"""
    dirname, filename = os.path.split(path)
    pid = str(os.getpid())

    # This is a hassle, but paths can be either str or bytes.
    if isinstance(path, bytes):
        prefix = b'.tmp'
        empty = b''
        dot = b'.'
        seq_chars = _SEQ_CHARS.encode('ascii')
        pid = pid.encode('ascii')
    else:
        prefix = '.tmp'
        empty = ''
        dot = '.'
        seq_chars = _SEQ_CHARS

    for attempt in range(max_tries):
        if attempt == 0:
            # We expect that this will usually succeed on the first try and are
            # trying to save the use of entropy here.
            seq = empty
        else:
            seq = empty.join([dot] + random.choices(seq_chars, k=6))

        yield (
            os.path.join(dirname,
                         empty.join([prefix, dot, pid, seq, dot, filename])),
            attempt == max_tries - 1)


def open_with_perms(path, mode, perms, *args, **kwargs):
    """like open() but permits control of third argument to os.open()

    Somewhat confusingly both the second argument to open(), for example 'r' or
    'wb', and the third argument to os.open(), for example 0o0666, are both
    called mode.  The first is about the capabilities of the created python
    file object; the second is about the permissions of any file in the
    filesystem.

    open() provides no way of controlling the second.  open_with_perms() does.
    mode is the first; perms is the second.  As with os.open(), the perms
    argument only matters when a file is created.  Additional arguments and
    keyword arguments, for example encoding, are passed to open().
    """

    if perms is None:
        # Calling open(path, 'w') would have the group and other write bits set
        # (0o666 vs 0o644 here).  This is modified by the umask, which is
        # typically 0o022, and so with default umask both will result in 0o644
        # files.  We use 0o644 as the default here for safety, in particular
        # because the umask is process-wide, not per-thread.  That means in a
        # multi-threaded program a temporary umask change to write g+w or o+w
        # file is not safe if other threads rely on the umask.
        perms = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH

    def opener(path, flags):
        return os.open(path, flags, perms)

    return open(path, mode, opener=opener, *args, **kwargs)


class AbortUpdate(Exception):
    """raise within tempfile_to_update to abort the update"""
    pass


@contextlib.contextmanager
def tempfile_to_update(path, mode=None, binary=False, *args, **kwargs):
    """set contents of a file by writing a temporary and rename()

    Returns a context manager.  When entered, creates and returns a temporary
    file in the same directory as the target path.  The file is closed when the
    context exits.  If the context exits without exception, the temporary file
    is moved into the target location via os.rename(), which (per POSIX
    semantics) is atomic.  If the context exits with an exception the temporary
    is removed and the target left intact.

    The primary intent is to prevent readers of the file from observing partial
    or inconsistent contents without using any other form of synchronization.

    Note that no sort of lock is held during this process.  For example an
    atomic read-modify-write of the target file is not possible without some
    other form of lock.

    Example:

        with tempfile_to_update('foo') as f:
           f.write('hello\n')

    which might result (roughly) in the equivalent system calls/C code

        fd = open(".tmp.10000.foo", O_WRONLY|O_CREAT|O_EXCL, 0644);
        write(fd, "hello\n", 6);
        close(fd);
        rename(".tmp.10000.foo", ".foo");

    mode, if given, specifies the mode parameter (permissions) passed to
    os.open.  If unspecified or None, user read/write, group read, other read
    is used (0o644).  Note that this differs from os.open with unspecified mode
    (0o777 is assumed) or from builtin open() (0o666 is assumed).

    If binary is true, the file object created  is created with
    mode='wb', otherwise with mode='b'.  Any additional args or keyword args
    (for example, encoding) are passed to os.fdopen.

    The context manager will abort an update on any exception, will swallow an
    AbortUpdate exception, and pass any other through.

    If path is relative the current working directory must be preserved
    between context entry and exit.
    """

    open_mode = 'xb' if binary else 'x'  # x -> O_CREAT | O_EXCL

    # Another approach to consider here would be using tempfile.mkstemp() and
    # then if necessary fix permissions with os.fchmod().  Alternately would it
    # be better to use opendir() to resolve path's dirname at context entry, so
    # that the os.open(), .rename() and .remove() calls could be done using
    # dir_fd (if supported on the platform)?  It would fix the issue with
    # chdir() during context.
    for temp_path, is_last in _temp_name_to_update(path):
        try:
            # Builtin open() has no way of specifying the permissions of the
            # created file.
            f = open_with_perms(temp_path, open_mode, mode, *args, **kwargs)
            break
        except FileExistsError:
            if is_last:
                # This should be vanishingly unlikely with 15 tries with over
                # 32 bits of entropy in each try.
                raise
            continue
    else:
        # This should be unreachable -- _temp_name_to_update must not have
        # returned anything.
        assert False

    try:
        with f:
            yield f  # Exception inside context body comes out here.
        os.rename(temp_path, path)
    except AbortUpdate:
        os.remove(temp_path)
    except BaseException as outer:
        try:
            os.remove(temp_path)
        except Exception:
            pass  # Defer to re-raise below.
        except BaseException:
            if not isinstance(outer, BaseException):
                # For example, outer was ValueError and this is
                # KeyboardInterrupt.  Prefer the non-Exception BaseException of
                # the two (KeyboardInterrupt here).
                raise
        raise


def write_json_via_rename(path, contents, pretty=False, mode=None):
    """update path to contain json dump of contents via rename of temporary"""
    with tempfile_to_update(path, mode=mode) as f:
        if pretty:
            json.dump(contents, f, indent=4, sort_keys=True)
        else:
            json.dump(contents, f)


def _write_contents(f, contents):
    if isinstance(contents, (str, bytes)):
        f.write(contents)
    else:
        for part in contents:
            f.write(part)


def write_file_via_rename(path, contents, mode=None):
    with tempfile_to_update(path, mode=mode) as f:
        _write_contents(f, contents)


def write_binary_file_via_rename(path, contents, mode=None):
    with tempfile_to_update(path, mode=mode, binary=True) as f:
        _write_contents(f, contents)


# Aliases indicate that user is not in particular reliant on the "atomic"
# update.
write_json_to = write_json_via_rename
write_contents_to = write_file_via_rename
write_binary_to = write_binary_file_via_rename


def write_file_directly(path, contents, mode=None, *args, **kwargs):
    with open_with_perms(path, 'w', mode, *args, **kwargs) as f:
        _write_contents(f, contents)


def write_binary_directly(path, contents, mode=None, *args, **kwargs):
    with open_with_perms(path, 'wb', mode, *args, **kwargs) as f:
        _write_contents(f, contents)


def write_json_directly(path, contents, pretty=False, mode=None):
    with open_with_perms(path, 'w', mode) as f:
        json.dump(f)


def find_recursive_with_extension(top, extension=''):
    return [
        os.path.join(dirname, basename)
        for (dirname, subdirs, files) in os.walk(top)
        for basename in files
        if basename.endswith(extension)
    ]


def prune_directory(root):
    for dirpath, _, _ in os.walk(root, topdown=False):
        try:
            os.rmdir(dirpath)
        except OSError as e:
            if e.errno != errno.ENOTEMPTY:
                raise


def prune_directories_in(root):
    for entry in os.scandir(root):
        if entry.is_dir():
            prune_directory_tree(os.path.join(root, entry.name))


"""
Advantages of rename-based update:

Start state: file foo contains '{}'

Three concurrent processes:

Process 1:

    with open('foo', 'w') as f:
        json.dump(f, lotsa_stuff)

Process 2:

    with open('foo') as f:
        stuff = json.load(f)

Process 3:

    with open('foo', 'w') as f:
        json.dump(f, almost_as_much_stuff)

Bad outcomes:

* Process 2 runs halfway through process 1's execution and sees partial
  contents (premature end-of-file).  With rename: process 1 observes initial
  contents {} instead.

* Process 1 completes before process 2 starts, but process 3 runs halfway
  through process 2's execution.  Process 2 sees half what's written by process
  1 and half what's written by process 3.  It could be invalid json due to the
  splice, or a premature end-of-file if process 3's content is shorter, or it
  could even be valid json!  With rename: process 2 sees process 1's results.
  After process 3 executes process 2 continues to read from the (now deleted)
  file containing process 1's update.

* Process 3 experiences an exception (e.g. unserializable object in
  almost_as_much_stuff), or is killed, or the disk becomes full, halfway
  through and foo is left indefinitely with partial contents.  With rename: foo
  is unmodified (possibly the temporary file is left for example if process 3
  is killed with SIGKILL).

* Process 1 and 3 run at about the same speed and foo contains and retains
  indefinitely a random intermingling of their json.  With rename: the rename()
  executed by processes 1 and 3 complete in some order.  foo contains the
  initial contents, then the update from the first to complete, then the update
  from the second to complete.
"""
