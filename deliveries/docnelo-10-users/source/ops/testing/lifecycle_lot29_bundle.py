"""Synthetic-only encrypted backup and quarantine restore for lifecycle SQLite stores."""
from __future__ import annotations

import base64
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Mapping, Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from backend.lifecycle_admissions import AdmissionAnchor
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore, canonical
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry


LAB_ENV = "PHASE154L29_LAB"
LAB_MARKER = ".synthetic-only"
LAB_MARKER_CONTENT = b"documind-phase-15-4-lot-2-9-synthetic-only\n"
FORMAT_VERSION = 1
MAX_BUNDLE_SIZE = 256 * 1024 * 1024
MAX_COMPONENT_SIZE = 128 * 1024 * 1024
DOMAIN = "documind-local-v2"

COMPONENTS = {
    "registry": {
        "setting": "lifecycle_registry_path",
        "identity": "lifecycle-registry",
        "user_version": 1,
        "tables": {"requests", "admission_watermark", "document_erasures"},
    },
    "witness": {
        "setting": "lifecycle_confirmation_path",
        "identity": "admission-witness-and-legacy-confirmations",
        "user_version": 1,
        "tables": {"confirmations", "admissions"},
    },
    "authenticated": {
        "setting": "lifecycle_authenticated_confirmation_path",
        "identity": "authenticated-transitions-and-hold-mirrors",
        "user_version": 2,
        "tables": {"synthetic_transitions", "hold_mirrors", "authenticated_header"},
    },
    "holds": {
        "setting": "lifecycle_holds_path",
        "identity": "scoped-a20-holds",
        "user_version": 2,
        "tables": {"holds_v2", "hold_decisions_v2"},
    },
    "admission_anchor": {
        "setting": "lifecycle_admission_anchor_path",
        "identity": "authenticated-admission-anchor",
        "user_version": 2,
        "tables": {"confirmations", "admissions", "admission_anchor"},
    },
}

_COMPONENT_KEYS = frozenset(COMPONENTS)
_KEY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_CONFIRMATION_BASE_TABLES = {
    "confirmations", "admissions",
}

COMPONENTS["witness"]["tables"] = _CONFIRMATION_BASE_TABLES
COMPONENTS["authenticated"]["tables"] = _CONFIRMATION_BASE_TABLES | {
    "synthetic_transitions", "hold_mirrors", "authenticated_header",
}
COMPONENTS["holds"]["tables"] = _CONFIRMATION_BASE_TABLES | {"holds_v2", "hold_decisions_v2"}
COMPONENTS["admission_anchor"]["tables"] = _CONFIRMATION_BASE_TABLES | {"admission_anchor"}


class BundleError(ValueError):
    """A synthetic backup or restore failed closed."""


class ConsistencyVerifier(Protocol):
    def verify(self, stores: Mapping[str, Path]) -> Mapping[str, object]: ...


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bundle_key(master_key: bytes, backup_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=UUID(backup_id).bytes,
        info=b"documind-phase-15-4-lot-2-9-bundle-v1",
    ).derive(master_key)


def _check_lab_root(root: Path) -> Path:
    root = Path(root).absolute()
    if os.environ.get(LAB_ENV) != "isolated":
        raise BundleError("Explicit synthetic laboratory mode is required")
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise BundleError("Canonical synthetic laboratory root required")
    marker = root / LAB_MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != LAB_MARKER_CONTENT:
        raise BundleError("Synthetic laboratory marker missing or invalid")
    return root


def _path_in_lab(path: Path, root: Path, *, must_exist: bool, expect: str = "file") -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise BundleError("Absolute laboratory paths required")
    path = path.absolute()
    try:
        path.relative_to(root)
    except ValueError:
        raise BundleError("Path outside synthetic laboratory") from None
    if path.resolve() != path or any(part.is_symlink() for part in (path, *path.parents) if part.exists()):
        raise BundleError("Symlinked laboratory paths are forbidden")
    if must_exist and not (path.is_dir() if expect == "directory" else path.is_file()):
        raise BundleError(f"Required laboratory {expect} is missing")
    if must_exist and expect == "file":
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise BundleError("Required SQLite store is not a non-empty regular file")
    return path


