from io import BytesIO
from uuid import UUID

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.maintenance import reconcile
from backend.models import Document
from backend.services.documents import delete_document, import_document
from tests.test_lifecycle_durability import attach_legacy_owner, enable, ledgers


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


@pytest.mark.posix
def test_failed_uncommitted_upload_cleans_temporary_without_lifecycle_receipt(app, ledgers):
    # A strict temporary cleanup needs a real, available hold authority, even
    # though an unpublished source needs neither an erasure receipt nor a mutation switch.
    attach_legacy_owner(app)
    enable(app, ledgers)
    settings = app.state.settings
    settings.lifecycle_durable_receipts_required = True
    settings.lifecycle_synthetic_mutations_enabled = False
    settings.storage_dir.mkdir(mode=0o700)

    def fail_before_commit():
        raise RuntimeError("synthetic pre-commit failure")

    with app.state.sessions() as session:
        upload = UploadFile(filename="partial.txt", file=BytesIO(b"Partial upload."))
        with pytest.raises(RuntimeError, match="synthetic pre-commit failure"):
            import_document(
                session, settings, upload, UUID(int=1), app.state.slots,
                before_commit=fail_before_commit,
            )

    assert not list(settings.storage_dir.glob("*.part"))
    with ledgers[0].connection() as ledger:
        assert ledger.execute('SELECT count(*) FROM document_erasures').fetchone()[0] == 0


@pytest.mark.parametrize('state', ['unknown', 'present'])
def test_failed_temporary_cleanup_preserves_unproven_publication(app, monkeypatch, state):
    from backend.services import documents
    settings = app.state.settings
    settings.storage_dir.mkdir(mode=0o700)
    monkeypatch.setattr(documents, 'durable_document_state', lambda *args: state)
    def interrupted():
        raise RuntimeError('synthetic extraction interrupted')
    with app.state.sessions() as session:
        with pytest.raises(RuntimeError, match='interrupted'):
            import_document(session, settings, UploadFile(filename='fake.txt', file=BytesIO(b'private temporary')),
                            UUID(int=1), app.state.slots, before_commit=interrupted)
    assert [path.read_bytes() for path in settings.storage_dir.glob('*.part')] == [b'private temporary']
    assert app.state.slots.acquire(blocking=False)
    app.state.slots.release()


def test_failed_upload_never_cleans_an_independently_published_source(app):
    import hashlib
    settings = app.state.settings
    settings.storage_dir.mkdir(mode=0o700)
    published = []
    def publish_then_fail():
        temporary = next(settings.storage_dir.glob('*.part'))
        data = temporary.read_bytes()
        final = temporary.with_suffix('.txt')
        final.write_bytes(data)
        with app.state.sessions() as other:
            document = Document(owner_id=UUID(int=1), filename='synthetic.txt', storage_name=final.name,
                                media_type='text/plain', size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            other.add(document)
            other.commit()
            published.append((document.id, final))
        raise RuntimeError('synthetic partial publication')
    with app.state.sessions() as session:
        with pytest.raises(RuntimeError, match='partial publication'):
            import_document(session, settings, UploadFile(filename='fake.txt', file=BytesIO(b'published source')),
                            UUID(int=1), app.state.slots, before_commit=publish_then_fail)
    identifier, final = published[0]
    assert final.read_bytes() == b'published source'
    assert [path.read_bytes() for path in settings.storage_dir.glob('*.part')] == [b'published source']
    with app.state.sessions() as session:
        assert session.get(Document, identifier) is not None


@pytest.mark.parametrize('replacement', ['inode', pytest.param('symlink', marks=pytest.mark.posix), 'hardlink'])
def test_failed_upload_never_adopts_replaced_or_linked_temporary(app, replacement):
    import os
    settings = app.state.settings
    settings.storage_dir.mkdir(mode=0o700)
    def replace_then_fail():
        temporary = next(settings.storage_dir.glob('*.part'))
        evidence = temporary.with_suffix('.kept')
        if replacement == 'hardlink':
            os.link(temporary, evidence)
        else:
            temporary.rename(evidence)
            if replacement == 'inode': temporary.write_bytes(b'replacement')
            else: temporary.symlink_to(evidence)
        raise RuntimeError('synthetic temporary identity changed')
    with app.state.sessions() as session:
        with pytest.raises(RuntimeError, match='identity changed'):
            import_document(session, settings, UploadFile(filename='fake.txt', file=BytesIO(b'owned source')),
                            UUID(int=1), app.state.slots, before_commit=replace_then_fail)
    assert len(list(settings.storage_dir.glob('*.part'))) == 1
    assert [path.read_bytes() for path in settings.storage_dir.glob('*.kept')] == [b'owned source']


@pytest.mark.parametrize('suffix', ['.part', '.txt'])
def test_failed_upload_never_cleans_a_preexisting_token(app, monkeypatch, suffix):
    from backend.services import documents
    from fastapi import HTTPException
    token = UUID(int=8123)
    settings = app.state.settings
    settings.storage_dir.mkdir(mode=0o700)
    path = settings.storage_dir / (token.hex + suffix)
    path.write_bytes(b'preexisting protected bytes')
    monkeypatch.setattr(documents, 'uuid4', lambda: token)
    with app.state.sessions() as session:
        with pytest.raises(FileExistsError if suffix == '.part' else HTTPException):
            import_document(session, settings, UploadFile(filename='fake.txt', file=BytesIO(b'new source')),
                            UUID(int=1), app.state.slots)
    assert path.read_bytes() == b'preexisting protected bytes'


@pytest.mark.posix
def test_failed_upload_preserves_a_token_with_protected_deletion_history(app, client, ledgers, monkeypatch):
    from backend.services import documents
    from tests.test_lifecycle_lot22_integration import holds, hold_for
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('old.txt', b'old synthetic source', 'text/plain')})
    assert response.status_code == 201
    identifier = UUID(response.json()['id'])
    with app.state.sessions() as session:
        token = UUID(hex=session.get(Document, identifier).storage_name.split('.')[0])
    assert client.delete('/api/v1/documents/' + str(identifier)).status_code == 204
    hold, at = hold_for('document', identifier)
    holds(app.state.settings).create(hold, at)
    monkeypatch.setattr(documents, 'uuid4', lambda: token)
    def interrupted(): raise RuntimeError('synthetic history collision')
    with app.state.sessions() as session:
        with pytest.raises(RuntimeError, match='history collision'):
            import_document(session, app.state.settings, UploadFile(filename='new.txt', file=BytesIO(b'new temporary')),
                            UUID(int=1), app.state.slots, before_commit=interrupted)
    assert (app.state.settings.storage_dir / (token.hex + '.part')).read_bytes() == b'new temporary'
    with app.state.sessions() as session:
        assert session.get(Document, identifier) is None
    with ledgers[0].connection() as ledger:
        assert ledger.execute('SELECT state FROM document_erasures WHERE document_id=?', (str(identifier),)).fetchone()[0] == 'active_erased'


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
    from backend.maintenance import reconciliation_plan
    reconcile(app.state.settings, apply=True, offline_confirmed=True,
              approved_plan_sha256=reconciliation_plan(app.state.settings)['plan_sha256'])
    assert path.exists() and not tombstone.exists() and not orphan.exists()
    assert unrelated.exists()
