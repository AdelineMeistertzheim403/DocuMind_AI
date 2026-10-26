"""Consistent local Compose snapshot; run with API/web stopped. Never prints credentials."""
import json
import argparse
import subprocess
import hashlib
import tarfile
from pathlib import PurePosixPath
from datetime import datetime, timezone
from pathlib import Path


def create_backup(compose, destination, env=None):
    """Reusable by the approved VPS deployment; compose contains no credential arguments."""
    def compose_command(command):
        return compose+command[2:]
    running=subprocess.check_output(compose+['ps','--status','running','--services'],text=True,env=env,stderr=subprocess.PIPE).splitlines()
    if 'api' in running or 'web' in running:
        raise ValueError('Stop API and web before a consistent snapshot')
    destination.mkdir(parents=True, mode=0o700)
    commands = {
        'database.dump': ['docker', 'compose', 'exec', '-T', 'db', 'sh', '-c',
            'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
        # Read the persistent files with a one-off container; API remains stopped.
        'documents.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T', '--entrypoint',
            'tar', 'api', '-C', '/app/var', '-czf', '-', 'documents'],
    }
    for name, command in commands.items():
        with (destination / name).open('wb') as output:
            subprocess.run(compose_command(command), stdout=output, stderr=subprocess.PIPE, check=True,env=env)
    with (destination/'database.dump').open('rb') as dump:
        subprocess.run(compose+['exec','-T','db','pg_restore','--list'],stdin=dump,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,env=env)
    with tarfile.open(destination/'documents.tar.gz') as archive:
        for member in archive:
            if member.issym() or member.islnk() or PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts:
                raise ValueError('Unexpected archive member')
    tables = ['documents', 'document_pages', 'document_chunks', 'analyses', 'users', 'ai_budgets',
              'ai_reservations', 'ai_usage', 'ai_summaries', 'ai_interactions', 'ai_sources']
    existing=subprocess.check_output(compose+['exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT tablename FROM pg_tables WHERE schemaname=\'public\'"'],text=True,env=env,stderr=subprocess.PIPE).splitlines()
    tables += [name for name in ['chunk_embeddings','index_jobs','rag_results','rag_documents',
        'ai_operation_documents','long_summary_jobs','summary_steps','workspaces','workspace_memberships','account_tokens','account_deletion_requests','public_registration_quota'] if name in existing]
    integrity = {}
    for table in tables:
        columns_sql=f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND table_schema='public' ORDER BY ordinal_position"
        columns=subprocess.check_output(compose+['exec','-T','db','sh','-c','exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"','columns',columns_sql],text=True,env=env,stderr=subprocess.PIPE).splitlines()
        order='row_to_json(t)::text'
        sql = f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM (SELECT {','.join(columns)} FROM {table}) t"
        result = subprocess.check_output(compose+['exec','-T','db','sh','-c',
            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"', 'backup-check', sql], text=True,env=env,stderr=subprocess.PIPE)
        count, digest = result.strip().split('|')
        integrity[table] = {'count': int(count), 'digest': digest, 'columns':columns}
    (destination / 'integrity.json').write_text(json.dumps(integrity, indent=2), encoding='utf-8')
    revision=subprocess.check_output(compose+['exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT version_num FROM alembic_version"'],text=True,env=env,stderr=subprocess.PIPE).strip()
    if revision=='0007' and 'public_registration_quota' not in integrity:
        raise ValueError('Schema 0007 requires the public registration quota inventory')
    checksums={}
    for name in commands:
        with (destination/name).open('rb') as source:
            checksums[name]=hashlib.file_digest(source,'sha256').hexdigest()
    (destination / 'manifest.json').write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(),
        'database_major': 17, 'migration': revision, 'integrity_version':2, 'files': list(commands), 'sha256':checksums}, indent=2), encoding='utf-8')
    return destination


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--production',action='store_true')
    parser.add_argument('--release-env',type=Path,help='Digest-pinned images.env for production')
    parser.add_argument('--compose-file',type=Path,help='Production release Compose, e.g. current/compose.production.yaml')
    args=parser.parse_args()
    compose=['docker','compose'] + (['--project-directory',str(Path.cwd()),'-p','documind-prod','--env-file','.env.production'] if args.production else [])
    if args.release_env:
        compose+=['--env-file',str(args.release_env)]
    if args.production:
        compose+=['-f',str(args.compose_file or 'compose.production.yaml')]
    elif args.compose_file:
        compose+=['-f',str(args.compose_file)]
    destination = Path('var/backups') / datetime.now(timezone.utc).strftime('sprint6-%Y%m%d-%H%M%S')
    create_backup(compose,destination)
    print(f'Backup created: {destination}')


if __name__ == '__main__':
    main()