def configured_store_paths(settings: object, lab_root: Path) -> dict[str, Path]:
    """Inventory the five configured SQLite files without creating or defaulting any."""
    root = _check_lab_root(lab_root)
    paths: dict[str, Path] = {}
    seen: list[Path] = []
    for name, metadata in COMPONENTS.items():
        raw = getattr(settings, metadata["setting"], None)
        if raw is None:
            raise BundleError(f"Required lifecycle store is not configured: {name}")
        path = _path_in_lab(Path(raw), root, must_exist=True)
        if any(path == prior or os.path.samefile(path, prior) for prior in seen):
            raise BundleError(f"Lifecycle store paths must be distinct: {name}")
        paths[name] = path
        seen.append(path)
    return paths


def _validate_keyring(keyring: Mapping[str, bytes], key_id: str) -> bytes:
    if (not isinstance(keyring, Mapping) or not isinstance(key_id, str)
            or not _KEY_ID.fullmatch(key_id)
            or not key_id.startswith(("test-", "synthetic-"))):
        raise BundleError("Explicit synthetic keyring and key identifier required")
    key = keyring.get(key_id)
    if not isinstance(key, bytes) or len(key) != 32:
        raise BundleError("A 256-bit synthetic backup key is required")
    if any(not isinstance(name, str) or not _KEY_ID.fullmatch(name)
           or not name.startswith(("test-", "synthetic-"))
           or not isinstance(value, bytes) or len(value) != 32
           for name, value in keyring.items()):
        raise BundleError("Invalid synthetic keyring")
    return key


def _check_store_schema(connection: sqlite3.Connection, name: str) -> dict[str, object]:
    metadata = COMPONENTS[name]
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise BundleError(f"SQLite integrity check failed: {name}")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if version != metadata["user_version"] or tables != metadata["tables"]:
        raise BundleError(f"SQLite schema is missing, unexpected, or incompatible: {name}")
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
    if journal_mode not in {"delete", "truncate", "persist", "memory", "wal", "off"}:
        raise BundleError(f"Unsupported SQLite journal mode: {name}")
    return {"user_version": version, "tables": sorted(tables), "journal_mode": journal_mode}


def _snapshot_database(path: Path, name: str, timeout: float) -> tuple[bytes, dict[str, object]]:
    uri = path.as_uri() + "?mode=ro"
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=path.parent) as temporary:
        target_path = Path(temporary) / "snapshot.sqlite"
        source = sqlite3.connect(uri, uri=True, timeout=timeout)
        target = sqlite3.connect(target_path)
        try:
            schema = _check_store_schema(source, name)
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BundleError(f"SQLite backup integrity check failed: {name}")
            copied_schema = _check_store_schema(target, name)
            if (copied_schema["user_version"] != schema["user_version"]
                    or copied_schema["tables"] != schema["tables"]):
                raise BundleError(f"SQLite schema changed during capture: {name}")
            # Normalize the on-disk snapshot to rollback journaling so it can be
            # deserialized later without requiring a WAL sidecar.
            if target.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise BundleError(f"Could not normalize SQLite snapshot: {name}")
            target.commit()
        finally:
            target.close()
            source.close()
        return target_path.read_bytes(), schema


def _materialize_for_verification(
    payloads: Mapping[str, bytes], lab_root: Path
) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory(prefix="verify-", dir=lab_root / "work")
    base = Path(temporary.name)
    for name, payload in payloads.items():
        directory = base / name
        directory.mkdir(mode=0o700)
        destination = directory / (name + ".sqlite")
        with destination.open("xb") as stream:
            stream.write(payload)
        if os.name == "posix":
            destination.chmod(0o600)
    return temporary


