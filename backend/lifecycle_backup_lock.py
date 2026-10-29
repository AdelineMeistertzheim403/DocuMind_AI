"""Cooperative process lock shared by lifecycle stores and backup capture."""
from contextlib import contextmanager, nullcontext
import os
from pathlib import Path
import stat


def _lock_file(required: bool):
    raw_path = os.environ.get("LIFECYCLE_BACKUP_LOCK_PATH")
    if not raw_path:
        if required:
            raise ValueError("Lifecycle backup lock is not configured")
        return nullcontext()
    path = Path(raw_path)
    if not path.is_absolute() or path.resolve() != path or any(
        parent.is_symlink() for parent in (path, *path.parents) if parent.exists()
    ):
        raise ValueError("Canonical lifecycle backup lock path required")
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or (os.name == "posix" and parent.st_mode & 0o077):
        raise ValueError("Private lifecycle backup lock directory required")
    return path


@contextmanager
def lifecycle_store_lock(*, exclusive: bool = False, required: bool = False):
    """Serialize configured lifecycle access with an exclusive snapshot barrier."""
    path = _lock_file(required)
    if path is None or hasattr(path, "__enter__"):
        with path:
            yield
        return
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Private regular lifecycle backup lock required")
        if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise ValueError("Private lifecycle backup lock required")
        if os.name == "posix":
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        else:
            import msvcrt
            if info.st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(descriptor)
