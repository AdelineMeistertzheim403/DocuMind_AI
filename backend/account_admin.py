"""Local administrator only; deliberately not exposed as HTTP routes."""
import argparse
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, delete,func,update

from .account_api import EmailInput, issue_token
from .account_models import AccountToken, DeletionRequest, PublicRegistrationQuota, WorkspaceMembership
from .auth import User
from .config import Settings
from .db import make_engine, make_sessions
from .models import Document
from .services.documents import delete_document
from .ai.models import AIReservation, AIUsage
from .ai.long_models import LongSummaryJob, SummaryStep
from .ai.long_summary import cancel
from .rag.models import IndexJob, RAGResult
from .security_audit import emit


def registration_control(session,settings,action,execute=False):
    """Local operator decision; never alter the lifetime admission counter."""
    if action not in ('status','close','reopen'):
        raise ValueError('Action de contrôle inconnue')
    query=select(PublicRegistrationQuota).where(PublicRegistrationQuota.id=='public')
    if action!='status' and execute:query=query.with_for_update()
    quota=session.scalar(query.execution_options(populate_existing=True))
    if quota is None:raise ValueError('Migration 0007 requise')
    before={'closed':quota.closed,'issued_count':quota.issued_count}
    if action=='reopen' and execute:
        if getattr(settings, 'lifecycle_durable_receipts_required', True):
            raise ValueError('Réouverture interdite avant garde de restauration approuvée')
        if (settings.registration_mode!='public' or settings.public_registration_limit!=5 or settings.ai_enabled
                or settings.owner_demo_enabled or settings.legacy_api_enabled):
            raise ValueError('La réouverture exige public/5, IA, démonstration et clés historiques désactivées')
        if not 0<=quota.issued_count<5:
            raise ValueError('Aucune admission disponible ; ne pas réinitialiser le compteur')
    if action!='status' and execute:
        # The same row lock serializes with admission's conditional UPDATE.
        session.execute(update(PublicRegistrationQuota).where(PublicRegistrationQuota.id=='public').values(closed=action=='close'))
        session.commit()
        session.expire_all()
        quota=session.get(PublicRegistrationQuota,'public',populate_existing=True)
        valid_counter=quota is not None and quota.issued_count==before['issued_count']
        if action=='reopen' and quota is not None:
            # A legitimate admission can commit immediately after reopening; never
            # mistake a monotonic increment for a failed operator decision.
            valid_counter=before['issued_count']<=quota.issued_count<=5
        if quota is None or quota.closed!=(action=='close') or not valid_counter:
            raise ValueError('Résultat du contrôle incohérent ; inspection opérateur requise')
    result={'closed':quota.closed,'issued_count':quota.issued_count,'limit':settings.public_registration_limit,
            'mode':settings.registration_mode,'simulation':action!='status' and not execute,
            'action':action,'before':before,'verified':True,
            'timestamp':datetime.now(timezone.utc).isoformat()}
    return result


def pending_account_control(session,identifier,action,execute=False):
    """Explicit review of an unverified account; never reactivate or delete its history."""
    if action not in ('block','release'):raise ValueError('Action inconnue')
    user=session.get(User,identifier,populate_existing=True,with_for_update=execute)
    if (user is None or user.registration_kind!='public' or user.email_verified_at is not None or
            session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==identifier)) is not None):
        raise ValueError('Un compte public non vérifié sans demande de suppression est requis')
    previous=user.disabled_at is not None
    invalidated=0
    if execute:
        from .models import now
        user.disabled_at=now() if action=='block' else None
        invalidated=session.execute(update(AccountToken).where(AccountToken.email==user.email,
            AccountToken.kind.in_(['verify','reset']),AccountToken.used_at.is_(None)).values(used_at=now())).rowcount
        session.commit()
    return {'action':action,'simulation':not execute,'blocked_before':previous,
            'blocked':action=='block' if execute else previous,'tokens_invalidated':invalidated,
            'timestamp':datetime.now(timezone.utc).isoformat()}


