"""Real HTTP admissions from independent API instances and PostgreSQL connections."""
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager, ExitStack
from queue import Queue
from threading import Barrier, Event
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, func, text

from backend.api import db as database_dependency
from backend.main import create_app
from backend.auth import User, SessionVault
from backend.account_models import PublicRegistrationQuota, Workspace, WorkspaceMembership, AccountToken
from backend.account_admin import registration_control
from tests.conftest import BFF_KEY
from tests.test_public_beta import beta, signup_body, PASSWORD
from tests.test_public_beta_state import new_request


@pytest.fixture
def pg_beta(beta):
    client, app, sent = beta
    if app.state.engine.dialect.name != 'postgresql':
        pytest.skip('Requires a NEW dedicated PostgreSQL 17 test database')
    app.state.settings.public_registration_limit = 5
    return beta


@contextmanager
def actors(beta):
    parent_client, parent, parent_sent = beta
    output = Queue()
    def bounded_database(application):
        def db():
            with application.state.sessions() as session:
                session.execute(text("SET LOCAL lock_timeout='8s'"))
                session.execute(text("SET LOCAL statement_timeout='12s'"))
                yield session
        return db
    with ExitStack() as stack:
        result = []
        for index in range(2):
            app = create_app(parent.state.settings.model_copy())
            app.state.mail_sender = lambda email, token: output.put((email, token))
            app.dependency_overrides[database_dependency] = bounded_database(app)
            client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
            client.headers.update({'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1',
                                   'X-Documind-Client-IP': f'192.0.2.{210 + index}'})
            result.append((client, app))
        assert result[0][1].state.registration_challenges is not result[1][1].state.registration_challenges
        try:
            yield result, output
        finally:
            for _, app in result:
                app.state.engine.dispose()


def seed(beta, count):
    client, app, sent = beta
    for index in range(count):
        email = f'prior-{index}@example.test'
        response = client.post('/api/v1/auth/register', json=new_request(client, email))
        assert response.status_code == 202
        assert sent.get(timeout=3)[0] == email


def counts(app):
    with app.state.sessions() as db:
        return tuple(db.scalar(select(func.count()).select_from(model))
                     for model in (User, Workspace, WorkspaceMembership, AccountToken)) + (db.get(PublicRegistrationQuota, 'public').issued_count,)


def parallel(functions):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(function) for function in functions]
        done, pending = wait(futures, timeout=25)
        assert not pending, 'Bounded concurrent requests did not finish'
        return [future.result() for future in futures]


@contextmanager
def rendezvous(instances, predicate):
    barrier, pids = Barrier(2, timeout=15), []
    def before(connection, cursor, statement, parameters, context, many):
        if predicate(statement):
            pids.append(connection.exec_driver_sql('SELECT pg_backend_pid()').scalar_one())
            barrier.wait()
    for _, app in instances:
        event.listen(app.state.engine, 'before_cursor_execute', before)
    try:
        yield pids
    finally:
        barrier.abort()
        for _, app in instances:
            event.remove(app.state.engine, 'before_cursor_execute', before)


def wait_for_lock(app, pid):
    deadline = time.monotonic() + 5
    while True:
        with app.state.sessions() as db:
            state = db.scalar(text('SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid'), {'pid': pid})
        if state == 'Lock':
            return
        assert time.monotonic() < deadline, 'Expected PostgreSQL lock wait was not observed'
        time.sleep(.01)  # Poll server state; never synchronize by an arbitrary fixed delay.


@pytest.mark.parametrize('same_email', [False, True])
def test_two_real_admissions_are_atomic_without_shared_ram_semaphore(pg_beta, same_email):
    client, parent, sent = pg_beta
    seed(pg_beta, 3 if same_email else 4)
    original = counts(parent)
    with actors(pg_beta) as (instances, output):
        bodies = [signup_body(client, 'shared@example.test' if same_email else f'new-{index}@example.test')
                  for index, (client, _) in enumerate(instances)]
        with rendezvous(instances, lambda sql: sql.startswith('UPDATE public_registration_quota')) as pids:
            responses = parallel([lambda i=i: instances[i][0].post('/api/v1/auth/register', json=bodies[i]) for i in range(2)])
        assert [response.status_code for response in responses] == [202, 202]
        assert responses[0].json() == responses[1].json()
        assert len(pids) == len(set(pids)) == 2
        # Last-slot loser, or duplicate-email rollback: no orphan account/workspace/token.
        assert counts(parent) == tuple(value + 1 for value in original)
        assert output.get(timeout=3)[0].endswith('@example.test')
        assert output.empty()


