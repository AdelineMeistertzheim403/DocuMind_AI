"""Authentication experiments use exclusively synthetic keys and data."""
import hashlib
import os
from uuid import uuid4

import pytest

from ops.testing.lifecycle_lot21_confirmation import SyntheticAuthenticatedConfirmation


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / 'independent'
    root.mkdir(mode=0o700)
    key = os.urandom(32)
    store = SyntheticAuthenticatedConfirmation(root / 'proof.sqlite', key, 'test-domain')
    store.initialize()
    operation = {'id': str(uuid4()), 'type': 'document_erasure', 'target': str(uuid4()),
                 'receipt_sha256': hashlib.sha256(b'synthetic receipt').hexdigest()}
    return store, operation, key


def test_authenticated_transitions_are_sequential_and_idempotent(experiment):
    store, operation, _ = experiment
    with pytest.raises(ValueError, match='Previous'):
        store.confirm(operation)
    assert store.prepare(operation) == 'prepared'
    assert store.prepare(operation) == 'prepared'
    assert store.confirm(operation) == 'confirmed'
    assert store.reconcile(operation) == 'confirmed'
    assert store.authorize(operation) == 'authorized'
    assert store.record_result(operation) == 'result_recorded'
    assert store.close(operation) == 'closed'
    assert store.confirm(operation) == 'closed'
    with pytest.raises(ValueError, match='Conflicting'):
        store.verify({**operation, 'target': str(uuid4())})


def test_lost_reply_is_resolved_by_verification(experiment, monkeypatch):
    store, operation, _ = experiment
    store.prepare(operation)
    original = store.verify
    monkeypatch.setattr(store, 'verify', lambda _: (_ for _ in ()).throw(OSError('lost reply')))
    with pytest.raises(OSError):
        store.confirm(operation)
    monkeypatch.setattr(store, 'verify', original)
    assert store.reconcile(operation) == 'confirmed'
    assert store.confirm(operation) == 'confirmed'


def test_tampering_and_wrong_key_fail_closed(experiment):
    store, operation, _ = experiment
    store.prepare(operation)
    store.confirm(operation)
    wrong = SyntheticAuthenticatedConfirmation(store.store.path, os.urandom(32), 'test-domain')
    with pytest.raises(ValueError, match='authentication'):
        wrong.verify(operation)
    with store.store.connection() as db:
        db.execute("UPDATE synthetic_transitions SET tag=? WHERE sequence=1", ('0' * 64,))
    with pytest.raises(ValueError, match='authentication'):
        store.verify(operation)
    with pytest.raises(ValueError):
        store.authorize(operation)


def test_missing_transition_and_wrong_domain_fail_closed(experiment):
    store, operation, key = experiment
    store.prepare(operation)
    store.confirm(operation)
    wrong_domain = SyntheticAuthenticatedConfirmation(store.store.path, key, 'other-domain')
    with pytest.raises(ValueError):
        wrong_domain.verify(operation)
    with store.store.connection() as db:
        db.execute('DELETE FROM synthetic_transitions WHERE sequence=1')
    with pytest.raises(ValueError):
        store.verify(operation)


def test_coherent_history_truncation_requires_external_freshness(experiment):
    store, operation, _ = experiment
    store.prepare(operation)
    store.confirm(operation)
    with store.store.connection() as db:
        db.execute('DELETE FROM synthetic_transitions WHERE sequence=2')
    # A self-consistent older prefix is indistinguishable without an external anchor.
    assert store.verify(operation) == 'prepared'
