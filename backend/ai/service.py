import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from ..models import Document, DocumentChunk, DocumentPage, now
from ..services.documents import owned_document
from .models import AIBudget, AIInteraction, AIReservation, AISource, AISummary, AIUsage
from .providers import ProviderError, input_bound
from .retrieval import load_passages, relevant_passages, summary_groups
from .schemas import AIResultOut, AIStatus, AnswerContent, SourceOut, SummaryContent

ACTIVE = ['reserved', 'uncertain']
MESSAGES = {
    'output_truncated': 'La réponse IA a atteint la limite de sortie avant de terminer. Les étapes validées sont conservées.',
    'provider_refusal': 'Le fournisseur a refusé cette étape. Les étapes validées sont conservées.',
    'invalid_json': 'Le fournisseur a renvoyé un JSON illisible. Les étapes validées sont conservées.',
    'invalid_schema': 'La réponse IA ne respecte pas le format demandé. Les étapes validées sont conservées.',
    'invalid_references': 'La réponse IA cite une source absente du contexte. Les étapes validées sont conservées.',

    'disabled': 'L’IA est désactivée côté serveur.',
    'provider_unavailable': 'Le fournisseur IA est indisponible ou mal configuré.',
    'pricing_unverified': 'Le modèle ou ses tarifs doivent être vérifiés côté serveur.',
    'budget_exhausted': 'Budget insuffisant pour réserver cette opération.',
    'quota_reached': 'Le quota de cette fonctionnalité est atteint.',
    'rate_limit': 'Trop de demandes IA. Réessayez dans une minute.',
    'busy': 'Le nombre maximal de traitements IA simultanés est atteint.',
    'request_in_progress': 'Cette demande est déjà en cours ou nécessite une réconciliation. Aucun nouvel appel lancé.',
    'idempotency_conflict': 'Cette clé d’idempotence correspond à une autre demande.',
    'invalid_output': 'Le fournisseur a refusé la demande ou renvoyé une réponse structurée ou des références invalides.',
    'provider_rate_limit': 'Le fournisseur limite les requêtes. Réessayez plus tard avec une nouvelle demande.',
    'provider_uncertain': 'La réponse du fournisseur est incertaine. La réservation reste bloquée pour éviter un dépassement.',
    'usage_unknown': 'La consommation fournisseur est inconnue. La réservation reste bloquée.',
    'context_limit': 'La synthèse dépasserait la limite de contexte. Les étapes déjà réalisées restent comptabilisées.',
    'estimate_changed': 'Le coût maximal a changé. Rechargez le plan et confirmez la nouvelle estimation.',
    'session_required': 'Reconnectez votre compte et sa clé avant de reprendre la tâche.',
}


def fail(code, status):
    raise HTTPException(status, {'code': code, 'message': MESSAGES.get(code, MESSAGES['provider_unavailable'])})


def configuration_issue(settings):
    if not settings.ai_enabled:
        return 'disabled'
    if settings.ai_configuration_reason:
        return settings.ai_configuration_reason
    if settings.ai_mode == 'OWNER_DEMO' and not settings.owner_demo_enabled:
        return 'disabled'
    if settings.ai_provider == 'openai' and not settings.openai_api_key.get_secret_value():
        return 'provider_unavailable'
    try:
        age = (date.today() - date.fromisoformat(settings.ai_pricing_verified_on)).days
    except ValueError:
        age = 1000
    if settings.openai_model != settings.ai_pricing_model or not 0 <= age <= 90:
        return 'pricing_unverified'
    if settings.openai_model == 'gpt-5.6-luna' and (settings.ai_input_usd_per_million < Decimal('.25') or settings.ai_output_usd_per_million < Decimal('1.2')):
        return 'pricing_unverified'
    return None


def lock_budget(session, scope='development'):
    # All reservations and reconciliations serialize on this seeded row, across owners/processes.
    session.rollback()
    if session.bind.dialect.name == 'sqlite':
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    # Global lock also serializes cross-user concurrency admission; scoped budget is separate.
    global_budget = session.scalar(select(AIBudget).where(AIBudget.id == 'development').with_for_update())
    budget = global_budget if scope == 'development' else session.scalar(select(AIBudget).where(AIBudget.id == scope).with_for_update())
    if budget is None:
        fail('provider_unavailable', 503)
    return budget


