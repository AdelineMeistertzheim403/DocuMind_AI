"""Lite admission contract. No operational confirmation authority is shipped here.

The injectable backend belongs to isolated tests until independently provisioned
confirmation and recovery are implemented. Neither HTTP nor environment settings
can install/approve one. Pending proposals contain an Argon2 verifier, never a
clear password; administrative exports must omit this verifier and invitation.
"""
from contextlib import AbstractContextManager
from datetime import datetime
from dataclasses import dataclass, field
import hashlib
import sqlite3
from typing import Literal, Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .auth import User, SessionVault, hash_password, verify_password
from .account_models import AccountToken, PublicRegistrationQuota, Workspace, WorkspaceMembership
from .ai.models import AIBudget
from .models import now

State = Literal['proposal_created', 'reservation_pending', 'reservation_confirmed',
                'sql_committed', 'result_pending', 'admitted', 'uncertain', 'cancelled', 'refused']


@dataclass
class AdmissionOperation:
    id: UUID
    cohort_id: UUID
    invitation_digest: str = field(repr=False)
    email_digest: str = field(repr=False)
    terms_version: str
    terms_sha256: str
    accepted_at: str
    password_hash: str = field(repr=False)
    user_id: UUID = field(default_factory=uuid4)
    owner_id: UUID = field(default_factory=uuid4)
    state: State = 'proposal_created'
    issued_count: int | None = None
    reserved_count: int | None = None
    adult_declared: bool = True
    terms_accepted: bool = True

    def export(self):
        # Explicit allowlist: no credentials, contact, invitation or verifier.
        return {'operation_id': str(self.id), 'cohort_id': str(self.cohort_id),
                'user_id': str(self.user_id), 'owner_id': str(self.owner_id),
                'terms_version': self.terms_version, 'terms_sha256': self.terms_sha256,
                'accepted_at': self.accepted_at, 'adult_declared': self.adult_declared,
                'terms_accepted': self.terms_accepted, 'state': self.state,
                'issued_count': self.issued_count}


class AdmissionConfirmation(Protocol):
    """All methods fail closed on missing/stale/contradictory evidence.

    exclusive serializes *short requests*, including API/CLI and other processes;
    never an operator's waiting time. prepare must durably deduplicate invitation
    and requester; it cannot approve. Reservation/result verification must bind
    all proposal fields and cohort. Cancellation requires independently attested
    absence of a SQL commit; no automatic timeout/release or quota decrement.
    """
    cohort_id: UUID

    def exclusive(self) -> AbstractContextManager: ...
    def find(self, invitation_digest: str, email_digest: str) -> AdmissionOperation | None: ...
    def for_user(self, user_id: UUID) -> AdmissionOperation | None: ...
    def prepare(self, operation: AdmissionOperation) -> AdmissionOperation: ...
    def reservation_verified(self, operation: AdmissionOperation, issued_count: int) -> bool: ...
    def committed(self, operation: AdmissionOperation, issued_count: int) -> None: ...
    def result_verified(self, operation: AdmissionOperation) -> bool: ...
    # Exact settled history, plus a bound in-flight commit when applicable;
    # not merely "SQL >= watermark". Missing admission identities must refuse.
    def counter_verified(self, issued_count: int) -> bool: ...
    def uncertain(self, operation: AdmissionOperation) -> None: ...
    def reconcile(self, operation: AdmissionOperation, sql_evidence: dict) -> None: ...


def coordinator(app):
    value = getattr(app.state, 'lite_confirmation', None)
    if value is None or value.cohort_id != app.state.settings.lite_cohort_id:
        raise HTTPException(503, 'Confirmation administrative indépendante indisponible')
    return value


