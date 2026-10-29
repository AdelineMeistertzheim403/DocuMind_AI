"""Synthetic-only anti-rollback protocol for lifecycle state and PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import threading
from types import SimpleNamespace
from typing import Callable, Iterator, Mapping, Sequence
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.lifecycle_admissions import AdmissionCoordinator
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore
from backend.lifecycle_holds import ActiveHoldError, HoldStore
from backend.lifecycle_registry import Registry
from ops.testing import lifecycle_lot29_bundle as lot29


LAB_ENV = "PHASE154L210_LAB"
LAB_MARKER = ".phase154-lot210-synthetic-only"
LAB_MARKER_CONTENT = b"documind-phase-15-4-lot-2-10-synthetic-only\n"
AUTHORITY_RELATIVE_PATH = Path("authority") / "state.sqlite"
ARTIFACT_VERSION = 1
MAX_ARTIFACT_BYTES = lot29.MAX_BUNDLE_SIZE
ADMISSION_LIMIT = 5
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DATABASE_NAME = re.compile(r"phase154l210_[a-z0-9_]{1,48}\Z")
_TABLES = (
    "public_registration_quota",
    "lot210_admissions",
    "lot210_operations",
)


class ProtocolError(ValueError):
    """A synthetic protocol precondition or invariant failed."""


class FreshnessUnavailable(ProtocolError):
    """The independent freshness authority could not be consulted."""


class RollbackDetected(ProtocolError):
    """The restored view does not match the independent authority."""


class ReconciliationRequired(ProtocolError):
    """An operation is ambiguous and cannot be replayed automatically."""


class AuthorityResponseLost(ProtocolError):
    """The authority committed a transition but its response was lost."""


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ProtocolError("Canonical UUID required")
    try:
        normalized = str(UUID(value))
    except ValueError:
        raise ProtocolError("Canonical UUID required") from None
    if normalized != value:
        raise ProtocolError("Canonical UUID required")
    return normalized


def _check_lab(root: Path) -> Path:
    if os.environ.get(LAB_ENV) != "isolated" or os.environ.get(lot29.LAB_ENV) != "isolated":
        raise ProtocolError("Both explicit synthetic laboratory guards are required")
    root = Path(root).absolute()
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise ProtocolError("Canonical synthetic laboratory root required")
    marker = root / lot29.LAB_MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != lot29.LAB_MARKER_CONTENT:
        raise ProtocolError("Lot 2.9 synthetic marker missing")
    lot210_marker = root / LAB_MARKER
    if (lot210_marker.is_symlink() or not lot210_marker.is_file()
            or lot210_marker.read_bytes() != LAB_MARKER_CONTENT):
        raise ProtocolError("Lot 2.10 synthetic marker missing")
    for directory in ("authority", "bundles", "quarantine", "work"):
        path = root / directory
        if path.is_symlink() or not path.is_dir() or path.resolve() != path:
            raise ProtocolError(f"Existing synthetic {directory} directory required")
    return root


class CooperativeWriteGate:
    """In-process gate; every participating synthetic writer must hold a lease."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = 0
        self._frozen = False

    @contextmanager
    def writer(self) -> Iterator[None]:
        with self._condition:
            if self._frozen:
                raise ProtocolError("Synthetic writes are frozen for capture")
            self._active += 1
        try:
            yield
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()

    @contextmanager
    def freeze(self) -> Iterator[None]:
        with self._condition:
            if self._frozen or self._active:
                raise ProtocolError("Cooperative writer fence is busy")
            self._frozen = True
        try:
            yield
        finally:
            with self._condition:
                self._frozen = False
                self._condition.notify_all()


