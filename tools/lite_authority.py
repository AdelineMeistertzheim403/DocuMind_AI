"""Explicit CLI for manual Lite authority; no web approval, purge or deployment.

Operator commands run in the operator domain. app-* commands require root on the
application domain, a trusted manifest, and read-only SQL corroboration for export.
"""
import argparse
import json
from pathlib import Path
import sys
from sqlalchemy.exc import SQLAlchemyError

from backend.lite_authority import (AuthorityError,OperatorLedger,LocalOperations,OperationalConfirmation,
    canonical,strict,read,write,verify,validate_request,load_provision,export_proposal,import_view)


def parser():
    root=argparse.ArgumentParser(description=__doc__)
    root.add_argument('--instance',required=True)
    root.add_argument('--cohort',required=True)
    sub=root.add_subparsers(dest='command',required=True)
    for name in ('operator-init','operator-review','operator-confirm','operator-refresh','operator-recover','operator-restore','operator-provision-review'):
        p=sub.add_parser(name)
        for flag in ('ledger','recovery','signing-key','recovery-key','export-public-key'):p.add_argument('--'+flag,required=True)
        if name in ('operator-review','operator-confirm'):p.add_argument('--input',required=True)
        if name in ('operator-init','operator-confirm','operator-refresh','operator-restore','operator-provision-review'):p.add_argument('--confirm',required=True)
        if name=='operator-confirm':p.add_argument('--reference',required=True)
        if name=='operator-refresh':p.add_argument('--challenge',required=True)
        if name=='operator-provision-review':
            for flag in ('application-domain','operator-domain','recovery-domain','reference'):p.add_argument('--'+flag,required=True)
            p.add_argument('--scope',choices=('laboratory','deployment'),required=True)
        if name in ('operator-confirm','operator-refresh','operator-recover','operator-provision-review'):p.add_argument('--out',required=True)
    for name in ('app-challenge','app-export','app-import','app-inspect','app-prepare-deletion','app-apply-deletion'):
        p=sub.add_parser(name);p.add_argument('--manifest',required=True)
        if name in ('app-export','app-inspect','app-prepare-deletion','app-apply-deletion'):p.add_argument('--operation',required=True)
        if name=='app-export':p.add_argument('--phase',choices=('reserve','result','cancel','authorize','complete'),required=True)
        if name in ('app-prepare-deletion','app-apply-deletion'):
            p.add_argument('--confirm',required=True)
            p.add_argument('--offline-confirmed',action='store_true',required=True)
        if name=='app-prepare-deletion':
            p.add_argument('--kind',choices=('document_deletion_execution','account_purge_execution'),required=True)
        if name in ('app-export','app-challenge'):p.add_argument('--out',required=True)
        if name=='app-import':p.add_argument('--input',required=True)
    return root


def execute(args):
    import os
    if args.command.startswith('operator-'):
        ledger=OperatorLedger(args.ledger,args.recovery,args.signing_key,args.recovery_key,
            instance=args.instance,cohort=args.cohort,export_public_key=args.export_public_key)
        if args.command=='operator-init':
            if args.confirm!=args.instance:raise AuthorityError('Explicit genesis confirmation required')
            ledger.initialize();return {'status':'initialized','opening_authorized':False}
        if args.command=='operator-restore':return ledger.restore_empty(confirmation=args.confirm)
        if args.command=='operator-provision-review':
            result=ledger.attest_domains(args.application_domain,args.operator_domain,args.recovery_domain,
                reference=args.reference,scope=args.scope,confirmation=args.confirm)
        elif args.command=='operator-refresh':
            result=ledger.refresh(args.challenge,confirmation=args.confirm)
        elif args.command=='operator-recover':
            result=ledger.recover()
        else:
            proposal=strict(read(args.input,os.geteuid()))
            request=verify(proposal,args.export_public_key)
            validate_request(request,args.instance,args.cohort)
            if args.command=='operator-review':
                return {'operation':request['operation']['operation_id'],'kind':request['operation']['kind'],
                        'phase':request['phase'],'counter':request['counter'],'approval_created':False}
            result=ledger.approve(proposal,confirmation=args.confirm,reference=args.reference)
        write(args.out,canonical(result),os.geteuid())
        return {'status':'exported','opening_authorized':False}

    from backend.config import Settings
    settings=Settings(lite_authority_manifest=Path(args.manifest))
    manifest=load_provision(settings,administrative=True)
    if manifest is None or manifest['instance']!=args.instance or manifest['cohort']!=args.cohort:
        raise AuthorityError('Wrong explicit application target')
    store=LocalOperations(manifest['store'],manifest['api_uid'])
    adapter=OperationalConfirmation(store=store,control=manifest['control'],instance=args.instance,
        cohort=args.cohort,public_key=manifest['authority_public_key'],renew=False)
    if args.command=='app-challenge':
        write(args.out,canonical({'version':1,'instance':args.instance,'cohort':args.cohort,'challenge':adapter.nonce}),0)
    elif args.command=='app-import':
        if Path(args.input).parent!=Path(manifest['control'])/'inbox':raise AuthorityError('Administrative inbox required')
        import_view(strict(read(args.input,0)),control=manifest['control'],store=store,instance=args.instance,
                    cohort=args.cohort,public_key=manifest['authority_public_key'])
    elif args.command=='app-inspect':
        op=next((o for o in store.all() if str(o.id)==args.operation),None)
        if op:return op.export()
        op=next((o for o in store.deletions() if o.operation_id==args.operation),None)
        if not op:raise AuthorityError('Unknown local operation')
        from backend.lite_deletions import status
        return status(adapter,op)
    else:
        from backend.db import make_engine,make_sessions
        engine=make_engine(settings.database_url)
        try:
            with make_sessions(engine)() as session:
                session.info['deletion_settings']=settings
                if args.command=='app-apply-deletion':
                    from backend.lite_deletions import apply
                    return apply(session,settings,adapter,args.operation,confirmation=args.confirm,
                                 offline_confirmed=args.offline_confirmed)
                if args.command=='app-prepare-deletion':
                    from backend.lite_deletions import prepare_execution
                    if args.confirm!=args.operation:raise AuthorityError('Explicit request confirmation required')
                    # Root validates the manifest first; only the API identity writes its cache.
                    os.seteuid(manifest['api_uid'])
                    try:
                        op=prepare_execution(session,settings,adapter,args.operation,args.kind)
                        return {'operation_id':op.operation_id,'state':'awaiting_confirmation'}
                    finally:os.seteuid(0)
                session.connection().exec_driver_sql('SET TRANSACTION READ ONLY' if engine.dialect.name=='postgresql' else 'PRAGMA query_only=ON')
                result=export_proposal(adapter,args.operation,args.phase,session,read(manifest['export_private_key'],0))
            write(args.out,canonical(result),0)
        finally:engine.dispose()
    return {'status':'completed','opening_authorized':False}


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=execute(args)
    except (ValueError,OSError,ImportError,KeyError,TypeError,RuntimeError,SQLAlchemyError):
        # Never echo paths, private keys, DSNs, SQL/driver failures or raw inputs.
        print('{"status":"blocked","opening_authorized":false}')
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':sys.exit(main())
