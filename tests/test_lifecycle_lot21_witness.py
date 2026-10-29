import os
from uuid import uuid4

import pytest

from ops.testing.lifecycle_lot21_witness import inspect_witness, synthetic_anchor


def test_external_anchor_detects_truncation_and_conflict():
    key = os.urandom(32)
    entries = [{'sequence': i, 'user_id': str(uuid4())} for i in (1, 2, 3)]
    anchor = synthetic_anchor(entries, key)
    result = inspect_witness(entries, anchor, key, 2)
    assert result['minimum_issued_count'] == 3
    assert result['state'] == 'reconciliation_required'
    assert result['keep_registration_closed'] and not result['opening_authorized']
    with pytest.raises(ValueError, match='anchor'):
        inspect_witness(entries[:2], anchor, key, 2)
    with pytest.raises(ValueError, match='anchor'):
        inspect_witness([*entries[:2], {**entries[2], 'user_id': str(uuid4())}], anchor, key, 3)
    with pytest.raises(ValueError, match='anchor'):
        inspect_witness(entries, anchor, os.urandom(32), 3)
    with pytest.raises(ValueError, match='older than database'):
        inspect_witness(entries, anchor, key, 4)


def test_both_sources_rolled_back_cannot_prove_freshness():
    key = os.urandom(32)
    entries = [{'sequence': i, 'user_id': str(uuid4())} for i in (1, 2, 3)]
    old_entries = entries[:2]
    old_anchor = synthetic_anchor(old_entries, key)
    result = inspect_witness(old_entries, old_anchor, key, 2)
    assert result['state'] == 'observed_consistent'
    assert result['keep_registration_closed'] and not result['opening_authorized']
