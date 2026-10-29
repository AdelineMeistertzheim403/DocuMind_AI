from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ops.testing.lifecycle_lot21_holds import SyntheticHolds


def test_persistent_hold_is_scoped_and_review_is_required(tmp_path):
    root = tmp_path / 'holds'
    root.mkdir(mode=0o700)
    path = root / 'holds.sqlite'
    registry = SyntheticHolds(path)
    registry.initialize()
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    hold = {'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(uuid4()),
            'reason': 'legal_hold', 'reviewed_at': now, 'review_at': now + timedelta(days=30),
            'ends_at': None, 'end_event': 'legal_hold_lifted'}
    registry.create(hold, now)
    registry.create(hold, now)
    reopened = SyntheticHolds(path)
    assert len(reopened.for_scope(hold['scope_id'], now)) == 1
    assert reopened.for_scope(str(uuid4()), now) == []
    with pytest.raises(ValueError, match='review'):
        reopened.for_scope(hold['scope_id'], now + timedelta(days=30))
    with pytest.raises(ValueError, match='Conflicting'):
        reopened.create({**hold, 'scope_id': str(uuid4())}, now)
    with pytest.raises(ValueError, match='predates'):
        reopened.release(hold['id'], hold['responsible_id'], now - timedelta(seconds=1))
    reopened.release(hold['id'], hold['responsible_id'], now + timedelta(days=1))
    reopened.release(hold['id'], hold['responsible_id'], now + timedelta(days=1))
    with pytest.raises(ValueError, match='cannot be recreated'):
        reopened.create(hold, now)
    assert reopened.for_scope(hold['scope_id'], now + timedelta(days=1)) == []
    with reopened.store.connection() as db:
        assert [row['action'] for row in db.execute('SELECT action FROM synthetic_hold_history ORDER BY sequence')] == ['created', 'released']


def test_incomplete_hold_is_rejected(tmp_path):
    root = tmp_path / 'holds'
    root.mkdir(mode=0o700)
    registry = SyntheticHolds(root / 'holds.sqlite')
    registry.initialize()
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='Incomplete hold'):
        registry.create({'id': str(uuid4())}, now)
