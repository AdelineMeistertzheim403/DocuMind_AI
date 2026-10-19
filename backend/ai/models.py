from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import now

json_type = JSON().with_variant(JSONB, 'postgresql')
money = Numeric(18, 10)


class AIBudget(Base):
    __tablename__ = 'ai_budgets'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    spent_usd: Mapped[Decimal] = mapped_column(money, default=Decimal('0'))
    reserved_usd: Mapped[Decimal] = mapped_column(money, default=Decimal('0'))


class AIReservation(Base):
    __tablename__ = 'ai_reservations'
    __table_args__ = (UniqueConstraint('owner_id', 'idempotency_key'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey('ai_budgets.id'))
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey('documents.id', ondelete='SET NULL'), index=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid)
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    feature: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default='reserved')
    reserved_usd: Mapped[Decimal] = mapped_column(money)
    actual_usd: Mapped[Decimal] = mapped_column(money, default=Decimal('0'))
    model: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(16))
    provider_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AIUsage(Base):
    __tablename__ = 'ai_usage'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey('documents.id', ondelete='SET NULL'))
    feature: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    reasoning_tokens: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    estimated_usd: Mapped[Decimal] = mapped_column(money)
    input_rate: Mapped[Decimal] = mapped_column(money)
    output_rate: Mapped[Decimal] = mapped_column(money)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AISummary(Base):
    __tablename__ = 'ai_summaries'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), unique=True)
    content: Mapped[dict] = mapped_column(json_type)
    coverage: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AIInteraction(Base):
    __tablename__ = 'ai_interactions'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), unique=True)
    question: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(json_type)
    coverage: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AISource(Base):
    __tablename__ = 'ai_sources'
    __table_args__ = (UniqueConstraint('reservation_id', 'chunk_id'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey('document_chunks.id', ondelete='CASCADE'))
