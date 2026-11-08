"""Conservative reconciliation; never infer rollback from a COMMIT exception."""
import hashlib
import os
import re
import stat

from fastapi import HTTPException
from sqlalchemy import create_engine, or_, select, text
from sqlalchemy.pool import NullPool

from ..models import Document
from ..security_audit import emit

STORAGE_NAME = re.compile(r'[0-9a-f]{32}\.(?:pdf|txt)\Z')


def cleanup_file(path):
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        emit('system.file_cleanup.failed', reason_code='cleanup_failed')
        return False


def discard_session(session):
    # rollback() alone can return a DBAPI connection still in INTRANS to the pool
    # after a failed driver COMMIT. Close/invalidate that physical connection first.
    session.invalidate()


def durable_document_state(bind, identity):
    """Return present/absent/unknown, with a fresh physical connection, never app pool.

    The shared writer fence waits for an earlier server-side COMMIT to finish.
    A plain SELECT absence would not prove rollback while that COMMIT is pending.
    No business data is changed and no COMMIT is retried.
    """
    engine = None
    try:
        postgres = bind.dialect.name == 'postgresql'
        options = ({'connect_timeout': 3, 'options': '-c statement_timeout=3000 -c lock_timeout=3000'}
                   if postgres else {'timeout': 3})
        engine = create_engine(bind.url, poolclass=NullPool, connect_args=options)
        with engine.connect() as connection:
            if postgres:
                fence = connection.execute(text("SELECT id FROM ai_budgets WHERE id='development' FOR UPDATE")).scalar_one_or_none()
                if fence is None:
                    return 'unknown'
            else:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            rows = connection.execute(select(Document.id, Document.owner_id, Document.storage_name,
                Document.size_bytes, Document.sha256).where(or_(Document.id == identity[0],
                                                               Document.storage_name == identity[2]))).all()
            if not rows:
                return 'absent'
            return 'present' if len(rows) == 1 and tuple(rows[0]) == identity else 'unknown'
    except Exception:
        # Intentionally no exception message, DSN, SQL, identifiers or file paths.
        return 'unknown'
    finally:
        if engine is not None:
            engine.dispose()


def identity_of(document):
    return (document.id, document.owner_id, document.storage_name, document.size_bytes, document.sha256)


def retained_storage_admission(session, settings, incoming_size):
    """Under the shared writer fence, bound *unreferenced* retained sources.

    Separate safety backpressure, not a change to account quotas. Never auto-purge.
    Crash .part files remain subject to SEC10-02's existing temporary budget.
    """
    referenced = set(session.scalars(select(Document.storage_name)))
    count = size = 0
    try:
        for path in settings.storage_dir.iterdir():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise OSError('unsafe storage entry')
            if path.name not in referenced and not path.name.endswith('.part'):
                count += 1
                size += info.st_size
        if (count >= settings.document_retention_max_files or
                size + incoming_size > settings.document_retention_max_bytes):
            raise HTTPException(503, 'Stockage en attente de verification')
    except OSError:
        raise HTTPException(503, 'Verification du stockage indisponible') from None


def check_document_integrity(engine, root):
    """Read-only, aggregate report. Run with writers stopped for a coherent snapshot.

    No original names, paths, document/owner IDs, SQL or error strings leave here.
    No symlinks followed, no automatic cleanup or repair, including stale parts.
    """
    report = dict(checked=0, missing=0, size_mismatch=0, sha256_mismatch=0,
                  unsafe_identity=0, unreferenced=0, partials=0, tombstones=0,
                  io_errors=0, database_errors=0)
    expected = set()
    independent = None
    try:
        if root.is_symlink() or not root.is_dir():
            raise OSError('unsafe storage root')
        independent = create_engine(engine.url, poolclass=NullPool)
        with independent.connect() as connection:
            if engine.dialect.name == 'postgresql':
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            else:
                connection.exec_driver_sql('PRAGMA query_only=ON')
            for name, size, digest in connection.execute(select(Document.storage_name, Document.size_bytes, Document.sha256)):
                report['checked'] += 1
                if not STORAGE_NAME.fullmatch(name):
                    report['unsafe_identity'] += 1
                    continue
                expected.add(name)
                try:
                    path = root / name
                    info = path.lstat()
                    if not stat.S_ISREG(info.st_mode):
                        report['unsafe_identity'] += 1
                        continue
                    # O_NOFOLLOW closes the lstat/open race on Linux; Windows is
                    # supported for local tests, not the production audit platform.
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
                    with os.fdopen(descriptor, 'rb') as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            report['unsafe_identity'] += 1
                            continue
                        total = 0
                        actual = hashlib.sha256()
                        while data := stream.read(65536):
                            actual.update(data)
                            total += len(data)
                    report['size_mismatch'] += int(total != size)
                    report['sha256_mismatch'] += int(actual.hexdigest() != digest)
                except FileNotFoundError:
                    report['missing'] += 1
                except OSError:
                    report['io_errors'] += 1
        for path in root.iterdir():
            if path.name not in expected:
                key = ('partials' if path.name.endswith('.part') else
                       'tombstones' if path.name.endswith('.deleted') else 'unreferenced')
                report[key] += 1
    except OSError:
        report['io_errors'] += 1
    except Exception:
        report['database_errors'] += 1
    finally:
        if independent is not None:
            independent.dispose()
    report['consistent'] = not any(value for key, value in report.items() if key != 'checked')
    return report
