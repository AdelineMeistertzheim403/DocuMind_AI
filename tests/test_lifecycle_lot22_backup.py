"""Persistent backup tests use isolated synthetic paths and synthetic keys only."""
from datetime import datetime, timedelta, timezone
import base64
import json
import os
import sqlite3
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag

from backend.lifecycle_registry import Registry
from backend.lifecycle_durability import canonical
from ops.testing.lifecycle_lot22_backup import PersistentSyntheticBackups

# Every test builds PersistentSyntheticBackups: private POSIX directories/keys and O_NOFOLLOW.
pytestmark = pytest.mark.posix


@pytest.fixture
def persistent_backups(tmp_path, monkeypatch):
    monkeypatch.setenv('PHASE154L22_SYNTHETIC', 'isolated')
    (tmp_path / '.synthetic-only').write_bytes(b'documind-synthetic-only\n')
    for name in ('registry', 'copies', 'alerts', 'keys'):
        (tmp_path / name).mkdir(mode=0o700)
    keys = {}
    for version in ('v1', 'v2'):
        path = tmp_path / 'keys' / (version + '.key')
        path.write_bytes(os.urandom(32))
        os.chmod(path, 0o600)
        keys[version] = path
    registry = Registry(tmp_path / 'registry' / 'registry.sqlite')
    registry.initialize()
    backup = PersistentSyntheticBackups(registry, tmp_path / 'copies', tmp_path / 'alerts',
                                        keys, 'v1', tmp_path)
    return backup, registry, keys, tmp_path


def test_persistent_daily_updates_rotation_and_seven_day_boundaries(persistent_backups):
    backup, registry, keys, root = persistent_backups
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    first = backup.daily(at)
    assert backup.daily(at) is None
    user, owner = uuid4(), uuid4()
    registry.receive('erasure', user_id=user, owner_id=owner, received_at=at)
    update = backup.after_administrative_update(at + timedelta(hours=1))
    backup.rotate('v2')
    following = backup.daily(at + timedelta(days=1))
    reopened = PersistentSyntheticBackups(registry, root / 'copies', root / 'alerts', keys, 'v2', root)
    assert reopened.daily(at + timedelta(days=1)) is None
    assert [reopened.restore(path)[0]['key_version'] for path in (first, update, following)] == ['v1', 'v1', 'v2']
    with sqlite3.connect(':memory:') as db:
        db.deserialize(reopened.restore(update)[1])
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 1
    assert str(user).encode() not in update.read_bytes()
    plan = {item['id']: item for item in reopened.retention_plan(at + timedelta(days=7))}
    first_id = reopened.restore(first)[0]['id']
    update_id = reopened.restore(update)[0]['id']
    assert plan[first_id]['eligible_simulated']
    assert not plan[update_id]['eligible_simulated']
    assert plan[first_id]['target_at'] == (at + timedelta(days=8)).isoformat()
    assert all(path.exists() for path in (first, update, following))


def test_corrupt_archive_and_wrong_key_raise_and_persist_alert(persistent_backups):
    backup, _, keys, root = persistent_backups
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    archive = backup.daily(at)
    keys['v1'].write_bytes(os.urandom(32))
    with pytest.raises(InvalidTag):
        backup.daily(at + timedelta(days=1))
    assert 'snapshot_failed' in (root / 'alerts' / 'alerts.jsonl').read_text(encoding='utf-8')
    assert archive.exists()
    assert len(list((root / 'copies').glob('*.json'))) == 1


@pytest.mark.parametrize('fault', ['metadata', 'ciphertext', 'truncated', 'missing_key'])
def test_archive_tampering_and_missing_key_never_restore(persistent_backups, fault):
    backup, _, _, _ = persistent_backups
    archive = backup.daily(datetime(2026, 10, 27, tzinfo=timezone.utc))
    envelope = json.loads(archive.read_bytes())
    if fault == 'metadata':
        envelope['metadata']['reason'] = 'administrative_update'
    elif fault == 'ciphertext':
        ciphertext = bytearray(base64.b64decode(envelope['ciphertext']))
        ciphertext[-1] ^= 1
        envelope['ciphertext'] = base64.b64encode(ciphertext).decode()
    elif fault == 'truncated':
        archive.write_bytes(b'{"metadata":')
    else:
        backup.keys.pop('v1')
    if fault in ('metadata', 'ciphertext'):
        archive.write_text(canonical(envelope), encoding='utf-8')
    with pytest.raises((ValueError, InvalidTag)):
        backup.restore(archive)


def test_snapshot_interruption_leaves_evidence_and_blocks_next_run(persistent_backups, monkeypatch):
    backup, _, _, root = persistent_backups
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    first = backup.daily(at)
    monkeypatch.setattr(os, 'link', lambda *args: (_ for _ in ()).throw(OSError('synthetic disk failure')))
    with pytest.raises(OSError):
        backup.after_administrative_update(at + timedelta(hours=1))
    assert first.exists()
    partials = list((root / 'copies').glob('*.part'))
    assert len(partials) == 1
    with pytest.raises(ValueError, match='Incomplete'):
        backup.restore(partials[0])
    with pytest.raises(ValueError, match='Interrupted'):
        backup.daily(at + timedelta(days=1))
    assert (root / 'alerts' / 'alerts.jsonl').read_text(encoding='utf-8').count('snapshot_failed') == 2


def test_backup_source_failure_and_clock_rollback_are_explicit(persistent_backups, monkeypatch):
    backup, registry, _, root = persistent_backups
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    backup.daily(at)
    with pytest.raises(ValueError, match='clock moved backwards'):
        backup.daily(at - timedelta(seconds=1))
    monkeypatch.setattr(registry, 'connection', lambda: (_ for _ in ()).throw(OSError('synthetic source failure')))
    with pytest.raises(OSError):
        backup.after_administrative_update(at + timedelta(hours=1))
    assert (root / 'alerts' / 'alerts.jsonl').read_text(encoding='utf-8').count('snapshot_failed') == 2


def test_simulated_monthly_restoration_after_process_recreation(persistent_backups):
    backup, registry, keys, root = persistent_backups
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for day in range(31):
        backup.daily(at + timedelta(days=day))
    reopened = PersistentSyntheticBackups(registry, root / 'copies', root / 'alerts', keys, 'v1', root)
    archives = sorted((root / 'copies').glob('*.json'))
    assert len(archives) == 31
    for archive in archives:
        metadata, plaintext = reopened.restore(archive)
        assert metadata['reason'] == 'daily' and plaintext.startswith(b'SQLite format 3')


def test_backup_requires_synthetic_marker_and_separate_directories(persistent_backups):
    _, registry, keys, root = persistent_backups
    with pytest.raises(ValueError, match='Separate'):
        PersistentSyntheticBackups(registry, root / 'registry', root / 'alerts', keys, 'v1', root)
    with pytest.raises(ValueError, match='inside'):
        PersistentSyntheticBackups(registry, root / 'copies', root / 'alerts',
                                   {'v1': root.parent / 'outside.key'}, 'v1', root)
