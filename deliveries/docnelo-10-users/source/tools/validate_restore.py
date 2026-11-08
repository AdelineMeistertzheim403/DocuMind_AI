"""Restore a complete snapshot only into a marked, local, isolated quarantine lab."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

if __package__:
    from .verify_snapshot import verify_capture, verify_snapshot
else:
    from verify_snapshot import verify_capture, verify_snapshot


LAB_ENV = "DOCUMIND_RESTORE_LAB"
LAB_MARKER = ".synthetic-only"
LAB_MARKER_CONTENT = b"documind-isolated-restore-lab-v1\n"


def _validate_lab(snapshot: Path, database: str, root: Path):
    if os.environ.get(LAB_ENV) != "isolated":
        raise ValueError("Explicit isolated restore lab mode is required")
    if not re.fullmatch(r"documind_restore_[a-f0-9]{12}", database):
        raise ValueError("Use a unique documind_restore_<12 hex> database name")
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise ValueError("Canonical existing restore lab directory required")
    marker = root / LAB_MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != LAB_MARKER_CONTENT:
        raise ValueError("Synthetic-only restore lab marker missing or invalid")
    if snapshot.resolve() != snapshot or snapshot.is_symlink() or not snapshot.is_dir():
        raise ValueError("Canonical snapshot directory required")
    manifest = snapshot / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Regular backup manifest required")


def _isolated_url():
    raw = os.environ.get("DOCUMIND_RESTORE_DATABASE_URL")
    if not raw:
        raise ValueError("DOCUMIND_RESTORE_DATABASE_URL is required")
    url = make_url(raw)
    if (url.get_backend_name() != "postgresql"
            or url.host not in {"127.0.0.1", "::1"}
            or url.port is None or not 1 <= url.port <= 65535
            or not url.username or url.database != "documind_restore_admin"):
        raise ValueError("Restore database must be the explicit loopback documind_restore_admin database")
    return url


def _extract_archive(archive_path: Path, destination: Path, *, documents: bool):
    expected_prefix = "documents" if documents else "lifecycle"
    destination.mkdir(mode=0o700)
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            allowed = (path.parts[0] == expected_prefix) if documents else (
                path.parts[0] in {"metadata.json", "stores"})
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or not allowed or member.issym() or member.islnk()):
                raise ValueError("Unsafe restore archive member")
            if documents:
                relative = path.parts[1:]
            elif path.parts[0] == "stores" and len(path.parts) == 2:
                relative = (Path(path.parts[1]).stem, path.parts[1])
            elif path.parts[0] == "metadata.json":
                relative = path.parts
            else:
                raise ValueError("Unexpected lifecycle archive path")
            target = destination.joinpath(*relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            if not member.isfile():
                raise ValueError("Restore archive contains unsupported member type")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Restore archive member cannot be read")
            with target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if os.name == "posix":
                target.chmod(0o600)


def check_resurrection_denials(engine, registry_path: Path, documents_path: Path):
    """Report any restored active account/document contradicted by a lifecycle tombstone."""
    with engine.connect() as connection:
        restored_documents = {
            (str(row.id), row.storage_name)
            for row in connection.execute(text("SELECT id,storage_name FROM documents"))
        }
        restored_users = {
            (str(row.id), str(row.owner_id), row.disabled_at)
            for row in connection.execute(text("SELECT id,owner_id,disabled_at FROM users"))
        }

    import sqlite3
    registry = sqlite3.connect(f"file:{registry_path.as_posix()}?mode=ro", uri=True)
    try:
        account_receipts = registry.execute(
            "SELECT user_id,owner_id,state FROM requests WHERE kind='erasure'"
        ).fetchall()
        document_receipts = registry.execute(
            "SELECT document_id,storage_name,state FROM document_erasures"
        ).fetchall()
    finally:
        registry.close()

    account_resurrections = 0
    unlinked_account_receipts = 0
    pending_account_operations = 0
    for user_id, owner_id, state in account_receipts:
        try:
            user_key = str(UUID(str(user_id)))
            owner_key = str(UUID(str(owner_id)))
        except (ValueError, TypeError, AttributeError):
            unlinked_account_receipts += 1
            continue
        if state not in {"deactivated", "active_erased", "closed"}:
            pending_account_operations += 1
        if any((user_key == user or owner_key == owner) and disabled_at is None
               for user, owner, disabled_at in restored_users):
            account_resurrections += 1
    active_by_id = {identifier for identifier, _ in restored_documents}
    storage_by_name = {storage_name for _, storage_name in restored_documents}
    document_resurrections = sum(
        1 for document_id, storage_name, state in document_receipts
        if state == "active_erased" and (
            not isinstance(storage_name, str)
            or not re.fullmatch(r"[0-9a-f]{32}\.(?:pdf|txt)", storage_name)
            or str(document_id) in active_by_id or storage_name in storage_by_name
            or (documents_path / storage_name).exists()
            or os.path.lexists(documents_path / storage_name)
        )
    )
    pending_document_operations = sum(
        1 for _, _, state in document_receipts
        if state not in {"active_erased"}
    )
    return {
        "account_receipts_checked": len(account_receipts),
        "document_tombstones_checked": len(document_receipts),
        "account_resurrections": account_resurrections,
        "unlinked_account_receipts": unlinked_account_receipts,
        "pending_account_operations": pending_account_operations,
        "document_resurrections": document_resurrections,
        "pending_document_operations": pending_document_operations,
        "opening_authorized": False,
    }


def _restore(snapshot: Path, database: str, root: Path, url):
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_capture(snapshot, manifest, require_s2=True)
    target = root / database
    if target.exists() or target.is_symlink():
        raise ValueError("Restore evidence path already exists; inspect it before retrying")
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise ValueError("Local pg_restore is required; no Compose or default database fallback is allowed")

    admin_url = url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            if connection.scalar(text("SELECT current_setting('cluster_name')")) != "documind-restore-lab":
                raise ValueError("PostgreSQL cluster is not explicitly marked as an isolated restore lab")
            if connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
            ):
                raise ValueError("Restore database already exists; nothing changed")
            connection.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        admin.dispose()

    target.mkdir(mode=0o700)
    database_url = url.set(database=database)
    restore_env = os.environ.copy()
    if url.password is not None:
        restore_env["PGPASSWORD"] = url.password
    arguments = [pg_restore, "--host", url.host, "--port", str(url.port),
                 "--username", url.username, "--dbname", database,
                 "--no-owner", "--exit-on-error", str(snapshot / "database.dump")]
    subprocess.run(arguments, env=restore_env, capture_output=True, check=True, timeout=3600)
    verify_snapshot(snapshot, database, database_url=database_url)

    documents_root = target / "documents"
    _extract_archive(snapshot / "documents.tar.gz", documents_root, documents=True)
    lifecycle_root = target / "lifecycle"
    _extract_archive(snapshot / "lifecycle.sqlite.tar.gz", lifecycle_root, documents=False)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            quota_exists = connection.scalar(text("SELECT to_regclass('public.public_registration_quota')"))
            quota = None
            if quota_exists is not None:
                rows = connection.execute(
                    text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")
                ).all()
                if len(rows) != 1 or type(rows[0].issued_count) is not int or rows[0].issued_count < 0:
                    raise ValueError("Restored public quota is missing or incoherent")
                quota = {"issued_count": rows[0].issued_count, "closed": rows[0].closed}
            document_rows = connection.execute(
                text("SELECT storage_name,sha256,size_bytes FROM documents")
            ).all()
        expected_document_files = {row.storage_name for row in document_rows}
        actual_document_files = set()
        for path in documents_root.rglob("*"):
            if path.is_symlink():
                raise ValueError("Symlink in restored document archive")
            if path.is_file():
                actual_document_files.add(path.relative_to(documents_root).as_posix())
            elif not path.is_dir():
                raise ValueError("Unsupported restored document entry")
        for name, digest, size in document_rows:
            if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{32}\.(?:pdf|txt)", name):
                raise ValueError("Restored document identity is unsafe")
            source_path = documents_root / name
            path = source_path.resolve()
            if source_path.is_symlink() or not path.is_relative_to(documents_root.resolve()):
                raise ValueError("Restored document path escapes quarantine")
            with path.open("rb") as source:
                if path.stat().st_size != size or hashlib.file_digest(source, "sha256").hexdigest() != digest:
                    raise ValueError("Restored document checksum mismatch")
        resurrections = check_resurrection_denials(
            engine, lifecycle_root / "registry" / "registry.sqlite", documents_root)
        missing_documents = sorted(expected_document_files - actual_document_files)
        unreferenced_documents = sorted(actual_document_files - expected_document_files)
        conflicts = (resurrections["account_resurrections"]
                     + resurrections["document_resurrections"]
                     + resurrections["unlinked_account_receipts"]
                     + resurrections["pending_account_operations"]
                     + resurrections["pending_document_operations"]
                     + len(missing_documents) + len(unreferenced_documents))
        report = {
            "format": 1,
            "capture_id": manifest["capture_id"],
            "database": database,
            "quota": quota,
            "documents_verified": len(document_rows),
            "missing_documents": len(missing_documents),
            "unreferenced_documents": len(unreferenced_documents),
            "lifecycle_stores_restored": 5,
            "resurrection_checks": resurrections,
            "status": "blocked" if conflicts else "quarantined",
            "critical_mutations_allowed": False,
            "api_attached": False,
            "s2_recovery_authorized": False,
            "opening_authorized": False,
        }
        (target / "quarantine.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if os.name == "posix":
            (target / "quarantine.json").chmod(0o600)
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--database", required=True)
    parser.add_argument("--restore-root", required=True, type=Path)
    args = parser.parse_args()
    _validate_lab(args.snapshot, args.database, args.restore_root)
    url = _isolated_url()
    result = _restore(args.snapshot, args.database, args.restore_root, url)
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "blocked":
        raise SystemExit("Resurrection evidence requires reconciliation; restored copy remains quarantined")


if __name__ == "__main__":
    main()
