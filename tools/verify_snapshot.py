"""Compare original table fingerprints with a local or restored database; read-only."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--database', default='documind')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_]+',args.database):
        raise SystemExit('Invalid database name')
    integrity=json.loads((args.snapshot/'integrity.json').read_text(encoding='utf-8'))
    allowed={'documents','document_pages','document_chunks','analyses','users','ai_budgets',
        'ai_reservations','ai_usage','ai_summaries','ai_interactions','ai_sources','chunk_embeddings',
        'index_jobs','rag_results','rag_documents','ai_operation_documents','long_summary_jobs','summary_steps'}
    if not set(integrity).issubset(allowed) or not {'documents','document_pages','document_chunks','analyses'}.issubset(integrity):
        raise SystemExit('Invalid snapshot manifest')
    for table,expected in integrity.items():
        order='row_to_json(t)::text' if table=='ai_operation_documents' else 'id'
        sql=f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM {table} t"
        output=subprocess.check_output(['docker','compose','exec','-T','db','sh','-c',
            'exec psql -U "$POSTGRES_USER" -d "$1" -At -c "$2"', 'snapshot-check',args.database,sql],text=True)
        count,digest=output.strip().split('|')
        if int(count)!=expected['count'] or digest!=expected['digest']:
            raise SystemExit(f'Integrity mismatch: {table}')
    print(f'Integrity verified: {len(integrity)} original tables unchanged.')


if __name__=='__main__':
    main()