class FreshnessAuthority:
    """Append-only synthetic authority, separate from the lot 2.9 bundle.

    The SQLite file is a laboratory stand-in, not an external trust service.
    """

    def __init__(
        self,
        path: Path,
        lab_root: Path,
        key: bytes,
        *,
        timeout: float = 0.25,
    ) -> None:
        self.root = _check_lab(lab_root)
        self.path = Path(path).absolute()
        expected = self.root / AUTHORITY_RELATIVE_PATH
        if (self.path != expected or self.path.resolve() != self.path
                or self.path.is_symlink() or self.path.parent.is_symlink()):
            raise ProtocolError("Authority must use the dedicated synthetic authority path")
        if not isinstance(key, bytes) or len(key) != 32:
            raise ProtocolError("Synthetic authority requires an explicit 256-bit key")
        if not 0 < timeout <= 30:
            raise ProtocolError("Invalid authority timeout")
        self._key = key
        self.timeout = timeout
        self.available = True
        self.drop_next_response = False

    def _connect(self) -> sqlite3.Connection:
        if not self.available:
            raise FreshnessUnavailable("Freshness authority is unavailable")
        if not self.path.is_file() or self.path.is_symlink():
            raise FreshnessUnavailable("Freshness authority store is missing")
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise FreshnessUnavailable("Freshness authority store is not a private regular file")
        connection = sqlite3.connect(
            self.path.as_uri() + "?mode=rw", uri=True, timeout=self.timeout,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(f"PRAGMA busy_timeout={max(1, int(self.timeout * 1000))}")
        return connection

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        if self.path.exists():
            raise ProtocolError("Freshness authority is already initialized")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.resolve() != self.path.parent:
            raise ProtocolError("Non-canonical authority directory")
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.executescript(
                """
                CREATE TABLE authority_head (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    generation INTEGER NOT NULL,
                    admission_count INTEGER NOT NULL,
                    registration_open INTEGER NOT NULL,
                    last_digest TEXT NOT NULL
                );
                CREATE TABLE authority_events (
                    generation INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    operation_id TEXT,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    tag TEXT NOT NULL
                );
                CREATE TABLE authority_operations (
                    operation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    subject_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    result_sha256 TEXT
                );
                CREATE TABLE authority_admissions (
                    sequence INTEGER PRIMARY KEY CHECK(sequence BETWEEN 1 AND 5),
                    operation_id TEXT NOT NULL UNIQUE,
                    subject_sha256 TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL
                );
                PRAGMA user_version=1;
                """
            )
            genesis = _digest(b"documind-lot210-authority-genesis-v1")
            connection.execute(
                "INSERT INTO authority_head VALUES (1,0,0,0,?)", (genesis,))
            os.chmod(self.path, 0o600)
        finally:
            connection.close()

    def _verify_chain(self, db: sqlite3.Connection) -> sqlite3.Row:
        head = db.execute("SELECT * FROM authority_head WHERE id=1").fetchone()
        if (head is None or type(head["generation"]) is not int
                or type(head["admission_count"]) is not int
                or not 0 <= head["admission_count"] <= ADMISSION_LIMIT
                or head["registration_open"] not in (0, 1)
                or not isinstance(head["last_digest"], str)):
            raise FreshnessUnavailable("Authority head is malformed")
        previous = _digest(b"documind-lot210-authority-genesis-v1")
        rows = db.execute("SELECT * FROM authority_events ORDER BY generation").fetchall()
        if len(rows) != head["generation"]:
            raise FreshnessUnavailable("Authority history has a gap or was truncated")
        for expected_generation, row in enumerate(rows, 1):
            envelope = {
                "generation": row["generation"], "event_id": row["event_id"],
                "operation_id": row["operation_id"], "kind": row["kind"],
                "state": row["state"],
                "payload": json.loads(row["payload"])["payload"],
                "previous_digest": row["previous_digest"],
            }
            encoded = _json(envelope)
            expected_digest = _digest(encoded)
            expected_tag = hmac.new(self._key, encoded, hashlib.sha256).hexdigest()
            if (row["generation"] != expected_generation
                    or row["previous_digest"] != previous
                    or _json(envelope) != row["payload"].encode("utf-8")
                    or not hmac.compare_digest(row["digest"], expected_digest)
                    or not hmac.compare_digest(row["tag"], expected_tag)):
                raise FreshnessUnavailable("Authority event chain authentication failed")
            previous = expected_digest
        if not hmac.compare_digest(head["last_digest"], previous):
            raise FreshnessUnavailable("Authority head and event chain differ")
        expected_operations: dict[str, dict[str, object]] = {}
        expected_admissions: dict[str, dict[str, object]] = {}
        expected_registration_open = False
        for row in rows:
            payload = json.loads(row["payload"])["payload"]
            if row["kind"] == "registration_gate":
                expected_registration_open = payload["registration_open"]
                continue
            if row["operation_id"] is None:
                raise FreshnessUnavailable("Authority operation event has no stable identifier")
            current = expected_operations.get(row["operation_id"])
            if row["state"] == "prepared":
                if current is not None:
                    raise FreshnessUnavailable("Authority operation was prepared more than once")
                current = {
                    "operation_id": row["operation_id"], "kind": row["kind"],
                    "subject_sha256": payload["subject_sha256"],
                    "receipt_sha256": payload.get("receipt_sha256", "0" * 64),
                    "state": "prepared", "generation": row["generation"],
                    "result_sha256": None,
                }
                expected_operations[row["operation_id"]] = current
            elif row["kind"] == "admission" and row["state"] == "authorized":
                if current is None or current["state"] != "prepared":
                    raise FreshnessUnavailable("Admission authorization lacks preparation")
                current["state"] = "authorized"
                current["generation"] = row["generation"]
                sequence = payload.get("sequence")
                if type(sequence) is not int or not 1 <= sequence <= ADMISSION_LIMIT:
                    raise FreshnessUnavailable("Authority admission sequence is invalid")
                expected_admissions[row["operation_id"]] = {
                    "sequence": sequence, "operation_id": row["operation_id"],
                    "subject_sha256": current["subject_sha256"], "state": "reserved",
                }
            elif row["state"] == "authorized":
                if current is None or current["state"] != "prepared":
                    raise FreshnessUnavailable("Operation authorization lacks preparation")
                current["state"] = "authorized"
                current["generation"] = row["generation"]
            elif row["state"] == "uncertain":
                if current is None or current["state"] not in {"prepared", "authorized"}:
                    raise FreshnessUnavailable("Uncertain operation has an invalid predecessor")
                current["state"] = "uncertain"
                current["generation"] = row["generation"]
                if row["kind"] == "admission":
                    expected_admissions[row["operation_id"]]["state"] = "uncertain"
            elif row["state"] == "result_recorded":
                if current is None or current["state"] not in {"authorized", "uncertain"}:
                    raise FreshnessUnavailable("Recorded result has no authorized operation")
                current["state"] = "result_recorded"
                current["generation"] = row["generation"]
                current["result_sha256"] = payload["result_sha256"]
                if row["kind"] == "admission":
                    expected_admissions[row["operation_id"]]["state"] = "settled"
            else:
                raise FreshnessUnavailable("Authority event transition is unsupported")
        actual_operations = {
            row["operation_id"]: {
                "operation_id": row["operation_id"], "kind": row["kind"],
                "subject_sha256": row["subject_sha256"],
                "receipt_sha256": row["receipt_sha256"], "state": row["state"],
                "generation": row["generation"], "result_sha256": row["result_sha256"],
            }
            for row in db.execute("SELECT * FROM authority_operations")
        }
        actual_admissions = {
            row["operation_id"]: {
                "sequence": row["sequence"], "operation_id": row["operation_id"],
                "subject_sha256": row["subject_sha256"], "state": row["state"],
            }
            for row in db.execute("SELECT * FROM authority_admissions")
        }
        if (actual_operations != expected_operations
                or actual_admissions != expected_admissions
                or bool(head["registration_open"]) != expected_registration_open):
            raise FreshnessUnavailable("Authority materialized state differs from its append-only history")
        count = db.execute("SELECT COUNT(*) FROM authority_admissions").fetchone()[0]
        sequences = [row[0] for row in db.execute(
            "SELECT sequence FROM authority_admissions ORDER BY sequence")]
        if count != head["admission_count"] or sequences != list(range(1, count + 1)):
            raise FreshnessUnavailable("Authority admission sequence is incomplete")
        return head

    @staticmethod
    def _operation_row(db: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
        return db.execute(
            "SELECT * FROM authority_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()

    def _append(
        self,
        db: sqlite3.Connection,
        head: sqlite3.Row,
        *,
        operation_id: str | None,
        kind: str,
        state: str,
        payload: Mapping[str, object],
    ) -> tuple[int, str]:
        generation = head["generation"] + 1
        event_id = str(UUID(bytes=os.urandom(16), version=4))
        envelope = {
            "generation": generation, "event_id": event_id,
            "operation_id": operation_id, "kind": kind, "state": state,
            "payload": dict(payload), "previous_digest": head["last_digest"],
        }
        encoded = _json(envelope)
        digest = _digest(encoded)
        tag = hmac.new(self._key, encoded, hashlib.sha256).hexdigest()
        db.execute(
            "INSERT INTO authority_events VALUES (?,?,?,?,?,?,?,?,?)",
            (generation, event_id, operation_id, kind, state, encoded.decode(),
             head["last_digest"], digest, tag),
        )
        return generation, digest

    def _commit(self, db: sqlite3.Connection) -> None:
        db.commit()
        if self.drop_next_response:
            self.drop_next_response = False
            raise AuthorityResponseLost("Authority committed; response intentionally lost")

    def _snapshot(self, db: sqlite3.Connection) -> dict[str, object]:
        head = self._verify_chain(db)
        operations = [
            {
                "operation_id": row["operation_id"], "kind": row["kind"],
                "subject_sha256": row["subject_sha256"],
                "receipt_sha256": row["receipt_sha256"], "state": row["state"],
                "generation": row["generation"], "result_sha256": row["result_sha256"],
            }
            for row in db.execute("SELECT * FROM authority_operations ORDER BY operation_id")
        ]
        admissions = [
            {
                "sequence": row["sequence"], "operation_id": row["operation_id"],
                "subject_sha256": row["subject_sha256"], "state": row["state"],
            }
            for row in db.execute("SELECT * FROM authority_admissions ORDER BY sequence")
        ]
        return {
            "generation": head["generation"], "admission_count": head["admission_count"],
            "registration_open": bool(head["registration_open"]),
            "head_digest": head["last_digest"], "operations": operations,
            "admissions": admissions,
        }

    def snapshot(self) -> dict[str, object]:
        try:
            with self._session() as db:
                return self._snapshot(db)
        except sqlite3.Error as error:
            raise FreshnessUnavailable(f"Authority read failed: {type(error).__name__}") from None

    @contextmanager
    def capture_fence(self) -> Iterator[dict[str, object]]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield self._snapshot(db)
            db.commit()
        except sqlite3.Error as error:
            db.rollback()
            raise FreshnessUnavailable(
                f"Authority capture fence failed: {type(error).__name__}"
            ) from None
        finally:
            db.close()

    def set_registration_open(self, opened: bool) -> None:
        if type(opened) is not bool:
            raise ProtocolError("Registration state must be explicit")
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                if bool(head["registration_open"]) == opened:
                    db.rollback()
                    return
                generation, digest = self._append(
                    db, head, operation_id=None, kind="registration_gate",
                    state="open" if opened else "closed",
                    payload={"registration_open": opened},
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,registration_open=?,last_digest=? WHERE id=1",
                    (generation, int(opened), digest),
                )
                self._commit(db)
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority gate transition failed: {type(error).__name__}"
            ) from None

    def prepare(
        self,
        operation_id: str,
        kind: str,
        subject: str,
        receipt_sha256: str,
    ) -> dict[str, object]:
        operation_id, subject = _canonical_uuid(operation_id), _canonical_uuid(subject)
        if kind not in {"account_deactivation", "document_erasure", "hold_release"}:
            raise ProtocolError("Unsupported synthetic critical operation")
        if not isinstance(receipt_sha256, str) or not _SHA256.fullmatch(receipt_sha256):
            raise ProtocolError("Receipt fingerprint required")
        subject_digest = _digest(subject.encode())
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                existing = self._operation_row(db, operation_id)
                if existing:
                    if (existing["kind"] != kind
                            or existing["subject_sha256"] != subject_digest
                            or existing["receipt_sha256"] != receipt_sha256):
                        raise ProtocolError("Conflicting operation identity")
                    db.rollback()
                    return dict(existing)
                generation, digest = self._append(
                    db, head, operation_id=operation_id, kind=kind, state="prepared",
                    payload={"subject_sha256": subject_digest, "receipt_sha256": receipt_sha256},
                )
                db.execute(
                    "INSERT INTO authority_operations VALUES (?,?,?,?,?,?,NULL)",
                    (operation_id, kind, subject_digest, receipt_sha256, "prepared", generation),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,last_digest=? WHERE id=1",
                    (generation, digest),
                )
                self._commit(db)
                return dict(self._operation_row(db, operation_id))
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority prepare failed: {type(error).__name__}"
            ) from None

    def authorize(self, operation_id: str) -> dict[str, object]:
        operation_id = _canonical_uuid(operation_id)
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                if row is None:
                    raise ProtocolError("Operation was not prepared")
                if row["state"] != "prepared":
                    raise ReconciliationRequired(
                        "Authorization was already consumed or operation is uncertain")
                generation, digest = self._append(
                    db, head, operation_id=operation_id, kind=row["kind"],
                    state="authorized",
                    payload={"receipt_sha256": row["receipt_sha256"]},
                )
                db.execute(
                    "UPDATE authority_operations SET state='authorized',generation=? WHERE operation_id=?",
                    (generation, operation_id),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,last_digest=? WHERE id=1",
                    (generation, digest),
                )
                self._commit(db)
                return dict(self._operation_row(db, operation_id))
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority authorization failed: {type(error).__name__}"
            ) from None

    def reserve_admission(self, operation_id: str, user_id: str) -> dict[str, object]:
        operation_id, user_id = _canonical_uuid(operation_id), _canonical_uuid(user_id)
        subject_digest = _digest(user_id.encode())
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                existing = self._operation_row(db, operation_id)
                if existing:
                    if (existing["kind"] != "admission"
                            or existing["subject_sha256"] != subject_digest):
                        raise ProtocolError("Conflicting admission operation identity")
                    admission = db.execute(
                        "SELECT sequence FROM authority_admissions WHERE operation_id=?",
                        (operation_id,),
                    ).fetchone()
                    if admission is None:
                        raise FreshnessUnavailable("Admission operation has no reserved sequence")
                    db.rollback()
                    return {**dict(existing), "sequence": admission["sequence"]}
                if not head["registration_open"]:
                    raise ProtocolError("Independent authority keeps registration closed")
                if db.execute(
                    "SELECT 1 FROM authority_admissions WHERE subject_sha256=?",
                    (subject_digest,),
                ).fetchone():
                    raise ProtocolError("Previously admitted identity cannot be reused")
                if head["admission_count"] >= ADMISSION_LIMIT:
                    raise ProtocolError("Cumulative admission limit reached")
                sequence = head["admission_count"] + 1
                prepared_generation, prepared_digest = self._append(
                    db, head, operation_id=operation_id, kind="admission",
                    state="prepared",
                    payload={"sequence": sequence, "subject_sha256": subject_digest},
                )
                db.execute(
                    "INSERT INTO authority_operations VALUES (?,?,?,?,?,?,NULL)",
                    (operation_id, "admission", subject_digest, "0" * 64,
                     "prepared", prepared_generation),
                )
                prepared_head = dict(head)
                prepared_head["generation"] = prepared_generation
                prepared_head["last_digest"] = prepared_digest
                authorized_generation, authorized_digest = self._append(
                    db, prepared_head, operation_id=operation_id, kind="admission",
                    state="authorized",
                    payload={"sequence": sequence, "subject_sha256": subject_digest},
                )
                db.execute(
                    "UPDATE authority_operations SET state='authorized',generation=? WHERE operation_id=?",
                    (authorized_generation, operation_id),
                )
                db.execute(
                    "INSERT INTO authority_admissions VALUES (?,?,?,'reserved')",
                    (sequence, operation_id, subject_digest),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,admission_count=?,last_digest=? WHERE id=1",
                    (authorized_generation, sequence, authorized_digest),
                )
                self._commit(db)
                result = dict(self._operation_row(db, operation_id))
                result["sequence"] = sequence
                return result
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority admission reservation failed: {type(error).__name__}"
            ) from None

    def record_result(self, operation_id: str, result_sha256: str) -> dict[str, object]:
        operation_id = _canonical_uuid(operation_id)
        if not isinstance(result_sha256, str) or not _SHA256.fullmatch(result_sha256):
            raise ProtocolError("Result fingerprint required")
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                if row is None:
                    raise ProtocolError("Operation is unknown")
                if row["state"] == "result_recorded":
                    if row["result_sha256"] != result_sha256:
                        raise ProtocolError("Conflicting operation result")
                    db.rollback()
                    return dict(row)
                if row["state"] != "authorized":
                    raise ReconciliationRequired("Only an authorized operation can record a result")
                generation, digest = self._append(
                    db, head, operation_id=operation_id, kind=row["kind"],
                    state="result_recorded",
                    payload={"result_sha256": result_sha256},
                )
                db.execute(
                    "UPDATE authority_operations SET state='result_recorded',generation=?,"
                    "result_sha256=? WHERE operation_id=?",
                    (generation, result_sha256, operation_id),
                )
                db.execute(
                    "UPDATE authority_admissions SET state='settled' WHERE operation_id=?",
                    (operation_id,),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,last_digest=? WHERE id=1",
                    (generation, digest),
                )
                self._commit(db)
                return dict(self._operation_row(db, operation_id))
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority result recording failed: {type(error).__name__}"
            ) from None

    def mark_uncertain(self, operation_id: str) -> dict[str, object]:
        operation_id = _canonical_uuid(operation_id)
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                if row is None:
                    raise ProtocolError("Operation is unknown")
                if row["state"] == "uncertain":
                    db.rollback()
                    return dict(row)
                if row["state"] not in {"prepared", "authorized"}:
                    raise ProtocolError("Only an unfinished operation can become uncertain")
                generation, digest = self._append(
                    db, head, operation_id=operation_id, kind=row["kind"],
                    state="uncertain",
                    payload={"previous_state": row["state"]},
                )
                db.execute(
                    "UPDATE authority_operations SET state='uncertain',generation=? WHERE operation_id=?",
                    (generation, operation_id),
                )
                db.execute(
                    "UPDATE authority_admissions SET state='uncertain' WHERE operation_id=?",
                    (operation_id,),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,last_digest=? WHERE id=1",
                    (generation, digest),
                )
                self._commit(db)
                return dict(self._operation_row(db, operation_id))
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority uncertainty record failed: {type(error).__name__}"
            ) from None

    def reconcile_applied(
        self, operation_id: str, result_sha256: str, evidence_sha256: str,
    ) -> dict[str, object]:
        operation_id = _canonical_uuid(operation_id)
        if not all(isinstance(value, str) and _SHA256.fullmatch(value)
                   for value in (result_sha256, evidence_sha256)):
            raise ProtocolError("Explicit reconciliation evidence fingerprints required")
        try:
            with self._session() as db:
                db.execute("BEGIN IMMEDIATE")
                head = self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                if row is None or row["state"] != "uncertain":
                    raise ReconciliationRequired("Operation is not awaiting reconciliation")
                generation, digest = self._append(
                    db, head, operation_id=operation_id, kind=row["kind"],
                    state="result_recorded",
                    payload={"result_sha256": result_sha256,
                             "reconciliation_evidence_sha256": evidence_sha256},
                )
                db.execute(
                    "UPDATE authority_operations SET state='result_recorded',generation=?,"
                    "result_sha256=? WHERE operation_id=?",
                    (generation, result_sha256, operation_id),
                )
                db.execute(
                    "UPDATE authority_admissions SET state='settled' WHERE operation_id=?",
                    (operation_id,),
                )
                db.execute(
                    "UPDATE authority_head SET generation=?,last_digest=? WHERE id=1",
                    (generation, digest),
                )
                self._commit(db)
                return dict(self._operation_row(db, operation_id))
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority reconciliation failed: {type(error).__name__}"
            ) from None

    def verify_authorization(self, operation_id: str, generation: int) -> bool:
        operation_id = _canonical_uuid(operation_id)
        if type(generation) is not int or generation < 1:
            return False
        try:
            with self._session() as db:
                self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                event = db.execute(
                    "SELECT state,generation FROM authority_events "
                    "WHERE operation_id=? AND state='authorized' ORDER BY generation DESC LIMIT 1",
                    (operation_id,),
                ).fetchone()
                return bool(
                    row and row["state"] == "authorized" and row["generation"] == generation
                    and event and event["generation"] == generation
                )
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority authorization verification failed: {type(error).__name__}"
            ) from None

    def operation(self, operation_id: str) -> dict[str, object] | None:
        operation_id = _canonical_uuid(operation_id)
        try:
            with self._session() as db:
                self._verify_chain(db)
                row = self._operation_row(db, operation_id)
                return dict(row) if row else None
        except sqlite3.Error as error:
            raise FreshnessUnavailable(
                f"Authority operation read failed: {type(error).__name__}"
            ) from None


