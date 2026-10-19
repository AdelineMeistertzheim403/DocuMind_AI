import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Response, Security, UploadFile
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .models import Analysis, Document
from .schemas import AnalysisOut, AnalyzeOptions, DocumentDetail, DocumentList, DocumentOut, ErrorOut, HealthOut
from .services.documents import analyze_document, delete_document, import_document, owned_document

router = APIRouter(prefix="/api/v1")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def owner(request: Request, key: Annotated[str | None, Security(key_header)]):
    authorization = request.headers.get('authorization', '')
    if authorization.startswith('Bearer '):
        context = request.app.state.session_vault.resolve(authorization[7:])
        from .auth import User
        with request.app.state.sessions() as session:
            user = session.get(User, context.user_id)
            if user is None or user.disabled_at is not None or user.owner_id != context.owner_id:
                request.app.state.session_vault.revoke(authorization[7:])
                raise HTTPException(401, 'Session révoquée')
        request.state.user_session = context
        request.app.state.rate_limiter.check(f'user:{context.user_id}', request.app.state.settings.requests_per_minute)
        return context.owner_id
    settings = request.app.state.settings
    for expected, owner_id in (settings.api_keys.items() if settings.legacy_api_enabled else []):
        if key and secrets.compare_digest(key.encode(), expected.encode()):
            from .auth import User
            with request.app.state.sessions() as session:
                if session.scalar(select(User.id).where(User.owner_id == owner_id, User.disabled_at.is_not(None))):
                    raise HTTPException(403, 'Propriétaire désactivé')
            request.app.state.rate_limiter.check(f'owner:{owner_id}', settings.requests_per_minute)
            return owner_id
    raise HTTPException(401, "Clé API absente ou invalide", headers={"WWW-Authenticate": "APIKey"})


def db(request: Request):
    with request.app.state.sessions() as session:
        yield session


protected = APIRouter(prefix="/documents", tags=["documents"], responses={
    401: {"model": ErrorOut, "description": "Clé API absente ou invalide"},
    404: {"model": ErrorOut, "description": "Document ou analyse absent pour ce propriétaire"},
    503: {"model": ErrorOut, "description": "Base indisponible ou capacité de traitement atteinte"},
})
Owner = Annotated[UUID, Depends(owner)]
Session = Annotated[object, Depends(db)]


@protected.post("", response_model=DocumentOut, status_code=201, summary="Importer et extraire un PDF ou TXT", responses={
    413: {"model": ErrorOut, "description": "Limite de taille dépassée"},
    415: {"model": ErrorOut, "description": "Extension non prise en charge"},
    422: {"description": "Fichier vide, corrompu, binaire, chiffré ou limite de traitement dépassée"},
})
def upload_document(request: Request, owner_id: Owner, session: Session, file: UploadFile = File(...)):
    try:
        request.app.state.rate_limiter.check(f'upload:{owner_id}', request.app.state.settings.uploads_per_minute)
        return import_document(session, request.app.state.settings, file, owner_id, request.app.state.slots)
    finally:
        file.file.close()


@protected.get("", response_model=DocumentList, summary="Lister les documents du propriétaire")
def list_documents(owner_id: Owner, session: Session, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    condition = Document.owner_id == owner_id
    total = session.scalar(select(func.count()).select_from(Document).where(condition))
    items = session.scalars(select(Document).where(condition).order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit)).all()
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@protected.get("/{document_id}", response_model=DocumentDetail, summary="Consulter le document et son texte par page")
def get_document(document_id: UUID, owner_id: Owner, session: Session):
    return owned_document(session, document_id, owner_id)


@protected.delete("/{document_id}", status_code=204, summary="Supprimer le fichier et toutes ses données")
def remove_document(document_id: UUID, request: Request, owner_id: Owner, session: Session):
    delete_document(session, request.app.state.settings, owned_document(session, document_id, owner_id, lock=True))
    return Response(status_code=204)


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


@router.get("/health", response_model=HealthOut, tags=["health"], responses={503: {"model": ErrorOut}})
def health(session: Session):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Base indisponible") from exc
    return {"status": "ok", "database": "ok"}
