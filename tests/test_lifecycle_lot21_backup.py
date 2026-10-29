from datetime import datetime, timedelta, timezone
import os
import sqlite3
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag

from backend.lifecycle_registry import Registry
from ops.testing.lifecycle_lot21_backup import SyntheticBackupSimulation


def test_daily_update_rotation_recovery_and_retention_are_simulated(tmp_path):
    root = tmp_path / 'ledger'
    root.mkdir(mode=0o700)
    registry = Registry(root / 'registry.sqlite')
    registry.initialize()
    keys = {'v1': os.urandom(32), 'v2': os.urandom(32)}
    simulation = SyntheticBackupSimulation(registry, keys, 'v1')
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    first = simulation.daily(at)
    assert simulation.daily(at) is None
    registry.receive('erasure', user_id=uuid4(), owner_id=uuid4(), received_at=at)
    updated = simulation.after_administrative_update(at + timedelta(hours=1))
    simulation.rotate('v2')
    second_day = simulation.daily(at + timedelta(days=1))
    assert [item['metadata']['key_version'] for item in simulation.copies] == ['v1', 'v1', 'v2']
    with sqlite3.connect(':memory:') as db:
        db.deserialize(simulation.restore(updated))
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 1
    assert simulation.restore(first) and simulation.restore(second_day)
    plan = simulation.retention_plan(at + timedelta(days=7))
    assert plan[0]['eligible_simulated'] and not plan[1]['eligible_simulated']
    assert plan[0]['target_at'] == (at + timedelta(days=8)).isoformat()
    assert len(simulation.copies) == 3
    simulation.keys.pop('v1')
    with pytest.raises(ValueError, match='key unavailable'):
        simulation.restore(first)


def test_wrong_key_metadata_and_snapshot_failure_are_reported(tmp_path, monkeypatch):
    root = tmp_path / 'ledger'
    root.mkdir(mode=0o700)
    registry = Registry(root / 'registry.sqlite')
    registry.initialize()
    simulation = SyntheticBackupSimulation(registry, {'v1': os.urandom(32)}, 'v1')
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    copy = simulation.daily(at)
    tampered = {**copy, 'metadata': {**copy['metadata'], 'reason': 'administrative_update'}}
    with pytest.raises(InvalidTag):
        simulation.restore(tampered)
    simulation.keys['v1'] = os.urandom(32)
    with pytest.raises(InvalidTag):
        simulation.restore(copy)
    monkeypatch.setattr(registry, 'connection', lambda: (_ for _ in ()).throw(OSError('synthetic outage')))
    with pytest.raises(OSError):
        simulation.daily(at + timedelta(days=1))
    assert len(simulation.copies) == 1
    assert simulation.alerts[0]['reason'] == 'snapshot_failed'
