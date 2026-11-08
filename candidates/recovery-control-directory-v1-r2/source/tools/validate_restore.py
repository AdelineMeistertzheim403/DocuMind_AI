"""Restore a complete snapshot only into a marked, local, isolated quarantine lab."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

if __package__:
    from .verify_snapshot import verify_capture, verify_snapshot
    from .lifecycle_key_policy import validate_key_member
    from .restore_pgvector import (
        filtered_restore_list, preparation_url, prepare_extension,
        restore_environment, validate_lab_url, lab_connect_args,
    )
else:
    from verify_snapshot import verify_capture, verify_snapshot
    from lifecycle_key_policy import validate_key_member
    from restore_pgvector import (
        filtered_restore_list, preparation_url, prepare_extension,
        restore_environment, validate_lab_url, lab_connect_args,
    )




def seal_restored_registration(engine):
    """Fail-closed sealer for offline restored quotas.

    This function is intended for *synthetic/offline* restore verification.
    It never opens admissions; it only enforces `closed=true` when the public
    quota table exists.
    """
    if os.environ.get(LAB_ENV) != "isolated":
        raise ValueError('Explicit isolated restore lab mode required for quota sealing')
    validate_lab_url(engine.url.set(database="documind_restore_admin"))
    with engine.begin() as connection:
        database = connection.execute(text('SELECT current_database()')).scalar_one()
        if not isinstance(database, str) or not re.fullmatch(r'documind_restore_[a-f0-9]{12}', database):
            raise ValueError('Refuse to seal a non-restore database')
        if connection.scalar(text("SELECT current_setting('cluster_name')")) != "documind-restore-lab":
            raise ValueError('Refuse to seal outside the isolated restore cluster')
        quota_table = connection.execute(text("SELECT to_regclass('public.public_registration_quota')")).scalar_one()
        if quota_table is None:
            raise ValueError('Restored public quota table is missing')
        rows = connection.execute(text(
            "SELECT id, issued_count, closed FROM public.public_registration_quota FOR UPDATE"
        )).all()
        if (len(rows) != 1 or rows[0].id != 'public'
                or type(rows[0].issued_count) is not int or rows[0].issued_count < 0
                or type(rows[0].closed) is not bool):
            raise ValueError('Restored public quota row is missing or invalid')
        issued_count = rows[0].issued_count
        connection.execute(text("UPDATE public.public_registration_quota SET closed=true WHERE id='public'"))
        checked = connection.execute(text(
            "SELECT issued_count, closed FROM public.public_registration_quota WHERE id='public'"
        )).one()
        if checked.closed is not True or checked.issued_count != issued_count:
            raise ValueError('Restored public quota closure was not effective')
    with engine.connect() as connection:
        checked = connection.execute(text(
            "SELECT issued_count, closed FROM public.public_registration_quota WHERE id='public'"
        )).one()
        if checked.closed is not True or checked.issued_count != issued_count:
            raise ValueError('Committed restored public quota closure was not effective')
    return {'issued_count': issued_count, 'closed': True}
LAB_ENV = "DOCUMIND_RESTORE_LAB"
LAB_MARKER = ".synthetic-only"
LAB_MARKER_CONTENT = b"documind-isolated-restore-lab-v1\n"


LIFECYCLE_KEYS_ARCHIVE = "lifecycle-keys.tar.gz"
LIFECYCLE_KEY_PATHS = ("keys/authentication.key", "keys/admission.key")


def _validate_lab(snapshot: Path, database: str, root: Path):
    if os.environ.get(LAB_ENV) != "isolated":
        raise ValueError("Explicit isolated restore lab mode is required")
    if not re.fullmatch(r"documind_restore_[a-f0-9]{12}", database):
        raise ValueError("Use a unique documind_restore_<12 hex> database name")
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise ValueError("Canonical existing restore lab directory required")
    if os.name == "posix" and (
        root.stat().st_uid != os.geteuid() or stat.S_IMODE(root.stat().st_mode) & 0o077
    ):
        raise ValueError("Private restorer-owned lab directory required")
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
    return validate_lab_url(url)


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


def _extract_lifecycle_keys(snapshot: Path, manifest: dict, lifecycle_root: Path) -> None:
    keys = manifest.get('lifecycle_keys')
    expected_names = set(LIFECYCLE_KEY_PATHS)
    if (not isinstance(keys, dict) or set(keys) != expected_names):
        raise ValueError('Lifecycle key inventory missing or invalid')
    keys_dir = lifecycle_root / 'keys'
    if lifecycle_root.resolve() != lifecycle_root or lifecycle_root.is_symlink():
        raise ValueError('Canonical lifecycle restore root required')
    # Never reuse a pre-existing key directory or follow a directory alias.
    keys_dir.mkdir(mode=0o700)
    with tarfile.open(snapshot / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        if (names != expected_names or len(members) != len(expected_names)
                or any(not member.isfile() or member.issym() or member.islnk() for member in members)):
            raise ValueError('Lifecycle key archive must contain exactly the two key files')
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe lifecycle key archive member')
            expected = keys[member.name]
            if (not isinstance(expected, dict)
                    or type(expected.get('size')) is not int or expected['size'] < 1
                    or type(expected.get('mode')) is not int
                    or not isinstance(expected.get('sha256'), str)
                    or not re.fullmatch(r'[a-f0-9]{64}', expected['sha256'])):
                raise ValueError('Lifecycle key inventory entry is invalid')
            validate_key_member(member, expected)
            mode = member.mode
            if member.size != expected['size'] or mode != expected['mode']:
                raise ValueError('Lifecycle key metadata mismatch')
            source = archive.extractfile(member)
            if source is None:
                raise ValueError('Lifecycle key archive entry is unreadable')
            payload = source.read()
            if len(payload) != member.size or hashlib.sha256(payload).hexdigest() != expected['sha256']:
                raise ValueError('Lifecycle key checksum mismatch')
            target = keys_dir / Path(member.name).name
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(payload)
                output.flush()
                _seal_lab_key(output.fileno())


def _seal_lab_key(descriptor):
    if os.name == 'posix':
        # Lab files belong to the restorer, not to archive UID/GID or an API user.
        os.fchmod(descriptor, 0o400)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise ValueError('Private restored lifecycle key required')


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


def _write_quarantine(target, report):
    path = target / "quarantine.json"
    temporary = target / ".quarantine.json.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == "posix":
        temporary.chmod(0o600)
    temporary.replace(path)


def _restore(snapshot: Path, database: str, root: Path, url, *, pgvector_version=None):
    _validate_lab(snapshot, database, root)
    validate_lab_url(url)
    connect_args = lab_connect_args(url)
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_capture(snapshot, manifest, require_s2=True)
    target = root / database
    if target.exists() or target.is_symlink():
        raise ValueError("Restore evidence path already exists; inspect it before retrying")
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise ValueError("Local pg_restore is required; no Compose or default database fallback is allowed")

    privileged_url = preparation_url(url, pgvector_version) if pgvector_version is not None else None
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args=connect_args)
    state = {
        "format": 1, "database": database, "capture_id": manifest["capture_id"],
        "status": "incomplete", "validation_complete": False, "reusable": False,
        "critical_mutations_allowed": False, "opening_authorized": False,
        "s2_recovery_authorized": False, "quota": None,
    }
    created_target = False
    try:
        with admin.connect() as connection:
            if connection.scalar(text("SELECT current_setting('cluster_name')")) != "documind-restore-lab":
                raise ValueError("PostgreSQL cluster is not explicitly marked as an isolated restore lab")
            role = connection.execute(text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname=current_user"
            )).one()
            if role.rolsuper or role.rolcreaterole or role.rolreplication or role.rolbypassrls or not role.rolcreatedb:
                raise ValueError("Restore role must have CREATEDB but no elevated role privileges")
            if connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
            ):
                raise ValueError("Restore database already exists; nothing changed")

            target.mkdir(mode=0o700)
            created_target = True
            _write_quarantine(target, state)
            (target / "recovery-state.json").write_text(
                '{"format":1,"state":"quarantined"}\n', encoding="utf-8")
            if os.name == "posix":
                (target / "recovery-state.json").chmod(0o600)
            restore_list = filtered_restore_list(pg_restore, snapshot / "database.dump", target)
            if (restore_list is not None) != (privileged_url is not None):
                raise ValueError("pgvector dump requires explicit preparation; non-vector dump must not request it")
            connection.execute(text(f'CREATE DATABASE "{database}"'))

        if privileged_url is not None:
            prepare_extension(privileged_url, database, url.username, pgvector_version)
        database_url = url.set(database=database)
        arguments = [pg_restore, "--host", url.host, "--port", str(url.port),
                     "--username", url.username, "--dbname", database,
                     "--no-owner", "--exit-on-error"]
        if restore_list is not None:
            arguments += ["--use-list", str(restore_list)]
        arguments.append(str(snapshot / "database.dump"))
        engine = create_engine(database_url, connect_args=connect_args)
        try:
            try:
                subprocess.run(arguments, env=restore_environment(url),
                               capture_output=True, check=True, timeout=3600)
                # Prove fidelity, including the original quota, BEFORE closing the copy.
                verify_snapshot(snapshot, database, database_url=database_url,
                                database_connect_args=connect_args)
            finally:
                state["quota"] = seal_restored_registration(engine)
        finally:
            engine.dispose()
        report = _restore_contents(snapshot, database, target, database_url, manifest)
        if report["quota"] != state["quota"]:
            raise ValueError("Restored quota changed after sealing")
        report["pgvector_prepared_version"] = pgvector_version
        report["validation_complete"] = report["status"] == "quarantined"
        report["reusable"] = False
        _write_quarantine(target, report)
        return report
    except BaseException as error:
        if created_target:
            state.update(status="failed", error_type=type(error).__name__)
            try:
                _write_quarantine(target, state)
            except OSError:
                # The original incomplete marker still prohibits reuse if storage is unavailable.
                pass
        raise
    finally:
        admin.dispose()


def _restore_contents(snapshot, database, target, database_url, manifest):
    documents_root = target / "documents"
    _extract_archive(snapshot / "documents.tar.gz", documents_root, documents=True)
    lifecycle_root = target / "lifecycle"
    _extract_archive(snapshot / "lifecycle.sqlite.tar.gz", lifecycle_root, documents=False)

    if int(manifest.get('backup_format_version', 0) or 0) >= 5:
        _extract_lifecycle_keys(snapshot, manifest, lifecycle_root)

    # Preserve the captured latch for audit, but always enforce quarantine for restored copies.
    shutil.copy2(snapshot / 'recovery-state.json', target / 'source-recovery-state.json')
    (target / 'recovery-state.json').write_text('{"format":1,"state":"quarantined"}\n', encoding='utf-8')
    if os.name == 'posix':
        (target / 'recovery-state.json').chmod(0o600)
        (target / 'source-recovery-state.json').chmod(0o600)

    engine = create_engine(database_url, connect_args=lab_connect_args(database_url))
    try:
        with engine.connect() as connection:
            quota_exists = connection.scalar(text("SELECT to_regclass('public.public_registration_quota')"))
            quota = None
            if quota_exists is not None:
                rows = connection.execute(
                    text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")
                ).all()
                if (len(rows) != 1 or type(rows[0].issued_count) is not int
                        or rows[0].issued_count < 0 or rows[0].closed is not True):
                    raise ValueError("Restored public quota is missing or incoherent")
                quota = {"issued_count": rows[0].issued_count, "closed": rows[0].closed}
            if quota is None:
                raise ValueError("Restored public quota table is missing")
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
            "lifecycle_keys_restored": 2 if int(manifest.get("backup_format_version", 0) or 0) >= 5 else 0,
            "lifecycle_key_restore_policy": "restorer_owned_0400_in_private_lab",
            "resurrection_checks": resurrections,
            "status": "blocked" if conflicts else "quarantined",
            "critical_mutations_allowed": False,
            "api_attached": None,
            "api_attachment_verified": False,
            "s2_recovery_authorized": False,
            "opening_authorized": False,
        }
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--database", required=True)
    parser.add_argument("--restore-root", required=True, type=Path)
    parser.add_argument("--prepare-pgvector-version",
                        help="Explicit privileged preparation on the new lab DB only; requires a distinct preparation URL")
    args = parser.parse_args()
    _validate_lab(args.snapshot, args.database, args.restore_root)
    url = _isolated_url()
    result = _restore(args.snapshot, args.database, args.restore_root, url,
                      pgvector_version=args.prepare_pgvector_version)
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "blocked":
        raise SystemExit("Resurrection evidence requires reconciliation; restored copy remains quarantined")


if __name__ == "__main__":
    main()
