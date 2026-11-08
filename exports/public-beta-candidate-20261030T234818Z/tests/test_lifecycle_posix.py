"""Additional phase 15.2 proofs on private native filesystems / real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from backend.account_models import PublicRegistrationQuota
from backend.lifecycle_registry import Registry


@pytest.fixture
def private_registry(tmp_path):
    directory=tmp_path/'ledger';directory.mkdir(mode=0o700)
    registry=Registry(directory/'cases.sqlite');registry.initialize()
    return registry


@pytest.mark.skipif(os.name!='posix',reason='Native POSIX permission/symlink proof')
@pytest.mark.parametrize('fault',['directory_permissions','file_permissions','file_symlink','file_hardlink'])
@pytest.mark.posix
def test_registry_rejects_unsafe_filesystem_state(private_registry,tmp_path,fault):
    registry=private_registry
    original=registry.path.read_bytes()
    if fault=='directory_permissions':
        os.chmod(registry.path.parent,0o755)
    elif fault=='file_permissions':
        os.chmod(registry.path,0o644)
    elif fault=='file_symlink':
        alias=registry.path.parent/'alias.sqlite';alias.symlink_to(registry.path)
        registry=Registry(alias)
    else:
        alias=registry.path.parent/'alias.sqlite';os.link(registry.path,alias)
        registry=Registry(alias)
    try:
        with pytest.raises(ValueError):registry.receive('access')
        assert private_registry.path.read_bytes()==original
    finally:
        os.chmod(private_registry.path.parent,0o700)
        os.chmod(private_registry.path,0o600)


def test_independent_sqlite_connections_serialize_duplicate_receipts(private_registry):
    user,owner=uuid4(),uuid4()
    def receive(_):
        return Registry(private_registry.path).receive('erasure',user_id=user,owner_id=owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts=list(pool.map(receive,range(2)))
    assert receipts[0]==receipts[1]
    with private_registry.connection() as connection:
        assert connection.execute('SELECT count(*) FROM requests').fetchone()[0]==1


def test_inventory_postgresql_transaction_rejects_writes(app,monkeypatch):
    from tools import pending_lifecycle
    if app.state.engine.dialect.name!='postgresql':
        pytest.skip('Requires the disposable PostgreSQL recipe')
    with app.state.sessions() as session:
        before=session.get(PublicRegistrationQuota,'public').issued_count
    def attempt_write(session,hours):
        session.execute(update(PublicRegistrationQuota).values(issued_count=99))
        return {}
    monkeypatch.setattr(pending_lifecycle,'plan_pending_cleanup',attempt_write)
    with pytest.raises(DBAPIError):pending_lifecycle.run(app.state.settings,168)
    with app.state.sessions() as session:
        assert session.scalar(select(PublicRegistrationQuota.issued_count))==before