def purge_pending(session, settings, hours=168, execute=False):
    """Local explicit cleanup only. Never free lifetime admission slots or touch active users."""
    from datetime import timedelta
    from .models import now
    if type(hours) is not int or not 48<=hours<=720:raise ValueError('Choisir une ancienneté entre 48 et 720 heures')
    if execute and getattr(settings, 'lifecycle_durable_receipts_required', True):
        raise ValueError('Pending-account purge disabled until confirmation precedes all mutations')
    candidates=session.scalars(select(User.id).where(User.registration_kind=='public',User.email_verified_at.is_(None),User.disabled_at.is_(None),
        User.created_at<now()-timedelta(hours=hours))).all()
    count=0
    for identifier in candidates:
        user=session.get(User,identifier,populate_existing=True,with_for_update=True)
        if pending_exclusion(session,user,hours) is not None:continue
        count+=1
        if execute:
            user.disabled_at=now()
            if session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==user.id)) is None:
                session.add(DeletionRequest(user_id=user.id,owner_id=user.owner_id))
            session.commit()
            purge_account(session,settings,user.id)
    return count


def pending_exclusion(session, user, hours, at=None):
    """Shared dry-run/execution predicate, rechecked after the user row lock."""
    from datetime import timedelta
    from .models import now
    if type(hours) is not int or not 48 <= hours <= 720:
        raise ValueError('Invalid pending-account age')
    if user is None or user.registration_kind != 'public':return 'not_public'
    if user.email_verified_at is not None:return 'verified'
    if user.disabled_at is not None:return 'disabled'
    created = user.created_at
    if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
    if created >= (at or now())-timedelta(hours=hours):return 'too_recent'
    if session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==user.id)) is not None:return 'deletion_pending'
    if session.scalar(select(AccountToken.id).where(AccountToken.email==user.email,AccountToken.kind=='verify',
            AccountToken.used_at.is_(None),AccountToken.expires_at>(at or now())).limit(1)) is not None:return 'valid_verification_link'
    for model, reason in ((Document,'documents_present'),(AIReservation,'ai_reservation_present'),(AIUsage,'ai_usage_present')):
        if session.scalar(select(model.id).where(model.owner_id==user.owner_id).limit(1)) is not None:return reason
    return None


def plan_pending_cleanup(session, hours):
    """Aggregate-only inventory; no locks, token invalidation or account mutation."""
    from collections import Counter
    from .models import now
    if type(hours) is not int or not 48 <= hours <= 720:raise ValueError('Invalid pending-account age')
    at=now(); counts=Counter()
    for user in session.scalars(select(User).where(User.registration_kind=='public')).yield_per(100):
        counts[pending_exclusion(session,user,hours,at) or 'eligible']+=1
    return {'simulation':True,'older_than_hours':hours,'observed_at':at.isoformat(),
            'counts':dict(sorted(counts.items())),'execution_enabled':False}


def purge_account(session, settings, identifier):
    if getattr(settings, 'lifecycle_durable_receipts_required', True):
        raise ValueError('Account purge disabled until multi-step erasure is reconciled')
    from .lifecycle_registry import configured_registry
    from .lifecycle_durability import configured_coordinator
    registry = configured_registry(settings)
    coordinator = configured_coordinator(settings, registry)
    receipt = None
    if registry:
        user = session.get(User, identifier)
        request = session.scalar(select(DeletionRequest).where(DeletionRequest.user_id == identifier))
        if user is None or user.disabled_at is None or request is None:
            raise ValueError('A disabled account with a deletion request is required')
        receipt = registry.receive('erasure', user_id=user.id, owner_id=user.owner_id,
                                   received_at=request.created_at.replace(tzinfo=timezone.utc) if request.created_at.tzinfo is None else request.created_at)
        if coordinator:
            coordinator.confirm_account(receipt)
        quota = session.get(PublicRegistrationQuota, 'public')
        if quota is not None:
            registry.observe_admissions(quota.issued_count)
    try:
        _purge_account(session, settings, identifier)
    except Exception:
        if registry:
            registry.finish(receipt, failed=True)
        raise
    if registry:
        # No legal duration inferred; operator closes/sets expiry after residual
        # reconciliation. SQL deletion alone is not proof of physical erasure.
        registry.active_erased(receipt)


