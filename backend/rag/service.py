from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func

from ..models import now
from ..ai.api import ConfiguredProvider
from ..ai.providers import ProviderError, input_bound
from ..ai.schemas import AnswerContent, SummaryRequest
from ..ai.service import (fail, cost, configuration_issue, record_usage, lock_budget,
                          apply_settlement, settle, validate_content)
from .billing import authorize_documents, reserve_operation, require_fresh, fingerprint, embedding_settings
from .models import RAGResult, RAGDocument, ChunkEmbedding
from .providers import embed, usage, validate_vectors, runtime_settings
from .retrieval import HybridRetriever
from .schemas import SearchOut, AskOut, ComparisonOut, ComparisonSummary
from .comparison import compare


def cached_result(session, owner, digest, key=None):
    if key:
        from ..ai.models import AIReservation
        previous = session.scalar(select(AIReservation).where(AIReservation.owner_id == owner, AIReservation.idempotency_key == key))
        if previous and previous.request_hash != digest:
            fail('idempotency_conflict', 409)
    return session.scalar(select(RAGResult).where(RAGResult.owner_id == owner, RAGResult.request_hash == digest)
        .order_by(RAGResult.created_at.desc()).limit(1))


def save(session, settings, owner, ids, digest, kind, content, reservation=None, settle_budget=True):
    budget = lock_budget(session, settings.ai_budget_scope)
    authorize_documents(session, owner, ids, settings, lock=True)
    row = RAGResult(owner_id=owner, kind=kind, request_hash=digest,
        reservation_id=reservation, content=content)
    session.add(row); session.flush()
    for identifier in ids:
        session.add(RAGDocument(result_id=row.id, document_id=identifier))
    if reservation and settle_budget:
        apply_settlement(session, budget, reservation)
    session.commit()
    return row


def handle_error(session, reservation, exc):
    session.rollback()
    if isinstance(exc, ProviderError):
        from ..ai.models import AIReservation
        row = session.get(AIReservation, reservation)
        row.provider_calls += exc.attempts; session.commit()
        settle(session, reservation, exc.code, exc.status, exc.uncertain)
        fail(exc.code, exc.status)
    if isinstance(exc, HTTPException):
        code = exc.detail.get('code', 'invalid_output') if isinstance(exc.detail, dict) else 'invalid_output'
        settle(session, reservation, code, exc.status_code)
        raise exc
    settle(session, reservation, 'provider_uncertain', 503, True)
    fail('provider_uncertain', 503)


def search(request, session, settings, owner, body, answer=False):
    ids = body.document_ids
    authorize_documents(session, owner, ids, settings)
    retriever = HybridRetriever(session, settings, owner, ids)
    indexed = retriever.indexed()
    use_vector = body.semantic and indexed and configuration_issue(settings) is None
    external = use_vector or answer
    if external and not body.consent:
        fail('consent_required', 422)
    epoch = session.execute(select(func.max(ChunkEmbedding.indexed_at), func.count()).where(
        ChunkEmbedding.owner_id == owner, ChunkEmbedding.document_id.in_(ids))).one()
    digest = fingerprint('rag-v1', sorted(map(str, ids)), body.query, body.semantic, body.limit, answer,
        settings.ai_budget_scope, settings.ai_provider, settings.openai_model, settings.embedding_model,
        settings.embedding_dimensions, settings.embedding_version, epoch)
    schema = AskOut if answer else SearchOut
    previous = cached_result(session, owner, digest, body.idempotency_key)
    if previous:
        data = schema.model_validate(previous.content); data.cached = True
        return data
    if not external:
        result = retriever.search(body.query, body.limit)
        if body.semantic:
            result.notice += ' Repli lexical : aucun index compatible ou IA indisponible.'
        return result
    emb_settings = embedding_settings(settings) if use_vector else None
    maximum = cost(emb_settings, len(body.query.encode()) + 128, 0) if use_vector else 0
    if answer:
        maximum += cost(settings, settings.ai_max_input_tokens, settings.ai_max_output_tokens) * 2
    row = reserve_operation(session, settings, owner, ids, body.idempotency_key, digest,
        'rag_question' if answer else 'search', maximum, settings.rag_question_quota if answer else settings.rag_search_quota)
    require_fresh(row)
    reservation = row.id
    try:
        vector, embedding_error = None, None
        if use_vector:
            try:
                current = runtime_settings(request.app, session, getattr(request.state, 'user_session', None))
                if current.openai_api_key != settings.openai_api_key:
                    raise ProviderError('byok_disconnected', 403, False, 0)
                result = embed(request.app, settings, [body.query], str(reservation))
                record_usage(session, emb_settings, reservation, usage(result))
                validate_vectors(result, 1, settings.embedding_dimensions)
                vector = result.vectors[0]
            except ProviderError as exc:
                if answer:
                    raise
                # Retrieval remains useful without the remote query vector. Preserve uncertain charges.
                from ..ai.models import AIReservation
                failed = session.get(AIReservation, reservation)
                failed.provider_calls += exc.attempts
                session.commit()
                settle(session, reservation, exc.code, exc.status, exc.uncertain)
                embedding_error = exc
        found = retriever.search(body.query, body.limit, vector)
        if embedding_error:
            found.notice += ' Fournisseur indisponible : repli lexical. Consommation éventuellement réservée ; consultez les paramètres IA.'
        if answer:
            selected = []
            for passage in found.passages:
                candidate = [*selected, passage]
                payload = {'operation': 'question', 'question': body.query,
                           'passages': [dict(chunk_id=str(item.chunk_id), text=item.excerpt, filename=item.filename,
                                             document_id=str(item.document_id), page_number=item.page_number) for item in candidate]}
                if input_bound(payload, AnswerContent) <= settings.ai_max_input_tokens:
                    selected = candidate
            if not selected:
                content = AnswerContent(answer='Les passages disponibles ne permettent pas de répondre.', insufficient_information=True, source_ids=[])
            else:
                payload = {'operation': 'question', 'question': body.query, 'passages': [dict(chunk_id=str(item.chunk_id),
                    text=item.excerpt, filename=item.filename, page_number=item.page_number) for item in selected]}
                response = ConfiguredProvider(request, settings).generate(payload, AnswerContent, str(reservation))
                record_usage(session, settings, reservation, response)
                content = validate_content(response, AnswerContent, {str(item.chunk_id) for item in selected})
            data = AskOut(id=uuid4(), content=content, sources=[item for item in selected if str(item.chunk_id) in content.source_ids], strategy=found.strategy)
        else:
            data = found
        save(session, settings, owner, ids, digest, 'question' if answer else 'search', data.model_dump(mode='json'),
            reservation, settle_budget=embedding_error is None)
        return data
    except Exception as exc:
        handle_error(session, reservation, exc)


