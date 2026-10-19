import time
from decimal import Decimal
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import select, func

from tests.test_ai import ai, upload, payload
from tests.test_byok import accounts, login, connect
from tests.conftest import OTHER_KEY, KEY
from backend.ai.providers import MockAIProvider, ProviderError
from backend.ai.models import AIBudget, AIReservation, AIUsage
from backend.ai.long_models import LongSummaryJob, SummaryStep
from backend.ai.long_summary import recover, SummaryWorker


def wait_job(client,identifier,statuses=('completed','partial','failed','cancelled')):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        response=client.get(f'/api/v1/summary-jobs/{identifier}')
        assert response.status_code==200,response.text
        if response.json()['status'] in statuses: return response.json()
        time.sleep(.03)
    pytest.fail('Summary worker did not reach an expected status')


def long_text():
    return ('Chapitre 1 : Atlas\n\nLe projet Atlas a un budget de 120 euros. Camille est responsable.\n\n'*1100).encode()


def test_short_plan_and_direct_summary_are_preserved(ai):
    client,app,provider=ai
    identifier=upload(client)
    plan=client.get(f'/api/v1/documents/{identifier}/summary-plan').json()
    assert plan['direct'] and plan['steps']==1 and not provider.calls
    assert client.post(f'/api/v1/documents/{identifier}/summarize',json=payload()).status_code==200


@pytest.mark.parametrize('pages,chars',[(20,1600),(53,1742),(200,400)])
def test_large_pdfs_multilevel_complete_with_page_provenance(ai,pages,chars):
    import pymupdf
    client,app,provider=ai
    pdf=pymupdf.open()
    for number in range(pages):
        page=pdf.new_page()
        text=(f'Chapitre {number+1}. Le projet Atlas utilise un budget de 120 euros. Camille le suit.\n'*40)[:chars]
        assert page.insert_textbox(pymupdf.Rect(36,36,560,780),text,fontsize=8)>=0
    content=pdf.tobytes();pdf.close()
    response=client.post('/api/v1/documents',files={'file':('synthetic-long.pdf',content,'application/pdf')})
    assert response.status_code==201,response.text
    identifier=response.json()['id']
    plan=client.get(f'/api/v1/documents/{identifier}/summary-plan').json()
    assert not plan['direct'] and plan['steps']>1 and plan['levels']>=2 and not provider.calls
    body=payload()
    response=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=body)
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['id'])
    assert job['status']=='completed',job['error_code']
    assert job['covered_pages']==list(range(1,pages+1)) and job['unprocessed_pages']==[]
    assert job['completed_steps']==plan['steps'] and len(provider.calls)==plan['steps']
    assert job['result']['sources'] and 'intégral' in job['result']['coverage']
    assert client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=body).json()['id']==job['id']
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(AIReservation))==1
        assert session.scalar(select(func.count()).select_from(AIUsage))==plan['steps']
        assert session.get(AIBudget,'development').reserved_usd==0
        assert session.get(AIBudget,'development').spent_usd<=Decimal(str(plan['maximum_usd']))


def test_paragraph_boundaries_empty_pages_and_budget_preflight(ai):
    import pymupdf
    client,app,provider=ai
    pdf=pymupdf.open();pdf.new_page();page=pdf.new_page();page.insert_text((36,72),'A short paragraph.');data=pdf.tobytes();pdf.close()
    identifier=client.post('/api/v1/documents',files={'file':('empty-page.pdf',data,'application/pdf')}).json()['id']
    plan=client.get(f'/api/v1/documents/{identifier}/summary-plan').json()
    assert plan['empty_pages']==[1] and not provider.calls
    identifier=upload(client,long_text())
    from backend.ai.long_plan import LongDocumentSummarizer
    from backend.models import Document
    with app.state.sessions() as session:
        plan=LongDocumentSummarizer(app.state.settings).plan(session,session.get(Document,UUID(identifier)))
        assert plan['levels']>=3
        groups=[node['passages'] for node in plan['nodes'] if not node['parents']]
        assert any(part['text'].endswith('\n\n') for group in groups for part in group)
    app.state.settings.ai_budget_usd=Decimal('0')
    assert client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload()).status_code==402
    assert not provider.calls


