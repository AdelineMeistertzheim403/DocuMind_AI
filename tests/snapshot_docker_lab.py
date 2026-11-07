"""Synthetic native Docker fixtures; no production Compose or default database fallback."""
from contextlib import contextmanager
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tools.backup_local import create_backup, _offline_api_compose


DOCUMENT = b"Only synthetic snapshot qualification data.\n"
STORAGE_NAME = "a" * 32 + ".txt"


def seed_volume_data():
    import json
    import os
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from uuid import UUID, uuid4
    from backend.lifecycle_registry import Registry
    from backend.lifecycle_durability import ConfirmationStore
    from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
    from backend.lifecycle_holds import HoldStore
    from backend.lifecycle_admissions import AdmissionAnchor
    from backend.lifecycle_snapshot import configured_store_paths
    from ops.testing.lifecycle_lot29_bundle import DOMAIN, SyntheticLifecycleConsistencyVerifier

    assert os.environ["DOCUMIND_SNAPSHOT_LAB"] == "isolated"
    root = Path("/app/lifecycle")
    assert not list(root.iterdir()), "Never overwrite a lifecycle volume"
    variables = {
        "registry": "LIFECYCLE_REGISTRY_PATH", "witness": "LIFECYCLE_CONFIRMATION_PATH",
        "authenticated": "LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH",
        "holds": "LIFECYCLE_HOLDS_PATH", "admission_anchor": "LIFECYCLE_ADMISSION_ANCHOR_PATH",
    }
    paths = {name: Path(os.environ[variable]) for name, variable in variables.items()}
    for path in paths.values():
        path.parent.mkdir(mode=0o700)
    registry = Registry(paths["registry"])
    registry.initialize()
    witness = ConfirmationStore(paths["witness"])
    witness.initialize()
    auth_key, admission_key = os.urandom(32), os.urandom(32)
    auth = AuthenticatedConfirmationStore(paths["authenticated"], auth_key, DOMAIN)
    auth.initialize()
    holds = HoldStore(paths["holds"], auth)
    holds.initialize()
    anchor = AdmissionAnchor(paths["admission_anchor"], admission_key)
    anchor.initialize()
    for count in range(1, 5):
        before = witness.admission_entries()
        user = str(UUID(int=count))
        witness.reserve_admission(count, user)
        after = witness.admission_entries()
        anchor.reserve(before, after)
        anchor.settle(after, user)
    registry.observe_admissions(4)
    now = datetime.now(timezone.utc)
    holds.create({
        "id": str(uuid4()), "responsible_id": str(uuid4()), "scope_id": str(UUID(int=1)),
        "scope_kind": "account", "reason": "legal_hold",
        "reviewed_at": now - timedelta(seconds=1), "review_at": now + timedelta(days=29),
        "ends_at": None, "end_event": "legal_hold_lifted",
    }, now)
    assert set(configured_store_paths()) == set(paths)
    consistency = SyntheticLifecycleConsistencyVerifier(auth_key, admission_key).verify(paths)
    documents = Path("/app/var/documents")
    assert not documents.exists(), "Never overwrite a documents volume"
    documents.mkdir(mode=0o700)
    document = documents / ("a" * 32 + ".txt")
    document.write_bytes(b"Only synthetic snapshot qualification data.\n")
    document.chmod(0o600)
    print(json.dumps({"auth_key": auth_key.hex(), "admission_key": admission_key.hex(),
                      "consistency": consistency}))


