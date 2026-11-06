"""Root-only, offline erasure decisions. No production defaults or auto approval."""
import argparse
import json
from pathlib import Path
from uuid import UUID

from . import erasure
from .auth import User
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description='Offline standard-profile administrative erasure')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    request = commands.add_parser('request-account')
    request.add_argument('user_id', type=UUID)
    for name in ('plan', 'authorize', 'execute', 'verify', 'status'):
        command = commands.add_parser(name)
        command.add_argument('operation_id', type=UUID)
        if name in ('authorize', 'execute'):
            command.add_argument('--confirm', type=UUID, required=True)
        if name == 'authorize':
            command.add_argument('--policy', type=Path, required=True)
            command.add_argument('--identity-evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        erasure.require_root()
        settings = Settings()
        if args.command == 'init':
            engine, sessions = erasure.fresh_session(settings)
            try:
                # Initialization does not authorize or mutate application data.
                erasure.checked_path(settings.recovery_state_path, 0)
                if erasure.read_recovery_state(settings.recovery_state_path) != 'quarantined':
                    raise erasure.ErasureError('Quarantine required before explicit provisioning')
                with sessions() as session:
                    if session.get_bind().dialect.name != 'postgresql':
                        raise erasure.ErasureError('PostgreSQL required')
                erasure.Authority(settings).initialize()
            finally:
                engine.dispose()
            report = {'state': 'initialized', 'completed': False}
        elif args.command == 'request-account':
            engine, sessions = erasure.fresh_session(settings)
            try:
                with sessions() as session:
                    user = session.get(User, args.user_id)
                    if user is None:
                        raise erasure.ErasureError('Known account required')
                    report = erasure.submit(session, settings, user, administrative=True)
            finally:
                engine.dispose()
        else:
            operation = str(args.operation_id)
            if args.command == 'plan':
                report = erasure.plan(settings, operation)
            elif args.command == 'authorize':
                report = erasure.authorize(settings, operation, str(args.confirm),
                                           args.policy, args.identity_evidence)
            elif args.command == 'execute':
                report = erasure.execute(settings, operation, str(args.confirm))
            elif args.command == 'verify':
                report = erasure.verify(settings, operation)
            else:
                # Status is evidence state only, never a fresh erasure assertion.
                report = erasure.summary(erasure.Authority(settings).operation(operation))
                report['active_erasure_verified'] = False
                report['verification_required'] = True
        print(json.dumps(report, sort_keys=True))
        return 0
    except erasure.ErasureError as error:
        print(json.dumps({'state': 'refused', 'completed': False, 'reason': str(error)}))
        return 1
    except Exception:
        print('{"state":"failed","completed":false,"reason":"administrative_erasure_unavailable"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
