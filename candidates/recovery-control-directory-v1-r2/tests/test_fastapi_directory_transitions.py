"""Synthetic atomic replacements only. The restored latch is never opened."""
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from tests.test_recovery_quarantine_inprocess import (
    harness, quarantine_route_cases, registered_routes, request, run,
)

WORKERS = {'summary_recover', 'index_recover', 'summary_start', 'thread_start', 'cleanup_schedule'}
MIDDLEWARES = ['LiteBoundary', 'RecoveryQuarantine', 'SecurityAudit',
               'IPAdmission', 'UploadAdmission', 'RequestSizeLimit']


def atomic_synthetic(path, payload):
    temporary = path.with_name('.synthetic-publication.tmp')
    with temporary.open('xb') as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def payload(state):
    return json.dumps({'format': 1, 'state': state}).encode()


def lite_blocked(path):
    path = path.rstrip('/')
    return (any(part in path for part in (
        '/ai', '/rag', '/byok', '/library', '/compare', '/comparisons',
        '/embeddings', '/search', '/summary-jobs',
    )) or path.endswith((
        '/index', '/summarize', '/summaries', '/ask', '/summary-plan',
        '/resend-verification', '/verify-email',
    )))


def tripwire(app, reached):
    app.middleware_stack = app.build_middleware_stack()
    current = app.middleware_stack
    while getattr(current, 'app', None) is not app.router:
        current = getattr(current, 'app', None)
        assert current is not None

    class BeforeRealRouter:
        def __init__(self, original):
            self.app = original

        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http':
                reached.append(scope['path'])
                raise AssertionError('synthetic downstream sentinel')
            return await self.app(scope, receive, send)

    current.app = BeforeRealRouter(app.router)


def application(h, latch, profile):
    values = {'recovery_state_path': latch}
    if profile == 'beta_lite':
        values.update(
            application_profile=profile, registration_mode='invite',
            public_registration_limit=5, ai_enabled=False, owner_demo_enabled=False,
            legacy_api_enabled=False, api_keys={}, lite_cohort_id=UUID(int=2),
            lite_terms_sha256='a' * 64, public_legal_ready=True,
            public_operator_name='Synthetic', public_contact_email='lab@example.invalid',
            public_terms_version='synthetic', smtp_from='lab@example.invalid',
            public_legal_notice_url='https://example.invalid/legal',
            public_privacy_url='https://example.invalid/privacy',
            public_terms_url='https://example.invalid/terms',
        )

    class NoAuthority:
        def __getattr__(self, name):
            h.forbidden('authority:' + name)()

    settings = h.settings(**values)
    app = h.module.create_app(settings, lite_confirmation=NoAuthority())
    assert app.state.settings is settings
    assert app.state.settings.recovery_state_path == latch
    assert [item.cls.__name__ for item in app.user_middleware] == MIDDLEWARES
    return app


FAILURES = {
    'quarantined': payload('quarantined'), 'ready': payload('ready'),
    'missing': None, 'invalid-json': b'not-json', 'invalid-utf8': b'\xff',
    'duplicate': b'{"format":1,"state":"ready","state":"quarantined"}',
    'boolean': b'{"format":true,"state":"ready"}',
    'unknown': payload('unknown'), 'extra': b'{"format":1,"state":"ready","extra":true}',
    'oversized': b'x' * 1025,
}


