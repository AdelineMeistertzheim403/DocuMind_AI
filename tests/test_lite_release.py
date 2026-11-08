"""Real non-root loopback API from a reconciled synthetic PostgreSQL restore."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4, UUID

import httpx
import pytest
from sqlalchemy import select, text

from backend import lite_release as release
from backend import lite_reconciliation as recovery
from backend.auth import User
from backend.account_models import AccountToken
from backend.lite_authority import AuthorityError, canonical, strict, operation_payload
from backend.models import Document
from backend.recovery_quarantine import read_recovery_state
from tests.test_lite_reconciliation import (laboratory, capture_env, deletions, domains, real_admissions, ledgers,
    consult, inventory, planned, applied, diagnosis, source_document_deleted, source_purged,
    take, restored, resume_source, enroll)
from tests.test_lite_admissions import PASSWORD, invitation
from tests.conftest import BFF_KEY
from tools.validate_restore import LAB_MARKER, LAB_MARKER_CONTENT


@pytest.fixture
def release_env(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    inventory(lab, target, snapshot, engine)
    public = Path('/tmp')/('lite-release-'+uuid4().hex)
    public.mkdir(mode=0o755)
    (public/LAB_MARKER).write_bytes(LAB_MARKER_CONTENT)
    (public/LAB_MARKER).chmod(0o644)
    settings = lab[0][1].state.settings.model_copy(update={
        'database_url': engine.url.render_as_string(hide_password=False), 'extraction_mode': 'sandbox'})
    yield lab, snapshot, target, engine, public, settings
    engine.dispose()


def validated(env, **options):
    lab, snapshot, target, engine, public, settings = env
    runtime = public/('runtime-'+uuid4().hex)
    args = dict(candidate=strict((target/'destination.json').read_bytes())['candidate'],
        api_uid=10001, api_gid=10001, confirmation=strict((target/'destination.json').read_bytes())['destination'],
        export_key=lab[0][2]['export'], offline_confirmed=True)
    args.update(options)
    proposal = release.validate(target, snapshot, engine, consult(lab, target, snapshot, engine),
                                settings, runtime, **args)
    return runtime, proposal


def approved(env, runtime, proposal):
    lab = env[0]
    return lab[0][2]['ledger'].approve(proposal,
        confirmation=proposal['payload']['operation']['operation_id'], reference='synthetic-recovery-release')


def authorized(env, runtime):
    lab, snapshot, target, engine, *_ = env
    current = consult(lab, target, snapshot, engine)
    return release.authorize(target, snapshot, engine, current, runtime,
        confirmation=strict((target/'destination.json').read_bytes())['destination'], offline_confirmed=True)


@contextmanager
def running(env, runtime, proposal, *, expect_started=True):
    env[3].dispose()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    op = proposal['payload']['operation']['operation_id']
    output = runtime/'server.log'
    with output.open('wb') as log:
        process = subprocess.Popen([sys.executable, '-m', 'tools.lite_restore', 'recovery-serve',
            '--runtime', str(runtime), '--port', str(port), '--confirm', op], stdout=log, stderr=log)
        try:
            with httpx.Client(base_url='http://127.0.0.1:'+str(port), timeout=2,
                              headers={'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1'}) as client:
                status = None
                for _ in range(160):
                    if process.poll() is not None:
                        break
                    try:
                        response = client.get('/api/v1/auth/options')
                        status = response.status_code
                        break
                    except httpx.TransportError:
                        time.sleep(.1)
                if expect_started:
                    assert status == 200, output.read_text()
                yield client, process, status
        finally:
            launch = runtime/'launch.json'
            if launch.exists():
                child = strict(launch.read_bytes())['pid']
                try:
                    os.kill(child, 15)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate(); process.wait(timeout=10)
            assert read_recovery_state(runtime/'recovery-state.json') == 'quarantined'
            (Path('/results')/('server-'+runtime.name+'.log')).write_bytes(output.read_bytes())


def test_actual_nonroot_api_restarts_with_active_document_and_closed_quota(release_env):
    env = release_env
    runtime, proposal = validated(env)
    assert read_recovery_state(runtime/'recovery-state.json') == 'quarantined'
    approved(env, runtime, proposal)
    authorized(env, runtime)
    assert runtime.joinpath('keys/lifecycle_authentication_key_path/key').stat().st_uid == 0
    assert runtime.joinpath('lite/operations.sqlite').stat().st_uid == 10001
    assert not runtime.joinpath('keys/lifecycle_authentication_key_path/key').stat().st_mode & 0o222
    op = env[0][0][3]
    with env[3].connect() as connection:
        email = connection.scalar(text('SELECT email FROM users WHERE id=:id'), {'id': op.user_id})
    env[3].dispose()
    with running(env, runtime, proposal) as (client, process, _):
        response = client.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
        assert response.status_code == 200, response.text
        client.headers['Authorization'] = 'Bearer '+response.json()['session_token']
        response = client.get(f'/api/v1/documents/{env[0][0][4]}/download')
        assert response.status_code == 200, response.text+(runtime/'server.log').read_text()
        assert response.content == env[0][0][-1].read_bytes()
        assert client.get('/api/v1/account').status_code == 200
        assert client.post('/api/v1/auth/register', json=invitation(env[0][0][1])).status_code == 403
        assert client.post('/api/v1/ai/summary', json={}).status_code in (403, 404)
        launch = strict((runtime/'launch.json').read_bytes())
        uid = Path(f"/proc/{launch['pid']}/status").read_text().split('Uid:')[1].splitlines()[0].split()
        assert uid == ['10001']*4
        Path('/results/release-real-evidence.json').write_bytes(canonical({
            'context': proposal['payload']['operation']['context'], 'operation': proposal['payload']['operation']['operation_id'],
            'uid': uid, 'login': 200, 'download': 200, 'document_sha256': hashlib.sha256(response.content).hexdigest(),
            'quota_closed': True, 'registration': 403, 'ai_enabled': False,
            'status': 'serving_closed', 'opening_authorized': False}))


@pytest.mark.parametrize('bad', ['candidate', 'store', 'permissions', 'document', 'residue', 'quota',
                                'holds', 'identity', 'manifest', 'unfinished', 'admission', 'foreign_key',
                                'cursor', 'cache'])
def test_final_validation_refuses_unsafe_destination(release_env, bad):
    env = release_env
    lab, snapshot, target, engine, _, _ = env
    options = {}
    if bad == 'candidate':
        options['candidate'] = '0'*64
    elif bad == 'store':
        (target/'lifecycle/registry.sqlite').unlink()
    elif bad == 'permissions':
        (target/'documents').chmod(0o777)
    elif bad == 'document':
        (target/'documents'/lab[0][-1].name).unlink()
    elif bad == 'residue':
        (target/'documents/unattributed.txt').write_bytes(b'synthetic')
    elif bad == 'quota':
        with engine.begin() as connection:
            connection.execute(text('UPDATE public_registration_quota SET closed=false'))
    elif bad == 'holds':
        recovery_path = lab[0][2]['dirs']['recovery']/'current.json'
        recovery_path.rename(recovery_path.with_suffix('.unavailable'))
    elif bad == 'identity':
        path = target/'destination.json'; value = strict(path.read_bytes()); value['cohort'] = str(uuid4())
        path.write_bytes(canonical(value))
    elif bad == 'manifest':
        path = snapshot/'manifest.json'; path.write_bytes(path.read_bytes()+b' ')
    elif bad == 'unfinished':
        # A signed result-less recovery authorization is never a release.
        resume_source(lab)
        origin = source_document_deleted(lab)
        inventory(lab, target, snapshot, engine)
        planned(lab, target, snapshot, engine, origin)
    elif bad == 'admission':
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM users'))
    elif bad == 'foreign_key':
        with engine.begin() as connection:
            name = connection.scalar(text("SELECT conname FROM pg_constraint WHERE contype='f' "
                                          "AND conrelid='document_chunks'::regclass LIMIT 1"))
            assert name
            connection.execute(text('ALTER TABLE document_chunks DROP CONSTRAINT "'+name+'"'))
    elif bad == 'cursor':
        (target/'control'/('effect-'+str(uuid4())+'.json')).write_bytes(b'{}')
    elif bad == 'cache':
        cache = release.LocalOperations(target/'lite', 0)
        op = cache.all()[0]
        op.invitation_digest = 'e'*64; op.email_digest = 'f'*64; op.id = uuid4()
        cache.save(op)
    with pytest.raises((AuthorityError, OSError, ValueError)):
        validated(env, **options)
    assert read_recovery_state(target/'recovery-state.json') == 'quarantined'


@pytest.mark.parametrize('bad', ['no_approval', 'forgery', 'old_bound', 'old_challenge', 'changed_document',
                                'changed_sql', 'changed_store', 'wrong_destination', 'symlink', 'wrong_gid'])
def test_release_authorization_is_current_exact_and_not_automatic(release_env, bad):
    env = release_env
    lab, snapshot, target, engine, _, _ = env
    runtime, proposal = validated(env)
    if bad != 'no_approval':
        approved(env, runtime, proposal)
    current = consult(lab, target, snapshot, engine)
    if bad == 'forgery':
        current['signature'] = '0'*128
    elif bad == 'old_bound':
        current = strict((target/'control/accepted.json').read_bytes())
    elif bad == 'old_challenge':
        consult(lab, target, snapshot, engine)
    elif bad == 'changed_document':
        (runtime/'documents'/lab[0][-1].name).write_bytes(b'modified synthetic')
    elif bad == 'changed_sql':
        with engine.begin() as connection:
            connection.execute(text("UPDATE users SET username='changed'"))
    elif bad == 'changed_store':
        (runtime/'registry/registry.sqlite').chmod(0o644)
    elif bad == 'wrong_destination':
        p = target/'destination.json'; d = strict(p.read_bytes()); d['destination'] = str(uuid4()); p.write_bytes(canonical(d))
    elif bad == 'symlink':
        path = runtime/'documents'/lab[0][-1].name
        path.unlink(); path.symlink_to(lab[0][-1])
    elif bad == 'wrong_gid':
        os.chown(runtime/'documents', 10001, 10002)
    with pytest.raises((AuthorityError, OSError, ValueError)):
        release.authorize(target, snapshot, engine, current, runtime,
            confirmation=strict((target/'destination.json').read_bytes())['destination'], offline_confirmed=True)
    assert read_recovery_state(runtime/'recovery-state.json') == 'quarantined'


def test_release_cannot_be_replayed_and_restart_needs_new_validation(release_env):
    env = release_env
    runtime, proposal = validated(env)
    approved(env, runtime, proposal); authorized(env, runtime)
    with pytest.raises(AuthorityError):
        authorized(env, runtime)
    with running(env, runtime, proposal):
        pass
    with pytest.raises(AuthorityError):
        release.serve(runtime, confirmation=proposal['payload']['operation']['operation_id'], port=14099)


@pytest.mark.parametrize('point', ['remap', 'manifest', 'transition', 'startup'])
def test_interrupted_release_stays_closed(release_env, monkeypatch, point):
    env = release_env
    if point == 'remap':
        original = os.chown
        def broken(path, uid, gid):
            original(path, uid, gid)
            if uid == 10001:
                raise OSError('synthetic remap interruption')
        with monkeypatch.context() as patch:
            patch.setattr(os, 'chown', broken)
            with pytest.raises(OSError):
                validated(env)
        assert all(read_recovery_state(p/'recovery-state.json') == 'quarantined'
                   for p in env[4].glob('runtime-*'))
        return
    runtime, proposal = validated(env)
    approved(env, runtime, proposal)
    if point == 'startup':
        authorized(env, runtime)
        (runtime/'holds/holds.sqlite').unlink()
        with running(env, runtime, proposal, expect_started=False) as (_, _, status):
            assert status is None
        return
    original = release.write
    def broken(path, *args, **kwargs):
        if (point == 'manifest' and path.name == 'manifest.json'
                or point == 'transition' and path.name == 'release-state.json'):
            raise OSError('synthetic preparation interruption')
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(release, 'write', broken)
        with pytest.raises(OSError):
            authorized(env, runtime)
    assert read_recovery_state(runtime/'recovery-state.json') == 'quarantined'
    with pytest.raises(AuthorityError):
        authorized(env, runtime)


@pytest.mark.parametrize('outcome', ['no_effect', 'effect_verified', 'contradictory'])
def test_signed_obsolete_plan_resolution_does_not_invent_effects(laboratory, outcome):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        old = planned(lab, target, snapshot, engine, origin)
        if outcome == 'effect_verified':
            applied(lab, target, snapshot, engine, old, complete=False)
        elif outcome == 'contradictory':
            (target/'documents'/lab[0][-1].name).write_bytes(b'contradictory synthetic identity')
        inventory(lab, target, snapshot, engine)
        if outcome == 'contradictory':
            with pytest.raises(AuthorityError):
                release.resolve_obsolete(target, snapshot, engine, consult(lab, target, snapshot, engine),
                    old['operation_id'], confirmation=old['operation_id'],
                    export_key=lab[0][2]['export'], offline_confirmed=True)
            assert (target/'documents'/lab[0][-1].name).exists()
            return
        assert 'reapplication_result_unconfirmed' in diagnosis(lab, target, snapshot, engine)['reasons']
        current = consult(lab, target, snapshot, engine)
        proposal = release.resolve_obsolete(target, snapshot, engine, current, old['operation_id'],
            confirmation=old['operation_id'], export_key=lab[0][2]['export'], offline_confirmed=True)
        assert proposal['payload']['operation']['outcome'] == outcome
        assert (target/'documents'/lab[0][-1].name).exists() is (outcome == 'no_effect')
        lab[0][2]['ledger'].approve(proposal, confirmation=proposal['payload']['operation']['operation_id'],
                                  reference='synthetic-obsolete-plan-resolution')
        if outcome == 'no_effect':
            op = planned(lab, target, snapshot, engine, origin)
            applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
        with pytest.raises(AuthorityError):
            applied(lab, target, snapshot, engine, old)
    finally:
        engine.dispose()


def test_nonroot_cannot_validate_or_authorize():
    if os.name == 'posix' and os.geteuid() == 0:
        with release.api_identity(10001, 10001, '/tmp/not-used'):
            with pytest.raises(AuthorityError):
                release.laboratory('/never', '/never', None)
    elif os.name != 'posix':
        with pytest.raises(AuthorityError):
            release.laboratory('/never', '/never', None)


def test_real_reconciled_purge_closure_and_pending_restriction_survive_http_restart(laboratory):
    from backend.lite_deletions import prepare_request
    from tests.test_lite_deletions import confirm, effect
    lab = laboratory
    active = enroll(lab)
    closed = enroll(lab)
    source = lab[0][1]
    raw = b'Synthetic active content surviving the entire recovery.'
    paths = []
    with source.state.sessions() as session:
        active_email = session.get(User, active.user_id).email
        closed_email = session.get(User, closed.user_id).email
        purged_email = session.get(User, lab[0][3].user_id).email
        for _ in range(2):
            path = source.state.settings.storage_dir/(uuid4().hex+'.txt')
            path.write_bytes(raw); path.chmod(0o600)
            doc = Document(owner_id=active.owner_id, filename='synthetic.txt', storage_name=path.name,
                           media_type='text/plain', size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            session.add(doc); session.flush()
            paths.append((doc.id, path))
        session.commit()
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    _, purge = source_purged(lab)
    with source.state.sessions() as session:
        closure = prepare_request(session, source.state.settings, lab[0][2]['adapter'],
                                  session.get(User, closed.user_id))
    closure = next(o for o in lab[0][2]['store'].deletions() if o.operation_id == closure['operation_id'])
    confirm(lab[0], closure, 'authorize'); effect(lab[0], closure); confirm(lab[0], closure, 'complete')
    with source.state.sessions() as session:
        pending = prepare_request(session, source.state.settings, lab[0][2]['adapter'],
                                  session.get(User, active.user_id), session.get(Document, paths[1][0]))
    pending = next(o for o in lab[0][2]['store'].deletions() if o.operation_id == pending['operation_id'])
    confirm(lab[0], pending, 'authorize'); effect(lab[0], pending); confirm(lab[0], pending, 'complete')
    target, engine, _ = restored(lab, snapshot, checksum)
    public = Path('/tmp')/('lite-release-full-'+uuid4().hex)
    public.mkdir(mode=0o755)
    (public/LAB_MARKER).write_bytes(LAB_MARKER_CONTENT); (public/LAB_MARKER).chmod(0o644)
    settings = source.state.settings.model_copy(update={
        'database_url': engine.url.render_as_string(hide_password=False), 'extraction_mode': 'sandbox'})
    env = lab, snapshot, target, engine, public, settings
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, purge)
        applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
        runtime, proposal = validated(env)
        approved(env, runtime, proposal); authorized(env, runtime)
        with running(env, runtime, proposal) as (client, _, _):
            for email in (purged_email, closed_email):
                assert client.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD}).status_code == 401
            logged = client.post('/api/v1/auth/login', json={'email': active_email, 'password': PASSWORD})
            assert logged.status_code == 200, logged.text
            client.headers['Authorization'] = 'Bearer '+logged.json()['session_token']
            assert client.get(f'/api/v1/documents/{paths[0][0]}/download').content == raw
            assert client.get(f'/api/v1/documents/{paths[1][0]}/download').status_code == 410
            assert client.get(f'/api/v1/documents/{lab[0][4]}/download').status_code != 200
            assert client.post('/api/v1/auth/register', json=invitation(source)).status_code == 403
            client.headers['Authorization'] = 'Bearer '+lab[0][0].headers['Authorization'].removeprefix('Bearer ')
            assert client.get('/api/v1/account').status_code == 401
            denied = subprocess.run([sys.executable, '-c',
                'import sys;from pathlib import Path;p=Path(sys.argv[1]);p.write_bytes(p.read_bytes())',
                str(runtime/'manifest.json')], user=10001, group=10001, extra_groups=[], capture_output=True)
            assert denied.returncode != 0 and b'PermissionError' in denied.stderr
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT issued_count FROM public_registration_quota')) == 3
            assert connection.scalar(text('SELECT count(*) FROM users')) == 2
        Path('/results/release-lifecycle-evidence.json').write_bytes(canonical({
            'context': proposal['payload']['operation']['context'], 'purged_login': 401, 'closed_login': 401,
            'active_login': 200, 'active_download_sha256': hashlib.sha256(raw).hexdigest(), 'restricted_download': 410,
            'registration': 403, 'issued_count': 3, 'users_after_purge': 2, 'root_manifest_write_refused': True,
            'historical_purge_unchanged': operation_payload(purge) == lab[0][2]['ledger'].recover()['events'][
                next(i for i,e in enumerate(lab[0][2]['ledger'].recover()['events'])
                     if e['request']['operation']['operation_id'] == purge.operation_id)]['request']['operation']}))
    finally:
        engine.dispose()


def test_live_quota_or_latch_change_cannot_open_serving_api(release_env):
    env = release_env
    runtime, proposal = validated(env)
    approved(env, runtime, proposal); authorized(env, runtime)
    with running(env, runtime, proposal) as (client, _, _):
        with env[3].begin() as connection:
            connection.execute(text('UPDATE public_registration_quota SET closed=false'))
        assert client.get('/api/v1/auth/options').status_code == 503
        assert client.post('/api/v1/auth/register', json={}).status_code == 503
        with env[3].begin() as connection:
            connection.execute(text('UPDATE public_registration_quota SET closed=true'))
        release.state(runtime, 'ready')
        assert client.get('/api/v1/auth/options').status_code == 503


def test_lost_supervisor_closes_http_and_rejects_reuse(release_env):
    env = release_env
    runtime, proposal = validated(env)
    approved(env, runtime, proposal); authorized(env, runtime)
    with running(env, runtime, proposal) as (client, process, _):
        process.kill(); process.wait(timeout=10)
        assert client.get('/api/v1/auth/options').status_code == 503
        with pytest.raises(AuthorityError):
            release.serve(runtime, confirmation=proposal['payload']['operation']['operation_id'], port=14099)
        # A dead root supervisor cannot rewrite a root latch. Explicit root
        # rollback is needed, while the orphan API already denies every request.
        release.state(runtime, 'quarantined')
