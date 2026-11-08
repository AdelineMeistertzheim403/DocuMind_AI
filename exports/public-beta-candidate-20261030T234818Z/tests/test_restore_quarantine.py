from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from backend.lifecycle_registry import Registry
from tools.validate_restore import (
    LAB_MARKER,
    LAB_MARKER_CONTENT,
    _isolated_url,
    _validate_lab,
    check_resurrection_denials,
)


def test_restore_requires_marked_local_synthetic_lab(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    root = tmp_path / "lab"
    snapshot.mkdir()
    root.mkdir()
    (root / LAB_MARKER).write_bytes(LAB_MARKER_CONTENT)
    (snapshot / "manifest.json").write_text("{}")
    monkeypatch.setenv("DOCUMIND_RESTORE_LAB", "isolated")
    _validate_lab(snapshot, "documind_restore_012345abcdef", root)

    monkeypatch.delenv("DOCUMIND_RESTORE_LAB")
    with pytest.raises(ValueError, match="Explicit isolated"):
        _validate_lab(snapshot, "documind_restore_012345abcdef", root)


def test_restore_database_url_must_target_explicit_loopback_admin(monkeypatch):
    monkeypatch.setenv(
        "DOCUMIND_RESTORE_DATABASE_URL",
        "postgresql+psycopg://synthetic:synthetic@127.0.0.1:55432/documind_restore_admin",
    )
    assert _isolated_url().database == "documind_restore_admin"
    monkeypatch.setenv(
        "DOCUMIND_RESTORE_DATABASE_URL",
        "postgresql+psycopg://synthetic:synthetic@example.test:5432/documind_restore_admin",
    )
    with pytest.raises(ValueError, match="loopback"):
        _isolated_url()


def test_resurrection_tombstones_block_reappearance_in_database_or_documents(tmp_path):
    registry_path = tmp_path / "registry" / "registry.sqlite"
    registry_path.parent.mkdir(mode=0o700)
    registry = Registry(registry_path)
    registry.initialize()
    document_id, owner_id = uuid4(), uuid4()
    user_id, account_owner_id = uuid4(), uuid4()
    receipt_id = registry.receive("erasure", user_id=user_id, owner_id=account_owner_id)
    registry.account_deactivated(receipt_id)
    storage_name = uuid4().hex + ".txt"
    registry.document_requested(document_id, owner_id, storage_name)
    registry.document_finished(document_id, True)

    root = tmp_path / "restore"
    root.mkdir()
    source = root / storage_name
    source.write_bytes(b"synthetic resurrected data")
    database = create_engine("sqlite://")
    with database.begin() as connection:
        connection.execute(text("CREATE TABLE documents (id TEXT, storage_name TEXT)"))
        connection.execute(text("CREATE TABLE users (id TEXT, owner_id TEXT, disabled_at TEXT)"))
        connection.execute(text(
            "INSERT INTO documents VALUES (:id,:name)"),
            {"id": str(document_id), "name": storage_name},
        )
        connection.execute(text("INSERT INTO users VALUES (:id,:owner,NULL)"),
                           {"id": str(user_id), "owner": str(account_owner_id)})

    result = check_resurrection_denials(database, registry_path, root)
    assert result["document_resurrections"] == 1
    assert result["account_resurrections"] == 1
    assert result["opening_authorized"] is False

    source.unlink()
    with database.begin() as connection:
        connection.execute(text("DELETE FROM documents"))
        connection.execute(text("UPDATE users SET disabled_at='2026-01-01T00:00:00+00:00'"))
    result = check_resurrection_denials(database, registry_path, root)
    assert result["document_resurrections"] == 0
    assert result["account_resurrections"] == 0
    database.dispose()
