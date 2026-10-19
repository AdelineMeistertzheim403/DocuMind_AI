"""Create a local account with an interactive password prompt; no plaintext password stored."""
import argparse
import getpass
from uuid import UUID, uuid4

from sqlalchemy import select

from .auth import User, hash_password
from .config import Settings
from .db import make_engine, make_sessions
from .ai.models import AIBudget
from .account_models import WorkspaceMembership
from .resource_limits import lock_workspace
from .account_api import EmailInput


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    parser.add_argument('--owner-id', type=UUID, help='UUID existant pour retrouver les documents de ce propriétaire')
    parser.add_argument('--email', help='Adresse vérifiée par l’administrateur local')
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not username or len(username) > 80:
        raise SystemExit('Nom de compte invalide')
    password = getpass.getpass('Mot de passe (12 caractères minimum) : ')
    confirmation = getpass.getpass('Confirmer : ')
    if password != confirmation or not 12 <= len(password) <= 256:
        raise SystemExit('Mot de passe trop court ou confirmation différente')
    engine = make_engine(Settings().database_url)
    try:
        with make_sessions(engine)() as session:
            owner_id = args.owner_id or uuid4()
            if session.scalar(select(User).where((User.username == username) | (User.owner_id == owner_id))):
                raise SystemExit('Nom ou propriétaire déjà associé à un compte')
            lock_workspace(session,owner_id)
            user=User(username=username, email=EmailInput(email=args.email).email if args.email else None,
                      owner_id=owner_id, password_hash=hash_password(password))
            session.add(user);session.flush()
            session.add(WorkspaceMembership(user_id=user.id,owner_id=owner_id))
            if session.get(AIBudget,f'byok:{owner_id}:openai') is None:
                session.add(AIBudget(id=f'byok:{owner_id}:openai'))
            session.commit()
        print('Compte créé. Aucune clé OpenAI enregistrée.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
