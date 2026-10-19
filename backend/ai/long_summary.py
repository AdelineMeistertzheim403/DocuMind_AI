"""Dedicated worker and durable, budgeted, resumable map/reduce summaries."""
import queue
import threading
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func

from ..models import now
from ..services.documents import owned_document
from ..rag.providers import runtime_settings
from ..rag.billing import fingerprint
from .models import AIReservation, AIUsage, AISummary, AISource
from .long_models import LongSummaryJob, SummaryStep
from .long_plan import LongDocumentSummarizer, intermediate_schema
from .schemas import SummaryContent
from .providers import ProviderError, input_bound
from .service import (reserve, lock_budget, fail, configuration_issue, cost, record_usage,
                      validate_content, apply_settlement, result_out)

SNAPSHOT = ['openai_model','ai_provider','ai_max_input_tokens','ai_max_output_tokens',
            'ai_input_usd_per_million','ai_output_usd_per_million','ai_pricing_model','ai_pricing_verified_on']
ACTIVE = ['pending','processing','partial']


def owned_job(session, identifier, owner):
    row=session.scalar(select(LongSummaryJob).where(LongSummaryJob.id==identifier,LongSummaryJob.owner_id==owner))
    if row is None: fail('not_found',404)
    owned_document(session,row.document_id,owner)
    return row


def public_plan(plan):
    return {key:value for key,value in plan.items() if key!='nodes'}


def job_out(session, job):
    steps=session.scalars(select(SummaryStep).where(SummaryStep.job_id==job.id)).all()
    done=[step for step in steps if step.status=='completed']
    map_ids={node['id'] for node in job.plan['nodes'] if not node['parents']}
    maps={node['id']:{item['page_number'] for item in node['passages']} for node in job.plan['nodes'] if not node['parents']}
    completed_maps={step.node_id for step in done if step.node_id in map_ids}
    covered=sorted(page for page in {page for pages in maps.values() for page in pages}
                   if all(identifier in completed_maps for identifier,pages in maps.items() if page in pages))
    empty=job.plan['empty_pages']
    unprocessed=[page for page in range(1,job.plan['pages_total']+1) if page not in covered and page not in empty]
    result=session.scalar(select(AISummary).where(AISummary.reservation_id==job.reservation_id))
    return {'id':str(job.id),'document_id':str(job.document_id),'status':job.status,'error_code':job.error_code,
        'plan':public_plan(job.plan),'completed_steps':job.completed_steps,'covered_pages':covered,
        'unprocessed_pages':unprocessed,'empty_pages':empty,'cancel_requested':job.cancel_requested,
        'partials':[{'node_id':step.node_id,'summary':step.content.get('summary',''),'pages':step.pages,
            'source_ids':step.content.get('source_ids',[])} for step in done if step.node_id in map_ids],
        'result':result_out(session,result,'summary',True).model_dump(mode='json') if result else None,
        'updated_at':job.updated_at}


def start(request, session, settings, owner, document_id, body):
    document=owned_document(session,document_id,owner)
    plan=LongDocumentSummarizer(settings).plan(session,document)
    approved=getattr(body,'approved_maximum_usd',None)
    if approved is not None and Decimal(plan['maximum_usd'])>approved:
        fail('estimate_changed',409)
    digest=fingerprint('long-summary-v1',document_id,document.sha256,settings.ai_budget_scope,
        settings.openai_model,settings.ai_provider,plan['nodes'],plan['summary_chars'],settings.ai_max_output_tokens)
    previous=session.scalar(select(AIReservation).where(AIReservation.owner_id==owner,
        AIReservation.idempotency_key==body.idempotency_key))
    if previous:
        if previous.request_hash!=digest: fail('idempotency_conflict',409)
        job=session.scalar(select(LongSummaryJob).where(LongSummaryJob.reservation_id==previous.id))
        if job: return job_out(session,job)
    # Multiple confirmation clicks reuse the same task, including paused tasks.
    job=session.scalar(select(LongSummaryJob).join(AIReservation,AIReservation.id==LongSummaryJob.reservation_id).where(
        LongSummaryJob.owner_id==owner,LongSummaryJob.document_id==document_id,AIReservation.request_hash==digest)
        .order_by(LongSummaryJob.created_at.desc()).limit(1))
    if job and job.status!='cancelled': return job_out(session,job)
    reusable={step.node_id:step for step in session.scalars(select(SummaryStep).where(
        SummaryStep.job_id==job.id,SummaryStep.status=='completed'))} if job else {}
    reservation_id,cached=reserve(session,settings,owner,document_id,body.idempotency_key,digest,'summary',plan['steps'])
    if cached: return {'status':'completed','result':cached.model_dump(mode='json')}
    try:
        job=LongSummaryJob(owner_id=owner,document_id=document_id,reservation_id=reservation_id,plan=plan,
            configuration={key:str(getattr(settings,key)) if isinstance(getattr(settings,key),Decimal) else getattr(settings,key) for key in SNAPSHOT})
        session.add(job);session.flush()
        for node in plan['nodes']:
            passages=node.get('passages',[])
            previous=reusable.get(node['id'])
            session.add(SummaryStep(job_id=job.id,node_id=node['id'],chunk_ids=previous.chunk_ids if previous else list(dict.fromkeys(item['chunk_id'] for item in passages)),
                pages=previous.pages if previous else sorted({item['page_number'] for item in passages}),
                status='completed' if previous else 'pending',content=previous.content if previous else None))
            if previous: job.completed_steps+=1
        session.commit()
        output=job_out(session,job)
        request.app.state.summary_worker.submit(job.id,getattr(request.state,'user_session',None))
        return output
    except Exception:
        session.rollback()
        from .service import settle
        settle(session,reservation_id,'worker_unavailable',503)
        raise


