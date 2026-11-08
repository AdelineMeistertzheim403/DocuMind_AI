import hashlib
import os
import sqlite3
import stat
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, delete, func

from ..models import Analysis, Document, DocumentChunk, DocumentPage
from ..schemas import AnalysisResult
from .worker import run_worker
from .document_integrity import (cleanup_file, discard_session, durable_document_state,
                                 identity_of, retained_storage_admission, STORAGE_NAME)

from ..security_audit import emit, mark


def owned_document(session, document_id, owner_id, lock=False):
    query = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    document = session.scalar(query)
    if document is None:
        exists = session.scalar(select(Document.id).where(Document.id == document_id))
        mark('access.cross_owner.denied' if exists is not None else 'access.denied',
             'not_owner' if exists is not None else 'not_found')
        raise HTTPException(404, "Document introuvable")
    return document


def open_document_source(settings, document):
    """Open one verified source through its opaque storage name, never a client path."""
    root = Path(settings.storage_dir)
    if root.is_symlink() or not root.is_dir() or not STORAGE_NAME.fullmatch(document.storage_name):
        raise HTTPException(409, 'Le fichier original est indisponible ou son intégrité ne peut pas être vérifiée.')
    descriptor = None
    stream = None
    try:
        descriptor = os.open(root / document.storage_name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        stream = os.fdopen(descriptor, 'rb')
        descriptor = None
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != document.size_bytes:
            raise OSError('document source mismatch')
        actual = hashlib.sha256()
        while data := stream.read(64 * 1024):
            actual.update(data)
        if actual.hexdigest() != document.sha256:
            raise OSError('document source mismatch')
        stream.seek(0)
        return stream
    except (FileNotFoundError, OSError):
        if stream is not None:
            stream.close()
        elif descriptor is not None:
            os.close(descriptor)
        raise HTTPException(409, 'Le fichier original est indisponible ou son intégrité ne peut pas être vérifiée.') from None


def cleanup_failed_import(session, settings, owner_id, path, document_id=None):
    if not os.path.lexists(path):
        return True
    if not getattr(settings, 'lifecycle_durable_receipts_required', True):
        return cleanup_file(path)
    from sqlalchemy.exc import SQLAlchemyError
    from ..auth import User
    from ..lifecycle_durability import configured_coordinator, require_synthetic_mutation
    from ..lifecycle_holds import configured_hold_guard
    from ..lifecycle_registry import configured_registry
    try:
        require_synthetic_mutation(settings)
        coordinator = configured_coordinator(settings, configured_registry(settings))
        account = session.scalar(select(User.id).where(User.owner_id == owner_id))
        if account is None:
            raise ValueError('Import account scope cannot be verified')
        scopes = [('owner', owner_id), ('account', account)]
        if document_id is not None:
            scopes.append(('document', document_id))
        with configured_hold_guard(settings, scopes, coordinator):
            return cleanup_file(path)
    except (OSError, ValueError, sqlite3.Error, SQLAlchemyError):
        emit('system.file_cleanup.failed', reason_code='cleanup_failed')
        return False


def _owns_import_path(path, root, created_identity):
    """A cleanup must never adopt a pre-existing, replaced or linked file."""
    if created_identity is None or path.parent != root or root.is_symlink():
        return False
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and (info.st_dev, info.st_ino) == created_identity)
    except OSError:
        return False