class SyntheticLifecycleConsistencyVerifier:
    """Checks the existing SQLite cross-store relationships using test-only keys."""

    def __init__(self, authentication_key: bytes, admission_key: bytes):
        if not isinstance(authentication_key, bytes) or len(authentication_key) != 32:
            raise BundleError("Synthetic authentication key must be 256 bits")
        if not isinstance(admission_key, bytes) or len(admission_key) != 32:
            raise BundleError("Synthetic admission key must be 256 bits")
        self.authentication_key = authentication_key
        self.admission_key = admission_key

    @staticmethod
    def _expected_operation(kind: str, row: sqlite3.Row) -> dict[str, str]:
        identifier = row["id"] if kind == "account" else row["document_id"]
        if kind == "account":
            if row["kind"] != "erasure" or not row["user_id"] or not row["owner_id"]:
                raise BundleError("Incomplete account erasure receipt")
            receipt = {key: row[key] for key in ("id", "kind", "user_id", "owner_id", "received_at")}
            mutation, target = "account_deactivation", row["user_id"]
        else:
            if not row["owner_id"] or not row["storage_name"] or not row["requested_at"]:
                raise BundleError("Incomplete document erasure receipt")
            receipt = {key: row[key] for key in ("document_id", "owner_id", "storage_name", "requested_at")}
            mutation, target = "document_erasure", row["document_id"]
        operation_id = str(uuid5(NAMESPACE_URL, f"documind:receipt-v2:{kind}:{identifier}"))
        return {
            "id": operation_id,
            "type": mutation,
            "target": str(UUID(target)),
            "receipt_sha256": _sha256(canonical(receipt).encode("utf-8")),
        }

    def verify(self, stores: Mapping[str, Path]) -> Mapping[str, object]:
        if set(stores) != _COMPONENT_KEYS:
            raise BundleError("Cross-store verification requires the exact lifecycle store set")
        registry = Registry(stores["registry"])
        witness = ConfirmationStore(stores["witness"])
        authenticated = AuthenticatedConfirmationStore(
            stores["authenticated"], self.authentication_key, DOMAIN)
        holds = HoldStore(stores["holds"], authenticated)
        anchor = AdmissionAnchor(stores["admission_anchor"], self.admission_key)

        with registry.connection() as db:
            accounts = db.execute(
                "SELECT id,kind,user_id,owner_id,received_at,state FROM requests WHERE kind='erasure'"
            ).fetchall()
            documents = db.execute(
                "SELECT document_id,owner_id,storage_name,requested_at,state FROM document_erasures"
            ).fetchall()
            watermarks = db.execute(
                "SELECT id,issued_count,observed_at FROM admission_watermark"
            ).fetchall()
        with witness.connection() as db:
            legacy = db.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0]
        if legacy:
            raise BundleError("Legacy SHA-only confirmations require explicit review")
        if len(watermarks) > 1:
            raise BundleError("Admission watermark is ambiguous")

        expected_operations: dict[str, tuple[dict[str, str], str]] = {}
        for row in accounts:
            operation = self._expected_operation("account", row)
            expected_operations[operation["id"]] = (operation, row["state"])
        for row in documents:
            operation = self._expected_operation("document", row)
            expected_operations[operation["id"]] = (operation, row["state"])

        with authenticated.store.connection() as db:
            if (db.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0]
                    or db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]):
                raise BundleError("Unused confirmation-store tables contain unexpected records")
            actual_operations = {row[0] for row in db.execute(
                "SELECT DISTINCT operation FROM synthetic_transitions")}
        if actual_operations != set(expected_operations):
            raise BundleError("Lifecycle receipts and authenticated confirmations differ")

        allowed_states = {
            "received": {"confirmed"},
            "requested": {"confirmed"},
            "deactivated": {"result_recorded", "closed"},
            "active_erased": {"result_recorded", "closed"},
            "closed": {"result_recorded", "closed"},
        }
        for operation, receipt_state in expected_operations.values():
            state = authenticated.verify(operation)
            if state not in allowed_states.get(receipt_state, set()):
                raise BundleError("Lifecycle receipt state and HMAC history require reconciliation")

        with holds.store.connection() as db:
            if (db.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0]
                    or db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]):
                raise BundleError("Unused hold-store tables contain unexpected records")
            snapshots = holds._snapshots(db)
        authenticated.verify_holds(snapshots)

        entries = witness.admission_entries()
        anchor_state = anchor.check(entries)
        if anchor_state["state"] != "settled":
            raise BundleError("Admission reservation is pending and requires reconciliation")
        with anchor.store.connection() as db:
            if (db.execute("SELECT COUNT(*) FROM confirmations").fetchone()[0]
                    or db.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]):
                raise BundleError("Unused anchor-store tables contain unexpected records")
        if entries and not watermarks:
            raise BundleError("Admission watermark is required when the witness is populated")
        if watermarks:
            watermark = watermarks[0]
            if (watermark["id"] != 1 or type(watermark["issued_count"]) is not int
                    or not 0 <= watermark["issued_count"] <= 5
                    or not isinstance(watermark["observed_at"], str)
                    or watermark["issued_count"] != len(entries)):
                raise BundleError("Admission watermark, witness, and anchor differ")
            try:
                observed_at = datetime.fromisoformat(watermark["observed_at"])
                if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise BundleError("Admission watermark timestamp is invalid") from None

        return {
            "verified": True,
            "scope": sorted(_COMPONENT_KEYS),
            "account_receipts": len(accounts),
            "document_receipts": len(documents),
            "admissions": len(entries),
            "admission_watermark_present": bool(watermarks),
            "holds": len(snapshots),
            "legacy_confirmations": legacy,
            "freshness": "not_verified",
            "external_state_excluded": ["postgresql.public_registration_quota"],
        }


