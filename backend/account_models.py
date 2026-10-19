"""Personal workspaces keep historical owner UUIDs; sharing is intentionally disabled."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now


class Workspace(Base):
    __tablename__ = 'workspaces'
    owner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default='Espace personnel')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkspaceMembership(Base):
    __tablename__ = 'workspace_memberships'
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.owner_id'), unique=True)
    role: Mapped[str] = mapped_column(String(20), default='owner')


class AccountToken(Base):
    __tablename__ = 'account_tokens'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(254), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionRequest(Base):
    __tablename__ = 'account_deletion_requests'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
