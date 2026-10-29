"""Durable file/SQL invariants under synthetic commit faults, using fake documents."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db import make_engine, make_sessions
from backend.models import Document
from backend.services.document_integrity import check_document_integrity
from tests.conftest import OTHER_KEY


@contextmanager
def commit_fault(app, monkeypatch, outcome, deleting=False):
    engine = app.state.engine
    original = engine.dialect.do_commit
    state = {'armed': False, 'fired': False, 'committed': False}

    def flush(session, *args):
        rows = session.deleted if deleting else session.new
        if session.bind is engine and any(isinstance(row, Document) for row in rows):
            state['armed'] = True

    def commit(connection):
        if state['armed'] and not state['fired']:
            state['fired'] = True
            if outcome == 'committed':
                original(connection)
                state['committed'] = True
            raise engine.dialect.dbapi.OperationalError('synthetic commit fault')
        return original(connection)

    def before_commit(session):
        if outcome == 'before' and session.bind is engine and state['armed'] and not state['fired']:
            state['fired'] = True
            raise SQLAlchemyError('synthetic pre-commit failure')

    event.listen(Session, 'before_flush', flush)
    event.listen(Session, 'before_commit', before_commit)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(engine.dialect, 'do_commit', commit)
            yield state
    finally:
        event.remove(Session, 'before_flush', flush)
        event.remove(Session, 'before_commit', before_commit)


@contextmanager
def durable(app):
    engine = make_engine(app.state.settings.database_url)
    try:
        with make_sessions(engine)() as session:
            yield session
    finally:
        engine.dispose()


def upload(client):
    return client.post('/api/v1/documents', files={'file': ('synthetic.txt', b'Fictitious source.', 'text/plain')})


@pytest.mark.parametrize('outcome', ['before', 'uncommitted', 'committed'])
def test_import_commit_fault_preserves_durable_source_and_recovers(client, app, monkeypatch, outcome):
    with commit_fault(app, monkeypatch, outcome) as fault:
        result = upload(client)
    assert result.status_code == 503 and fault['fired']
    with durable(app) as session:
        rows = session.scalars(select(Document)).all()
        assert len(rows) == int(outcome == 'committed')
        for row in rows:
            assert (app.state.settings.storage_dir / row.storage_name).read_bytes() == b'Fictitious source.'
    if outcome != 'committed':
        assert list(app.state.settings.storage_dir.iterdir()) == []
    assert upload(client).status_code == 201
    # No retry/idempotency promise: a repeated POST is a second, owner-isolated document.
    assert client.get('/api/v1/documents').json()['total'] == 1 + int(outcome == 'committed')
    client.headers['X-API-Key'] = OTHER_KEY
    assert client.get('/api/v1/documents').json()['total'] == 0


@pytest.mark.parametrize('outcome', ['uncommitted', 'committed'])
def test_delete_commit_fault_never_removes_an_active_source(client, app, monkeypatch, outcome):
    created = upload(client)
    assert created.status_code == 201
    with durable(app) as session:
        row = session.scalar(select(Document))
        path = app.state.settings.storage_dir / row.storage_name
    with commit_fault(app, monkeypatch, outcome, deleting=True) as fault:
        response = client.delete('/api/v1/documents/' + created.json()['id'])
    assert response.status_code == 503 and fault['fired']
    with durable(app) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == int(outcome != 'committed')
    if outcome != 'committed':
        assert path.read_bytes() == b'Fictitious source.'
    assert not list(app.state.settings.storage_dir.glob('*.deleted'))
    assert upload(client).status_code == 201


@pytest.mark.parametrize('outcome', ['uncommitted', 'committed'])
def test_unverifiable_import_retains_private_source_across_restart(client, app, monkeypatch, outcome):
    from backend.main import create_app
    from fastapi.testclient import TestClient
    from tests.conftest import KEY
    with monkeypatch.context() as patch:
        patch.setattr('backend.services.documents.durable_document_state', lambda *args: 'unknown')
        with commit_fault(app, patch, outcome):
            assert upload(client).status_code == 503
    retained = list(app.state.settings.storage_dir.iterdir())
    assert len(retained) == 1 and retained[0].read_bytes() == b'Fictitious source.'
    restarted = create_app(app.state.settings)
    try:
        with TestClient(restarted) as other:
            other.headers['X-API-Key'] = KEY
            assert other.get('/api/v1/documents').json()['total'] == int(outcome == 'committed')
            # Files are never a public directory, even when their names are known.
            assert other.get('/' + retained[0].name).status_code == 404
            other.headers['X-API-Key'] = OTHER_KEY
            assert other.get('/api/v1/documents').json()['total'] == 0
        assert retained[0].is_file()
    finally:
        restarted.state.authentication_engine.dispose()
        restarted.state.engine.dispose()


def test_commit_verification_discards_suspect_connection_and_uses_nullpool(client, app, monkeypatch):
    import backend.services.document_integrity as integrity
    from sqlalchemy.pool import NullPool
    original = integrity.create_engine
    observed = []
    invalidated = []
    def factory(*args, **kwargs):
        assert kwargs['poolclass'] is NullPool
        assert invalidated, 'Suspect physical connection must be invalidated first'
        observed.append(True)
        return original(*args, **kwargs)
    def invalidation(*args):
        invalidated.append(True)
    event.listen(app.state.engine, 'invalidate', invalidation)
    try:
        monkeypatch.setattr(integrity, 'create_engine', factory)
        with commit_fault(app, monkeypatch, 'uncommitted'):
            assert upload(client).status_code == 503
    finally:
        event.remove(app.state.engine, 'invalidate', invalidation)
    assert observed and invalidated
    assert client.get('/api/v1/health').status_code == 200
    assert upload(client).status_code == 201


def test_retained_files_bound_new_imports_without_purging(client, app, monkeypatch):
    root = app.state.settings.storage_dir
    orphan = root / ('a' * 32 + '.txt')
    orphan.write_bytes(b'Unreferenced fake source.')
    app.state.settings.document_retention_max_files = 1
    assert upload(client).status_code == 503
    assert orphan.read_bytes() == b'Unreferenced fake source.'
    assert list(root.iterdir()) == [orphan]


def test_retained_byte_budget_blocks_without_deleting_evidence(client, app):
    root = app.state.settings.storage_dir
    orphan = root / ('a' * 32 + '.txt')
    orphan.write_bytes(b'x' * 1024)
    app.state.settings.document_retention_max_bytes = 1024
    assert upload(client).status_code == 503
    assert orphan.stat().st_size == 1024


def test_independent_verification_connection_failure_retains_source(client, app, monkeypatch):
    import backend.services.document_integrity as integrity
    def unavailable(*args, **kwargs):
        raise SQLAlchemyError('fictitious secret DSN must not escape')
    with monkeypatch.context() as patch:
        patch.setattr(integrity, 'create_engine', unavailable)
        with commit_fault(app, patch, 'committed'):
            response = upload(client)
    assert response.status_code == 503 and 'fictitious secret' not in response.text
    with durable(app) as session:
        row = session.scalar(select(Document))
        assert (app.state.settings.storage_dir / row.storage_name).is_file()
    assert upload(client).status_code == 201


@pytest.mark.parametrize('outcome', ['uncommitted', 'committed'])
def test_unverifiable_delete_retains_source_without_tombstone(client, app, monkeypatch, outcome):
    response = upload(client)
    source = next(app.state.settings.storage_dir.glob('*.txt'))
    with monkeypatch.context() as patch:
        patch.setattr('backend.services.documents.durable_document_state', lambda *args: 'unknown')
        with commit_fault(app, patch, outcome, deleting=True):
            assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    assert source.read_bytes() == b'Fictitious source.'
    assert not list(app.state.settings.storage_dir.glob('*.deleted'))


def test_verification_identity_mismatch_is_not_cleanup_permission(client, app):
    from backend.services.document_integrity import durable_document_state, identity_of
    assert upload(client).status_code == 201
    with durable(app) as session:
        identity = identity_of(session.scalar(select(Document)))
    assert durable_document_state(app.state.engine, identity) == 'present'
    forged = (*identity[:-1], '0' * 64)
    assert durable_document_state(app.state.engine, forged) == 'unknown'


@pytest.mark.skipif(os.name != 'posix', reason='Linux no-follow and Unix file permissions')
@pytest.mark.posix
def test_checker_refuses_symlink_and_import_is_private(client, app, tmp_path):
    assert upload(client).status_code == 201
    source = next(app.state.settings.storage_dir.glob('*.txt'))
    assert source.stat().st_mode & 0o777 == 0o600
    external = tmp_path / 'fake-private.txt'
    external.write_bytes(b'Fictitious secret, never read.')
    source.unlink()
    source.symlink_to(external)
    report = check_document_integrity(app.state.engine, app.state.settings.storage_dir)
    assert report['unsafe_identity'] == 1 and not report['consistent']
    assert external.read_bytes() == b'Fictitious secret, never read.'


def test_postgresql_verifier_waits_for_original_writer_fence(client, app, monkeypatch):
    if app.state.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL row-lock ordering requires disposable PostgreSQL')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import text
    import backend.services.document_integrity as integrity
    assert upload(client).status_code == 201
    with durable(app) as session:
        identity = integrity.identity_of(session.scalar(select(Document)))
    entered = Event()
    original = integrity.create_engine
    def factory(*args, **kwargs):
        engine = original(*args, **kwargs)
        def executing(connection, cursor, statement, *args):
            assert 'FOR UPDATE' in statement if not entered.is_set() else True
            entered.set()
        event.listen(engine, 'before_cursor_execute', executing)
        return engine
    monkeypatch.setattr(integrity, 'create_engine', factory)
    with app.state.engine.connect() as writer, ThreadPoolExecutor(max_workers=1) as executor:
        writer.execute(text("SELECT id FROM ai_budgets WHERE id='development' FOR UPDATE"))
        writer.execute(Document.__table__.delete().where(Document.id == identity[0]))
        future = executor.submit(integrity.durable_document_state, app.state.engine, identity)
        try:
            assert entered.wait(3)
            assert not future.done()
        finally:
            writer.commit()
        assert future.result(timeout=5) == 'absent'


def test_readonly_checker_detects_missing_corrupt_partial_tombstone_and_unsafe_identity(client, app):
    assert upload(client).status_code == 201
    root = app.state.settings.storage_dir
    report = check_document_integrity(app.state.engine, root)
    assert report['consistent'] and report['checked'] == 1
    source = next(root.glob('*.txt'))
    before = source.read_bytes()
    source.write_bytes(b'Wrong size and hash.')
    report = check_document_integrity(app.state.engine, root)
    assert report['size_mismatch'] == report['sha256_mismatch'] == 1
    source.unlink()  # Only this test's fictitious source.
    (root / ('b' * 32 + '.part')).write_bytes(b'Partial fake upload.')
    (root / ('c' * 32 + '.txt.deleted')).write_bytes(b'Old fake tombstone.')
    (root / ('d' * 32 + '.txt')).write_bytes(before)
    snapshot = {p.name: p.read_bytes() for p in root.iterdir()}
    report = check_document_integrity(app.state.engine, root)
    assert not report['consistent']
    assert report['missing'] == report['partials'] == report['tombstones'] == report['unreferenced'] == 1
    assert {p.name: p.read_bytes() for p in root.iterdir()} == snapshot
    with app.state.sessions() as session:
        row = session.scalar(select(Document))
        row.storage_name = '../private-identity.txt'
        session.commit()
    report = check_document_integrity(app.state.engine, root)
    assert report['unsafe_identity'] == 1
    serialized = json.dumps(report)
    for private in ('synthetic', 'private-identity', str(root), source.name):
        assert private not in serialized


@pytest.mark.parametrize('stage', ['part', 'renamed', 'committed', 'delete-uncommitted', 'delete-committed'])
def test_abrupt_process_exit_retains_sources_at_critical_boundaries(app, client, stage, tmp_path):
    # Separate spawned interpreter, fake DB/storage only. os._exit skips finally,
    # rollback and interpreter cleanup, unlike raising an exception in the parent.
    script = Path(__file__).with_name('document_integrity_crash_child.py')
    if stage.startswith('delete-'):
        assert upload(client).status_code == 201
    configuration = tmp_path / 'child-config.json'
    configuration.write_text(json.dumps({'database_url': app.state.settings.database_url,
        'storage_dir': str(app.state.settings.storage_dir), 'extraction_mode': 'development',
        'lifecycle_durable_receipts_required': app.state.settings.lifecycle_durable_receipts_required}), encoding='utf-8')
    # Dedicated test DB only; no authentication material is passed to this child.
    result = subprocess.run([sys.executable, str(script), str(configuration), stage],
                            capture_output=True, timeout=30)
    assert result.returncode == 73, (result.returncode, result.stderr.decode(errors='replace'))
    root = app.state.settings.storage_dir
    with durable(app) as session:
        rows = session.scalars(select(Document)).all()
        assert len(rows) == int(stage in ('committed', 'delete-uncommitted'))
        for row in rows:
            source = root / row.storage_name
            assert source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == row.sha256
    assert len(list(root.iterdir())) == 1
    assert not list(root.glob('*.deleted'))
    report = check_document_integrity(app.state.engine, root)
    assert report['consistent'] == bool(rows)
