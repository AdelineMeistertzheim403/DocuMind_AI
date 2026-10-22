"""SEC10-02: denied uploads must never ask ASGI for a body or create a spool."""
import asyncio
import time
from uuid import UUID

import pytest
from pydantic import SecretStr

from backend.auth import User
from backend.models import now


def session_token(app, state='valid'):
    with app.state.sessions() as db:
        user = User(owner_id=UUID(int=931), username='upload-test', password_hash='unused-test-hash')
        db.add(user)
        db.commit()
        token = app.state.session_vault.create(user)
        if state == 'disabled':
            user.disabled_at = now()
            db.commit()
    if state == 'expired':
        app.state.session_vault.resolve(token).expires_at = time.time() - 1
    elif state == 'revoked':
        app.state.session_vault.revoke(token)
    return token


def raw_request(app, headers, chunks, path='/api/v1/documents', method='POST'):
    metrics = {'receive_calls': 0, 'bytes': 0, 'messages': []}

    async def run():
        iterator = iter(chunks)

        async def receive():
            metrics['receive_calls'] += 1
            try:
                item = next(iterator)
            except StopIteration:
                return {'type': 'http.disconnect'}
            if isinstance(item, dict):
                return item
            if callable(item):
                result = item()
                return await result if asyncio.iscoroutine(result) else result
            metrics['bytes'] += len(item)
            return {'type': 'http.request', 'body': item, 'more_body': True}

        async def send(message):
            metrics['messages'].append(message)

        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': method, 'scheme': 'http', 'path': path,
                 'raw_path': path.encode(), 'root_path': '', 'query_string': b'',
                 'headers': [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 'client': ('127.0.0.1', 10000), 'server': ('test', 80)}
        await app(scope, receive, send)

    asyncio.run(run())
    starts = [m for m in metrics['messages'] if m['type'] == 'http.response.start']
    metrics['status'] = starts[0]['status'] if starts else None
    return metrics


@pytest.mark.parametrize('state', ['absent', 'invented', 'expired', 'revoked', 'disabled'])
@pytest.mark.parametrize('path', ['/api/v1/documents', '/api/v1/documents/'])
def test_denied_session_never_receives_or_spools(app, monkeypatch, state, path):
    app.state.settings.legacy_api_enabled = False
    app.state.settings.bff_service_key = SecretStr('test-service-credential-not-real-00001')
    headers = {'x-api-key': app.state.settings.bff_service_key.get_secret_value(),
               'x-documind-secure': '1', 'content-type': 'multipart/form-data; boundary=test'}
    if state != 'absent':
        token = 'A' * 43 if state == 'invented' else session_token(app, state)
        headers['authorization'] = 'Bearer ' + token
    import backend.main as main
    spools = []
    original = main.tempfile.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        spools.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(main.tempfile, 'SpooledTemporaryFile', tracked)
    body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.txt"\r\n\r\n' + b'x' * 300000 + b'\r\n--test--\r\n'
    result = raw_request(app, headers, [body, {'type': 'http.request', 'body': b'', 'more_body': False}], path)
    assert result['status'] == 401
    assert result['receive_calls'] == 0
    assert result['bytes'] == 0
    assert spools == []
    assert not app.state.settings.storage_dir.exists()


def multipart(data=b'hello', closing=True):
    return (b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            b'Content-Type: text/plain\r\n\r\n' + data + (b'\r\n--test--\r\n' if closing else b''))


def legacy_headers():
    from tests.conftest import KEY
    return {'x-api-key': KEY, 'content-type': 'multipart/form-data; boundary=test'}


def completed(body):
    return [body, {'type':'http.request', 'body':b'', 'more_body':False}]


def track_spools(monkeypatch):
    import tempfile
    import backend.main as main
    import starlette.formparsers as forms
    streams = []
    original = tempfile.SpooledTemporaryFile
    def tracked(*args, **kwargs):
        stream = original(*args, **kwargs)
        streams.append(stream)
        return stream
    monkeypatch.setattr(main.tempfile, 'SpooledTemporaryFile', tracked)
    monkeypatch.setattr(forms, 'SpooledTemporaryFile', tracked)
    return streams


@pytest.mark.parametrize('body', [multipart(closing=False), multipart()[:-5],
                                multipart().replace(b'--test--', b'--test'),
                                b'--test\r\nContent-Disposition: form-data; name="other"\r\n\r\nx\r\n--test--\r\n'])
