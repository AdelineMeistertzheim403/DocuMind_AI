from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..api import Owner, Session
from ..services.documents import owned_document
from .schemas import SummaryRequest, AIResultOut
from .settings_api import settings_for_request
from .long_models import LongSummaryJob
from .long_plan import LongDocumentSummarizer
from . import long_summary


class SummaryPlanOut(BaseModel):
    direct: bool
    parts: int
    steps: int
    levels: int
    root: str
    summary_chars: int
    pages_total: int
    empty_pages: list[int]
    maximum_usd: float
    input_limit: int
    overlap_chars: int


class PartialOut(BaseModel):
    node_id: str
    summary: str
    pages: list[int]
    source_ids: list[str]


class LongStartRequest(SummaryRequest):
    approved_maximum_usd: Decimal | None = Field(None,ge=0)


class LongJobOut(BaseModel):
    id: UUID
    document_id: UUID
    status: str
    error_code: str | None
    plan: SummaryPlanOut
    completed_steps: int
    covered_pages: list[int]
    unprocessed_pages: list[int]
    empty_pages: list[int]
    cancel_requested: bool
    partials: list[PartialOut]
    result: AIResultOut | None
    updated_at: datetime


router=APIRouter(prefix='/api/v1',tags=['résumés approfondis'],responses={
    401:{'description':'Authentification requise'},402:{'description':'Budget insuffisant'},
    403:{'description':'IA ou session non disponible'},404:{'description':'Ressource non autorisée'},
    409:{'description':'Conflit ou consommation incertaine'},413:{'description':'Limite de parties ou de contexte'},
    429:{'description':'Quota ou concurrence atteints'},503:{'description':'Fournisseur ou worker indisponible'}})


@router.get('/documents/{document_id}/summary-plan',response_model=SummaryPlanOut)
def plan(document_id: UUID,request:Request,owner:Owner,session:Session):
    settings=settings_for_request(request,session)
    document=owned_document(session,document_id,owner)
    return long_summary.public_plan(LongDocumentSummarizer(settings).plan(session,document))


@router.post('/documents/{document_id}/summary-jobs',response_model=LongJobOut,status_code=202)
def create(document_id:UUID,body:LongStartRequest,request:Request,owner:Owner,session:Session):
    return long_summary.start(request,session,settings_for_request(request,session),owner,document_id,body)


@router.get('/documents/{document_id}/summary-jobs',response_model=list[LongJobOut])
def jobs(document_id:UUID,owner:Owner,session:Session):
    owned_document(session,document_id,owner)
    rows=session.scalars(select(LongSummaryJob).where(LongSummaryJob.document_id==document_id,
        LongSummaryJob.owner_id==owner).order_by(LongSummaryJob.created_at.desc()).limit(10)).all()
    return [long_summary.job_out(session,row) for row in rows]


@router.get('/summary-jobs/{job_id}',response_model=LongJobOut)
def get(job_id:UUID,owner:Owner,session:Session):
    return long_summary.job_out(session,long_summary.owned_job(session,job_id,owner))


@router.post('/summary-jobs/{job_id}/resume',response_model=LongJobOut)
def resume(job_id:UUID,body:SummaryRequest,request:Request,owner:Owner,session:Session):
    return long_summary.resume(request,session,settings_for_request(request,session),owner,job_id)


@router.post('/summary-jobs/{job_id}/cancel',response_model=LongJobOut)
def cancel(job_id:UUID,request:Request,owner:Owner,session:Session):
    return long_summary.cancel(session,request.app.state.settings,long_summary.owned_job(session,job_id,owner))
