"""Network-free ASGI campaign. Run with qualification/quarantine_inprocess/pytest.ini."""
import asyncio
from collections import Counter
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

import httpx
import pytest


if "tests.conftest" in sys.modules or "conftest" in sys.modules:
    raise RuntimeError("Use the standalone --noconftest profile; application fixtures are forbidden")


class NoSocketLoop(asyncio.SelectorEventLoop):
    """Single-thread test loop: no self-pipe socket and no cross-thread callbacks."""
    def _make_self_pipe(self):
        pass

    def _close_self_pipe(self):
        pass

    def _write_to_self(self):
        raise AssertionError("Cross-thread event-loop scheduling is forbidden")


class NoIOSelector(selectors.SelectSelector):
    def select(self, timeout=None):
        if self.get_map():
            raise AssertionError("The test loop must not register any I/O descriptor")
        if timeout:
            time.sleep(timeout)
        return []


def run(coroutine):
    loop = NoSocketLoop(selector=NoIOSelector())
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def write_state(path, state):
    path.write_text(json.dumps({"format": 1, "state": state}), encoding="utf-8")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    if "backend.main" in sys.modules:
        pytest.fail("backend.main was imported before isolation; refusing to reuse its global app")
    effects = Counter()
    unexpected = []

    def forbidden(label):
        def fail(*args, **kwargs):
            unexpected.append(label)
            raise AssertionError("Unexpected isolated dependency: " + label)
        return fail

    monkeypatch.setattr(socket, "socket", forbidden("socket"))
    monkeypatch.setattr(socket, "create_connection", forbidden("network"))
    monkeypatch.setattr(subprocess, "Popen", forbidden("subprocess"))
    monkeypatch.setattr(threading.Thread, "start", forbidden("real_thread"))
    monkeypatch.setattr(platform, "machine", lambda: "synthetic-inprocess")

    # No settings source may read host variables or a dotenv file.
    with patch.dict(os.environ, {}, clear=True):
        import sqlalchemy
        import psycopg
        import sqlite3
        import smtplib
        import openai
        from alembic import command
        from backend import config, db, security_audit

        monkeypatch.setattr(sqlalchemy, "create_engine", forbidden("real_engine"))
        monkeypatch.setattr(psycopg, "connect", forbidden("postgres"))
        monkeypatch.setattr(sqlite3, "connect", forbidden("sqlite"))
        monkeypatch.setattr(smtplib, "SMTP", forbidden("smtp"))
        monkeypatch.setattr(smtplib, "SMTP_SSL", forbidden("smtp_ssl"))
        monkeypatch.setattr(openai, "OpenAI", forbidden("ai"))
        monkeypatch.setattr(openai, "AsyncOpenAI", forbidden("async_ai"))
        monkeypatch.setattr(command, "upgrade", forbidden("migration"))
        monkeypatch.setattr(command, "downgrade", forbidden("migration"))
        monkeypatch.setattr(security_audit, "emit", lambda *a, **k: effects.update(["audit"]))

        class SyntheticSettings(config.Settings):
            @classmethod
            def settings_customise_sources(cls, settings_cls, init_settings, **kwargs):
                return (init_settings,)

        latch = tmp_path / "configured-latch.json"
        write_state(latch, "quarantined")

        def settings(**overrides):
            values = dict(
                _env_file=None, database_url="sqlite:///:memory:",
                api_keys={"synthetic-quarantine-api-key-00000001": UUID(int=1)},
                bff_service_key="synthetic-bff-key-0000000000000000001",
                recovery_state_path=latch, storage_dir=tmp_path / "documents",
                extraction_mode="development", ai_enabled=True,
                smtp_host="synthetic.invalid",
            )
            values.update(overrides)
            return SyntheticSettings(**values)

        monkeypatch.setattr(config, "Settings", settings)

        def make_engine(*args):
            effects["engine_factory"] += 1
            return SimpleNamespace(
                connect=forbidden("db_connect"), begin=forbidden("db_begin"),
                execute=forbidden("db_execute"),
                dispose=lambda: effects.update(["engine_dispose"]),
            )

        monkeypatch.setattr(db, "make_engine", make_engine)
        monkeypatch.setattr(db, "make_authentication_engine", lambda url, engine: engine)
        monkeypatch.setattr(db, "make_sessions", lambda engine: forbidden("session"))

        long_summary = importlib.import_module("backend.ai.long_summary")
        indexing = importlib.import_module("backend.rag.indexing")
        monkeypatch.setattr(long_summary, "recover", lambda app: effects.update(["summary_recover"]))
        monkeypatch.setattr(indexing, "recover_jobs", lambda app: effects.update(["index_recover"]))

        class ThreadSpy:
            def __init__(self, *args, **kwargs):
                self.target = kwargs.get("target")

            def start(self):
                effects["thread_start"] += 1

            def join(self, *args):
                effects["thread_join"] += 1

        class WorkerSpy:
            def __init__(self, app):
                self.thread = SimpleNamespace(start=lambda: effects.update(["summary_start"]))

            def stop(self):
                effects["summary_stop"] += 1

            submit = forbidden("job")

        monkeypatch.setattr(long_summary, "SummaryWorker", WorkerSpy)
        module = importlib.import_module("backend.main")
        recovery = importlib.import_module("backend.recovery_quarantine")
        audit = importlib.import_module("backend.audit_middleware")
        monkeypatch.setattr(recovery, "emit", security_audit.emit)
        monkeypatch.setattr(audit, "emit", security_audit.emit)
        monkeypatch.setattr(module, "threading", SimpleNamespace(
            Thread=ThreadSpy, BoundedSemaphore=threading.BoundedSemaphore, Event=threading.Event))

        async def inline(function, *args):
            return function(*args)

        class TaskSpy:
            def cancel(self):
                effects["cleanup_cancel"] += 1

            def __await__(self):
                async def done():
                    return None
                return done().__await__()

        def schedule(coroutine):
            effects["cleanup_schedule"] += 1
            coroutine.close()
            return TaskSpy()

        monkeypatch.setattr(module, "asyncio", SimpleNamespace(
            to_thread=inline, create_task=schedule, CancelledError=asyncio.CancelledError,
            sleep=forbidden("cleanup_body")))

        account = importlib.import_module("backend.account_api")
        authentication = importlib.import_module("backend.authentication")
        documents = importlib.import_module("backend.services.documents")
        for name in ("send_reset", "send_verification"):
            monkeypatch.setattr(account, name, forbidden("email"))
        monkeypatch.setattr(authentication, "authenticate", forbidden("auth"))
        monkeypatch.setattr(documents, "open_document_source", forbidden("document"))

        @contextmanager
        def app_factory(**overrides):
            app = module.create_app(settings(**overrides))
            yield app

        try:
            yield SimpleNamespace(
                module=module, settings=settings, app_factory=app_factory, latch=latch,
                effects=effects, unexpected=unexpected, forbidden=forbidden, root=tmp_path,
            )
        finally:
            sys.modules.pop("backend.main", None)
            import backend
            if hasattr(backend, "main"):
                delattr(backend, "main")
            assert not unexpected, "Isolation violations: " + repr(unexpected)


