from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.lifecycle_admissions import AdmissionAnchor, AdmissionCoordinator
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry
from ops.testing import lifecycle_lot29_bundle as lot29
from ops.testing import lifecycle_lot210_protocol as lot210


@pytest.fixture(scope="session")
def postgres_server():
    dsn = os.environ.get("DOCUMIND_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Requires an explicitly provisioned disposable isolated PostgreSQL endpoint")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    connection = conninfo_to_dict(dsn)
    if (connection.get("host") != "127.0.0.1"
            or connection.get("port") != "5432"
            or connection.get("dbname") != "postgres"
            or connection.get("user") != "lot210"
            or not connection.get("password")):
        pytest.fail("PostgreSQL protocol tests require the dedicated isolated test service")
    connection["port"] = int(connection["port"])
    try:
        with psycopg.connect(dsn, connect_timeout=3):
            pass
    except psycopg.OperationalError:
        pytest.fail("The isolated disposable PostgreSQL service is unavailable")
    return connection


@pytest.fixture
def postgres_databases(postgres_server, monkeypatch):
    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import URL

    monkeypatch.setenv(lot210.LAB_ENV, "isolated")
    suffix = uuid4().hex[:12]
    primary_name = "phase154l210_" + suffix
    restored_name = "phase154l210_restore_" + suffix
    admin = {
        "host": postgres_server["host"], "port": postgres_server["port"],
        "dbname": "postgres", "user": postgres_server["user"],
        "password": postgres_server["password"],
    }
    with psycopg.connect(**admin, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(primary_name)))
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_name)))

    def adapter(name):
        dsn = URL.create(
            "postgresql", username=postgres_server["user"],
            password=postgres_server["password"], host=postgres_server["host"],
            port=postgres_server["port"], database=name,
        ).render_as_string(hide_password=False)
        return lot210.SyntheticPostgres(dsn, lock_timeout_ms=150)

    primary, restored = adapter(primary_name), adapter(restored_name)
    primary.initialize()
    restored.initialize()
    try:
        yield primary, restored
    finally:
        with psycopg.connect(**admin, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(primary_name)))
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(restored_name)))


