"""Reconcile local files against committed database records with the API stopped."""
import argparse
import hashlib
import json
import re
import stat

from sqlalchemy import select

from .config import Settings
from .db import make_engine
from .models import Document

GENERATED = re.compile(r"^[0-9a-f]{32}\.(?:part|pdf|txt|pdf\.deleted|txt\.deleted)$")


def reconciliation_plan(settings):
    engine = make_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            referenced = set(connection.scalars(select(Document.storage_name)))
    finally:
        engine.dispose()
    raw = settings.storage_dir.absolute()
    if any(path.is_symlink() for path in (raw,*raw.parents)):
        raise ValueError('Symlinked storage is unsafe')
    root = raw.resolve()
    actions = []
    if not root.exists():
        raise ValueError('Storage directory unavailable')
    if not root.is_dir() or any(not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|txt)',name) for name in referenced):
        raise ValueError('Unsafe storage inventory')
    inventory=[]
    for path in sorted(root.iterdir()):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Unsafe storage entry')
        inventory.append((path.name,info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns))
        if not GENERATED.fullmatch(path.name):
            continue
        original = path.name.removesuffix(".deleted")
        if path.name.endswith(".deleted") and original in referenced:
            destination = root / original
            if not destination.exists():
                actions.append(("restore", path.name))
                continue
        if path.name not in referenced:
            actions.append(("delete", path.name))
    for name in sorted(referenced):
        if not (root / name).exists() and not (root / (name + ".deleted")).exists():
            actions.append(("missing", name))
    payload={'root':str(root),'database_fingerprint':hashlib.sha256(settings.database_url.encode()).hexdigest(),
             'referenced':sorted(referenced),'files':inventory,'actions':actions}
    seal=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return {'simulation':True,'actions':actions,'plan_sha256':seal}


def reconcile(settings, apply=False, *, offline_confirmed=False, approved_plan_sha256=None):
    if apply and getattr(settings, 'lifecycle_durable_receipts_required', True):
        raise ValueError('Destructive reconciliation disabled pending independent receipt review')
    plan=reconciliation_plan(settings)
    if apply:
        if not offline_confirmed or approved_plan_sha256 != plan['plan_sha256']:
            raise ValueError('Stopped writers and approval of the unchanged plan required')
        # Detect changes between planning and execution. No repair with active writers.
        if reconciliation_plan(settings)['plan_sha256'] != approved_plan_sha256:
            raise ValueError('Storage changed during review')
        root=settings.storage_dir.resolve()
        for action,name in plan['actions']:
            path=root/name
            if action=='restore':path.replace(root/name.removesuffix('.deleted'))
            elif action=='delete':path.unlink()
    return plan['actions']


def main():
    parser = argparse.ArgumentParser(description="Maintenance API arrêtée uniquement ; simulation par défaut")
    parser.add_argument("--apply", action="store_true", help="Appliquer suppressions et restaurations")
    parser.add_argument('--offline-confirmed',action='store_true')
    parser.add_argument('--approved-plan-sha256')
    args = parser.parse_args()
    settings=Settings()
    if args.apply:
        reconcile(settings,True,offline_confirmed=args.offline_confirmed,approved_plan_sha256=args.approved_plan_sha256)
        print('{"applied":true}')
    else:
        print(json.dumps(reconciliation_plan(settings),sort_keys=True))


if __name__ == "__main__":
    main()