def cleanup_failed_temporary(session, settings, owner_id, temporary, final,
                             created_identity, document_identity, bind):
    """Remove only our unpublished source, with verified SQL absence and holds.

    No receipt or mutation authorization is needed for an unpublished temporary,
    but an account/owner/document hold or unavailable authority still forbids it.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from ..auth import User
    from ..lifecycle_durability import configured_coordinator
    from ..lifecycle_holds import configured_hold_guard
    from ..lifecycle_registry import configured_registry
    if not os.path.lexists(temporary):
        return True
    try:
        if not _owns_import_path(temporary, final.parent, created_identity):
            raise ValueError('Temporary identity cannot be verified')
        # Check both possible durable storage names through fresh fenced connections.
        identity = document_identity or (UUID(hex=temporary.stem), owner_id, final.name, 0, '')
        if (durable_document_state(bind, identity) != 'absent'
                or durable_document_state(bind, (*identity[:2], temporary.name, *identity[3:])) != 'absent'):
            raise ValueError('Temporary publication cannot be excluded')
        registry = configured_registry(settings)
        if registry:
            with registry.connection() as ledger:
                if ledger.execute('SELECT 1 FROM document_erasures WHERE storage_name IN (?,?) LIMIT 1',
                                  (temporary.name, final.name)).fetchone():
                    raise ValueError('Temporary identity has a durable lifecycle history')
        coordinator = configured_coordinator(settings, registry)
        scopes = [('owner', owner_id)]
        if getattr(settings, 'lifecycle_durable_receipts_required', True):
            account = session.scalar(select(User.id).where(User.owner_id == owner_id))
            if account is None:
                raise ValueError('Temporary account scope cannot be verified')
            scopes.append(('account', account))
        if document_identity is not None:
            scopes.append(('document', document_identity[0]))
        with configured_hold_guard(settings, scopes, coordinator):
            if not _owns_import_path(temporary, final.parent, created_identity):
                raise ValueError('Temporary identity changed')
            return cleanup_file(temporary)
    except (OSError, ValueError, sqlite3.Error, SQLAlchemyError):
        emit('system.file_cleanup.failed', reason_code='cleanup_failed')
        return False


def import_document(session, settings, upload, owner_id, slots, before_commit=None):
    filename = (upload.filename or "").replace("\\", "/").split("/")[-1]
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".txt"}:
        raise HTTPException(415, "Seuls PDF et TXT sont acceptés")
    if len(filename) > 255:
        raise HTTPException(422, "Nom de fichier trop long")
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "Capacité de traitement atteinte, réessayez")
    root = settings.storage_dir.resolve()
    token = uuid4().hex
    temporary = root / f"{token}.part"
    final = root / f"{token}{extension}"
    commit_attempted = False
    identity = None
    created_identity = None
    final_owned = False
    bind = session.get_bind()
    try:
        if os.path.lexists(final):
            raise HTTPException(503, 'Identité de stockage indisponible')
        size = 0
        digest = hashlib.sha256()
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600), 'wb') as stream:
            info = os.fstat(stream.fileno())
            created_identity = (info.st_dev, info.st_ino)
            while data := upload.file.read(64 * 1024):
                size += len(data)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "Fichier trop volumineux")
                digest.update(data)
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if size == 0:
            raise HTTPException(422, "Fichier vide")
        pages = run_worker(settings, "extract", str(temporary), extension, settings.max_pdf_pages, settings.max_text_chars)
        if before_commit is not None:
            before_commit()
        from ..resource_limits import lock_workspace
        lock_workspace(session, owner_id)
        retained_storage_admission(session, settings, size)
        count, used = session.execute(select(func.count(), func.coalesce(func.sum(Document.size_bytes),0)).where(Document.owner_id==owner_id)).one()
        if count >= settings.max_documents_per_owner or used + size > settings.max_storage_bytes_per_owner:
            mark('quota.exceeded', 'quota')
            raise HTTPException(413, 'Quota documentaire ou stockage personnel atteint')
        total=session.scalar(select(func.coalesce(func.sum(Document.size_bytes),0)))
        if total+size>settings.max_storage_bytes_total:
            mark('quota.exceeded', 'quota')
            raise HTTPException(413,'Quota global de stockage atteint')
        document = Document(owner_id=owner_id, filename=filename, storage_name=final.name,
                            media_type="application/pdf" if extension == ".pdf" else "text/plain",
                            size_bytes=size, sha256=digest.hexdigest())
        session.add(document)
        session.flush()
        identity = identity_of(document)
        index = 0
        for number, text in enumerate(pages, 1):
            page = DocumentPage(document_id=document.id, page_number=number, text=text)
            session.add(page)
            session.flush()
            for start in range(0, len(text), settings.chunk_chars):
                fragment = text[start:start + settings.chunk_chars]
                session.add(DocumentChunk(document_id=document.id, page_id=page.id, chunk_index=index,
                                          start_char=start, end_char=start + len(fragment), text=fragment))
                index += 1
        if os.path.lexists(final):
            raise HTTPException(503, 'Identité de stockage indisponible')
        temporary.replace(final)
        final_owned = True
        # Make the rename durable before SQL can expose the source (Linux production).
        if os.name == 'posix':
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        commit_attempted = True
        session.commit()
        return document
    except BaseException:
        if commit_attempted:
            # A failed COMMIT does not establish rollback. Discard the suspect
            # connection before querying through an independent physical connection.
            try:
                discard_session(session)
                state = durable_document_state(bind, identity)
            except Exception:
                state = 'unknown'
            if state == 'absent' and _owns_import_path(final, root, created_identity):
                cleanup_failed_import(session, settings, owner_id, final, identity[0])
            else:
                emit('system.file_cleanup.failed', reason_code='cleanup_failed')
        else:
            rolled_back = False
            try:
                session.rollback()
                rolled_back = True
            finally:
                if final_owned and rolled_back and _owns_import_path(final, root, created_identity):
                    if durable_document_state(bind, identity) == 'absent':
                        cleanup_failed_import(session, settings, owner_id, final, identity[0])
                    else:
                        emit('system.file_cleanup.failed', reason_code='cleanup_failed')
        raise
    finally:
        try:
            cleanup_failed_temporary(session, settings, owner_id, temporary, final,
                                     created_identity, identity, bind)
        finally:
            slots.release()


def delete_document(session, settings, document):
    from ..ai.models import AIReservation
    from ..auth import User
    from ..lifecycle_durability import configured_coordinator, require_synthetic_mutation
    from ..lifecycle_holds import ActiveHoldError, configured_hold_guard
    from ..lifecycle_registry import configured_registry
    from ..rag.models import IndexJob, OperationDocument, RAGDocument, RAGResult
    from ..resource_limits import lock_workspace
    try:
        require_synthetic_mutation(settings)
    except ValueError:
        emit('system.security_config.invalid', reason_code='security_unavailable')
        raise HTTPException(503,'Suppression indisponible ; une vérification administrative est nécessaire.') from None
    lock_workspace(session, document.owner_id)
    active = session.scalar(select(OperationDocument.reservation_id).join(AIReservation,
        AIReservation.id == OperationDocument.reservation_id).where(OperationDocument.document_id == document.id,
            AIReservation.status == 'reserved').limit(1))
    indexing = session.scalar(select(IndexJob.id).where(IndexJob.document_id == document.id,
        IndexJob.status.in_(['queued', 'running'])).limit(1))
    if active or indexing:
        raise HTTPException(409, 'Un traitement documentaire est en cours. Attendez sa fin.')
    if session.scalar(select(AIReservation.id).where(AIReservation.document_id == document.id, AIReservation.status == 'reserved').limit(1)):
        raise HTTPException(409, 'Un traitement IA est en cours. Attendez sa fin avant de supprimer le document.')
    path = settings.storage_dir.resolve() / document.storage_name
    # Keep the live source until deletion is durably confirmed. Renaming it to
    # a tombstone before COMMIT leaves an active row without a file after a crash.
    bind = session.get_bind()
    identity = identity_of(document)
    commit_attempted = False
    try:
        registry=configured_registry(settings)
        coordinator=configured_coordinator(settings, registry)
        scopes = [('owner', identity[1]), ('document', identity[0])]
        account = session.scalar(select(User.id).where(User.owner_id == identity[1]))
        if coordinator and account is None:
            raise ValueError('Document account scope cannot be verified')
        if account is not None:
            scopes.append(('account', account))
        with configured_hold_guard(settings, scopes, coordinator):
            if registry:
                registry.document_requested(identity[0],identity[1],identity[2])
            if coordinator:
                coordinator.confirm_document(identity[0])
                coordinator.authorize_document(identity[0])
            try:
                linked = select(RAGDocument.result_id).where(RAGDocument.document_id == identity[0])
                session.execute(delete(RAGResult).where(RAGResult.id.in_(linked)))
                session.delete(document)
                session.flush()
                commit_attempted = True
                session.commit()
            except BaseException:
                if commit_attempted:
                    try:
                        discard_session(session)
                        state = durable_document_state(bind, identity)
                    except Exception:
                        state = 'unknown'
                    if state == 'absent':
                        cleanup_file(path)
                    else:
                        emit('system.file_cleanup.failed', reason_code='cleanup_failed')
                else:
                    session.rollback()
                raise
            cleaned=cleanup_file(path)
            if registry:
                registry.document_finished(identity[0],cleaned)
            if coordinator:
                if not cleaned:
                    raise HTTPException(503,'Suppression incomplète ; une vérification administrative est nécessaire.')
                coordinator.document_result(identity[0])
    except ActiveHoldError:
        raise HTTPException(409,'La suppression est suspendue par un gel de conservation actif.') from None
    except (OSError, ValueError, sqlite3.Error):
        emit('system.security_config.invalid', reason_code='security_unavailable')
        raise HTTPException(503,'Suppression indisponible ; une vérification administrative est nécessaire.') from None


def analyze_document(session, settings, document, options, slots):
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "Capacité de traitement atteinte, réessayez")
    try:
        result = run_worker(settings, "analyze", [page.text for page in document.pages], options.model_dump())
        validated = AnalysisResult.model_validate(result).model_dump(mode="json")
        analysis = Analysis(document_id=document.id, parameters=options.model_dump(), result=validated)
        session.add(analysis)
        session.commit()
        return analysis
    finally:
        slots.release()
