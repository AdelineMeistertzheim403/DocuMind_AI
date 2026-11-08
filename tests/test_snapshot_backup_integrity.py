import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from uuid import uuid4

import pytest

from backend.lifecycle_snapshot import STORES, write_snapshot_archive
from tests.test_lifecycle_lot29_bundle import laboratory
from tools.verify_snapshot import verify_capture


def _capture_directory(lab, monkeypatch, tmp_path):
    variables = {
        "registry": "LIFECYCLE_REGISTRY_PATH",
        "witness": "LIFECYCLE_CONFIRMATION_PATH",
        "authenticated": "LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH",
        "holds": "LIFECYCLE_HOLDS_PATH",
        "admission_anchor": "LIFECYCLE_ADMISSION_ANCHOR_PATH",
    }
    monkeypatch.setenv("LIFECYCLE_DATA_ROOT", str(lab.root))
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(lab.root / ".backup.lock"))
    capture_id = str(uuid4())
    monkeypatch.setenv("LIFECYCLE_CAPTURE_ID", capture_id)
    for name, variable in variables.items():
        monkeypatch.setenv(variable, str(lab.paths[name]))

    stream = io.BytesIO()
    metadata = write_snapshot_archive(stream)
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "lifecycle.sqlite.tar.gz").write_bytes(stream.getvalue())
    (root / "database.dump").write_bytes(b"synthetic pg_dump")
    (root / "documents.tar.gz").write_bytes(b"synthetic documents")
    (root / "integrity.json").write_text(json.dumps({}), encoding="utf-8")
    (root / "recovery-state.json").write_text("{\"format\":1,\"state\":\"quarantined\"}\n", encoding="utf-8")
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("database.dump", "documents.tar.gz", "lifecycle.sqlite.tar.gz", "recovery-state.json", "integrity.json")
    }
    stores = {
        name: {
            "snapshot": f"stores/{name}.sqlite",
            "user_version": version,
            "tables": sorted(tables),
            "journal_mode": "delete",
            "sha256": metadata["stores"][name]["sha256"],
        }
        for name, (_, version, tables) in STORES.items()
    }
    manifest = {
        "backup_format_version": 4,
        "capture_id": capture_id,
        "capture_complete": True,
        "s2_recovery_authorized": False,
        "recovery_disposition": "quarantine_pending_independent_freshness_and_operator_review",
        "capture_scope": ["postgresql", "documents", "lifecycle_sqlite", "recovery_state"],
        "recovery_state": {
            "path": "/run/documind/recovery-state.json",
            "state": "quarantined",
            "sha256": hashes["recovery-state.json"],
        },
        "files": list(hashes),
        "sha256": hashes,
        "lifecycle_stores": stores,
        "lifecycle_store_sha256": {
            name: store["sha256"] for name, store in stores.items()
        },
        "quiescence": {
            "api_web_stopped": True,
            "only_database_service_running": True,
            "private_networks_exclusive": True,
            "no_other_postgresql_clients": True,
            "lifecycle_exclusive_lock_acquired": True,
            "out_of_band_privileged_host_access": "trusted_operator_boundary_not_machine_verifiable",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, manifest


def test_full_manifest_verifies_all_five_stores_without_authorizing_recovery(
    laboratory, monkeypatch, tmp_path
):
    root, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    assert verify_capture(root, manifest, require_s2=True) is True
    assert manifest["s2_recovery_authorized"] is False


def test_legacy_and_tampered_archives_are_refused_for_s2(laboratory, monkeypatch, tmp_path):
    root, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    legacy = {**manifest, "backup_format_version": 2}
    with pytest.raises(SystemExit, match="Legacy snapshot"):
        verify_capture(root, legacy, require_s2=True)

    (root / "lifecycle.sqlite.tar.gz").write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="checksum"):
        verify_capture(root, manifest, require_s2=True)


def _write_keys_archive(path: Path, authentication: bytes, admission: bytes, *, mode: int = 0o600, extra: bool = False):
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in (
            ("keys/authentication.key", authentication),
            ("keys/admission.key", admission),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
        if extra:
            info = tarfile.TarInfo("keys/unexpected.key")
            payload = b"unexpected"
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))


