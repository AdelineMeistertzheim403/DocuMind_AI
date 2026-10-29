"""Synthetic native systemd payload; never used by production units."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('seed','notify','notify-fail','emit','bulk'))
    args=parser.parse_args()
    if args.mode=='seed':
        os.chdir('/app');sys.path.insert(0,'/app')
        os.environ['DATABASE_URL']='sqlite:////fixture/inventory.db'
        os.environ['REGISTRATION_MODE']='disabled';os.environ['AI_ENABLED']='false'
        from alembic import command
        from alembic.config import Config
        command.upgrade(Config('/app/alembic.ini'),'0007')
        from backend.db import make_engine,make_sessions
        from backend.auth import User
        from backend.models import now
        from uuid import uuid4
        engine=make_engine(os.environ['DATABASE_URL'])
        try:
            with make_sessions(engine)() as session:
                session.add(User(owner_id=uuid4(),username='synthetic-pending',email='systemd-private@example.test',
                                 password_hash='synthetic-not-used-for-auth',registration_kind='public',
                                 created_at=now()-timedelta(days=8)))
                session.commit()
        finally:engine.dispose()
        os.chmod('/fixture/inventory.db',0o444)
        print('synthetic_inventory_seeded')
    elif args.mode in ('notify','notify-fail'):
        sys.path.insert(0,'/app')
        from tools import lifecycle_alert
        def sink(event):
            if args.mode=='notify-fail':raise RuntimeError('SYNTHETIC_PRIVATE_NOTIFICATION_ERROR')
            print(json.dumps({'synthetic_notification_sink':event},sort_keys=True))
        lifecycle_alert.send=sink
        return lifecycle_alert.main()
    elif args.mode=='emit':
        print('PHASE152_TIME_MARKER',flush=True)
    else:
        # Distinct bounded lines: no personal data, no external sender/receiver.
        for index in range(28000):print(f'PHASE152_CAPACITY {index:06d} '+('x'*1000))
    return 0


if __name__=='__main__':raise SystemExit(main())