def recover(app):
    with app.state.sessions() as session:
        for job in session.scalars(select(LongSummaryJob).where(LongSummaryJob.status.in_(['pending','processing']))):
            active=session.scalars(select(SummaryStep).where(SummaryStep.job_id==job.id,SummaryStep.status=='processing')).all()
            for step in active: step.status='uncertain'
            job.status='partial' if job.completed_steps or active else 'pending'
            job.error_code='provider_uncertain' if active else 'session_required'
            if active:
                session.get(AIReservation,job.reservation_id).status='uncertain'
        session.commit()


def cancel(session, settings, job):
    budget=lock_budget(session,session.get(AIReservation,job.reservation_id).budget_id)
    job=session.get(LongSummaryJob,job.id,populate_existing=True)
    if job.status in ['completed','cancelled']: return job_out(session,job)
    job.cancel_requested=True
    active=session.scalar(select(SummaryStep.id).where(SummaryStep.job_id==job.id,SummaryStep.status=='processing').limit(1))
    if not active:
        reservation=session.get(AIReservation,job.reservation_id)
        if reservation.status in ['reserved','uncertain']:
            apply_settlement(session,budget,job.reservation_id,'cancelled',409,reservation.status=='uncertain')
        job.status='cancelled'
    job.updated_at=now();session.commit()
    return job_out(session,job)


def resume(request, session, settings, owner, identifier):
    job=owned_job(session,identifier,owner)
    budget=lock_budget(session,session.get(AIReservation,job.reservation_id).budget_id)
    job=session.get(LongSummaryJob,identifier,populate_existing=True)
    reservation=session.get(AIReservation,job.reservation_id)
    if job.status in ['completed','cancelled']: return job_out(session,job)
    issue=configuration_issue(settings)
    if issue: fail(issue,403 if issue=='disabled' else 503)
    if settings.ai_budget_scope!=reservation.budget_id: fail('session_required',403)
    if reservation.status!='reserved': fail('provider_uncertain',409)
    if job.status=='processing' or request.app.state.summary_worker.contains(job.id): return job_out(session,job)
    job.status,job.error_code='pending',None;session.commit()
    output=job_out(session,job)
    request.app.state.summary_worker.submit(job.id,getattr(request.state,'user_session',None))
    return output


