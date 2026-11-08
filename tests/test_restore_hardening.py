import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.engine import make_url

from tools import validate_restore as restore


DATABASE = "documind_restore_012345abcdef"
URL = make_url("postgresql+psycopg://synthetic@127.0.0.1:55432/documind_restore_admin")


@pytest.fixture(autouse=True)
def synthetic_lab_mode(monkeypatch):
    monkeypatch.setenv(restore.LAB_ENV, "isolated")


def quota_engine(*, closed=False, missing=False, invalid=False, ineffective=False, commit_ineffective=False):
    engine = MagicMock()
    engine.url = URL.set(database=DATABASE)
    connection = engine.begin.return_value.__enter__.return_value
    committed = engine.connect.return_value.__enter__.return_value
    state = {"closed": closed}

    def execute(statement):
        sql = str(statement)
        result = Mock()
        if "current_database" in sql:
            result.scalar_one.return_value = DATABASE
        elif "to_regclass" in sql:
            result.scalar_one.return_value = None if missing else "public_registration_quota"
        elif sql.startswith("UPDATE"):
            if not ineffective:
                state["closed"] = True
        elif "SELECT id," in sql:
            result.all.return_value = [
                SimpleNamespace(id="public", issued_count=-1 if invalid else 7, closed=state["closed"])
            ]
        else:
            result.one.return_value = SimpleNamespace(issued_count=7, closed=state["closed"])
        return result

    connection.scalar.return_value = "documind-restore-lab"
    connection.execute.side_effect = execute
    if commit_ineffective:
        committed.execute.side_effect = lambda _: SimpleNamespace(
            one=lambda: SimpleNamespace(issued_count=7, closed=False))
    else:
        committed.execute.side_effect = execute
    return engine, state


@pytest.mark.parametrize("closed", [False, True])
def test_quota_is_closed_and_read_after_commit(closed):
    engine, state = quota_engine(closed=closed)
    assert restore.seal_restored_registration(engine) == {"issued_count": 7, "closed": True}
    assert state["closed"] is True
    assert engine.connect.called


@pytest.mark.parametrize("failure", ["missing", "invalid", "ineffective", "commit_ineffective"])
def test_quota_cannot_be_certified_without_effective_closure(failure):
    engine, _ = quota_engine(**{failure: True})
    with pytest.raises(ValueError):
        restore.seal_restored_registration(engine)


@pytest.mark.parametrize("guard", ["database", "cluster"])
def test_sealer_refuses_wrong_database_or_cluster(guard):
    engine, _ = quota_engine()
    connection = engine.begin.return_value.__enter__.return_value
    if guard == "cluster":
        connection.scalar.return_value = "not-a-lab"
    else:
        connection.execute.side_effect = None
        connection.execute.return_value.scalar_one.return_value = "production"
    with pytest.raises(ValueError):
        restore.seal_restored_registration(engine)
    assert not any(str(call.args[0]).startswith("UPDATE") for call in connection.execute.call_args_list)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    root = tmp_path.resolve() / "lab"
    root.mkdir(mode=0o700)
    (root / restore.LAB_MARKER).write_bytes(restore.LAB_MARKER_CONTENT)
    snapshot = tmp_path.resolve() / "synthetic-control-flow"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(json.dumps({"capture_id": "synthetic-control-flow-only"}))
    monkeypatch.setenv(restore.LAB_ENV, "isolated")
    monkeypatch.setattr(restore, "verify_capture", Mock())
    monkeypatch.setattr(restore.shutil, "which", lambda _: "synthetic-pg_restore")
    monkeypatch.setattr(restore, "filtered_restore_list", Mock(return_value=None))
    admin = MagicMock()
    connection = admin.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = lambda statement, *args: (
        "documind-restore-lab" if "cluster_name" in str(statement) else None
    )
    connection.execute.return_value.one.return_value = SimpleNamespace(
        rolsuper=False, rolcreatedb=True, rolcreaterole=False, rolreplication=False, rolbypassrls=False
    )
    engine, state = quota_engine()
    monkeypatch.setattr(restore, "create_engine", Mock(side_effect=[admin, engine]))
    order = []
    monkeypatch.setattr(restore.subprocess, "run", Mock(side_effect=lambda *a, **k: order.append("dump")))
    monkeypatch.setattr(restore, "verify_snapshot", Mock(side_effect=lambda *a, **k: order.append("fidelity")))
    original = restore.seal_restored_registration

    def seal(engine):
        order.append("seal")
        return original(engine)

    monkeypatch.setattr(restore, "seal_restored_registration", Mock(side_effect=seal))
    monkeypatch.setattr(restore, "_restore_contents", Mock(return_value={
        "status": "quarantined", "quota": {"issued_count": 7, "closed": True},
        "opening_authorized": False, "s2_recovery_authorized": False,
        "critical_mutations_allowed": False,
    }))
    return snapshot, root, connection, state, order