def test_known_provider_error_resume_uses_saved_steps_and_one_quota(ai):
    client,app,provider=ai
    identifier=upload(client,long_text())
    original=provider.generate
    calls=[0]
    def failure(*args):
        calls[0]+=1
        if calls[0]==2: raise ProviderError('provider_rate_limit',429,False,2)
        return original(*args)
    provider.generate=failure
    response=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload())
    identifier=response.json()['id'];job=wait_job(client,identifier)
    assert job['status']=='partial' and job['completed_steps']==1 and job['unprocessed_pages']
    deadline=time.monotonic()+2
    while app.state.summary_worker.contains(UUID(identifier)) and time.monotonic()<deadline: time.sleep(.01)
    provider.generate=original
    assert client.post(f'/api/v1/summary-jobs/{identifier}/resume',json=payload()).status_code==200
    job=wait_job(client,identifier,('completed','failed'))
    assert job['status']=='completed',job['error_code']
    assert len(provider.calls)==job['plan']['steps']
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(AIReservation))==1


def test_cancel_inflight_job_accounts_response_and_stops_next_calls(ai):
    client,app,provider=ai
    identifier=upload(client,long_text())
    entered,release=Event(),Event();original=provider.generate
    def blocked(*args):
        entered.set();assert release.wait(10);return original(*args)
    provider.generate=blocked
    response=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload())
    jobid=response.json()['id'];assert entered.wait(10)
    try:
        assert client.delete(f'/api/v1/documents/{identifier}').status_code==409
        assert client.post(f'/api/v1/summary-jobs/{jobid}/cancel',json={}).json()['cancel_requested']
    finally: release.set()
    job=wait_job(client,jobid,('cancelled',))
    assert len(provider.calls)==1 and job['result'] is None
    with app.state.sessions() as session:
        assert session.get(AIBudget,'development').reserved_usd==0
        assert session.get(AIBudget,'development').spent_usd>0
    provider.generate=original
    restarted=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload())
    assert restarted.status_code==202,restarted.text
    completed=wait_job(client,restarted.json()['id'],('completed','failed'))
    assert completed['status']=='completed',completed['error_code']
    assert len(provider.calls)==completed['plan']['steps']


def test_worker_interruption_resume_and_owner_isolation(ai):
    client,app,provider=ai
    identifier=upload(client,long_text());original=provider.generate
    def stopping(*args):
        result=original(*args);app.state.summary_worker.stopping.set();return result
    provider.generate=stopping
    response=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload())
    jobid=response.json()['id'];job=wait_job(client,jobid,('partial',))
    app.state.summary_worker.thread.join(2)
    assert job['completed_steps']==1
    recover(app)
    app.state.summary_worker=SummaryWorker(app);app.state.summary_worker.thread.start()
    provider.generate=original
    client.headers['X-API-Key']=OTHER_KEY
    assert client.get(f'/api/v1/summary-jobs/{jobid}').status_code==404
    assert client.post(f'/api/v1/summary-jobs/{jobid}/resume',json=payload()).status_code==404
    client.headers['X-API-Key']=KEY
    client.post(f'/api/v1/summary-jobs/{jobid}/resume',json=payload())
    job=wait_job(client,jobid,('completed','failed'))
    assert job['status']=='completed' and len(provider.calls)==job['plan']['steps']


def test_byok_expiration_and_reattach_without_rebilling_completed_part(accounts,monkeypatch):
    client,app=accounts
    monkeypatch.setattr('openai.OpenAI',lambda **kwargs:pytest.fail('External call forbidden'))
    app.state.settings.ai_enabled=True
    token=login(client,'alice');connect(client)
    identifier=upload(client,long_text());provider=MockAIProvider();app.state.ai_provider=provider
    original=provider.generate;context=app.state.session_vault.resolve(token)
    def expiring(*args):
        result=original(*args);context.expires_at=time.time()-1;return result
    provider.generate=expiring
    jobid=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload()).json()['id']
    # The session expires after the first call; inspect only administrative state until re-login.
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        with app.state.sessions() as session:
            job=session.get(LongSummaryJob,UUID(jobid))
            if job.status=='partial':break
        time.sleep(.03)
    assert job.status=='partial' and job.completed_steps==1
    login(client,'alice');connect(client);provider.generate=original
    client.post(f'/api/v1/summary-jobs/{jobid}/resume',json=payload())
    result=wait_job(client,jobid,('completed','failed'))
    assert result['status']=='completed',result['error_code']
    with app.state.sessions() as session:
        assert session.get(AIBudget,'development').spent_usd==0
        assert session.scalar(select(func.count()).select_from(AIReservation))==1


