"""Actual synthetic pg_dump/pg_restore and filesystem/SQLite recovery, no mocks."""
from contextlib import closing
import io
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url

from backend.account_models import PublicRegistrationQuota
from backend import lite_snapshot as snapshots
from backend.lite_authority import AuthorityError, canonical, strict
from backend.lite_deletions import prepare_execution
from backend.recovery_quarantine import read_recovery_state
from tests.test_lite_deletions import (deletions, domains, real_admissions, ledgers,
    document_request, execution, confirm, effect, close)
from tests.test_lite_authority import prepare_http, confirm_phase
from tests.test_lite_admissions import send
from tools.validate_restore import LAB_MARKER, LAB_MARKER_CONTENT


CANDIDATE = os.environ.get('LITE_CANDIDATE_SHA256')


@pytest.fixture
def capture_env(deletions, tmp_path, monkeypatch):
    if os.name != 'posix' or os.geteuid() != 0:
        pytest.skip('Requires the isolated Linux root/PostgreSQL lab; not qualified on Windows')
    if deletions[1].state.engine.dialect.name != 'postgresql':
        pytest.skip('Real PostgreSQL clients/cluster required; no mock restoration')
    if CANDIDATE is None:
        pytest.fail('A measured source inventory digest is required for the Linux restore lab')
    lock = tmp_path/'capture-lock'
    lock.mkdir(mode=0o700)
    monkeypatch.setenv('LIFECYCLE_BACKUP_LOCK_PATH', str(lock/'snapshot.lock'))
    monkeypatch.setenv('DOCUMIND_RESTORE_LAB', 'isolated')
    snapshots_root = tmp_path/'captures'
    snapshots_root.mkdir(mode=0o700)
    restore_root = tmp_path/'restores'
    restore_root.mkdir(mode=0o700)
    (restore_root/LAB_MARKER).write_bytes(LAB_MARKER_CONTENT)
    (restore_root/LAB_MARKER).chmod(0o600)
    return deletions, snapshots_root, restore_root


def take(env, name='snapshot'):
    deletions, captures, _ = env
    client, app, d, *_ = deletions
    with app.state.sessions() as session:
        session.execute(update(PublicRegistrationQuota).values(closed=True))
        session.commit()
    # Neutralize HTTP writers, not the administrative CLI. Other lab processes
    # do not exist; PostgreSQL clients and prepared transactions are checked.
    app.state.recovery_ready_at_start = False
    assert client.get('/api/v1/account').status_code == 503
    app.state.engine.dispose()
    app.state.authentication_engine.dispose()
    snapshot = captures/name
    with app.state.sessions() as session:
        manifest = snapshots.capture(app.state.settings, d['adapter'], session, snapshot,
                                     candidate=CANDIDATE, offline_confirmed=True)
    return snapshot, manifest, snapshots.file_hash(snapshot/'manifest.json')


def restored(env, snapshot, checksum):
    d = env[0][2]
    database = 'documind_restore_'+uuid4().hex[:12]
    admin = make_url(os.environ['TEST_DATABASE_URL']).set(database='documind_restore_admin')
    result = snapshots.restore(snapshot, root=env[2], database=database, admin_url=admin,
        expected_sha256=checksum, instance=d['instance'], cohort=str(d['adapter'].cohort_id), candidate=CANDIDATE)
    return env[2]/database, create_engine(admin.set(database=database)), result


def assessment(env, target, snapshot, engine):
    identity = strict((target/'destination.json').read_bytes())
    d = env[0][2]
    envelope = d['ledger'].refresh(identity['challenge'], confirmation=identity['challenge'])
    return snapshots.assess_recovery(target, snapshot, engine, envelope,
        confirmation=identity['destination'], offline_confirmed=True)


def resume_source(env):
    app = env[0][1]
    app.state.recovery_ready_at_start = True
    with app.state.sessions() as session:
        session.execute(update(PublicRegistrationQuota).values(closed=False))
        session.commit()


def enroll(env):
    source = env[0][:3]
    body, operation = prepare_http(source)
    confirm_phase(source, operation, 'reserve')
    assert send(source[0], body).status_code == 202
    confirm_phase(source, operation, 'result')
    assert send(source[0], body).status_code == 201
    return operation


