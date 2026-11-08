"""SQLite backup-API snapshots for the five lifecycle stores."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from uuid import UUID

from .lifecycle_backup_lock import lifecycle_store_lock


STORES = {
    "registry": ("LIFECYCLE_REGISTRY_PATH", 1, {
        "requests", "admission_watermark", "document_erasures",
    }),
    "witness": ("LIFECYCLE_CONFIRMATION_PATH", 1, {
        "confirmations", "admissions",
    }),
    "authenticated": ("LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH", 2, {
        "confirmations", "admissions", "synthetic_transitions",
        "hold_mirrors", "authenticated_header",
    }),
    "holds": ("LIFECYCLE_HOLDS_PATH", 2, {
        "confirmations", "admissions", "holds_v2", "hold_decisions_v2",
    }),
    "admission_anchor": ("LIFECYCLE_ADMISSION_ANCHOR_PATH", 2, {
        "confirmations", "admissions", "admission_anchor",
    }),
}


class SnapshotError(ValueError):
    pass


def configured_store_paths() -> dict[str, Path]:
    result: dict[str, Path] = {}
    seen: set[Path] = set()
    directories: set[Path] = set()
    raw_root = os.environ.get("LIFECYCLE_DATA_ROOT")
    if not raw_root:
        raise SnapshotError("Persistent lifecycle volume root is not configured")
    root = Path(raw_root)
    if not root.is_absolute() or root.resolve() != root or root.is_symlink():
        raise SnapshotError("Canonical lifecycle volume root required")
    for name, (variable, _, _) in STORES.items():
        raw = os.environ.get(variable)
        if not raw:
            raise SnapshotError(f"Lifecycle store path is not configured: {name}")
        path = Path(raw)
        if not path.is_absolute() or path.resolve() != path:
            raise SnapshotError(f"Canonical absolute lifecycle store path required: {name}")
        try:
            path.relative_to(root)
        except ValueError:
            raise SnapshotError(f"Lifecycle store must be under the persistent volume: {name}") from None
        if path in seen:
            raise SnapshotError(f"Lifecycle store paths must be distinct: {name}")
        seen.add(path)
        if any(path.parent == directory or path.parent.is_relative_to(directory)
               or directory.is_relative_to(path.parent) for directory in directories):
            raise SnapshotError("Lifecycle stores require separate directories")
        directories.add(path.parent)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise SnapshotError(f"Symlinked lifecycle store path: {name}")
        try:
            info = path.lstat()
        except FileNotFoundError:
            raise SnapshotError(f"Lifecycle store is missing: {name}") from None
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (os.name == "posix" and info.st_mode & 0o077)):
            raise SnapshotError(f"Private regular lifecycle store required: {name}")
        parent = path.parent.stat()
        if (not stat.S_ISDIR(parent.st_mode)
                or (os.name == "posix" and parent.st_mode & 0o077)):
            raise SnapshotError(f"Private lifecycle store directory required: {name}")
    for name, (variable, _, _) in STORES.items():
        result[name] = Path(os.environ[variable])
    return result


def _schema(connection: sqlite3.Connection, name: str) -> dict[str, object]:
    _, user_version, expected_tables = STORES[name]
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SnapshotError(f"SQLite integrity check failed: {name}")
    actual_version = connection.execute("PRAGMA user_version").fetchone()[0]
    actual_tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }
    if actual_version != user_version or actual_tables != expected_tables:
        raise SnapshotError(f"Unexpected or incomplete SQLite schema: {name}")
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
    return {
        "user_version": actual_version,
        "tables": sorted(actual_tables),
        "journal_mode": journal_mode,
    }


def _snapshot(path: Path, name: str) -> tuple[Path, dict[str, object]]:
    source_uri = path.as_uri() + "?mode=ro"
    temporary = tempfile.TemporaryDirectory(prefix=".snapshot-", dir=path.parent)
    target_path = Path(temporary.name) / "snapshot.sqlite"
    source = sqlite3.connect(source_uri, uri=True, timeout=10)
    target = sqlite3.connect(target_path)
    try:
        if os.name == 'posix':
            target_path.chmod(0o600)
        source_schema = _schema(source, name)
        source.backup(target)
        copied_schema = _schema(target, name)
        if (copied_schema["user_version"] != source_schema["user_version"]
                or copied_schema["tables"] != source_schema["tables"]):
            raise SnapshotError(f"SQLite schema changed during capture: {name}")
        if target.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
            raise SnapshotError(f"Could not normalize SQLite snapshot: {name}")
        target.commit()
        target.close()
        source.close()
        return target_path, {**source_schema, "sha256": _sha256_file(target_path),
                             "_temporary": temporary}
    except BaseException:
        target.close()
        source.close()
        temporary.cleanup()
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_snapshot_archive(output=None) -> dict[str, object]:
    capture_id = os.environ.get("LIFECYCLE_CAPTURE_ID", "")
    try:
        if str(UUID(capture_id)) != capture_id:
            raise ValueError
    except ValueError:
        raise SnapshotError("Canonical capture identifier required") from None
    snapshots: dict[str, tuple[Path, dict[str, object]]] = {}
    try:
        with lifecycle_store_lock(exclusive=True, required=True):
            paths = configured_store_paths()
            source_identities = {
                name: (path.stat().st_dev, path.stat().st_ino) for name, path in paths.items()
            }
            for name in sorted(STORES):
                snapshots[name] = _snapshot(paths[name], name)
            if any((path.stat().st_dev, path.stat().st_ino) != source_identities[name]
                   for name, path in paths.items()):
                raise SnapshotError("Lifecycle store path changed during capture")
            metadata = {
                "format": 1,
                "capture_id": capture_id,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "stores": {
                    name: {
                        "snapshot": f"stores/{name}.sqlite",
                        **{key: value for key, value in schema.items() if key != "_temporary"},
                    }
                    for name, (_, schema) in snapshots.items()
                },
            }
            stream = output or sys.stdout.buffer
            with tarfile.open(fileobj=stream, mode="w|gz") as archive:
                data = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
                info = tarfile.TarInfo("metadata.json")
                info.size = len(data)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(data))
                for name, (snapshot_path, _) in snapshots.items():
                    archive.add(snapshot_path, f"stores/{name}.sqlite", recursive=False)
        return metadata
    finally:
        for _, schema in snapshots.values():
            schema["_temporary"].cleanup()


if __name__ == "__main__":
    write_snapshot_archive()
