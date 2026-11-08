"""Opt-in component integrations only; never a complete backup qualification.

Existing and newly created databases are never dropped by this suite.
"""
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tools.restore_pgvector import (
    filtered_restore_list, preparation_url, prepare_extension, restore_environment, lab_connect_args,
)
from tools.validate_restore import (
    LAB_ENV, LAB_MARKER, LAB_MARKER_CONTENT, _isolated_url, seal_restored_registration,
)


@pytest.fixture
def postgres_lab():
    if os.environ.get("DOCUMIND_HARDENING_POSTGRES_LAB") != "isolated":
        pytest.skip("Requires explicit authorized synthetic PostgreSQL lab; no connection attempted")
    if os.environ.get(LAB_ENV) != "isolated":
        pytest.fail("Explicit restore lab mode required")
    root_raw = os.environ.get("DOCUMIND_HARDENING_EVIDENCE_ROOT")
    if not root_raw:
        pytest.fail("Explicit private synthetic evidence root required")
    root = Path(root_raw)
    if (not root.is_absolute() or root.resolve() != root or not root.is_dir()
            or (root / LAB_MARKER).is_symlink()
            or (root / LAB_MARKER).read_bytes() != LAB_MARKER_CONTENT):
        pytest.fail("Canonical marked synthetic evidence root required")
    if os.name == "posix" and (root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077):
        pytest.fail("Private restorer-owned evidence root required")
    url = _isolated_url()
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args=lab_connect_args(url))
    with admin.connect() as connection:
        assert connection.scalar(text("SELECT current_setting('cluster_name')")) == "documind-restore-lab"
        version = connection.scalar(text("SELECT current_setting('server_version_num')"))
        assert 170000 <= int(version) < 180000
        role = connection.execute(text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        )).one()
        assert tuple(role) == (False, True, False, False, False)

    def new_database():
        name = "documind_restore_" + uuid4().hex[:12]
        directory = root / name
        directory.mkdir(mode=0o700)
        (directory / "INCOMPLETE.txt").write_text(
            "Synthetic component integration only; no API attachment or reuse authorized.\n")
        with admin.connect() as connection:
            assert not connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name})
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        return name, directory

    try:
        yield url, new_database
    finally:
        admin.dispose()


@pytest.mark.parametrize("closed", [False, True])
def test_postgres_committed_quota_closure_without_changing_count(postgres_lab, closed):
    url, new_database = postgres_lab
    name, _ = new_database()
    engine = create_engine(url.set(database=name), connect_args=lab_connect_args(url))
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE public.public_registration_quota "
                "(id text PRIMARY KEY, issued_count integer NOT NULL, closed boolean NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO public.public_registration_quota VALUES ('public', 7, :closed)"
            ), {"closed": closed})
        assert seal_restored_registration(engine) == {"issued_count": 7, "closed": True}
        with engine.connect() as connection:
            assert tuple(connection.execute(text(
                "SELECT issued_count, closed FROM public.public_registration_quota"
            )).one()) == (7, True)
    finally:
        engine.dispose()


def test_actual_pgvector_dump_with_non_superuser_restore(postgres_lab):
    url, new_database = postgres_lab
    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    assert pg_dump and pg_restore, "Explicit local PostgreSQL tools required"
    privileged = preparation_url(url, "0.8.0")
    source, source_directory = new_database()
    destination, destination_directory = new_database()
    prepare_extension(privileged, source, url.username, "0.8.0")
    prepare_extension(privileged, destination, url.username, "0.8.0")
    engine = create_engine(url.set(database=source), connect_args=lab_connect_args(url))
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE public.samples (id integer PRIMARY KEY, embedding public.vector(3))"))
            connection.execute(text("INSERT INTO public.samples VALUES (1, '[1,2,3]')"))
            connection.execute(text(
                "CREATE TABLE public.public_registration_quota "
                "(id text PRIMARY KEY, issued_count integer NOT NULL, closed boolean NOT NULL)"
            ))
            connection.execute(text("INSERT INTO public.public_registration_quota VALUES ('public', 7, false)"))
    finally:
        engine.dispose()
    dump = source_directory / "synthetic.dump"
    connection_args = ["--host", url.host, "--port", str(url.port), "--username", url.username]
    subprocess.run([pg_dump, *connection_args, "--dbname", source, "--format=custom", "--file", str(dump)],
                   env=restore_environment(url), capture_output=True, check=True, timeout=60)
    filtered = filtered_restore_list(pg_restore, dump, destination_directory)
    assert filtered is not None
    destination_engine = create_engine(url.set(database=destination), connect_args=lab_connect_args(url))
    try:
        try:
            subprocess.run([pg_restore, *connection_args, "--dbname", destination,
                            "--no-owner", "--exit-on-error", "--use-list", str(filtered), str(dump)],
                           env=restore_environment(url), capture_output=True, check=True, timeout=60)
            with destination_engine.connect() as connection:
                assert tuple(connection.execute(text("SELECT id, embedding::text FROM public.samples")).one()) == (1, "[1,2,3]")
                assert tuple(connection.execute(text(
                    "SELECT issued_count, closed FROM public.public_registration_quota"
                )).one()) == (7, False)
        finally:
            assert seal_restored_registration(destination_engine) == {"issued_count": 7, "closed": True}
    finally:
        destination_engine.dispose()
