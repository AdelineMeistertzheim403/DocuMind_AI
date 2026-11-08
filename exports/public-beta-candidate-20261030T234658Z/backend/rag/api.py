from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select, func

from ..api import Owner, Session
from ..ai.schemas import SummaryRequest
from ..ai.settings_api import settings_for_request
from ..ai.service import configuration_issue, fail
from ..services.documents import owned_document
from .billing import embedding_settings
from .indexing import prepare, run_job
from .models import IndexJob
from .schemas import IndexRequest, JobOut, SearchRequest, SearchOut, AskOut, CompareRequest, ComparisonOut
from .service import search, create_comparison, get_comparison, summarize_comparison

router = APIRouter(prefix='/api/v1', tags=['recherche et comparaison'], responses={
    401: {'description': 'Authentification requise'}, 403: {'description': 'IA désactivée ou session révoquée'},
    402: {'description': 'Plafond insuffisant'}, 404: {'description': 'Ressource absente pour ce propriétaire'},
    409: {'description': 'Conflit ou requête déjà en cours'}, 413: {'description': 'Limite de documents, texte ou contexte'},
    422: {'description': 'Paramètres ou consentement invalides'}, 429: {'description': 'Quota, débit ou concurrence'},
    502: {'description': 'Réponse fournisseur invalide'}, 503: {'description': 'Fournisseur ou tarifs indisponibles'},
})


@router.post('/documents/{document_id}/index', response_model=JobOut, status_code=202)
def index_document(document_id: UUID, body: IndexRequest, request: Request, background: BackgroundTasks, owner: Owner, session: Session):
    settings = settings_for_request(request, session)
    owned_document(session, document_id, owner)
    issue = configuration_issue(settings) or configuration_issue(embedding_settings(settings))
    if issue:
        fail(issue, 403 if issue == 'disabled' else 503)
    job, launch = prepare(session, settings, owner, document_id, body)
    result = JobOut.model_validate(job, from_attributes=True)
    if launch:
        background.add_task(run_job, request.app, job.id, getattr(request.state, 'user_session', None), settings)
    return result


@router.get('/documents/{document_id}/index', response_model=list[JobOut])
def index_status(document_id: UUID, owner: Owner, session: Session):
    owned_document(session, document_id, owner)
    return [JobOut.model_validate(job, from_attributes=True) for job in session.scalars(select(IndexJob).where(
        IndexJob.document_id == document_id, IndexJob.owner_id == owner).order_by(IndexJob.updated_at.desc()))]


@router.get('/search/status')
def search_status(request: Request, owner: Owner, session: Session):
    from ..ai.models import AIReservation
    settings = request.app.state.settings
    counts = dict(session.execute(select(AIReservation.feature, func.count()).where(AIReservation.owner_id == owner)
                   .group_by(AIReservation.feature)).all())
    return {'embedding_model': settings.embedding_model, 'dimensions': settings.embedding_dimensions,
        'version': settings.embedding_version, 'max_documents': settings.rag_max_documents,
        'max_passages': settings.rag_max_passages,
        'quotas': {feature: {'used': counts.get(feature, 0), 'limit': quota} for feature, quota in
            [('embedding', settings.embedding_batch_quota), ('search', settings.rag_search_quota),
             ('rag_question', settings.rag_question_quota), ('comparison', settings.rag_comparison_quota)]}}


@router.post('/search/semantic', response_model=SearchOut)
def semantic(body: SearchRequest, request: Request, owner: Owner, session: Session):
    return search(request, session, settings_for_request(request, session), owner, body)


@router.post('/search/ask', response_model=AskOut)
def ask(body: SearchRequest, request: Request, owner: Owner, session: Session):
    return search(request, session, settings_for_request(request, session), owner, body, answer=True)


@router.post('/documents/compare', response_model=ComparisonOut)
def compare_documents(body: CompareRequest, request: Request, owner: Owner, session: Session):
    return create_comparison(session, request.app.state.settings, owner, body)


@router.get('/comparisons/{comparison_id}', response_model=ComparisonOut)
def comparison(comparison_id: UUID, request: Request, owner: Owner, session: Session):
    return get_comparison(session, request.app.state.settings, owner, comparison_id)[1]


@router.post('/comparisons/{comparison_id}/summarize', response_model=ComparisonOut)
def comparison_summary(comparison_id: UUID, body: SummaryRequest, request: Request, owner: Owner, session: Session):
    return summarize_comparison(request, session, settings_for_request(request, session), owner, comparison_id, body)