def user_admitted(app, user):
    if app.state.settings.application_profile != 'beta_lite':
        return True
    try:
        confirmation = coordinator(app)
        if hasattr(confirmation, 'store'):
            from .lite_deletions import account_restricted
            if account_restricted(confirmation, user.id):
                app.state.session_vault.revoke_user(user.id)
                return False
        operation = confirmation.for_user(user.id)
        with app.state.sessions() as session:
            quota = session.get(PublicRegistrationQuota, 'public')
            database_count = quota.issued_count if quota is not None else -1
        valid_counter = confirmation.counter_verified(database_count)
        return bool(user.registration_kind == 'invite' and operation
                    and operation.cohort_id == app.state.settings.lite_cohort_id
                    and operation.user_id == user.id and operation.owner_id == user.owner_id
                    and valid_counter and operation.state == 'admitted' and confirmation.result_verified(operation))
    except (OSError, ValueError, RuntimeError, sqlite3.Error, HTTPException):
        return False


def response(operation, state):
    return {'profile': 'beta_lite', 'operation_id': str(operation.id), 'state': state,
            'created': state == 'admitted', 'confirmation_operational': False}


def admit(request, session, body):
    """Same invitation endpoint; SQL atomicity and independent proof are distinct."""
    from .account_api import consume_token
    from .public_registration import increment_quota
    settings = request.app.state.settings
    if (settings.registration_mode != 'invite' or settings.public_registration_limit != 5
            or not settings.lifecycle_durable_receipts_required or settings.lifecycle_synthetic_mutations_enabled
            or settings.ai_enabled or settings.owner_demo_enabled or settings.legacy_api_enabled or settings.api_keys):
        raise HTTPException(503, 'Profil Beta Lite incohérent : admissions fermées')
    if not body.adult_declared or not body.terms_accepted or not body.terms_version:
        raise HTTPException(400, 'Majorité et acceptation des conditions requises')
    if body.invitation is None:
        raise HTTPException(422, 'Invitation requise')
    confirmation = coordinator(request.app)
    invitation = SessionVault.digest(body.invitation.get_secret_value())
    email = hashlib.sha256(body.email.encode()).hexdigest()
    try:
        with confirmation.exclusive():
            operation = confirmation.find(invitation, email)
            prepared_here = operation is None
            if body.operation_id and (operation is None or operation.id != body.operation_id):
                raise HTTPException(409, 'Opération incohérente')
            if operation:
                if (operation.cohort_id != settings.lite_cohort_id
                        or operation.invitation_digest != invitation or operation.email_digest != email
                        or not operation.adult_declared or not operation.terms_accepted
                        or operation.terms_version != body.terms_version
                        or not verify_password(body.password.get_secret_value(), operation.password_hash)):
                    raise HTTPException(409, 'La proposition ne correspond pas à cette opération')
                if operation.state in ('uncertain', 'cancelled', 'refused'):
                    raise HTTPException(409, 'Vérification administrative requise')
                user = session.get(User, operation.user_id)
                if user:
                    # Recovery after COMMIT/result/response loss. Never consume again.
                    quota = session.get(PublicRegistrationQuota, 'public')
                    valid = (user.email == body.email and user.owner_id == operation.owner_id
                             and user.registration_kind == 'invite' and user.disabled_at is None
                             and user.terms_version == operation.terms_version
                             and verify_password(body.password.get_secret_value(), user.password_hash)
                             and quota is not None and 0 < quota.issued_count <= 5)
                    count = operation.reserved_count
                    database_count = quota.issued_count if quota else -1
                    session.rollback()  # no SQL transaction during proof I/O
                    counter_ok = confirmation.counter_verified(database_count)
                    if not valid or not counter_ok or count is None or not 1 <= count <= database_count:
                        confirmation.uncertain(operation)
                        raise HTTPException(409, 'Rapprochement administratif requis')
                    confirmation.committed(operation, count)
                    if confirmation.result_verified(operation):
                        return response(operation, 'admitted'), 201
                    return response(operation, 'result_pending'), 202
                if operation.issued_count is not None or operation.state in ('sql_committed', 'result_pending', 'admitted'):
                    session.rollback()
                    confirmation.uncertain(operation)
                    raise HTTPException(409, 'Compte absent : restauration à vérifier')
            if body.terms_version != settings.public_terms_version or (operation and operation.terms_sha256 != settings.lite_terms_sha256):
                raise HTTPException(400, 'Acceptez la version actuelle des conditions')
            token = session.scalar(select(AccountToken).where(AccountToken.digest == invitation,
                AccountToken.kind == 'invite', AccountToken.email == body.email,
                AccountToken.used_at.is_(None), AccountToken.expires_at > now()))
            if token is None:
                raise HTTPException(400, 'Invitation invalide, expirée ou déjà utilisée')
            quota = session.get(PublicRegistrationQuota, 'public')
            if quota is None or quota.closed or not 0 <= quota.issued_count < 5:
                raise HTTPException(403, 'Admissions fermées ou plafond atteint')
            if session.scalar(select(User.id).where(User.email == body.email)) is not None:
                raise HTTPException(400, 'Inscription impossible avec cette invitation')
            count = quota.issued_count
            session.rollback()
            if not confirmation.counter_verified(count):
                raise HTTPException(409, 'Compteur restauré incohérent : rapprochement requis')
            if operation is None:
                operation = confirmation.prepare(AdmissionOperation(uuid4(), settings.lite_cohort_id,
                    invitation, email, body.terms_version, settings.lite_terms_sha256, now().isoformat(),
                    hash_password(body.password.get_secret_value())))
            if not confirmation.reservation_verified(operation, count):
                return response(operation, 'proposal_created' if prepared_here else 'reservation_pending'), 202
            if operation.reserved_count != count + 1:
                raise HTTPException(409, 'Réservation incohérente')
            # Everything below is one short SQL transaction. A human never holds it.
            granted = increment_quota(session, 5)
            if granted is None:
                session.rollback()
                raise HTTPException(403, 'Admissions fermées ou plafond atteint')
            if granted != operation.reserved_count:
                session.rollback()
                raise HTTPException(409, 'Compteur modifié : rapprochement requis')
            consume_token(session, body.invitation.get_secret_value(), 'invite', body.email)
            session.add(Workspace(owner_id=operation.owner_id))
            session.add(User(id=operation.user_id, owner_id=operation.owner_id, email=body.email,
                username='user-'+operation.user_id.hex, password_hash=operation.password_hash,
                registration_kind='invite', terms_version=operation.terms_version,
                terms_accepted_at=datetime.fromisoformat(operation.accepted_at)))
            session.flush()
            session.add(WorkspaceMembership(user_id=operation.user_id, owner_id=operation.owner_id))
            session.add(AIBudget(id=f'byok:{operation.owner_id}:openai'))
            try:
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                confirmation.uncertain(operation)
                raise HTTPException(503, 'Admission incertaine : rapprochement administratif requis') from None
            confirmation.committed(operation, granted)
            if confirmation.result_verified(operation):
                return response(operation, 'admitted'), 201
            return response(operation, 'result_pending'), 202
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        session.rollback()
        raise HTTPException(503, 'Preuve indisponible : vérification administrative requise') from None


class LiteBoundary:
    """Deny unused capabilities server-side; HTTP auth/session routes stay intact."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['app'].state.settings.application_profile == 'beta_lite':
            path = scope.get('path', '').rstrip('/')
            blocked = ('/ai', '/rag', '/byok', '/library', '/compare', '/comparisons',
                       '/embeddings', '/search', '/summary-jobs')
            if (any(part in path for part in blocked)
                    or path.endswith(('/index', '/summarize', '/summaries', '/ask', '/summary-plan'))
                    or path.endswith('/resend-verification') or path.endswith('/verify-email')):
                from starlette.responses import JSONResponse
                await JSONResponse({'detail': 'Fonction indisponible dans Beta Lite'}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