def test_actual_capture_restore_encrypted_independent_retrieval(capture_env, tmp_path):
    snapshot, manifest, checksum = take(capture_env)
    assert len([p for p in manifest['entries'] if p.startswith('lifecycle/')]) == 5
    assert manifest['sql']['document_chunks']['count'] == 1
    assert not any('operator' in name or 'export_keys' in name for name in manifest['entries'])
    copies = Path('/independent')/uuid4().hex
    keys = Path('/recovery-keys')/uuid4().hex
    copies.mkdir(mode=0o700); keys.mkdir(mode=0o700)
    key = keys/'key'
    key.write_bytes(os.urandom(32)); key.chmod(0o600)
    encrypted = copies/'capture.enc'
    snapshots.encrypted_copy(snapshot, encrypted, key, manifest_sha256=checksum)
    recovered = tmp_path/'recovered'
    snapshots.recover_encrypted_copy(encrypted, key, recovered, manifest_sha256=checksum,
        instance=manifest['instance'], cohort=manifest['cohort'], candidate=CANDIDATE)
    assert all((snapshot/name).read_bytes() == (recovered/name).read_bytes()
               for name in snapshots.PAYLOADS | {'manifest.json'})
    operator_before = {p.name: snapshots.file_hash(p) for p in capture_env[0][2]['dirs']['operator'].glob('event-*')}
    target, engine, result = restored(capture_env, recovered, checksum)
    try:
        assert result['status'] == 'quarantined' and result['documents_verified'] == 1
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM users')) == 1
            assert connection.scalar(text('SELECT count(*) FROM document_chunks')) == 1
            assert connection.scalar(text("SELECT closed FROM public_registration_quota WHERE id='public'")) is True
        report = assessment(capture_env, target, recovered, engine)
        assert report['status'] == 'blocked' and report['counter_independent'] == 1
        assert report['quarantine_release_authorized'] is False
        assert {p.name: snapshots.file_hash(p) for p in capture_env[0][2]['dirs']['operator'].glob('event-*')} == operator_before
        evidence = {'restore': result, 'assessment': report, 'manifest_sha256': checksum,
                    'database_dump_sha256': snapshots.file_hash(snapshot/'database.dump'),
                    'cipher_sha256': snapshots.file_hash(encrypted), 'retrieved_bytes_identical': True}
        evidence_root = Path('/results')/('verified-capture-'+manifest['capture_id'])
        evidence_root.mkdir()
        for name in snapshots.PAYLOADS | {'manifest.json'}:
            shutil.copyfile(snapshot/name, evidence_root/name)
        shutil.copyfile(encrypted, evidence_root/'independent-copy.enc')
        evidence['synthetic_capture_evidence'] = evidence_root.name
        Path('/results/real-lite-restore-evidence.json').write_bytes(canonical(evidence))
    finally:
        engine.dispose()


@pytest.mark.parametrize('bad', ['store', 'quota_open', 'uncertain', 'offline', 'sql_client', 'unconfirmed'])
def test_incomplete_or_live_capture_refused(capture_env, bad):
    env, captures, _ = capture_env
    _, app, d, *_ = env
    if bad == 'unconfirmed':
        prepare_http(env[:3])
    with app.state.sessions() as session:
        session.execute(update(PublicRegistrationQuota).values(closed=bad != 'quota_open'))
        session.commit()
    app.state.engine.dispose(); app.state.authentication_engine.dispose()
    extra_engine = extra = None
    try:
        if bad == 'store':
            app.state.settings.lifecycle_holds_path.unlink()
        if bad == 'uncertain':
            op = d['store'].all()[0]; op.state = 'uncertain'; d['store'].save(op)
        if bad == 'sql_client':
            extra_engine = create_engine(app.state.settings.database_url)
            extra = extra_engine.connect()
        with app.state.sessions() as session, pytest.raises((AuthorityError, FileNotFoundError)):
            snapshots.capture(app.state.settings, d['adapter'], session, captures/'refused',
                candidate=CANDIDATE, offline_confirmed=bad != 'offline')
    finally:
        if extra is not None:
            extra.close(); extra_engine.dispose()