@pytest.fixture
def system(tmp_path, monkeypatch, postgres_databases):
    monkeypatch.setenv(lot210.LAB_ENV, "isolated")
    monkeypatch.setenv(lot29.LAB_ENV, "isolated")
    root = tmp_path / "synthetic-lab"
    root.mkdir(mode=0o700)
    (root / lot29.LAB_MARKER).write_bytes(lot29.LAB_MARKER_CONTENT)
    (root / lot210.LAB_MARKER).write_bytes(lot210.LAB_MARKER_CONTENT)
    for directory in (
        "authority", "registry", "witness", "authenticated", "holds",
        "admission_anchor", "bundles", "quarantine", "work",
    ):
        (root / directory).mkdir(mode=0o700)

    paths = {
        "registry": root / "registry" / "registry.sqlite",
        "witness": root / "witness" / "witness.sqlite",
        "authenticated": root / "authenticated" / "authenticated.sqlite",
        "holds": root / "holds" / "holds.sqlite",
        "admission_anchor": root / "admission_anchor" / "anchor.sqlite",
    }
    Registry(paths["registry"]).initialize()
    ConfirmationStore(paths["witness"]).initialize()
    authentication_key, admission_key = os.urandom(32), os.urandom(32)
    authenticated = AuthenticatedConfirmationStore(
        paths["authenticated"], authentication_key, lot29.DOMAIN)
    authenticated.initialize()
    holds = HoldStore(paths["holds"], authenticated)
    holds.initialize()
    anchor = AdmissionAnchor(paths["admission_anchor"], admission_key)
    anchor.initialize()

    settings = SimpleNamespace(
        lifecycle_registry_path=paths["registry"],
        lifecycle_confirmation_path=paths["witness"],
        lifecycle_authenticated_confirmation_path=paths["authenticated"],
        lifecycle_holds_path=paths["holds"],
        lifecycle_admission_anchor_path=paths["admission_anchor"],
    )
    authority = lot210.FreshnessAuthority(
        root / lot210.AUTHORITY_RELATIVE_PATH, root, os.urandom(32))
    authority.initialize()
    postgres, postgres_restore = postgres_databases
    verifier = lot29.SyntheticLifecycleConsistencyVerifier(
        authentication_key, admission_key)
    keyring = {"test-v1": os.urandom(32)}
    gate = lot210.CooperativeWriteGate()
    admission_protocol = lot210.LifecycleAdmissionProtocol(
        authority, postgres, ConfirmationStore(paths["witness"]),
        AdmissionCoordinator(ConfirmationStore(paths["witness"]), anchor),
        Registry(paths["registry"]), gate)

    def operation_protocol(owner_id, scopes=None):
        return lot210.LifecycleOperationProtocol(
            authority, postgres, authenticated, holds,
            lambda operation: scopes or [("account", operation["target"]),
                                          ("owner", str(owner_id))],
            gate)

    def capture():
        return lot210.CoordinatedCapture(
            authority, postgres, settings, root, keyring, "test-v1",
            verifier, gate, lock_timeout=0.15,
        ).capture()

    def recover(artifact, destination=None):
        return lot210.recover(
            artifact, root, root / "quarantine",
            destination or root / "quarantine" / ("restore-" + uuid4().hex[:12]),
            keyring, "test-v1", verifier, authority, postgres_restore)

    result = SimpleNamespace(
        root=root, paths=paths, settings=settings, authority=authority,
        postgres=postgres, postgres_restore=postgres_restore,
        authenticated=authenticated, holds=holds, anchor=anchor,
        verifier=verifier, keyring=keyring, gate=gate,
        admissions=admission_protocol, operation_protocol=operation_protocol,
        capture=capture, recover=recover,
    )
    yield result


def open_admissions(system):
    system.authority.set_registration_open(True)
    system.postgres.set_registration_open(True)


def close_admissions(system):
    system.authority.set_registration_open(False)
    system.postgres.set_registration_open(False)


def admit(system, *, operation_id=None, user_id=None):
    return system.admissions.admit(
        str(operation_id or uuid4()), str(user_id or uuid4()))


def add_confirmed_erasure(system, *, user_id=None, owner_id=None, confirm=True):
    user_id, owner_id = user_id or uuid4(), owner_id or uuid4()
    receipt_id = Registry(system.paths["registry"]).receive(
        "erasure", user_id=user_id, owner_id=owner_id)
    with Registry(system.paths["registry"]).connection() as db:
        row = db.execute(
            "SELECT id,kind,user_id,owner_id,received_at,state FROM requests WHERE id=?",
            (receipt_id,),
        ).fetchone()
    operation = system.verifier._expected_operation("account", row)
    system.authenticated.prepare(operation)
    if confirm:
        system.authenticated.confirm(operation)
    return receipt_id, operation, owner_id


def add_active_hold(system, user_id):
    now = datetime.now(timezone.utc)
    hold = {
        "id": str(uuid4()), "responsible_id": str(uuid4()),
        "scope_id": str(user_id), "scope_kind": "account",
        "reason": "legal_hold", "reviewed_at": now - timedelta(minutes=1),
        "review_at": now + timedelta(days=29), "ends_at": None,
        "end_event": "legal_hold_lifted",
    }
    system.holds.create(hold, now)
    return hold


def capture_metadata(system, artifact):
    wrapper, metadata = lot210._decode_artifact(artifact, system.root)
    bundle_path = system.root / "bundles" / (metadata["backup_id"] + ".bundle")
    envelope = lot29._read_bundle(bundle_path, system.root)
    key = lot29._validate_keyring(system.keyring, "test-v1")
    state_bytes = lot210.AESGCM(
        lot29._bundle_key(key, metadata["backup_id"])).decrypt(
            bytes.fromhex(wrapper["postgres_nonce"]),
            bytes.fromhex(wrapper["postgres_ciphertext"]),
            lot210._json({"metadata": metadata}))
    return metadata, json.loads(state_bytes)