async def request(app, method, path, *, authenticated=False):
    consumed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            consumed.append(True)
            yield b"synthetic request body"

    headers = {
        "x-api-key": app.state.settings.bff_service_key.get_secret_value(),
        "x-documind-secure": "1",
        "authorization": "Bearer synthetic-session",
    } if authenticated else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://inprocess.invalid",
    ) as client:
        response = await client.request(method, path, headers=headers, content=Body())
    return response, consumed


def registered_routes(app):
    def flatten(routes):
        for route in routes:
            if hasattr(route, "effective_candidates"):
                yield from flatten(route.effective_candidates())
            elif getattr(route, "path", None) is not None:
                yield route
            else:
                raise AssertionError("Unknown route inventory representation")
    return list(flatten(app.routes))


def quarantine_route_cases(app):
    cases = []
    for route in registered_routes(app):
        path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", route.path)
        methods = getattr(route, "methods", None)
        if not methods:
            raise AssertionError("Uncovered non-HTTP route: " + route.path)
        cases.extend((method, path) for method in sorted(methods))
    return cases


def poison_routes(app, forbidden):
    # A downstream tripwire, never a replacement of the actual security middleware.
    class RoutingTripwire:
        def __init__(self, original):
            self.original = original

        def __getattr__(self, name):
            return getattr(self.original, name)

        async def __call__(self, scope, receive, send):
            forbidden("endpoint_or_dependency")()

    app.router = RoutingTripwire(app.router)


INVALID_STATES = [
    "quarantined", "missing", "unreadable", "invalid_json", "invalid_utf8",
    "duplicate", "extra", "boolean_format", "unknown", "oversized", "directory", "unconfigured",
]