@pytest.mark.parametrize('initial', ['ready', 'quarantined'])
@pytest.mark.parametrize('profile', ['standard', 'beta_lite'])
@pytest.mark.parametrize('failure', FAILURES)
def test_real_fastapi_after_atomic_publication(
    harness, monkeypatch, record_property, initial, profile, failure,
):
    h = harness
    directory = h.root / 'recovery-control'
    directory.mkdir()
    latch = directory / 'recovery-state.json'
    atomic_synthetic(latch, payload(initial))
    directory_identity = directory.stat().st_ino
    before_inode = latch.stat().st_ino
    app = application(h, latch, profile)
    reached, reads = [], []
    tripwire(app, reached)
    original_open = os.open

    def observe(path, flags, *args, **kwargs):
        if not isinstance(path, int) and Path(path).absolute() == latch:
            assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            reads.append(str(path))
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', observe)
    cases = quarantine_route_cases(app)
    inventory = sorted((method, route.path) for route in registered_routes(app) for method in route.methods)
    assert {('GET', '/api/v1/health'), ('POST', '/api/v1/auth/login'),
            ('POST', '/api/v1/auth/register'), ('GET', '/api/v1/documents'),
            ('GET', '/docs'), ('GET', '/redoc'), ('GET', '/openapi.json')} <= set(inventory)
    record_property('registered_http', json.dumps(inventory))
    record_property('registered_administration', json.dumps([
        row for row in inventory if 'admin' in row[1].lower()]))
    outcomes = {}

    async def scenario():
        async with app.router.lifespan_context(app):
            assert reads == [str(latch)], 'startup must read the configured child'
            assert app.state.recovery_ready_at_start is (initial == 'ready')
            started = {name: h.effects[name] for name in WORKERS}
            if initial == 'quarantined':
                assert not any(started.values())
            else:
                assert started['thread_start'] == started['cleanup_schedule'] == 1
                assert started['summary_start'] == (profile == 'standard')
            if FAILURES[failure] is None:
                latch.unlink()
            else:
                atomic_synthetic(latch, FAILURES[failure])
                assert latch.stat().st_ino != before_inode
                record_property('published_sha256', hashlib.sha256(latch.read_bytes()).hexdigest())
            assert directory.stat().st_ino == directory_identity
            # Only the synthetic initially-ready process may reopen. Never a real latch.
            if initial == 'ready' and failure == 'ready':
                response, _ = await request(app, 'GET', '/api/v1/health', authenticated=True)
                assert response.status_code == 500 and reached == ['/api/v1/health']
            else:
                for authenticated in (False, True):
                    for method, path in cases:
                        count = len(reads)
                        response, consumed = await request(app, method, path, authenticated=authenticated)
                        expected = 403 if profile == 'beta_lite' and lite_blocked(path) else 503
                        assert response.status_code == expected, (method, path, response.status_code)
                        assert len(reads) == count + (expected == 503)
                        assert not consumed
                        outcomes[str(expected)] = outcomes.get(str(expected), 0) + 1
                assert not reached
            assert started == {name: h.effects[name] for name in WORKERS}
            assert app.state.mail_queue.empty()
    run(scenario())
    record_property('http_outcomes', json.dumps(outcomes))
    assert not h.unexpected


def test_same_ready_process_can_reopen_only_in_synthetic_test(harness):
    h = harness
    latch = h.root / 'runtime-latch.json'
    atomic_synthetic(latch, payload('ready'))
    app = application(h, latch, 'standard')
    reached = []
    tripwire(app, reached)

    async def scenario():
        async with app.router.lifespan_context(app):
            atomic_synthetic(latch, payload('quarantined'))
            response, _ = await request(app, 'GET', '/api/v1/health')
            assert response.status_code == 503 and not reached
            atomic_synthetic(latch, payload('ready'))
            response, _ = await request(app, 'GET', '/api/v1/health')
            assert response.status_code == 500 and reached == ['/api/v1/health']
    run(scenario())


def test_new_synthetic_process_ready_is_a_positive_startup_control(harness):
    h = harness
    latch = h.root / 'runtime-latch.json'
    atomic_synthetic(latch, payload('quarantined'))
    closed = application(h, latch, 'standard')
    closed_reached = []
    tripwire(closed, closed_reached)

    async def scenario():
        async with closed.router.lifespan_context(closed):
            atomic_synthetic(latch, payload('ready'))
            response, _ = await request(closed, 'GET', '/api/v1/health')
            assert response.status_code == 503 and not closed_reached
            assert not any(h.effects[name] for name in WORKERS)
        new = application(h, latch, 'standard')
        reached = []
        tripwire(new, reached)
        async with new.router.lifespan_context(new):
            response, _ = await request(new, 'GET', '/api/v1/health')
            assert response.status_code == 500 and reached == ['/api/v1/health']
            assert all(h.effects[name] == 1 for name in WORKERS)
    run(scenario())
