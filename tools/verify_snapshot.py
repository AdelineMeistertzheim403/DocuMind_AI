"""Compare original table fingerprints with a local or restored database; read-only."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def verify_snapshot(snapshot,database='documind',compose=None,env=None):
    """Read-only, usable with an explicitly isolated Compose project in restore tests."""
    if not re.fullmatch(r'[a-zA-Z0-9_]+',database):
        raise SystemExit('Invalid database name')
    integrity=json.loads((snapshot/'integrity.json').read_text(encoding='utf-8'))
    manifest_path=snapshot/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    version=manifest.get('integrity_version',1)
    if type(version) is not int or version not in (1,2):raise SystemExit('Unsupported integrity version')
    allowed={'documents','document_pages','document_chunks','analyses','users','ai_budgets',
        'ai_reservations','ai_usage','ai_summaries','ai_interactions','ai_sources','chunk_embeddings',
        'index_jobs','rag_results','rag_documents','ai_operation_documents','long_summary_jobs','summary_steps',
        'workspaces','workspace_memberships','account_tokens','account_deletion_requests','public_registration_quota'}
    if not set(integrity).issubset(allowed) or not {'documents','document_pages','document_chunks','analyses'}.issubset(integrity):
        raise SystemExit('Invalid snapshot manifest')
    if version==2 and manifest.get('migration')=='0007' and 'public_registration_quota' not in integrity:
        raise SystemExit('Missing public quota integrity for schema 0007')
    if 'public_registration_quota' in integrity:
        columns=integrity['public_registration_quota'].get('columns')
        if columns is not None and set(columns)!={'id','issued_count','closed'}:
            raise SystemExit('Incomplete public quota integrity columns')
    for table,expected in integrity.items():
        columns=expected.get('columns')
        if columns is not None and (not columns or any(not re.fullmatch(r'[a-z_][a-z0-9_]*',name) for name in columns)):
            raise SystemExit('Invalid column manifest')
        order='row_to_json(t)::text' if columns or table=='ai_operation_documents' else 'id'
        source=f"(SELECT {','.join(columns)} FROM {table})" if columns else table
        sql=f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM {source} t"
        output=subprocess.check_output((compose or ['docker','compose'])+['exec','-T','db','sh','-c',
            'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At -c "$2"', 'snapshot-check',database,sql],text=True,env=env)
        count,digest=output.strip().split('|')
        if int(count)!=expected['count'] or digest!=expected['digest']:
            raise SystemExit(f'Integrity mismatch: {table}')
    print(f'Integrity verified: {len(integrity)} original tables unchanged.')
    certified='public_registration_quota' in integrity
    if not certified:print('Legacy inventory: public admission quota is NOT certified; keep restores offline and closed.')
    return {'quota_certified':certified,'tables':len(integrity)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--database', default='documind')
    args=parser.parse_args()
    verify_snapshot(args.snapshot,args.database)


if __name__=='__main__':
    main()
