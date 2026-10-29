import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.lifecycle_admissions import AdmissionAnchor
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry
from backend.lifecycle_snapshot import STORES, write_snapshot_archive
from ops.testing import lifecycle_lot29_bundle as bundle


@pytest.fixture
def laboratory(tmp_path, monkeypatch):
    monkeypatch.setenv(bundle.LAB_ENV, "isolated")
    root = tmp_path / "synthetic-lab"
    root.mkdir(mode=0o700)
    (root / bundle.LAB_MARKER).write_bytes(bundle.LAB_MARKER_CONTENT)
    for directory in ("registry", "witness", "authenticated", "holds",
                      "admission_anchor", "bundles", "quarantine", "work"):
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
    auth_key = os.urandom(32)
    admission_key = os.urandom(32)
    AuthenticatedConfirmationStore(paths["authenticated"], auth_key, bundle.DOMAIN).initialize()
    auth = AuthenticatedConfirmationStore(paths["authenticated"], auth_key, bundle.DOMAIN)
    HoldStore(paths["holds"], auth).initialize()
    AdmissionAnchor(paths["admission_anchor"], admission_key).initialize()

    settings = SimpleNamespace(
        lifecycle_registry_path=paths["registry"],
        lifecycle_confirmation_path=paths["witness"],
        lifecycle_authenticated_confirmation_path=paths["authenticated"],
        lifecycle_holds_path=paths["holds"],
        lifecycle_admission_anchor_path=paths["admission_anchor"],
    )
    keys = {"test-v1": os.urandom(32)}
    verifier = bundle.SyntheticLifecycleConsistencyVerifier(auth_key, admission_key)
    return SimpleNamespace(
        root=root, paths=paths, settings=settings, keys=keys, verifier=verifier,
        auth_key=auth_key, admission_key=admission_key,
    )


def create(lab):
    return bundle.create_bundle(
        lab.settings, lab.root, lab.root / "bundles", lab.keys, "test-v1", lab.verifier)


def restore(lab, archive, destination=None, verifier=None):
    return bundle.restore_bundle(
        archive, lab.root, lab.root / "quarantine",
        destination or lab.root / "quarantine" / "restored",
        lab.keys, verifier or lab.verifier,
    )


def add_confirmed_account_receipt(lab):
    user_id, owner_id = uuid4(), uuid4()
    receipt_id = Registry(lab.paths["registry"]).receive(
        "erasure", user_id=user_id, owner_id=owner_id)
    with Registry(lab.paths["registry"]).connection() as db:
        row = db.execute(
            "SELECT id,kind,user_id,owner_id,received_at FROM requests WHERE id=?",
            (receipt_id,),
        ).fetchone()
    operation = lab.verifier._expected_operation("account", row)
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    auth.prepare(operation)
    auth.confirm(operation)
    return receipt_id, operation


def test_complete_synthetic_set_round_trips_into_quarantine(laboratory):
    lab = laboratory
    archive = create(lab)
    result = restore(lab, archive)

    assert result["restored_components"] == sorted(bundle.COMPONENTS)
    assert result["integrity_verified"] is True
    assert result["completeness_verified"] is True
    assert result["cross_store_consistency_verified"] is True
    assert result["independent_freshness_verified"] is False
    assert result["critical_mutations_allowed"] is False
    for name in bundle.COMPONENTS:
        with sqlite3.connect(Path(result["restore_path"]) / f"{name}.sqlite") as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_populated_receipts_holds_and_admissions_are_cross_checked(laboratory):
    lab = laboratory
    add_confirmed_account_receipt(lab)

    user_id = str(uuid4())
    witness = ConfirmationStore(lab.paths["witness"])
    witness.reserve_admission(1, user_id)
    anchor = AdmissionAnchor(lab.paths["admission_anchor"], lab.admission_key)
    entries = witness.admission_entries()
    anchor.reserve([], entries)
    anchor.settle(entries, user_id)
    Registry(lab.paths["registry"]).observe_admissions(1)

    now = datetime.now(timezone.utc)
    hold = {
        "id": str(uuid4()), "responsible_id": str(uuid4()), "scope_id": user_id,
        "scope_kind": "account", "reason": "legal_hold",
        "reviewed_at": now - timedelta(seconds=1),
        "review_at": now + timedelta(days=29), "ends_at": None,
        "end_event": "legal_hold_lifted",
    }
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    HoldStore(lab.paths["holds"], auth).create(hold, now)

    archive = create(lab)
    result = restore(lab, archive)
    assert result["cross_store_consistency_verified"] is True
    assert result["critical_mutations_allowed"] is False