def test_restore_preserves_fidelity_then_closes_open_quota(flow):
    snapshot, root, _, state, order = flow
    result = restore._restore(snapshot, DATABASE, root, URL)
    assert order == ["dump", "fidelity", "seal"]
    assert state["closed"] is True
    assert result["opening_authorized"] is False and result["reusable"] is False
    assert result["validation_complete"] is True
    assert json.loads((root / DATABASE / "quarantine.json").read_text()) == result
    assert json.loads((root / DATABASE / "recovery-state.json").read_text())["state"] == "quarantined"


@pytest.mark.parametrize("stage", ["dump", "fidelity", "contents", "seal"])
def test_partial_restores_are_failed_and_never_reused(flow, monkeypatch, stage):
    snapshot, root, _, _, _ = flow
    replacement = Mock(side_effect=RuntimeError("synthetic failure, not a database error log"))
    if stage == "dump":
        monkeypatch.setattr(restore.subprocess, "run", replacement)
    else:
        monkeypatch.setattr(restore, {
            "fidelity": "verify_snapshot", "contents": "_restore_contents",
            "seal": "seal_restored_registration",
        }[stage], replacement)
    with pytest.raises(RuntimeError):
        restore._restore(snapshot, DATABASE, root, URL)
    report = json.loads((root / DATABASE / "quarantine.json").read_text())
    assert report["status"] == "failed"
    assert report["validation_complete"] is False and report["reusable"] is False
    assert report["opening_authorized"] is False
    assert "synthetic failure" not in json.dumps(report)
    with pytest.raises(ValueError, match="already exists"):
        restore._restore(snapshot, DATABASE, root, URL)


def test_existing_database_is_not_deleted_or_overwritten(flow):
    snapshot, root, connection, _, _ = flow
    connection.scalar.side_effect = ["documind-restore-lab", 1]
    with pytest.raises(ValueError, match="already exists"):
        restore._restore(snapshot, DATABASE, root, URL)
    assert not (root / DATABASE).exists()
    assert not any("CREATE DATABASE" in str(c.args[0]) or "DROP" in str(c.args[0])
                   for c in connection.execute.call_args_list)


@pytest.mark.parametrize("privilege", ["rolsuper", "rolcreaterole", "rolreplication", "rolbypassrls"])
def test_elevated_restore_role_refused_before_mutation(flow, privilege):
    snapshot, root, connection, _, _ = flow
    setattr(connection.execute.return_value.one.return_value, privilege, True)
    with pytest.raises(ValueError, match="no elevated"):
        restore._restore(snapshot, DATABASE, root, URL)
    assert not (root / DATABASE).exists()


