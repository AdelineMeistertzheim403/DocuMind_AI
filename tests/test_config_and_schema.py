from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from backend.config import Settings
from backend.main import create_app


def test_migration_matches_models(app):
    command.check(Config("alembic.ini"))


def test_no_keys_rejects_startup(tmp_path):
    app = create_app(Settings(_env_file=None, api_keys={}, database_url="sqlite://", storage_dir=tmp_path))
    with pytest.raises(RuntimeError, match="API_KEYS"):
        with TestClient(app):
            pass
    app.state.engine.dispose()


def test_configuration_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_bytes=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_keys={"short": "00000000-0000-0000-0000-000000000001"})


def test_schema_documents_auth_and_types(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    paths = schema["paths"]
    assert paths["/api/v1/documents"]["post"]["security"] == [{"APIKeyHeader": []}]
    assert "security" not in paths["/api/v1/health"]["get"]
    assert "AnalysisResult" in schema["components"]["schemas"]
