"""Explicit local operator actions; no production defaults, no provider calls."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from uuid import UUID

from backend.lifecycle_registry import Registry, KINDS


def main():
    parser = argparse.ArgumentParser(description='Private lifecycle ledger; never exposed over HTTP')
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--backup-lock', type=Path,
                        default=Path(os.environ['LIFECYCLE_BACKUP_LOCK_PATH'])
                        if os.environ.get('LIFECYCLE_BACKUP_LOCK_PATH') else None)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    plan=commands.add_parser('expiry-plan')
    plan.add_argument('--at',type=datetime.fromisoformat)
    plan.add_argument('--backup-safe-before',type=datetime.fromisoformat)
    receive = commands.add_parser('receive')
    receive.add_argument('kind', choices=sorted(KINDS))
    receive.add_argument('--user-id', type=UUID)
    receive.add_argument('--owner-id', type=UUID)
    close = commands.add_parser('close')
    close.add_argument('id', type=UUID)
    close.add_argument('--retention-days', type=int, required=True)
    observe = commands.add_parser('observe-admissions')
    observe.add_argument('count', type=int)
    restore = commands.add_parser('restore-plan')
    restore.add_argument('--restored-count', type=int, required=True)
    expire = commands.add_parser('expire')
    expire.add_argument('--at', type=datetime.fromisoformat, required=True)
    expire.add_argument('--backup-safe-before', type=datetime.fromisoformat, required=True)
    expire.add_argument('--execute', action='store_true')
    documents=commands.add_parser('expire-document-receipts')
    documents.add_argument('--retention-days',type=int,required=True)
    documents.add_argument('--at',type=datetime.fromisoformat,required=True)
    documents.add_argument('--backup-safe-before',type=datetime.fromisoformat,required=True)
    documents.add_argument('--execute',action='store_true')
    confirm=commands.add_parser('confirm-document-absent')
    confirm.add_argument('id',type=UUID)
    confirm.add_argument('--offline-confirmed',action='store_true',required=True)
    args = parser.parse_args()
    if args.backup_lock is None or not args.backup_lock.is_absolute():
        parser.error('A shared absolute --backup-lock path is required')
    os.environ['LIFECYCLE_BACKUP_LOCK_PATH'] = str(args.backup_lock)
    try:
        registry = Registry(args.registry)
        if args.command == 'init':
            registry.initialize()
            report = {'initialized': True}
        elif args.command=='expiry-plan':
            report=registry.expiry_plan(at=args.at,backup_safe_before=args.backup_safe_before)
        elif args.command == 'receive':
            report = {'id': registry.receive(args.kind, user_id=args.user_id, owner_id=args.owner_id)}
        elif args.command == 'close':
            registry.finish(str(args.id), retention_days=args.retention_days)
            report = {'closed': True}
        elif args.command == 'observe-admissions':
            registry.observe_admissions(args.count)
            report = {'observed': True}
        elif args.command == 'restore-plan':
            report = registry.restore_plan(args.restored_count)
        elif args.command == 'expire-document-receipts':
            report=registry.expire_documents(retention_days=args.retention_days,at=args.at,
                                            backup_safe_before=args.backup_safe_before,execute=args.execute)
        elif args.command == 'confirm-document-absent':
            from backend.config import Settings
            registry.confirm_document_absent(args.id,Settings())
            report={'confirmed':True}
        else:
            report = registry.expire(at=args.at, backup_safe_before=args.backup_safe_before, execute=args.execute)
    except Exception:
        print(json.dumps({'status': 'failed', 'reason': 'registry_operation_failed'}))
        return 1
    # Restore plans contain pseudonymous identifiers: output to private terminal/file only.
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
