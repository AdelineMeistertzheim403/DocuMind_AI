"""Local administrator only; deliberately not exposed as HTTP routes."""
import argparse
import json
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


def purge_pending(session, settings, hours=48, execute=False):
    """Local explicit cleanup only. Never free lifetime admission slots or touch active users."""
    from datetime import timedelta
    from .models import now
    if not 48<=hours<=720:raise ValueError('Choisir une ancienneté entre 48 et 720 heures')
    candidates=session.scalars(select(User.id).where(User.registration_kind=='public',User.email_verified_at.is_(None),
        User.created_at<now()-timedelta(hours=hours))).all()
    count=0
    for identifier in candidates:
        user=session.get(User,identifier,populate_existing=True,with_for_update=True)
        if user is None or user.registration_kind!='public' or user.email_verified_at is not None:continue
        if session.scalar(select(AccountToken.id).where(AccountToken.email==user.email,AccountToken.kind=='verify',
                AccountToken.used_at.is_(None),AccountToken.expires_at>now()).limit(1)) is not None:continue
        if session.scalar(select(Document.id).where(Document.owner_id==user.owner_id).limit(1)) is not None:continue
        if session.scalar(select(AIReservation.id).where(AIReservation.owner_id==user.owner_id).limit(1)) is not None:continue
        if session.scalar(select(AIUsage.id).where(AIUsage.owner_id==user.owner_id).limit(1)) is not None:continue
        count+=1
        if execute:
            user.disabled_at=now()
            if session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==user.id)) is None:
                session.add(DeletionRequest(user_id=user.id,owner_id=user.owner_id))
            session.commit()
            purge_account(session,settings,user.id)
    return count


def purge_account(session, settings, identifier):
    user=session.get(User,identifier)
    if user is None or user.disabled_at is None or session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==identifier)) is None:
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
    pending=commands.add_parser('purge-pending');pending.add_argument('--older-than-hours',type=int,default=48);pending.add_argument('--execute',action='store_true')
    control=commands.add_parser('public-registration');control.add_argument('action',choices=['status','close','reopen']);control.add_argument('--execute',action='store_true')
    args=parser.parse_args();settings=Settings();engine=make_engine(settings.database_url)
    try:
        with make_sessions(engine)() as session:
            if args.command=='public-registration':
                if args.action!='status' and args.execute:
                    session.execute(update(PublicRegistrationQuota).where(PublicRegistrationQuota.id=='public').values(closed=args.action=='close'))
                    session.commit()
                quota=session.get(PublicRegistrationQuota,'public')
                if quota is None:raise ValueError('Migration 0007 requise')
                print(json.dumps({'closed':quota.closed,'issued_count':quota.issued_count,'limit':settings.public_registration_limit,
                                  'mode':settings.registration_mode,'simulation':args.action!='status' and not args.execute}))
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
