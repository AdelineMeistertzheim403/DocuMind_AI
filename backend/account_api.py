"""Account lifecycle. No provider calls, ownership claims, cookies or secrets in responses."""
import re
import secrets
import smtplib
import ssl
import time
import queue
from datetime import timedelta, timezone
from email.message import EmailMessage
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from .api import Owner, Session
from .auth import User, SessionVault, hash_password, verify_password
from .account_models import AccountToken, DeletionRequest, WorkspaceMembership
from .ai.models import AIBudget, AIInteraction, AIReservation, AISummary, AISource
from .ai.schemas import StrictModel
from .ai.settings_api import user_session
from .gateway import secure_gateway, client_ip
from .models import now
from .resource_limits import lock_workspace

router = APIRouter(prefix='/api/v1', tags=['comptes'], dependencies=[Depends(secure_gateway)])


class EmailInput(StrictModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator('email')
    @classmethod
    def normalize(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}', value):
            raise ValueError('Adresse email invalide')
        return value


class Register(EmailInput):
    password: SecretStr = Field(min_length=12, max_length=256)
    invitation: SecretStr = Field(min_length=32, max_length=128)


class Reset(StrictModel):
    token: SecretStr = Field(min_length=32, max_length=128)
    password: SecretStr = Field(min_length=12, max_length=256)


class PasswordInput(StrictModel):
    password: SecretStr = Field(min_length=1, max_length=256)


class ChangePassword(PasswordInput):
    new_password: SecretStr = Field(min_length=12, max_length=256)


def issue_token(session, kind, email, ttl):
    token = secrets.token_urlsafe(32)
    session.add(AccountToken(digest=SessionVault.digest(token), kind=kind, email=email,
                             expires_at=now()+timedelta(seconds=ttl)))
    return token


def consume_token(session, token, kind, email=None):
    # Atomic conditional UPDATE handles concurrent consumption in PostgreSQL and SQLite.
    condition = [AccountToken.digest==SessionVault.digest(token), AccountToken.kind==kind,
                 AccountToken.used_at.is_(None), AccountToken.expires_at>now()]
    if email is not None:
        condition.append(AccountToken.email==email)
    result = session.execute(update(AccountToken).where(*condition).values(used_at=now()).returning(AccountToken.email)).scalar_one_or_none()
    if result is None:
        raise HTTPException(400, 'Lien ou invitation invalide ou expiré')
    return result


def current_user(request, session, owner):
    context = user_session(request, owner)
    user = session.get(User, context.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(401, 'Compte indisponible')
    return user


def profile(user):
    return {'id':str(user.id), 'email':user.email, 'username':user.username,
            'owner_id':str(user.owner_id), 'workspace':'Espace personnel'}


@router.get('/auth/options')
def options(request: Request):
    return {'registration_mode':request.app.state.settings.registration_mode}


@router.post('/auth/register', status_code=201)
def register(body: Register, request: Request, session: Session):
    request.app.state.rate_limiter.check(f'register:{client_ip(request)}', 5)
    if request.app.state.settings.registration_mode != 'invite':
        raise HTTPException(403, 'Inscription désactivée')
    consume_token(session, body.invitation.get_secret_value(), 'invite', body.email)
    if session.scalar(select(User.id).where(User.email==body.email)):
        raise HTTPException(400, 'Inscription impossible avec cette invitation')
    owner = uuid4()
    lock_workspace(session, owner)
    user = User(owner_id=owner, email=body.email, username=f'user-{uuid4().hex}',
                password_hash=hash_password(body.password.get_secret_value()))
    session.add(user)
    session.flush()
    session.add(WorkspaceMembership(user_id=user.id, owner_id=owner))
    session.add(AIBudget(id=f'byok:{owner}:openai'))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(400, 'Inscription impossible avec cette invitation') from None
    return {'created':True}


def send_reset(settings, email, token):
    if not settings.smtp_host:
        return
    message = EmailMessage()
    message['From'], message['To'], message['Subject'] = settings.smtp_from, email, 'Réinitialisation DocuMind'
    # Fragment is never sent to the web server or its access log; UI immediately clears it.
    message.set_content(f"Réinitialisez votre mot de passe : {settings.account_base_url}/reset-password#token={token}\nCe lien est temporaire et à usage unique.")
    context = ssl.create_default_context()
    if settings.smtp_starttls:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    else:
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=context)
    with client:
        if settings.smtp_starttls:
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        client.send_message(message)


@router.post('/auth/forgot-password', status_code=202)
def forgot(body: EmailInput, request: Request, session: Session):
    request.app.state.rate_limiter.check(f'reset-ip:{client_ip(request)}', 5, 900)
    request.app.state.rate_limiter.check(f'reset-email:{body.email}', 3, 900)
    user = session.scalar(select(User).where(User.email==body.email, User.disabled_at.is_(None)))
    # Do the same token derivation and minimum work for unknown addresses.
    token = secrets.token_urlsafe(32)
    if user and (request.app.state.settings.smtp_host or getattr(request.app.state,'mail_sender',None)):
        token = issue_token(session,'reset',body.email,request.app.state.settings.reset_ttl_seconds)
        session.commit()
        # Queue delivery so SMTP timing/failures cannot disclose account existence.
        try:
            request.app.state.mail_queue.put_nowait((body.email,token))
        except queue.Full:
            pass
    return {'message':'Si ce compte est éligible, un message de récupération sera envoyé.'}


@router.post('/auth/reset-password')
def reset(body: Reset, request: Request, session: Session):
    request.app.state.rate_limiter.check(f'reset-consume:{client_ip(request)}',10,900)
    email = consume_token(session,body.token.get_secret_value(),'reset')
    user = session.scalar(select(User).where(User.email==email, User.disabled_at.is_(None)).with_for_update())
    if user is None:
        raise HTTPException(400,'Lien invalide ou expiré')
    user.password_hash = hash_password(body.password.get_secret_value())
    session.execute(update(AccountToken).where(AccountToken.email==email,AccountToken.kind=='reset').values(used_at=now()))
    session.commit()
    request.app.state.session_vault.revoke_user(user.id)
    return {'reset':True}


@router.get('/account')
def get_account(request: Request, owner: Owner, session: Session):
    return profile(current_user(request,session,owner))


@router.get('/account/sessions')
def sessions(request: Request, owner: Owner, session: Session):
    user = current_user(request,session,owner)
    vault = request.app.state.session_vault
    with vault.lock:
        vault.purge()
        current = vault.digest(request.headers['authorization'][7:])
        return {'items':[{'id':digest,'current':digest==current,'expires_at':value.expires_at}
                         for digest,value in vault.sessions.items() if value.user_id==user.id]}


@router.delete('/account/sessions/{identifier}')
def revoke_session(identifier: str, request: Request, owner: Owner, session: Session):
    user = current_user(request,session,owner)
    vault = request.app.state.session_vault
    with vault.lock:
        value = vault.sessions.get(identifier)
        if value is None or value.user_id != user.id:
            raise HTTPException(404,'Session introuvable')
        value.key=None;value.expires_at=0
        del vault.sessions[identifier]
    return {'revoked':True}


@router.post('/account/password')
def password(body: ChangePassword, request: Request, owner: Owner, session: Session):
    user = current_user(request,session,owner)
    request.app.state.rate_limiter.check(f'password:{user.id}',5)
    if not verify_password(body.password.get_secret_value(),user.password_hash):
        raise HTTPException(401,'Identifiants invalides')
    user.password_hash=hash_password(body.new_password.get_secret_value())
    session.execute(update(AccountToken).where(AccountToken.email==user.email,AccountToken.kind=='reset').values(used_at=now()))
    session.commit()
    request.app.state.session_vault.revoke_user(user.id)
    return {'changed':True,'reconnect':True}


@router.post('/account/deletion-request',status_code=202)
def deletion(body: PasswordInput, request: Request, owner: Owner, session: Session):
    user = current_user(request,session,owner)
    request.app.state.rate_limiter.check(f'delete:{user.id}',5)
    if not verify_password(body.password.get_secret_value(),user.password_hash):
        raise HTTPException(401,'Identifiants invalides')
    lock_workspace(session,owner)
    session.add(DeletionRequest(user_id=user.id,owner_id=owner))
    user.disabled_at=now()
    session.commit()
    request.app.state.session_vault.revoke_user(user.id)
    return {'requested':True,'message':'Compte désactivé. La suppression doit être traitée par l’administrateur local.'}


@router.delete('/documents/{document_id}/ai-results',status_code=204)
def clear_ai(document_id: UUID, request: Request, owner: Owner, session: Session):
    from .services.documents import owned_document
    from .ai.long_models import LongSummaryJob
    from .rag.models import RAGDocument, RAGResult, OperationDocument
    current_user(request,session,owner)
    lock_workspace(session,owner)
    owned_document(session,document_id,owner,lock=True)
    linked_reservations=select(OperationDocument.reservation_id).where(OperationDocument.document_id==document_id)
    if session.scalar(select(AIReservation.id).where(AIReservation.status=='reserved',
        (AIReservation.document_id==document_id)|(AIReservation.id.in_(linked_reservations))).limit(1)):
        raise HTTPException(409,'Un traitement est en cours ou réservé')
    for model in [AISource,AISummary,AIInteraction,LongSummaryJob]:
        session.execute(delete(model).where(model.document_id==document_id))
    linked=select(RAGDocument.result_id).where(RAGDocument.document_id==document_id)
    session.execute(delete(RAGResult).where(RAGResult.owner_id==owner,RAGResult.id.in_(linked)))
    session.commit()


@router.delete('/documents/{document_id}/embeddings',status_code=204)
def clear_embeddings(document_id: UUID, request: Request, owner: Owner, session: Session):
    from .services.documents import owned_document
    from .rag.models import ChunkEmbedding,IndexJob,RAGResult,RAGDocument
    current_user(request,session,owner)
    lock_workspace(session,owner)
    owned_document(session,document_id,owner,lock=True)
    if session.scalar(select(IndexJob.id).where(IndexJob.document_id==document_id,IndexJob.status.in_(['queued','running'])).limit(1)):
        raise HTTPException(409,'Une indexation est en cours')
    session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.document_id==document_id,ChunkEmbedding.owner_id==owner))
    session.execute(delete(IndexJob).where(IndexJob.document_id==document_id,IndexJob.owner_id==owner))
    linked=select(RAGDocument.result_id).where(RAGDocument.document_id==document_id)
    session.execute(delete(RAGResult).where(RAGResult.owner_id==owner,RAGResult.kind=='index_request',RAGResult.id.in_(linked)))
    session.commit()