def test_five_cumulative_admissions_are_idempotent_and_sixth_is_refused(system):
    open_admissions(system)
    operations = []
    for _ in range(5):
        operation_id, user_id = str(uuid4()), str(uuid4())
        operations.append((operation_id, user_id))
        assert system.admissions.admit(operation_id, user_id)["state"] == "result_recorded"

    repeated = system.admissions.admit(*operations[1])
    assert repeated == {
        "operation_id": operations[1][0], "sequence": 2,
        "state": "result_recorded", "idempotent": True,
    }
    with pytest.raises(lot210.ProtocolError, match="limit"):
        admit(system)
    with pytest.raises(lot210.ProtocolError, match="cannot be reused"):
        admit(system, user_id=operations[0][1])
    assert system.authority.snapshot()["admission_count"] == 5
    assert system.postgres.read_state_from_new_connection()["quota"]["issued_count"] == 5
    assert len(ConfirmationStore(system.paths["witness"]).admission_entries()) == 5


def test_concurrent_distinct_reservations_allocate_monotone_unique_slots(system):
    system.authority.set_registration_open(True)
    requests = [(str(uuid4()), str(uuid4())) for _ in range(5)]
    with ThreadPoolExecutor(max_workers=5) as workers:
        reservations = list(workers.map(
            lambda request: system.authority.reserve_admission(*request), requests))
    assert sorted(row["sequence"] for row in reservations) == [1, 2, 3, 4, 5]
    assert len({row["operation_id"] for row in reservations}) == 5
    assert system.authority.snapshot()["admission_count"] == 5
    with pytest.raises(lot210.ProtocolError, match="limit"):
        system.authority.reserve_admission(str(uuid4()), str(uuid4()))


def test_concurrent_repetition_of_same_reservation_keeps_one_slot(system):
    system.authority.set_registration_open(True)
    request = str(uuid4()), str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as workers:
        reservations = list(workers.map(
            lambda _: system.authority.reserve_admission(*request), range(4)))
    assert {row["sequence"] for row in reservations} == {1}
    assert system.authority.snapshot()["admission_count"] == 1
    assert len(system.authority.snapshot()["admissions"]) == 1


def test_closed_or_unavailable_authority_fails_before_postgres_mutation(system):
    with pytest.raises(lot210.ProtocolError, match="keeps registration closed"):
        admit(system)
    system.authority.available = False
    with pytest.raises(lot210.FreshnessUnavailable, match="unavailable"):
        admit(system)
    state = system.postgres.read_state_from_new_connection()
    assert state["quota"]["issued_count"] == 0
    assert state["admissions"] == []


def test_lost_reservation_response_consumes_place_and_cannot_be_replayed(system):
    open_admissions(system)
    system.authority.drop_next_response = True
    operation_id, user_id = str(uuid4()), str(uuid4())
    with pytest.raises(lot210.AuthorityResponseLost):
        system.admissions.admit(operation_id, user_id)
    assert system.authority.operation(operation_id)["state"] == "uncertain"
    assert system.authority.snapshot()["admission_count"] == 1
    with pytest.raises(lot210.ReconciliationRequired):
        system.admissions.admit(operation_id, user_id)
    next_reservation = system.authority.reserve_admission(str(uuid4()), str(uuid4()))
    assert next_reservation["sequence"] == 2
    assert system.postgres.read_state_from_new_connection()["quota"]["issued_count"] == 0