def cost(settings, input_tokens, output_tokens):
    return ((Decimal(input_tokens) * settings.ai_input_usd_per_million + Decimal(output_tokens) * settings.ai_output_usd_per_million) / Decimal(1_000_000)).quantize(Decimal('.0000000001'))


def result_out(session, row, feature, cached=False):
    reservation = session.get(AIReservation, row.reservation_id)
    rows = session.execute(select(DocumentChunk, DocumentPage.page_number).join(AISource, AISource.chunk_id == DocumentChunk.id)
                           .join(DocumentPage, DocumentPage.id == DocumentChunk.page_id)
                           .where(AISource.reservation_id == row.reservation_id,
                                  DocumentChunk.document_id == row.document_id, DocumentPage.document_id == row.document_id)
                           .order_by(DocumentChunk.chunk_index)).all()
    return AIResultOut(id=row.id, document_id=row.document_id, feature=feature,
                       question=row.question if feature == 'question' else None,
                       content=(SummaryContent if feature == 'summary' else AnswerContent).model_validate(row.content),
                       sources=[SourceOut(chunk_id=chunk.id, page_number=number, excerpt=chunk.text) for chunk, number in rows],
                       model=reservation.model, provider=reservation.provider, created_at=row.created_at,
                       coverage=row.coverage, cached=cached)


def reserve(session, settings, owner_id, document_id, key, fingerprint, feature, steps):
    budget = lock_budget(session, settings.ai_budget_scope)
    owned_document(session, document_id, owner_id, lock=True)
    if settings.ai_mode == 'USER_BYOK':
        from ..auth import User
        settings.ai_budget_usd = session.scalar(select(User.ai_limit_usd).where(User.owner_id == owner_id))
    existing = session.scalar(select(AIReservation).where(AIReservation.owner_id == owner_id, AIReservation.idempotency_key == key))
    if existing and existing.request_hash != fingerprint:
        fail('idempotency_conflict', 409)
    model = AISummary if feature == 'summary' else AIInteraction
    cached = session.scalar(select(model).join(AIReservation, model.reservation_id == AIReservation.id)
                            .where(model.document_id == document_id, model.owner_id == owner_id,
                                   AIReservation.request_hash == fingerprint).order_by(model.created_at.desc()).limit(1))
    if cached:
        output = result_out(session, cached, feature, True)
        session.rollback()
        return None, output
    if existing:
        fail(existing.error_code or 'request_in_progress', existing.error_status or 409)
    issue = configuration_issue(settings)
    if issue:
        fail(issue, 403 if issue == 'disabled' else 503)
    duplicates = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id,
                                AIReservation.request_hash == fingerprint, AIReservation.status.in_(ACTIVE)))
    if duplicates:
        fail('request_in_progress', 409)
    used = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id, AIReservation.feature == feature))
    quota = settings.ai_summary_quota if feature == 'summary' else settings.ai_question_quota
    if used >= quota:
        fail('quota_reached', 429)
    recent = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id,
                               AIReservation.created_at >= now() - timedelta(minutes=1)))
    if recent >= settings.ai_requests_per_minute:
        fail('rate_limit', 429)
    active = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.status == 'reserved'))
    if active >= settings.ai_max_concurrent_requests:
        fail('busy', 429)
    maximum = cost(settings, settings.ai_max_input_tokens, settings.ai_max_output_tokens) * steps * 2
    if budget.spent_usd + budget.reserved_usd + maximum > settings.ai_budget_usd:
        fail('budget_exhausted', 402)
    personal_active = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id==owner_id, AIReservation.status=='reserved'))
    if personal_active >= settings.ai_max_concurrent_per_owner:
        fail('busy',429)
    reservation = AIReservation(owner_id=owner_id, budget_id=settings.ai_budget_scope, document_id=document_id, idempotency_key=key,
                                request_hash=fingerprint, feature=feature, reserved_usd=maximum,
                                model=settings.openai_model, provider=settings.ai_provider)
    session.add(reservation)
    budget.reserved_usd += maximum
    session.commit()
    return reservation.id, None