@pytest.mark.parametrize('bad', ['instance', 'cohort', 'candidate', 'manifest', 'archive', 'missing', 'schema'])
def test_wrong_or_corrupt_snapshot_refused(capture_env, bad):
    snapshot, manifest, checksum = take(capture_env)
    kwargs = dict(expected_sha256=checksum, instance=manifest['instance'], cohort=manifest['cohort'], candidate=CANDIDATE)
    if bad in ('instance', 'cohort'):
        kwargs[bad] = str(uuid4())
    if bad == 'candidate':
        kwargs['candidate'] = '0'*64
    if bad == 'manifest':
        (snapshot/'manifest.json').write_bytes(canonical({**manifest, 'issued_count': 0}))
    if bad == 'archive':
        with (snapshot/'application.tar.gz').open('ab') as stream:
            stream.write(b'corrupt')
    if bad == 'missing':
        (snapshot/'database.dump').unlink()
    if bad == 'schema':
        manifest['schema']['migration'] = '0006'
        (snapshot/'manifest.json').write_bytes(canonical(manifest))
        kwargs['expected_sha256'] = snapshots.file_hash(snapshot/'manifest.json')
    with pytest.raises((AuthorityError, FileNotFoundError)):
        snapshots.verify_capture(snapshot, **kwargs)


def test_wal_cache_capture_includes_committed_rows(capture_env):
    store = capture_env[0][2]['store']
    with closing(sqlite3.connect(store.path)) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        writer.execute("UPDATE operations SET payload=payload")
        writer.commit()
        snapshot, _, checksum = take(capture_env)
        with tarfile.open(snapshot/'application.tar.gz') as archive:
            cache = archive.extractfile('lite/operations.sqlite').read()
        with closing(sqlite3.connect(':memory:')) as check:
            check.deserialize(cache)
            snapshots.validate_local(check)
            assert check.execute('SELECT count(*) FROM operations').fetchone()[0] == 1
        assert checksum


@pytest.mark.parametrize('when', ['intent', 'erased', 'closure', 'purge'])
def test_post_snapshot_effects_never_escape_quarantine(capture_env, when):
    snapshot, _, checksum = take(capture_env)
    resume_source(capture_env)
    env = capture_env[0]
    if when == 'intent':
        operation = document_request(env); confirm(env, operation, 'authorize')
    elif when == 'erased':
        operation = execution(env)
        confirm(env, operation, 'authorize'); effect(env, operation); confirm(env, operation, 'complete')
    else:
        operation = close(env)
        if when == 'purge':
            with env[1].state.sessions() as session:
                operation = prepare_execution(session, env[1].state.settings, env[2]['adapter'],
                                              operation.operation_id, 'account_purge_execution')
            confirm(env, operation, 'authorize'); effect(env, operation); confirm(env, operation, 'complete')
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        report = assessment(capture_env, target, snapshot, engine)
        assert 'deletion_requires_destination_bound_reconciliation' in report['reasons']
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
        assert report['opening_authorized'] is False
        # It is deliberately NOT claimed that restored SQL/files have been erased.
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM documents')) == 1
        assert (target/'documents'/env[-1].name).read_bytes() == b'Synthetic personal text, never user data.'
    finally:
        engine.dispose()


def test_three_then_five_and_purge_stays_blocked_without_recreating_accounts(capture_env):
    env = capture_env[0]
    enroll(capture_env); enroll(capture_env)
    snapshot, manifest, checksum = take(capture_env)
    assert manifest['issued_count'] == 3
    resume_source(capture_env)
    enroll(capture_env); enroll(capture_env)
    request = close(env)
    with env[1].state.sessions() as session:
        operation = prepare_execution(session, env[1].state.settings, env[2]['adapter'],
                                      request.operation_id, 'account_purge_execution')
    confirm(env, operation, 'authorize'); effect(env, operation); confirm(env, operation, 'complete')
    from tests.test_lite_admissions import invitation
    assert send(env[0], invitation(env[1])).status_code != 201
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        report = assessment(capture_env, target, snapshot, engine)
        assert report['counter_restored'] == 3 and report['counter_independent'] == 5
        assert 'admission_sql_not_reconstructible' in report['reasons']
        assert 'cumulative_counter_conflict' in report['reasons']
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM users')) == 3
            assert connection.scalar(text("SELECT closed FROM public_registration_quota WHERE id='public'"))
    finally:
        engine.dispose()