def test_lost_result_response_is_idempotently_reconciled_without_replaying_effect(system, monkeypatch):
    open_admissions(system)
    original = system.postgres.settle_admission

    def lose_after_postgres_commit(operation_id, sequence):
        original(operation_id, sequence)
        system.authority.drop_next_response = True

    monkeypatch.setattr(system.postgres, "settle_admission", lose_after_postgres_commit)
    operation_id, user_id = str(uuid4()), str(uuid4())
    with pytest.raises(lot210.AuthorityResponseLost):
        system.admissions.admit(operation_id, user_id)
    assert system.authority.operation(operation_id)["state"] == "result_recorded"
    assert system.authority.snapshot()["admission_count"] == 1
    repeated = system.admissions.admit(operation_id, user_id)
    assert repeated["idempotent"] is True
    assert system.postgres.read_state_from_new_connection()["quota"]["issued_count"] == 1
    assert len(ConfirmationStore(system.paths["witness"]).admission_entries()) == 1


def test_authority_busy_timeout_blocks_admission_and_preserves_count(system):
    system.authority.timeout = 0.02
    locker = sqlite3.connect(system.authority.path, timeout=0.1, isolation_level=None)
    locker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(lot210.FreshnessUnavailable, match="failed|read failed"):
            admit(system)
    finally:
        locker.rollback()
        locker.close()
    assert system.postgres.read_state_from_new_connection()["quota"]["issued_count"] == 0


def test_operation_requires_confirmed_receipt_and_active_hold_blocks(system):
    receipt_id, operation, owner_id = add_confirmed_erasure(system, confirm=False)
    protocol = system.operation_protocol(owner_id)
    with pytest.raises(lot210.ReconciliationRequired, match="confirmation"):
        protocol.prepare(operation)
    assert system.authority.operation(operation["id"]) is None

    user_id = str(uuid4())
    receipt_id, operation, owner_id = add_confirmed_erasure(system, user_id=user_id)
    add_active_hold(system, user_id)
    before = system.authority.snapshot()["generation"]
    with pytest.raises(lot210.ProtocolError, match="A20 hold"):
        system.operation_protocol(owner_id).prepare(operation)
    assert system.authority.snapshot()["generation"] == before
    assert system.postgres.read_state_from_new_connection()["operations"] == []


def test_operation_authorization_is_persisted_once_and_result_is_idempotent(system):
    receipt_id, operation, owner_id = add_confirmed_erasure(system)
    protocol = system.operation_protocol(owner_id)
    prepared = protocol.prepare(operation)
    authorized = protocol.authorize(operation)
    assert prepared["state"] == "prepared"
    assert authorized["state"] == "authorized"
    assert system.authority.verify_authorization(operation["id"], authorized["generation"])
    generation = system.authority.snapshot()["generation"]
    with pytest.raises(lot210.ReconciliationRequired, match="fresh prepared"):
        protocol.authorize(operation)
    assert system.authority.snapshot()["generation"] == generation

    Registry(system.paths["registry"]).account_deactivated(receipt_id)
    result_digest = lot210._digest(b"synthetic effect proof")
    result = protocol.record_result(operation, result_digest)
    repeated = protocol.record_result(operation, result_digest)
    assert result["state"] == "result_recorded"
    assert repeated["generation"] == result["generation"]
    assert system.authenticated.verify(operation) == "result_recorded"


def test_uncertain_operation_never_reauthorizes_and_requires_explicit_evidence(system):
    receipt_id, operation, owner_id = add_confirmed_erasure(system)
    protocol = system.operation_protocol(owner_id)
    protocol.prepare(operation)
    protocol.authorize(operation)
    uncertain = protocol.mark_uncertain(operation["id"])
    assert uncertain["state"] == "uncertain"
    with pytest.raises(lot210.ReconciliationRequired):
        protocol.authorize(operation)
    Registry(system.paths["registry"]).account_deactivated(receipt_id)
    result = protocol.reconcile_applied(
        operation, lot210._digest(b"applied"), lot210._digest(b"review evidence"))
    assert result["state"] == "result_recorded"
    assert system.authenticated.verify(operation) == "result_recorded"


