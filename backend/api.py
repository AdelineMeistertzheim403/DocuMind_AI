from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .models import Analysis, Document
from .schemas import AnalysisOut, AnalyzeOptions, DocumentDetail, DocumentList, DocumentOut, ErrorOut, HealthOut
from .services.documents import analyze_document, delete_document, import_document, open_document_source, owned_document

router = APIRouter(prefix="/api/v1")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def owner(request: Request, key: Annotated[str | None, Security(key_header)]):
    from .authentication import authenticate
    if getattr(request.state, 'admitted_owner', None) is not None:
        return request.state.admitted_owner
    return authenticate(request, key)


def db(request: Request):
    with request.app.state.sessions() as session:
        session.info['application'] = request.app
        yield session


protected = APIRouter(prefix="/documents", tags=["documents"], responses={
    401: {"model": ErrorOut, "description": "Clé API absente ou invalide"},
    404: {"model": ErrorOut, "description": "Document ou analyse absent pour ce propriétaire"},
    503: {"model": ErrorOut, "description": "Base indisponible ou capacité de traitement atteinte"},
})
Owner = Annotated[UUID, Depends(owner)]
Session = Annotated[object, Depends(db)]


@protected.post("", response_model=DocumentOut, status_code=201, summary="Importer et extraire un PDF ou TXT", openapi_extra={
    'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {
        'type': 'object', 'required': ['file'], 'properties': {'file': {'type': 'string', 'format': 'binary'}}}}}},
}, responses={
    413: {"model": ErrorOut, "description": "Limite de taille dépassée"},
    415: {"model": ErrorOut, "description": "Extension non prise en charge"},
    422: {"description": "Fichier vide, corrompu, binaire, chiffré ou limite de traitement dépassée"},
})
async def upload_document(request: Request, owner_id: Owner, session: Session):
    from .uploads import parse_upload
    from .upload_admission import early_authenticate
    from .authentication import authenticate
    from starlette.concurrency import run_in_threadpool
    form = await parse_upload(request)
    try:
        current = await early_authenticate(request, charge=False)
        if current != owner_id:
            raise HTTPException(401, 'Session révoquée')
        def verify_before_commit():
            if authenticate(request, charge=False) != owner_id:
                raise HTTPException(401, 'Session révoquée')
        return await run_in_threadpool(import_document, session, request.app.state.settings, form['file'], owner_id,
                                      request.app.state.slots, before_commit=verify_before_commit)
    finally:
        await form.close()


@protected.get("", response_model=DocumentList, summary="Lister les documents du propriétaire")
def list_documents(request: Request, owner_id: Owner, session: Session, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    condition = Document.owner_id == owner_id
    if request.app.state.settings.application_profile == 'beta_lite':
        from .lite_deletions import restricted_documents
        try:
            excluded = restricted_documents(request.app.state.lite_confirmation, owner_id)
        except (OSError, ValueError):
            raise HTTPException(503, 'Vérification administrative indisponible.') from None
        condition = condition & Document.id.not_in(excluded)
    total = session.scalar(select(func.count()).select_from(Document).where(condition))
    items = session.scalars(select(Document).where(condition).order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit)).all()
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@protected.get("/{document_id}", response_model=DocumentDetail, summary="Consulter le document et son texte par page")
def get_document(document_id: UUID, owner_id: Owner, session: Session):
    return owned_document(session, document_id, owner_id)


@protected.get("/{document_id}/download", summary="Télécharger le fichier original")
def download_document(document_id: UUID, request: Request, owner_id: Owner, session: Session):
    document = owned_document(session, document_id, owner_id)
    stream = open_document_source(request.app.state.settings, document)

    def content():
        try:
            while data := stream.read(64 * 1024):
                yield data
        finally:
            stream.close()

    extension = '.pdf' if document.media_type == 'application/pdf' else '.txt'
    fallback = f'document-{document.id}{extension}'
    original = quote(document.filename, safe='')
    return StreamingResponse(content(), media_type=document.media_type, headers={
        'Content-Disposition': f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{original}',
        'Content-Length': str(document.size_bytes),
        'Cache-Control': 'no-store',
    })


