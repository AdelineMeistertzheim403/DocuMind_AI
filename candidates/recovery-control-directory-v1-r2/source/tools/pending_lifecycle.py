"""Schedulable read-only inventory. Never invokes purge_pending(execute=True)."""
import argparse
import json

from backend.account_admin import plan_pending_cleanup
from backend.config import Settings
from backend.db import make_engine, make_sessions


def run(settings, hours):
    engine = make_engine(settings.database_url)
    try:
        with make_sessions(engine)() as session:
            connection = session.connection()
            connection.exec_driver_sql('SET TRANSACTION READ ONLY' if engine.dialect.name == 'postgresql' else 'PRAGMA query_only=ON')
            return plan_pending_cleanup(session, hours)
    finally:
        engine.dispose()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--simulate', action='store_true', required=True)
    parser.add_argument('--older-than-hours', type=int, required=True)
    args=parser.parse_args()
    try:
        report=run(Settings(),args.older_than_hours)
    except Exception:
        print('{"status":"failed","reason":"pending_inventory_failed","execution_enabled":false}')
        return 1
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