def test_old_view_replayed_confirmation_and_used_destination_refused(capture_env):
    snapshot, manifest, checksum = take(capture_env)
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        identity = strict((target/'destination.json').read_bytes())
        old = strict((target/'control/accepted.json').read_bytes())
        with pytest.raises(AuthorityError):
            snapshots.assess_recovery(target, snapshot, engine, old,
                confirmation=identity['destination'], offline_confirmed=True)
        report = assessment(capture_env, target, snapshot, engine)
        assert report['status'] == 'blocked'
        with pytest.raises(AuthorityError):
            snapshots.assess_recovery(target, snapshot, engine, old,
                confirmation=str(uuid4()), offline_confirmed=True)
        with pytest.raises(AuthorityError):
            snapshots.restore(snapshot, root=capture_env[2], database=identity['database'],
                admin_url=engine.url.set(database='documind_restore_admin'), expected_sha256=checksum,
                instance=manifest['instance'], cohort=manifest['cohort'], candidate=CANDIDATE)
    finally:
        engine.dispose()


def test_corrupt_encrypted_copy_and_wrong_key_refused(capture_env, tmp_path):
    snapshot, _, checksum = take(capture_env)
    keys = tmp_path/'keys'; keys.mkdir(mode=0o700)
    copies = tmp_path/'copies'; copies.mkdir(mode=0o700)
    key = keys/'key'; key.write_bytes(os.urandom(32)); key.chmod(0o600)
    encrypted = copies/'capture.enc'
    snapshots.encrypted_copy(snapshot, encrypted, key, manifest_sha256=checksum)
    raw = encrypted.read_bytes()
    encrypted.write_bytes(raw[:-1])
    with pytest.raises(AuthorityError):
        snapshots.decrypt_copy(encrypted, key, manifest_sha256=checksum)
    encrypted.write_bytes(raw)
    key.write_bytes(os.urandom(32))
    with pytest.raises(AuthorityError):
        snapshots.decrypt_copy(encrypted, key, manifest_sha256=checksum)


def test_no_root_no_effect_and_cli_errors_are_minimized(monkeypatch, capsys):
    from tools.lite_restore import main
    monkeypatch.setattr(os, 'geteuid', lambda: 10001, raising=False)
    with pytest.raises(AuthorityError):
        snapshots.root_required()
    assert main(['verify', '--snapshot', '/never-real', '--manifest-sha256', '0'*64,
                 '--instance', str(uuid4()), '--cohort', str(uuid4()), '--candidate', CANDIDATE or '0'*64]) == 1
    assert capsys.readouterr().out == '{"status":"blocked","opening_authorized":false}\n'


@pytest.mark.parametrize('point', ['capture_archive', 'restore_sql', 'restore_files'])
def test_interrupted_attempt_is_not_reused_or_promoted(capture_env, monkeypatch, point):
    if point == 'capture_archive':
        original = snapshots.add_file
        calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('synthetic capture interruption')
            return original(*args, **kwargs)
        monkeypatch.setattr(snapshots, 'add_file', interrupted)
        with pytest.raises(OSError):
            take(capture_env, 'interrupted')
        incomplete = capture_env[1]/'interrupted'
        assert (incomplete/'database.dump').exists()
        assert not (incomplete/'manifest.json').exists()
        with pytest.raises(FileExistsError):
            take(capture_env, 'interrupted')
        monkeypatch.setattr(snapshots, 'add_file', original)
        assert take(capture_env, 'new-attempt')[1]['complete'] is True
        return
    snapshot, manifest, checksum = take(capture_env)
    original_pg = snapshots.pg_command
    original_copy = snapshots.shutil.copyfileobj
    def interrupted_pg(engine, executable, arguments, **kwargs):
        # pg_restore REALLY ran; the interruption is its lost acknowledgement.
        original_pg(engine, executable, arguments, **kwargs)
        raise OSError('synthetic lost restore acknowledgement')
    def interrupted_copy(source, destination, *args, **kwargs):
        original_copy(source, destination, *args, **kwargs)
        raise OSError('synthetic file restore interruption')
    if point == 'restore_sql':
        monkeypatch.setattr(snapshots, 'pg_command', interrupted_pg)
    else:
        monkeypatch.setattr(snapshots.shutil, 'copyfileobj', interrupted_copy)
    database = 'documind_restore_'+uuid4().hex[:12]
    admin = make_url(os.environ['TEST_DATABASE_URL']).set(database='documind_restore_admin')
    kwargs = dict(root=capture_env[2], database=database, admin_url=admin, expected_sha256=checksum,
                  instance=manifest['instance'], cohort=manifest['cohort'], candidate=CANDIDATE)
    with pytest.raises(OSError):
        snapshots.restore(snapshot, **kwargs)
    target = capture_env[2]/database
    assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    assert not (target/'recovery-assessment.json').exists()
    with pytest.raises(AuthorityError):
        snapshots.restore(snapshot, **kwargs)


