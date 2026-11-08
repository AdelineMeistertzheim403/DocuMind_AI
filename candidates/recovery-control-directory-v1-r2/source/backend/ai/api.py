from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, func
from .models import AIUsage, AIReservation

from ..api import Owner, Session
from .providers import MockAIProvider, OpenAIProvider, ProviderError, ensure_ai_enabled
from .schemas import AIHistory, AIResultOut, AIStatus, AskRequest, SummaryRequest
from .service import execute, history, status
from .settings_api import settings_for_request
from .long_api import LongJobOut

router = APIRouter(prefix='/api/v1', tags=['assistant IA'], responses={
    401: {'description': 'Clé API absente ou invalide'}, 403: {'description': 'IA désactivée'},
    402: {'description': 'Budget insuffisant'}, 404: {'description': 'Document absent pour ce propriétaire'},
    409: {'description': 'Requête déjà en cours ou clé d’idempotence réutilisée'},
    413: {'description': 'Contexte ou document trop long'}, 429: {'description': 'Quota, débit ou concurrence atteints'},
    502: {'description': 'Réponse fournisseur ou sources invalides'}, 503: {'description': 'Fournisseur indisponible ou consommation incertaine'},
})


class ConfiguredProvider:
    def __init__(self, request, settings):
        self.request, self.settings = request, settings

    def check_enabled(self):
        ensure_ai_enabled(self.request.app.state.settings)
        ensure_ai_enabled(self.settings)

    def generate(self, payload, schema, request_id):
        self.check_enabled()
        context = getattr(self.request.state, 'user_session', None)
        if self.settings.ai_mode == 'USER_BYOK':
            import time
            with self.request.app.state.session_vault.lock:
                if context is None or context.expires_at <= time.time() or not context.validated or context.key != self.settings.openai_api_key.get_secret_value():
                    raise ProviderError('byok_disconnected', 403, False, 0)
        provider = self.request.app.state.ai_provider
        if provider is None:
            settings = self.settings
            provider = MockAIProvider() if settings.ai_provider == 'mock' else OpenAIProvider(settings)
            # Owned providers recheck the live switch before every SDK attempt, including retries.
            provider.enabled_check = self.check_enabled
            try:
                return provider.generate(payload, schema, request_id)
            finally:
                close = getattr(provider, 'close', None)
                if close:
                    close()
        return provider.generate(payload, schema, request_id)


@router.get('/ai/status', response_model=AIStatus, summary='État IA, budget global et consommation du propriétaire')
def ai_status(request: Request, owner_id: Owner, session: Session):
    return status(session, settings_for_request(request, session), owner_id)


@router.get('/ai/usage', summary='Consommations connues du propriétaire, sans contenu documentaire')
def ai_usage(owner_id: Owner, session: Session, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    condition = AIUsage.owner_id == owner_id
    rows = session.execute(select(AIUsage, AIReservation.budget_id).join(AIReservation, AIUsage.reservation_id == AIReservation.id)
                           .where(condition).order_by(AIUsage.created_at.desc()).offset(offset).limit(limit)).all()
    return {'items': [{'id': str(row.id), 'feature': row.feature, 'model': row.model, 'provider': row.provider,
                       'mode': 'USER_BYOK' if budget.startswith('byok:') else 'OWNER_DEMO',
                       'input_tokens': row.input_tokens, 'output_tokens': row.output_tokens, 'reasoning_tokens': row.reasoning_tokens,
                       'estimated_usd': float(row.estimated_usd), 'created_at': row.created_at} for row, budget in rows],
            'total': session.scalar(select(func.count()).select_from(AIUsage).where(condition)), 'offset': offset, 'limit': limit}


@router.post('/documents/{document_id}/summarize', response_model=AIResultOut, responses={202:{'model':LongJobOut,'description':'Résumé approfondi accepté ; consulter la progression de la tâche'}}, summary='Générer ou réutiliser un résumé IA sourcé')
def summarize(document_id: UUID, payload: SummaryRequest, request: Request, owner_id: Owner, session: Session):
    settings = settings_for_request(request, session)
    from .long_plan import LongDocumentSummarizer
    from ..services.documents import owned_document
    plan = LongDocumentSummarizer(settings).plan(session, owned_document(session, document_id, owner_id))
    if not plan['direct']:
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import JSONResponse
        from .long_summary import start
        return JSONResponse(jsonable_encoder(start(request,session,settings,owner_id,document_id,payload)),status_code=202)
    return execute(session, settings, ConfiguredProvider(request, settings), owner_id, document_id, payload, 'summary')


@router.get('/documents/{document_id}/summaries', response_model=AIHistory, summary='Consulter les résumés sans appel fournisseur')
def summaries(document_id: UUID, owner_id: Owner, session: Session, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return history(session, document_id, owner_id, 'summary', offset, limit)


@router.post('/documents/{document_id}/ask', response_model=AIResultOut, summary='Poser une question sur les passages pertinents')
def ask(document_id: UUID, payload: AskRequest, request: Request, owner_id: Owner, session: Session):
    settings = settings_for_request(request, session)
    return execute(session, settings, ConfiguredProvider(request, settings), owner_id, document_id, payload, 'question')


@router.get('/documents/{document_id}/ai-history', response_model=AIHistory, summary='Historique des questions/réponses sans nouvel appel')
def ai_history(document_id: UUID, owner_id: Owner, session: Session, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return history(session, document_id, owner_id, 'question', offset, limit)
