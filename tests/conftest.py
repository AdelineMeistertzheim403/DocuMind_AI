import os
from uuid import UUID

import pytest
from pydantic import SecretStr
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.config import Settings
from backend.main import create_app
from backend.db import make_engine

KEY = "test-owner-one-key-000000000000000001"
OTHER_KEY = "test-owner-two-key-000000000000000002"
BFF_KEY = "test-bff-service-key-not-a-real-secret-0001"


@pytest.fixture(autouse=True)
def prohibit_real_openai_clients(monkeypatch):
    import openai
    def prohibited(*args,**kwargs):
        raise AssertionError('Real OpenAI clients are forbidden in automated tests')
    monkeypatch.setattr(openai,'OpenAI',prohibited)
    monkeypatch.setattr(openai,'AsyncOpenAI',prohibited)


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Set TEST_DATABASE_URL to a dedicated, disposable PostgreSQL database to test the same API there.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    probe = make_engine(url)
    try:
        if set(inspect(probe).get_table_names()) - {"alembic_version"}:
            pytest.fail("TEST_DATABASE_URL doit désigner une base vide dédiée aux tests")
    finally:
        probe.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    settings = Settings(_env_file=None, database_url=url, storage_dir=tmp_path / "private",
                        api_keys={KEY: UUID(int=1), OTHER_KEY: UUID(int=2)}, bff_service_key=SecretStr(BFF_KEY), requests_per_minute=10000,
                        extraction_mode='development')  # Explicitly unconfined portable regression suite.
    application = create_app(settings)
    yield application
    application.state.authentication_engine.dispose()
    application.state.engine.dispose()
    command.downgrade(config, "base")


@pytest.fixture
def client(app):
    with TestClient(app) as connection:
        connection.headers["X-API-Key"] = KEY
        yield connection


@pytest.fixture
def gateway_client(client):
    # Gateway identity is independent of both legacy owners and personal sessions.
    client.headers['X-API-Key'] = BFF_KEY
    return client