def test_pgvector_needs_explicit_preparation_before_database_creation(flow, monkeypatch):
    snapshot, root, connection, _, _ = flow
    monkeypatch.setattr(restore, "filtered_restore_list", Mock(return_value=root / "synthetic.list"))
    with pytest.raises(ValueError, match="explicit preparation"):
        restore._restore(snapshot, DATABASE, root, URL)
    assert not any("CREATE DATABASE" in str(c.args[0]) for c in connection.execute.call_args_list)
    assert json.loads((root / DATABASE / "quarantine.json").read_text())["status"] == "failed"


def test_direct_restore_call_cannot_bypass_lab_guard(flow, monkeypatch):
    snapshot, root, connection, _, _ = flow
    monkeypatch.delenv(restore.LAB_ENV)
    with pytest.raises(ValueError, match="isolated"):
        restore._restore(snapshot, DATABASE, root, URL)
    assert not connection.scalar.called


def test_explicit_pgvector_preparation_is_limited_to_new_target(flow, monkeypatch):
    snapshot, root, connection, _, _ = flow
    filtered = root / DATABASE / "restore.list"
    privileged = make_url("postgresql+psycopg://preparer@127.0.0.1:55432/documind_restore_admin")
    monkeypatch.setattr(restore, "filtered_restore_list", Mock(return_value=filtered))
    monkeypatch.setattr(restore, "preparation_url", Mock(return_value=privileged))
    prepare = Mock()
    monkeypatch.setattr(restore, "prepare_extension", prepare)
    restore._restore(snapshot, DATABASE, root, URL, pgvector_version="0.8.0")
    prepare.assert_called_once_with(privileged, DATABASE, URL.username, "0.8.0")
    assert any("CREATE DATABASE" in str(c.args[0]) for c in connection.execute.call_args_list)
    arguments = restore.subprocess.run.call_args.args[0]
    assert arguments[arguments.index("--use-list") + 1] == str(filtered)


def test_blocked_copy_is_not_validated_or_reusable(flow, monkeypatch):
    snapshot, root, _, _, _ = flow
    monkeypatch.setattr(restore, "_restore_contents", Mock(return_value={
        "status": "blocked", "opening_authorized": False, "s2_recovery_authorized": False,
        "quota": {"issued_count": 7, "closed": True},
    }))
    result = restore._restore(snapshot, DATABASE, root, URL)
    assert result["validation_complete"] is False and result["reusable"] is False
    assert json.loads((root / DATABASE / "quarantine.json").read_text())["status"] == "blocked"


@pytest.mark.parametrize("error", [SystemExit("synthetic integrity refusal"), KeyboardInterrupt()])
def test_abort_paths_leave_failed_evidence_and_attempt_quota_closure(flow, monkeypatch, error):
    snapshot, root, _, state, _ = flow
    monkeypatch.setattr(restore, "verify_snapshot", Mock(side_effect=error))
    with pytest.raises(type(error)):
        restore._restore(snapshot, DATABASE, root, URL)
    assert state["closed"] is True
    report = json.loads((root / DATABASE / "quarantine.json").read_text())
    assert report["status"] == "failed" and report["validation_complete"] is False


def test_evidence_failure_precedes_database_creation(flow, monkeypatch):
    snapshot, root, connection, _, _ = flow
    monkeypatch.setattr(restore, "_write_quarantine", Mock(side_effect=OSError("synthetic disk full")))
    with pytest.raises(OSError):
        restore._restore(snapshot, DATABASE, root, URL)
    assert not any("CREATE DATABASE" in str(call.args[0]) for call in connection.execute.call_args_list)


def test_quota_drift_after_sealing_blocks_validation(flow, monkeypatch):
    snapshot, root, _, _, _ = flow
    monkeypatch.setattr(restore, "_restore_contents", Mock(return_value={
        "status": "quarantined", "quota": {"issued_count": 8, "closed": True},
    }))
    with pytest.raises(ValueError, match="changed after sealing"):
        restore._restore(snapshot, DATABASE, root, URL)
    assert json.loads((root / DATABASE / "quarantine.json").read_text())["validation_complete"] is False
