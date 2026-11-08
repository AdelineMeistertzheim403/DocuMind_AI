import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from tools.validate_restore import _extract_lifecycle_keys, LIFECYCLE_KEYS_ARCHIVE


def _write_keys_archive(snapshot: Path, authentication: bytes, admission: bytes, *, mode: int = 0o600, extra: bool = False):
    archive_path = snapshot / LIFECYCLE_KEYS_ARCHIVE
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, payload in (
            ("keys/authentication.key", authentication),
            ("keys/admission.key", admission),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
        if extra:
            payload = b"unexpected"
            info = tarfile.TarInfo("keys/unexpected.key")
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
    return archive_path


def test_extract_lifecycle_keys_restores_into_quarantine_tree(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    authentication = b"authentication-key-v1"
    admission = b"admission-key-v1"
    _write_keys_archive(snapshot, authentication, admission)

    manifest = {
        "backup_format_version": 5,
        "lifecycle_keys": {
            "keys/authentication.key": {
                "size": len(authentication),
                "mode": 0o600,
                "sha256": hashlib.sha256(authentication).hexdigest(),
            },
            "keys/admission.key": {
                "size": len(admission),
                "mode": 0o600,
                "sha256": hashlib.sha256(admission).hexdigest(),
            },
        },
    }

    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    _extract_lifecycle_keys(snapshot, manifest, lifecycle_root)

    assert (lifecycle_root / "keys" / "authentication.key").read_bytes() == authentication
    assert (lifecycle_root / "keys" / "admission.key").read_bytes() == admission


def test_extract_lifecycle_keys_refuses_unexpected_members(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    authentication = b"authentication-key-v1"
    admission = b"admission-key-v1"
    _write_keys_archive(snapshot, authentication, admission, extra=True)

    manifest = {
        "backup_format_version": 5,
        "lifecycle_keys": {
            "keys/authentication.key": {
                "size": len(authentication),
                "mode": 0o600,
                "sha256": hashlib.sha256(authentication).hexdigest(),
            },
            "keys/admission.key": {
                "size": len(admission),
                "mode": 0o600,
                "sha256": hashlib.sha256(admission).hexdigest(),
            },
        },
    }

    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    with pytest.raises(ValueError, match="exactly the two key files"):
        _extract_lifecycle_keys(snapshot, manifest, lifecycle_root)