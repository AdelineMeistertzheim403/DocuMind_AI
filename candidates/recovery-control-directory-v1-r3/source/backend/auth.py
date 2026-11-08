"""Local account authentication; OpenAI keys exist only inside short-lived sessions."""
import base64
import hashlib
import secrets
import threading
import time
from functools import wraps
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import DateTime, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

from .db import Base
from .models import now


class User(Base):
    __tablename__ = 'users'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    ai_limit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), default=Decimal(4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_kind: Mapped[str] = mapped_column(String(16), default='legacy', server_default='legacy')
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_version: Mapped[str | None] = mapped_column(String(40))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)
PASSWORD_SLOTS = threading.BoundedSemaphore(2)


def bounded_password_work(function):
    @wraps(function)
    def run(*args,**kwargs):
        if not PASSWORD_SLOTS.acquire(timeout=1):
            raise HTTPException(503,'Capacité de vérification atteinte')
        try:
            return function(*args,**kwargs)
        finally:
            PASSWORD_SLOTS.release()
    return run


@bounded_password_work
def hash_password(password):
    return PASSWORD_HASHER.hash(password)


@bounded_password_work
def verify_password(password, encoded):
    try:
        if encoded.startswith('$argon2id$'):
            return PASSWORD_HASHER.verify(encoded, password)
        modern = encoded.startswith('scrypt65536$')
        raw = base64.b64decode(encoded.split('$', 1)[1] if modern else encoded)
        digest = hashlib.scrypt(password.encode(), salt=raw[:16], n=65536 if modern else 16384, r=8, p=1, maxmem=128 * 1024 * 1024)
        return secrets.compare_digest(digest, raw[16:])
    except (ValueError, TypeError, VerificationError, InvalidHashError):
        return False


DUMMY_HASH = hash_password('dummy-password-for-equal-timing')


@dataclass(repr=False)
class UserSession:
    owner_id: UUID
    user_id: UUID
    expires_at: float
    mode: str = 'USER_BYOK'
    key: str | None = None
    validated: bool = False


class SessionVault:
    def __init__(self, ttl):
        self.ttl, self.lock = ttl, threading.RLock()
        self.sessions = {}
        self.attempts = {}

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def purge(self):
        for token in list(self.sessions):
            if self.sessions[token].expires_at <= time.time():
                self.sessions[token].key = None
                del self.sessions[token]
        self.attempts = {key: values for key, values in self.attempts.items() if values[-1] > time.time() - 60}

    def create(self, user):
        with self.lock:
            self.purge()
            if len(self.sessions) >= 256:
                raise HTTPException(503, 'Trop de sessions actives')
            token = secrets.token_urlsafe(32)
            self.sessions[self.digest(token)] = UserSession(user.owner_id, user.id, time.time() + self.ttl)
            return token

    def resolve(self, token):
        with self.lock:
            self.purge()
            session = self.sessions.get(self.digest(token))
            if session is None:
                raise HTTPException(401, 'Session absente ou expirée')
            return session

    def revoke(self, token):
        with self.lock:
            session = self.sessions.pop(self.digest(token), None)
            if session:
                session.key = None
                session.expires_at = 0

    def revoke_user(self, user_id, except_token=None):
        with self.lock:
            for digest, context in list(self.sessions.items()):
                if context.user_id == user_id and digest != except_token:
                    context.key = None
                    context.expires_at = 0
                    del self.sessions[digest]

    def clear(self):
        with self.lock:
            for session in self.sessions.values():
                session.key = None
                session.expires_at = 0
            self.sessions.clear()
            self.attempts.clear()

    def login_limit(self, username):
        with self.lock:
            self.purge()
            key = self.digest(username)
            if key not in self.attempts and len(self.attempts) >= 512:
                raise HTTPException(429, 'Trop de tentatives de connexion')
            previous = [value for value in self.attempts.get(key, []) if value > time.time() - 60]
            if len(previous) >= 5:
                raise HTTPException(429, 'Trop de tentatives. Attendez une minute.')
            self.attempts[key] = [*previous, time.time()]