@pytest.mark.parametrize('operation', ['verify', 'resend'])
def test_email_operations_serialize_on_the_actual_user_row(pg_beta, operation):
    client, parent, sent = pg_beta
    seed(pg_beta, 1)
    with parent.state.sessions() as db:
        user = db.scalar(select(User))
        original_identity = user.id, user.owner_id
        # Raw token is issued only into the fake mail hook; get a fresh one for this operation.
    resend = client.post('/api/v1/auth/resend-verification', json=new_request(client, 'prior-0@example.test'))
    assert resend.status_code == 202
    original_token = sent.get(timeout=3)[1]
    with actors(pg_beta) as (instances, output):
        if operation == 'verify':
            bodies = [{'token': original_token, 'password': PASSWORD}] * 2
            path = '/api/v1/auth/verify-email'
        else:
            bodies = [signup_body(client, 'prior-0@example.test') for client, _ in instances]
            path = '/api/v1/auth/resend-verification'
        with rendezvous(instances, lambda sql: 'FROM users' in sql and sql.rstrip().endswith('FOR UPDATE')) as pids:
            responses = parallel([lambda i=i: instances[i][0].post(path, json=bodies[i]) for i in range(2)])
        assert len(set(pids)) == 2
        assert sorted(response.status_code for response in responses) == ([200, 400] if operation == 'verify' else [202, 202])
        assert all(not app.state.session_vault.sessions for _, app in instances)
        if operation == 'resend':
            tokens = [output.get(timeout=3)[1] for _ in range(2)]
            with parent.state.sessions() as db:
                active = db.scalars(select(AccountToken).where(AccountToken.kind == 'verify', AccountToken.used_at.is_(None))).all()
                assert len(active) == 1
                valid_token = next(token for token in tokens if SessionVault.digest(token) == active[0].digest)
            assert client.post('/api/v1/auth/verify-email', json={'token': original_token, 'password': PASSWORD}).status_code == 400
            stale = next(token for token in tokens if token != valid_token)
            assert client.post('/api/v1/auth/verify-email', json={'token': stale, 'password': PASSWORD}).status_code == 400
            assert client.post('/api/v1/auth/verify-email', json={'token': valid_token, 'password': PASSWORD}).status_code == 200
        with parent.state.sessions() as db:
            user = db.scalar(select(User))
            assert (user.id, user.owner_id) == original_identity and user.email_verified_at is not None
            assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
            assert db.scalar(select(func.count()).select_from(Workspace)) == 1


@pytest.mark.parametrize('admission_first', [True, False])
def test_real_admission_and_emergency_close_have_both_serial_orders(pg_beta, admission_first):
    client, parent, sent = pg_beta
    seed(pg_beta, 4)
    locked, release, waiting = Event(), Event(), Event()
    pids = []
    with actors(pg_beta) as (instances, output):
        http, app = instances[0]
        body = signup_body(http, 'racing@example.test')
        def hold(connection, cursor, sql, params, context, many):
            if sql.startswith('UPDATE public_registration_quota'):
                locked.set()
                assert release.wait(15)
        def record_pid(connection, cursor, sql, params, context, many):
            if sql.startswith('UPDATE public_registration_quota'):
                pids.append(connection.exec_driver_sql('SELECT pg_backend_pid()').scalar_one())
                waiting.set()
        def close():
            with parent.state.sessions() as db:
                db.execute(text("SET LOCAL lock_timeout='8s'"))
                db.execute(text("SET LOCAL statement_timeout='12s'"))
                if admission_first:
                    pids.append(db.scalar(text('SELECT pg_backend_pid()')))
                    waiting.set()
                return registration_control(db, parent.state.settings, 'close', True)
        first_engine = app.state.engine if admission_first else parent.state.engine
        event.listen(first_engine, 'after_cursor_execute', hold)
        if not admission_first:
            event.listen(app.state.engine, 'before_cursor_execute', record_pid)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(lambda: http.post('/api/v1/auth/register', json=body)) if admission_first else pool.submit(close)
                try:
                    assert locked.wait(5)
                    second = pool.submit(close) if admission_first else pool.submit(lambda: http.post('/api/v1/auth/register', json=body))
                    assert waiting.wait(5)
                    wait_for_lock(parent, pids[0])
                finally:
                    release.set()
                one,two=first.result(timeout=20),second.result(timeout=20)
                response,closure=(one,two) if admission_first else (two,one)
                assert response.status_code==202 and closure['closed'] is True
        finally:
            release.set()
            event.remove(first_engine, 'after_cursor_execute', hold)
            if not admission_first:
                event.remove(app.state.engine, 'before_cursor_execute', record_pid)
    with parent.state.sessions() as db:
        quota = db.get(PublicRegistrationQuota, 'public')
        assert quota.closed and quota.issued_count == (5 if admission_first else 4)
        assert db.scalar(select(func.count()).select_from(User)) == quota.issued_count
        assert db.scalar(select(func.count()).select_from(Workspace)) == quota.issued_count


