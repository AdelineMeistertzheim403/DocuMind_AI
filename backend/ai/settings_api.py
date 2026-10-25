import secrets
import time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select

from ..api import Owner, Session
from ..auth import DUMMY_HASH, User, verify_password, hash_password, PASSWORD_HASHER
from ..gateway import secure_gateway, client_ip

router = APIRouter(prefix='/api/v1', tags=['comptes et BYOK'])


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=254, validation_alias=AliasChoices('username', 'email'))
    password: SecretStr = Field(min_length=1, max_length=256)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    api_key: SecretStr = Field(min_length=20, max_length=256)


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['OWNER_DEMO', 'USER_BYOK']
    limit_usd: Decimal = Field(ge=0, le=100)


def user_session(request, owner_id):
    context = getattr(request.state, 'user_session', None)
    if context is None or context.owner_id != owner_id:
        raise HTTPException(401, 'Connectez-vous avec un compte personnel')
    return context


def preferences_out(context, user):
    return {'username': user.username, 'owner_id': str(user.owner_id), 'mode': context.mode,
            'limit_usd': float(user.ai_limit_usd), 'key_connected': context.key is not None,
            'key_validated': context.validated, 'expires_at': context.expires_at}


@router.post('/auth/login', dependencies=[Depends(secure_gateway)])
def login(body: Login, request: Request, session: Session):
    username = body.username.strip().lower()
    request.app.state.rate_limiter.check(f'login-ip:{client_ip(request)}', 10)
    request.app.state.session_vault.login_limit(username)
    user = session.scalar(select(User).where((User.username == username) | (User.email == username)))
    # Do a real password derivation for unknown users too.
    encoded = user.password_hash if user else DUMMY_HASH
    if (not verify_password(body.password.get_secret_value(), encoded) or user is None or user.disabled_at is not None or
            (user.registration_kind=='public' and user.email_verified_at is None)):
        raise HTTPException(401, 'Identifiants invalides')
    if not encoded.startswith('$argon2id$') or PASSWORD_HASHER.check_needs_rehash(encoded):
        user.password_hash = hash_password(body.password.get_secret_value())
        session.commit()
    old = request.headers.get('authorization', '')
    if old.startswith('Bearer '):
        request.app.state.session_vault.revoke(old[7:])
    token = request.app.state.session_vault.create(user)
    # This backend response is consumed ONLY by the BFF and stripped before browser delivery.
    return {'session_token': token, 'expires_in': request.app.state.settings.ai_session_ttl_seconds}


@router.post('/auth/logout', dependencies=[Depends(secure_gateway)])
def logout(request: Request, owner_id: Owner):
    user_session(request, owner_id)
    request.app.state.session_vault.revoke(request.headers['authorization'][7:])
    return {'connected': False}


@router.get('/ai/settings', dependencies=[Depends(secure_gateway)])
def get_settings(request: Request, owner_id: Owner, session: Session):
    context = user_session(request, owner_id)
    return preferences_out(context, session.get(User, context.user_id))


@router.put('/ai/settings', dependencies=[Depends(secure_gateway)])
def set_preferences(body: Preferences, request: Request, owner_id: Owner, session: Session):
    context = user_session(request, owner_id)
    from .service import lock_budget
    lock_budget(session, f'byok:{owner_id}:openai')
    user = session.get(User, context.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(401, 'Compte désactivé')
    if user.registration_kind=='public' and (body.mode!='USER_BYOK' or body.limit_usd>request.app.state.settings.public_ai_max_budget_usd):
        raise HTTPException(403,'La bêta publique utilise uniquement BYOK avec le budget autorisé')
    user.ai_limit_usd = body.limit_usd
    session.commit()
    with request.app.state.session_vault.lock:
        context.mode = body.mode
    return preferences_out(context, user)


@router.post('/ai/key', dependencies=[Depends(secure_gateway)])
def connect_key(body: KeyInput, request: Request, owner_id: Owner, session: Session):
    context = user_session(request, owner_id)
    key = body.api_key.get_secret_value()
    if any(character.isspace() for character in key):
        raise HTTPException(422, 'Format de clé non valide')
    with request.app.state.session_vault.lock:
        context.key, context.validated, context.mode = key, False, 'USER_BYOK'
    return preferences_out(context, session.get(User, context.user_id))


@router.delete('/ai/key', dependencies=[Depends(secure_gateway)])
def disconnect_key(request: Request, owner_id: Owner, session: Session):
    context = user_session(request, owner_id)
    with request.app.state.session_vault.lock:
        for value in request.app.state.session_vault.sessions.values():
            if value.owner_id == owner_id:
                value.key, value.validated = None, False
    return preferences_out(context, session.get(User, context.user_id))


@router.post('/ai/key/validate', dependencies=[Depends(secure_gateway)])
def validate_key(request: Request, owner_id: Owner, session: Session):
    context = user_session(request, owner_id)
    with request.app.state.session_vault.lock:
        key = context.key
        request.app.state.session_vault.login_limit(f'validate:{owner_id}')
    if not key:
        raise HTTPException(409, 'Aucune clé personnelle connectée')
    validator = getattr(request.app.state, 'ai_key_validator', None)
    try:
        if validator:
            validator(key, request.app.state.settings.openai_model)
        else:
            from openai import OpenAI
            import logging
            logging.getLogger('openai').setLevel(logging.WARNING)
            with OpenAI(api_key=key, max_retries=0, timeout=10, base_url='https://api.openai.com/v1') as client:
                client.models.retrieve(request.app.state.settings.openai_model)
    except Exception:
        raise HTTPException(422, 'Clé refusée, modèle inaccessible ou fournisseur indisponible. Aucun texte généré.') from None
    with request.app.state.session_vault.lock:
        if context.key != key or context.expires_at <= time.time():
            raise HTTPException(409, 'La session ou la clé a changé pendant la validation')
        context.validated = True
    return preferences_out(context, session.get(User, context.user_id))


def settings_for_request(request, session):
    settings = request.app.state.settings
    context = getattr(request.state, 'user_session', None)
    if context is None:
        return settings
    user = session.get(User, context.user_id, populate_existing=True)
    if user is None or user.disabled_at is not None:
        raise HTTPException(401, 'Compte désactivé')
    if context.mode == 'OWNER_DEMO':
        if user.registration_kind=='public':
            raise HTTPException(403,'La clé de démonstration est interdite aux comptes publics')
        return settings
    with request.app.state.session_vault.lock:
        request.app.state.session_vault.purge()
        if context.expires_at <= time.time():
            raise HTTPException(401, 'Session expirée')
        key = context.key
        validated = context.validated
    return settings.model_copy(update={'ai_mode': 'USER_BYOK', 'ai_budget_scope': f'byok:{user.owner_id}:openai',
                                      'ai_budget_usd': user.ai_limit_usd, 'openai_api_key': SecretStr(key or ''),
                                      'ai_configuration_reason': None if key and validated else 'byok_disconnected' if not key else 'byok_unvalidated'})
