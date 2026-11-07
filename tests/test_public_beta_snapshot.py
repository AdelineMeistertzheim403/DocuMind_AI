"""Quota inventory and opt-in physical Linux snapshot/quarantine qualification."""
import json
import hashlib
import subprocess
import tarfile
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from tools.verify_snapshot import verify_snapshot
from tests.snapshot_docker_lab import (
    DOCUMENT, STORAGE_NAME, docker_snapshot_lab, snapshot_lab,
)


def snapshot(tmp_path, *, version=2, quota=True):
    tables = {name: {'count': 0, 'digest': 'empty'} for name in ('documents', 'document_pages', 'document_chunks', 'analyses')}
    if quota:
        tables['public_registration_quota'] = {'count': 1, 'digest': 'original', 'columns': ['id', 'issued_count', 'closed']}
    (tmp_path / 'integrity.json').write_text(json.dumps(tables))
    manifest = {'migration': '0007'}
    if version is not None:
        manifest['integrity_version'] = version
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    return tmp_path


def fake_sql(command, **kwargs):
    return '1|original' if 'FROM (SELECT id,issued_count,closed FROM public_registration_quota)' in command[-1] else '0|empty'


def test_new_snapshot_certifies_both_quota_fields(tmp_path, monkeypatch):
    monkeypatch.setattr('tools.verify_snapshot.subprocess.check_output', fake_sql)
    assert verify_snapshot(snapshot(tmp_path))['quota_certified']


def test_quota_digest_mismatch_is_detected(tmp_path, monkeypatch):
    def sql(command, **kwargs):
        return '1|modified' if 'public_registration_quota' in command[-1] else '0|empty'
    monkeypatch.setattr('tools.verify_snapshot.subprocess.check_output', sql)
    with pytest.raises(SystemExit, match='Integrity mismatch: public_registration_quota'):
        verify_snapshot(snapshot(tmp_path))


def test_new_schema_0007_inventory_cannot_silently_omit_quota(tmp_path):
    with pytest.raises(SystemExit, match='Missing public quota'):
        verify_snapshot(snapshot(tmp_path, quota=False))


