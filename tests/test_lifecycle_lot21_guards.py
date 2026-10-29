"""Strict-profile regression tests, with synthetic application data only."""
from uuid import UUID

import pytest
from sqlalchemy import func, select

from backend.account_admin import purge_pending
from backend.ai.models import AIBudget, AISummary
from backend.auth import User, hash_password
from backend.rag.models import ChunkEmbedding
from tests.test_ai import ai, payload, upload
from tests.test_byok import PASSWORD, login
from tests.test_rag import index, rag


def test_derived_erasure_and_force_reindex_are_blocked_in_strict_profile(rag):
    client, app, _, _ = rag
    with app.state.sessions() as db:
        db.add(User(username='owner', owner_id=UUID(int=1), password_hash=hash_password(PASSWORD)))
        db.add(AIBudget(id=f'byok:{UUID(int=1)}:openai'))
        db.commit()
    login(client, 'owner')
    client.put('/api/v1/ai/settings', json={'mode': 'OWNER_DEMO', 'limit_usd': 4})
    identifier = upload(client)
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).status_code == 200
    index(client, identifier)
    with app.state.sessions() as db:
        summaries = db.scalar(select(func.count()).select_from(AISummary))
        embeddings = db.scalar(select(func.count()).select_from(ChunkEmbedding))
    assert summaries > 0 and embeddings > 0
    app.state.settings.lifecycle_durable_receipts_required = True
    assert client.delete(f'/api/v1/documents/{identifier}/ai-results').status_code == 503
    assert client.delete(f'/api/v1/documents/{identifier}/embeddings').status_code == 503
    assert client.post(f'/api/v1/documents/{identifier}/index', json=payload(force=True)).status_code == 503
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AISummary)) == summaries
        assert db.scalar(select(func.count()).select_from(ChunkEmbedding)) == embeddings


def test_pending_purge_is_blocked_before_sql_in_strict_profile(app):
    class NoSQL:
        def scalars(self, *args, **kwargs):
            pytest.fail('SQL must not execute before the strict guard')

    app.state.settings.lifecycle_durable_receipts_required = True
    with pytest.raises(ValueError, match='Pending-account purge disabled'):
        purge_pending(NoSQL(), app.state.settings, execute=True)