def test_all_aes_gcm_nonces_are_distinct_within_bundle(laboratory):
    raw = json.loads(create(laboratory).read_text(encoding="utf-8"))
    nonces = [raw["manifest_nonce"]]
    nonces.extend(value["nonce"] for value in raw["components"].values())
    assert len(nonces) == len(set(nonces))


def test_configured_paths_are_required_existing_distinct_and_inside_lab(laboratory):
    lab = laboratory
    missing = SimpleNamespace(**vars(lab.settings))
    missing.lifecycle_holds_path = None
    with pytest.raises(bundle.BundleError, match="not configured"):
        bundle.configured_store_paths(missing, lab.root)

    outside = SimpleNamespace(**vars(lab.settings))
    outside.lifecycle_holds_path = lab.root.parent / "outside.sqlite"
    with pytest.raises(bundle.BundleError, match="outside"):
        bundle.configured_store_paths(outside, lab.root)

    aliased = SimpleNamespace(**vars(lab.settings))
    aliased.lifecycle_holds_path = lab.paths["registry"]
    with pytest.raises(bundle.BundleError, match="distinct"):
        bundle.configured_store_paths(aliased, lab.root)


def test_synthetic_fresh_provisioning_has_private_files_and_exact_schemas(laboratory):
    lab = laboratory
    for name, (_, expected_version, expected_tables) in STORES.items():
        path = lab.paths[name]
        if os.name == "posix":
            assert path.parent.stat().st_mode & 0o077 == 0
            assert path.stat().st_mode & 0o077 == 0
        with sqlite3.connect(path) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("PRAGMA user_version").fetchone()[0] == expected_version
            actual_tables = {
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            }
            assert actual_tables == expected_tables


def test_missing_store_fails_without_creating_empty_database(laboratory):
    lab = laboratory
    path = lab.paths["holds"]
    path.unlink()
    with pytest.raises(bundle.BundleError, match="missing"):
        create(lab)
    assert not path.exists()
    assert list((lab.root / "bundles").iterdir()) == []


def test_empty_registry_substituted_for_receipt_registry_is_rejected(laboratory):
    lab = laboratory
    add_confirmed_account_receipt(lab)
    path = lab.paths["registry"]
    path.unlink()
    Registry(path).initialize()
    with pytest.raises(bundle.BundleError, match="differ"):
        create(lab)
    assert list((lab.root / "bundles").iterdir()) == []


def test_missing_confirmation_is_rejected(laboratory):
    lab = laboratory
    _, operation = add_confirmed_account_receipt(lab)
    with sqlite3.connect(lab.paths["authenticated"]) as db:
        db.execute("DELETE FROM synthetic_transitions WHERE operation=?", (operation["id"],))
    with pytest.raises(bundle.BundleError, match="differ"):
        create(lab)


def test_valid_old_hmac_prefix_is_not_mistaken_for_freshness(laboratory):
    lab = laboratory
    _, operation = add_confirmed_account_receipt(lab)
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    auth.authorize_once(operation)
    with sqlite3.connect(lab.paths["authenticated"]) as db:
        db.execute(
            "DELETE FROM synthetic_transitions WHERE operation=? AND sequence=3",
            (operation["id"],),
        )

    archive = create(lab)
    result = restore(lab, archive)
    assert result["integrity_verified"] is True
    assert result["cross_store_consistency_verified"] is True
    assert result["independent_freshness_verified"] is False
    assert result["critical_mutations_allowed"] is False


def test_hmac_truncation_with_sequence_gap_is_rejected(laboratory):
    lab = laboratory
    _, operation = add_confirmed_account_receipt(lab)
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    auth.authorize_once(operation)
    with sqlite3.connect(lab.paths["authenticated"]) as db:
        db.execute(
            "DELETE FROM synthetic_transitions WHERE operation=? AND sequence=2",
            (operation["id"],),
        )
    with pytest.raises(bundle.BundleError, match="consistency"):
        create(lab)


