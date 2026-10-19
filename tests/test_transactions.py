from io import BytesIO
from uuid import UUID

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.maintenance import reconcile
from backend.models import Document
from backend.services.documents import delete_document, import_document


def test_failed_upload_commit_removes_file_and_rows(app, client, monkeypatch):
    with app.state.sessions() as session:
        def fail_commit():
            raise SQLAlchemyError("simulated commit failure")
        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(SQLAlchemyError):
            upload = UploadFile(filename="test.txt", file=BytesIO(b"A document."))
            import_document(session, app.state.settings, upload, UUID(int=1), app.state.slots)
    assert not list(app.state.settings.storage_dir.iterdir())
    assert client.get("/api/v1/documents").json()["total"] == 0


def test_failed_delete_commit_restores_file(app, client, monkeypatch):
    identifier = client.post("/api/v1/documents", files={"file": ("test.txt", b"A document.")}).json()["id"]
    with app.state.sessions() as session:
        document = session.get(Document, UUID(identifier))
        filename = document.storage_name
        def fail_commit():
            raise SQLAlchemyError("simulated commit failure")
        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(SQLAlchemyError):
            delete_document(session, app.state.settings, document)
    assert (app.state.settings.storage_dir / filename).read_bytes() == b"A document."
    assert client.get(f"/api/v1/documents/{identifier}").status_code == 200


def test_offline_maintenance(app, client):
    client.post("/api/v1/documents", files={"file": ("test.txt", b"A document.")})
    root = app.state.settings.storage_dir
    with app.state.sessions() as session:
        document = session.scalar(select(Document))
        path = root / document.storage_name
    tombstone = path.with_suffix(path.suffix + ".deleted")
    path.replace(tombstone)
    orphan = root / ("a" * 32 + ".part")
    orphan.write_bytes(b"partial")
    unrelated = root / "keep.txt"
    unrelated.write_text("keep")
    actions = reconcile(app.state.settings)
    assert ("restore", tombstone.name) in actions
    assert ("delete", orphan.name) in actions
    assert tombstone.exists() and orphan.exists()
    reconcile(app.state.settings, apply=True)
    assert path.exists() and not tombstone.exists() and not orphan.exists()
    assert unrelated.exists()
