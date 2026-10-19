"""Upgrade/downgrade must retain historical owners and old password hashes."""
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from backend.db import make_engine


def test_historical_account_backfill_and_rollback_preserve_data(tmp_path,monkeypatch):
    url=f'sqlite:///{(tmp_path/"migration.db").as_posix()}'
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config('alembic.ini');command.upgrade(config,'0005')
    engine=make_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users(id,owner_id,username,password_hash,ai_limit_usd,created_at) VALUES (:id,:owner,'historical','original-scrypt',4,CURRENT_TIMESTAMP)"),{'id':'1'*32,'owner':'2'*32})
        before=tuple(connection.execute(text('SELECT * FROM users')).first())
    command.upgrade(config,'head')
    with engine.connect() as connection:
        assert tuple(connection.execute(text('SELECT id,owner_id,username,password_hash,ai_limit_usd,created_at FROM users')).first())==before
        assert connection.execute(text('SELECT owner_id FROM workspaces')).scalar_one()=='2'*32
        assert connection.execute(text('SELECT user_id FROM workspace_memberships')).scalar_one()=='1'*32
    command.downgrade(config,'0005')
    with engine.connect() as connection:
        assert tuple(connection.execute(text('SELECT * FROM users')).first())==before
    engine.dispose()
