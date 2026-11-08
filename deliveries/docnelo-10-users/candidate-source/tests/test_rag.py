from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func

from backend.ai.models import AIBudget, AIReservation, AIUsage
from backend.ai.providers import ProviderError
from backend.rag.models import ChunkEmbedding, IndexJob, RAGResult
from backend.rag.providers import MockEmbeddingProvider
from backend.rag.indexing import recover_jobs
from tests.test_ai import ai, upload, payload
from tests.conftest import OTHER_KEY, KEY
from tests.test_byok import accounts, login, connect


@pytest.fixture
def rag(ai):
    client, app, text_provider = ai
    app.state.settings.embedding_dimensions = 16
    app.state.settings.embedding_batch_size = 2
    embedding = MockEmbeddingProvider(16)
    app.state.embedding_provider = embedding
    return client, app, embedding, text_provider


def index(client, identifier, **extra):
    response = client.post(f'/api/v1/documents/{identifier}/index', json=payload(**extra))
    assert response.status_code == 202, response.text
    return client.get(f'/api/v1/documents/{identifier}/index').json()[0]


def query(ids, **extra):
    return {**dict(document_ids=ids, query='budget du projet Atlas', semantic=True, limit=8), **payload(**extra)}


def test_index_batches_idempotent_force_and_costs(rag):
    client, app, embedding, _ = rag
    identifier = upload(client, (('Le budget Atlas est de 120 euros. '*200)).encode())
    result = index(client, identifier)
    assert result['status'] == 'completed' and result['completed'] == result['total'] > 2
    calls = len(embedding.calls)
    assert index(client, identifier)['status'] == 'completed'
    assert len(embedding.calls) == calls
    assert index(client, identifier, force=True)['status'] == 'completed'
    assert len(embedding.calls) == calls*2
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == result['total']
        assert session.scalar(select(func.count()).select_from(AIUsage).where(AIUsage.model == 'text-embedding-3-small')) == calls*2
        assert session.get(AIBudget, 'development').spent_usd > 0
        assert session.get(AIBudget, 'development').reserved_usd == 0


def test_index_version_change_is_explicit_and_old_vectors_preserved(rag):
    client, app, embedding, _ = rag
    identifier = upload(client)
    index(client, identifier)
    app.state.settings.embedding_version = 'chunks-v2'
    index(client, identifier)
    with app.state.sessions() as session:
        assert set(session.scalars(select(ChunkEmbedding.version))) == {'chunks-v1', 'chunks-v2'}
    assert len(client.get(f'/api/v1/documents/{identifier}/index').json()) == 2


def test_failed_index_retains_hold_and_no_ambiguous_retry(rag):
    client, app, embedding, _ = rag
    identifier = upload(client)
    def broken(*args):
        embedding.calls.append('failed')
        raise ProviderError('provider_uncertain', 503, True)
    embedding.embed = broken
    assert index(client, identifier)['status'] == 'failed'
    assert index(client, identifier)['status'] == 'failed'
    assert len(embedding.calls) == 1
    with app.state.sessions() as session:
        assert session.get(AIBudget, 'development').reserved_usd > 0
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0


def test_recovery_requires_session_and_resumes_checkpoints(rag):
    client, app, embedding, _ = rag
    identifier = upload(client)
    index(client, identifier)
    with app.state.sessions() as session:
        job = session.scalar(select(IndexJob)); job.status='running'; session.commit()
    recover_jobs(app)
    assert client.get(f'/api/v1/documents/{identifier}/index').json()[0]['status'] == 'paused'
    assert index(client, identifier)['status'] == 'completed'
    assert len(embedding.calls) == 1


def test_lexical_and_vector_hybrid_multidocument_and_cache(rag):
    client, app, embedding, text_provider = rag
    ids = [upload(client, text.encode()) for text in ['Le budget Atlas est de 120 euros.', 'Camille gère le projet Atlas.']]
    lexical = client.post('/api/v1/search/semantic', json=query(ids, semantic=False))
    assert lexical.status_code == 200, lexical.text
    assert lexical.json()['strategy'] == 'lexical'
    assert len(embedding.calls) == 0
    for identifier in ids:
        index(client, identifier)
    body = query(ids)
    response = client.post('/api/v1/search/semantic', json=body)
    assert response.status_code == 200, response.text
    found = response.json()
    assert found['strategy'] == 'hybrid_rrf'
    assert {item['document_id'] for item in found['passages']} == set(ids)
    assert all(item['vector_rank'] and item['cosine_distance'] is not None for item in found['passages'])
    assert client.post('/api/v1/search/semantic', json=body).json()['cached']
    assert len(embedding.calls) == 3
    answer = client.post('/api/v1/search/ask', json=query(ids))
    assert answer.status_code == 200, answer.text
    data = answer.json()
    assert data['content']['source_ids'] and all(item['page_number'] == 1 for item in data['sources'])
    assert all(item['excerpt'] in ['Le budget Atlas est de 120 euros.', 'Camille gère le projet Atlas.'] for item in data['sources'])
    vector_only = client.post('/api/v1/search/semantic', json={**query(ids), 'query':'notions totalement absentes'})
    assert vector_only.status_code == 200
    assert vector_only.json()['passages'] and all(item['lexical_rank'] is None and item['vector_rank'] for item in vector_only.json()['passages'])


