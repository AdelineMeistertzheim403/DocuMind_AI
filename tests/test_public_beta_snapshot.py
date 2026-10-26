"""Backward-compatible quota inventory; no real Docker, SMTP or credentials in unit tests."""
import json
import os
import hashlib
import re
import subprocess
import tarfile
from uuid import uuid4
from pathlib import Path

import pytest

from tools.verify_snapshot import verify_snapshot
from tests.test_public_beta import beta, enroll


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


@pytest.mark.skipif(not os.environ.get('TEST_SNAPSHOT_COMPOSE'), reason='Requires the explicit disposable Docker backup project')
@pytest.mark.parametrize('closed', [False, True])
@pytest.mark.parametrize('legacy', [False, True])
def test_real_backup_and_independent_restore_preserve_then_seal_quota(beta, tmp_path, closed, legacy):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from tools.backup_local import create_backup
    from tools.validate_restore import seal_restored_registration
    from backend.account_models import PublicRegistrationQuota
    client, app, sent = beta
    assert app.state.engine.dialect.name == 'postgresql'
    compose = json.loads(os.environ['TEST_SNAPSHOT_COMPOSE'])
    assert compose[:3] == ['docker', '--host', 'npipe:////./pipe/dockerDesktopLinuxEngine']
    assert 'documind-s14-4-backup-20261025-f94b' in compose
    app.state.settings.public_registration_limit = 5
    for index in range(4):
        enroll(beta, f'restore-{index}@example.test')
    with app.state.sessions() as db:
        db.get(PublicRegistrationQuota, 'public').closed = closed
        db.commit()
    snapshot_root = create_backup(compose, tmp_path / 'new-snapshot')
    manifest = json.loads((snapshot_root / 'manifest.json').read_text())
    assert manifest['integrity_version'] == 2 and manifest['migration'] == '0007'
    inventory = json.loads((snapshot_root / 'integrity.json').read_text())
    assert set(inventory['public_registration_quota']['columns']) == {'id', 'issued_count', 'closed'}
    assert verify_snapshot(snapshot_root, 'documind_beta_backup', compose)['quota_certified']
    with tarfile.open(snapshot_root / 'documents.tar.gz') as archive:
        assert 'documents/fictitious.txt' in archive.getnames()
    if legacy:
        # A NEW synthetic old-format copy, never edit the real source snapshot or any existing archive.
        import shutil
        old = tmp_path / 'synthetic-legacy-copy'
        shutil.copytree(snapshot_root, old)
        manifest.pop('integrity_version')
        inventory.pop('public_registration_quota')
        (old / 'manifest.json').write_text(json.dumps(manifest))
        (old / 'integrity.json').write_text(json.dumps(inventory))
        snapshot_root = old
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in snapshot_root.iterdir()}
    name = 'documind_restore_s14_4_' + uuid4().hex
    assert re.fullmatch(r'documind_restore_s14_4_[a-f0-9]{32}', name)
    url = make_url(app.state.settings.database_url)
    admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    restored = None
    created = False
    try:
        with admin.connect() as db:
            assert not db.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': name})
            db.execute(text(f'CREATE DATABASE {name}'))
            created = True
        with (snapshot_root / 'database.dump').open('rb') as dump:
            subprocess.run(compose + ['exec', '-T', 'db', 'pg_restore', '-U', 'documind_test', '-d', name,
                                      '--no-owner', '--exit-on-error'], stdin=dump, capture_output=True, check=True, timeout=30)
        assert verify_snapshot(snapshot_root, name, compose)['quota_certified'] == (not legacy)
        restored = create_engine(url.set(database=name))
        with restored.connect() as db:
            row = db.execute(text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")).one()
            assert row.issued_count == 4 and row.closed == closed
        # Restore fidelity is proven BEFORE deliberately closing only the offline copy.
        result = seal_restored_registration(restored)
        assert result == {'quota_present': True, 'closed': True, 'issued_count': 4, 'requires_review': True}
        assert checksums == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in snapshot_root.iterdir()}
        with app.state.sessions() as db:
            source = db.get(PublicRegistrationQuota, 'public')
            assert source.issued_count == 4 and source.closed == closed
    finally:
        if restored is not None:
            restored.dispose()
        if created:
            with admin.connect() as db:
                db.execute(text(f'DROP DATABASE {name}'))
        admin.dispose()


@pytest.mark.skipif(not os.environ.get('TEST_SNAPSHOT_COMPOSE'), reason='Requires the explicit disposable Docker backup project')
@pytest.mark.parametrize('field', ['issued_count', 'closed'])
def test_actual_postgresql_field_tampering_is_detected(beta, tmp_path, field):
    from sqlalchemy import text
    from tools.backup_local import create_backup
    client, app, sent = beta
    assert app.state.engine.dialect.name == 'postgresql'
    compose = json.loads(os.environ['TEST_SNAPSHOT_COMPOSE'])
    assert compose[:3] == ['docker', '--host', 'npipe:////./pipe/dockerDesktopLinuxEngine']
    assert 'documind-s14-4-backup-20261025-f94b' in compose
    root = create_backup(compose, tmp_path / 'tamper-proof-source')
    assert verify_snapshot(root, 'documind_beta_backup', compose)['quota_certified']
    with app.state.sessions() as db:
        statement = ('UPDATE public_registration_quota SET issued_count=issued_count+1' if field == 'issued_count'
                     else 'UPDATE public_registration_quota SET closed=true')
        db.execute(text(statement))
        db.commit()
    with pytest.raises(SystemExit, match='Integrity mismatch: public_registration_quota'):
        verify_snapshot(root, 'documind_beta_backup', compose)
