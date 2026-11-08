"""Durable checkpoints; keys remain solely in the current authenticated session."""
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import select, func, delete, update

from ..models import DocumentChunk, now
from ..ai.service import lock_budget, record_usage, settle, apply_settlement, fail, cost
from ..ai.providers import ProviderError
from .billing import embedding_settings, reserve_operation, require_fresh, fingerprint
from .models import ChunkEmbedding, IndexJob, RAGResult, RAGDocument
from .providers import runtime_settings, embed, usage, validate_vectors


def config_filter(model, settings):
    return (model.model == settings.embedding_model, model.dimensions == settings.embedding_dimensions,
            model.version == settings.embedding_version)


def prepare(session, settings, owner, identifier, body):
    from ..services.documents import owned_document
    lock_budget(session, settings.ai_budget_scope)
    owned_document(session, identifier, owner, lock=True)
    admission_hash = fingerprint('index-admission', owner, body.idempotency_key)
    input_hash = fingerprint(identifier, body.force, settings.embedding_model, settings.embedding_dimensions, settings.embedding_version)
    admission = session.scalar(select(RAGResult).where(RAGResult.owner_id == owner, RAGResult.request_hash == admission_hash))
    if admission:
        if admission.content['input_hash'] != input_hash:
            fail('idempotency_conflict', 409)
        from uuid import UUID
        job = session.get(IndexJob, UUID(admission.content['job_id']))
        session.rollback()
        return job, False
    job = session.scalar(select(IndexJob).where(IndexJob.document_id == identifier, *config_filter(IndexJob, settings)))
    if job and (job.status in ['queued', 'running'] or (job.status == 'completed' and not body.force)):
        session.rollback()
        return job, False
    if session.scalar(select(func.count()).select_from(IndexJob).where(IndexJob.status.in_(['queued', 'running']))) >= 4:
        fail('busy', 429)
    total = session.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == identifier, func.trim(DocumentChunk.text) != ''))
    if total > settings.rag_max_chunks:
        fail('document_limit', 413)
    if job is None:
        job = IndexJob(document_id=identifier, owner_id=owner, model=settings.embedding_model,
            dimensions=settings.embedding_dimensions, version=settings.embedding_version, total=total)
        session.add(job)
    elif body.force:
        from ..derived_mutations import require_derived_erasure_support
        require_derived_erasure_support(settings)
        session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.document_id == identifier, *config_filter(ChunkEmbedding, settings)))
        job.generation, job.completed = uuid4(), 0
    job.status, job.error_code, job.updated_at = 'queued', None, now()
    session.flush()
    admission = RAGResult(owner_id=owner, kind='index_request', request_hash=admission_hash,
                          content={'job_id': str(job.id), 'input_hash': input_hash})
    session.add(admission); session.flush()
    session.add(RAGDocument(result_id=admission.id, document_id=identifier))
    session.commit()
    return job, True


def recover_jobs(app):
    with app.state.sessions() as session:
        session.execute(update(IndexJob).where(IndexJob.status.in_(['queued', 'running'])).values(status='paused', error_code='session_required', updated_at=now()))
        session.commit()


def run_job(app, job_id, context, admitted_settings):
    with app.state.sessions() as session:
        job = session.get(IndexJob, job_id)
        if job is None:
            return
        reservation_id = None
        try:
            job.status = 'running'; session.commit()
            while True:
                current = runtime_settings(app, session, context)
                if current.ai_budget_scope != admitted_settings.ai_budget_scope:
                    raise ProviderError('session_required', 403, False, 0)
                current = current.model_copy(update={'embedding_model': job.model, 'embedding_dimensions': job.dimensions,
                                                    'embedding_version': job.version})
                config = embedding_settings(current)
                existing = select(ChunkEmbedding.chunk_id).where(ChunkEmbedding.document_id == job.document_id,
                    ChunkEmbedding.owner_id == job.owner_id, *config_filter(ChunkEmbedding, current))
                chunks = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == job.document_id,
                    func.trim(DocumentChunk.text) != '', DocumentChunk.id.not_in(existing)).order_by(DocumentChunk.chunk_index)
                    .limit(current.embedding_batch_size)).all()
                if not chunks:
                    job.status, job.error_code, job.updated_at = 'completed', None, now()
                    session.commit()
                    return
                texts, ids = [chunk.text for chunk in chunks], [chunk.id for chunk in chunks]
                if any(len(text.encode()) > 8000 for text in texts):
                    raise ProviderError('context_limit', 413, False, 0)
                key = uuid5(NAMESPACE_URL, f'{job.generation}:' + ':'.join(map(str, ids)))
                digest = fingerprint(job.id, job.generation, ids, job.model, job.dimensions, job.version, config.ai_budget_scope)
                maximum = cost(config, sum(len(text.encode()) for text in texts) + 128, 0)
                row = reserve_operation(session, config, job.owner_id, [job.document_id], key, digest, 'embedding', maximum, current.embedding_batch_quota)
                require_fresh(row)
                reservation_id = row.id
                latest = runtime_settings(app, session, context)
                if latest.openai_api_key != current.openai_api_key:
                    raise ProviderError('byok_disconnected', 403, False, 0)
                result = embed(app, current, texts, str(row.id))
                record_usage(session, config, row.id, usage(result))
                validate_vectors(result, len(chunks), job.dimensions)
                budget = lock_budget(session, config.ai_budget_scope)
                for identifier, vector in zip(ids, result.vectors):
                    session.add(ChunkEmbedding(chunk_id=identifier, document_id=job.document_id, owner_id=job.owner_id,
                        vector=vector, model=job.model, dimensions=job.dimensions, version=job.version))
                apply_settlement(session, budget, row.id)
                job = session.get(IndexJob, job_id)
                job.completed += len(chunks); job.updated_at = now()
                session.commit()
                reservation_id = None
        except Exception as exc:
            session.rollback()
            code = exc.code if isinstance(exc, ProviderError) else (exc.detail.get('code', 'index_failed') if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else 'index_failed')
            if reservation_id:
                if isinstance(exc, ProviderError) and exc.attempts:
                    from ..ai.models import AIReservation
                    reservation = session.get(AIReservation, reservation_id)
                    reservation.provider_calls += exc.attempts
                    session.commit()
                uncertain = not isinstance(exc, (ProviderError, HTTPException)) or (isinstance(exc, ProviderError) and exc.uncertain)
                settle(session, reservation_id, code, getattr(exc, 'status', 503), uncertain)
            job = session.get(IndexJob, job_id)
            if job:
                job.status = 'paused' if code in ['disabled', 'byok_disconnected', 'session_required', 'budget_exhausted', 'quota_reached', 'rate_limit', 'busy'] else 'failed'
                job.error_code, job.updated_at = code, now()
                session.commit()