def test_hold_release_requires_verified_active_hold_and_records_release_evidence(system):
    user_id, owner_id = str(uuid4()), str(uuid4())
    hold = add_active_hold(system, user_id)
    operation = {
        "id": str(uuid4()), "type": "hold_release", "target": hold["id"],
        "receipt_sha256": lot210._digest(b"synthetic hold release evidence"),
    }
    protocol = system.operation_protocol(
        owner_id, [("account", user_id), ("owner", owner_id)])
    protocol.prepare(operation)
    authorized = protocol.authorize(operation)
    evidence = b"synthetic hold release evidence"
    assert lot210._digest(evidence) == operation["receipt_sha256"]
    system.holds.release(
        hold["id"], hold["responsible_id"], str(uuid4()), evidence,
        datetime.now(timezone.utc),
    )
    result = protocol.record_result(operation, operation["receipt_sha256"])
    assert authorized["state"] == "authorized"
    assert result["state"] == "result_recorded"
    assert system.authority.operation(operation["id"])["state"] == "result_recorded"


def test_capture_and_restore_binds_postgres_sqlite_and_authority_and_keeps_closed(system):
    open_admissions(system)
    for _ in range(3):
        admit(system)
    close_admissions(system)
    artifact = system.capture()
    metadata, pg_state = capture_metadata(system, artifact)
    assert metadata["postgres_transaction_snapshot"]
    assert metadata["postgres_wal_lsn"]
    assert metadata["authority_admission_count"] == 3
    assert pg_state["quota"]["issued_count"] == 3

    result = system.recover(artifact)
    assert result["independent_freshness_verified"] is True
    assert result["critical_mutations_allowed"] is False
    assert result["registration_open"] is False
    restored_state = system.postgres_restore.read_state_from_new_connection()
    assert restored_state["quota"] == {
        "id": "public", "issued_count": 3, "closed": True,
    }
    assert result["requires_separate_reconciliation"] is True


def test_old_postgres_and_sqlite_snapshot_is_rejected_after_authority_advances(system):
    open_admissions(system)
    for _ in range(3):
        admit(system)
    close_admissions(system)
    artifact = system.capture()
    open_admissions(system)
    for _ in range(2):
        admit(system)
    close_admissions(system)

    destination = system.root / "quarantine" / "old-coordinated-copy"
    with pytest.raises(lot210.RollbackDetected, match="predate or diverge"):
        system.recover(artifact, destination)
    assert destination.is_dir()
    with sqlite3.connect(destination / "witness.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] == 3
    restored = system.postgres_restore.read_state_from_new_connection()
    assert restored["quota"]["issued_count"] == 3
    assert restored["quota"]["closed"] is True
    assert system.authority.snapshot()["admission_count"] == 5


def test_valid_old_hmac_prefix_cannot_authorize_after_capture(system):
    receipt_id, operation, owner_id = add_confirmed_erasure(system)
    protocol = system.operation_protocol(owner_id)
    protocol.prepare(operation)
    artifact = system.capture()
    old_generation = system.authority.snapshot()["generation"]

    protocol.authorize(operation)
    Registry(system.paths["registry"]).account_deactivated(receipt_id)
    protocol.record_result(operation, lot210._digest(b"deleted"))
    assert not system.authority.verify_authorization(operation["id"], old_generation)
    with pytest.raises(lot210.RollbackDetected, match="predate or diverge"):
        system.recover(artifact)


def test_single_component_divergence_is_not_repaired_or_promoted(system):
    open_admissions(system)
    admit(system)
    close_admissions(system)
    artifact = system.capture()
    metadata, pg_state = capture_metadata(system, artifact)
    witness = ConfirmationStore(system.paths["witness"]).admission_entries()
    authority = system.authority.snapshot()
    pg_state["quota"]["issued_count"] = 0
    pg_state["admissions"] = []
    with pytest.raises(lot210.RollbackDetected, match="counts differ"):
        lot210._validate_cross_store_state(pg_state, authority, witness)
    assert metadata["authority_admission_count"] == 1


def test_postgres_sqlite_count_disagreement_blocks_capture_before_publication(system):
    open_admissions(system)
    admit(system)
    close_admissions(system)
    with system.postgres._connect() as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public_registration_quota SET issued_count=0 "
                               "WHERE id='public'")
    with pytest.raises(lot210.RollbackDetected, match="counts differ"):
        system.capture()
    assert list((system.root / "bundles").iterdir()) == []


