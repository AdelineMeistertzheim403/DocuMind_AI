"""Disposable ledger failure cases; no production paths or data."""
import sqlite3
from uuid import uuid4

import pytest

from backend.lifecycle_durability import DurableCoordinator
from tests.test_lifecycle_durability import ledgers


@pytest.mark.parametrize('which', ['registry', 'confirmation'])
@pytest.mark.posix
def test_corrupt_store_blocks_recovery(ledgers, which):
    registry, store = ledgers
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    coordinator = DurableCoordinator(registry, store)
    coordinator.confirm_account(receipt)
    path = registry.path if which == 'registry' else store.path
    path.write_bytes(b'corrupt synthetic sqlite')
    with pytest.raises(sqlite3.DatabaseError):
        coordinator.verify_recovery_receipts()


@pytest.mark.posix
def test_simultaneous_store_loss_blocks_recovery(ledgers):
    registry, store = ledgers
    registry.path.unlink()
    store.path.unlink()
    with pytest.raises(FileNotFoundError):
        DurableCoordinator(registry, store)
