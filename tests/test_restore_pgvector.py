from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import make_url

from tools import restore_pgvector as vector


TOC = "; synthetic TOC\n2; 3079 16400 EXTENSION - vector\n3; 0 0 COMMENT - EXTENSION vector\n4; 1259 16401 TABLE public samples synthetic\n"
SQL = """-- synthetic pg_restore output
SET statement_timeout = 0;
SET client_encoding = 'UTF8';
SELECT pg_catalog.set_config('search_path', '', false);
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';
"""


def test_only_exact_two_entries_are_removed(tmp_path, monkeypatch):
    run = Mock(side_effect=[SimpleNamespace(stdout=TOC), SimpleNamespace(stdout=SQL)])
    monkeypatch.setattr(vector.subprocess, "run", run)
    result = vector.filtered_restore_list("synthetic-pg_restore", tmp_path / "dump", tmp_path)
    assert result.read_text() == "; synthetic TOC\n4; 1259 16401 TABLE public samples synthetic\n"
    assert "--schema-only" in run.call_args.args[0]
    assert (tmp_path / "pgvector-selected.list").read_text().splitlines() == TOC.splitlines()[1:3]


@pytest.mark.parametrize("toc", [
    TOC.replace("3; 0 0 COMMENT - EXTENSION vector\n", ""),
    TOC + "5; 3079 16403 EXTENSION - hstore\n",
    TOC + "5; 3079 16403 EXTENSION - vector\n",
    TOC.replace("3; 0 0", "2; 0 0"),
    TOC.replace("EXTENSION - vector", "EXTENSION public vector"),
    "garbage\n",
    "; empty\n",
])
def test_invalid_or_unexpected_toc_refused_before_sql(tmp_path, monkeypatch, toc):
    run = Mock(return_value=SimpleNamespace(stdout=toc))
    monkeypatch.setattr(vector.subprocess, "run", run)
    with pytest.raises(ValueError):
        vector.filtered_restore_list("synthetic-pg_restore", tmp_path / "dump", tmp_path)
    assert run.call_count == 1
    assert not (tmp_path / "restore.list").exists()


@pytest.mark.parametrize("sql", [
    SQL + "\nDROP TABLE public.samples;\n",
    SQL.replace("WITH SCHEMA public", "WITH SCHEMA other"),
    SQL.replace("vector data type and ivfflat and hnsw access methods", "unexpected definition"),
    SQL.replace("CREATE EXTENSION IF NOT EXISTS vector", "CREATE EXTENSION IF NOT EXISTS hstore"),
    SQL + "\n\\connect production\n",
])
def test_extension_sql_is_not_trusted_from_descriptor_alone(tmp_path, monkeypatch, sql):
    monkeypatch.setattr(vector.subprocess, "run", Mock(
        side_effect=[SimpleNamespace(stdout=TOC), SimpleNamespace(stdout=sql)]))
    with pytest.raises(ValueError, match="Unexpected"):
        vector.filtered_restore_list("synthetic-pg_restore", tmp_path / "dump", tmp_path)
    assert not (tmp_path / "restore.list").exists()


def test_nonvector_dump_is_not_filtered(tmp_path, monkeypatch):
    monkeypatch.setattr(vector.subprocess, "run", Mock(
        return_value=SimpleNamespace(stdout=TOC.splitlines()[3])))
    assert vector.filtered_restore_list("synthetic-pg_restore", tmp_path / "dump", tmp_path) is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://lab@remote:5432/documind_restore_admin",
    "postgresql+psycopg://lab@127.0.0.1/documind_restore_admin",
    "postgresql+psycopg://lab@127.0.0.1:5432/postgres",
    "postgresql+psycopg://lab@127.0.0.1:5432/documind_restore_admin?hostaddr=remote",
    "postgresql://lab@127.0.0.1:5432/documind_restore_admin",
])
def test_connection_overrides_or_nonlab_endpoints_refused(url):
    with pytest.raises(ValueError):
        vector.validate_lab_url(make_url(url))