class SnapshotLab:
    def __init__(self, compose, url, seed):
        self.compose, self.url, self.seed = compose, url, seed

    @contextmanager
    def connection(self, database=None):
        engine = create_engine(self.url.set(database=database or self.url.database),
                               poolclass=NullPool, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as connection:
                yield connection
        finally:
            engine.dispose()

    def exists(self, name):
        with self.connection("postgres") as db:
            return bool(db.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"),
                                  {"name": name}))

    def drop(self, name):
        assert re.fullmatch(r"(?:documind_restore_|snapshot_legacy_)[a-f0-9]{12}", name)
        if self.exists(name):
            with self.connection("postgres") as db:
                db.execute(text(f'DROP DATABASE "{name}"'))
        assert not self.exists(name)

    def quota(self, *, closed=None, issued_count=None):
        with self.connection() as db:
            if closed is not None:
                db.execute(text("UPDATE public_registration_quota SET closed=:closed"),
                           {"closed": closed})
            if issued_count is not None:
                db.execute(text("UPDATE public_registration_quota SET issued_count=:count"),
                           {"count": issued_count})
            return dict(db.execute(text(
                "SELECT issued_count,closed FROM public_registration_quota WHERE id='public'"
            )).one()._mapping)

    def database_state(self, database=None):
        with self.connection(database) as db:
            tables = db.scalars(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )).all()
            rows = {}
            for table in tables:
                assert re.fullmatch(r"[a-z_0-9]+", table)
                rows[table] = db.scalars(text(
                    f"SELECT row_to_json(t)::text FROM {table} t ORDER BY row_to_json(t)::text"
                )).all()
        return rows

    def state(self):
        rows = self.database_state()
        script = (
            "import json,hashlib,os; from pathlib import Path; "
            "paths=[Path(os.environ[k]) for k in os.environ if k.startswith('LIFECYCLE_') "
            "and k.endswith('_PATH') and k!='LIFECYCLE_BACKUP_LOCK_PATH']; "
            "paths+=list(Path('/app/var/documents').iterdir()); "
            "print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))"
        )
        with _offline_api_compose(self.compose, None) as offline:
            files = json.loads(subprocess.check_output(
                offline + ["run", "--rm", "--no-deps", "-T", "--entrypoint", "python",
                           "api", "-c", script], text=True))
        return {"rows": rows, "files": files}

    def capture(self, destination):
        with self.connection() as db:
            assert db.scalar(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND backend_type='client backend' AND pid<>pg_backend_pid()"
            )) == 0
        return create_backup(self.compose, destination)

    def restore_command(self, snapshot, root, name):
        env = os.environ.copy()
        env["DOCUMIND_RESTORE_LAB"] = "isolated"
        env["DOCUMIND_RESTORE_DATABASE_URL"] = self.url.set(
            database="documind_restore_admin").render_as_string(hide_password=False)
        return subprocess.run(
            [sys.executable, "tools/validate_restore.py", str(snapshot), "--database", name,
             "--restore-root", str(root)], env=env, text=True, capture_output=True, timeout=60)

    @contextmanager
    def restored(self, snapshot, root):
        root.mkdir(mode=0o700)
        (root / ".synthetic-only").write_bytes(b"documind-isolated-restore-lab-v1\n")
        name = "documind_restore_" + uuid4().hex[:12]
        assert not self.exists(name)
        try:
            result = self.restore_command(snapshot, root, name)
            assert result.returncode == 0, result.stdout + result.stderr
            report = json.loads(result.stdout.splitlines()[-1])
            yield SimpleNamespace(name=name, root=root / name, report=report)
        finally:
            self.drop(name)


