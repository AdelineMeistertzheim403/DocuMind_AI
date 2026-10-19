"""Consistent local Compose snapshot; run with API/web stopped. Never prints credentials."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    destination = Path('var/backups') / datetime.now(timezone.utc).strftime('sprint4-%Y%m%d-%H%M%S')
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
            subprocess.run(command, stdout=output, check=True)
    tables = ['documents', 'document_pages', 'document_chunks', 'analyses', 'users', 'ai_budgets',
              'ai_reservations', 'ai_usage', 'ai_summaries', 'ai_interactions', 'ai_sources']
    existing=subprocess.check_output(['docker','compose','exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT tablename FROM pg_tables WHERE schemaname=\'public\'"'],text=True).splitlines()
    tables += [name for name in ['chunk_embeddings','index_jobs','rag_results','rag_documents',
        'ai_operation_documents','long_summary_jobs','summary_steps'] if name in existing]
    integrity = {}
    for table in tables:
        order='row_to_json(t)::text' if table=='ai_operation_documents' else 'id'
        sql = f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM {table} t"
        result = subprocess.check_output(['docker','compose','exec','-T','db','sh','-c',
            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"', 'backup-check', sql], text=True)
        count, digest = result.strip().split('|')
        integrity[table] = {'count': int(count), 'digest': digest}
    (destination / 'integrity.json').write_text(json.dumps(integrity, indent=2), encoding='utf-8')
    revision=subprocess.check_output(['docker','compose','exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT version_num FROM alembic_version"'],text=True).strip()
    (destination / 'manifest.json').write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(),
        'database_major': 17, 'migration': revision, 'files': list(commands)}, indent=2), encoding='utf-8')
    print(f'Backup created: {destination}')


if __name__ == '__main__':
    main()