def test_old_inventory_remains_readable_but_not_quota_certified(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr('tools.verify_snapshot.subprocess.check_output', fake_sql)
    result = verify_snapshot(snapshot(tmp_path, version=None, quota=False))
    assert not result['quota_certified']
    assert 'NOT certified' in capsys.readouterr().out


@pytest.mark.parametrize('columns', [['id'], ['id', 'issued_count'], ['id', 'closed']])
def test_partial_quota_projection_is_not_a_certificate(tmp_path, columns):
    root = snapshot(tmp_path)
    data = json.loads((root / 'integrity.json').read_text())
    data['public_registration_quota']['columns'] = columns
    (root / 'integrity.json').write_text(json.dumps(data))
    with pytest.raises(SystemExit, match='Incomplete public quota'):
        verify_snapshot(root)


@pytest.mark.parametrize('closed', [False, True])
def test_real_format3_backup_restores_faithfully_without_opening_quarantine(snapshot_lab, tmp_path, closed):
    from sqlalchemy import text
    from tools.verify_snapshot import verify_capture, LIFECYCLE_STORES
    from ops.testing.lifecycle_lot29_bundle import SyntheticLifecycleConsistencyVerifier
    lab = snapshot_lab
    try:
        lab.quota(closed=closed)
        source = lab.state()
        root = lab.capture(tmp_path / 'snapshot')
        manifest = json.loads((root / 'manifest.json').read_text())
        assert manifest['backup_format_version'] == 3 and manifest['migration'] == '0008'
        assert manifest['integrity_version'] == 2
        assert verify_capture(root, manifest, require_s2=True)
        assert verify_snapshot(root, database_url=lab.url)['quota_certified']
        inventory = json.loads((root / 'integrity.json').read_text())
        assert set(inventory['public_registration_quota']['columns']) == {'id', 'issued_count', 'closed'}
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        with tarfile.open(root / 'documents.tar.gz') as archive:
            assert archive.extractfile('documents/' + STORAGE_NAME).read() == DOCUMENT
        with lab.restored(root, tmp_path / 'restore-lab') as restored:
            result = restored.report
            assert result['status'] == 'quarantined'
            assert result['quota'] == {'issued_count': 4, 'closed': closed}
            assert result['documents_verified'] == 1 and result['lifecycle_stores_restored'] == 5
            assert not result['missing_documents'] and not result['unreferenced_documents']
            for field in ('critical_mutations_allowed', 'api_attached', 's2_recovery_authorized', 'opening_authorized'):
                assert result[field] is False
            assert json.loads((restored.root / 'quarantine.json').read_text()) == result
            document = restored.root / 'documents' / STORAGE_NAME
            assert document.read_bytes() == DOCUMENT and document.stat().st_mode & 0o077 == 0
            with lab.connection(restored.name) as db:
                assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0008'
                assert db.execute(text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")).one() == (4, closed)
                assert db.scalar(text('SELECT count(*) FROM users WHERE approved_at IS NOT NULL')) == 4
                assert db.scalar(text('SELECT text FROM document_pages')) == DOCUMENT.decode()
                assert db.scalar(text('SELECT sha256 FROM documents')) == hashlib.sha256(DOCUMENT).hexdigest()
                assert db.scalar(text('SELECT result FROM analyses')) == {'qualification': 'snapshot'}
            assert lab.database_state(restored.name) == source['rows']
            paths = {}
            for name, (version, tables) in LIFECYCLE_STORES.items():
                path = restored.root / 'lifecycle' / name / (name + '.sqlite')
                paths[name] = path
                assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['lifecycle_store_sha256'][name]
                assert path.stat().st_mode & 0o077 == 0
                with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
                    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                    assert db.execute('PRAGMA user_version').fetchone()[0] == version
                    assert {row[0] for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )} == tables
            verifier = SyntheticLifecycleConsistencyVerifier(
                bytes.fromhex(lab.seed['auth_key']), bytes.fromhex(lab.seed['admission_key']))
            assert verifier.verify(paths)['verified']
        assert lab.state() == source
        assert checksums == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        (Path('/results') / f'capture-closed-{str(closed).lower()}.json').write_text(
            json.dumps({'manifest': manifest, 'quarantine': result,
                        'source_unchanged': True, 'database_rows_equal': True,
                        'lifecycle_consistency_verified': True}, indent=2) + '\n',
            encoding='utf-8')
    finally:
        lab.quota(closed=False)


@pytest.mark.parametrize('field', ['issued_count', 'closed'])
def test_actual_postgresql_field_tampering_is_detected(snapshot_lab, tmp_path, field):
    from sqlalchemy import text
    lab = snapshot_lab
    root = lab.capture(tmp_path / 'snapshot')
    assert verify_snapshot(root, database_url=lab.url)['quota_certified']
    try:
        with lab.connection() as db:
            statement = ('UPDATE public_registration_quota SET issued_count=issued_count+1'
                         if field == 'issued_count' else 'UPDATE public_registration_quota SET closed=true')
            db.execute(text(statement))
        with pytest.raises(SystemExit, match='Integrity mismatch: public_registration_quota'):
            verify_snapshot(root, database_url=lab.url)
    finally:
        lab.quota(issued_count=4, closed=False)


@pytest.mark.parametrize('payload', ['database.dump', 'documents.tar.gz', 'lifecycle.sqlite.tar.gz', 'integrity.json'])
def test_altered_payload_is_refused_before_restore_creation(snapshot_lab, tmp_path, payload):
    lab = snapshot_lab
    root = lab.capture(tmp_path / 'snapshot')
    (root / payload).write_bytes((root / payload).read_bytes() + b'altered')
    destination = tmp_path / 'restore-lab'
    destination.mkdir(mode=0o700)
    (destination / '.synthetic-only').write_bytes(b'documind-isolated-restore-lab-v1\n')
    name = 'documind_restore_' + uuid4().hex[:12]
    result = lab.restore_command(root, destination, name)
    assert result.returncode != 0 and 'Backup payload checksum mismatch' in result.stderr
    assert not lab.exists(name) and not (destination / name).exists()


@pytest.mark.parametrize('version', [1, 2])
def test_coherent_historical_snapshot_is_readable_but_cannot_restore_s2(snapshot_lab, tmp_path, monkeypatch, version):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from tools.backup_local import _offline_api_compose
    lab = snapshot_lab
    historical = 'snapshot_legacy_' + uuid4().hex[:12]
    assert not lab.exists(historical)
    try:
        with lab.connection('postgres') as db:
            db.execute(text(f'CREATE DATABASE "{historical}"'))
        with monkeypatch.context() as patch:
            patch.setenv('DATABASE_URL', lab.url.set(database=historical).render_as_string(hide_password=False))
            command.upgrade(Config('alembic.ini'), '0007')
        from sqlalchemy import Table, MetaData
        with lab.connection() as source, lab.connection(historical) as target:
            for table in ('users', 'documents', 'document_pages', 'analyses', 'public_registration_quota'):
                original = Table(table, MetaData(), autoload_with=source)
                old = Table(table, MetaData(), autoload_with=target)
                rows = [{key: value for key, value in row.items() if key in old.c}
                        for row in source.execute(original.select()).mappings()]
                if rows:
                    target.execute(old.delete())
                    target.execute(old.insert(), rows)
        root = tmp_path / 'historical-snapshot'
        root.mkdir(mode=0o700)
        with (root / 'database.dump').open('wb') as output:
            subprocess.run(lab.compose + ['exec', '-T', 'db', 'pg_dump', '-U',
                'documind_snapshot', '-d', historical, '-Fc'], stdout=output, check=True, timeout=30)
        # Historical evidence is produced from its own real schema, not by relabelling a format-3 dump.
        with _offline_api_compose(lab.compose, None) as offline:
            with (root / 'documents.tar.gz').open('wb') as output:
                subprocess.run(offline + ['run', '--rm', '--no-deps', '-T', '--entrypoint',
                    'tar', 'api', '-C', '/app/var', '-czf', '-', 'documents'],
                    stdout=output, check=True, timeout=30)
        integrity = {}
        tables = ['documents', 'document_pages', 'document_chunks', 'analyses']
        if version == 2:
            tables.append('public_registration_quota')
        with lab.connection(historical) as db:
            for table in tables:
                columns = db.scalars(text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
                    "AND table_name=:table ORDER BY ordinal_position"), {'table': table}).all()
                count, digest = db.execute(text(
                    f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' "
                    f"ORDER BY row_to_json(t)::text),'')) FROM (SELECT {','.join(columns)} FROM {table}) t"
                )).one()
                integrity[table] = {'count': count, 'digest': digest, 'columns': columns}
            revision = db.scalar(text('SELECT version_num FROM alembic_version'))
        (root / 'integrity.json').write_text(json.dumps(integrity), encoding='utf-8')
        (root / 'manifest.json').write_text(json.dumps({
            'backup_format_version': version, 'migration': revision, 'database_major': 17,
            'integrity_version': version,
        }), encoding='utf-8')
        assert revision == '0007'
        result = verify_snapshot(root, database_url=lab.url.set(database=historical))
        assert result['quota_certified'] == (version == 2)
        assert result['capture_complete'] is False
        destination = tmp_path / 'restore-lab'
        destination.mkdir(mode=0o700)
        (destination / '.synthetic-only').write_bytes(b'documind-isolated-restore-lab-v1\n')
        name = 'documind_restore_' + uuid4().hex[:12]
        refusal = lab.restore_command(root, destination, name)
        assert refusal.returncode != 0 and 'Legacy snapshot lacks the five SQLite lifecycle stores' in refusal.stderr
        assert not lab.exists(name) and not (destination / name).exists()
    finally:
        lab.drop(historical)


def test_live_postgresql_client_prevents_capture(snapshot_lab, tmp_path):
    from sqlalchemy import text
    from tools.backup_local import create_backup
    lab = snapshot_lab
    destination = tmp_path / 'must-not-exist'
    with lab.connection() as db:
        db.execute(text('SELECT 1'))
        with pytest.raises(ValueError, match='Uncontrolled PostgreSQL client session'):
            create_backup(lab.compose, destination)
    assert not destination.exists()


def test_running_api_prevents_capture(snapshot_lab, tmp_path):
    from tools.backup_local import create_backup
    lab = snapshot_lab
    destination = tmp_path / 'must-not-exist'
    try:
        subprocess.run(lab.compose + ['up', '-d', '--no-deps', 'api'], check=True, timeout=30)
        with pytest.raises(ValueError, match='Only the database may run'):
            create_backup(lab.compose, destination)
        assert not destination.exists()
    finally:
        subprocess.run(lab.compose + ['rm', '--stop', '--force', 'api'], check=True, timeout=30)