def test_missing_a20_hold_mirror_is_rejected(laboratory):
    lab = laboratory
    now = datetime.now(timezone.utc)
    hold = {
        "id": str(uuid4()), "responsible_id": str(uuid4()), "scope_id": str(uuid4()),
        "scope_kind": "document", "reason": "legal_hold",
        "reviewed_at": now - timedelta(seconds=1),
        "review_at": now + timedelta(days=29), "ends_at": None,
        "end_event": "legal_hold_lifted",
    }
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    HoldStore(lab.paths["holds"], auth).create(hold, now)
    with sqlite3.connect(lab.paths["holds"]) as db:
        db.execute("DELETE FROM holds_v2")
        db.execute("DELETE FROM hold_decisions_v2")
    with pytest.raises(bundle.BundleError, match="Hold registries differ"):
        create(lab)


def test_missing_admission_witness_or_anchor_is_rejected(laboratory):
    lab = laboratory
    user_id = str(uuid4())
    witness = ConfirmationStore(lab.paths["witness"])
    witness.reserve_admission(1, user_id)
    anchor = AdmissionAnchor(lab.paths["admission_anchor"], lab.admission_key)
    entries = witness.admission_entries()
    anchor.reserve([], entries)
    anchor.settle(entries, user_id)
    with sqlite3.connect(lab.paths["witness"]) as db:
        db.execute("DELETE FROM admissions")
    with pytest.raises(bundle.BundleError, match="admission"):
        create(lab)


def test_absent_anchor_row_is_rejected(laboratory):
    lab = laboratory
    with sqlite3.connect(lab.paths["admission_anchor"]) as db:
        db.execute("DELETE FROM admission_anchor")
    with pytest.raises(bundle.BundleError, match="anchor"):
        create(lab)


def test_populated_admissions_require_matching_registry_watermark(laboratory):
    lab = laboratory
    user_id = str(uuid4())
    witness = ConfirmationStore(lab.paths["witness"])
    witness.reserve_admission(1, user_id)
    anchor = AdmissionAnchor(lab.paths["admission_anchor"], lab.admission_key)
    entries = witness.admission_entries()
    anchor.reserve([], entries)
    anchor.settle(entries, user_id)
    with pytest.raises(bundle.BundleError, match="watermark"):
        create(lab)


@pytest.mark.parametrize("tamper", ["component", "manifest"])
def test_modified_encrypted_component_or_manifest_is_rejected(laboratory, tamper):
    lab = laboratory
    archive = create(lab)
    raw = json.loads(archive.read_text(encoding="utf-8"))
    if tamper == "component":
        value = raw["components"]["registry"]["ciphertext"]
        raw["components"]["registry"]["ciphertext"] = value[:-4] + "AAAA"
    else:
        value = bytearray(base64.b64decode(raw["manifest_ciphertext"]))
        value[-1] ^= 0x01
        raw["manifest_ciphertext"] = base64.b64encode(value).decode("ascii")
    archive.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(bundle.BundleError):
        restore(lab, archive)
    assert not (lab.root / "quarantine" / "restored").exists()


def test_wrong_key_fails_before_quarantine_creation(laboratory):
    lab = laboratory
    archive = create(lab)
    lab.keys["test-v1"] = os.urandom(32)
    with pytest.raises(bundle.BundleError, match="authentication"):
        restore(lab, archive)
    assert not (lab.root / "quarantine" / "restored").exists()


def test_incompatible_schema_version_fails_closed(laboratory):
    lab = laboratory
    with sqlite3.connect(lab.paths["registry"]) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(bundle.BundleError, match="schema"):
        create(lab)


def test_nonempty_and_outside_quarantine_destinations_are_rejected(laboratory):
    lab = laboratory
    archive = create(lab)
    destination = lab.root / "quarantine" / "existing"
    destination.mkdir()
    with pytest.raises(bundle.BundleError, match="new direct child"):
        restore(lab, archive, destination)
    with pytest.raises(bundle.BundleError, match="new direct child"):
        restore(lab, archive, lab.root / "outside")


def test_capture_failure_publishes_no_partial_bundle(laboratory, monkeypatch):
    lab = laboratory
    original = bundle._snapshot_database
    calls = 0

    def fail_on_third(path, name, timeout):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise sqlite3.OperationalError("synthetic capture failure")
        return original(path, name, timeout)

    monkeypatch.setattr(bundle, "_snapshot_database", fail_on_third)
    with pytest.raises(bundle.BundleError, match="capture failed"):
        create(lab)
    assert list((lab.root / "bundles").iterdir()) == []


