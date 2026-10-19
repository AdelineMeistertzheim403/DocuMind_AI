from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import now
from .models import json_type


class LongSummaryJob(Base):
    __tablename__ = 'long_summary_jobs'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), unique=True)
    status: Mapped[str] = mapped_column(String(24), default='pending')
    plan: Mapped[dict] = mapped_column(json_type)
    configuration: Mapped[dict] = mapped_column(json_type)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SummaryStep(Base):
    __tablename__ = 'summary_steps'
    __table_args__ = (UniqueConstraint('job_id', 'node_id'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey('long_summary_jobs.id', ondelete='CASCADE'), index=True)
    node_id: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default='pending')
    content: Mapped[dict | None] = mapped_column(json_type)
    chunk_ids: Mapped[list] = mapped_column(json_type)
    pages: Mapped[list] = mapped_column(json_type)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