def test_multipart_errors_close_all_temporaries(app, monkeypatch, body):
    streams = track_spools(monkeypatch)
    result = raw_request(app, legacy_headers(), completed(body))
    assert result['status'] == 400
    assert all(s.closed for s in streams)
    assert app.state.upload_capacity.active == app.state.upload_capacity.reserved == 0
    assert not app.state.settings.storage_dir.exists()


def test_chunked_valid_file_and_size_boundary(app, monkeypatch):
    app.state.settings.storage_dir.mkdir()
    app.state.settings.max_upload_bytes = 5
    streams = track_spools(monkeypatch)
    body = multipart()
    result = raw_request(app, legacy_headers(), completed(body[:50])[:-1]+completed(body[50:]))
    assert result['status'] == 201
    assert all(s.closed for s in streams)
    assert len(list(app.state.settings.storage_dir.iterdir())) == 1
    too_large = raw_request(app, legacy_headers(), completed(multipart(b'123456')))
    assert too_large['status'] == 413
    assert all(s.closed for s in streams)
    assert not list(app.state.settings.storage_dir.glob('*.part'))


def test_disconnect_closes_spool_and_releases_capacity(app, monkeypatch):
    streams = track_spools(monkeypatch)
    result = raw_request(app, legacy_headers(), [multipart(closing=False), {'type':'http.disconnect'}])
    assert result['status'] is None
    assert streams and all(s.closed for s in streams)
    assert app.state.upload_capacity.active == app.state.upload_capacity.reserved == 0


@pytest.mark.parametrize('reason', ['budget','space','auth_capacity'])
def test_resource_refusal_before_receive(app, monkeypatch, reason):
    if reason == 'budget':
        app.state.settings.upload_temp_budget_bytes = 1
    elif reason == 'space':
        from collections import namedtuple
        monkeypatch.setattr('backend.upload_admission.shutil.disk_usage', lambda _: namedtuple('Usage','free')(0))
    else:
        while app.state.authentication_slots.acquire(blocking=False):
            pass
    streams = track_spools(monkeypatch)
    result = raw_request(app, legacy_headers(), completed(multipart()))
    assert result['status'] == 503
    assert result['receive_calls'] == 0 and streams == []
    assert app.state.upload_capacity.active == 0


@pytest.mark.parametrize('headers,status', [({'content-length':'99999999'},413),
                                         ({'content-length':'invalid'},400),
                                         ({'content-length':'3','transfer-encoding':'chunked'},400),
                                         ({'content-encoding':'gzip'},415)])
def test_invalid_envelope_rejected_without_body(app, headers, status):
    result = raw_request(app, {**legacy_headers(),**headers}, completed(multipart()))
    assert result['status'] == status and result['receive_calls'] == 0


def test_session_revoked_during_receive_is_rejected_and_cleaned(app, monkeypatch):
    token = session_token(app)
    streams = track_spools(monkeypatch)
    def revoke():
        app.state.session_vault.revoke(token)
        return {'type':'http.request','body':b'x','more_body':False}
    result = raw_request(app, {**legacy_headers(),'authorization':'Bearer '+token}, [multipart(closing=False),revoke])
    assert result['status'] == 401
    assert all(s.closed for s in streams)
    assert app.state.upload_capacity.active == 0


def test_session_revoked_during_extraction_cannot_commit(app, monkeypatch):
    token = session_token(app)
    app.state.settings.storage_dir.mkdir()
    def extract(*_):
        app.state.session_vault.revoke(token)
        return ['fake test text']
    monkeypatch.setattr('backend.services.documents.run_worker',extract)
    result = raw_request(app,{**legacy_headers(),'authorization':'Bearer '+token},completed(multipart()))
    assert result['status'] == 401
    assert not list(app.state.settings.storage_dir.iterdir())
    assert app.state.upload_capacity.active == 0


def test_preflight_is_body_free_and_contains_no_session_data(app):
    token = session_token(app)
    headers = {'x-api-key':app.state.settings.bff_service_key.get_secret_value(),
               'authorization':'Bearer '+token,'x-documind-secure':'1'}
    result = raw_request(app,headers,[b'never consumed'],path='/api/v1/internal/upload-admission',method='GET')
    assert result['status'] == 204 and result['receive_calls'] == 0
    assert token.encode() not in b''.join(m.get('body',b'') for m in result['messages'])
    denied = raw_request(app,{**headers,'x-api-key':'wrong'},[b'never'],path='/api/v1/internal/upload-admission',method='GET')
    assert denied['status'] == 403 and denied['receive_calls'] == 0