@pytest.mark.parametrize('mode', ['forged', 'other_destination', 'wrong_instance', 'no_offline', 'lost_authority'])
def test_current_authority_and_confirmation_cannot_be_substituted(capture_env, mode):
    snapshot, _, checksum = take(capture_env)
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        identity = strict((target/'destination.json').read_bytes())
        d = capture_env[0][2]
        challenge = identity['challenge'] if mode != 'other_destination' else '0'*64
        envelope = d['ledger'].refresh(challenge, confirmation=challenge)
        if mode == 'forged':
            envelope['signature'] = '0'*128
        if mode == 'wrong_instance':
            envelope['payload']['instance'] = str(uuid4())
        if mode == 'lost_authority':
            envelope = {}
        with pytest.raises(AuthorityError):
            snapshots.assess_recovery(target, snapshot, engine, envelope,
                confirmation=identity['destination'], offline_confirmed=mode != 'no_offline')
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    finally:
        engine.dispose()


def test_uncertain_reservation_post_snapshot_blocks_assessment(capture_env):
    snapshot, _, checksum = take(capture_env)
    resume_source(capture_env)
    env = capture_env[0]
    _, pending = prepare_http(env[:3])
    confirm_phase(env[:3], pending, 'reserve')
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        assert 'uncertain_reservation' in assessment(capture_env, target, snapshot, engine)['reasons']
    finally:
        engine.dispose()


def test_snapshot_cannot_establish_completeness_of_new_holds(capture_env):
    from datetime import timedelta
    from backend.lifecycle_durability import configured_coordinator
    from backend.lifecycle_holds import HoldStore
    from backend.lifecycle_registry import configured_registry
    from backend.models import now
    snapshot, _, checksum = take(capture_env)
    env = capture_env[0]
    settings = env[1].state.settings
    coordinator = configured_coordinator(settings, configured_registry(settings))
    holds = HoldStore(settings.lifecycle_holds_path, coordinator.authenticated)
    before = snapshots.file_hash(settings.lifecycle_holds_path)
    at = now()
    holds.create(dict(id=str(uuid4()), responsible_id=str(uuid4()), scope_kind='owner',
        scope_id=str(env[3].owner_id), reason='legal_hold', reviewed_at=at,
        review_at=at+timedelta(days=1), ends_at=None, end_event='legal_hold_lifted'), at)
    assert snapshots.file_hash(settings.lifecycle_holds_path) != before
    current_hash = snapshots.file_hash(settings.lifecycle_holds_path)
    target, engine, _ = restored(capture_env, snapshot, checksum)
    try:
        report = assessment(capture_env, target, snapshot, engine)
        assert 'current_holds_completeness_unproven' in report['reasons']
        assert holds is not None
        assert snapshots.file_hash(settings.lifecycle_holds_path) == current_hash
    finally:
        engine.dispose()


@pytest.mark.parametrize('bad', ['symlink', 'hardlink', 'public_mode', 'duplicate', 'traversal'])
def test_unsafe_archive_is_refused_even_with_a_recomputed_outer_hash(capture_env, bad):
    snapshot, manifest, _ = take(capture_env)
    with tarfile.open(snapshot/'application.tar.gz') as archive:
        contents = [(member.name, archive.extractfile(member).read()) for member in archive]
    with tarfile.open(snapshot/'application.tar.gz', 'w:gz') as archive:
        for number, (name, raw) in enumerate(contents):
            member = tarfile.TarInfo('../outside' if bad == 'traversal' and number == 0 else name)
            member.mode = 0o644 if bad == 'public_mode' and number == 0 else 0o600
            member.size = len(raw)
            if number == 0 and bad in ('symlink', 'hardlink'):
                member.type = tarfile.SYMTYPE if bad == 'symlink' else tarfile.LNKTYPE
                member.linkname = '/never-real'
                member.size = 0
            archive.addfile(member, io.BytesIO(raw) if member.isfile() else None)
            if number == 0 and bad == 'duplicate':
                archive.addfile(member, io.BytesIO(raw))
    manifest['sha256']['application.tar.gz'] = snapshots.file_hash(snapshot/'application.tar.gz')
    (snapshot/'manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(AuthorityError):
        snapshots.verify_capture(snapshot, expected_sha256=snapshots.file_hash(snapshot/'manifest.json'),
            instance=manifest['instance'], cohort=manifest['cohort'], candidate=CANDIDATE)