def create_comparison(session, settings, owner, body):
    if body.document_a == body.document_b:
        fail('comparison_same_document', 422)
    ids = [body.document_a, body.document_b]
    authorize_documents(session, owner, ids, settings)
    digest = fingerprint('diff-v1', ids)
    previous = cached_result(session, owner, digest)
    if previous:
        return ComparisonOut.model_validate(previous.content)
    from ..services.documents import owned_document
    a, b = [owned_document(session, identifier, owner) for identifier in ids]
    changes, unchanged = compare(a, b, settings)
    identifier = uuid4()
    data = ComparisonOut(id=identifier, document_a=a.id, document_b=b.id, filename_a=a.filename,
        filename_b=b.filename, identical=not changes, changes=changes, unchanged_blocks=unchanged, created_at=now())
    row = save(session, settings, owner, ids, digest, 'comparison', data.model_dump(mode='json'))
    # Public comparison identifiers are database result identifiers.
    data.id = row.id; row.content = data.model_dump(mode='json'); session.commit()
    return data


def get_comparison(session, settings, owner, identifier):
    row = session.scalar(select(RAGResult).where(RAGResult.id == identifier, RAGResult.owner_id == owner, RAGResult.kind == 'comparison'))
    if row is None:
        fail('not_found', 404)
    data = ComparisonOut.model_validate(row.content)
    authorize_documents(session, owner, [data.document_a, data.document_b], settings)
    return row, data


def summarize_comparison(request, session, settings, owner, identifier, body: SummaryRequest):
    original, data = get_comparison(session, settings, owner, identifier)
    if data.ai_summary is not None:
        return data
    if not data.changes:
        data.ai_summary = ComparisonSummary(observations=[], limitations=['Documents identiques après normalisation des espaces ; aucun appel IA nécessaire.'])
        original.content = data.model_dump(mode='json'); session.commit()
        return data
    ids = [data.document_a, data.document_b]
    digest = fingerprint('comparison-summary-v1', identifier, settings.ai_budget_scope, settings.openai_model, settings.ai_provider)
    # Send only a bounded prefix, disclose its exact coverage, never silently claim full coverage.
    selected = []
    for change in data.changes[:30]:
        payload = {'operation': 'comparison', 'changes': [item.model_dump() for item in [*selected, change]]}
        if input_bound(payload, ComparisonSummary) > settings.ai_max_input_tokens:
            break
        selected.append(change)
    if not selected:
        fail('context_limit', 413)
    row = reserve_operation(session, settings, owner, ids, body.idempotency_key, digest, 'comparison',
        cost(settings, settings.ai_max_input_tokens, settings.ai_max_output_tokens) * 2, settings.rag_comparison_quota)
    require_fresh(row)
    reservation = row.id
    try:
        payload = {'operation': 'comparison', 'changes': [item.model_dump() for item in selected]}
        response = ConfiguredProvider(request, settings).generate(payload, ComparisonSummary, str(reservation))
        record_usage(session, settings, reservation, response)
        if not response.valid_response:
            fail('invalid_output', 502)
        try:
            summary = ComparisonSummary.model_validate(response.content)
        except Exception:
            fail('invalid_output', 502)
        references = [item.change_id for item in summary.observations]
        if len(references) != len(set(references)) or any(item not in {change.id for change in selected} for item in references):
            fail('invalid_output', 502)
        budget = lock_budget(session, settings.ai_budget_scope)
        original, data = get_comparison(session, settings, owner, identifier)
        data.ai_summary = summary
        data.summary_coverage = f'{len(selected)} différence(s) sur {len(data.changes)} transmises. Vérification humaine requise ; aucune conclusion juridique.'
        original.content = data.model_dump(mode='json')
        apply_settlement(session, budget, reservation)
        session.commit()
        return data
    except Exception as exc:
        handle_error(session, reservation, exc)
