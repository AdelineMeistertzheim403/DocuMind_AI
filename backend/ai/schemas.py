from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SummaryContent(StrictModel):
    general_summary: str = Field(min_length=1, max_length=12000)
    key_points: list[str] = Field(max_length=20)
    important_information: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=20)
    source_ids: list[str] = Field(max_length=20)


class AnswerContent(StrictModel):
    answer: str = Field(min_length=1, max_length=12000)
    insufficient_information: bool
    source_ids: list[str] = Field(max_length=10)


class SummaryRequest(StrictModel):
    consent: Literal[True]
    idempotency_key: UUID


class AskRequest(SummaryRequest):
    question: str = Field(min_length=3, max_length=1000)

    @field_validator('question')
    @classmethod
    def question_not_blank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('La question doit contenir au moins 3 caractères')
        return value.strip()


class SourceOut(BaseModel):
    chunk_id: UUID
    page_number: int
    excerpt: str


class AIResultOut(BaseModel):
    id: UUID
    document_id: UUID
    feature: Literal['summary', 'question']
    question: str | None
    content: SummaryContent | AnswerContent
    sources: list[SourceOut]
    model: str
    provider: str
    created_at: datetime
    coverage: str
    cached: bool = False


class AIHistory(BaseModel):
    items: list[AIResultOut]
    total: int
    offset: int
    limit: int


class AIStatus(BaseModel):
    mode: str
    enabled: bool
    available: bool
    reason: str | None
    provider: str
    model: str
    budget_usd: float
    spent_usd: float
    reserved_usd: float
    remaining_usd: float
    summary_quota: int
    question_quota: int
    summaries_used: int
    questions_used: int
    requests: int
    provider_calls: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    pending_requests: int
    pricing_verified_on: str