def _purge_account(session, settings, identifier):
    if getattr(settings, 'lifecycle_durable_receipts_required', True):
        raise ValueError('Account purge disabled until multi-step erasure is reconciled')
    user=session.get(User,identifier)
    request=session.scalar(select(DeletionRequest).where(DeletionRequest.user_id==identifier))
    if user is None or user.disabled_at is None or request is None:
        raise ValueError('A disabled account with a deletion request is required')
    if session.scalar(select(SummaryStep.id).join(LongSummaryJob).where(LongSummaryJob.owner_id==user.owner_id,SummaryStep.status=='processing').limit(1)):
        raise ValueError('A worker is processing this account; wait for it to stop')
    if session.scalar(select(IndexJob.id).where(IndexJob.owner_id==user.owner_id,IndexJob.status.in_(['running','queued'])).limit(1)):
        raise ValueError('An index worker is active; wait or restart the API to pause it')
    for job in session.scalars(select(LongSummaryJob).where(LongSummaryJob.owner_id==user.owner_id,LongSummaryJob.status.not_in(['completed','cancelled']))).all():
        cancel(session,settings,job)
    if session.scalar(select(AIReservation.id).where(AIReservation.owner_id==user.owner_id,AIReservation.status=='reserved').limit(1)):
        raise ValueError('An outstanding reservation requires reconciliation')
    for document in session.scalars(select(Document).where(Document.owner_id==user.owner_id)).all():
        delete_document(session,settings,document)
    from .lifecycle_registry import configured_registry
    registry=configured_registry(settings)
    if registry and registry.pending_document_files(user.owner_id):
        raise ValueError('Document residual reconciliation required before final account purge')
    session.execute(delete(RAGResult).where(RAGResult.owner_id==user.owner_id))
    if user.email:
        session.execute(delete(AccountToken).where(AccountToken.email==user.email))
    session.delete(user)
    session.commit()
    emit('account.deletion.completed', reason_code='completed')
    # Anonymous owner UUID and accounting remain to prevent budget/quota reset.


def main():
    parser=argparse.ArgumentParser(description='Administration locale des comptes')
    commands=parser.add_subparsers(dest='command',required=True)
    invite=commands.add_parser('invite');invite.add_argument('email')
    attach=commands.add_parser('attach-email');attach.add_argument('username');attach.add_argument('email')
    purge=commands.add_parser('purge');purge.add_argument('user_id',type=UUID)
    commands.add_parser('owners')
    pending=commands.add_parser('purge-pending');pending.add_argument('--older-than-hours',type=int,default=168);pending.add_argument('--execute',action='store_true')
    control=commands.add_parser('public-registration');control.add_argument('action',choices=['status','close','reopen']);control.add_argument('--execute',action='store_true')
    pending_control=commands.add_parser('pending-account');pending_control.add_argument('action',choices=['block','release']);pending_control.add_argument('user_id',type=UUID);pending_control.add_argument('--execute',action='store_true')
    args=parser.parse_args();settings=Settings();engine=make_engine(settings.database_url)
    try:
        with make_sessions(engine)() as session:
            if args.command=='public-registration':
                print(json.dumps(registration_control(session,settings,args.action,args.execute)))
            elif args.command=='pending-account':
                print(json.dumps(pending_account_control(session,args.user_id,args.action,args.execute)))
            elif args.command=='purge-pending':
                count=purge_pending(session,settings,args.older_than_hours,args.execute)
                print('Comptes en attente :',count,'; mode :','exécution' if args.execute else 'simulation')
            elif args.command=='owners':
                from .account_models import Workspace
                for workspace in session.scalars(select(Workspace)).all():
                    user=session.scalar(select(User.username).where(User.owner_id==workspace.owner_id))
                    count=session.scalar(select(func.count()).select_from(Document).where(Document.owner_id==workspace.owner_id))
                    print(workspace.owner_id,'claimed' if user else 'unclaimed','documents',count)
            elif args.command=='invite':
                email=EmailInput(email=args.email).email
                token=issue_token(session,'invite',email,86400)
                session.commit()
                print('Invitation (secret temporaire, à transmettre au destinataire uniquement) :',token)
            elif args.command=='attach-email':
                user=session.scalar(select(User).where(User.username==args.username.strip().lower()))
                if user is None: raise SystemExit('Compte introuvable')
                user.email=EmailInput(email=args.email).email
                session.commit();print('Email associé. Le propriétaire et ses données sont inchangés.')
            else:
                purge_account(session,settings,args.user_id)
                print('Compte et contenu supprimés. Comptabilité pseudonymisée conservée.')
    finally:
        engine.dispose()


if __name__=='__main__':main()
