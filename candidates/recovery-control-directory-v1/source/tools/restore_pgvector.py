"""Strict pgvector TOC filtering and explicit preparation of a new lab database."""
import os
import re
import subprocess

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def validate_lab_url(url):
    if (url.drivername != "postgresql+psycopg"
            or url.host not in {"127.0.0.1", "::1"}
            or url.port is None or not 1 <= url.port <= 65535
            or not url.username or url.database != "documind_restore_admin"
            or url.query):
        raise ValueError("Explicit loopback restore admin URL without connection overrides required")
    return url


def restore_environment(url):
    # PGHOSTADDR/PGSERVICE/PGOPTIONS must not redirect or alter an explicit lab connection.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PG")}
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    env["PGPASSFILE"] = os.devnull
    env["PGSSLMODE"] = "disable"
    env["PGGSSENCMODE"] = "disable"
    return env


def lab_connect_args(url):
    validate_lab_url(url.set(database="documind_restore_admin"))
    if any(os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")):
        raise ValueError("Ambient PostgreSQL connection overrides are forbidden in the restore lab")
    if url.password is None and os.environ.get("PGPASSWORD"):
        raise ValueError("Implicit ambient PostgreSQL password is forbidden")
    return {
        "hostaddr": url.host, "passfile": os.devnull, "connect_timeout": 10,
        "sslmode": "disable", "gssencmode": "disable",
        "options": "-c statement_timeout=60000 -c lock_timeout=10000",
    }


def filtered_restore_list(pg_restore, dump, directory):
    result = subprocess.run(
        [pg_restore, "--list", str(dump)], capture_output=True, text=True,
        check=True, timeout=60, env=restore_environment(make_url("postgresql://")),
    )
    lines = result.stdout.splitlines()
    selected = {}
    identifiers = set()
    for line in lines:
        if not line.strip() or line.startswith(";"):
            continue
        match = re.fullmatch(r"(\d+);\s+\d+\s+\d+\s+(.+?)\s*", line)
        if match is None or match[1] in identifiers:
            raise ValueError("Invalid or duplicate dump TOC entry")
        identifiers.add(match[1])
        descriptor = match[2]
        if descriptor.startswith("EXTENSION ") or descriptor.startswith("COMMENT - EXTENSION "):
            if descriptor not in {"EXTENSION - vector", "COMMENT - EXTENSION vector"}:
                raise ValueError("Only the two expected pgvector extension entries are supported")
            if descriptor in selected:
                raise ValueError("Duplicate pgvector extension entry")
            selected[descriptor] = line
    if not identifiers:
        raise ValueError("Empty dump TOC")
    if not selected:
        return None
    if set(selected) != {"EXTENSION - vector", "COMMENT - EXTENSION vector"}:
        raise ValueError("Both pgvector TOC entries are required")

    selected_path = directory / "pgvector-selected.list"
    with selected_path.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(selected.values()) + "\n")
    sql = subprocess.run(
        [pg_restore, "--schema-only", "--use-list", str(selected_path),
         "--file=-", str(dump)],
        capture_output=True, text=True, check=True, timeout=60,
        env=restore_environment(make_url("postgresql://")),
    ).stdout
    _validate_extension_sql(sql)
    filtered = directory / "restore.list"
    with filtered.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(line for line in lines if line not in selected.values()) + "\n")
    if os.name == "posix":
        selected_path.chmod(0o600)
        filtered.chmod(0o600)
    return filtered


def _validate_extension_sql(sql):
    statements = "\n".join(
        line for line in sql.splitlines()
        if not line.lstrip().startswith("--")
        and not re.fullmatch(r"\\(?:un)?restrict [A-Za-z0-9]+", line)
    )
    statements = re.sub(
        r"(?m)^SET (?:statement_timeout|lock_timeout|idle_in_transaction_session_timeout|"
        r"transaction_timeout|client_encoding|standard_conforming_strings|check_function_bodies|"
        r"xmloption|client_min_messages|row_security) = (?:0|'UTF8'|on|off|false|content|warning);$",
        "", statements,
    )
    statements = statements.replace("SELECT pg_catalog.set_config('search_path', '', false);", "")
    expected = (
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;",
        "COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';",
    )
    if " ".join(statements.split()) != " ".join(expected):
        raise ValueError("Unexpected pgvector definition/comment in dump")


def preparation_url(restore_url, version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        raise ValueError("Explicit pgvector version required")
    raw = os.environ.get("DOCUMIND_RESTORE_PREPARE_DATABASE_URL")
    if not raw:
        raise ValueError("Explicit privileged preparation URL required")
    url = validate_lab_url(make_url(raw))
    if (url.host, url.port) != (restore_url.host, restore_url.port) or url.username == restore_url.username:
        raise ValueError("Preparation must use a distinct role on the same isolated endpoint")
    return url


def prepare_extension(url, database, restore_user, version):
    if os.environ.get("DOCUMIND_RESTORE_LAB") != "isolated":
        raise ValueError("Explicit isolated restore lab mode required for preparation")
    validate_lab_url(url)
    if (not re.fullmatch(r"documind_restore_[a-f0-9]{12}", database)
            or not re.fullmatch(r"\d+\.\d+\.\d+", version or "")):
        raise ValueError("Invalid preparation target")
    engine = create_engine(url.set(database=database), connect_args=lab_connect_args(url))
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT current_setting('cluster_name')")) != "documind-restore-lab":
                raise ValueError("Isolated cluster required for preparation")
            if connection.scalar(text("SELECT current_database()")) != database:
                raise ValueError("Unexpected preparation database")
            owner = connection.scalar(text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"
            ))
            if owner != restore_user:
                raise ValueError("Preparation target must belong to the restore role")
            if connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema')"
            )) or connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname<>'plpgsql')")):
                raise ValueError("Preparation requires a fresh empty database")
            # No CASCADE, role grants or installation of server packages.
            connection.execute(text(f"CREATE EXTENSION vector WITH SCHEMA public VERSION '{version}'"))
            installed = connection.execute(text(
                "SELECT extversion, extnamespace::regnamespace::text FROM pg_extension WHERE extname='vector'"
            )).one()
            if tuple(installed) != (version, "public"):
                raise ValueError("Unexpected installed pgvector version/schema")
    finally:
        engine.dispose()