def record_usage(session, settings, reservation_id, response):
    reservation = session.get(AIReservation, reservation_id)
    if min(response.input_tokens, response.output_tokens, response.reasoning_tokens) < 0 or response.reasoning_tokens > response.output_tokens:
        raise ProviderError('usage_unknown', 503, True)
    amount = cost(settings, response.input_tokens, response.output_tokens) if settings.ai_provider != 'mock' else Decimal(0)
    reservation.provider_calls += response.attempts
    session.add(AIUsage(reservation_id=reservation.id, owner_id=reservation.owner_id, document_id=reservation.document_id,
                        feature=reservation.feature, model=settings.openai_model, provider=reservation.provider,
                        input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                        reasoning_tokens=response.reasoning_tokens, attempts=response.attempts,
                        estimated_usd=amount, input_rate=settings.ai_input_usd_per_million,
                        output_rate=settings.ai_output_usd_per_million))
    session.commit()


def apply_settlement(session, budget, reservation_id, code=None, status=None, uncertain=False):
    reservation = session.get(AIReservation, reservation_id, populate_existing=True)
    amount = session.scalar(select(func.coalesce(func.sum(AIUsage.estimated_usd), 0)).where(AIUsage.reservation_id == reservation_id))
    reservation.actual_usd = amount
    reservation.error_code, reservation.error_status = code, status
    if uncertain:
        reservation.status = 'uncertain'
    else:
        reservation.status = 'failed' if code else 'settled'
        budget.reserved_usd -= reservation.reserved_usd
        budget.spent_usd += amount
    return reservation


def settle(session, reservation_id, code=None, status=None, uncertain=False):
    scope = session.scalar(select(AIReservation.budget_id).where(AIReservation.id == reservation_id))
    budget = lock_budget(session, scope)
    reservation = apply_settlement(session, budget, reservation_id, code, status, uncertain)
    session.commit()
    from ..security_audit import emit
    emit('system.ai.settled', reason_code='settled')


def validate_content(response, schema, allowed):
    if response.error_code in {'output_truncated', 'provider_refusal', 'invalid_json'}:
        fail(response.error_code, 502)
    if not response.valid_response:
        fail('invalid_output', 502)
    try:
        content = schema.model_validate(response.content)
    except (ValidationError, TypeError) as exc:
        # Diagnostics contain categories only: no document text, provider output or keys.
        from ..security_audit import emit
        emit('system.ai.output_rejected', reason_code='invalid_output')
        fail('invalid_schema', 502)
    references = content.source_ids
    if any(source not in allowed for source in references):
        fail('invalid_references', 502)
    # Repeated valid citations carry no extra meaning, especially across overlapping parts.
    content.source_ids = list(dict.fromkeys(references))
    insufficient = isinstance(content, AnswerContent) and content.insufficient_information
    if (insufficient and references) or (not insufficient and not references):
        fail('invalid_references', 502)
    return content