def test_pg_environment_cannot_redirect_connection(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "remote")
    monkeypatch.setenv("PGSERVICE", "production")
    monkeypatch.setenv("PGOPTIONS", "unsafe")
    monkeypatch.setenv("PGPASSWORD", "not-the-requested-password")
    url = make_url("postgresql+psycopg://lab:synthetic@127.0.0.1:5432/documind_restore_admin")
    env = vector.restore_environment(url)
    import os

    assert {key: value for key, value in env.items() if key.upper().startswith("PG")} == {
        "PGPASSWORD": "synthetic", "PGPASSFILE": os.devnull,
        "PGSSLMODE": "disable", "PGGSSENCMODE": "disable"}


@pytest.mark.parametrize("prepare,version", [
    (None, "0.8.0"),
    ("postgresql+psycopg://lab@127.0.0.1:5432/documind_restore_admin", "0.8.0"),
    ("postgresql+psycopg://admin@127.0.0.1:5433/documind_restore_admin", "0.8.0"),
    ("postgresql+psycopg://admin@127.0.0.1:5432/documind_restore_admin", "0.8.0'; DROP DATABASE x;"),
])
def test_privileged_preparation_requires_explicit_distinct_same_lab_role(monkeypatch, prepare, version):
    restore = make_url("postgresql+psycopg://lab@127.0.0.1:5432/documind_restore_admin")
    if prepare:
        monkeypatch.setenv("DOCUMIND_RESTORE_PREPARE_DATABASE_URL", prepare)
    else:
        monkeypatch.delenv("DOCUMIND_RESTORE_PREPARE_DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        vector.preparation_url(restore, version)


@pytest.mark.parametrize("failure", [None, "cluster", "database", "owner", "not_empty", "extension", "version"])
def test_preparation_is_minimal_and_rolls_back_failed_validation(monkeypatch, failure):
    from unittest.mock import MagicMock

    monkeypatch.setenv("DOCUMIND_RESTORE_LAB", "isolated")
    url = make_url("postgresql+psycopg://preparer@127.0.0.1:5432/documind_restore_admin")
    database = "documind_restore_012345abcdef"
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.side_effect = [
        "other" if failure == "cluster" else "documind-restore-lab",
        "other" if failure == "database" else database,
        "other" if failure == "owner" else "restorer",
        failure == "not_empty",
        failure == "extension",
    ]
    connection.execute.return_value.one.return_value = (
        "unexpected" if failure == "version" else "0.8.0", "public"
    )
    monkeypatch.setattr(vector, "create_engine", Mock(return_value=engine))
    if failure:
        with pytest.raises(ValueError):
            vector.prepare_extension(url, database, "restorer", "0.8.0")
    else:
        vector.prepare_extension(url, database, "restorer", "0.8.0")
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    creates = [sql for sql in statements if sql.startswith("CREATE")]
    assert creates == (["CREATE EXTENSION vector WITH SCHEMA public VERSION '0.8.0'"]
                       if failure in {None, "version"} else [])
    assert not any("GRANT" in sql or "ALTER ROLE" in sql or "CASCADE" in sql for sql in statements)
    assert engine.dispose.called


@pytest.mark.parametrize("name", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"])
def test_sql_connections_refuse_ambient_redirects(monkeypatch, name):
    monkeypatch.setenv(name, "synthetic-unsafe-override")
    with pytest.raises(ValueError, match="Ambient"):
        vector.lab_connect_args(make_url(
            "postgresql+psycopg://lab@127.0.0.1:5432/documind_restore_admin"))


def test_sql_does_not_consume_an_implicit_environment_password(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "synthetic-not-explicitly-authorized")
    with pytest.raises(ValueError, match="Implicit ambient"):
        vector.lab_connect_args(make_url(
            "postgresql+psycopg://lab@127.0.0.1:5432/documind_restore_admin"))
