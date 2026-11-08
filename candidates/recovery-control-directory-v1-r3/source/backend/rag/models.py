from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import now
from ..ai.models import json_type


class ChunkEmbedding(Base):
    __tablename__ = 'chunk_embeddings'
    __table_args__ = (UniqueConstraint('chunk_id', 'model', 'dimensions', 'version'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey('document_chunks.id', ondelete='CASCADE'), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    vector: Mapped[list] = mapped_column(Vector().with_variant(JSON, 'sqlite'))
    model: Mapped[str] = mapped_column(String(100))
    dimensions: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(40))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IndexJob(Base):
    __tablename__ = 'index_jobs'
    __table_args__ = (UniqueConstraint('document_id', 'model', 'dimensions', 'version'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    generation: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model: Mapped[str] = mapped_column(String(100))
    dimensions: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default='queued')
    completed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RAGResult(Base):
    __tablename__ = 'rag_results'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    reservation_id: Mapped[UUID | None] = mapped_column(ForeignKey('ai_reservations.id'), unique=True)
    content: Mapped[dict] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RAGDocument(Base):
    __tablename__ = 'rag_documents'
    __table_args__ = (UniqueConstraint('result_id', 'document_id'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    result_id: Mapped[UUID] = mapped_column(ForeignKey('rag_results.id', ondelete='CASCADE'), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)


class OperationDocument(Base):
    __tablename__ = 'ai_operation_documents'
    reservation_id: Mapped[UUID] = mapped_column(ForeignKey('ai_reservations.id'), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