def execute(session, settings, provider, owner_id, document_id, request, feature):
    document = owned_document(session, document_id, owner_id)
    passages = load_passages(session, document_id)
    question = request.question if feature == 'question' else None
    if feature == 'summary':
        groups = summary_groups(passages, settings)
    else:
        groups = [relevant_passages(passages, question, settings)]
    steps = len(groups) + (1 if len(groups) > 1 else 0)
    fingerprint = hashlib.sha256(json.dumps([str(document_id), document.sha256, feature, question,
                               settings.openai_model, settings.ai_provider, settings.ai_max_input_tokens,
                               settings.ai_max_output_tokens, settings.ai_max_question_chunks, settings.ai_budget_scope, 'prompt-v1'], ensure_ascii=False).encode()).hexdigest()
    reservation_id, cached = reserve(session, settings, owner_id, document_id, request.idempotency_key, fingerprint, feature, steps)
    if cached:
        return cached
    allowed = {item['chunk_id'] for group in groups for item in group}
    schema = SummaryContent if feature == 'summary' else AnswerContent
    try:
        def generate(payload, eligible):
            if input_bound(payload, schema) > settings.ai_max_input_tokens:
                fail('context_limit', 413)
            response = provider.generate(payload, schema, str(reservation_id))
            record_usage(session, settings, reservation_id, response)
            return validate_content(response, schema, eligible)

        if feature == 'question' and not groups[0]:
            content = AnswerContent(answer='Les passages disponibles ne permettent pas de répondre à cette question. Essayez des termes précis présents dans le document.',
                                    insufficient_information=True, source_ids=[])
        else:
            partials = []
            for group in groups:
                partials.append(generate({'operation': feature, 'question': question, 'passages': group}, {item['chunk_id'] for item in group}))
            content = partials[0]
            if len(partials) > 1:
                # Only already-validated provenance may survive synthesis.
                provenance = {source for partial in partials for source in partial.source_ids}
                content = generate({'operation': 'synthesis', 'partial_summaries': [part.model_dump() for part in partials]}, provenance)
        row_type = AISummary if feature == 'summary' else AIInteraction
        coverage = f'Document intégral : {len(passages)} passages, {steps} étape(s).' if feature == 'summary' else f'Recherche lexicale : {len(groups[0])} passage(s) sur {len(passages)}. Sans mémoire conversationnelle envoyée.'
        values = dict(document_id=document_id, owner_id=owner_id, reservation_id=reservation_id, content=content.model_dump(), coverage=coverage)
        if feature == 'question':
            values['question'] = question
        budget = lock_budget(session, settings.ai_budget_scope)
        row = row_type(**values)
        session.add(row)
        for reference in content.source_ids:
            session.add(AISource(reservation_id=reservation_id, document_id=document_id, chunk_id=UUID(reference)))
        # The result and accounting commit together under the budget lock.
        apply_settlement(session, budget, reservation_id)
        session.flush()
        row_id = row.id
        session.commit()
        return result_out(session, session.get(row_type, row_id), feature)
    except ProviderError as exc:
        session.rollback()
        reservation = session.get(AIReservation, reservation_id)
        reservation.provider_calls += exc.attempts
        session.commit()
        settle(session, reservation_id, exc.code, exc.status, exc.uncertain)
        fail(exc.code, exc.status)
    except HTTPException as exc:
        session.rollback()
        settle(session, reservation_id, exc.detail.get('code', 'invalid_output'), exc.status_code)
        raise
    except Exception:
        session.rollback()
        settle(session, reservation_id, 'provider_uncertain', 503, True)
        fail('provider_uncertain', 503)


def history(session, document_id, owner_id, feature, offset, limit):
    owned_document(session, document_id, owner_id)
    model = AISummary if feature == 'summary' else AIInteraction
    condition = (model.document_id == document_id, model.owner_id == owner_id)
    total = session.scalar(select(func.count()).select_from(model).where(*condition))
    rows = session.scalars(select(model).where(*condition).order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)).all()
    return {'items': [result_out(session, row, feature, True) for row in rows], 'total': total, 'offset': offset, 'limit': limit}


def status(session, settings, owner_id):
    budget = session.get(AIBudget, settings.ai_budget_scope)
    spent = budget.spent_usd if budget else Decimal(0)
    held = budget.reserved_usd if budget else Decimal(0)
    summary_count = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id, AIReservation.feature == 'summary'))
    question_count = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id, AIReservation.feature == 'question'))
    totals = session.execute(select(func.coalesce(func.sum(AIUsage.input_tokens), 0), func.coalesce(func.sum(AIUsage.output_tokens), 0),
                                   func.coalesce(func.sum(AIUsage.reasoning_tokens), 0)).where(AIUsage.owner_id == owner_id)).one()
    pending = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner_id, AIReservation.status.in_(ACTIVE)))
    calls = session.scalar(select(func.coalesce(func.sum(AIReservation.provider_calls), 0)).where(AIReservation.owner_id == owner_id))
    reason = configuration_issue(settings) or ('budget_exhausted' if spent + held >= settings.ai_budget_usd else None)
    return AIStatus(mode=settings.ai_mode, enabled=settings.ai_enabled, available=reason is None, reason=reason, provider=settings.ai_provider, model=settings.openai_model,
                    budget_usd=float(settings.ai_budget_usd), spent_usd=float(spent), reserved_usd=float(held),
                    remaining_usd=float(max(Decimal(0), settings.ai_budget_usd - spent - held)),
                    summary_quota=settings.ai_summary_quota, question_quota=settings.ai_question_quota,
                    summaries_used=summary_count, questions_used=question_count, requests=summary_count + question_count,
                    provider_calls=calls, input_tokens=totals[0], output_tokens=totals[1], reasoning_tokens=totals[2],
                    pending_requests=pending, pricing_verified_on=settings.ai_pricing_verified_on)
