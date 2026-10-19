"""Local administrator only; deliberately not exposed as HTTP routes."""
import argparse
from uuid import UUID

from sqlalchemy import select, delete,func

from .account_api import EmailInput, issue_token
from .account_models import AccountToken, DeletionRequest, WorkspaceMembership
from .auth import User
from .config import Settings
from .db import make_engine, make_sessions
from .models import Document
from .services.documents import delete_document
from .ai.models import AIReservation
from .ai.long_models import LongSummaryJob, SummaryStep
from .ai.long_summary import cancel
from .rag.models import IndexJob, RAGResult


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
    # Anonymous owner UUID and accounting remain to prevent budget/quota reset.


def main():
    parser=argparse.ArgumentParser(description='Administration locale des comptes')
    commands=parser.add_subparsers(dest='command',required=True)
    invite=commands.add_parser('invite');invite.add_argument('email')
    attach=commands.add_parser('attach-email');attach.add_argument('username');attach.add_argument('email')
    purge=commands.add_parser('purge');purge.add_argument('user_id',type=UUID)
    commands.add_parser('owners')
    args=parser.parse_args();settings=Settings();engine=make_engine(settings.database_url)
    try:
        with make_sessions(engine)() as session:
            if args.command=='owners':
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