class SummaryWorker:
    def __init__(self, app):
        self.app,self.queue,self.stopping=app,queue.Queue(),threading.Event()
        self.lock,self.active=threading.Lock(),set()
        self.thread=threading.Thread(target=self.loop,name='documind-long-summary',daemon=True)

    def contains(self,identifier):
        with self.lock: return identifier in self.active

    def submit(self,identifier,context):
        with self.lock:
            if identifier in self.active: return
            self.active.add(identifier)
        self.queue.put((identifier,context))

    def loop(self):
        while not self.stopping.is_set():
            try: identifier,context=self.queue.get(timeout=.2)
            except queue.Empty: continue
            try: self.run(identifier,context)
            except Exception:
                # Never log input, provider exception, configuration or credentials.
                import logging
                logging.getLogger(__name__).error('long_summary_worker_failed job=%s',identifier)
            finally:
                with self.lock: self.active.discard(identifier)

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=self.app.state.settings.ai_timeout_seconds+5)

    def run(self,identifier,context):
        from .api import ConfiguredProvider
        with self.app.state.sessions() as session:
            job=session.get(LongSummaryJob,identifier)
            if job is None or job.status in ['completed','cancelled']: return
            reservation_id=job.reservation_id
            current_step=None
            try:
                for node in job.plan['nodes']:
                    job=session.get(LongSummaryJob,identifier,populate_existing=True)
                    if job.cancel_requested:
                        cancel(session,self.app.state.settings,job);return
                    if self.stopping.is_set():
                        job.status='partial';job.error_code='worker_stopped';session.commit();return
                    settings=runtime_settings(self.app,session,context)
                    reservation=session.get(AIReservation,reservation_id)
                    if settings.ai_budget_scope!=reservation.budget_id: raise ProviderError('session_required',403,False,0)
                    snapshot=dict(job.configuration)
                    for key in ['ai_input_usd_per_million','ai_output_usd_per_million']: snapshot[key]=Decimal(snapshot[key])
                    settings=settings.model_copy(update=snapshot)
                    issue=configuration_issue(settings)
                    if issue: raise ProviderError(issue,403,False,0)
                    step=session.scalar(select(SummaryStep).where(SummaryStep.job_id==identifier,SummaryStep.node_id==node['id']))
                    if step.status=='completed': continue
                    if step.status=='uncertain': raise ProviderError('provider_uncertain',503,True,0)
                    parents=[session.scalar(select(SummaryStep).where(SummaryStep.job_id==identifier,SummaryStep.node_id==parent)) for parent in node['parents']]
                    root=node['id']==job.plan['root']
                    schema=SummaryContent if root else intermediate_schema(job.plan['summary_chars'])
                    if parents:
                        payload={'operation':'synthesis','partial_summaries':[parent.content for parent in parents]}
                        allowed={source for parent in parents for source in parent.content['source_ids']}
                        chunk_ids=list(dict.fromkeys(source for parent in parents for source in parent.chunk_ids))
                        pages=sorted({page for parent in parents for page in parent.pages})
                    else:
                        payload={'operation':'summary','passages':node['passages']}
                        allowed=set(step.chunk_ids);chunk_ids,pages=step.chunk_ids,step.pages
                    if input_bound(payload,schema)>job.plan['input_limit']: fail('context_limit',413)
                    budget=lock_budget(session,reservation.budget_id)
                    job=session.get(LongSummaryJob,identifier,populate_existing=True)
                    step=session.get(SummaryStep,step.id,populate_existing=True)
                    if job.cancel_requested:
                        session.rollback();cancel(session,settings,job);return
                    spent=session.scalar(select(func.coalesce(func.sum(AIUsage.estimated_usd),0)).where(AIUsage.reservation_id==reservation_id))
                    if job.attempts+2>job.plan['steps']*2 or spent+cost(settings,settings.ai_max_input_tokens,settings.ai_max_output_tokens)*2>reservation.reserved_usd:
                        fail('budget_exhausted',402)
                    job.status='processing';job.attempts+=2;job.updated_at=now()
                    step.status='processing';session.commit();current_step=step.id
                    latest=runtime_settings(self.app,session,context)
                    if latest.openai_api_key!=settings.openai_api_key: raise ProviderError('byok_disconnected',403,False,0)
                    provider=ConfiguredProvider(SimpleNamespace(app=self.app,state=SimpleNamespace(user_session=context)),settings)
                    response=provider.generate(payload,schema,f'{reservation_id}:{node["id"]}')
                    record_usage(session,settings,reservation_id,response)
                    # A received, billed response consumes only the attempts actually made,
                    # including when subsequent validation rejects its content.
                    job=session.get(LongSummaryJob,identifier,populate_existing=True)
                    job.attempts-=2-response.attempts
                    session.commit()
                    content=validate_content(response,schema,allowed)
                    budget=lock_budget(session,reservation.budget_id)
                    job=session.get(LongSummaryJob,identifier,populate_existing=True)
                    step=session.get(SummaryStep,current_step,populate_existing=True)
                    step.content=content.model_dump();step.chunk_ids=chunk_ids;step.pages=pages;step.status='completed';step.updated_at=now()
                    job.completed_steps+=1;job.updated_at=now();job.error_code=None
                    if job.cancel_requested:
                        apply_settlement(session,budget,reservation_id,'cancelled',409)
                        job.status='cancelled';session.commit();return
                    if root:
                        result=AISummary(owner_id=job.owner_id,document_id=job.document_id,reservation_id=reservation_id,
                            content=content.model_dump(),coverage=f'Document intégral : {job.plan["parts"]} parties, {job.plan["steps"]} étapes sur {job.plan["levels"]} niveaux ; {len(job.plan["empty_pages"])} page(s) vide(s).')
                        session.add(result)
                        for source in content.source_ids:
                            session.add(AISource(reservation_id=reservation_id,document_id=job.document_id,chunk_id=UUID(source)))
                        apply_settlement(session,budget,reservation_id)
                        job.status='completed'
                    session.commit();current_step=None
                return
            except Exception as exc:
                session.rollback()
                reservation=session.get(AIReservation,reservation_id)
                budget=lock_budget(session,reservation.budget_id)
                job=session.get(LongSummaryJob,identifier,populate_existing=True)
                if job is None: return
                code=exc.code if isinstance(exc,ProviderError) else (exc.detail.get('code','invalid_output') if isinstance(exc,HTTPException) and isinstance(exc.detail,dict) else 'provider_uncertain')
                uncertain=(isinstance(exc,ProviderError) and exc.uncertain) or not isinstance(exc,(ProviderError,HTTPException))
                if isinstance(exc,ProviderError):
                    session.get(AIReservation,reservation_id).provider_calls+=exc.attempts
                    if current_step: job.attempts-=2-exc.attempts
                if current_step:
                    step=session.get(SummaryStep,current_step)
                    step.status='uncertain' if uncertain else 'failed'
                if uncertain: session.get(AIReservation,reservation_id).status='uncertain'
                job.status='partial' if job.completed_steps or uncertain or code in ['byok_disconnected','session_required','disabled','worker_stopped'] else 'failed'
                job.error_code,job.updated_at=code,now()
                # Keep the global reservation for a safe resume/cancel; no second user quota is consumed.
                session.commit()