def test_admission_during_uncommitted_reopening_stays_closed_until_retry(pg_beta):
    client, parent, sent = pg_beta
    seed(pg_beta, 4)
    with parent.state.sessions() as db:
        registration_control(db, parent.state.settings, 'close', True)
    locked, release = Event(), Event()
    def hold(connection, cursor, sql, params, context, many):
        if 'FROM public_registration_quota' in sql and sql.rstrip().endswith('FOR UPDATE'):
            locked.set()
            assert release.wait(15)
    def reopen():
        with parent.state.sessions() as db:
            db.execute(text("SET LOCAL statement_timeout='12s'"))
            return registration_control(db, parent.state.settings, 'reopen', True)
    event.listen(parent.state.engine, 'after_cursor_execute', hold)
    try:
        with actors(pg_beta) as (instances, output), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(reopen)
            try:
                assert locked.wait(5)
                http, app = instances[0]
                refused = http.post('/api/v1/auth/register', json=signup_body(http, 'later@example.test'))
                assert refused.status_code == 202 and counts(parent)[-1] == 4 and output.empty()
            finally:
                release.set()
            assert future.result(timeout=20)['issued_count'] == 4
            accepted = http.post('/api/v1/auth/register', json=signup_body(http, 'later@example.test'))
            assert accepted.status_code == 202 and output.get(timeout=3)[0] == 'later@example.test'
    finally:
        release.set()
        event.remove(parent.state.engine, 'after_cursor_execute', hold)
    assert counts(parent)[-1] == 5


def test_rollback_after_reservation_does_not_leave_orphans_or_consume_a_place(pg_beta, monkeypatch):
    from backend import account_api
    client, parent, sent = pg_beta
    seed(pg_beta, 4)
    before = counts(parent)
    original = account_api.issue_token
    def fail(*args, **kwargs):
        raise RuntimeError('Fictitious transaction abort')
    with actors(pg_beta) as (instances, output):
        monkeypatch.setattr(account_api, 'issue_token', fail)
        http, app = instances[0]
        assert http.post('/api/v1/auth/register', json=signup_body(http, 'aborted@example.test')).status_code == 500
        assert counts(parent) == before and output.empty()
        monkeypatch.setattr(account_api, 'issue_token', original)
        assert http.post('/api/v1/auth/register', json=signup_body(http, 'success@example.test')).status_code == 202
        assert output.get(timeout=3)[0] == 'success@example.test'
    assert counts(parent) == tuple(value + 1 for value in before)


def test_pending_administrative_block_and_verification_share_the_user_lock(pg_beta):
    from backend.account_admin import pending_account_control
    from tests.test_public_beta import enroll
    client, parent, sent = pg_beta
    token = enroll(pg_beta)
    with parent.state.sessions() as db:
        identifier = db.scalar(select(User.id))
    def block():
        with parent.state.sessions() as db:
            db.execute(text("SET LOCAL statement_timeout='12s'"))
            try:
                return pending_account_control(db, identifier, 'block', True)
            except ValueError:
                # If verification won the row lock, this pending-only operation must refuse.
                return {'already_verified': True}
    with actors(pg_beta) as (instances, output):
        selected = [instances[0], (client, parent)]
        with rendezvous(selected, lambda sql: 'FROM users' in sql and sql.rstrip().endswith('FOR UPDATE')) as pids:
            response, result = parallel([
                lambda: instances[0][0].post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}), block])
        assert len(set(pids)) == 2
    with parent.state.sessions() as db:
        user = db.get(User, identifier)
        if result.get('blocked'):
            assert response.status_code == 400 and user.email_verified_at is None and user.disabled_at is not None
        else:
            assert result.get('already_verified') and response.status_code == 200 and user.email_verified_at is not None
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
