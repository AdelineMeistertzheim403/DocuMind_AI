import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, delete, func

from ..models import Analysis, Document, DocumentChunk, DocumentPage
from ..schemas import AnalysisResult
from .worker import run_worker

logger = logging.getLogger(__name__)


def owned_document(session, document_id, owner_id, lock=False):
    query = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    document = session.scalar(query)
    if document is None:
        raise HTTPException(404, "Document introuvable")
    return document


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
    try:
        size = 0
        digest = hashlib.sha256()
        with temporary.open("xb") as stream:
            while data := upload.file.read(64 * 1024):
                size += len(data)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "Fichier trop volumineux")
                digest.update(data)
                stream.write(data)
        if size == 0:
            raise HTTPException(422, "Fichier vide")
        pages = run_worker(settings, "extract", str(temporary), extension, settings.max_pdf_pages, settings.max_text_chars)
        if before_commit is not None:
            before_commit()
        from ..resource_limits import lock_workspace
        lock_workspace(session, owner_id)
        count, used = session.execute(select(func.count(), func.coalesce(func.sum(Document.size_bytes),0)).where(Document.owner_id==owner_id)).one()
        if count >= settings.max_documents_per_owner or used + size > settings.max_storage_bytes_per_owner:
            raise HTTPException(413, 'Quota documentaire ou stockage personnel atteint')
        total=session.scalar(select(func.coalesce(func.sum(Document.size_bytes),0)))
        if total+size>settings.max_storage_bytes_total:
            raise HTTPException(413,'Quota global de stockage atteint')
        document = Document(owner_id=owner_id, filename=filename, storage_name=final.name,
                            media_type="application/pdf" if extension == ".pdf" else "text/plain",
                            size_bytes=size, sha256=digest.hexdigest())
        session.add(document)
        session.flush()
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
        temporary.replace(final)
        session.commit()
        return document
    except BaseException:
        session.rollback()
        final.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        slots.release()


def delete_document(session, settings, document):
    from ..ai.models import AIReservation
    from ..rag.models import IndexJob, OperationDocument, RAGDocument, RAGResult
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
    tombstone = path.with_suffix(path.suffix + ".deleted")
    moved = False
    try:
        if path.exists():
            path.replace(tombstone)
            moved = True
        linked = select(RAGDocument.result_id).where(RAGDocument.document_id == document.id)
        session.execute(delete(RAGResult).where(RAGResult.id.in_(linked)))
        session.delete(document)
        session.commit()
    except BaseException:
        session.rollback()
        if moved:
            tombstone.replace(path)
        raise
    try:
        tombstone.unlink(missing_ok=True)
    except OSError:
        logger.exception("Suppression différée du fichier %s", tombstone.name)


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
