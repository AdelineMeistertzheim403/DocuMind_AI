"""Inspect ambiguous reservations, or conservatively charge their whole reserved amount."""
import argparse
from uuid import UUID

from sqlalchemy import select

from ..config import Settings
from ..db import make_engine, make_sessions
from .models import AIReservation
from .service import lock_budget


def main():
    parser = argparse.ArgumentParser(description='API arrêtée : audit budgétaire sans appel fournisseur')
    parser.add_argument('--charge-reservation', type=UUID, help='Comptabiliser le maximum réservé, sans restituer de budget incertain')
    args = parser.parse_args()
    engine = make_engine(Settings().database_url)
    try:
        with make_sessions(engine)() as session:
            if args.charge_reservation:
                row = session.get(AIReservation, args.charge_reservation)
                if row is None or row.status not in ['reserved', 'uncertain']:
                    raise SystemExit('Réservation en attente introuvable')
                scope = row.budget_id
                budget = lock_budget(session, scope)
                row = session.get(AIReservation, args.charge_reservation, populate_existing=True)
                budget.reserved_usd -= row.reserved_usd
                budget.spent_usd += row.reserved_usd
                row.actual_usd, row.status = row.reserved_usd, 'failed'
                row.error_code, row.error_status = 'provider_uncertain', 503
                session.commit()
                print('Maximum réservé comptabilisé comme estimation prudente. Aucun budget incertain remboursé.')
            else:
                for row in session.scalars(select(AIReservation).where(AIReservation.status.in_(['reserved', 'uncertain']))):
                    print(f'{row.id} owner={row.owner_id} mode={row.budget_id} status={row.status} reserved_usd={row.reserved_usd}')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