def _acquire_write_locks(paths: Mapping[str, Path], timeout: float) -> ExitStack:
    stack = ExitStack()
    try:
        for name in sorted(paths):
            path = paths[name]
            connection = sqlite3.connect(
                path.as_uri() + "?mode=rw", uri=True, timeout=timeout, isolation_level=None)
            stack.callback(connection.close)
            connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
            connection.execute("BEGIN IMMEDIATE")
        return stack
    except (OSError, sqlite3.Error):
        stack.close()
        raise BundleError("Could not establish a common SQLite writer fence") from None


def _verify_envelope(
    envelope: Mapping[str, object],
    master_key: bytes,
    verifier: SyntheticLifecycleConsistencyVerifier,
    lab_root: Path,
) -> tuple[dict[str, object], dict[str, bytes]]:
    manifest = _decrypt_manifest(envelope, master_key)
    _validate_manifest(manifest, envelope)
    payloads = _decrypt_components(envelope, manifest, master_key)
    with _materialize_for_verification(payloads, lab_root) as temporary:
        base = Path(temporary)
        materialized = {name: base / name / (name + ".sqlite") for name in payloads}
        consistency = verifier.verify(materialized)
    if not isinstance(consistency, Mapping) or consistency.get("verified") is not True:
        raise BundleError("Cross-store consistency could not be verified")
    if set(consistency.get("scope", ())) != _COMPONENT_KEYS:
        raise BundleError("Cross-store verifier did not cover the exact store set")
    return manifest, payloads