@pytest.fixture(scope="session")
def docker_snapshot_lab(tmp_path_factory):
    if os.environ.get("DOCUMIND_SNAPSHOT_LAB") != "isolated":
        pytest.skip("Requires ops/testing/run_snapshot_lab.py and its new synthetic Linux project")
    assert sys.platform == "linux"
    project = os.environ["SNAPSHOT_LAB_PROJECT"]
    assert re.fullmatch(r"documind-snapshot-[a-f0-9]{12}", project)
    assert all(re.fullmatch(r"sha256:[a-f0-9]{64}", os.environ[key])
               for key in ("SNAPSHOT_LAB_API_IMAGE", "SNAPSHOT_LAB_DB_IMAGE"))
    root = tmp_path_factory.mktemp("snapshot-control")
    env_file = root / "empty.env"
    env_file.write_text("", encoding="utf-8")
    compose = ["docker", "compose", "-p", project, "--env-file", str(env_file),
               "-f", str(Path("ops/testing/compose.snapshot-lab.yaml").resolve())]
    config = json.loads(subprocess.check_output(
        compose + ["config", "--format", "json"], text=True))
    assert config["name"] == project and config["networks"]["data"]["internal"]
    assert not any(service.get("ports") or service.get("env_file")
                   for service in config["services"].values())
    ids = subprocess.check_output(compose + ["ps", "-q", "db"], text=True).split()
    assert len(ids) == 1
    container = json.loads(subprocess.check_output(["docker", "inspect", ids[0]], text=True))[0]
    assert container["Config"]["Labels"]["documind.snapshot-lab"] == project
    assert not container["HostConfig"]["PortBindings"]
    from sqlalchemy.engine import URL
    url = URL.create("postgresql+psycopg", username="documind_snapshot",
                     password="fictitious-snapshot-lab-only", host="127.0.0.1",
                     port=5432, database="snapshot_source")
    lab = SnapshotLab(compose, url, None)
    with lab.connection("postgres") as db:
        assert db.scalar(text("SELECT current_setting('cluster_name')")) == "documind-restore-lab"
        assert set(db.scalars(text(
            "SELECT datname FROM pg_database WHERE NOT datistemplate"
        ))) == {"postgres", "snapshot_source"}
        db.execute(text("CREATE DATABASE documind_restore_admin"))
    with lab.connection() as db:
        assert db.scalar(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
        )) == 0, "Never migrate an existing source database"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        command.upgrade(Config("alembic.ini"), "head")
    from backend.auth import User, hash_password
    from backend.models import Document, DocumentPage, Analysis, now
    from sqlalchemy.orm import Session
    engine = create_engine(url, poolclass=NullPool)
    try:
        with Session(engine) as db:
            password = hash_password("Only-fictitious-snapshot-password-2026!")
            for number in range(1, 5):
                db.add(User(id=UUID(int=number), owner_id=UUID(int=100 + number),
                            username=f"snapshot-{number}", email=f"snapshot-{number}@example.test",
                            password_hash=password, registration_kind="public",
                            email_verified_at=now(), approved_at=now()))
            document = Document(id=UUID(int=1000), owner_id=UUID(int=101),
                                filename="synthetic.txt", storage_name=STORAGE_NAME,
                                media_type="text/plain", size_bytes=len(DOCUMENT),
                                sha256=hashlib.sha256(DOCUMENT).hexdigest())
            document.pages.append(DocumentPage(page_number=1, text=DOCUMENT.decode()))
            document.analyses.append(Analysis(parameters={"synthetic": True},
                                             result={"qualification": "snapshot"}))
            db.add(document)
            db.execute(text(
                "UPDATE public_registration_quota SET issued_count=4,closed=false WHERE id='public'"
            ))
            db.commit()
    finally:
        engine.dispose()
    with _offline_api_compose(compose, None) as offline:
        subprocess.run(offline + ["run", "--rm", "--no-deps", "-T", "--user", "0:0",
            "--cap-add", "CHOWN", "--entrypoint", "python", "api", "-c",
            "import os; from pathlib import Path; "
            "roots=[Path('/app/var'),Path('/app/lifecycle')]; "
            "assert all(not list(p.iterdir()) for p in roots); "
            "[(p.chmod(0o700),os.chown(p,1000,1000)) for p in roots]"],
            check=True, timeout=30)
        lab.seed = json.loads(subprocess.check_output(
            offline + ["run", "--rm", "--no-deps", "-T", "--entrypoint", "python", "api",
                       "-c", inspect.getsource(seed_volume_data) + "\nseed_volume_data()"], text=True))
    with lab.connection() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0008"
    yield lab
    with lab.connection("postgres") as db:
        databases = set(db.scalars(text(
            "SELECT datname FROM pg_database WHERE NOT datistemplate"
        )))
        assert databases == {"postgres", "documind_restore_admin", "snapshot_source"}


@pytest.fixture
def snapshot_lab(docker_snapshot_lab):
    lab = docker_snapshot_lab
    before = lab.state()
    try:
        yield lab
    finally:
        assert lab.state() == before, "Snapshot proof mutated the source"
