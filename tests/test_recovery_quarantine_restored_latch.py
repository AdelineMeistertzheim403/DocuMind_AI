"""Real backend.main application; external latch is strictly read-only.

Run only through qualification/restored_latch/run_campaign.py.
The imported harness owns isolation of backend.main's synthetic global app.
"""
import json
import os
from pathlib import Path
import stat

import pytest

from tests.test_recovery_quarantine_inprocess import (
    harness, quarantine_route_cases, registered_routes, request, run, write_state,
)


STARTED = {
    "summary_recover", "index_recover", "summary_start", "thread_start",
    "cleanup_schedule", "summary_stop", "thread_join", "cleanup_cancel",
}
MIDDLEWARES = [
    "LiteBoundary", "RecoveryQuarantine", "SecurityAudit", "IPAdmission",
    "UploadAdmission", "RequestSizeLimit",
]


def snapshot(path):
    import hashlib

    metadata = path.stat()
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mode": stat.S_IMODE(metadata.st_mode), "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns, "inode": metadata.st_ino,
        "device": metadata.st_dev,
    }


def lite_blocked(path):
    # Independent expected HTTP contract, not a call to the middleware under test.
    path = path.rstrip("/")
    return (
        any(part in path for part in (
            "/ai", "/rag", "/byok", "/library", "/compare", "/comparisons",
            "/embeddings", "/search", "/summary-jobs",
        ))
        or path.endswith((
            "/index", "/summarize", "/summaries", "/ask", "/summary-plan",
            "/resend-verification", "/verify-email",
        ))
    )


def install_tripwire(app, reached):
    """Insert immediately before the REAL router, retaining every middleware."""
    app.middleware_stack = app.build_middleware_stack()
    current = app.middleware_stack
    while getattr(current, "app", None) is not app.router:
        current = getattr(current, "app", None)
        assert current is not None, "Real router not found in middleware stack"

    class Tripwire:
        def __init__(self, original):
            self.app = original

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                reached.append(scope["path"])
                raise AssertionError("Business router reached")
            return await self.app(scope, receive, send)

    current.app = Tripwire(app.router)


