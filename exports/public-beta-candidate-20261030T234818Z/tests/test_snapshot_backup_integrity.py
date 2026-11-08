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
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("database.dump", "documents.tar.gz", "lifecycle.sqlite.tar.gz", "integrity.json")
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
        "backup_format_version": 3,
        "capture_id": capture_id,
        "capture_complete": True,
        "s2_recovery_authorized": False,
        "recovery_disposition": "quarantine_pending_independent_freshness_and_operator_review",
        "capture_scope": ["postgresql", "documents", "lifecycle_sqlite"],
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