def test_bundle_name_collision_preserves_existing_file(laboratory, monkeypatch):
    lab = laboratory
    backup_id = "00000000-0000-4000-8000-000000000001"
    ids = iter((UUID(backup_id), UUID("00000000-0000-4000-8000-000000000002")))
    monkeypatch.setattr(bundle, "uuid4", lambda: next(ids))
    destination = lab.root / "bundles" / f"{backup_id}.bundle"
    existing = b"existing synthetic archive"
    destination.write_bytes(existing)

    with pytest.raises(bundle.BundleError, match="Could not publish"):
        create(lab)

    assert destination.read_bytes() == existing
    assert sorted(path.name for path in (lab.root / "bundles").iterdir()) == [
        destination.name,
    ]


def test_restore_failure_removes_partial_quarantine(laboratory, monkeypatch):
    lab = laboratory
    archive = create(lab)
    original = bundle._write_database
    calls = 0

    def fail_after_one(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic restore failure")
        original(path, payload)

    monkeypatch.setattr(bundle, "_write_database", fail_after_one)
    with pytest.raises(bundle.BundleError, match="restore failed"):
        restore(lab, archive)
    assert not (lab.root / "quarantine" / "restored").exists()
    assert list((lab.root / "quarantine").iterdir()) == []


def test_wal_database_is_backed_up_through_sqlite_backup_api(laboratory):
    lab = laboratory
    connection = sqlite3.connect(lab.paths["registry"])
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute(
            "INSERT INTO admission_watermark VALUES (1, 0, ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()
        archive = create(lab)
    finally:
        connection.close()

    result = restore(lab, archive)
    assert result["integrity_verified"] is True
    with sqlite3.connect(Path(result["restore_path"]) / "registry.sqlite") as db:
        assert db.execute("SELECT issued_count FROM admission_watermark WHERE id=1").fetchone()[0] == 0


def _configure_snapshot_environment(lab, monkeypatch):
    monkeypatch.setenv("LIFECYCLE_DATA_ROOT", str(lab.root))
    variables = {
        "registry": "LIFECYCLE_REGISTRY_PATH",
        "witness": "LIFECYCLE_CONFIRMATION_PATH",
        "authenticated": "LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH",
        "holds": "LIFECYCLE_HOLDS_PATH",
        "admission_anchor": "LIFECYCLE_ADMISSION_ANCHOR_PATH",
    }
    for name, variable in variables.items():
        monkeypatch.setenv(variable, str(lab.paths[name]))
    monkeypatch.setenv("LIFECYCLE_BACKUP_LOCK_PATH", str(lab.root / ".backup.lock"))
    monkeypatch.setenv("LIFECYCLE_CAPTURE_ID", "00000000-0000-4000-8000-000000000001")


def _snapshot_paths(archive_path, destination):
    with tarfile.open(archive_path, "r:gz") as archive:
        if os.name == 'posix':
            assert all(member.mode & 0o077 == 0 for member in archive.getmembers())
        archive.extractall(destination, filter="data")
    result = {}
    for name in STORES:
        directory = destination / name
        directory.mkdir(mode=0o700)
        path = directory / f"{name}.sqlite"
        (destination / "stores" / f"{name}.sqlite").replace(path)
        result[name] = path
    return result


def test_real_capture_includes_exact_five_wal_stores_and_keeps_quarantine(laboratory, monkeypatch, tmp_path):
    lab = laboratory
    add_confirmed_account_receipt(lab)

    user_id = str(uuid4())
    witness = ConfirmationStore(lab.paths["witness"])
    witness.reserve_admission(1, user_id)
    anchor = AdmissionAnchor(lab.paths["admission_anchor"], lab.admission_key)
    entries = witness.admission_entries()
    anchor.reserve([], entries)
    anchor.settle(entries, user_id)
    Registry(lab.paths["registry"]).observe_admissions(1)

    now = datetime.now(timezone.utc)
    hold = {
        "id": str(uuid4()), "responsible_id": str(uuid4()), "scope_id": user_id,
        "scope_kind": "account", "reason": "legal_hold",
        "reviewed_at": now - timedelta(seconds=1),
        "review_at": now + timedelta(days=29), "ends_at": None,
        "end_event": "legal_hold_lifted",
    }
    auth = AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN)
    HoldStore(lab.paths["holds"], auth).create(hold, now)

    document_id, owner_id = str(uuid4()), str(uuid4())
    storage_name = uuid4().hex + ".txt"
    registry = Registry(lab.paths["registry"])
    registry.document_requested(document_id, owner_id, storage_name)
    with registry.connection() as db:
        row = db.execute(
            "SELECT document_id,owner_id,storage_name,requested_at FROM document_erasures "
            "WHERE document_id=?", (document_id,),
        ).fetchone()
    operation = lab.verifier._expected_operation("document", row)
    auth.prepare(operation)
    auth.confirm(operation)
    auth.authorize(operation)
    auth.record_result(operation)
    registry.document_finished(document_id, True)

    for path in lab.paths.values():
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
            connection.execute("PRAGMA wal_autocheckpoint=0")

    output = io.BytesIO()
    _configure_snapshot_environment(lab, monkeypatch)
    metadata = write_snapshot_archive(output)
    archive_path = tmp_path / "lifecycle.sqlite.tar.gz"
    archive_path.write_bytes(output.getvalue())
    assert set(metadata["stores"]) == set(STORES)
    assert all(value["journal_mode"] == "wal" for value in metadata["stores"].values())
    restored = _snapshot_paths(archive_path, tmp_path / "restored-stores")
    for name, path in restored.items():
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    with monkeypatch.context() as context:
        context.delenv("LIFECYCLE_BACKUP_LOCK_PATH")
        evidence = lab.verifier.verify(restored)
    assert evidence["document_receipts"] == 1
    assert evidence["holds"] == 1
    assert evidence["admissions"] == 1
    assert evidence["freshness"] == "not_verified"
    assert evidence["external_state_excluded"] == ["postgresql.public_registration_quota"]


def test_uncertain_operation_snapshot_cannot_claim_cross_store_consistency(laboratory, monkeypatch, tmp_path):
    lab = laboratory
    receipt_id = Registry(lab.paths["registry"]).receive(
        "erasure", user_id=uuid4(), owner_id=uuid4())
    with Registry(lab.paths["registry"]).connection() as db:
        row = db.execute(
            "SELECT id,kind,user_id,owner_id,received_at FROM requests WHERE id=?", (receipt_id,)
        ).fetchone()
    operation = lab.verifier._expected_operation("account", row)
    AuthenticatedConfirmationStore(
        lab.paths["authenticated"], lab.auth_key, bundle.DOMAIN).prepare(operation)

    output = io.BytesIO()
    _configure_snapshot_environment(lab, monkeypatch)
    metadata = write_snapshot_archive(output)
    archive_path = tmp_path / "uncertain.sqlite.tar.gz"
    archive_path.write_bytes(output.getvalue())
    restored = _snapshot_paths(archive_path, tmp_path / "uncertain-stores")
    assert set(metadata["stores"]) == set(STORES)
    with monkeypatch.context() as context:
        context.delenv("LIFECYCLE_BACKUP_LOCK_PATH")
        with pytest.raises(bundle.BundleError, match="reconciliation"):
            lab.verifier.verify(restored)


def test_active_writer_prevents_verified_common_boundary(laboratory):
    lab = laboratory
    writer = sqlite3.connect(
        lab.paths["registry"], timeout=0.1, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(bundle.BundleError, match="common SQLite writer fence"):
            bundle.create_bundle(
                lab.settings, lab.root, lab.root / "bundles", lab.keys,
                "test-v1", lab.verifier, lock_timeout=0.02,
            )
    finally:
        writer.rollback()
        writer.close()
    assert list((lab.root / "bundles").iterdir()) == []


def test_missing_common_fence_verifier_is_rejected(laboratory):
    lab = laboratory
    with pytest.raises(bundle.BundleError, match="verifier"):
        bundle.create_bundle(
            lab.settings, lab.root, lab.root / "bundles", lab.keys,
            "test-v1", None,
        )


def test_explicit_verifier_failure_never_marks_consistency_true(laboratory, monkeypatch):
    lab = laboratory
    monkeypatch.setattr(
        lab.verifier, "verify",
        lambda stores: {"verified": False, "scope": sorted(stores)},
    )

    with pytest.raises(bundle.BundleError, match="could not be verified"):
        bundle.create_bundle(
            lab.settings, lab.root, lab.root / "bundles", lab.keys,
            "test-v1", lab.verifier,
        )
    assert list((lab.root / "bundles").iterdir()) == []
