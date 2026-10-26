"""Restore to a NEW test database, verify files/data and migration rollback, then remove only that copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from backend.config import Settings


def seal_restored_registration(engine):
    """After exact snapshot verification, keep a restored COPY closed without changing its count."""
    with engine.begin() as connection:
        exists=connection.scalar(text("SELECT to_regclass('public.public_registration_quota')"))
        if exists is None:return {'quota_present':False,'closed':None,'requires_review':True}
        row=connection.execute(text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public' FOR UPDATE")).one_or_none()
        if row is None or type(row.issued_count) is not int or row.issued_count<0:
            raise ValueError('Restored public quota is missing or incoherent; keep the copy offline')
        connection.execute(text("UPDATE public_registration_quota SET closed=true WHERE id='public'"))
        checked=connection.execute(text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")).one()
        if checked.issued_count!=row.issued_count or checked.closed is not True:
            raise ValueError('Restored admission closure could not be verified')
        return {'quota_present':True,'closed':True,'issued_count':checked.issued_count,'requires_review':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--database',default='documind_restore_sprint5')
    args=parser.parse_args()
    if not re.fullmatch(r'documind_restore_[a-z0-9_]+',args.database):
        raise SystemExit('Use an isolated documind_restore_ database name')
    url=make_url(Settings().database_url).set(host='127.0.0.1')
    admin=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        if connection.execute(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':args.database}).scalar():
            raise SystemExit('Restore database already exists; nothing changed')
        connection.execute(text(f'CREATE DATABASE {args.database}'))
    extracted=Path('var/restores')/args.database
    if extracted.exists():
        raise SystemExit('Restore directory already exists; inspect it before retrying')
    extracted.mkdir(parents=True,mode=0o700)
    with (args.snapshot/'database.dump').open('rb') as source:
        subprocess.run(['docker','compose','exec','-T','db','sh','-c',
            'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error','restore',args.database],stdin=source,check=True)
    verify=[sys.executable,'tools/verify_snapshot.py',str(args.snapshot),'--database',args.database]
    subprocess.run(verify,check=True)
    env={**os.environ,'DATABASE_URL':url.set(database=args.database).render_as_string(hide_password=False)}
    manifest=json.loads((args.snapshot/'manifest.json').read_text(encoding='utf-8'))
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True)
    subprocess.run(verify,check=True)
    subprocess.run([sys.executable,'-m','alembic','downgrade',manifest['migration']],env=env,check=True)
    subprocess.run(verify,check=True)
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True)
    subprocess.run(verify,check=True)
    with tarfile.open(args.snapshot/'documents.tar.gz') as archive:
        archive.extractall(extracted,filter='data')
    restored=create_engine(url.set(database=args.database))
    count=0
    with restored.connect() as connection:
        for name,digest,size in connection.execute(text('SELECT storage_name,sha256,size_bytes FROM documents')):
            path=(extracted/'documents'/name).resolve()
            if not path.is_relative_to((extracted/'documents').resolve()):
                raise SystemExit('Unexpected file path in restore')
            if path.stat().st_size!=size or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise SystemExit('Restored document checksum mismatch')
            count+=1
    # The copy never has an API/BFF attached. Verify original fingerprints FIRST,
    # then deliberately close admissions before any possible reuse; never rewrite the archive.
    seal_restored_registration(restored)
    restored.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE {args.database}'))
    admin.dispose()
    target=extracted.resolve()
    if target.parent==Path('var/restores').resolve() and target.name==args.database:
        shutil.rmtree(target)
    print(f'Restore verified: database, upgrade/rollback, and {count} document checksums. Isolated copy removed.')


if __name__=='__main__':main()