@protected.delete("/{document_id}", status_code=204, summary="Supprimer le fichier et toutes ses données")
def remove_document(document_id: UUID, request: Request, owner_id: Owner, session: Session):
    if request.app.state.settings.application_profile == 'beta_lite':
        from .auth import User
        from .lite_deletions import prepare_request
        from .lifecycle_holds import ActiveHoldError
        from .security_audit import emit
        from fastapi.responses import JSONResponse
        document = session.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner_id))
        if document is None:
            raise HTTPException(404, 'Document introuvable')
        user = session.scalar(select(User).where(User.owner_id == owner_id))
        try:
            result = prepare_request(session, request.app.state.settings, request.app.state.lite_confirmation, user, document)
        except ActiveHoldError:
            raise HTTPException(409, 'Suppression suspendue par un gel de conservation.') from None
        except (OSError, ValueError):
            emit('system.security_config.invalid', reason_code='security_unavailable')
            raise HTTPException(503, 'Demande non confirmée ; vérification administrative nécessaire.') from None
        return JSONResponse(result, status_code=202)
    from .resource_limits import lock_workspace
    lock_workspace(session,owner_id)
    delete_document(session, request.app.state.settings, owned_document(session, document_id, owner_id, lock=True))
    return Response(status_code=204)


@protected.get("/{document_id}/deletion-status")
def deletion_status(document_id: UUID, request: Request, owner_id: Owner, session: Session):
    from .lite_deletions import status
    if request.app.state.settings.application_profile != 'beta_lite':
        raise HTTPException(404, 'Opération introuvable')
    try:
        adapter = request.app.state.lite_confirmation
        op = next((o for o in adapter.store.deletions() if o.kind == 'document_deletion_request'
                   and o.target_id == str(document_id) and o.owner_id == str(owner_id)), None)
        if op is None:
            raise HTTPException(404, 'Opération introuvable')
        execution = next((o for o in adapter.store.deletions() if o.parent_id == op.operation_id), None)
        return status(adapter, execution or op)
    except (OSError, ValueError):
        raise HTTPException(503, 'Vérification administrative indisponible.') from None


@protected.post("/{document_id}/analyze", response_model=AnalysisOut, status_code=201, summary="Exécuter une analyse sans IA")
def run_analysis(document_id: UUID, request: Request, owner_id: Owner, session: Session,
                 options: AnalyzeOptions = Body(default_factory=AnalyzeOptions)):
    document = owned_document(session, document_id, owner_id, lock=True)
    return analyze_document(session, request.app.state.settings, document, options, request.app.state.slots)


@protected.get("/{document_id}/analysis", response_model=AnalysisOut, summary="Consulter la dernière analyse")
def latest_analysis(document_id: UUID, owner_id: Owner, session: Session):
    owned_document(session, document_id, owner_id)
    result = session.scalar(select(Analysis).where(Analysis.document_id == document_id).order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(1))
    if result is None:
        raise HTTPException(404, "Aucune analyse disponible")
    return result


router.include_router(protected)


@router.get('/internal/upload-admission', include_in_schema=False, status_code=204)
async def upload_preflight(request: Request):
    from .gateway import secure_gateway
    from .upload_admission import early_authenticate
    secure_gateway(request)
    if not request.headers.get('authorization', '').startswith('Bearer '):
        raise HTTPException(401, 'Session personnelle requise')
    await early_authenticate(request, charge=False)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@router.get("/health", response_model=HealthOut, tags=["health"], responses={503: {"model": ErrorOut}})
def health(session: Session):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        from .security_audit import mark
        mark('system.database.unavailable', 'database')
        raise HTTPException(503, "Base indisponible") from exc
    return {"status": "ok", "database": "ok"}
