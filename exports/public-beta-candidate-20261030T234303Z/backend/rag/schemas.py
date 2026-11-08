from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator
from ..ai.schemas import StrictModel, SummaryRequest, AnswerContent


class IndexRequest(SummaryRequest):
    force: bool = False


class JobOut(StrictModel):
    id: UUID
    document_id: UUID
    model: str
    dimensions: int
    version: str
    status: str
    completed: int
    total: int
    error_code: str | None
    updated_at: datetime


class SearchRequest(StrictModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=3, max_length=1000)
    semantic: bool = False
    consent: bool = False
    idempotency_key: UUID
    limit: int = Field(8, ge=1, le=20)

    @field_validator('query')
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Recherche trop courte')
        return value.strip()

    @field_validator('document_ids')
    @classmethod
    def unique_documents(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Documents dupliqués')
        return value


class Passage(StrictModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    start_char: int
    end_char: int
    excerpt: str
    rrf_score: float
    lexical_rank: int | None
    vector_rank: int | None
    cosine_distance: float | None


class SearchOut(StrictModel):
    passages: list[Passage]
    strategy: str
    notice: str
    cached: bool = False


class AskOut(StrictModel):
    id: UUID
    content: AnswerContent
    sources: list[Passage]
    strategy: str
    cached: bool = False


class CompareRequest(StrictModel):
    document_a: UUID
    document_b: UUID


class DiffSide(StrictModel):
    text: str
    pages: list[int]


class Change(StrictModel):
    id: str
    kind: Literal['added', 'removed', 'modified', 'moved']
    before: DiffSide | None
    after: DiffSide | None


class Observation(StrictModel):
    change_id: str
    theme: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    review: str = Field(min_length=1, max_length=1000)


class ComparisonSummary(StrictModel):
    observations: list[Observation] = Field(max_length=30)
    limitations: list[str] = Field(max_length=10)


class ComparisonOut(StrictModel):
    id: UUID
    document_a: UUID
    document_b: UUID
    filename_a: str
    filename_b: str
    identical: bool
    changes: list[Change]
    unchanged_blocks: int
    ai_summary: ComparisonSummary | None = None
    summary_coverage: str | None = None
    created_at: datetime
