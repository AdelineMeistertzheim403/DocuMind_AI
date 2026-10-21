"""Shared account checks. Only server-created request state may cache admission."""
import secrets

from fastapi import HTTPException
from sqlalchemy import select

from .auth import User


def authenticate(request, key=None, *, charge=True):
    authorization = request.headers.get('authorization', '')
    settings = request.app.state.settings
    sessions = getattr(request.app.state, 'authentication_sessions', request.app.state.sessions)
    if authorization.startswith('Bearer '):
        token = authorization[7:]
        context = request.app.state.session_vault.resolve(token)
        with sessions() as session:
            user = session.get(User, context.user_id)
            if user is None or user.disabled_at is not None or user.owner_id != context.owner_id:
                request.app.state.session_vault.revoke(token)
                raise HTTPException(401, 'Session révoquée')
        # Recheck after SQL, which may have overlapped a logout or expiration.
        request.app.state.session_vault.resolve(token)
        request.state.user_session = context
        if charge:
            request.app.state.rate_limiter.check(f'user:{context.user_id}', settings.requests_per_minute)
        return context.owner_id
    key = request.headers.get('x-api-key', '') if key is None else key
    for expected, owner_id in (settings.api_keys.items() if settings.legacy_api_enabled else []):
        if key and secrets.compare_digest(key.encode(), expected.encode()):
            with sessions() as session:
                if session.scalar(select(User.id).where(User.owner_id == owner_id, User.disabled_at.is_not(None))):
                    raise HTTPException(403, 'Propriétaire désactivé')
            if charge:
                request.app.state.rate_limiter.check(f'owner:{owner_id}', settings.requests_per_minute)
            return owner_id
    raise HTTPException(401, 'Session ou clé API absente ou invalide', headers={'WWW-Authenticate': 'APIKey'})
