import multiprocessing
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backend import lifecycle_backup_lock as locks


def _contender(path, attempted, acquired, release, errors, exclusive):
    os.environ["LIFECYCLE_BACKUP_LOCK_PATH"] = path
    attempted.set()
    try:
        with locks.lifecycle_store_lock(exclusive=exclusive, required=True):
            acquired.set()
            if not release.wait(10):
                raise TimeoutError("Synthetic lock holder was not released")
    except BaseException as error:
        errors.put(type(error).__name__)


@pytest.mark.parametrize("exclusive", [False, True])
def test_exclusive_barrier_blocks_another_process_and_releases(tmp_path, monkeypatch, exclusive):
    tmp_path.chmod(0o700)
    path = tmp_path.resolve() / ".backup.lock"
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(path))
    context = multiprocessing.get_context("spawn")
    attempted, acquired, release = (context.Event() for _ in range(3))
    errors = context.Queue()
    process = context.Process(
        target=_contender,
        args=(str(path), attempted, acquired, release, errors, exclusive),
    )
    try:
        with locks.lifecycle_store_lock(exclusive=True, required=True):
            process.start()
            assert attempted.wait(10)
            assert not acquired.wait(0.3), "A second process bypassed the snapshot barrier"
        assert acquired.wait(10)
        release.set()
        process.join(10)
        assert process.exitcode == 0
        assert errors.empty()
    finally:
        release.set()
        if process.pid is not None:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(10)


def test_path_context_manager_cannot_bypass_lock(tmp_path, monkeypatch):
    class ContextPath(type(Path())):
        def __enter__(self):
            raise AssertionError("Path context management must not be used for locking")

        def __exit__(self, *args):
            return False

    tmp_path.chmod(0o700)
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(tmp_path.resolve() / ".backup.lock"))
    monkeypatch.setattr(locks, "Path", ContextPath)
    with patch.object(locks.os, "open", wraps=os.open) as opened:
        with locks.lifecycle_store_lock(required=True):
            pass
        assert opened.call_count == 1


def test_body_failure_closes_descriptor_and_allows_reacquisition(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(tmp_path.resolve() / ".backup.lock"))
    with patch.object(locks.os, "close", wraps=os.close) as closed:
        with pytest.raises(RuntimeError, match="synthetic"):
            with locks.lifecycle_store_lock(exclusive=True, required=True):
                raise RuntimeError("synthetic body failure")
        assert closed.call_count == 1
    with locks.lifecycle_store_lock(exclusive=True, required=True):
        pass


def test_open_failure_does_not_enter_body(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(tmp_path.resolve() / ".backup.lock"))
    with patch.object(locks.os, "open", side_effect=PermissionError("synthetic")):
        with pytest.raises(PermissionError):
            with locks.lifecycle_store_lock(required=True):
                pytest.fail("Failed lock acquisition must not enter the body")


@pytest.mark.posix
def test_flock_failure_closes_descriptor(tmp_path, monkeypatch):
    import fcntl

    tmp_path.chmod(0o700)
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(tmp_path.resolve() / ".backup.lock"))
    with patch.object(fcntl, "flock", side_effect=OSError("synthetic flock failure")), \
            patch.object(locks.os, "close", wraps=os.close) as closed:
        with pytest.raises(OSError):
            with locks.lifecycle_store_lock(required=True):
                pytest.fail("Failed flock must not enter the body")
        assert closed.call_count == 1


@pytest.mark.posix
@pytest.mark.parametrize("invalid", ["public", "symlink", "hardlink"])
def test_existing_file_guards_are_preserved(tmp_path, monkeypatch, invalid):
    tmp_path.chmod(0o700)
    path = tmp_path.resolve() / ".backup.lock"
    source = tmp_path / "source"
    source.write_bytes(b"")
    source.chmod(0o600)
    if invalid == "symlink":
        path.symlink_to(source)
    elif invalid == "hardlink":
        os.link(source, path)
    else:
        path.write_bytes(b"")
        path.chmod(0o644)
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(path))
    with pytest.raises(ValueError):
        with locks.lifecycle_store_lock(required=True):
            pytest.fail("Invalid lock must not be acquired")


def test_unconfigured_optional_and_required_modes(monkeypatch):
    monkeypatch.delenv("LIFECYCLE_BACKUP_LOCK_PATH", raising=False)
    with locks.lifecycle_store_lock():
        pass
    with pytest.raises(ValueError, match="not configured"):
        with locks.lifecycle_store_lock(required=True):
            pass