def test_provider_outage_falls_back_lexical_without_refunding_unknown_cost(rag):
    client, app, embedding, _ = rag
    identifier = upload(client, b'Le budget Atlas est connu.')
    index(client, identifier)
    embedding.embed = lambda *args: (_ for _ in ()).throw(ProviderError('provider_uncertain',503,True))
    response = client.post('/api/v1/search/semantic', json=query([identifier]))
    assert response.status_code == 200
    assert response.json()['strategy'] == 'lexical' and 'réservée' in response.json()['notice']
    with app.state.sessions() as session:
        assert session.get(AIBudget,'development').reserved_usd > 0


def test_ownership_before_costs_and_deletion_cascade(rag):
    client, app, embedding, _ = rag
    a = upload(client, b'Budget Atlas 120 euros.')
    index(client,a)
    b = upload(client, b'Budget Atlas 150 euros.')
    comparison = client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':b}).json()
    assert client.post('/api/v1/search/ask',json=query([a,b])).status_code == 200
    calls = len(embedding.calls)
    client.headers['X-API-Key'] = OTHER_KEY
    for route, body in [('/api/v1/search/semantic',query([a])),('/api/v1/search/ask',query([a])),
                         ('/api/v1/documents/compare',{'document_a':a,'document_b':b})]:
        assert client.post(route,json=body).status_code == 404
    assert client.get(f"/api/v1/comparisons/{comparison['id']}").status_code == 404
    assert client.post(f'/api/v1/documents/{a}/index',json=payload()).status_code == 404
    assert len(embedding.calls) == calls
    client.headers['X-API-Key'] = KEY
    assert client.delete(f'/api/v1/documents/{b}').status_code == 204
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(RAGResult).where(RAGResult.kind != 'index_request')) == 0
    assert client.delete(f'/api/v1/documents/{a}').status_code == 204
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0
        assert session.scalar(select(func.count()).select_from(AIUsage)) > 0


@pytest.mark.parametrize('first,second,kind',[
    ('Un budget de 120 euros.','Un budget de 150 euros.','modified'),
    ('Premier paragraphe.','Premier paragraphe.\n\nNouveau texte.','added'),
    ('Premier paragraphe.\n\nAncien texte.','Premier paragraphe.','removed'),
    ('Alpha.\n\nBeta.\n\nGamma.','Gamma.\n\nAlpha.\n\nBeta.','moved'),
])
def test_comparison_changes_pages_and_optional_summary(rag,first,second,kind):
    client, app, embedding, provider = rag
    a,b=[upload(client,text.encode()) for text in [first,second]]
    result=client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':b})
    assert result.status_code == 200, result.text
    data=result.json()
    assert kind in [change['kind'] for change in data['changes']]
    assert all(side['pages']==[1] for change in data['changes'] for side in [change['before'],change['after']] if side)
    response=client.post(f"/api/v1/comparisons/{data['id']}/summarize",json=payload())
    assert response.status_code==200,response.text
    summary=response.json()
    assert summary['ai_summary']['observations']
    assert client.get(f"/api/v1/comparisons/{data['id']}").json()['ai_summary']


def test_identical_formatting_and_long_document_limits(rag):
    client,app,embedding,provider=rag
    a=upload(client,b'Identical text.\nWrapped text.')
    b=upload(client,b'Identical text. Wrapped text.')
    result=client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':b}).json()
    assert result['identical'] and result['changes']==[]
    assert client.post(f"/api/v1/comparisons/{result['id']}/summarize",json=payload()).status_code==200
    assert not provider.calls
    app.state.settings.comparison_max_chars=10
    c=upload(client,b'A different very long paragraph for testing.')
    assert client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':c}).status_code==413


def test_embedding_budget_and_quota_enforced_before_provider(rag):
    client,app,embedding,_=rag
    a=upload(client)
    app.state.settings.ai_budget_usd=Decimal('0')
    assert index(client,a)['error_code']=='budget_exhausted'
    assert not embedding.calls
    app.state.settings.ai_budget_usd=Decimal('4')
    app.state.settings.embedding_batch_quota=0
    assert index(client,a)['error_code']=='quota_reached'
    assert not embedding.calls


def test_byok_expiration_between_batches_and_resume(accounts, monkeypatch):
    import time
    client, app = accounts
    monkeypatch.setattr('openai.OpenAI', lambda **kwargs: pytest.fail('External OpenAI forbidden'))
    app.state.settings.ai_enabled = True
    app.state.settings.ai_requests_per_minute = 60
    app.state.settings.embedding_batch_size = 1
    app.state.settings.embedding_dimensions = 16
    token = login(client, 'alice'); connect(client)
    identifier = upload(client, ('Le budget Atlas reste confidentiel. '*100).encode())
    provider = MockEmbeddingProvider(16)
    original = provider.embed
    context = app.state.session_vault.resolve(token)
    def expiring(*args):
        result = original(*args)
        context.expires_at = time.time()-1
        return result
    provider.embed=expiring; app.state.embedding_provider=provider
    response=client.post(f'/api/v1/documents/{identifier}/index',json=payload())
    assert response.status_code==202
    with app.state.sessions() as session:
        job=session.scalar(select(IndexJob))
        assert job.status=='paused' and job.completed==1
        assert session.get(AIBudget, f'byok:{UUID(int=101)}:openai').spent_usd>0
        assert session.get(AIBudget, 'development').spent_usd==0
    login(client,'alice');connect(client)
    provider.embed=original
    result=index(client,identifier)
    assert result['status']=='completed' and len(provider.calls)==result['total']


