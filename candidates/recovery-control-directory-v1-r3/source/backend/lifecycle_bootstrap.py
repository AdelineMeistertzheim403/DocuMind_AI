"""Provision the five lifecycle SQLite stores for synthetic backups.

This module is intended for local recipe/lab environments. It creates missing
SQLite stores and key material inside the configured lifecycle volume, then
verifies schemas match backend.lifecycle_snapshot expectations.

It never talks to the network or the application database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sqlite3

from .lifecycle_admissions import AdmissionAnchor
from .lifecycle_authenticated import AuthenticatedConfirmationStore
from .lifecycle_durability import ConfirmationStore, _read_private_key
from .lifecycle_holds import HoldStore
from .lifecycle_registry import Registry
from .lifecycle_snapshot import STORES, SnapshotError, configured_store_paths, _schema


def _ensure_key(path: Path) -> bytes:
    if path.exists():
        return _read_private_key(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, secrets.token_bytes(32))
    finally:
        os.close(descriptor)
    return _read_private_key(path)


def _verify_store(path: Path, name: str) -> None:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        _schema(connection, name)
    finally:
        connection.close()


def ensure_lifecycle_bootstrap() -> dict[str, object]:
    root = Path(os.environ.get("LIFECYCLE_DATA_ROOT", ""))
    if not root.is_absolute():
        raise SnapshotError("Persistent lifecycle volume root is not configured")

    created: list[str] = []

    registry_path = Path(os.environ["LIFECYCLE_REGISTRY_PATH"])
    witness_path = Path(os.environ["LIFECYCLE_CONFIRMATION_PATH"])
    authenticated_path = Path(os.environ["LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH"])
    holds_path = Path(os.environ["LIFECYCLE_HOLDS_PATH"])
    anchor_path = Path(os.environ["LIFECYCLE_ADMISSION_ANCHOR_PATH"])

    for path in (registry_path, witness_path, authenticated_path, holds_path, anchor_path):
        if not path.is_absolute():
            raise SnapshotError("Canonical absolute lifecycle store path required")
        try:
            path.relative_to(root)
        except ValueError:
            raise SnapshotError("Lifecycle store must be under the persistent volume") from None
        path.parent.mkdir(parents=True, exist_ok=True)

    auth_key_path = Path(os.environ.get("LIFECYCLE_AUTHENTICATION_KEY_PATH", ""))
    admission_key_path = Path(os.environ.get("LIFECYCLE_ADMISSION_KEY_PATH", ""))
    if not auth_key_path.is_absolute() or not admission_key_path.is_absolute():
        raise SnapshotError("Lifecycle key paths are not configured")
    auth_key = _ensure_key(auth_key_path)
    admission_key = _ensure_key(admission_key_path)

    if not registry_path.exists():
        Registry(registry_path).initialize()
        created.append("registry")

    if not witness_path.exists():
        ConfirmationStore(witness_path).initialize()
        created.append("witness")

    authenticated = AuthenticatedConfirmationStore(authenticated_path, auth_key, "documind-local-v2")
    if not authenticated_path.exists():
        authenticated.initialize()
        created.append("authenticated")

    if not holds_path.exists():
        HoldStore(holds_path, authenticated).initialize()
        created.append("holds")

    if not anchor_path.exists():
        AdmissionAnchor(anchor_path, admission_key).initialize()
        created.append("admission_anchor")

    verified_paths = configured_store_paths()
    for name in STORES:
        _verify_store(verified_paths[name], name)

    return {"created": created, "verified": sorted(STORES.keys())}


def main() -> int:
    report = ensure_lifecycle_bootstrap()
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