class SyntheticPostgres:
    """Adapter restricted to explicit loopback PostgreSQL test databases."""

    def __init__(self, dsn: str, *, lock_timeout_ms: int = 250) -> None:
        if os.environ.get(LAB_ENV) != "isolated":
            raise ProtocolError("Synthetic PostgreSQL guard is required")
        if not isinstance(dsn, str) or not 0 < lock_timeout_ms <= 30000:
            raise ProtocolError("Explicit synthetic PostgreSQL DSN and bounded timeout required")
        try:
            from sqlalchemy.engine import make_url
            url = make_url(dsn)
        except Exception as error:
            raise ProtocolError(f"Invalid synthetic PostgreSQL DSN: {type(error).__name__}") from None
        if (url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}
                or not url.database or not _DATABASE_NAME.fullmatch(url.database)):
            raise ProtocolError("Only a loopback phase154l210 PostgreSQL database is permitted")
        self.dsn = dsn
        self.database = url.database
        self.lock_timeout_ms = lock_timeout_ms

    def _connect(self):
        try:
            import psycopg
        except ImportError:
            raise ProtocolError("Declared psycopg dependency is required for PostgreSQL lab tests") from None
        return psycopg.connect(self.dsn)

    def initialize(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE public_registration_quota (
                        id text PRIMARY KEY CHECK(id='public'),
                        issued_count integer NOT NULL CHECK(issued_count BETWEEN 0 AND 5),
                        closed boolean NOT NULL
                    );
                    INSERT INTO public_registration_quota VALUES ('public',0,true);
                    CREATE TABLE lot210_admissions (
                        sequence integer PRIMARY KEY CHECK(sequence BETWEEN 1 AND 5),
                        operation_id uuid NOT NULL UNIQUE,
                        subject_sha256 text NOT NULL UNIQUE,
                        state text NOT NULL CHECK(state IN ('reserved','settled','uncertain'))
                    );
                    CREATE TABLE lot210_operations (
                        operation_id uuid PRIMARY KEY,
                        kind text NOT NULL,
                        target uuid NOT NULL,
                        receipt_sha256 text NOT NULL,
                        state text NOT NULL CHECK(state IN
                            ('prepared','authorized','result_recorded','uncertain')),
                        authority_generation integer NOT NULL,
                        result_sha256 text
                    );
                """)

    def set_registration_open(self, opened: bool) -> None:
        if type(opened) is not bool:
            raise ProtocolError("Synthetic PostgreSQL registration state must be explicit")
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE public_registration_quota SET closed=%s "
                                   "WHERE id='public'", (not opened,))
                    if cursor.rowcount != 1:
                        raise ProtocolError("Synthetic PostgreSQL quota row is missing")

    @contextmanager
    def capture_fence(self) -> Iterator[object]:
        connection = self._connect()
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('lock_timeout', %s, true)",
                                   (f"{self.lock_timeout_ms}ms",))
                    cursor.execute("LOCK TABLE public_registration_quota, "
                                   "lot210_admissions, lot210_operations IN SHARE MODE")
                    cursor.execute("SELECT current_database(), txid_current_snapshot()::text, "
                                   "pg_current_wal_lsn()::text")
                    identity = cursor.fetchone()
                    if identity[0] != self.database:
                        raise ProtocolError("Connected PostgreSQL database identity changed")
                    yield connection
        except ProtocolError:
            raise
        except Exception as error:
            raise ProtocolError(
                f"PostgreSQL writer fence failed: {type(error).__name__}"
            ) from None
        finally:
            connection.close()

    @staticmethod
    def read_state(connection: object) -> dict[str, object]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), txid_current_snapshot()::text, "
                           "pg_current_wal_lsn()::text")
            database, transaction_snapshot, wal_lsn = cursor.fetchone()
            cursor.execute("SELECT id,issued_count,closed FROM public_registration_quota")
            quota = cursor.fetchall()
            cursor.execute("SELECT sequence,operation_id::text,subject_sha256,state "
                           "FROM lot210_admissions ORDER BY sequence")
            admissions = cursor.fetchall()
            cursor.execute("SELECT operation_id::text,kind,target::text,receipt_sha256,state,"
                           "authority_generation,result_sha256 FROM lot210_operations "
                           "ORDER BY operation_id")
            operations = cursor.fetchall()
        if len(quota) != 1 or quota[0][0] != "public":
            raise ProtocolError("Synthetic PostgreSQL quota row is missing or ambiguous")
        return {
            "database": database, "transaction_snapshot": transaction_snapshot,
            "wal_lsn": wal_lsn,
            "quota": {"id": quota[0][0], "issued_count": quota[0][1], "closed": quota[0][2]},
            "admissions": [
                {"sequence": row[0], "operation_id": row[1],
                 "subject_sha256": row[2], "state": row[3]}
                for row in admissions
            ],
            "operations": [
                {"operation_id": row[0], "kind": row[1], "target": row[2],
                 "receipt_sha256": row[3], "state": row[4],
                 "generation": row[5], "result_sha256": row[6]}
                for row in operations
            ],
        }

    def apply_admission(self, operation_id: str, user_id: str, sequence: int) -> None:
        operation_id, user_id = _canonical_uuid(operation_id), _canonical_uuid(user_id)
        subject_digest = _digest(user_id.encode())
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT issued_count,closed FROM public_registration_quota "
                                   "WHERE id='public' FOR UPDATE")
                    quota = cursor.fetchone()
                    if quota is None or quota[1] or quota[0] != sequence - 1:
                        raise ProtocolError("PostgreSQL admission count or closure diverges")
                    cursor.execute("SELECT sequence,subject_sha256 FROM lot210_admissions "
                                   "WHERE operation_id=%s", (operation_id,))
                    existing = cursor.fetchone()
                    if existing:
                        if existing != (sequence, subject_digest):
                            raise ProtocolError("Conflicting PostgreSQL admission replay")
                        return
                    cursor.execute("INSERT INTO lot210_admissions VALUES (%s,%s,%s,'reserved')",
                                   (sequence, operation_id, subject_digest))
                    cursor.execute("UPDATE public_registration_quota SET issued_count=%s "
                                   "WHERE id='public'", (sequence,))

    def settle_admission(self, operation_id: str, sequence: int) -> None:
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE lot210_admissions SET state='settled' "
                                   "WHERE operation_id=%s AND sequence=%s "
                                   "AND state IN ('reserved','settled')",
                                   (_canonical_uuid(operation_id), sequence))
                    if cursor.rowcount != 1:
                        raise ReconciliationRequired("PostgreSQL admission cannot be settled")

    def mark_admission_uncertain(self, operation_id: str, sequence: int) -> bool:
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE lot210_admissions SET state='uncertain' "
                                   "WHERE operation_id=%s AND sequence=%s "
                                   "AND state IN ('reserved','uncertain')",
                                   (_canonical_uuid(operation_id), sequence))
                    return cursor.rowcount == 1

    def put_operation(
        self,
        operation: Mapping[str, str],
        state: str,
        generation: int,
        result_sha256: str | None = None,
    ) -> None:
        if state not in {"prepared", "authorized", "result_recorded", "uncertain"}:
            raise ProtocolError("Invalid PostgreSQL operation state")
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT kind,target::text,receipt_sha256,state,"
                                   "authority_generation,result_sha256 FROM lot210_operations "
                                   "WHERE operation_id=%s FOR UPDATE",
                                   (operation["id"],))
                    existing = cursor.fetchone()
                    identity = (operation["type"], operation["target"],
                                operation["receipt_sha256"])
                    if existing is None:
                        if state != "prepared":
                            raise ReconciliationRequired("PostgreSQL operation has no prepared row")
                        cursor.execute("INSERT INTO lot210_operations VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                       (operation["id"], *identity, state, generation, result_sha256))
                        return
                    if existing[:3] != identity:
                        raise ProtocolError("PostgreSQL operation identity conflicts")
                    allowed = {
                        "prepared": {"authorized", "uncertain"},
                        "authorized": {"result_recorded", "uncertain"},
                        "uncertain": {"result_recorded"},
                    }
                    if existing[3] == state:
                        if (existing[4] != generation or
                                existing[5] != result_sha256):
                            raise ProtocolError("PostgreSQL operation state conflicts")
                        return
                    if state not in allowed.get(existing[3], set()) or generation <= existing[4]:
                        raise ReconciliationRequired("PostgreSQL operation transition is not monotone")
                    cursor.execute("UPDATE lot210_operations SET state=%s,authority_generation=%s,"
                                   "result_sha256=%s WHERE operation_id=%s",
                                   (state, generation, result_sha256, operation["id"]))

    def restore_quarantine(self, snapshot: Mapping[str, object]) -> dict[str, object]:
        if not re.fullmatch(r"phase154l210_restore_[a-z0-9_]{1,40}", self.database):
            raise ProtocolError("PostgreSQL restoration is restricted to a new quarantine database")
        _validate_postgres_snapshot(snapshot)
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("LOCK TABLE public_registration_quota, "
                                   "lot210_admissions, lot210_operations IN ACCESS EXCLUSIVE MODE")
                    cursor.execute("DELETE FROM lot210_admissions")
                    cursor.execute("DELETE FROM lot210_operations")
                    cursor.execute("DELETE FROM public_registration_quota")
                    quota = snapshot["quota"]
                    cursor.execute("INSERT INTO public_registration_quota VALUES (%s,%s,%s)",
                                   (quota["id"], quota["issued_count"], True))
                    for row in snapshot["admissions"]:
                        cursor.execute("INSERT INTO lot210_admissions VALUES (%s,%s,%s,%s)",
                                       (row["sequence"], row["operation_id"],
                                        row["subject_sha256"], row["state"]))
                    for row in snapshot["operations"]:
                        cursor.execute("INSERT INTO lot210_operations VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                       (row["operation_id"], row["kind"], row["target"],
                                        row["receipt_sha256"], row["state"], row["generation"],
                                        row["result_sha256"]))
        return self.read_state_from_new_connection()

    def read_state_from_new_connection(self) -> dict[str, object]:
        with self._connect() as connection:
            return self.read_state(connection)


def _validate_postgres_snapshot(snapshot: Mapping[str, object]) -> None:
    if (not isinstance(snapshot, Mapping)
            or set(snapshot) != {"database", "transaction_snapshot", "wal_lsn",
                                 "quota", "admissions", "operations"}):
        raise ProtocolError("Malformed synthetic PostgreSQL snapshot")
    quota = snapshot["quota"]
    if (not isinstance(quota, dict) or set(quota) != {"id", "issued_count", "closed"}
            or quota["id"] != "public" or type(quota["issued_count"]) is not int
            or not 0 <= quota["issued_count"] <= ADMISSION_LIMIT
            or type(quota["closed"]) is not bool):
        raise ProtocolError("Invalid synthetic PostgreSQL quota snapshot")
    if (not isinstance(snapshot["database"], str)
            or not _DATABASE_NAME.fullmatch(snapshot["database"])
            or not isinstance(snapshot["transaction_snapshot"], str)
            or not isinstance(snapshot["wal_lsn"], str)
            or not isinstance(snapshot["admissions"], list)
            or not isinstance(snapshot["operations"], list)):
        raise ProtocolError("Invalid PostgreSQL snapshot boundary")
    for row in snapshot["admissions"]:
        if (not isinstance(row, dict)
                or set(row) != {"sequence", "operation_id", "subject_sha256", "state"}
                or type(row["sequence"]) is not int
                or not 1 <= row["sequence"] <= ADMISSION_LIMIT
                or not isinstance(row["operation_id"], str)
                or not isinstance(row["subject_sha256"], str)
                or not _SHA256.fullmatch(row["subject_sha256"])
                or row["state"] not in {"reserved", "settled", "uncertain"}):
            raise ProtocolError("Malformed PostgreSQL admission snapshot")
        _canonical_uuid(row["operation_id"])
    if [row["sequence"] for row in snapshot["admissions"]] != list(
            range(1, quota["issued_count"] + 1)):
        raise RollbackDetected("PostgreSQL quota and admissions counts differ")
    for row in snapshot["operations"]:
        if (not isinstance(row, dict) or set(row) != {
                "operation_id", "kind", "target", "receipt_sha256", "state",
                "generation", "result_sha256"}
                or row["kind"] not in {
                    "account_deactivation", "document_erasure", "hold_release"}
                or row["state"] not in {
                    "prepared", "authorized", "result_recorded", "uncertain"}
                or type(row["generation"]) is not int or row["generation"] < 1
                or not isinstance(row["receipt_sha256"], str)
                or not _SHA256.fullmatch(row["receipt_sha256"])
                or (row["result_sha256"] is not None
                    and (not isinstance(row["result_sha256"], str)
                         or not _SHA256.fullmatch(row["result_sha256"])))):
            raise ProtocolError("Malformed PostgreSQL operation snapshot")
        _canonical_uuid(row["operation_id"])
        _canonical_uuid(row["target"])


def _validate_cross_store_state(
    postgres: Mapping[str, object],
    authority: Mapping[str, object],
    sqlite_admissions: Sequence[Mapping[str, object]],
) -> None:
    _validate_postgres_snapshot(postgres)
    if (postgres["quota"]["issued_count"] != authority["admission_count"]
            or len(sqlite_admissions) != authority["admission_count"]):
        raise RollbackDetected("PostgreSQL, SQLite witness, and authority counts differ")
    postgres_admissions = postgres["admissions"]
    authority_admissions = authority["admissions"]
    expected_authority_admissions = [
        {"sequence": entry["sequence"], "operation_id": entry["operation_id"],
         "subject_sha256": entry["subject_sha256"], "state": entry["state"]}
        for entry in authority_admissions
    ]
    if postgres_admissions != expected_authority_admissions:
        raise RollbackDetected("PostgreSQL admissions differ from the freshness authority")
    for sequence, entry in enumerate(sqlite_admissions, 1):
        if (entry.get("sequence") != sequence
                or _digest(entry["user_id"].encode()) != authority_admissions[sequence - 1]["subject_sha256"]):
            raise RollbackDetected("SQLite witness and authority admission identities differ")

    authority_operations = [
        {"operation_id": row["operation_id"], "kind": row["kind"],
         "target": row["subject_sha256"], "receipt_sha256": row["receipt_sha256"],
         "state": row["state"], "generation": row["generation"],
         "result_sha256": row["result_sha256"]}
        for row in authority["operations"] if row["kind"] != "admission"
    ]
    postgres_operations = [
        {**row, "target": _digest(row["target"].encode())}
        for row in postgres["operations"]
    ]
    if postgres_operations != authority_operations:
        raise RollbackDetected("PostgreSQL operation journal differs from the authority")


def _verify_sqlite_operations(
    settings: object,
    postgres: Mapping[str, object],
    authority: Mapping[str, object],
    verifier: lot29.SyntheticLifecycleConsistencyVerifier,
) -> None:
    path = getattr(
        settings, lot29.COMPONENTS["authenticated"]["setting"], None)
    if path is None:
        raise RollbackDetected("Authenticated SQLite store is not configured")
    authenticated = AuthenticatedConfirmationStore(
        path, verifier.authentication_key, lot29.DOMAIN)
    authority_operations = {
        row["operation_id"]: row for row in authority["operations"]
        if row["kind"] != "admission"
    }
    postgres_operations = {
        row["operation_id"]: row for row in postgres["operations"]
    }
    if set(authority_operations) != set(postgres_operations):
        raise RollbackDetected("PostgreSQL and authority operation identifiers differ")
    with authenticated.store.connection() as db:
        local_ids = {row[0] for row in db.execute(
            "SELECT DISTINCT operation FROM synthetic_transitions")}
    authenticated_operation_ids = {
        identifier for identifier, row in authority_operations.items()
        if row["kind"] != "hold_release"
    }
    if local_ids != authenticated_operation_ids:
        raise RollbackDetected("Authenticated SQLite operation history differs from the authority")
    expected_local_state = {
        "prepared": "confirmed",
        "authorized": "authorized",
        "result_recorded": "result_recorded",
        "uncertain": {"confirmed", "authorized"},
    }
    for operation_id, authority_row in authority_operations.items():
        postgres_row = postgres_operations[operation_id]
        if (_digest(postgres_row["target"].encode()) != authority_row["subject_sha256"]
                or postgres_row["kind"] != authority_row["kind"]
                or postgres_row["receipt_sha256"] != authority_row["receipt_sha256"]):
            raise RollbackDetected("Operation identity differs across PostgreSQL and authority")
        if authority_row["kind"] == "hold_release":
            continue
        operation = {
            "id": operation_id, "type": authority_row["kind"],
            "target": postgres_row["target"],
            "receipt_sha256": authority_row["receipt_sha256"],
        }
        state = authenticated.verify(operation)
        expected = expected_local_state[authority_row["state"]]
        matches = state in expected if isinstance(expected, set) else state == expected
        if not matches:
            raise RollbackDetected("Authenticated SQLite operation state is stale or ambiguous")
    hold_path = getattr(settings, lot29.COMPONENTS["holds"]["setting"], None)
    if hold_path is None:
        raise RollbackDetected("A20 hold store is not configured")
    authenticated_path = getattr(
        settings, lot29.COMPONENTS["authenticated"]["setting"])
    hold_auth = AuthenticatedConfirmationStore(
        authenticated_path, verifier.authentication_key, lot29.DOMAIN)
    validation_directory: Path | None = None
    if Path(hold_path).parent == Path(authenticated_path).parent:
        work_directory = Path(hold_path).parent.parent.parent / "work"
        validation_directory = work_directory / ("hold-validation-" + uuid4().hex)
        validation_directory.mkdir(mode=0o700)
    try:
        if validation_directory is not None:
            hold_path = validation_directory / Path(hold_path).name
            shutil.copyfile(
                getattr(settings, lot29.COMPONENTS["holds"]["setting"]), hold_path)
            if os.name == "posix":
                os.chmod(hold_path, 0o600)
        holds = HoldStore(hold_path, hold_auth)
        with holds.store.connection() as db:
            hold_snapshots = holds._snapshots(db)
    finally:
        if validation_directory is not None:
            shutil.rmtree(validation_directory)
    hold_auth.verify_holds(hold_snapshots)
    for operation_id, authority_row in authority_operations.items():
        if authority_row["kind"] != "hold_release":
            continue
        target = postgres_operations[operation_id]["target"]
        snapshot = hold_snapshots.get(target)
        if snapshot is None:
            raise RollbackDetected("A20 release target is absent from the hold store")
        released = snapshot["release"]
        if authority_row["state"] == "result_recorded":
            if (released is None
                    or released["evidence_sha256"] != authority_row["receipt_sha256"]):
                raise RollbackDetected("A20 release evidence differs from the authority")
        elif authority_row["state"] == "prepared":
            if released is not None:
                raise RollbackDetected("A20 hold was released before authorization")
        elif authority_row["state"] == "authorized" and released is not None:
            raise RollbackDetected("A20 release effect lacks an authority result")


class LifecycleOperationProtocol:
    def __init__(
        self,
        authority: FreshnessAuthority,
        postgres: SyntheticPostgres,
        authenticated: AuthenticatedConfirmationStore,
        holds: HoldStore,
        scopes_for: Callable[[Mapping[str, str]], Sequence[tuple[str, str]]],
        write_gate: CooperativeWriteGate,
    ) -> None:
        self.authority = authority
        self.postgres = postgres
        self.authenticated = authenticated
        self.holds = holds
        self.scopes_for = scopes_for
        self.write_gate = write_gate

    def _identity(self, operation: Mapping[str, str]) -> dict[str, str]:
        if operation.get("type") != "hold_release":
            return self.authenticated._identity(dict(operation))
        if not isinstance(operation, dict) or set(operation) != {
                "id", "type", "target", "receipt_sha256"}:
            raise ProtocolError("Incomplete A20 release operation")
        operation_id = _canonical_uuid(operation["id"])
        target = _canonical_uuid(operation["target"])
        if (operation_id != operation["id"] or target != operation["target"]
                or not isinstance(operation["receipt_sha256"], str)
                or not _SHA256.fullmatch(operation["receipt_sha256"])):
            raise ProtocolError("Invalid A20 release identity or evidence fingerprint")
        return {
            "id": operation_id, "type": "hold_release", "target": target,
            "receipt_sha256": operation["receipt_sha256"],
        }

    def _verify_local_prerequisites(self, operation: Mapping[str, str]) -> None:
        if operation["type"] == "hold_release":
            with self.holds.store.connection() as db:
                snapshots = self.holds._snapshots(db)
            self.authenticated.verify_holds(snapshots)
            target = snapshots.get(operation["target"])
            if target is None or target["release"] is not None:
                raise ReconciliationRequired("A20 release target is missing or already released")
            allowed_scopes = set(self.scopes_for(operation))
            own_scope = (target["hold"]["scope_kind"], target["hold"]["scope_id"])
            if own_scope not in allowed_scopes:
                raise ProtocolError("A20 release scope differs from its authenticated hold")
            for identifier, snapshot in snapshots.items():
                if identifier == operation["target"] or snapshot["release"] is not None:
                    continue
                scope = (snapshot["hold"]["scope_kind"], snapshot["hold"]["scope_id"])
                if scope in allowed_scopes:
                    raise ActiveHoldError("Another A20 hold blocks the release")
            return
        state = self.authenticated.verify(dict(operation))
        if state not in {"confirmed", "authorized", "result_recorded"}:
            raise ReconciliationRequired("Authenticated local confirmation is missing")
        try:
            with self.holds.guard(self.scopes_for(operation)):
                pass
        except ActiveHoldError:
            raise ProtocolError("A20 hold blocks the critical operation") from None

    def prepare(self, operation: Mapping[str, str]) -> dict[str, object]:
        with self.write_gate.writer():
            identity = self._identity(operation)
            self._verify_local_prerequisites(identity)
            result = self.authority.prepare(
                identity["id"], identity["type"], identity["target"],
                identity["receipt_sha256"],
            )
            if result["state"] != "prepared":
                raise ReconciliationRequired("Prepared operation already advanced")
            self.postgres.put_operation(identity, "prepared", result["generation"])
            return result

    def authorize(self, operation: Mapping[str, str]) -> dict[str, object]:
        with self.write_gate.writer():
            identity = self._identity(operation)
            self._verify_local_prerequisites(identity)
            prepared = self.authority.operation(identity["id"])
            if prepared is None or prepared["state"] != "prepared":
                raise ReconciliationRequired("Operation is not in a fresh prepared state")
            result = self.authority.authorize(identity["id"])
            self.postgres.put_operation(identity, "authorized", result["generation"])
            if identity["type"] != "hold_release":
                self.authenticated.authorize_once(identity)
                local_verified = self.authenticated.verify(identity) == "authorized"
            else:
                local_verified = True
            if (not local_verified
                    or not self.authority.verify_authorization(identity["id"], result["generation"])):
                raise ReconciliationRequired("Independent authorization could not be verified")
            return result

    def record_result(
        self, operation: Mapping[str, str], result_sha256: str,
    ) -> dict[str, object]:
        with self.write_gate.writer():
            identity = self._identity(operation)
            current = self.authority.operation(identity["id"])
            if (current and current["state"] == "result_recorded"
                    and current["result_sha256"] == result_sha256):
                self.postgres.put_operation(
                    identity, "result_recorded", current["generation"], result_sha256)
                if identity["type"] != "hold_release":
                    self.authenticated.record_result(identity)
                return current
            if (identity["type"] != "hold_release"
                    and self.authenticated.verify(identity) != "authorized"):
                raise ReconciliationRequired("Local operation is not authorized")
            if identity["type"] == "hold_release" and (
                    current is None or current["state"] != "authorized"):
                raise ReconciliationRequired("A20 release is not independently authorized")
            result = self.authority.record_result(identity["id"], result_sha256)
            self.postgres.put_operation(
                identity, "result_recorded", result["generation"], result_sha256)
            if identity["type"] != "hold_release":
                self.authenticated.record_result(identity)
            return result

    def mark_uncertain(self, operation_id: str) -> dict[str, object]:
        with self.write_gate.writer():
            current = self.authority.operation(operation_id)
            if current is None:
                raise ProtocolError("Operation is unknown")
            result = self.authority.mark_uncertain(operation_id)
            if current["kind"] == "admission":
                admissions = self.authority.snapshot()["admissions"]
                admission = next(row for row in admissions
                                 if row["operation_id"] == operation_id)
                self.postgres.mark_admission_uncertain(operation_id, admission["sequence"])
            else:
                with self.postgres._connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT kind,target::text,receipt_sha256 FROM lot210_operations "
                                       "WHERE operation_id=%s", (operation_id,))
                        row = cursor.fetchone()
                if row is None:
                    raise ReconciliationRequired("PostgreSQL operation is missing")
                identity = {"id": operation_id, "type": row[0],
                            "target": row[1], "receipt_sha256": row[2]}
                self.postgres.put_operation(identity, "uncertain", result["generation"])
            return result

    def reconcile_applied(
        self,
        operation: Mapping[str, str],
        result_sha256: str,
        evidence_sha256: str,
    ) -> dict[str, object]:
        with self.write_gate.writer():
            identity = self._identity(operation)
            result = self.authority.reconcile_applied(
                identity["id"], result_sha256, evidence_sha256)
            self.postgres.put_operation(
                identity, "result_recorded", result["generation"], result_sha256)
            if identity["type"] == "hold_release":
                return result
            local_state = self.authenticated.verify(identity)
            if local_state == "authorized":
                self.authenticated.record_result(identity)
            elif local_state != "result_recorded":
                raise ReconciliationRequired("Local authenticated history cannot be reconciled")
            return result


class LifecycleAdmissionProtocol:
    def __init__(
        self,
        authority: FreshnessAuthority,
        postgres: SyntheticPostgres,
        witness: ConfirmationStore,
        admission_coordinator: AdmissionCoordinator,
        registry: Registry,
        write_gate: CooperativeWriteGate,
    ) -> None:
        self.authority = authority
        self.postgres = postgres
        self.witness = witness
        self.admission_coordinator = admission_coordinator
        self.registry = registry
        self.write_gate = write_gate

    def admit(self, operation_id: str, user_id: str) -> dict[str, object]:
        with self.write_gate.writer():
            operation_id, user_id = _canonical_uuid(operation_id), _canonical_uuid(user_id)
            existing = self.authority.operation(operation_id)
            if existing and existing["state"] == "result_recorded":
                reservation = self.authority.reserve_admission(operation_id, user_id)
                return {"operation_id": operation_id, "sequence": reservation["sequence"],
                        "state": "result_recorded", "idempotent": True}
            if existing:
                raise ReconciliationRequired(
                    "Admission reservation already exists; reconcile without issuing another place")
            sequence: int | None = None
            try:
                reservation = self.authority.reserve_admission(operation_id, user_id)
                sequence = reservation["sequence"]
                self.postgres.apply_admission(operation_id, user_id, sequence)
                self.admission_coordinator.reserve(sequence, user_id)
                self.registry.observe_admissions(sequence)
                self.admission_coordinator.settle(sequence, user_id)
                self.postgres.settle_admission(operation_id, sequence)
                result = self.authority.record_result(operation_id, _digest(
                    f"{operation_id}:{sequence}:{user_id}".encode()))
            except Exception:
                current = self.authority.operation(operation_id)
                if current and current["state"] == "authorized":
                    try:
                        self.authority.mark_uncertain(operation_id)
                        if sequence is None:
                            reservation_row = next(
                                row for row in self.authority.snapshot()["admissions"]
                                if row["operation_id"] == operation_id)
                            sequence = reservation_row["sequence"]
                        self.postgres.mark_admission_uncertain(operation_id, sequence)
                    except Exception as marker_error:
                        raise ReconciliationRequired(
                            "Admission failed and uncertainty could not be recorded in every store"
                        ) from marker_error
                raise
            return {"operation_id": operation_id, "sequence": sequence,
                    "state": result["state"], "idempotent": False}


class CoordinatedCapture:
    """Binds an encrypted lot 2.9 archive to PostgreSQL and authority evidence."""

    def __init__(
        self,
        authority: FreshnessAuthority,
        postgres: SyntheticPostgres,
        settings: object,
        root: Path,
        keyring: Mapping[str, bytes],
        key_id: str,
        verifier: lot29.ConsistencyVerifier,
        write_gate: CooperativeWriteGate,
        *,
        lock_timeout: float = 0.25,
    ) -> None:
        self.root = _check_lab(root)
        self.authority = authority
        self.postgres = postgres
        self.settings = settings
        self.keyring = keyring
        self.key_id = key_id
        self.verifier = verifier
        self.write_gate = write_gate
        self.lock_timeout = lock_timeout
        if type(verifier) is not lot29.SyntheticLifecycleConsistencyVerifier:
            raise ProtocolError("Lot 2.9 synthetic lifecycle verifier is required")
        lot29._validate_keyring(keyring, key_id)
        lot29.configured_store_paths(settings, self.root)

    def capture(self) -> Path:
        with self.write_gate.freeze():
            with self.postgres.capture_fence() as pg_connection:
                with self.authority.capture_fence() as authority_state:
                    postgres_state = self.postgres.read_state(pg_connection)
                    witness = ConfirmationStore(
                        getattr(self.settings, lot29.COMPONENTS["witness"]["setting"])
                    ).admission_entries()
                    _validate_cross_store_state(postgres_state, authority_state, witness)
                    sqlite_admission_count = self.verifier.verify(
                        lot29.configured_store_paths(self.settings, self.root)
                    )["admissions"]
                    if sqlite_admission_count != authority_state["admission_count"]:
                        raise RollbackDetected("Lot 2.9 stores and independent admission count differ")
                    _verify_sqlite_operations(
                        self.settings, postgres_state, authority_state, self.verifier)
                    bundle_path = lot29.create_bundle(
                        self.settings, self.root, self.root / "bundles",
                        self.keyring, self.key_id, self.verifier,
                        lock_timeout=self.lock_timeout,
                    )
                    envelope = lot29._read_bundle(bundle_path, self.root)
                    bundle_key = lot29._validate_keyring(self.keyring, self.key_id)
                    bundle_manifest, _ = lot29._verify_envelope(
                        envelope, bundle_key, self.verifier, self.root)
                    metadata = {
                        "artifact_version": ARTIFACT_VERSION,
                        "backup_id": envelope["backup_id"],
                        "sqlite_capture_boundary_id": bundle_manifest["capture_boundary_id"],
                        "authority_generation": authority_state["generation"],
                        "authority_head_digest": authority_state["head_digest"],
                        "authority_registration_open": authority_state["registration_open"],
                        "authority_admission_count": authority_state["admission_count"],
                        "authority_operations": authority_state["operations"],
                        "authority_admissions": authority_state["admissions"],
                        "postgres_database": postgres_state["database"],
                        "postgres_transaction_snapshot": postgres_state["transaction_snapshot"],
                        "postgres_wal_lsn": postgres_state["wal_lsn"],
                        "postgres_sha256": _digest(_json(postgres_state)),
                        "included": [
                            "lot2_9_encrypted_five_sqlite_bundle",
                            "synthetic_postgresql_quota_and_operation_tables",
                            "synthetic_independent_authority_generation_and_head",
                        ],
                        "excluded": [
                            "production_database_and_documents",
                            "real_independent_authority",
                            "keys_and_provider_credentials",
                            "application_write_paths_not_cooperating_with_this_lab_gate",
                        ],
                    }
                    nonce = os.urandom(12)
                    cipher_key = lot29._bundle_key(bundle_key, envelope["backup_id"])
                    aad = _json({
                        "metadata": metadata,
                    })
                    ciphertext = AESGCM(cipher_key).encrypt(
                        nonce, _json(postgres_state), aad)
                    artifact = {
                        "metadata": metadata,
                        "postgres_nonce": nonce.hex(),
                        "postgres_ciphertext": ciphertext.hex(),
                    }
                    destination = self.root / "bundles" / (
                        envelope["backup_id"] + ".coordinated")
                    temporary = destination.with_suffix(".coordinated.part")
                    try:
                        with temporary.open("xb") as stream:
                            stream.write(_json(artifact))
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.link(temporary, destination)
                        temporary.unlink()
                        return destination
                    except OSError as error:
                        if temporary.exists() and not temporary.is_symlink():
                            temporary.unlink()
                        raise ProtocolError(
                            f"Could not publish coordinated lab artifact: {type(error).__name__}"
                        ) from None


def _decode_artifact(path: Path, root: Path) -> tuple[dict[str, object], dict[str, object]]:
    path = Path(path).absolute()
    expected_parent = root / "bundles"
    if (path.parent != expected_parent or path.suffix != ".coordinated"
            or path.is_symlink() or not path.is_file()
            or path.resolve() != path or path.stat().st_size > MAX_ARTIFACT_BYTES):
        raise ProtocolError("Only a bounded coordinated artifact in the lab bundles directory is accepted")
    try:
        wrapper = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("Coordinated artifact is unreadable") from None
    if (not isinstance(wrapper, dict) or set(wrapper) != {
            "metadata", "postgres_nonce", "postgres_ciphertext"}
            or _json(wrapper) != path.read_bytes()):
        raise ProtocolError("Malformed or non-canonical coordinated artifact")
    metadata = wrapper["metadata"]
    expected_metadata = {
        "artifact_version", "backup_id", "sqlite_capture_boundary_id",
        "authority_generation", "authority_head_digest",
        "authority_registration_open", "authority_admission_count",
        "authority_operations", "authority_admissions", "postgres_database",
        "postgres_transaction_snapshot", "postgres_wal_lsn", "postgres_sha256",
        "included", "excluded",
    }
    if (not isinstance(metadata, dict) or set(metadata) != expected_metadata
            or metadata.get("artifact_version") != ARTIFACT_VERSION
            or metadata.get("included") != [
                "lot2_9_encrypted_five_sqlite_bundle",
                "synthetic_postgresql_quota_and_operation_tables",
                "synthetic_independent_authority_generation_and_head",
            ]):
        raise ProtocolError("Unsupported coordinated artifact manifest")
    return wrapper, metadata


def recover(
    artifact_path: Path,
    root: Path,
    quarantine_parent: Path,
    destination: Path,
    keyring: Mapping[str, bytes],
    key_id: str,
    verifier: lot29.ConsistencyVerifier,
    authority: FreshnessAuthority,
    postgres_quarantine: SyntheticPostgres,
) -> dict[str, object]:
    root = _check_lab(root)
    if authority.path != root / AUTHORITY_RELATIVE_PATH:
        raise FreshnessUnavailable("Restored authority copy is not independent of quarantine")
    if Path(quarantine_parent).absolute() != root / "quarantine":
        raise ProtocolError("Recovery must target the existing laboratory quarantine")
    wrapper, metadata = _decode_artifact(artifact_path, root)
    backup_id = metadata.get("backup_id")
    try:
        canonical_backup_id = _canonical_uuid(backup_id)
    except ProtocolError:
        raise ProtocolError("Invalid coordinated bundle identity")
    if canonical_backup_id != backup_id:
        raise ProtocolError("Invalid coordinated bundle identity")
    bundle_path = root / "bundles" / (backup_id + ".bundle")
    envelope = lot29._read_bundle(bundle_path, root)
    if envelope["backup_id"] != backup_id or envelope["key_id"] != key_id:
        raise ProtocolError("Coordinated artifact and lot 2.9 bundle differ")
    key = lot29._validate_keyring(keyring, key_id)
    try:
        nonce = bytes.fromhex(wrapper["postgres_nonce"])
        ciphertext = bytes.fromhex(wrapper["postgres_ciphertext"])
        if len(nonce) != 12:
            raise ValueError()
        cipher_key = lot29._bundle_key(key, backup_id)
        aad = _json({"metadata": metadata})
        postgres_state = json.loads(AESGCM(cipher_key).decrypt(nonce, ciphertext, aad))
    except (ValueError, KeyError, TypeError, InvalidTag, json.JSONDecodeError):
        raise ProtocolError("PostgreSQL snapshot authentication failed") from None
    _validate_postgres_snapshot(postgres_state)
    if _digest(_json(postgres_state)) != metadata.get("postgres_sha256"):
        raise ProtocolError("PostgreSQL snapshot fingerprint differs")

    sqlite_destination = Path(destination).absolute()
    restored_sqlite = lot29.restore_bundle(
        bundle_path, root, root / "quarantine", sqlite_destination,
        keyring, verifier,
    )
    restored_postgres = postgres_quarantine.restore_quarantine(postgres_state)
    current = authority.snapshot()
    if (current["generation"] != metadata.get("authority_generation")
            or current["head_digest"] != metadata.get("authority_head_digest")
            or current["admission_count"] != metadata.get("authority_admission_count")
            or current["operations"] != metadata.get("authority_operations")
            or current["admissions"] != metadata.get("authority_admissions")
            or current["registration_open"] is not metadata.get("authority_registration_open")):
        raise RollbackDetected(
            "Restored PostgreSQL and SQLite predate or diverge from the independent authority")
    witness = ConfirmationStore(
        sqlite_destination / "witness.sqlite"
    ).admission_entries()
    _validate_cross_store_state(restored_postgres, current, witness)
    _verify_sqlite_operations(
        SimpleNamespace(
            lifecycle_authenticated_confirmation_path=sqlite_destination / "authenticated.sqlite",
            lifecycle_holds_path=sqlite_destination / "holds.sqlite",
        ),
        restored_postgres, current, verifier)
    if restored_postgres["quota"]["closed"] is not True:
        raise RollbackDetected("Restored PostgreSQL admissions must remain closed")
    if current["registration_open"]:
        raise RollbackDetected("Independent authority has not confirmed closed admissions")
    return {
        "backup_id": backup_id,
        "authority_generation": current["generation"],
        "authority_head_digest": current["head_digest"],
        "postgres_transaction_snapshot": metadata["postgres_transaction_snapshot"],
        "postgres_wal_lsn": metadata["postgres_wal_lsn"],
        "restored_sqlite_path": str(restored_sqlite["restore_path"]),
        "restored_postgres_database": restored_postgres["database"],
        "integrity_verified": True,
        "completeness_verified": True,
        "cross_store_consistency_verified": True,
        "independent_freshness_verified": True,
        "freshness_scope": "synthetic authority object in this process only",
        "registration_open": False,
        "critical_mutations_allowed": False,
        "opening_authorized": False,
        "requires_separate_reconciliation": True,
    }


def inspect_restored_prefix(
    restored_authority_path: Path,
    lab_root: Path,
    key: bytes,
) -> dict[str, object]:
    """Show why copying the authority with a restored snapshot loses independence."""
    root = _check_lab(lab_root)
    path = Path(restored_authority_path).absolute()
    if path == root / AUTHORITY_RELATIVE_PATH:
        raise ProtocolError("A restored authority copy must not replace the live authority")
    if not path.is_file() or path.is_symlink():
        raise FreshnessUnavailable("Restored authority copy is missing")
    clone_root = root / "quarantine"
    try:
        path.relative_to(clone_root)
    except ValueError:
        raise ProtocolError("Demonstration copy must be inside quarantine") from None
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        head = connection.execute("SELECT generation,admission_count,"
                                  "registration_open,last_digest FROM authority_head "
                                  "WHERE id=1").fetchone()
        if head is None:
            raise FreshnessUnavailable("Restored authority head is missing")
        previous = _digest(b"documind-lot210-authority-genesis-v1")
        events = connection.execute(
            "SELECT * FROM authority_events ORDER BY generation").fetchall()
        if len(events) != head[0]:
            raise FreshnessUnavailable("Restored authority copy is truncated")
        for expected_generation, row in enumerate(events, 1):
            envelope = {
                "generation": row[0], "event_id": row[1],
                "operation_id": row[2], "kind": row[3], "state": row[4],
                "payload": json.loads(row[5])["payload"],
                "previous_digest": row[6],
            }
            encoded = _json(envelope)
            if (row[0] != expected_generation or row[6] != previous
                    or not hmac.compare_digest(row[7], _digest(encoded))
                    or not hmac.compare_digest(
                        row[8], hmac.new(key, encoded, hashlib.sha256).hexdigest())):
                raise FreshnessUnavailable("Restored authority copy failed HMAC verification")
            previous = row[7]
        if not hmac.compare_digest(head[3], previous):
            raise FreshnessUnavailable("Restored authority copy has an inconsistent head")
        return {
            "generation": head[0], "admission_count": head[1],
            "registration_open": bool(head[2]), "head_digest": head[3],
            "copied_chain_authentication_verified": True,
            "independent_freshness_verified": False,
            "reason": "A restored copy of the authority is part of the rollback set",
        }
    finally:
        connection.close()
