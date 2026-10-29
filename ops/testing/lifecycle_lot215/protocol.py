"""Synthetic-only witness-first transaction simulator.

This module uses only explicit paths below a marked laboratory root. It has no
network clients and imports no application configuration or production code.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Callable, Concatenate, Iterator, ParamSpec, TypeVar
from uuid import UUID


LAB_ENV = "PHASE154L215_LAB"
LAB_MARKER = ".phase154-lot215-synthetic"
LAB_MARKER_CONTENT = b"documind-phase-15-4-lot-2-15-synthetic\n"
SCHEMA_VERSION = 1
ADMISSION_LIMIT = 5
GENESIS = "0" * 64
_SHA256 = frozenset("0123456789abcdef")
_LOCKS_GUARD = threading.Lock()
_LAB_LOCKS: dict[tuple[str, str], threading.RLock] = {}
_LAB_RECOVERY_REQUIRED: dict[tuple[str, str], bool] = {}
_CONTEXT_CREATION_TOKEN = object()
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _synchronized(
    method: Callable[Concatenate[Any, _P], _R],
) -> Callable[Concatenate[Any, _P], _R]:
    @wraps(method)
    def wrapped(self: Any, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        with self.context._lock:
            return method(self, *args, **kwargs)

    return wrapped


def _require_context_open(context: LabContext) -> None:
    if context.recovery_required:
        raise Closed("Laboratory context is closed for recovery")


class ProtocolError(ValueError):
    """A synthetic protocol precondition or invariant failed."""


class LabGuardError(ProtocolError):
    """The explicit isolated-laboratory boundary was not satisfied."""


class Conflict(ProtocolError):
    """An operation ID, generation, or event conflicts with durable state."""


class Closed(ProtocolError):
    """Mutations are blocked by an ambiguity, restore, or quarantine."""


class InjectedFailure(ProtocolError):
    """A deterministic synthetic fault interrupted a protocol boundary."""


class FailurePoint(str, Enum):
    ADMISSION_BEFORE_W_COMMIT = "admission.before_w_commit"
    ADMISSION_AFTER_W_COMMIT = "admission.after_w_commit_before_reply"
    ADMISSION_BEFORE_P_APPLY = "admission.before_p_apply"
    ADMISSION_BEFORE_P_COMMIT = "admission.before_p_commit"
    ADMISSION_AFTER_P_COMMIT = "admission.after_p_commit_before_reply"
    ADMISSION_FINAL_RECONCILIATION = "admission.during_reconciliation"
    PREPARE_BEFORE_W_COMMIT = "critical.before_prepare_w_commit"
    PREPARE_AFTER_W_COMMIT = "critical.after_prepare_w_commit_before_reply"
    PREPARE_BEFORE_P_APPLY = "critical.before_prepare_p_apply"
    PREPARE_BEFORE_P_COMMIT = "critical.before_prepare_p_commit"
    PREPARE_AFTER_P_COMMIT = "critical.after_prepare_p_commit_before_reply"
    AUTHORIZE_BEFORE_W_COMMIT = "critical.before_authorize_w_commit"
    AUTHORIZE_AFTER_W_COMMIT = "critical.after_authorize_w_commit_before_reply"
    AUTHORIZE_BEFORE_P_APPLY = "critical.before_authorize_p_apply"
    AUTHORIZE_BEFORE_P_COMMIT = "critical.before_authorize_p_commit"
    AUTHORIZE_AFTER_P_COMMIT = "critical.after_authorize_p_commit_before_reply"
    EFFECT_BEFORE = "critical.before_effect"
    EFFECT_AFTER = "critical.after_effect_before_result"
    RESULT_BEFORE_W_COMMIT = "critical.before_result_w_commit"
    RESULT_AFTER_W_COMMIT = "critical.after_result_w_commit_before_p"
    RESULT_BEFORE_P_APPLY = "critical.before_result_p_apply"
    RESULT_BEFORE_P_COMMIT = "critical.before_result_p_commit"
    RESULT_AFTER_P_COMMIT = "critical.after_result_p_commit_before_reply"
    CRITICAL_FINAL_RECONCILIATION = "critical.during_final_reconciliation"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _check_digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in _SHA256 for c in value):
        raise ProtocolError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _check_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ProtocolError("operation_id must be a canonical UUID")
    try:
        normalized = str(UUID(value))
    except (ValueError, AttributeError):
        raise ProtocolError("operation_id must be a canonical UUID") from None
    if normalized != value:
        raise ProtocolError("operation_id must be a canonical UUID")
    return value


def _lab_guard() -> None:
    if os.environ.get(LAB_ENV) != "isolated":
        raise LabGuardError(f"{LAB_ENV}=isolated is required")


def _absolute(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise LabGuardError("All laboratory paths must be explicitly absolute")
    absolute = Path(os.path.abspath(path))
    if absolute != path:
        raise LabGuardError("Non-canonical laboratory path")
    return absolute


def _reject_symlink_components(path: Path, stop: Path | None = None) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise LabGuardError(f"Symbolic links are not allowed: {current}")
        if stop is not None and current == stop:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def _inside(root: Path, path: Path, *, must_exist: bool) -> Path:
    root = _absolute(root)
    path = _absolute(path)
    _reject_symlink_components(root)
    _reject_symlink_components(path, root)
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=must_exist)
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise LabGuardError("Every input path must remain below the laboratory root") from None
    if path == root:
        raise LabGuardError("A database or snapshot path cannot be the laboratory root")
    return path


def _require_marker(root: Path) -> None:
    root = _absolute(root)
    _reject_symlink_components(root)
    if not root.is_dir():
        raise LabGuardError("The explicit laboratory root must be an existing directory")
    marker = root / LAB_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise LabGuardError("The lot 2.15 synthetic marker is missing")
    if marker.read_bytes() != LAB_MARKER_CONTENT:
        raise LabGuardError("The lot 2.15 synthetic marker is invalid")


def _validate_database_paths(root: Path, witness_path: Path, primary_path: Path) -> tuple[Path, Path]:
    witness = _inside(root, witness_path, must_exist=witness_path.exists())
    primary = _inside(root, primary_path, must_exist=primary_path.exists())
    if witness == primary:
        raise LabGuardError("Witness and Primary must use distinct database files")
    if witness.exists() and primary.exists() and os.path.samefile(witness, primary):
        raise LabGuardError("Witness and Primary must not share a database file")
    for path in (witness, primary):
        if path.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
            raise LabGuardError("Database paths must have an explicit SQLite extension")
        path.parent.mkdir(parents=True, exist_ok=True)
        _inside(root, path, must_exist=False)
    return witness, primary


@dataclass
class LabContext:
    """In-memory lab capability; reopening an existing root is always closed."""

    root: Path
    witness_path: Path
    primary_path: Path
    _recovery_required: bool
    recovery_reason: str | None = None
    pending_operation_id: str | None = None
    incident_recoverable_in_process: bool = False
    _lock: threading.RLock | None = None
    _lab_key: tuple[str, str] | None = field(default=None, init=False, repr=False)
    _creation_token: object | None = field(default=None, repr=False)

    @property
    def recovery_required(self) -> bool:
        if self._lab_key is None:
            return self._recovery_required
        with _LOCKS_GUARD:
            return _LAB_RECOVERY_REQUIRED[self._lab_key]

    def _set_recovery_required(self, required: bool) -> None:
        self._recovery_required = required
        if self._lab_key is not None:
            with _LOCKS_GUARD:
                _LAB_RECOVERY_REQUIRED[self._lab_key] = required

    def __post_init__(self) -> None:
        if self._creation_token is not _CONTEXT_CREATION_TOKEN:
            raise LabGuardError("Create lab contexts only through initialize_lab or open_existing_lab")
        key = (str(self.witness_path.resolve()), str(self.primary_path.resolve()))
        with _LOCKS_GUARD:
            lock = _LAB_LOCKS.get(key)
            if lock is None:
                lock = self._lock or threading.RLock()
                _LAB_LOCKS[key] = lock
            self._lock = lock
            if key not in _LAB_RECOVERY_REQUIRED:
                _LAB_RECOVERY_REQUIRED[key] = self._recovery_required
            elif self._recovery_required:
                _LAB_RECOVERY_REQUIRED[key] = True
            self._recovery_required = _LAB_RECOVERY_REQUIRED[key]
            self._lab_key = key


def _connect(path: Path, root: Path, domain: str) -> sqlite3.Connection:
    _inside(root, path, must_exist=True)
    class ClosingConnection(sqlite3.Connection):
        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            try:
                return bool(super().__exit__(exc_type, exc, traceback))
            finally:
                self.close()

    connection = sqlite3.connect(
        path, timeout=10.0, isolation_level=None, factory=ClosingConnection
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = FULL")
    row = connection.execute(
        "SELECT domain_id, schema_version FROM lab_meta WHERE id = 1"
    ).fetchone()
    if row is None or row["domain_id"] != domain or row["schema_version"] != SCHEMA_VERSION:
        connection.close()
        raise LabGuardError(f"Unexpected or shared {domain} database")
    return connection


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def _initialize_database(path: Path, domain: str) -> None:
    connection = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.executescript(
        """
        CREATE TABLE lab_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            domain_id TEXT NOT NULL,
            schema_version INTEGER NOT NULL
        );
        CREATE TABLE events (
            generation INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            previous_digest TEXT NOT NULL,
            head_digest TEXT NOT NULL,
            event_type TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    if domain == "W":
        connection.executescript(
            """
            CREATE TABLE authority_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                generation INTEGER NOT NULL CHECK (generation >= 0),
                total_consumed INTEGER NOT NULL CHECK (total_consumed >= 0),
                max_admissions INTEGER NOT NULL CHECK (max_admissions = 5),
                head_digest TEXT NOT NULL,
                closed INTEGER NOT NULL CHECK (closed IN (0, 1))
            );
            CREATE TABLE reservations (
                operation_id TEXT PRIMARY KEY,
                identity_digest TEXT NOT NULL UNIQUE,
                reservation_no INTEGER NOT NULL UNIQUE,
                state TEXT NOT NULL,
                generation INTEGER NOT NULL,
                request_digest TEXT NOT NULL
            );
            CREATE TABLE critical_operations (
                operation_id TEXT PRIMARY KEY,
                operation_digest TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                hold_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                authorized_generation INTEGER,
                result_digest TEXT
            );
            """
        )
    else:
        connection.executescript(
            """
            CREATE TABLE authority_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                generation INTEGER NOT NULL CHECK (generation >= 0),
                head_digest TEXT NOT NULL,
                closed INTEGER NOT NULL CHECK (closed IN (0, 1))
            );
            CREATE TABLE reservations (
                operation_id TEXT PRIMARY KEY,
                identity_digest TEXT NOT NULL UNIQUE,
                reservation_no INTEGER NOT NULL UNIQUE,
                state TEXT NOT NULL,
                witness_generation INTEGER NOT NULL
            );
            CREATE TABLE critical_operations (
                operation_id TEXT PRIMARY KEY,
                operation_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                witness_authorization_generation INTEGER,
                result_digest TEXT
            );
            CREATE TABLE synthetic_effects (
                operation_id TEXT PRIMARY KEY,
                operation_digest TEXT NOT NULL,
                result_digest TEXT NOT NULL
            );
            """
        )
    with _transaction(connection):
        connection.execute(
            "INSERT INTO lab_meta(id, domain_id, schema_version) VALUES (1, ?, ?)",
            (domain, SCHEMA_VERSION),
        )
        if domain == "W":
            connection.execute(
                "INSERT INTO authority_state VALUES (1, 0, 0, ?, ?, 0)",
                (ADMISSION_LIMIT, GENESIS),
            )
        else:
            connection.execute(
                "INSERT INTO authority_state VALUES (1, 0, ?, 0)",
                (GENESIS,),
            )
    connection.close()


def initialize_lab(root: Path, witness_path: Path, primary_path: Path) -> LabContext:
    """Create a fresh, marked lab. The root must not exist before this call."""
    _lab_guard()
    root = _absolute(root)
    _reject_symlink_components(root)
    if root.exists():
        raise LabGuardError("A fresh laboratory root must not already exist")
    parent = root.parent
    if not parent.is_dir() or parent.resolve(strict=True) != parent:
        raise LabGuardError("The explicitly supplied laboratory parent must be canonical")
    root.mkdir()
    (root / LAB_MARKER).write_bytes(LAB_MARKER_CONTENT)
    witness, primary = _validate_database_paths(root, witness_path, primary_path)
    if witness.exists() or primary.exists():
        raise LabGuardError("Fresh Witness and Primary database files must not exist")
    _initialize_database(witness, "W")
    _initialize_database(primary, "P")
    return LabContext(
        root, witness, primary, _recovery_required=False,
        _creation_token=_CONTEXT_CREATION_TOKEN,
    )


def open_existing_lab(root: Path, witness_path: Path, primary_path: Path) -> LabContext:
    """Open explicitly named databases for inspection, always in recovery-closed mode."""
    _lab_guard()
    root = _absolute(root)
    _require_marker(root)
    witness, primary = _validate_database_paths(root, witness_path, primary_path)
    if not witness.is_file() or not primary.is_file():
        raise LabGuardError("Both explicitly named database files must already exist")
    _connect(witness, root, "W").close()
    _connect(primary, root, "P").close()
    return LabContext(
        root, witness, primary, _recovery_required=True, recovery_reason="existing root",
        _creation_token=_CONTEXT_CREATION_TOKEN,
    )


class Witness:
    """Authoritative synthetic transaction domain W."""

    def __init__(self, context: LabContext):
        self.context = context

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.context.witness_path, self.context.root, "W")

    def state(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone()
            return dict(row)

    def event(self, generation: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM events WHERE generation = ?", (generation,)).fetchone()
            return dict(row) if row else None

    def events(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM events ORDER BY generation")]

    def operation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row else None

    def reservation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM reservations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row else None

    def _append(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        operation_id: str,
        payload: dict[str, Any],
        expected_generation: int,
        fail_before_commit: bool,
    ) -> dict[str, Any]:
        state = connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone()
        if state["closed"]:
            raise Closed("Witness W is closed")
        if state["generation"] != expected_generation:
            raise Conflict("Witness generation conflict")
        generation = state["generation"] + 1
        event_id = f"W:{generation}:{operation_id}:{event_type}"
        payload_json = _canonical(payload).decode("ascii")
        payload_digest = _digest(payload_json.encode("ascii"))
        core = {
            "event_id": event_id,
            "generation": generation,
            "previous_digest": state["head_digest"],
            "event_type": event_type,
            "operation_id": operation_id,
            "payload_digest": payload_digest,
        }
        head_digest = _digest(_canonical(core))
        connection.execute(
            """INSERT INTO events
               (generation, event_id, previous_digest, head_digest, event_type,
                operation_id, payload_digest, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                generation, event_id, state["head_digest"], head_digest, event_type,
                operation_id, payload_digest, payload_json,
            ),
        )
        connection.execute(
            "UPDATE authority_state SET generation = ?, head_digest = ? WHERE id = 1",
            (generation, head_digest),
        )
        if fail_before_commit:
            raise InjectedFailure("Injected failure before Witness commit")
        return {
            **core,
            "previous_digest": state["head_digest"],
            "head_digest": head_digest,
            "payload_json": payload_json,
        }

    @_synchronized
    def reserve(
        self, operation_id: str, identity_digest: str, expected_generation: int,
        *, fail_before_commit: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        operation_id = _check_uuid(operation_id)
        identity_digest = _check_digest(identity_digest, "identity_digest")
        request_digest = _digest(_canonical({"identity_digest": identity_digest}))
        with self._connect() as connection:
            with _transaction(connection):
                old = connection.execute(
                    "SELECT * FROM reservations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if old:
                    if old["request_digest"] != request_digest:
                        raise Conflict("Reservation ID was reused with different content")
                    return dict(old), False
                _require_context_open(self.context)
                if connection.execute(
                    "SELECT 1 FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone():
                    raise Conflict("Operation ID is already used by a critical operation")
                if connection.execute(
                    "SELECT 1 FROM reservations WHERE identity_digest = ?", (identity_digest,)
                ).fetchone():
                    raise Conflict("Identity digest has already consumed an admission")
                state = connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone()
                if state["closed"]:
                    raise Closed("Witness W is closed")
                if state["generation"] != expected_generation:
                    raise Conflict("Witness generation conflict")
                if state["total_consumed"] >= state["max_admissions"]:
                    raise Conflict("Cumulative admission limit reached")
                reservation_no = state["total_consumed"] + 1
                payload = {
                    "identity_digest": identity_digest,
                    "request_digest": request_digest,
                    "reservation_no": reservation_no,
                    "state": "reserved",
                }
                event = self._append(
                    connection, "admission_reserved", operation_id, payload,
                    expected_generation, fail_before_commit,
                )
                connection.execute(
                    "UPDATE authority_state SET total_consumed = ? WHERE id = 1",
                    (reservation_no,),
                )
                connection.execute(
                    """INSERT INTO reservations
                       VALUES (?, ?, ?, 'reserved', ?, ?)""",
                    (operation_id, identity_digest, reservation_no, event["generation"], request_digest),
                )
                result = {
                    "operation_id": operation_id,
                    "identity_digest": identity_digest,
                    "reservation_no": reservation_no,
                    "state": "reserved",
                    "generation": event["generation"],
                    "request_digest": request_digest,
                    "event": event,
                }
                return result, True

    @_synchronized
    def prepare(
        self, operation_id: str, operation_digest: str, receipt_digest: str, hold_digest: str,
        expected_generation: int, *, fail_before_commit: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        operation_id = _check_uuid(operation_id)
        operation_digest = _check_digest(operation_digest, "operation_digest")
        receipt_digest = _check_digest(receipt_digest, "receipt_digest")
        hold_digest = _check_digest(hold_digest, "hold_digest")
        with self._connect() as connection:
            with _transaction(connection):
                old = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if old:
                    if (old["operation_digest"], old["receipt_digest"], old["hold_digest"]) != (
                        operation_digest, receipt_digest, hold_digest
                    ):
                        raise Conflict("Critical operation ID was reused with different content")
                    return dict(old), None
                _require_context_open(self.context)
                if connection.execute(
                    "SELECT 1 FROM reservations WHERE operation_id = ?", (operation_id,)
                ).fetchone():
                    raise Conflict("Operation ID is already used by an admission")
                payload = {
                    "operation_digest": operation_digest,
                    "receipt_digest": receipt_digest,
                    "hold_digest": hold_digest,
                    "state": "prepared",
                }
                event = self._append(
                    connection, "critical_prepared", operation_id, payload,
                    expected_generation, fail_before_commit,
                )
                connection.execute(
                    """INSERT INTO critical_operations
                       (operation_id, operation_digest, receipt_digest, hold_digest, state,
                        authorized_generation, result_digest)
                       VALUES (?, ?, ?, ?, 'prepared', NULL, NULL)""",
                    (operation_id, operation_digest, receipt_digest, hold_digest),
                )
                return {
                    "operation_id": operation_id, "operation_digest": operation_digest,
                    "receipt_digest": receipt_digest, "hold_digest": hold_digest,
                    "state": "prepared", "authorized_generation": None, "result_digest": None,
                }, event

    @_synchronized
    def authorize(
        self, operation_id: str, expected_generation: int, *, fail_before_commit: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        operation_id = _check_uuid(operation_id)
        with self._connect() as connection:
            with _transaction(connection):
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if operation is None:
                    raise Conflict("Critical operation is not prepared")
                if operation["state"] in {"authorized", "result_recorded"}:
                    return dict(operation), None
                if operation["state"] != "prepared":
                    raise Closed("Critical operation is not authorizable")
                _require_context_open(self.context)
                payload = {
                    "operation_digest": operation["operation_digest"],
                    "state": "authorized",
                }
                event = self._append(
                    connection, "critical_authorized", operation_id, payload,
                    expected_generation, fail_before_commit,
                )
                connection.execute(
                    """UPDATE critical_operations
                       SET state = 'authorized', authorized_generation = ?
                       WHERE operation_id = ? AND state = 'prepared'""",
                    (event["generation"], operation_id),
                )
                return {
                    **dict(operation),
                    "state": "authorized",
                    "authorized_generation": event["generation"],
                }, event

    @_synchronized
    def record_result(
        self, operation_id: str, result_digest: str, expected_generation: int,
        *, fail_before_commit: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        operation_id = _check_uuid(operation_id)
        result_digest = _check_digest(result_digest, "result_digest")
        with self._connect() as connection:
            with _transaction(connection):
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if operation is None:
                    raise Conflict("Critical operation does not exist")
                if operation["state"] == "result_recorded":
                    if operation["result_digest"] != result_digest:
                        raise Conflict("Critical result conflicts with the recorded result")
                    return dict(operation), None
                if operation["state"] != "authorized":
                    raise Closed("Critical operation is not authorized")
                _require_context_open(self.context)
                event = self._append(
                    connection, "critical_result_recorded", operation_id,
                    {"operation_digest": operation["operation_digest"], "result_digest": result_digest,
                     "state": "result_recorded"},
                    expected_generation, fail_before_commit,
                )
                connection.execute(
                    """UPDATE critical_operations SET state = 'result_recorded', result_digest = ?
                       WHERE operation_id = ? AND state = 'authorized'""",
                    (result_digest, operation_id),
                )
                return {
                    **dict(operation), "state": "result_recorded", "result_digest": result_digest,
                }, event

    @_synchronized
    def mark_uncertain(
        self, operation_id: str, evidence_digest: str, expected_generation: int,
    ) -> dict[str, Any]:
        operation_id = _check_uuid(operation_id)
        evidence_digest = _check_digest(evidence_digest, "evidence_digest")
        with self._connect() as connection:
            with _transaction(connection):
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if operation is None:
                    raise Conflict("Critical operation does not exist")
                if operation["state"] == "uncertain":
                    existing = connection.execute(
                        """SELECT payload_json FROM events
                           WHERE operation_id = ? AND event_type = 'critical_uncertain'
                           ORDER BY generation DESC LIMIT 1""",
                        (operation_id,),
                    ).fetchone()
                    if existing is None or json.loads(existing["payload_json"]).get(
                        "evidence_digest"
                    ) != evidence_digest:
                        raise Conflict("Uncertainty evidence conflicts with the recorded event")
                    return dict(operation)
                if operation["state"] not in {"prepared", "authorized"}:
                    raise Conflict("Only an unfinished operation can become uncertain")
                _require_context_open(self.context)
                event = self._append(
                    connection, "critical_uncertain", operation_id,
                    {"operation_digest": operation["operation_digest"],
                     "evidence_digest": evidence_digest, "state": "uncertain"},
                    expected_generation, False,
                )
                connection.execute(
                    "UPDATE critical_operations SET state = 'uncertain' WHERE operation_id = ?",
                    (operation_id,),
                )
                return {**dict(operation), "state": "uncertain", "generation": event["generation"]}

    @_synchronized
    def quarantine(
        self, operation_id: str, evidence_digest: str, expected_generation: int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        operation_id = _check_uuid(operation_id)
        evidence_digest = _check_digest(evidence_digest, "evidence_digest")
        with self._connect() as connection:
            with _transaction(connection):
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if operation is None:
                    raise Conflict("Critical operation does not exist")
                if operation["state"] == "quarantined":
                    existing = connection.execute(
                        """SELECT payload_json FROM events
                           WHERE operation_id = ? AND event_type = 'critical_quarantined'
                           ORDER BY generation DESC LIMIT 1""",
                        (operation_id,),
                    ).fetchone()
                    if existing is None or json.loads(existing["payload_json"]).get(
                        "evidence_digest"
                    ) != evidence_digest:
                        raise Conflict("Quarantine evidence conflicts with the recorded event")
                    return dict(operation), None
                if operation["state"] == "result_recorded":
                    raise Conflict("A completed operation cannot be quarantined")
                _require_context_open(self.context)
                event = self._append(
                    connection, "critical_quarantined", operation_id,
                    {"operation_digest": operation["operation_digest"],
                     "evidence_digest": evidence_digest, "state": "quarantined"},
                    expected_generation, False,
                )
                connection.execute(
                    "UPDATE critical_operations SET state = 'quarantined' WHERE operation_id = ?",
                    (operation_id,),
                )
                return {
                    **dict(operation), "state": "quarantined", "generation": event["generation"]
                }, event

    def verify_integrity(self) -> dict[str, Any]:
        with self._connect() as connection:
            state = dict(connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone())
            events = [dict(row) for row in connection.execute("SELECT * FROM events ORDER BY generation")]
            previous = GENESIS
            for index, event in enumerate(events, 1):
                if event["generation"] != index or event["previous_digest"] != previous:
                    raise ProtocolError("Witness event sequence is incomplete")
                payload = json.loads(event["payload_json"])
                if _digest(_canonical(payload)) != event["payload_digest"]:
                    raise ProtocolError("Witness event payload digest mismatch")
                core = {
                    key: event[key] for key in
                    ("event_id", "generation", "previous_digest", "event_type", "operation_id", "payload_digest")
                }
                if _digest(_canonical(core)) != event["head_digest"]:
                    raise ProtocolError("Witness event head digest mismatch")
                previous = event["head_digest"]
            if len(events) != state["generation"] or previous != state["head_digest"]:
                raise ProtocolError("Witness state head does not match its event history")
            reservation_count = connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
            if reservation_count != state["total_consumed"] or state["total_consumed"] > state["max_admissions"]:
                raise ProtocolError("Witness cumulative counter does not match reservations")
            reservation_events = [
                event for event in events if event["event_type"] == "admission_reserved"
            ]
            if len(reservation_events) != reservation_count:
                raise ProtocolError("Witness reservation rows do not match its event history")
            for event in reservation_events:
                payload = json.loads(event["payload_json"])
                reservation = connection.execute(
                    "SELECT * FROM reservations WHERE operation_id = ?", (event["operation_id"],)
                ).fetchone()
                if reservation is None or (
                    reservation["identity_digest"] != payload["identity_digest"]
                    or reservation["reservation_no"] != payload["reservation_no"]
                    or reservation["generation"] != event["generation"]
                    or reservation["request_digest"] != payload["request_digest"]
                    or reservation["request_digest"] != _digest(_canonical({
                        "identity_digest": reservation["identity_digest"]
                    }))
                ):
                    raise ProtocolError("Witness reservation row is inconsistent")
            prepared_events = [
                event for event in events if event["event_type"] == "critical_prepared"
            ]
            critical_count = connection.execute(
                "SELECT COUNT(*) FROM critical_operations"
            ).fetchone()[0]
            if len(prepared_events) != critical_count:
                raise ProtocolError("Witness critical operation rows do not match its history")
            for event in prepared_events:
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (event["operation_id"],)
                ).fetchone()
                if operation is None:
                    raise ProtocolError("Witness critical operation is missing")
                payload = json.loads(event["payload_json"])
                if (operation["operation_digest"], operation["receipt_digest"], operation["hold_digest"]) != (
                    payload["operation_digest"], payload["receipt_digest"], payload["hold_digest"]
                ):
                    raise ProtocolError("Witness critical operation content is inconsistent")
                related = [item for item in events if item["operation_id"] == event["operation_id"]]
                latest = related[-1]
                expected_state = {
                    "critical_prepared": "prepared",
                    "critical_authorized": "authorized",
                    "critical_result_recorded": "result_recorded",
                    "critical_uncertain": "uncertain",
                    "critical_quarantined": "quarantined",
                }[latest["event_type"]]
                if operation["state"] != expected_state:
                    raise ProtocolError("Witness critical operation state is inconsistent")
                authorization_events = [
                    item for item in related if item["event_type"] == "critical_authorized"
                ]
                if authorization_events:
                    if operation["authorized_generation"] != authorization_events[0]["generation"]:
                        raise ProtocolError("Witness authorization generation is inconsistent")
                elif operation["authorized_generation"] is not None:
                    raise ProtocolError("Witness has an authorization without an event")
                if latest["event_type"] == "critical_result_recorded":
                    latest_payload = json.loads(latest["payload_json"])
                    if operation["result_digest"] != latest_payload["result_digest"]:
                        raise ProtocolError("Witness result digest is inconsistent")
                elif operation["result_digest"] is not None:
                    raise ProtocolError("Witness has a result without a result event")
            return {"valid": True, **state, "event_count": len(events)}

    @_synchronized
    def close(self) -> None:
        with self._connect() as connection:
            with _transaction(connection):
                connection.execute("UPDATE authority_state SET closed = 1 WHERE id = 1")


class Primary:
    """Non-authoritative projection domain P."""

    def __init__(self, context: LabContext):
        self.context = context

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.context.primary_path, self.context.root, "P")

    def state(self) -> dict[str, Any]:
        with self._connect() as connection:
            return dict(connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone())

    def reservation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM reservations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row else None

    def operation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row else None

    def effect(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM synthetic_effects WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row else None

    @_synchronized
    def apply(
        self, event: dict[str, Any], *, fail_before_commit: bool = False,
    ) -> bool:
        event = dict(event)
        authoritative = Witness(self.context).event(event["generation"])
        if authoritative != event:
            raise Conflict("Primary accepts only the exact event committed in Witness W")
        payload = json.loads(event["payload_json"])
        if _digest(_canonical(payload)) != event["payload_digest"]:
            raise ProtocolError("Authoritative event payload digest mismatch")
        core = {
            key: event[key] for key in
            ("event_id", "generation", "previous_digest", "event_type", "operation_id", "payload_digest")
        }
        if _digest(_canonical(core)) != event["head_digest"]:
            raise ProtocolError("Authoritative event head digest mismatch")
        with self._connect() as connection:
            with _transaction(connection):
                state = connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone()
                existing = connection.execute(
                    "SELECT * FROM events WHERE generation = ?", (event["generation"],)
                ).fetchone()
                if existing:
                    if (existing["event_id"], existing["head_digest"]) != (
                        event["event_id"], event["head_digest"]
                    ):
                        raise Conflict("Primary contains a conflicting event at this generation")
                    return False
                if state["closed"]:
                    raise Closed("Primary P is closed")
                if event["generation"] != state["generation"] + 1:
                    raise Conflict("Primary requires the next contiguous Witness generation")
                if event["previous_digest"] != state["head_digest"]:
                    raise Conflict("Primary previous digest does not match Witness event")
                connection.execute(
                    """INSERT INTO events
                       (generation, event_id, previous_digest, head_digest, event_type,
                        operation_id, payload_digest, payload_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(event[key] for key in (
                        "generation", "event_id", "previous_digest", "head_digest",
                        "event_type", "operation_id", "payload_digest", "payload_json"
                    )),
                )
                self._project(connection, event, payload)
                connection.execute(
                    "UPDATE authority_state SET generation = ?, head_digest = ? WHERE id = 1",
                    (event["generation"], event["head_digest"]),
                )
                if fail_before_commit:
                    raise InjectedFailure("Injected interruption before Primary commit")
        return True

    @staticmethod
    def _project(connection: sqlite3.Connection, event: dict[str, Any], payload: dict[str, Any]) -> None:
        operation_id = event["operation_id"]
        event_type = event["event_type"]
        generation = event["generation"]
        if event_type == "admission_reserved":
            connection.execute(
                """INSERT INTO reservations VALUES (?, ?, ?, ?, ?)""",
                (operation_id, payload["identity_digest"], payload["reservation_no"],
                 payload["state"], generation),
            )
        elif event_type == "critical_prepared":
            connection.execute(
                """INSERT INTO critical_operations
                   VALUES (?, ?, 'prepared', NULL, NULL)""",
                (operation_id, payload["operation_digest"]),
            )
        elif event_type == "critical_authorized":
            cursor = connection.execute(
                """UPDATE critical_operations SET state = 'authorized',
                   witness_authorization_generation = ? WHERE operation_id = ? AND state = 'prepared'""",
                (generation, operation_id),
            )
            if cursor.rowcount != 1:
                raise Conflict("Primary critical operation is not prepared")
        elif event_type == "critical_result_recorded":
            cursor = connection.execute(
                """UPDATE critical_operations SET state = 'result_recorded', result_digest = ?
                   WHERE operation_id = ? AND state = 'authorized'""",
                (payload["result_digest"], operation_id),
            )
            if cursor.rowcount != 1:
                raise Conflict("Primary critical operation is not authorized")
        elif event_type == "critical_uncertain":
            cursor = connection.execute(
                "UPDATE critical_operations SET state = 'uncertain' WHERE operation_id = ?",
                (operation_id,),
            )
            if cursor.rowcount != 1:
                raise Conflict("Primary critical operation does not exist")
        elif event_type == "critical_quarantined":
            cursor = connection.execute(
                """UPDATE critical_operations SET state = 'quarantined'
                   WHERE operation_id = ? AND state IN ('prepared', 'authorized', 'uncertain')""",
                (operation_id,),
            )
            if cursor.rowcount != 1:
                raise Conflict("Primary critical operation cannot be quarantined")
        else:
            raise ProtocolError(f"Unsupported authoritative event type: {event_type}")

    def _require_current_witness_authorization(
        self, operation: sqlite3.Row, operation_id: str, operation_digest: str,
    ) -> None:
        """Fail closed unless W, not the P projection, currently authorizes this effect."""
        if self.context.recovery_required:
            raise Closed("Synthetic effect is closed while recovery or quarantine is required")
        witness = Witness(self.context)
        w_state = witness.state()
        if w_state["closed"]:
            raise Closed("Witness W is closed")
        if (operation["state"] not in {"authorized", "result_recorded"}
                or operation["witness_authorization_generation"] is None):
            raise Closed("Primary has no projected Witness authorization")
        p_state = self.state()
        if (p_state["generation"], p_state["head_digest"]) != (
            w_state["generation"], w_state["head_digest"]
        ):
            raise Closed("Primary projection is not current with Witness W")
        w_operation = witness.operation(operation_id)
        if (w_operation is None or w_operation["operation_digest"] != operation_digest
                or w_operation["state"] not in {"authorized", "result_recorded"}
                or w_operation["authorized_generation"]
                != operation["witness_authorization_generation"]):
            raise Closed("Witness W does not currently authorize this synthetic effect")

    def execute_effect_once(self, operation_id: str, operation_digest: str) -> dict[str, Any]:
        with self.context._lock:
            operation_id = _check_uuid(operation_id)
            operation_digest = _check_digest(operation_digest, "operation_digest")
            with self._connect() as connection:
                with _transaction(connection):
                    operation = connection.execute(
                        "SELECT * FROM critical_operations WHERE operation_id = ?", (operation_id,)
                    ).fetchone()
                    if operation is None:
                        raise Closed("Primary has no projected Witness authorization")
                    if operation["operation_digest"] != operation_digest:
                        raise Conflict("Synthetic effect digest does not match authorization")
                    self._require_current_witness_authorization(
                        operation, operation_id, operation_digest
                    )
                    old = connection.execute(
                        "SELECT * FROM synthetic_effects WHERE operation_id = ?", (operation_id,)
                    ).fetchone()
                    if old:
                        if old["operation_digest"] != operation_digest:
                            raise Conflict("Synthetic effect ID conflicts with prior content")
                        return dict(old)
                    if operation["state"] != "authorized":
                        raise Closed("Primary has no projected Witness authorization")
                    result_digest = _digest(_canonical({
                        "effect": "synthetic-only",
                        "operation_id": operation_id,
                        "operation_digest": operation_digest,
                    }))
                    connection.execute(
                        "INSERT INTO synthetic_effects VALUES (?, ?, ?)",
                        (operation_id, operation_digest, result_digest),
                    )
                    return {
                        "operation_id": operation_id,
                        "operation_digest": operation_digest,
                        "result_digest": result_digest,
                    }

    def verify_integrity(self) -> dict[str, Any]:
        with self._connect() as connection:
            state = dict(connection.execute("SELECT * FROM authority_state WHERE id = 1").fetchone())
            events = [dict(row) for row in connection.execute("SELECT * FROM events ORDER BY generation")]
            previous = GENESIS
            for index, event in enumerate(events, 1):
                if event["generation"] != index or event["previous_digest"] != previous:
                    raise ProtocolError("Primary event sequence is incomplete")
                payload = json.loads(event["payload_json"])
                if _digest(_canonical(payload)) != event["payload_digest"]:
                    raise ProtocolError("Primary event payload digest mismatch")
                core = {
                    key: event[key] for key in
                    ("event_id", "generation", "previous_digest", "event_type", "operation_id", "payload_digest")
                }
                if _digest(_canonical(core)) != event["head_digest"]:
                    raise ProtocolError("Primary event head digest mismatch")
                previous = event["head_digest"]
            if len(events) != state["generation"] or previous != state["head_digest"]:
                raise ProtocolError("Primary state head does not match its event history")
            reservation_events = [
                event for event in events if event["event_type"] == "admission_reserved"
            ]
            reservations = [
                dict(row) for row in connection.execute("SELECT * FROM reservations")
            ]
            if len(reservation_events) != len(reservations):
                raise ProtocolError("Primary reservation projection does not match its events")
            for event in reservation_events:
                payload = json.loads(event["payload_json"])
                reservation = connection.execute(
                    "SELECT * FROM reservations WHERE operation_id = ?", (event["operation_id"],)
                ).fetchone()
                if reservation is None or (
                    reservation["identity_digest"] != payload["identity_digest"]
                    or reservation["reservation_no"] != payload["reservation_no"]
                    or reservation["witness_generation"] != event["generation"]
                ):
                    raise ProtocolError("Primary reservation projection is inconsistent")
            prepared_events = [
                event for event in events if event["event_type"] == "critical_prepared"
            ]
            operations = [
                dict(row) for row in connection.execute("SELECT * FROM critical_operations")
            ]
            if len(prepared_events) != len(operations):
                raise ProtocolError("Primary critical projection does not match its events")
            for event in prepared_events:
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?", (event["operation_id"],)
                ).fetchone()
                if operation is None:
                    raise ProtocolError("Primary critical operation is missing")
                related = [item for item in events if item["operation_id"] == event["operation_id"]]
                latest = related[-1]
                expected_state = {
                    "critical_prepared": "prepared",
                    "critical_authorized": "authorized",
                    "critical_result_recorded": "result_recorded",
                    "critical_uncertain": "uncertain",
                    "critical_quarantined": "quarantined",
                }[latest["event_type"]]
                if operation["state"] != expected_state:
                    raise ProtocolError("Primary critical projection state is inconsistent")
                authorization_events = [
                    item for item in related if item["event_type"] == "critical_authorized"
                ]
                if authorization_events and operation["witness_authorization_generation"] != (
                    authorization_events[0]["generation"]
                ):
                    raise ProtocolError("Primary authorization generation is inconsistent")
                result_events = [
                    item for item in related if item["event_type"] == "critical_result_recorded"
                ]
                if result_events:
                    result_payload = json.loads(result_events[-1]["payload_json"])
                    if operation["result_digest"] != result_payload["result_digest"]:
                        raise ProtocolError("Primary result digest is inconsistent")
                elif operation["result_digest"] is not None:
                    raise ProtocolError("Primary has a result without a result event")
            for effect in connection.execute("SELECT * FROM synthetic_effects"):
                effect = dict(effect)
                operation = connection.execute(
                    "SELECT * FROM critical_operations WHERE operation_id = ?",
                    (effect["operation_id"],),
                ).fetchone()
                if operation is None or operation["operation_digest"] != effect["operation_digest"]:
                    raise ProtocolError("Synthetic effect does not match a projected operation")
                has_authorization = connection.execute(
                    """SELECT 1 FROM events WHERE operation_id = ?
                       AND event_type = 'critical_authorized'""",
                    (effect["operation_id"],),
                ).fetchone()
                expected_effect_digest = _digest(_canonical({
                    "effect": "synthetic-only",
                    "operation_id": effect["operation_id"],
                    "operation_digest": effect["operation_digest"],
                }))
                if has_authorization is None or effect["result_digest"] != expected_effect_digest:
                    raise ProtocolError("Synthetic effect lacks an authorization or valid result proof")
            return {"valid": True, **state, "event_count": len(events)}

    @_synchronized
    def close(self) -> None:
        with self._connect() as connection:
            with _transaction(connection):
                connection.execute("UPDATE authority_state SET closed = 1 WHERE id = 1")


@dataclass(frozen=True)
class Consistency:
    coherent: bool
    witness_generation: int | None
    primary_generation: int | None
    witness_head: str | None
    primary_head: str | None
    freshness: str
    reason: str | None = None


class Coordinator:
    """Witness-first coordinator; never represents the two commits as atomic."""

    def __init__(self, context: LabContext):
        self.context = context
        self.witness = Witness(context)
        self.primary = Primary(context)

    def _ensure_open(self, operation_id: str | None = None) -> None:
        if self.context.recovery_required:
            raise Closed("Recovery is closed until independent freshness evidence is supplied")
        if self.context.pending_operation_id is not None and operation_id != self.context.pending_operation_id:
            raise Closed("An interrupted operation must be explicitly resumed with the same ID")
        if self.witness.state()["closed"] or self.primary.state()["closed"]:
            raise Closed("A domain is closed")

    @contextmanager
    def _operation_scope(self, operation_id: str) -> Iterator[None]:
        self._ensure_open(operation_id)
        self._set_pending(operation_id)
        try:
            yield
        except InjectedFailure:
            raise
        except Conflict:
            self.context.pending_operation_id = None
            raise
        except Exception as error:
            self.context._set_recovery_required(True)
            self.context.recovery_reason = str(error)
            self.context.incident_recoverable_in_process = False
            raise

    def _fault(self, point: FailurePoint | None, expected: FailurePoint) -> None:
        if point == expected:
            self.context._set_recovery_required(True)
            self.context.recovery_reason = point.value
            self.context.incident_recoverable_in_process = True
            raise InjectedFailure(point.value)

    def _set_pending(self, operation_id: str) -> None:
        self.context.pending_operation_id = operation_id

    def _clear_pending(self) -> None:
        self.context.pending_operation_id = None
        self.context._set_recovery_required(False)
        self.context.recovery_reason = None
        self.context.incident_recoverable_in_process = False

    def _witness_primary_consistency(self) -> Consistency:
        w = self.witness.verify_integrity()
        p = self.primary.verify_integrity()
        if p["generation"] > w["generation"]:
            return Consistency(False, w["generation"], p["generation"], w["head_digest"],
                               p["head_digest"], "not_demonstrable", "Primary is ahead of Witness")
        for generation in range(1, p["generation"] + 1):
            we = self.witness.event(generation)
            pe = self._primary_event(generation)
            if not we or not pe or (we["event_id"], we["head_digest"]) != (
                pe["event_id"], pe["head_digest"]
            ):
                return Consistency(False, w["generation"], p["generation"], w["head_digest"],
                                   p["head_digest"], "not_demonstrable", "Conflicting history or fork")
        equal = p["generation"] == w["generation"] and p["head_digest"] == w["head_digest"]
        return Consistency(equal, w["generation"], p["generation"], w["head_digest"],
                           p["head_digest"], "not_demonstrable" if self.context.recovery_required
                           else "nominal_session_only",
                           None if equal else "Primary projection is incomplete")

    def _primary_event(self, generation: int) -> dict[str, Any] | None:
        with self.primary._connect() as connection:
            row = connection.execute("SELECT * FROM events WHERE generation = ?", (generation,)).fetchone()
            return dict(row) if row else None

    def inspect(self) -> Consistency:
        """Read-only consistency check; matching histories do not prove freshness."""
        try:
            result = self._witness_primary_consistency()
        except (sqlite3.DatabaseError, ProtocolError) as error:
            self.context._set_recovery_required(True)
            self.context.recovery_reason = str(error)
            return Consistency(False, None, None, None, None, "not_demonstrable", str(error))
        if not result.coherent:
            self.context._set_recovery_required(True)
            self.context.recovery_reason = result.reason
        return result

    def _project_event(
        self, event: dict[str, Any], before: FailurePoint | None,
        before_commit: FailurePoint | None, after: FailurePoint | None,
        before_point: FailurePoint, before_commit_point: FailurePoint,
        after_point: FailurePoint,
    ) -> None:
        self._fault(before, before_point)
        try:
            self.primary.apply(event, fail_before_commit=before_commit == before_commit_point)
        except InjectedFailure:
            self.context._set_recovery_required(True)
            self.context.recovery_reason = before_commit_point.value
            self.context.incident_recoverable_in_process = True
            raise
        self._fault(before_commit, before_commit_point)
        self._fault(after, after_point)

    def reserve_admission(
        self, operation_id: str, identity_digest: str, expected_generation: int,
        *, fail_at: FailurePoint | None = None,
    ) -> dict[str, Any]:
        with self.context._lock:
            _check_uuid(operation_id)
            with self._operation_scope(operation_id):
                self._fault(fail_at, FailurePoint.ADMISSION_BEFORE_W_COMMIT)
                reservation, committed = self.witness.reserve(
                    operation_id, identity_digest, expected_generation
                )
                if committed:
                    self._fault(fail_at, FailurePoint.ADMISSION_AFTER_W_COMMIT)
                    self._project_event(
                        reservation["event"], fail_at, fail_at, fail_at,
                        FailurePoint.ADMISSION_BEFORE_P_APPLY,
                        FailurePoint.ADMISSION_BEFORE_P_COMMIT,
                        FailurePoint.ADMISSION_AFTER_P_COMMIT,
                    )
                self._fault(fail_at, FailurePoint.ADMISSION_FINAL_RECONCILIATION)
                consistency = self._witness_primary_consistency()
                if not consistency.coherent:
                    self.context._set_recovery_required(True)
                    self.context.recovery_reason = consistency.reason
                    raise Closed("Reservation is committed in W but not fully reconciled in P")
                self._clear_pending()
                return {
                    **{key: reservation[key] for key in
                       ("operation_id", "identity_digest", "reservation_no", "state", "generation")},
                    "witness_committed": True,
                    "primary_projected": True,
                    "atomic_across_domains": False,
                }

    def _commit_and_project(
        self, event: dict[str, Any] | None, fail_at: FailurePoint | None,
        before: FailurePoint, after_w: FailurePoint, before_p: FailurePoint, after_p: FailurePoint,
        operation_id: str,
    ) -> None:
        if event is None:
            return
        self._fault(fail_at, before)
        self._fault(fail_at, after_w)
        self._project_event(event, fail_at, fail_at, before_p, after_p)
        self._set_pending(operation_id)

    def run_critical(
        self, operation_id: str, operation_digest: str, receipt_digest: str, hold_digest: str,
        expected_generation: int, *, confirmed: bool = False, hold_clear: bool = False,
        fail_at: FailurePoint | None = None,
    ) -> dict[str, Any]:
        """Run synthetic prepare -> authorize -> effect -> result, with independent commits."""
        if confirmed is not True or hold_clear is not True:
            raise Closed("Synthetic confirmation and clear-hold preconditions are required")
        with self.context._lock:
            operation_id = _check_uuid(operation_id)
            with self._operation_scope(operation_id):
                self._fault(fail_at, FailurePoint.PREPARE_BEFORE_W_COMMIT)
                prepared, event = self.witness.prepare(
                    operation_id, operation_digest, receipt_digest, hold_digest, expected_generation
                )
                self._set_pending(operation_id)
                if event:
                    self._fault(fail_at, FailurePoint.PREPARE_AFTER_W_COMMIT)
                    self._project_event(
                        event, fail_at, fail_at, fail_at,
                        FailurePoint.PREPARE_BEFORE_P_APPLY,
                        FailurePoint.PREPARE_BEFORE_P_COMMIT,
                        FailurePoint.PREPARE_AFTER_P_COMMIT,
                    )

                current = self.witness.state()["generation"]
                self._fault(fail_at, FailurePoint.AUTHORIZE_BEFORE_W_COMMIT)
                authorized, event = self.witness.authorize(operation_id, current)
                if event:
                    self._fault(fail_at, FailurePoint.AUTHORIZE_AFTER_W_COMMIT)
                    self._project_event(
                        event, fail_at, fail_at, fail_at,
                        FailurePoint.AUTHORIZE_BEFORE_P_APPLY,
                        FailurePoint.AUTHORIZE_BEFORE_P_COMMIT,
                        FailurePoint.AUTHORIZE_AFTER_P_COMMIT,
                    )
                elif authorized["state"] not in {"authorized", "result_recorded"}:
                    raise Closed("No durable authorization exists")

                self._fault(fail_at, FailurePoint.EFFECT_BEFORE)
                effect = self.primary.execute_effect_once(operation_id, operation_digest)
                self._set_pending(operation_id)
                self._fault(fail_at, FailurePoint.EFFECT_AFTER)

                current = self.witness.state()["generation"]
                self._fault(fail_at, FailurePoint.RESULT_BEFORE_W_COMMIT)
                result, event = self.witness.record_result(
                    operation_id, effect["result_digest"], current
                )
                if event:
                    self._set_pending(operation_id)
                    self._fault(fail_at, FailurePoint.RESULT_AFTER_W_COMMIT)
                    self._project_event(
                        event, fail_at, fail_at, fail_at,
                        FailurePoint.RESULT_BEFORE_P_APPLY,
                        FailurePoint.RESULT_BEFORE_P_COMMIT,
                        FailurePoint.RESULT_AFTER_P_COMMIT,
                    )
                self._fault(fail_at, FailurePoint.CRITICAL_FINAL_RECONCILIATION)
                consistency = self._witness_primary_consistency()
                if not consistency.coherent:
                    self.context._set_recovery_required(True)
                    self.context.recovery_reason = consistency.reason
                    raise Closed("Critical operation is not fully reconciled")
                self._clear_pending()
                return {
                    "operation_id": operation_id,
                    "state": result["state"],
                    "result_digest": effect["result_digest"],
                    "effect_count": 1,
                    "witness_committed": True,
                    "primary_projected": True,
                    "atomic_across_domains": False,
                }

    def quarantine_operation(self, operation_id: str, evidence_digest: str) -> dict[str, Any]:
        """Persist a synthetic quarantine in W, then project it independently into P."""
        operation_id = _check_uuid(operation_id)
        evidence_digest = _check_digest(evidence_digest, "evidence_digest")
        with self.context._lock:
            with self._operation_scope(operation_id):
                current = self.witness.state()["generation"]
                operation, event = self.witness.quarantine(
                    operation_id, evidence_digest, current
                )
                self._set_pending(operation_id)
                if event is not None:
                    self._project_event(
                        event, None, None, None,
                        FailurePoint.PREPARE_BEFORE_P_APPLY,
                        FailurePoint.PREPARE_BEFORE_P_COMMIT,
                        FailurePoint.PREPARE_AFTER_P_COMMIT,
                    )
                self.context._set_recovery_required(True)
                self.context.recovery_reason = "critical operation quarantined"
                self.context.incident_recoverable_in_process = False
                self.context.pending_operation_id = None
                self.witness.close()
                self.primary.close()
                return {"operation_id": operation_id, "state": operation["state"]}

    def mark_uncertain(self, operation_id: str, evidence_digest: str) -> dict[str, Any]:
        """Record uncertainty in W and P and leave both domains closed."""
        operation_id = _check_uuid(operation_id)
        evidence_digest = _check_digest(evidence_digest, "evidence_digest")
        with self.context._lock:
            with self._operation_scope(operation_id):
                current = self.witness.state()["generation"]
                operation = self.witness.mark_uncertain(
                    operation_id, evidence_digest, current
                )
                event = self.witness.event(operation["generation"])
                if event is None:
                    raise ProtocolError("Uncertain Witness event is missing")
                self.primary.apply(event)
                self.context._set_recovery_required(True)
                self.context.recovery_reason = "critical operation uncertain"
                self.context.incident_recoverable_in_process = False
                self.context.pending_operation_id = None
                self.witness.close()
                self.primary.close()
                return {"operation_id": operation_id, "state": operation["state"]}

    def resume_operation(self, operation_id: str, **same_request: Any) -> dict[str, Any]:
        """Explicit same-ID retry after an in-process injected failure only."""
        operation_id = _check_uuid(operation_id)
        if not self.context.incident_recoverable_in_process:
            raise Closed("Restored or reopened labs cannot resume without external freshness proof")
        if self.context.pending_operation_id != operation_id:
            raise Closed("Only the exact interrupted operation ID can be resumed")
        self.context._set_recovery_required(False)
        consistency = self.inspect()
        if consistency.reason and consistency.reason != "Primary projection is incomplete":
            self.context._set_recovery_required(True)
            raise Closed("Conflicting history blocks explicit same-ID recovery")
        if consistency.witness_generation is None or consistency.primary_generation is None:
            self.context._set_recovery_required(True)
            raise Closed("Integrity could not be established")
        # A P-behind-W prefix can be projected only from W's exact committed event.
        if consistency.primary_generation < consistency.witness_generation:
            for generation in range(consistency.primary_generation + 1, consistency.witness_generation + 1):
                event = self.witness.event(generation)
                if event is None or event["operation_id"] != operation_id:
                    self.context._set_recovery_required(True)
                    raise Closed("Unrelated missing Witness event requires quarantine")
                self.primary.apply(event)
            self.context._set_recovery_required(False)
            self.context.recovery_reason = None
        if "identity_digest" in same_request:
            result = self.reserve_admission(
                operation_id, same_request["identity_digest"],
                self.witness.state()["generation"],
            )
        elif {
            "operation_digest", "receipt_digest", "hold_digest", "expected_generation",
            "confirmed", "hold_clear",
        } <= set(same_request):
            result = self.run_critical(
                operation_id,
                same_request["operation_digest"],
                same_request["receipt_digest"],
                same_request["hold_digest"],
                self.witness.state()["generation"],
                confirmed=same_request["confirmed"],
                hold_clear=same_request["hold_clear"],
            )
        else:
            self.context._set_recovery_required(True)
            raise ProtocolError("Explicit same-operation request data is required")
        return result

    @_synchronized
    def require_recovery_evidence(self, evidence: object | None = None) -> None:
        """No verifier for real external freshness exists in this laboratory."""
        self.context._set_recovery_required(True)
        self.context.recovery_reason = "external freshness verifier not implemented"
        raise Closed("Recovery remains closed: independent freshness evidence is not implemented")

    @_synchronized
    def close(self, reason: str) -> None:
        self.context._set_recovery_required(True)
        self.context.recovery_reason = reason
        self.context.incident_recoverable_in_process = False
        self.witness.close()
        self.primary.close()


def create_snapshot(context: LabContext, source_path: Path, snapshot_path: Path) -> None:
    """Create a coherent SQLite snapshot via the backup API, never a hot file copy."""
    _lab_guard()
    _require_marker(context.root)
    source = _inside(context.root, source_path, must_exist=True)
    target = _inside(context.root, snapshot_path, must_exist=False)
    if target.exists():
        raise LabGuardError("Snapshot destination must not already exist")
    if source not in {context.witness_path, context.primary_path}:
        raise LabGuardError("Snapshot source must be the explicitly opened W or P database")
    domain = "W" if source == context.witness_path else "P"
    target.parent.mkdir(parents=True, exist_ok=True)
    _inside(context.root, target, must_exist=False)
    with _connect(source, context.root, domain) as source_connection:
        destination = sqlite3.connect(target, isolation_level=None)
        try:
            source_connection.backup(destination)
        finally:
            destination.close()


def restore_snapshot(
    context: LabContext, snapshot_path: Path, target_path: Path, *, domain: str,
) -> None:
    """Restore a synthetic snapshot and permanently close this context for recovery."""
    _lab_guard()
    _require_marker(context.root)
    if domain not in {"W", "P"}:
        raise LabGuardError("Restore domain must be explicitly W or P")
    target_expected = context.witness_path if domain == "W" else context.primary_path
    snapshot = _inside(context.root, snapshot_path, must_exist=True)
    target = _inside(context.root, target_path, must_exist=True)
    if target != target_expected:
        raise LabGuardError("Restore target must match the explicitly selected domain file")
    with context._lock:
        context._set_recovery_required(True)
        context.recovery_reason = f"{domain} snapshot restore"
        context.incident_recoverable_in_process = False
        _connect(snapshot, context.root, domain).close()
        with _connect(snapshot, context.root, domain) as source:
            with _connect(target, context.root, domain) as destination:
                source.backup(destination)


def tamper_for_test(context: LabContext, domain: str, sql: str, parameters: tuple[Any, ...] = ()) -> None:
    """Controlled corruption helper used only by the synthetic test suite."""
    _lab_guard()
    if domain not in {"W", "P"}:
        raise LabGuardError("Domain must be explicitly W or P")
    path = context.witness_path if domain == "W" else context.primary_path
    with context._lock:
        with _connect(path, context.root, domain) as connection:
            with _transaction(connection):
                connection.execute(sql, parameters)
