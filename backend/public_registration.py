"""Explicit public beta admission. No account can authenticate before email + password proof."""
import hashlib
import queue
import re
import secrets
import threading
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .account_models import AccountToken, DeletionRequest, PublicRegistrationQuota, Workspace, WorkspaceMembership
from .ai.models import AIBudget
from .auth import DUMMY_HASH, SessionVault, User, hash_password, verify_password
from .gateway import client_ip
from .models import now
from .security_audit import mark

GENERIC = {'message': "Si cette demande peut aboutir, un lien de vérification sera envoyé. Vérifiez aussi les courriers indésirables."}


class RegistrationChallenges:
    def __init__(self, clock=None, capacity=1024):
        self.clock=clock or time.monotonic
        self.capacity=capacity
        self.lock=threading.Lock()
        self.items={}
        self.slots=threading.BoundedSemaphore(1)

    def issue(self, ip, difficulty):
        with self.lock:
            current=self.clock()
            self.items={key:value for key,value in self.items.items() if value[0]>current}
            if len(self.items)>=self.capacity:
                raise HTTPException(503,'Vérification temporairement indisponible')
            token=secrets.token_urlsafe(32)
            self.items[token]=(current+300,ip,difficulty)
        return {'challenge':token,'difficulty':difficulty,'expires_in':300}

    def consume(self, token, proof, ip):
        with self.lock:
            entry=self.items.pop(token,None)
        if not entry or entry[0]<=self.clock() or entry[1]!=ip or not re.fullmatch(r'[0-9]{1,12}',proof):
            return False
        digest=hashlib.sha256(f'{token}:{proof}'.encode()).digest()
        return int.from_bytes(digest[:3],'big') >> (24-entry[2]) == 0


def challenge(request):
    limiter=request.app.state.rate_limiter
    limiter.check('signup-challenge-global',60)
    limiter.check('signup-challenge:'+client_ip(request),5)
    return request.app.state.registration_challenges.issue(client_ip(request),request.app.state.settings.public_challenge_difficulty)


def admit(request, session, body, *, resend=False):
    from .account_api import issue_token
    settings=request.app.state.settings
    if not resend and settings.registration_mode!='public':
        raise HTTPException(403,'Inscription désactivée')
    if not resend and (not body.terms_accepted or body.terms_version!=settings.public_terms_version):
        raise HTTPException(400,'Acceptez les conditions en vigueur après les avoir consultées')
    mark('account.registration.requested','completed')
    limiter=request.app.state.rate_limiter
    limiter.check('signup-global',10)
    limiter.check('signup-ip:'+client_ip(request),settings.public_registration_per_hour,3600)
    limiter.check('signup-email:'+body.email,settings.public_registration_per_hour,3600)
    state=request.app.state.registration_challenges
    valid_challenge=state.consume(body.challenge,body.proof,client_ip(request))
    if body.website or not valid_challenge:
        mark('account.registration.requested','denied')
        return GENERIC
    if not state.slots.acquire(blocking=False):
        mark('account.registration.denied','capacity')
        raise HTTPException(503,'Capacité de création de comptes atteinte')
    try:
        # Equal password work for a new or already registered address; never overwrite an account.
        password_hash=hash_password(body.password.get_secret_value())
        query=select(User).where(User.email==body.email)
        user=session.scalar(query.with_for_update() if resend else query)
        if resend:
            valid=verify_password(body.password.get_secret_value(),user.password_hash if user else DUMMY_HASH)
            if (not user or not valid or user.registration_kind!='public' or user.email_verified_at is not None or user.disabled_at is not None or
                    session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==user.id)) is not None):
                return GENERIC
        else:
            if user is not None:
                return GENERIC
            granted=session.execute(update(PublicRegistrationQuota).where(
                PublicRegistrationQuota.id=='public',PublicRegistrationQuota.issued_count<settings.public_registration_limit,
                PublicRegistrationQuota.issued_count>=0,
                PublicRegistrationQuota.closed.is_(False)
            ).values(issued_count=PublicRegistrationQuota.issued_count+1).returning(PublicRegistrationQuota.issued_count)).scalar_one_or_none()
            if granted is None:
                mark('account.registration.requested','quota')
                return GENERIC
            owner=uuid4()
            # Email verification already blocks login and authenticated requests in schema-0007 apps.
            # disabled_at is reserved for operator/deletion blocks, never cleared by verification.
            user=User(owner_id=owner,email=body.email,username='user-'+uuid4().hex,password_hash=password_hash,
                      registration_kind='public',terms_version=body.terms_version,
                      terms_accepted_at=now(),ai_limit_usd=settings.public_ai_max_budget_usd)
            session.add(Workspace(owner_id=owner));session.flush()
            session.add(user);session.flush()
            session.add(WorkspaceMembership(user_id=user.id,owner_id=owner))
            session.add(AIBudget(id=f'byok:{owner}:openai'))
        if not settings.smtp_host and getattr(request.app.state,'mail_sender',None) is None:
            mark('account.registration.denied','mail_failed')
            raise HTTPException(503,'Livraison du courrier indisponible')
        session.execute(update(AccountToken).where(AccountToken.email==body.email,AccountToken.kind=='verify',
                                                  AccountToken.used_at.is_(None)).values(used_at=now()))
        token=issue_token(session,'verify',body.email,settings.public_verification_ttl_seconds)
        session.commit()
        try:request.app.state.mail_queue.put_nowait((body.email,token,'verify'))
        except queue.Full:
            from .security_audit import emit
            emit('system.mail.failed',reason_code='mail_failed')
        mark('account.registration.requested','completed')
        return GENERIC
    except IntegrityError:
        session.rollback()
        return GENERIC
    finally:
        state.slots.release()


def verify(request, session, body):
    from .account_api import consume_token
    request.app.state.rate_limiter.check('verify-ip:'+client_ip(request),10)
    # User -> token lock order is shared with resend; avoid a token/user lock inversion.
    email=session.scalar(select(AccountToken.email).where(AccountToken.digest==SessionVault.digest(body.token.get_secret_value()),
                                                         AccountToken.kind=='verify'))
    if email is None:raise HTTPException(400,'Lien ou vérification invalide ou expiré')
    user=session.scalar(select(User).where(User.email==email).with_for_update())
    consume_token(session,body.token.get_secret_value(),'verify')
    valid=verify_password(body.password.get_secret_value(),user.password_hash if user else DUMMY_HASH)
    if (not user or not valid or user.registration_kind!='public' or user.email_verified_at is not None or user.disabled_at is not None or
            session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==user.id)) is not None):
        raise HTTPException(400,'Lien ou vérification invalide ou expiré')
    user.email_verified_at=now()
    session.commit()
    mark('account.email.verified','completed')
    return {'verified':True}