def test_global_reservation_blocks_parallel_jobs_before_provider(ai):
    client,app,provider=ai
    identifiers=[upload(client,long_text()) for _ in range(2)]
    plan=client.get(f'/api/v1/documents/{identifiers[0]}/summary-plan').json()
    app.state.settings.ai_budget_usd=Decimal(str(plan['maximum_usd']))
    entered,release=Event(),Event();original=provider.generate
    def blocked(*args):entered.set();assert release.wait(10);return original(*args)
    provider.generate=blocked
    first=client.post(f'/api/v1/documents/{identifiers[0]}/summary-jobs',json=payload()).json()
    assert entered.wait(10)
    try:
        assert client.post(f'/api/v1/documents/{identifiers[1]}/summary-jobs',json=payload()).status_code==402
        client.post(f"/api/v1/summary-jobs/{first['id']}/cancel",json={})
    finally:release.set()
    wait_job(client,first['id'],('cancelled',))
    assert len(provider.calls)==1


def test_ambiguous_call_cannot_resume_or_refund_its_hold(ai):
    client,app,provider=ai
    identifier=upload(client,long_text())
    provider.generate=lambda *args:(_ for _ in ()).throw(ProviderError('provider_uncertain',503,True))
    jobid=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload()).json()['id']
    job=wait_job(client,jobid,('partial',))
    assert job['error_code']=='provider_uncertain'
    assert client.post(f'/api/v1/summary-jobs/{jobid}/resume',json=payload()).status_code==409
    client.post(f'/api/v1/summary-jobs/{jobid}/cancel',json={})
    with app.state.sessions() as session:
        assert session.get(AIBudget,'development').reserved_usd>0
        assert session.get(AIReservation,session.get(LongSummaryJob,UUID(jobid)).reservation_id).status=='uncertain'


def test_confirmed_cost_cannot_increase_silently(ai):
    client,app,provider=ai
    identifier=upload(client,long_text())
    result=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload(approved_maximum_usd=0))
    assert result.status_code==409 and result.json()['detail']['code']=='estimate_changed'
    assert not provider.calls


def test_invalid_final_reference_preserves_steps_and_accounts_once(ai):
    client,app,provider=ai
    identifier=upload(client,long_text());original=provider.generate
    def invalid(data,schema,key):
        result=original(data,schema,key)
        if schema.__name__=='SummaryContent':result.content['source_ids']=['invented']
        return result
    provider.generate=invalid
    jobid=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload()).json()['id']
    job=wait_job(client,jobid,('partial','failed'))
    assert job['error_code']=='invalid_references' and job['result'] is None
    client.post(f'/api/v1/summary-jobs/{jobid}/cancel',json={})
    with app.state.sessions() as session:
        budget=session.get(AIBudget,'development')
        assert budget.reserved_usd==0 and budget.spent_usd>0
        spent=budget.spent_usd
    client.post(f'/api/v1/summary-jobs/{jobid}/cancel',json={})
    with app.state.sessions() as session:assert session.get(AIBudget,'development').spent_usd==spent



def test_truncated_response_preserves_checkpoint_and_counts_real_attempts_on_resume(ai):
    from backend.ai.providers import ProviderResult
    client,app,provider=ai
    identifier=upload(client,long_text());original=provider.generate;calls=[0]
    def truncated(data,schema,key):
        calls[0]+=1
        if calls[0]==2:
            return ProviderResult(None,100,1200,valid_response=False,error_code='output_truncated')
        return original(data,schema,key)
    provider.generate=truncated
    jobid=client.post(f'/api/v1/documents/{identifier}/summary-jobs',json=payload()).json()['id']
    job=wait_job(client,jobid,('partial',))
    assert job['error_code']=='output_truncated' and job['completed_steps']==1
    with app.state.sessions() as session:
        saved=session.get(LongSummaryJob,UUID(jobid))
        assert saved.attempts==2
        assert session.scalar(select(func.count()).select_from(AIUsage))==2
    assert client.post(f'/api/v1/summary-jobs/{jobid}/resume',json=payload()).status_code==200
    finished=wait_job(client,jobid,('completed',))
    with app.state.sessions() as session:
        assert session.get(LongSummaryJob,UUID(jobid)).attempts==finished['plan']['steps']+1
        assert session.scalar(select(func.count()).select_from(AIUsage))==finished['plan']['steps']+1
        assert session.scalar(select(func.count()).select_from(AIReservation))==1