@pytest.mark.parametrize("profile", ["standard", "beta_lite"])
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("missing", [False, True], ids=["restored", "absent"])
def test_real_fastapi_refuses_new_http(
    harness, monkeypatch, pytestconfig, record_property, profile, authenticated, missing,
):
    h = harness
    campaign = getattr(pytestconfig, "_restored_latch_campaign", None)
    assert campaign is not None, "The secured standalone launcher is required"
    restored = Path(campaign["latch"])
    assert restored.is_absolute()
    before = snapshot(restored)
    assert before["sha256"] == campaign["sha256"]
    assert json.loads(restored.read_bytes()) == {"format": 1, "state": "quarantined"}
    if os.name == "posix":
        assert before["mode"] == 0o600

    # Missing-path case lives only in pytest's scratch space, never by the latch.
    configured = h.root / "absent-latch.json" if missing else restored
    assert not missing or not configured.exists()
    values = dict(recovery_state_path=configured, extraction_mode="sandbox")
    if profile == "beta_lite":
        from uuid import UUID

        values.update(
            application_profile=profile, registration_mode="invite",
            public_registration_limit=5, ai_enabled=False, owner_demo_enabled=False,
            legacy_api_enabled=False, api_keys={}, lite_cohort_id=UUID(int=2),
            lite_terms_sha256="a" * 64, public_legal_ready=True,
            public_operator_name="Synthetic", public_contact_email="lab@example.invalid",
            public_terms_version="synthetic", smtp_from="lab@example.invalid",
            public_legal_notice_url="https://example.invalid/legal",
            public_privacy_url="https://example.invalid/privacy",
            public_terms_url="https://example.invalid/terms",
        )
    settings = h.settings(**values)
    assert settings.recovery_state_path == configured

    # Confirmation is a fail-on-access sentinel, not a real authority/database.
    class NoAuthority:
        def __getattr__(self, name):
            h.forbidden("lite_authority:" + name)()

    app = h.module.create_app(settings, lite_confirmation=NoAuthority())
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    assert app.state.settings is settings
    assert [item.cls.__name__ for item in app.user_middleware] == MIDDLEWARES
    routes = registered_routes(app)
    inventory = sorted(
        (method, route.path, getattr(route.endpoint, "__module__", ""))
        for route in routes for method in route.methods
    )
    registered = {(method, path) for method, path, _ in inventory}
    assert {
        ("GET", "/api/v1/health"), ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/register"), ("GET", "/api/v1/documents"),
        ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"),
    } <= registered
    administration = [
        row for row in inventory
        if "admin" in row[1].lower() or row[2] == "backend.account_admin"
    ]
    record_property("registered_http_inventory", json.dumps(inventory))
    record_property("registered_administration_http", json.dumps(administration))
    record_property("administration_scope", "registered only; no invented admin endpoint")
    cases = quarantine_route_cases(app)
    cases += [("GET", "/not-registered"), ("OPTIONS", "/api/v1/documents")]
    reached, reads, outcomes = [], [], []
    install_tripwire(app, reached)
    original_open = os.open

    def observed(path, flags, *args, **kwargs):
        if not isinstance(path, int) and Path(path).absolute() == configured:
            assert flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) == 0
            entry = {"path": str(path), "flags": flags, "result": "pending"}
            reads.append(entry)
            try:
                descriptor = original_open(path, flags, *args, **kwargs)
            except FileNotFoundError:
                entry["result"] = "absent"
                raise
            entry["result"] = "opened"
            return descriptor
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed)
    # Explicit DNS/API guards supplement the launcher's permanent audit hook.
    import socket

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        monkeypatch.setattr(socket, name, h.forbidden("dns:" + name))
    baseline = h.effects.copy()

    async def scenario():
        assert reads == []
        async with app.router.lifespan_context(app):
            assert app.state.recovery_ready_at_start is False
            assert len(reads) == 1, "Startup must open the explicitly configured path"
            for method, path in cases:
                count = len(reads)
                expected = 403 if profile == "beta_lite" and lite_blocked(path) else 503
                response, consumed = await request(app, method, path, authenticated=authenticated)
                assert response.status_code == expected, (method, path, response.status_code)
                assert not consumed, "A rejected request must not consume its body"
                if method != "HEAD":
                    detail = response.json()["detail"]
                    assert ("Beta Lite" if expected == 403 else "quarantaine") in detail
                assert len(reads) - count == (expected == 503), (
                    "Lite must deny before quarantine; quarantine must read on each 503"
                )
                outcomes.append([method, path, expected])

    try:
        run(scenario())
        assert not reached
        assert not (h.effects - baseline).keys() & STARTED
        assert not app.state.mail_stopping.is_set()
        assert app.state.mail_queue.empty()
        assert not settings.storage_dir.exists()
        assert not getattr(app.state, "recovery_release", None)
        assert all(entry["path"] == str(configured) for entry in reads)
        assert all(entry["result"] == ("absent" if missing else "opened") for entry in reads)
        assert not missing or not configured.exists()
    finally:
        assert snapshot(restored) == before, "Restored latch changed during the scenario"
        record_property("configured_latch", str(configured))
        record_property("recovery_ready_at_start", app.state.recovery_ready_at_start)
        record_property("restored_latch_snapshot", json.dumps(before))
        record_property("latch_reads", json.dumps(reads))
        record_property("http_outcomes", json.dumps(outcomes))
        record_property("downstream_calls", len(reached))
        record_property("started_activity", json.dumps(sorted((h.effects - baseline).keys() & STARTED)))


def test_synthetic_positive_control(harness):
    """Only this harness-owned synthetic latch becomes ready; NEVER the restored one."""
    h = harness
    write_state(h.latch, "ready")
    app = h.module.create_app(h.settings())
    reached = []
    install_tripwire(app, reached)

    async def scenario():
        async with app.router.lifespan_context(app):
            assert app.state.recovery_ready_at_start is True
            assert all(h.effects[name] == 1 for name in (
                "summary_recover", "index_recover", "summary_start",
                "thread_start", "cleanup_schedule",
            ))
            # SecurityAudit deliberately converts downstream exceptions to HTTP 500.
            response, _ = await request(app, "GET", "/api/v1/health")
            assert response.status_code == 500

    run(scenario())
    assert reached == ["/api/v1/health"]
    assert h.effects["summary_stop"] == 1
    assert h.effects["thread_join"] == 1
    assert h.effects["cleanup_cancel"] == 1