def create_bundle(
    settings: object,
    lab_root: Path,
    bundle_dir: Path,
    keyring: Mapping[str, bytes],
    key_id: str,
    verifier: ConsistencyVerifier,
    *,
    lock_timeout: float = 0.25,
) -> Path:
    """Capture all configured stores under SQLite write locks, then seal one bundle."""
    root = _check_lab_root(lab_root)
    paths = configured_store_paths(settings, root)
    output_dir = _path_in_lab(Path(bundle_dir), root, must_exist=True, expect="directory")
    if not output_dir.is_dir() or output_dir != root / "bundles":
        raise BundleError("Bundle output must be the existing laboratory bundles directory")
    if not isinstance(lock_timeout, (int, float)) or not 0 < lock_timeout <= 30:
        raise BundleError("Invalid SQLite lock timeout")
    key = _validate_keyring(keyring, key_id)
    if not isinstance(verifier, SyntheticLifecycleConsistencyVerifier):
        raise BundleError("The synthetic lifecycle consistency verifier is required")

    source_identities = {name: (path.stat().st_dev, path.stat().st_ino) for name, path in paths.items()}
    snapshots: dict[str, bytes] = {}
    schemas: dict[str, dict[str, object]] = {}
    lock_stack = _acquire_write_locks(paths, float(lock_timeout))
    try:
        for name in sorted(paths):
            snapshots[name], schemas[name] = _snapshot_database(paths[name], name, float(lock_timeout))
        if any((path.stat().st_dev, path.stat().st_ino) != source_identities[name]
               for name, path in paths.items()):
            raise BundleError("Lifecycle store path changed during capture")
    except (OSError, sqlite3.Error):
        raise BundleError("SQLite capture failed") from None
    finally:
        lock_stack.close()

    try:
        with _materialize_for_verification(snapshots, root) as temporary:
            base = Path(temporary)
            materialized = {
                name: base / name / (name + ".sqlite")
                for name in snapshots
            }
            consistency = verifier.verify(materialized)
        if not isinstance(consistency, Mapping) or consistency.get("verified") is not True:
            raise BundleError("Cross-store consistency could not be verified")
        if set(consistency.get("scope", ())) != _COMPONENT_KEYS:
            raise BundleError("Cross-store verifier did not cover the exact store set")
    except BundleError:
        raise
    except Exception as error:
        detail = str(error)
        if not detail or len(detail) > 96 or not re.fullmatch(r"[\w .-]+", detail):
            detail = type(error).__name__
        raise BundleError(f"Cross-store consistency verification failed: {detail}") from None

    backup_id = str(uuid4())
    boundary_id = str(uuid4())
    bundle_key = _bundle_key(key, backup_id)
    nonces: set[bytes] = set()

    def nonce() -> bytes:
        value = os.urandom(12)
        if value in nonces:
            raise BundleError("Synthetic AES-GCM nonce collision")
        nonces.add(value)
        return value

    encrypted_components: dict[str, dict[str, str]] = {}
    component_manifest: list[dict[str, object]] = []
    for name in sorted(snapshots):
        metadata = COMPONENTS[name]
        plaintext = snapshots[name]
        iv = nonce()
        aad = _canonical({
            "format_version": FORMAT_VERSION, "backup_id": backup_id,
            "component": name, "logical_identity": metadata["identity"],
            "key_id": key_id, "capture_boundary_id": boundary_id,
        })
        ciphertext = AESGCM(bundle_key).encrypt(iv, plaintext, aad)
        encrypted_components[name] = {
            "nonce": base64.b64encode(iv).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        component_manifest.append({
            "name": name,
            "logical_identity": metadata["identity"],
            "schema_version": schemas[name]["user_version"],
            "tables": schemas[name]["tables"],
            "journal_mode": schemas[name]["journal_mode"],
            "plaintext_sha256": _sha256(plaintext),
            "ciphertext_sha256": _sha256(ciphertext),
            "plaintext_size": len(plaintext),
            "ciphertext_size": len(ciphertext),
            "key_id": key_id,
            "capture_boundary_id": boundary_id,
            "state": "verified",
        })

    manifest = {
        "format_version": FORMAT_VERSION,
        "backup_id": backup_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_components": sorted(_COMPONENT_KEYS),
        "capture_boundary_id": boundary_id,
        "capture_method": "all_configured_sqlite_databases_locked_with_begin_immediate",
        "capture_lock_order": sorted(paths),
        "components": component_manifest,
        "integrity_verified": True,
        "completeness_verified": set(snapshots) == _COMPONENT_KEYS,
        "cross_store_consistency_verified": True,
        "consistency_scope": sorted(_COMPONENT_KEYS),
        "external_state_excluded": sorted(consistency.get("external_state_excluded", [])),
        "independent_freshness_verified": False,
        "critical_mutations_allowed": False,
    }
    manifest_bytes = _canonical(manifest)
    manifest_nonce = nonce()
    manifest_aad = _canonical({
        "format_version": FORMAT_VERSION, "backup_id": backup_id,
        "key_id": key_id, "purpose": "authenticated-manifest",
    })
    manifest_ciphertext = AESGCM(bundle_key).encrypt(manifest_nonce, manifest_bytes, manifest_aad)
    envelope = _canonical({
        "format_version": FORMAT_VERSION,
        "backup_id": backup_id,
        "key_id": key_id,
        "manifest_nonce": base64.b64encode(manifest_nonce).decode("ascii"),
        "manifest_ciphertext": base64.b64encode(manifest_ciphertext).decode("ascii"),
        "components": encrypted_components,
    })
    if len(envelope) > MAX_BUNDLE_SIZE:
        raise BundleError("Synthetic bundle exceeds size limit")
    try:
        _verify_envelope(json.loads(envelope), key, verifier, root)
    except BundleError:
        raise
    except Exception as error:
        raise BundleError(f"Encrypted bundle self-verification failed: {type(error).__name__}") from None

    final = output_dir / (backup_id + ".bundle")
    temporary = output_dir / (backup_id + ".part")
    temporary_created = False
    published_identity: tuple[int, int] | None = None

    def cleanup_owned_files() -> None:
        if temporary_created and temporary.parent == output_dir and temporary.is_file() and not temporary.is_symlink():
            temporary.unlink(missing_ok=True)
        if published_identity is not None and final.parent == output_dir and final.is_file() and not final.is_symlink():
            info = final.stat()
            if (info.st_dev, info.st_ino) == published_identity:
                final.unlink(missing_ok=True)

    try:
        with temporary.open("xb") as stream:
            temporary_created = True
            stream.write(envelope)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, final)
        info = final.stat()
        published_identity = (info.st_dev, info.st_ino)
        temporary.unlink()
        if os.name == "posix":
            descriptor = os.open(output_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        stored = _read_bundle(final, root)
        _verify_envelope(stored, key, verifier, root)
    except OSError as error:
        try:
            cleanup_owned_files()
        except OSError:
            pass
        raise BundleError(f"Could not publish synthetic bundle: {type(error).__name__}") from None
    except Exception as error:
        try:
            cleanup_owned_files()
        except OSError:
            pass
        if isinstance(error, BundleError):
            raise
        raise BundleError(f"Could not self-verify synthetic bundle: {type(error).__name__}") from None
    return final


def _decode_b64(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        raise BundleError(f"Invalid {label}")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error):
        raise BundleError(f"Invalid {label}") from None


def _read_bundle(path: Path, root: Path) -> dict[str, object]:
    path = _path_in_lab(path, root, must_exist=True)
    if path.parent != root / "bundles" or path.suffix != ".bundle":
        raise BundleError("Only a laboratory bundle may be restored")
    if path.stat().st_size > MAX_BUNDLE_SIZE:
        raise BundleError("Synthetic bundle exceeds size limit")
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise BundleError("Synthetic bundle is unreadable") from None
    expected = {"format_version", "backup_id", "key_id", "manifest_nonce",
                "manifest_ciphertext", "components"}
    if (not isinstance(data, dict) or set(data) != expected or data["format_version"] != FORMAT_VERSION
            or _canonical(data) != raw):
        raise BundleError("Unsupported or malformed synthetic bundle")
    if (not isinstance(data["backup_id"], str)
            or str(UUID(data["backup_id"])) != data["backup_id"]
            or path.stem != data["backup_id"]):
        raise BundleError("Synthetic bundle identity mismatch")
    if not isinstance(data["components"], dict) or set(data["components"]) != _COMPONENT_KEYS:
        raise BundleError("Synthetic bundle component set is incomplete or unexpected")
    return data


def _decrypt_manifest(envelope: Mapping[str, object], key: bytes) -> dict[str, object]:
    nonce = _decode_b64(envelope["manifest_nonce"], "manifest nonce")
    ciphertext = _decode_b64(envelope["manifest_ciphertext"], "manifest ciphertext")
    if len(nonce) != 12:
        raise BundleError("Invalid manifest nonce")
    aad = _canonical({
        "format_version": FORMAT_VERSION, "backup_id": envelope["backup_id"],
        "key_id": envelope["key_id"], "purpose": "authenticated-manifest",
    })
    bundle_key = _bundle_key(key, envelope["backup_id"])
    try:
        plaintext = AESGCM(bundle_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise BundleError("Manifest authentication failed") from None
    try:
        manifest = json.loads(plaintext)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BundleError("Authenticated manifest is malformed") from None
    if not isinstance(manifest, dict) or _canonical(manifest) != plaintext:
        raise BundleError("Authenticated manifest is not canonical")
    return manifest


def _validate_manifest(manifest: Mapping[str, object], envelope: Mapping[str, object]) -> list[dict[str, object]]:
    required = {
        "format_version", "backup_id", "created_at", "expected_components",
        "capture_boundary_id", "capture_method", "capture_lock_order", "components",
        "integrity_verified", "completeness_verified", "cross_store_consistency_verified",
        "consistency_scope", "external_state_excluded", "independent_freshness_verified",
        "critical_mutations_allowed",
    }
    if (set(manifest) != required or manifest["format_version"] != FORMAT_VERSION
            or not isinstance(manifest["external_state_excluded"], list)
            or "postgresql.public_registration_quota" not in manifest["external_state_excluded"]):
        raise BundleError("Manifest fields or version are incompatible")
    if manifest["backup_id"] != envelope["backup_id"]:
        raise BundleError("Manifest and bundle identities differ")
    if manifest["expected_components"] != sorted(_COMPONENT_KEYS):
        raise BundleError("Manifest does not describe the exact expected component set")
    if manifest["capture_method"] != "all_configured_sqlite_databases_locked_with_begin_immediate":
        raise BundleError("Unsupported capture-boundary claim")
    if set(manifest["capture_lock_order"]) != _COMPONENT_KEYS:
        raise BundleError("Capture lock list is incomplete")
    if (manifest["integrity_verified"] is not True or manifest["completeness_verified"] is not True
            or manifest["cross_store_consistency_verified"] is not True
            or manifest["consistency_scope"] != sorted(_COMPONENT_KEYS)
            or manifest["independent_freshness_verified"] is not False
            or manifest["critical_mutations_allowed"] is not False):
        raise BundleError("Manifest contains an unverified or unsafe status")
    try:
        timestamp = datetime.fromisoformat(manifest["created_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise BundleError("Invalid manifest timestamp") from None
    components = manifest["components"]
    if not isinstance(components, list) or len(components) != len(_COMPONENT_KEYS):
        raise BundleError("Manifest component list is incomplete")
    by_name = {}
    for item in components:
        if not isinstance(item, dict):
            raise BundleError("Malformed component metadata")
        name = item.get("name")
        if not isinstance(name, str) or name in by_name or name not in _COMPONENT_KEYS:
            raise BundleError("Duplicate or unknown component metadata")
        expected_fields = {
            "name", "logical_identity", "schema_version", "tables", "journal_mode",
            "plaintext_sha256", "ciphertext_sha256", "plaintext_size", "ciphertext_size",
            "key_id", "capture_boundary_id", "state",
        }
        if set(item) != expected_fields:
            raise BundleError(f"Malformed component metadata: {name}")
        metadata = COMPONENTS[name]
        if (type(item["schema_version"]) is not int
                or type(item["plaintext_size"]) is not int
                or type(item["ciphertext_size"]) is not int
                or not isinstance(item["plaintext_sha256"], str)
                or not isinstance(item["ciphertext_sha256"], str)
                or not isinstance(item["key_id"], str)
                or not isinstance(item["capture_boundary_id"], str)
                or item["logical_identity"] != metadata["identity"]
                or item["schema_version"] != metadata["user_version"]
                or item["tables"] != sorted(metadata["tables"])
                or item["capture_boundary_id"] != manifest["capture_boundary_id"]
                or item["key_id"] != envelope["key_id"] or item["state"] != "verified"
                or not isinstance(item["plaintext_size"], int) or not 0 < item["plaintext_size"] <= MAX_COMPONENT_SIZE
                or not isinstance(item["ciphertext_size"], int) or not 16 < item["ciphertext_size"] <= MAX_COMPONENT_SIZE
                or not re.fullmatch(r"[0-9a-f]{64}", item["plaintext_sha256"])
                or not re.fullmatch(r"[0-9a-f]{64}", item["ciphertext_sha256"])):
            raise BundleError(f"Invalid component metadata: {name}")
        by_name[name] = item
    if set(by_name) != _COMPONENT_KEYS:
        raise BundleError("Manifest component set is incomplete")
    return [by_name[name] for name in sorted(by_name)]


def _decrypt_components(
    envelope: Mapping[str, object], manifest: Mapping[str, object], key: bytes
) -> dict[str, bytes]:
    metadata_by_name = {item["name"]: item for item in manifest["components"]}
    bundle_key = _bundle_key(key, envelope["backup_id"])
    payloads: dict[str, bytes] = {}
    nonces: set[bytes] = {_decode_b64(envelope["manifest_nonce"], "manifest nonce")}
    for name in sorted(_COMPONENT_KEYS):
        item = metadata_by_name[name]
        component_envelope = envelope["components"][name]
        if not isinstance(component_envelope, dict) or set(component_envelope) != {"nonce", "ciphertext"}:
            raise BundleError(f"Malformed encrypted component: {name}")
        nonce = _decode_b64(component_envelope["nonce"], f"{name} nonce")
        ciphertext = _decode_b64(component_envelope["ciphertext"], f"{name} ciphertext")
        if len(nonce) != 12 or nonce in nonces:
            raise BundleError("Invalid or repeated AES-GCM nonce")
        nonces.add(nonce)
        if len(ciphertext) != item["ciphertext_size"] or _sha256(ciphertext) != item["ciphertext_sha256"]:
            raise BundleError(f"Encrypted component checksum mismatch: {name}")
        aad = _canonical({
            "format_version": FORMAT_VERSION, "backup_id": envelope["backup_id"],
            "component": name, "logical_identity": COMPONENTS[name]["identity"],
            "key_id": envelope["key_id"], "capture_boundary_id": manifest["capture_boundary_id"],
        })
        try:
            plaintext = AESGCM(bundle_key).decrypt(nonce, ciphertext, aad)
        except InvalidTag:
            raise BundleError(f"Component authentication failed: {name}") from None
        if (len(plaintext) != item["plaintext_size"]
                or _sha256(plaintext) != item["plaintext_sha256"]):
            raise BundleError(f"Plaintext component checksum mismatch: {name}")
        with sqlite3.connect(":memory:") as db:
            db.deserialize(plaintext)
            schema = _check_store_schema(db, name)
            if (schema["user_version"] != item["schema_version"]
                    or schema["tables"] != item["tables"]):
                raise BundleError(f"Restored SQLite schema differs from manifest: {name}")
        payloads[name] = plaintext
    return payloads


def _write_database(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == "posix":
        path.chmod(0o600)


def restore_bundle(
    bundle_path: Path,
    lab_root: Path,
    quarantine_root: Path,
    destination: Path,
    keyring: Mapping[str, bytes],
    verifier: ConsistencyVerifier,
) -> dict[str, object]:
    """Verify fully before publishing databases into a new synthetic quarantine."""
    root = _check_lab_root(lab_root)
    quarantine = _path_in_lab(Path(quarantine_root), root, must_exist=True, expect="directory")
    if not quarantine.is_dir() or quarantine != root / "quarantine":
        raise BundleError("Restore parent must be the existing laboratory quarantine directory")
    target = Path(destination).absolute()
    if target.parent != quarantine or target.exists() or target.is_symlink():
        raise BundleError("Restore destination must be a new direct child of laboratory quarantine")
    envelope = _read_bundle(Path(bundle_path), root)
    key = _validate_keyring(keyring, envelope["key_id"])
    if not isinstance(verifier, SyntheticLifecycleConsistencyVerifier):
        raise BundleError("The synthetic lifecycle consistency verifier is required")
    try:
        manifest, payloads = _verify_envelope(envelope, key, verifier, root)
    except BundleError:
        raise
    except Exception as error:
        detail = str(error)
        if not detail or len(detail) > 96 or not re.fullmatch(r"[\w .-]+", detail):
            detail = type(error).__name__
        raise BundleError(f"Restored cross-store consistency failed: {detail}") from None

    created_target = False
    names = {name: name + ".sqlite" for name in sorted(_COMPONENT_KEYS)}
    try:
        target.mkdir(mode=0o700)
        created_target = True
        marker = target / ".restore-incomplete"
        with marker.open("xb") as stream:
            stream.write(b"synthetic-quarantine-restore-incomplete\n")
            stream.flush()
            os.fsync(stream.fileno())
        for name, file_name in names.items():
            _write_database(target / file_name, payloads[name])
        marker.unlink()
        if os.name == "posix":
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception as error:
        try:
            if (created_target and target.parent == quarantine and target.is_dir()
                    and not target.is_symlink()):
                shutil.rmtree(target)
        except OSError:
            pass
        if isinstance(error, BundleError):
            raise
        raise BundleError(f"Quarantine restore failed: {type(error).__name__}") from None

    return {
        "backup_id": manifest["backup_id"],
        "format_version": FORMAT_VERSION,
        "restored_components": sorted(names),
        "integrity_verified": True,
        "completeness_verified": True,
        "cross_store_consistency_verified": True,
        "consistency_scope": sorted(_COMPONENT_KEYS),
        "external_state_excluded": manifest["external_state_excluded"],
        "independent_freshness_verified": False,
        "critical_mutations_allowed": False,
        "restore_path": str(target),
        "component_count": len(_COMPONENT_KEYS),
    }
