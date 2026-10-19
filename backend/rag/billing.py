"""Extend the existing transaction/ledger; no second wallet or secret storage."""
import hashlib
import json
from datetime import timedelta, date
from decimal import Decimal

from sqlalchemy import select, func

from ..ai.models import AIReservation
from ..ai.service import lock_budget, configuration_issue, fail, ACTIVE
from ..models import now
from ..services.documents import owned_document
from .models import OperationDocument


def fingerprint(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def embedding_settings(settings):
    age = (date.today() - date.fromisoformat(settings.embedding_pricing_verified_on)).days
    if settings.embedding_pricing_model != settings.embedding_model or not 0 <= age <= 90:
        fail('pricing_unverified', 503)
    if settings.embedding_model == 'text-embedding-3-small' and settings.embedding_input_usd_per_million < Decimal('.02'):
        fail('pricing_unverified', 503)
    return settings.model_copy(update={'openai_model': settings.embedding_model,
        'ai_pricing_model': settings.embedding_pricing_model, 'ai_pricing_verified_on': settings.embedding_pricing_verified_on,
        'ai_input_usd_per_million': settings.embedding_input_usd_per_million,
        'ai_output_usd_per_million': Decimal(0)})


def authorize_documents(session, owner, ids, settings, lock=False):
    if len(ids) > settings.rag_max_documents:
        fail('document_limit', 413)
    return [owned_document(session, identifier, owner, lock=lock) for identifier in sorted(set(ids), key=str)]


def reserve_operation(session, settings, owner, ids, key, digest, feature, maximum, quota):
    budget = lock_budget(session, settings.ai_budget_scope)
    authorize_documents(session, owner, ids, settings, lock=True)
    previous = session.scalar(select(AIReservation).where(AIReservation.owner_id == owner, AIReservation.idempotency_key == key))
    if previous:
        if previous.request_hash != digest:
            fail('idempotency_conflict', 409)
        session.rollback()
        return previous
    issue = configuration_issue(settings)
    if issue:
        fail(issue, 403 if issue == 'disabled' else 503)
    if session.scalar(select(AIReservation.id).where(AIReservation.owner_id == owner, AIReservation.request_hash == digest, AIReservation.status.in_(ACTIVE)).limit(1)):
        fail('request_in_progress', 409)
    used = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner, AIReservation.feature == feature))
    if used >= quota:
        fail('quota_reached', 429)
    recent = session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id == owner, AIReservation.created_at >= now() - timedelta(minutes=1)))
    if recent >= settings.ai_requests_per_minute:
        fail('rate_limit', 429)
    if session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.status == 'reserved')) >= settings.ai_max_concurrent_requests:
        fail('busy', 429)
    cap = settings.ai_budget_usd
    if settings.ai_mode == 'USER_BYOK':
        from ..auth import User
        cap = session.scalar(select(User.ai_limit_usd).where(User.owner_id == owner))
    if budget.spent_usd + budget.reserved_usd + maximum > cap:
        fail('budget_exhausted', 402)
    if session.scalar(select(func.count()).select_from(AIReservation).where(AIReservation.owner_id==owner, AIReservation.status=='reserved')) >= settings.ai_max_concurrent_per_owner:
        fail('busy',429)
    row = AIReservation(owner_id=owner, budget_id=settings.ai_budget_scope, document_id=ids[0],
        idempotency_key=key, request_hash=digest, feature=feature, reserved_usd=maximum,
        model=settings.openai_model, provider=settings.ai_provider)
    session.add(row)
    budget.reserved_usd += maximum
    session.flush()
    for identifier in ids:
        session.add(OperationDocument(reservation_id=row.id, document_id=identifier))
    session.commit()
    # Distinguish fresh admission from replay without persisting another status.
    row._new_admission = True
    return row


def require_fresh(row):
    if not getattr(row, '_new_admission', False):
        fail(row.error_code or 'request_in_progress', row.error_status or 409)
