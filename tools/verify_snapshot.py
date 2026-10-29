"""Compare original table fingerprints with a local or restored database; read-only."""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text


LIFECYCLE_STORES = {
    'registry': (1, {'requests', 'admission_watermark', 'document_erasures'}),
    'witness': (1, {'confirmations', 'admissions'}),
    'authenticated': (2, {'confirmations', 'admissions', 'synthetic_transitions',
                          'hold_mirrors', 'authenticated_header'}),
    'holds': (2, {'confirmations', 'admissions', 'holds_v2', 'hold_decisions_v2'}),
    'admission_anchor': (2, {'confirmations', 'admissions', 'admission_anchor'}),
}
BACKUP_FILES = {'database.dump', 'documents.tar.gz', 'lifecycle.sqlite.tar.gz', 'integrity.json'}


def verify_capture(snapshot, manifest, *, require_s2=False):
    """Verify exact archive completeness; never equate completeness with recovery authority."""
    version = manifest.get('backup_format_version', 0)
    if version != 3:
        if require_s2:
            raise SystemExit('Legacy snapshot lacks the five SQLite lifecycle stores; S2 restore refused')
        return False
    if (manifest.get('capture_complete') is not True
            or manifest.get('s2_recovery_authorized') is not False
            or manifest.get('recovery_disposition') !=
            'quarantine_pending_independent_freshness_and_operator_review'):
        raise SystemExit('Invalid or success-shaped S2 recovery declaration')
    files = manifest.get('files')
    checksums = manifest.get('sha256')
    if (not isinstance(manifest.get('capture_id'), str)
            or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                                manifest['capture_id'])
            or not isinstance(files, list) or len(files) != len(BACKUP_FILES)
            or set(files) != BACKUP_FILES
            or not isinstance(checksums, dict) or set(checksums) != BACKUP_FILES
            or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)
                   for value in checksums.values())
            or manifest.get('capture_scope') != ['postgresql', 'documents', 'lifecycle_sqlite']):
        raise SystemExit('Incomplete full-backup file manifest')
    if set(path.name for path in snapshot.iterdir()) != BACKUP_FILES | {'manifest.json'}:
        raise SystemExit('Unexpected or missing full-backup archive file')
    for name in BACKUP_FILES:
        path = snapshot / name
        if not path.is_file() or path.is_symlink():
            raise SystemExit('Backup payload must be a regular file')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if manifest['sha256'].get(name) != digest:
            raise SystemExit(f'Backup payload checksum mismatch: {name}')

    required_quiescence = {
        'api_web_stopped', 'only_database_service_running', 'private_networks_exclusive',
        'no_other_postgresql_clients', 'lifecycle_exclusive_lock_acquired',
    }
    quiescence = manifest.get('quiescence')
    if (not isinstance(quiescence, dict)
            or any(quiescence.get(key) is not True for key in required_quiescence)
            or quiescence.get('out_of_band_privileged_host_access')
            != 'trusted_operator_boundary_not_machine_verifiable'):
        raise SystemExit('Backup quiescence evidence is incomplete')

    declared = manifest.get('lifecycle_stores')
    lifecycle_hashes = manifest.get('lifecycle_store_sha256')
    if (not isinstance(declared, dict) or set(declared) != set(LIFECYCLE_STORES)
            or not isinstance(lifecycle_hashes, dict)
            or set(lifecycle_hashes) != set(LIFECYCLE_STORES)
            or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)
                   for value in lifecycle_hashes.values())):
        raise SystemExit('Exactly five lifecycle stores are required')
    with tarfile.open(snapshot / 'lifecycle.sqlite.tar.gz', 'r:gz') as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        expected_names = {'metadata.json'} | {
            f'stores/{name}.sqlite' for name in LIFECYCLE_STORES
        }
        if (names != expected_names or len(members) != len(expected_names)
                or any(not member.isfile() or member.issym() or member.islnk() for member in members)):
            raise SystemExit('Lifecycle archive is not the exact five-store set')
        metadata_file = archive.extractfile('metadata.json')
        metadata = json.load(metadata_file) if metadata_file else None
        if (not isinstance(metadata, dict) or type(metadata.get('format')) is not int
                or metadata.get('format') != 1
                or metadata.get('capture_id') != manifest['capture_id']
                or not isinstance(metadata.get('stores'), dict)
                or set(metadata['stores']) != set(LIFECYCLE_STORES)):
            raise SystemExit('Lifecycle capture metadata does not match the manifest')
        with tempfile.TemporaryDirectory(prefix='documind-snapshot-verify-') as temporary:
            for name, (version_expected, tables_expected) in LIFECYCLE_STORES.items():
                item = metadata['stores'][name]
                declared_item = declared[name]
                expected_file = f'stores/{name}.sqlite'
                if (not isinstance(item, dict) or item.get('snapshot') != expected_file
                        or type(item.get('user_version')) is not int
                        or item['user_version'] != version_expected
                        or not isinstance(item.get('tables'), list)
                        or len(item['tables']) != len(tables_expected)
                        or set(item['tables']) != tables_expected
                        or not isinstance(item.get('sha256'), str)
                        or not isinstance(declared_item, dict)
                        or declared_item != item
                        or item.get('journal_mode') not in {
                            'delete', 'truncate', 'persist', 'memory', 'wal', 'off'}):
                    raise SystemExit(f'Lifecycle schema metadata mismatch: {name}')
                source = archive.extractfile(expected_file)
                if source is None:
                    raise SystemExit(f'Lifecycle snapshot missing: {name}')
                payload = source.read()
                digest = hashlib.sha256(payload).hexdigest()
                if (digest != item['sha256']
                        or digest != lifecycle_hashes.get(name)):
                    raise SystemExit(f'Lifecycle SQLite checksum mismatch: {name}')
                database = Path(temporary) / f'{name}.sqlite'
                database.write_bytes(payload)
                connection = sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True)
                try:
                    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise SystemExit(f'Lifecycle SQLite integrity failure: {name}')
                    actual_version = connection.execute('PRAGMA user_version').fetchone()[0]
                    actual_tables = {row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                    if actual_version != version_expected or actual_tables != tables_expected:
                        raise SystemExit(f'Lifecycle SQLite schema mismatch: {name}')
                finally:
                    connection.close()
    return True


def verify_snapshot(snapshot,database='documind',compose=None,env=None,*,require_s2=False,database_url=None):
    """Read-only, usable with an explicitly isolated Compose project in restore tests."""
    if not re.fullmatch(r'[a-zA-Z0-9_]+',database):
        raise SystemExit('Invalid database name')
    integrity=json.loads((snapshot/'integrity.json').read_text(encoding='utf-8'))
    manifest_path=snapshot/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    capture_complete=verify_capture(snapshot,manifest,require_s2=require_s2)
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
    engine=create_engine(database_url) if database_url is not None else None
    try:
        for table,expected in integrity.items():
            columns=expected.get('columns')
            if columns is not None and (not columns or any(not re.fullmatch(r'[a-z_][a-z0-9_]*',name) for name in columns)):
                raise SystemExit('Invalid column manifest')
            order='row_to_json(t)::text' if columns or table=='ai_operation_documents' else 'id'
            source=f"(SELECT {','.join(columns)} FROM {table})" if columns else table
            sql=f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM {source} t"
            if engine is None:
                output=subprocess.check_output((compose or ['docker','compose'])+['exec','-T','db','sh','-c',
                    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At -c "$2"', 'snapshot-check',database,sql],text=True,env=env)
                count,digest=output.strip().split('|')
                count=int(count)
            else:
                with engine.connect() as connection:
                    count,digest=connection.execute(text(sql)).one()
            if count!=expected['count'] or digest!=expected['digest']:
                raise SystemExit(f'Integrity mismatch: {table}')
    finally:
        if engine is not None:
            engine.dispose()
    print(f'Integrity verified: {len(integrity)} original tables unchanged.')
    certified='public_registration_quota' in integrity
    if not certified:print('Legacy inventory: public admission quota is NOT certified; keep restores offline and closed.')
    if capture_complete:
        print('Capture inventory complete; S2 recovery remains quarantined pending independent freshness and operator review.')
    else:
        print('Legacy snapshot lacks lifecycle SQLite coverage; it is NOT complete for S2 recovery.')
    return {'quota_certified':certified,'tables':len(integrity),
            'capture_complete':capture_complete,'s2_recovery_authorized':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--database', default='documind')
    parser.add_argument('--require-s2', action='store_true',
                        help='Refuse legacy snapshots without all lifecycle stores')
    args=parser.parse_args()
    verify_snapshot(args.snapshot,args.database,require_s2=args.require_s2)


if __name__=='__main__':
    main()