def set_latch_state(h, monkeypatch, state):
    if state == "quarantined":
        write_state(h.latch, "quarantined")
    elif state == "missing":
        h.latch.unlink()
    elif state == "directory":
        h.latch.unlink()
        h.latch.mkdir()
    elif state == "unreadable":
        from backend import recovery_quarantine
        original = recovery_quarantine.os.open

        def denied(path, *args, **kwargs):
            if Path(path).absolute() == h.latch:
                raise PermissionError("synthetic unreadable latch")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(recovery_quarantine.os, "open", denied)
    else:
        invalid = {
            "invalid_json": b"not-json", "invalid_utf8": b"\xff",
            "duplicate": b'{"format":1,"state":"ready","state":"quarantined"}',
            "extra": b'{"format":1,"state":"ready","extra":true}',
            "boolean_format": b'{"format":true,"state":"ready"}',
            "unknown": b'{"format":1,"state":"unknown"}', "oversized": b"x" * 1025,
        }
        if state in invalid:
            h.latch.write_bytes(invalid[state])


@pytest.mark.parametrize("state", INVALID_STATES)
@pytest.mark.parametrize("authenticated", [False, True])
def test_all_registered_routes_fail_closed(harness, monkeypatch, record_property, state, authenticated):
    h = harness
    set_latch_state(h, monkeypatch, state)
    with h.app_factory(recovery_state_path=None if state == "unconfigured" else h.latch) as app:
        cases = quarantine_route_cases(app)
        modules = {getattr(route.endpoint, "__module__", "") for route in registered_routes(app)}
        assert {
            "backend.api", "backend.account_api", "backend.ai.api",
            "backend.ai.settings_api", "backend.ai.long_api", "backend.rag.api",
        } <= modules
        assert "backend.account_admin" not in modules, "New HTTP admin surface needs explicit coverage"
        record_property("registered_route_methods", len(cases))
        record_property("registered_router_modules", ",".join(sorted(modules)))
        cases += [("GET", "/api/v1/admin"), ("GET", "/not-registered"), ("OPTIONS", "/api/v1/documents")]
        poison_routes(app, h.forbidden)

        async def scenario():
            async with app.router.lifespan_context(app):
                assert app.state.recovery_ready_at_start is False
                for method, path in cases:
                    response, consumed = await request(app, method, path, authenticated=authenticated)
                    assert response.status_code == 503, (method, path, response.status_code)
                    if method == "HEAD":
                        assert not response.content
                    else:
                        assert "quarantaine" in response.json()["detail"]
                    assert not consumed

        run(scenario())
        assert not (h.root / "documents").exists()
        assert app.state.mail_queue.empty()
        assert not h.effects.keys() & {
            "summary_recover", "index_recover", "summary_start", "thread_start", "cleanup_schedule",
        }


@pytest.mark.parametrize("state", INVALID_STATES)
def test_ready_process_refuses_new_requests_after_latch_failure(harness, monkeypatch, state):
    h = harness
    write_state(h.latch, "ready")
    with h.app_factory() as app:
        cases = quarantine_route_cases(app)
        poison_routes(app, h.forbidden)

        async def scenario():
            async with app.router.lifespan_context(app):
                assert app.state.recovery_ready_at_start is True
                set_latch_state(h, monkeypatch, state)
                if state == "unconfigured":
                    app.state.settings.recovery_state_path = None
                for method, path in cases:
                    response, consumed = await request(app, method, path, authenticated=True)
                    assert response.status_code == 503
                    assert not consumed
        run(scenario())


def test_lite_boundary_denies_before_quarantine(harness):
    h = harness
    settings = h.settings(
        application_profile="beta_lite", registration_mode="invite",
        public_registration_limit=5, ai_enabled=False, owner_demo_enabled=False,
        legacy_api_enabled=False, api_keys={}, lite_cohort_id=UUID(int=2),
        lite_terms_sha256="a" * 64, bff_service_key="synthetic-bff-key-0000000000000000001",
        public_legal_ready=True, public_operator_name="Synthetic",
        public_contact_email="lab@example.invalid", public_terms_version="synthetic",
        smtp_from="lab@example.invalid", public_legal_notice_url="https://example.invalid/legal",
        public_privacy_url="https://example.invalid/privacy", public_terms_url="https://example.invalid/terms",
    )
    # Prevent any provisioned-authority read; the real config and HTTP guards stay active.
    app = h.module.create_app(settings, lite_confirmation=object())
    poison_routes(app, h.forbidden)

    async def scenario():
        async with app.router.lifespan_context(app):
            for path, expected in [
                ("/api/v1/ai/status", 403), ("/api/v1/search/semantic", 403),
                ("/api/v1/auth/verify-email", 403), ("/api/v1/health", 503),
                ("/api/v1/auth/register", 503), ("/api/v1/account", 503),
            ]:
                response, consumed = await request(app, "POST", path)
                assert response.status_code == expected
                assert not consumed
    run(scenario())