def test_noncooperating_postgres_writer_blocks_capture_at_table_fence(system):
    system.postgres.lock_timeout_ms = 80
    writer = system.postgres._connect()
    writer.execute("UPDATE public_registration_quota SET closed=false WHERE id='public'")
    try:
        with pytest.raises(lot210.ProtocolError, match="PostgreSQL writer fence failed"):
            system.capture()
    finally:
        writer.rollback()
        writer.close()
    assert list((system.root / "bundles").iterdir()) == []


def test_active_cooperative_writer_prevents_capture(system):
    with system.gate.writer():
        with pytest.raises(lot210.ProtocolError, match="Cooperative writer fence"):
            system.capture()
    assert list((system.root / "bundles").iterdir()) == []


def test_unavailable_or_locked_authority_blocks_capture_without_archive(system):
    system.authority.available = False
    with pytest.raises(lot210.FreshnessUnavailable, match="unavailable"):
        system.capture()
    assert list((system.root / "bundles").iterdir()) == []
    system.authority.available = True
    locker = sqlite3.connect(system.authority.path, timeout=0.1, isolation_level=None)
    locker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(lot210.FreshnessUnavailable, match="capture fence failed"):
            system.capture()
    finally:
        locker.rollback()
        locker.close()
    assert list((system.root / "bundles").iterdir()) == []


def test_authority_history_truncation_and_snapshot_copy_are_not_freshness(system):
    system.authority.set_registration_open(True)
    system.authority.set_registration_open(False)
    artifact = system.capture()
    clone = system.root / "quarantine" / "authority-copy.sqlite"
    shutil.copyfile(system.authority.path, clone)
    copied = lot210.inspect_restored_prefix(
        clone, system.root, system.authority._key)
    assert copied["copied_chain_authentication_verified"] is True
    assert copied["independent_freshness_verified"] is False

    cloned_authority = copy.copy(system.authority)
    cloned_authority.path = clone
    with pytest.raises(lot210.FreshnessUnavailable, match="not independent"):
        lot210.recover(
            artifact, system.root, system.root / "quarantine",
            system.root / "quarantine" / "clone-restore", system.keyring,
            "test-v1", system.verifier, cloned_authority, system.postgres_restore)

    with sqlite3.connect(clone) as db:
        db.execute("DELETE FROM authority_events WHERE generation=1")
    with pytest.raises(lot210.FreshnessUnavailable, match="truncated"):
        lot210.inspect_restored_prefix(clone, system.root, system.authority._key)


def test_tampered_coordinated_artifact_is_rejected_before_restore(system):
    artifact = system.capture()
    wrapper = json.loads(artifact.read_text(encoding="utf-8"))
    wrapper["metadata"]["authority_generation"] += 1
    artifact.write_text(json.dumps(wrapper, sort_keys=True, separators=(",", ":")),
                        encoding="utf-8")
    with pytest.raises(lot210.ProtocolError, match="authentication"):
        system.recover(artifact)
    assert not list((system.root / "quarantine").glob("restore-*"))


def test_restore_refuses_unclosed_authority_and_keeps_mutations_disabled(system):
    open_admissions(system)
    admit(system)
    artifact = system.capture()
    destination = system.root / "quarantine" / "authority-open"
    with pytest.raises(lot210.RollbackDetected, match="authority has not confirmed closed"):
        system.recover(artifact, destination)
    assert destination.is_dir()
    assert system.postgres_restore.read_state_from_new_connection()["quota"]["closed"] is True


def test_restoration_target_must_be_named_quarantine_database(system):
    ordinary = lot210.SyntheticPostgres(
        system.postgres.dsn.replace(system.postgres.database, "phase154l210_other"),
        lock_timeout_ms=100,
    )
    with pytest.raises(lot210.ProtocolError, match="new quarantine database"):
        ordinary.restore_quarantine({})