def test_upload_rate_limit_is_before_receive(app):
    app.state.settings.uploads_per_minute = 1
    first = raw_request(app,legacy_headers(),completed(multipart(closing=False)))
    assert first['status'] == 400
    second = raw_request(app,legacy_headers(),completed(multipart()))
    assert second['status'] == 429 and second['receive_calls'] == 0


@pytest.mark.parametrize('kind', ['idle','total'])
def test_body_deadlines_cleanup_and_release(app, monkeypatch, kind):
    app.state.settings.upload_idle_timeout_seconds = .01 if kind == 'idle' else .1
    app.state.settings.upload_read_timeout_seconds = .03 if kind == 'total' else 1
    streams = track_spools(monkeypatch)
    async def delayed():
        await asyncio.sleep(.02 if kind == 'total' else .05)
        return {'type':'http.request','body':b'x','more_body':True}
    result = raw_request(app,legacy_headers(),[delayed,delayed,delayed])
    assert result['status'] == 408
    assert streams and all(s.closed for s in streams)
    assert app.state.upload_capacity.active == app.state.upload_capacity.reserved == 0


def test_authentication_timeout_does_not_read_body_or_leak_slots(app, monkeypatch):
    app.state.settings.upload_auth_timeout_seconds = .005
    def slow(*args,**kwargs):
        time.sleep(.03)
        return UUID(int=1)
    monkeypatch.setattr('backend.upload_admission.authenticate',slow)
    result = raw_request(app,legacy_headers(),completed(multipart()))
    assert result['status'] == 503 and result['receive_calls'] == 0
    assert app.state.upload_capacity.active == 0
    assert app.state.authentication_slots.acquire(blocking=False)
    app.state.authentication_slots.release()


@pytest.mark.parametrize('same_owner', [False,True])
def test_simultaneous_upload_admission_is_atomic(app, monkeypatch, same_owner):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from tests.conftest import KEY, OTHER_KEY
    entered, release = Event(), Event()
    expected = 1 if same_owner else 2
    with app.state.sessions() as db:
        pass
    # Build once before concurrent calls; each request has its own ASGI loop/state.
    app.middleware_stack = app.build_middleware_stack()
    def held_body():
        if app.state.upload_capacity.active == expected:
            entered.set()
        assert release.wait(3)
        return {'type':'http.request','body':multipart(closing=False),'more_body':False}
    def request(key):
        return raw_request(app,{**legacy_headers(),'x-api-key':key},[held_body])
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(request,KEY)
        second = None if same_owner else pool.submit(request,OTHER_KEY)
        try:
            assert entered.wait(3)
            refused = request(KEY)
            assert refused['status'] == 503 and refused['receive_calls'] == 0
        finally:
            release.set()
        assert first.result()['status'] == 400
        if second:
            assert second.result()['status'] == 400
    assert app.state.upload_capacity.active == app.state.upload_capacity.reserved == 0


def test_crash_partial_is_counted_but_never_deleted(app):
    app.state.settings.storage_dir.mkdir()
    partial = app.state.settings.storage_dir/'fictitious-crash.part'
    with partial.open('wb') as file:
        file.truncate(40 * 1024 * 1024)
    result = raw_request(app,legacy_headers(),completed(multipart()))
    assert result['status'] == 503 and result['receive_calls'] == 0
    assert partial.exists()
    assert app.state.upload_capacity.active == 0


def test_openapi_keeps_required_multipart_upload(app):
    body = app.openapi()['paths']['/api/v1/documents']['post']['requestBody']
    assert body['required'] is True
    assert body['content']['multipart/form-data']['schema']['properties']['file']['format'] == 'binary'
    assert '/api/v1/internal/upload-admission' not in app.openapi()['paths']


def test_direct_bearer_policy_on_other_routes_is_unchanged(app):
    token = session_token(app)
    app.state.settings.legacy_api_enabled = False
    result = raw_request(app,{'authorization':'Bearer '+token},[],method='GET')
    assert result['status'] == 200 and result['receive_calls'] == 0
