"""Synthetic replacement at the SQLite check/open boundary."""
import os

import pytest

from backend.lifecycle_registry import Registry
from backend.lifecycle_durability import ConfirmationStore


@pytest.mark.skipif(os.name != 'posix', reason='POSIX pathname race experiment')
@pytest.mark.parametrize('store_type', [Registry, ConfirmationStore])
@pytest.mark.posix
def test_registry_refuses_replacement_between_check_and_sqlite_open(tmp_path, monkeypatch, store_type):
    root = tmp_path / 'ledger'
    root.mkdir(mode=0o700)
    original = store_type(root / 'original.sqlite')
    replacement = store_type(root / 'replacement.sqlite')
    original.initialize()
    replacement.initialize()
    check = original._check

    replaced = False

    def replace_after_check(*args, **kwargs):
        nonlocal replaced
        info = check(*args, **kwargs)
        if not replaced:
            os.replace(replacement.path, original.path)
            replaced = True
        return info

    monkeypatch.setattr(original, '_check', replace_after_check)
    with pytest.raises(ValueError, match='changed while opening'):
        with original.connection():
            pytest.fail('A replaced database must not be used')