def test_format_5_requires_lifecycle_keys_archive_and_strict_inventory(laboratory, monkeypatch, tmp_path):
    root, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    authentication = b"authentication-key-v1"
    admission = b"admission-key-v1"
    _write_keys_archive(root / "lifecycle-keys.tar.gz", authentication, admission)

    keys = {
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
    }

    sha = dict(manifest["sha256"])
    sha["lifecycle-keys.tar.gz"] = hashlib.sha256((root / "lifecycle-keys.tar.gz").read_bytes()).hexdigest()

    upgraded = {
        **manifest,
        "backup_format_version": 5,
        "capture_scope": ["postgresql", "documents", "lifecycle_sqlite", "lifecycle_keys", "recovery_state"],
        "lifecycle_keys": keys,
        "files": sorted(set(manifest["files"]) | {"lifecycle-keys.tar.gz"}),
        "sha256": sha,
    }
    (root / "manifest.json").write_text(json.dumps(upgraded), encoding="utf-8")

    assert verify_capture(root, upgraded, require_s2=True) is True


def test_format_5_refuses_missing_or_tampered_key_archives(laboratory, monkeypatch, tmp_path):
    root, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    authentication = b"authentication-key-v1"
    admission = b"admission-key-v1"
    _write_keys_archive(root / "lifecycle-keys.tar.gz", authentication, admission)

    keys = {
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
    }

    sha = dict(manifest["sha256"])
    sha["lifecycle-keys.tar.gz"] = hashlib.sha256((root / "lifecycle-keys.tar.gz").read_bytes()).hexdigest()
    upgraded = {
        **manifest,
        "backup_format_version": 5,
        "capture_scope": ["postgresql", "documents", "lifecycle_sqlite", "lifecycle_keys", "recovery_state"],
        "lifecycle_keys": keys,
        "files": sorted(set(manifest["files"]) | {"lifecycle-keys.tar.gz"}),
        "sha256": sha,
    }

    # Missing archive.
    missing = root / "lifecycle-keys.tar.gz"
    missing.unlink()
    with pytest.raises(SystemExit, match="missing|Unexpected"):
        verify_capture(root, upgraded, require_s2=True)

    # Tampered archive content.
    _write_keys_archive(root / "lifecycle-keys.tar.gz", authentication + b"tamper", admission)
    upgraded["sha256"]["lifecycle-keys.tar.gz"] = hashlib.sha256((root / "lifecycle-keys.tar.gz").read_bytes()).hexdigest()
    with pytest.raises(SystemExit, match="checksum|metadata mismatch"):
        verify_capture(root, upgraded, require_s2=True)


def test_format_5_refuses_permissive_permissions_or_unexpected_entries(laboratory, monkeypatch, tmp_path):
    root, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    authentication = b"authentication-key-v1"
    admission = b"admission-key-v1"
    _write_keys_archive(root / "lifecycle-keys.tar.gz", authentication, admission, mode=0o644, extra=True)

    keys = {
        "keys/authentication.key": {
            "size": len(authentication),
            "mode": 0o644,
            "sha256": hashlib.sha256(authentication).hexdigest(),
        },
        "keys/admission.key": {
            "size": len(admission),
            "mode": 0o644,
            "sha256": hashlib.sha256(admission).hexdigest(),
        },
    }

    sha = dict(manifest["sha256"])
    sha["lifecycle-keys.tar.gz"] = hashlib.sha256((root / "lifecycle-keys.tar.gz").read_bytes()).hexdigest()
    upgraded = {
        **manifest,
        "backup_format_version": 5,
        "capture_scope": ["postgresql", "documents", "lifecycle_sqlite", "lifecycle_keys", "recovery_state"],
        "lifecycle_keys": keys,
        "files": sorted(set(manifest["files"]) | {"lifecycle-keys.tar.gz"}),
        "sha256": sha,
    }

    with pytest.raises(SystemExit, match="Lifecycle key"):
        verify_capture(root, upgraded, require_s2=True)