def test_byok_embedding_concurrency_and_personal_budget(accounts,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.auth import User
    from backend.ai.service import cost
    from backend.rag.billing import embedding_settings
    client, app=accounts
    monkeypatch.setattr('openai.OpenAI', lambda **kwargs: pytest.fail('External OpenAI forbidden'))
    app.state.settings.ai_enabled=True
    app.state.settings.embedding_dimensions=16
    login(client,'alice');connect(client)
    ids=[upload(client,b'Budget Atlas 120 euros.') for _ in range(2)]
    limit=cost(embedding_settings(app.state.settings),len(b'Budget Atlas 120 euros.')+128,0)
    with app.state.sessions() as session:
        user=session.scalar(select(User).where(User.username=='alice'));user.ai_limit_usd=limit;session.commit()
    entered, release=Event(),Event()
    provider=MockEmbeddingProvider(16);original=provider.embed
    def blocked(*args):
        entered.set();assert release.wait(10);return original(*args)
    provider.embed=blocked;app.state.embedding_provider=provider
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(client.post,f'/api/v1/documents/{ids[0]}/index',json=payload())
        assert entered.wait(10)
        try:
            assert index(client,ids[1])['error_code']=='budget_exhausted'
            assert client.delete(f'/api/v1/documents/{ids[0]}').status_code==409
        finally: release.set()
        assert first.result().status_code==202
    assert len(provider.calls)==1


def test_force_index_request_replay_does_not_charge_again(rag):
    client,app,embedding,_=rag
    identifier=upload(client)
    index(client,identifier)
    body=payload(force=True)
    assert client.post(f'/api/v1/documents/{identifier}/index',json=body).status_code==202
    calls=len(embedding.calls)
    assert client.post(f'/api/v1/documents/{identifier}/index',json=body).status_code==202
    assert len(embedding.calls)==calls


def test_pdf_source_pages_and_comparison_long_blocks(rag):
    import fitz
    client,app,embedding,_=rag
    pdf=fitz.open()
    for value in ['Introduction du projet.', 'Le budget Atlas est de 500 euros.']:
        page=pdf.new_page();page.insert_text((72,72),value)
    content=pdf.tobytes();pdf.close()
    identifier=client.post('/api/v1/documents',files={'file':('atlas.pdf',content,'application/pdf')}).json()['id']
    index(client,identifier)
    result=client.post('/api/v1/search/semantic',json=query([identifier],semantic=False)).json()
    assert result['passages'][0]['page_number']==2
    first='\n\n'.join(f'Paragraphe {number} : le budget reste stable.' for number in range(300))
    second=first.replace('Paragraphe 150 : le budget reste stable.','Paragraphe 150 : le budget devient 250 euros.')
    a,b=[upload(client,text.encode()) for text in [first,second]]
    comparison=client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':b})
    assert comparison.status_code==200,comparison.text
    assert len(comparison.json()['changes'])==1 and comparison.json()['changes'][0]['kind']=='modified'


def test_fabricated_comparison_reference_is_rejected_and_accounted(rag):
    from backend.ai.providers import ProviderResult
    client,app,embedding,provider=rag
    a,b=[upload(client,text) for text in [b'Budget de 120 euros.',b'Budget de 150 euros.']]
    comparison=client.post('/api/v1/documents/compare',json={'document_a':a,'document_b':b}).json()
    provider.generate=lambda *args: ProviderResult({'observations':[{'change_id':'invented','theme':'Budget',
        'summary':'Fausse référence.','review':'Vérifier.'}],'limitations':[]},100,80)
    result=client.post(f"/api/v1/comparisons/{comparison['id']}/summarize",json=payload())
    assert result.status_code==502
    assert client.get(f"/api/v1/comparisons/{comparison['id']}").json()['ai_summary'] is None
    with app.state.sessions() as session:
        assert session.get(AIBudget,'development').spent_usd>0
        assert session.get(AIBudget,'development').reserved_usd==0


def test_invalid_embedding_dimensions_do_not_persist_but_usage_is_kept(rag):
    from backend.rag.providers import EmbeddingResult
    client,app,embedding,_=rag
    identifier=upload(client)
    embedding.embed=lambda *args: EmbeddingResult([[1.,0.]],10)
    result=index(client,identifier)
    assert result['status']=='failed' and result['error_code']=='invalid_output'
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChunkEmbedding))==0
        assert session.scalar(select(func.count()).select_from(AIUsage))==1
        assert session.get(AIBudget,'development').reserved_usd==0