@pytest.mark.parametrize("initial", ["quarantined", "ready"])
def test_transitions_and_positive_worker_control(harness, initial):
    h = harness
    write_state(h.latch, initial)
    with h.app_factory() as app:
        @app.get("/synthetic-probe", include_in_schema=False)
        async def probe():
            h.effects["probe"] += 1
            return {"synthetic": True}

        async def scenario():
            async with app.router.lifespan_context(app):
                assert app.state.recovery_ready_at_start is (initial == "ready")
                for state in ["ready", "quarantined", "ready"]:
                    write_state(h.latch, state)
                    response, _ = await request(app, "GET", "/synthetic-probe")
                    assert response.status_code == (200 if initial == "ready" and state == "ready" else 503)
                if initial == "ready":
                    assert all(h.effects[name] == 1 for name in (
                        "summary_recover", "index_recover", "summary_start", "thread_start", "cleanup_schedule"))
                else:
                    assert not h.effects.keys() & {
                        "summary_recover", "index_recover", "summary_start", "thread_start", "cleanup_schedule",
                    }
        run(scenario())
        assert h.effects["probe"] == (2 if initial == "ready" else 0)
        assert h.effects["summary_stop"] == (1 if initial == "ready" else 0)


def test_configured_path_not_decoy_is_read(harness, monkeypatch):
    h = harness
    from backend import recovery_quarantine
    decoy = h.root / "decoy.json"
    write_state(decoy, "ready")
    monkeypatch.setenv("RECOVERY_STATE_PATH", str(decoy))
    opened = []
    original = recovery_quarantine.os.open

    def observed(path, *args, **kwargs):
        opened.append(Path(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(recovery_quarantine.os, "open", observed)
    with h.app_factory() as app:
        async def scenario():
            async with app.router.lifespan_context(app):
                response, _ = await request(app, "GET", "/api/v1/health")
                assert response.status_code == 503
        run(scenario())
    assert opened == [h.latch, h.latch]
    assert decoy not in opened


def test_downstream_tripwire_has_a_ready_positive_control(harness):
    h = harness
    write_state(h.latch, "ready")
    reached = Mock()
    with h.app_factory() as app:
        poison_routes(app, lambda label: lambda: reached(label))

        # A harmless downstream replacement returns a deliberate response, no endpoint runs.
        original = app.router

        class PositiveTripwire:
            def __getattr__(self, name):
                return getattr(original, name)

            async def __call__(self, scope, receive, send):
                reached("router")
                from starlette.responses import Response
                await Response(status_code=204)(scope, receive, send)

        app.router = PositiveTripwire()

        async def scenario():
            async with app.router.lifespan_context(app):
                response, _ = await request(app, "GET", "/api/v1/health")
                assert response.status_code == 204
                reached.assert_called_once_with("router")
        run(scenario())


def test_admitted_work_is_not_cancelled_when_new_request_is_denied(harness):
    h = harness
    write_state(h.latch, "ready")
    with h.app_factory() as app:
        async def scenario():
            admitted, finish = asyncio.Event(), asyncio.Event()

            @app.get("/synthetic-inflight", include_in_schema=False)
            async def work():
                admitted.set()
                await finish.wait()
                h.effects["inflight_completed"] += 1
                return {"completed": True}

            async with app.router.lifespan_context(app):
                first = asyncio.create_task(request(app, "GET", "/synthetic-inflight"))
                await asyncio.wait_for(admitted.wait(), 2)
                write_state(h.latch, "quarantined")
                response, consumed = await request(app, "GET", "/synthetic-inflight")
                assert response.status_code == 503 and not consumed
                assert not first.done()
                finish.set()
                response, _ = await asyncio.wait_for(first, 2)
                assert response.status_code == 200
                assert h.effects["inflight_completed"] == 1
        run(scenario())
