"""Explicit Lite laboratory capture, reconciliation and closed recovery release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend import lite_snapshot
from backend.lite_authority import (AuthorityError, LocalOperations, OperationalConfirmation,
                                     load_provision, read, strict)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest='command', required=True)
    for name in ('capture', 'verify', 'restore', 'assess', 'encrypt', 'recover-copy'):
        p = sub.add_parser(name)
        p.add_argument('--snapshot', type=Path, required=True)
        if name == 'capture':
            p.add_argument('--settings', type=Path, required=True)
            p.add_argument('--candidate', required=True)
            p.add_argument('--offline-confirmed', action='store_true', required=True)
        elif name == 'assess':
            p.add_argument('--target', type=Path, required=True)
            p.add_argument('--authority-view', type=Path, required=True)
            p.add_argument('--confirm', required=True)
            p.add_argument('--offline-confirmed', action='store_true', required=True)
        else:
            p.add_argument('--manifest-sha256', required=True)
            if name in ('verify', 'restore', 'recover-copy'):
                for flag in ('instance', 'cohort', 'candidate'):
                    p.add_argument('--'+flag, required=True)
            if name == 'restore':
                p.add_argument('--restore-root', type=Path, required=True)
                p.add_argument('--database', required=True)
            if name in ('encrypt', 'recover-copy'):
                p.add_argument('--key-file', type=Path, required=True)
                p.add_argument('--copy', type=Path, required=True)
    for name in ('reconcile-challenge', 'reconcile-inventory', 'reconcile-plan', 'reconcile-apply', 'reconcile-diagnose'):
        p = sub.add_parser(name)
        p.add_argument('--confirm', required=True)
        p.add_argument('--out', type=Path, required=True)
        if name == 'reconcile-inventory':
            p.add_argument('--settings', type=Path, required=True)
            p.add_argument('--context', type=Path, required=True)
        else:
            p.add_argument('--snapshot', type=Path, required=True)
            p.add_argument('--target', type=Path, required=True)
        if name != 'reconcile-challenge':
            p.add_argument('--authority-view', type=Path, required=True)
            p.add_argument('--offline-confirmed', action='store_true', required=True)
        if name in ('reconcile-plan', 'reconcile-apply'):
            p.add_argument('--operation', required=True)
            p.add_argument('--export-key', type=Path, required=True)
    for name in ('recovery-validate', 'recovery-authorize', 'recovery-resolve'):
        p = sub.add_parser(name)
        for flag in ('snapshot', 'target', 'authority-view', 'out'):
            p.add_argument('--'+flag, type=Path, required=True)
        p.add_argument('--confirm', required=True)
        p.add_argument('--offline-confirmed', action='store_true', required=True)
        if name != 'recovery-resolve':
            p.add_argument('--runtime', type=Path, required=True)
        if name != 'recovery-authorize':
            p.add_argument('--export-key', type=Path, required=True)
        if name == 'recovery-validate':
            p.add_argument('--settings', type=Path, required=True)
            p.add_argument('--candidate', required=True)
            p.add_argument('--api-uid', type=int, required=True)
            p.add_argument('--api-gid', type=int, required=True)
        elif name == 'recovery-resolve':
            p.add_argument('--operation', required=True)
    for name in ('recovery-serve', 'serve-api'):
        p = sub.add_parser(name)
        p.add_argument('--runtime', type=Path, required=True)
        p.add_argument('--port', type=int, required=True)
        if name == 'recovery-serve':
            p.add_argument('--confirm', required=True)
    return root


def execute(args):
    if args.command == 'serve-api':
        from backend.lite_release import serve_api
        serve_api(args.runtime, args.port)
        return {'status': 'stopped', 'opening_authorized': False}
    lite_snapshot.root_required()
    if args.command == 'recovery-serve':
        from backend.lite_release import serve
        return serve(args.runtime, confirmation=args.confirm, port=args.port)
    if args.command.startswith('recovery-'):
        return execute_release(args)
    if args.command.startswith('reconcile-'):
        return execute_reconciliation(args)
    if args.command == 'capture':
        from backend.config import Settings
        # No .env file discovery. Only explicitly provisioned settings are read.
        settings = Settings(_env_file=None, **strict(read(args.settings, 0)))
        manifest = load_provision(settings, administrative=True)
        if manifest is None:
            raise AuthorityError('Explicit provisioned Lite authority required')
        adapter = OperationalConfirmation(
            store=LocalOperations(manifest['store'], manifest['api_uid']), control=manifest['control'],
            instance=manifest['instance'], cohort=manifest['cohort'],
            public_key=manifest['authority_public_key'], renew=False)
        engine = create_engine(settings.database_url)
        try:
            with Session(engine) as session:
                lite_snapshot.capture(settings, adapter, session, args.snapshot,
                                      candidate=args.candidate, offline_confirmed=args.offline_confirmed)
        finally:
            engine.dispose()
        return {'status': 'captured', 'manifest_sha256': lite_snapshot.file_hash(args.snapshot/'manifest.json'),
                'opening_authorized': False}
    if args.command == 'encrypt':
        checksum = lite_snapshot.encrypted_copy(args.snapshot, args.copy, args.key_file,
                                               manifest_sha256=args.manifest_sha256)
        return {'status': 'encrypted_copy_verified', 'sha256': checksum, 'opening_authorized': False}
    if args.command == 'assess':
        engine = create_engine(os.environ['DOCUMIND_RESTORE_DATABASE_URL'])
        try:
            return lite_snapshot.assess_recovery(
                args.target, args.snapshot, engine, strict(read(args.authority_view, 0)),
                confirmation=args.confirm, offline_confirmed=args.offline_confirmed)
        finally:
            engine.dispose()
    identity = dict(instance=args.instance, cohort=args.cohort, candidate=args.candidate)
    if args.command == 'recover-copy':
        lite_snapshot.recover_encrypted_copy(args.copy, args.key_file, args.snapshot,
                                            manifest_sha256=args.manifest_sha256, **identity)
        return {'status': 'copy_recovered', 'opening_authorized': False}
    if args.command == 'verify':
        lite_snapshot.verify_capture(args.snapshot, expected_sha256=args.manifest_sha256, **identity)
        return {'status': 'capture_verified', 'opening_authorized': False}
    return lite_snapshot.restore(args.snapshot, root=args.restore_root, database=args.database,
        admin_url=make_url(os.environ['DOCUMIND_RESTORE_DATABASE_URL']),
        expected_sha256=args.manifest_sha256, **identity)


def execute_release(args):
    from backend import lite_release as release
    from backend.config import Settings
    from backend.lite_authority import canonical, write
    engine = create_engine(os.environ['DOCUMIND_RESTORE_DATABASE_URL'])
    try:
        options = dict(confirmation=args.confirm, offline_confirmed=args.offline_confirmed)
        envelope = strict(read(args.authority_view, 0))
        if args.command == 'recovery-authorize':
            result = release.authorize(args.target, args.snapshot, engine, envelope, args.runtime, **options)
        elif args.command == 'recovery-resolve':
            result = release.resolve_obsolete(args.target, args.snapshot, engine, envelope,
                args.operation, export_key=read(args.export_key, 0), **options)
        else:
            result = release.validate(args.target, args.snapshot, engine, envelope,
                Settings(_env_file=None, **strict(read(args.settings, 0))), args.runtime,
                candidate=args.candidate, api_uid=args.api_uid, api_gid=args.api_gid,
                export_key=read(args.export_key, 0), **options)
    finally:
        engine.dispose()
    write(args.out, canonical(result), 0)
    return {'status': result.get('status', 'exported_for_independent_review'), 'opening_authorized': False}


def execute_reconciliation(args):
    from backend import lite_reconciliation as recovery
    from backend.lite_authority import canonical, write
    if args.command == 'reconcile-inventory':
        from backend.config import Settings
        settings = Settings(_env_file=None, **strict(read(args.settings, 0)))
        provision = load_provision(settings, administrative=True)
        if provision is None:
            raise AuthorityError('Provisioned source authority required')
        adapter = OperationalConfirmation(store=LocalOperations(provision['store'], provision['api_uid']),
            control=provision['control'], instance=provision['instance'], cohort=provision['cohort'],
            public_key=provision['authority_public_key'], renew=False)
        engine = create_engine(settings.database_url)
        try:
            with Session(engine) as session:
                context = strict(read(args.context, 0))
                envelope = strict(read(args.authority_view, 0))
                if envelope['payload']['challenge'] != context['challenge']:
                    raise AuthorityError('Wrong destination inventory challenge')
                result = recovery.export_inventory(settings, adapter, session, context['context'], envelope,
                    export_key=read(provision['export_private_key'], 0), confirmation=args.confirm,
                    offline_confirmed=args.offline_confirmed)
        finally:
            engine.dispose()
    else:
        engine = create_engine(os.environ['DOCUMIND_RESTORE_DATABASE_URL'])
        try:
            if args.command == 'reconcile-challenge':
                result = recovery.challenge(args.target, args.snapshot, engine, confirmation=args.confirm)
            else:
                options = dict(confirmation=args.confirm, offline_confirmed=args.offline_confirmed)
                envelope = strict(read(args.authority_view, 0))
                if args.command == 'reconcile-diagnose':
                    result = recovery.diagnose(args.target, args.snapshot, engine, envelope, **options)
                else:
                    function = recovery.plan if args.command == 'reconcile-plan' else recovery.execute
                    result = function(args.target, args.snapshot, engine, envelope, args.operation,
                                      export_key=read(args.export_key, 0), **options)
        finally:
            engine.dispose()
    write(args.out, canonical(result), 0)
    return {'status': result.get('status', 'exported'), 'opening_authorized': False}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (ValueError, OSError, KeyError, TypeError, ImportError, RuntimeError,
            subprocess.SubprocessError, tarfile.TarError, SQLAlchemyError):
        # Driver errors and private inputs must not be echoed into CLI logs.
        print('{"status":"blocked","opening_authorized":false}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get('status') == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
