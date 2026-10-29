"""Linux-only synthetic laboratory payload; never selects a configured real DB."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import create_engine, text
from backend.lifecycle_registry import Registry
from backend.lifecycle_durability import ConfirmationStore, canonical
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_admissions import AdmissionAnchor, AdmissionCoordinator
from backend.lifecycle_holds import HoldStore, ActiveHoldError

EVIDENCE = Path('/evidence')
DOMAIN = 'documind-local-v2'


def operation(kind, row):
    if kind == 'account':
        receipt = {key: row[key] for key in ('id', 'kind', 'user_id', 'owner_id', 'received_at')}
        identifier, target, mutation = row['id'], row['user_id'], 'account_deactivation'
    else:
        receipt = {key: row[key] for key in ('document_id', 'owner_id', 'storage_name', 'requested_at')}
        identifier, target, mutation = row['document_id'], row['document_id'], 'document_erasure'
    return {'id': str(uuid5(NAMESPACE_URL, f'documind:receipt-v2:{kind}:{identifier}')),
            'type': mutation, 'target': target,
            'receipt_sha256': hashlib.sha256(canonical(receipt).encode()).hexdigest()}


def seed():
    assert os.name == 'posix' and not Path('/src/.env').exists()
    Path('/app/lifecycle').chmod(0o700)
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config('/src/alembic.ini'), 'head')
    engine = create_engine(os.environ['DATABASE_URL'])
    admin = create_engine(os.environ['DATABASE_URL'], isolation_level='AUTOCOMMIT')
    with admin.connect() as db:
        db.execute(text("CREATE ROLE documind_restore_admin LOGIN SUPERUSER PASSWORD 'synthetic'"))
        db.execute(text('CREATE DATABASE documind_restore_admin OWNER documind_restore_admin'))
    admin.dispose()
    from sqlalchemy.orm import Session
    from backend.auth import User, hash_password
    from backend.models import Document
    from backend.account_models import PublicRegistrationQuota
    paths = {}
    for name in ('registry', 'witness', 'authenticated', 'holds', 'admission_anchor'):
        directory = Path('/app/lifecycle') / name
        directory.mkdir(mode=0o700)
        paths[name] = directory / (name + '.sqlite')
    keys = {'auth': os.urandom(32).hex(), 'admission': os.urandom(32).hex()}
    key_file = EVIDENCE / 'synthetic-keys.json'
    key_file.write_text(json.dumps(keys)); key_file.chmod(0o600)
    registry = Registry(paths['registry']); registry.initialize()
    witness = ConfirmationStore(paths['witness']); witness.initialize()
    auth = AuthenticatedConfirmationStore(paths['authenticated'], bytes.fromhex(keys['auth']), DOMAIN); auth.initialize()
    holds = HoldStore(paths['holds'], auth); holds.initialize()
    anchor = AdmissionAnchor(paths['admission_anchor'], bytes.fromhex(keys['admission'])); anchor.initialize()
    admissions = AdmissionCoordinator(witness, anchor)
    users = [uuid4() for _ in range(5)]
    owners = [uuid4() for _ in range(5)]
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        for index, (user, owner) in enumerate(zip(users, owners), 1):
            admissions.reserve(index, str(user)); admissions.settle(index, str(user))
            db.add(User(id=user, owner_id=owner, username=f'synthetic-{index}',
                        password_hash=hash_password('Synthetic-only-password-' + str(index)), email=f'synthetic-{index}@example.invalid',
                        registration_kind='public', email_verified_at=now,
                        terms_version='synthetic-only', terms_accepted_at=now))
        quota = db.get(PublicRegistrationQuota, 'public')
        quota.issued_count, quota.closed = 5, True
        documents = Path('/app/var/documents'); documents.mkdir(parents=True)
        retained = []
        for index in range(3):
            data = f'Synthetic laboratory document {index}\n'.encode()
            name = uuid4().hex + '.txt'
            (documents / name).write_bytes(data)
            identifier = uuid4()
            db.add(Document(id=identifier, owner_id=owners[0], filename=f'synthetic-{index}.txt',
                            storage_name=name, media_type='text/plain', size_bytes=len(data),
                            sha256=hashlib.sha256(data).hexdigest()))
            retained.append({'id': str(identifier), 'name': name, 'sha256': hashlib.sha256(data).hexdigest()})
        db.commit()
        # Erase a synthetic document using ledger state transitions and SQL/file operations.
        deleted = retained.pop()
        registry.document_requested(deleted['id'], owners[0], deleted['name'])
        with registry.connection() as ledger:
            row = ledger.execute('SELECT * FROM document_erasures').fetchone()
        op = operation('document', row)
        auth.prepare(op); auth.confirm(op); auth.authorize_once(op)
        db.execute(text('DELETE FROM documents WHERE id=:id'), {'id': deleted['id']})
        db.commit()
        (documents / deleted['name']).unlink()
        registry.document_finished(deleted['id'], True); auth.record_result(op)
        account_receipt = registry.receive('erasure', user_id=users[4], owner_id=owners[4])
        with registry.connection() as ledger:
            row = ledger.execute('SELECT * FROM requests WHERE id=?', (account_receipt,)).fetchone()
        op = operation('account', row)
        auth.prepare(op); auth.confirm(op); auth.authorize_once(op)
        db.get(User, users[4]).disabled_at = now; db.commit()
        registry.account_deactivated(account_receipt); auth.record_result(op)
    registry.observe_admissions(5)
    holds.create({'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(users[0]),
                  'scope_kind': 'account', 'reason': 'legal_hold', 'reviewed_at': now - timedelta(seconds=1),
                  'review_at': now + timedelta(days=29), 'ends_at': None, 'end_event': 'legal_hold_lifted'}, now)
    engine.dispose()
    expected = {'users': list(map(str, users)), 'owners': list(map(str, owners)),
                'documents': retained, 'deleted': deleted, 'quota': 5}
    (EVIDENCE / 'expected.json').write_text(json.dumps(expected, indent=2))
    print('Synthetic PostgreSQL 0007, five admissions closed, five stores, authenticated receipts and active hold created.')


def restore():
    assert os.name == 'posix' and not Path('/src/.env').exists()
    # Local image filesystem, no package download or Docker socket in this runner.
    Path('/opt/pg').mkdir(parents=True)
    subprocess.run(['tar', '-xf', '/materials/pg-rootfs.tar', '-C', '/opt/pg'], check=True)
    wrapper = Path('/usr/local/bin/pg_restore')
    wrapper.write_text('#!/bin/sh\nexec chroot /opt/pg /usr/local/bin/pg_restore "$@"\n')
    wrapper.chmod(0o755)
    version = subprocess.check_output(['pg_restore', '--version'], text=True).strip()
    wheel = next(Path('/materials').glob('cryptography*.whl'))
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)], check=True)
    from tools.verify_snapshot import verify_snapshot, verify_capture
    from tools.validate_restore import _restore, _validate_lab, _isolated_url, LAB_MARKER_CONTENT, check_resurrection_denials
    from sqlalchemy.engine import make_url
    root = Path('/lab'); root.chmod(0o700)
    (root / '.synthetic-only').write_bytes(LAB_MARKER_CONTENT)
    snapshot = root / 'snapshot'; shutil.copytree(EVIDENCE / 'snapshot', snapshot)
    client_snapshot = Path('/opt/pg/lab/snapshot')
    client_snapshot.mkdir(parents=True)
    shutil.copy2(snapshot / 'database.dump', client_snapshot / 'database.dump')
    assert (client_snapshot / 'database.dump').read_bytes() == (snapshot / 'database.dump').read_bytes()
    os.environ['DOCUMIND_RESTORE_LAB'] = 'isolated'
    os.environ['DOCUMIND_RESTORE_DATABASE_URL'] = 'postgresql+psycopg://documind_restore_admin:synthetic@127.0.0.1:5432/documind_restore_admin'
    os.environ['REGISTRATION_MODE'] = 'disabled'; os.environ['AI_ENABLED'] = 'false'
    url = _isolated_url()
    verified = verify_snapshot(snapshot, 'documind_source', database_url=url.set(database='documind_source'), require_s2=True)
    database = 'documind_restore_' + uuid4().hex[:12]
    _validate_lab(snapshot, database, root)
    # Call the CLI unchanged: main invokes the same verification and restore functions.
    command = [sys.executable, '-m', 'tools.validate_restore', str(snapshot), '--database', database, '--restore-root', str(root)]
    result = subprocess.run(command, capture_output=True, text=True)
    (EVIDENCE / 'restore-cli.stdout.log').write_text(result.stdout)
    (EVIDENCE / 'restore-cli.stderr.log').write_text(result.stderr)
    if result.returncode:
        raise RuntimeError('Actual restore CLI failed: ' + result.stderr)
    target = root / database
    report = json.loads((target / 'quarantine.json').read_text())
    assert report['status'] == 'quarantined' and report['quota'] == {'issued_count': 5, 'closed': True}
    assert not report['opening_authorized'] and not report['critical_mutations_allowed']
    # In-process HTTP client only: no listening server and no business workers.
    from backend.config import Settings
    from backend.main import create_app
    from backend.recovery_quarantine import read_recovery_state
    from fastapi.testclient import TestClient
    from uuid import UUID
    latch = target / 'recovery-state.json'
    latch.write_text('{"format":1,"state":"quarantined"}\n'); latch.chmod(0o600)
    settings = Settings(_env_file=None, database_url=url.set(database=database).render_as_string(hide_password=False),
                        storage_dir=target / 'documents', recovery_state_path=latch,
                        registration_mode='disabled', ai_enabled=False,
                        api_keys={'synthetic-lab-api-key-0000000000000000000001': UUID(int=1)},
                        extraction_mode='development')
    app = create_app(settings)
    with TestClient(app) as client:
        http_denials = {path: client.get(path).status_code for path in ('/api/v1/health', '/api/v1/documents')}
        retained_id = json.loads((EVIDENCE / 'expected.json').read_text())['documents'][0]['id']
        download_path = '/api/v1/documents/' + retained_id + '/download'
        http_denials[download_path] = client.get(download_path).status_code
        http_denials['/api/v1/auth/register'] = client.post('/api/v1/auth/register', json={}).status_code
        assert all(value == 503 for value in http_denials.values())
        assert not app.state.summary_worker.thread.is_alive() and not app.state.recovery_ready_at_start
        assert read_recovery_state(latch) == 'quarantined'
    app.state.authentication_engine.dispose(); app.state.engine.dispose()
    paths = {name: target / 'lifecycle' / name / (name + '.sqlite') for name in (
        'registry', 'witness', 'authenticated', 'holds', 'admission_anchor')}
    keys = json.loads((EVIDENCE / 'synthetic-keys.json').read_text())
    from ops.testing.lifecycle_lot29_bundle import SyntheticLifecycleConsistencyVerifier
    verifier = SyntheticLifecycleConsistencyVerifier(bytes.fromhex(keys['auth']), bytes.fromhex(keys['admission']))
    cross = verifier.verify(paths)
    assert cross['admissions'] == 5 and cross['document_receipts'] == 1 and cross['account_receipts'] == 1 and cross['holds'] == 1
    engine = create_engine(url.set(database=database))
    expected = json.loads((EVIDENCE / 'expected.json').read_text())
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM users')) == 5
        assert db.scalar(text('SELECT count(*) FROM documents')) == 2
        assert db.scalar(text('SELECT count(*) FROM users WHERE disabled_at IS NOT NULL')) == 1
    # The restored copy is not attached to API/workers. Check middleware in regression below.
    results = []
    def case(number, title, action):
        try:
            evidence = action()
            results.append({'id': number, 'scenario': title, 'status': 'PASS', 'evidence': evidence})
        except Exception as error:
            results.append({'id': number, 'scenario': title, 'status': 'FAIL', 'evidence': type(error).__name__ + ': ' + str(error)})
    def refused(action):
        try:
            action()
        except (Exception, SystemExit) as error:
            return type(error).__name__ + ': ' + str(error)
        raise AssertionError('Unsafe condition was accepted')
    def archive_case(number, mutate):
        copy = root / ('negative-' + str(number)); shutil.copytree(snapshot, copy)
        manifest = json.loads((copy / 'manifest.json').read_text())
        mutate(copy, manifest)
        return refused(lambda: verify_capture(copy, manifest, require_s2=True))
    def sqlite_variant(number, mutate):
        base = root / ('stores-negative-' + str(number)); base.mkdir(mode=0o700)
        copied = {}
        for name, source in paths.items():
            directory = base / name; directory.mkdir(mode=0o700)
            copied[name] = directory / (name + '.sqlite'); shutil.copy2(source, copied[name])
        mutate(copied)
        return refused(lambda: verifier.verify(copied))
    case(1, 'SQLite absent', lambda: sqlite_variant(1, lambda p: p['witness'].unlink()))
    case(2, 'SQLite corrompu', lambda: sqlite_variant(2, lambda p: p['holds'].write_bytes(b'corrupt synthetic SQLite')))
    case(3, 'Manifest modifié', lambda: archive_case(3, lambda p, m: m.update(s2_recovery_authorized=True)))
    case(4, 'Dump altéré', lambda: archive_case(4, lambda p, m: (p / 'database.dump').write_bytes(b'corrupt synthetic dump')))
    def resurrect():
        old = root / 'old-documents'; shutil.copytree(target / 'documents', old)
        (old / expected['deleted']['name']).write_text('Synthetic old snapshot resurrection\n')
        denial = check_resurrection_denials(engine, paths['registry'], old)
        assert denial['document_resurrections'] == 1
        return denial
    case(5, 'Document supprimé présent dans une copie ancienne', resurrect)
    def remove_receipt(p):
        with sqlite3.connect(p['registry']) as db: db.execute('DELETE FROM document_erasures')
    case(6, 'Tombstone absent', lambda: sqlite_variant(6, remove_receipt))
    def quota_regression():
        # Transaction rolls back; authoritative witness remains five.
        with engine.connect() as db:
            transaction = db.begin()
            db.execute(text("UPDATE public_registration_quota SET issued_count=4 WHERE id='public'"))
            count = db.scalar(text("SELECT issued_count FROM public_registration_quota WHERE id='public'"))
            anchor = AdmissionAnchor(paths['admission_anchor'], bytes.fromhex(keys['admission']))
            witness = ConfirmationStore(paths['witness'])
            denial = anchor.inspect(witness.admission_entries(), count)
            assert denial['minimum_issued_count'] == 5 and denial['state'] == 'reconciliation_required' and not denial['opening_authorized']
            transaction.rollback()
        return denial
    case(7, 'Quota régressif', quota_regression)
    auth = AuthenticatedConfirmationStore(paths['authenticated'], bytes.fromhex(keys['auth']), DOMAIN)
    holds = HoldStore(paths['holds'], auth)
    def held():
        def attempt():
            with holds.guard([('account', expected['users'][0])]): pass
        return refused(attempt)
    case(8, 'Hold A20 actif', held)
    def uncertain(p):
        registry = Registry(p['registry'])
        identifier = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
        with registry.connection() as db: row = db.execute('SELECT * FROM requests WHERE id=?', (identifier,)).fetchone()
        AuthenticatedConfirmationStore(p['authenticated'], bytes.fromhex(keys['auth']), DOMAIN).prepare(operation('account', row))
    case(9, 'Opération préparée non confirmée', lambda: sqlite_variant(9, uncertain))
    results.append({'id': 10, 'scenario': 'Autorité externe indisponible', 'status': 'NOT_TESTED',
                    'evidence': 'Aucune autorité externe raccordée/autorisée; fraîcheur indépendante non vérifiée, ouverture interdite.'})
    results.append(json.loads((EVIDENCE / 'negative-session.json').read_text()))
    case(12, 'Destination non vierge', lambda: refused(lambda: _restore(snapshot, database, root, url)))
    case(13, 'Tentative d’ouverture via manifeste', lambda: archive_case(13, lambda p, m: m.update(recovery_disposition='ready')))
    results.append({'id': 14, 'scenario': 'Snapshot ancien et autorité divergente', 'status': 'NOT_TESTED',
                    'evidence': 'Pas d’autorité indépendante simulée; des hashes cohérents ne démontrent pas la fraîcheur.'})
    (EVIDENCE / 'negative-results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
    tests = [sys.executable, '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider',
             'tests/test_backup_offline_compose.py',
             'tests/test_snapshot_backup_integrity.py', 'tests/test_restore_quarantine.py',
             'tests/test_recovery_quarantine.py', 'tests/test_lifecycle_lot29_bundle.py',
             'tests/test_production_backups.py', '--junitxml=/evidence/targeted-tests.xml']
    regression = subprocess.run(tests, capture_output=True, text=True)
    (EVIDENCE / 'targeted-tests.log').write_text(regression.stdout + regression.stderr)
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    with tarfile.open(EVIDENCE / 'restored-evidence.tar.gz', 'w:gz') as archive:
        archive.add(target, arcname=database)
    output = {'environment': {'python': sys.version, 'pg_restore': version, 'sqlite': sqlite3.sqlite_version},
              'capture_id': manifest['capture_id'], 'sha256': manifest['sha256'],
              'capture_verification': verified, 'restore_command': command, 'restoration': report,
              'cross_store_verification': cross, 'http_denials_on_restored_copy': http_denials,
              'latch_state': read_recovery_state(latch), 'business_workers_started': False, 'negative_tests': results,
              'regression_exit': regression.returncode, 'opening_authorized': False}
    (EVIDENCE / 'execution.json').write_text(json.dumps(output, indent=2, ensure_ascii=False))
    engine.dispose()
    print(json.dumps(output, indent=2, ensure_ascii=False))
    if regression.returncode or any(row['status'] == 'FAIL' for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    {'seed': seed, 'restore': restore}[sys.argv[1]]()
