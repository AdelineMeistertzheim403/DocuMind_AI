import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.config import Settings
from backend.services import extraction
from documind_extractor import contract


def request():
    return {'version': 1, 'job_id': uuid4().hex, 'extension': '.txt', 'size': 4,
            'max_pages': 200, 'max_chars': 1000000}


@pytest.mark.parametrize('change', ['extra', 'filename', 'path', 'size', 'bool', 'extension', 'pages', 'chars', 'job'])
def test_request_rejects_untrusted_or_unbounded_fields(change):
    value = request()
    if change in ('extra', 'filename', 'path'): value[change] = '../../secret'
    elif change == 'size': value['size'] = contract.MAX_INPUT + 1
    elif change == 'bool': value['size'] = True
    elif change == 'extension': value['extension'] = '.py'
    elif change == 'pages': value['max_pages'] = 201
    elif change == 'chars': value['max_chars'] = 1000001
    elif change == 'job': value['job_id'] = '../file'
    with pytest.raises(ValueError): contract.validate_request(value)


@pytest.mark.parametrize('change', ['job', 'extra', 'page_type', 'pages', 'chars', 'blank', 'error', 'version', 'unicode'])
def test_response_is_typed_bounded_and_bound_to_job(change):
    expected = request(); value = {'version': 1, 'job_id': expected['job_id'], 'pages': ['safe']}
    if change == 'job': value['job_id'] = uuid4().hex
    elif change == 'extra': value['secret'] = 'not accepted'
    elif change == 'page_type': value['pages'] = [123]
    elif change == 'pages': value['pages'] = ['a'] * 201
    elif change == 'chars': value['pages'] = ['a' * 1000001]
    elif change == 'blank': value['pages'] = [' ']
    elif change == 'error': value = {'version': 1, 'job_id': expected['job_id'], 'error': 'private exception'}
    elif change == 'version': value['version'] = True
    elif change == 'unicode': value['pages'] = ['\ud800']
    with pytest.raises(ValueError): contract.validate_response(value, expected)


@pytest.mark.parametrize('raw', ['{"version":1,"version":1}', '{"number":NaN}', '{"number":Infinity}', '\xff'])
def test_duplicate_invalid_json_and_constants_refused(raw):
    with pytest.raises(ValueError): contract.decode(raw)


def test_broker_passes_only_current_document_and_limits(tmp_path, monkeypatch):
    path = tmp_path / 'server-generated.part'; path.write_bytes(b'safe')
    settings = Settings(_env_file=None)
    monkeypatch.setattr(extraction, 'sandbox_command', lambda *a: ['fixed-runner'])
    calls = []
    def exchange(command, payload, timeout):
        length = int.from_bytes(payload[:4], 'big'); header = contract.decode(payload[4:4+length])
        assert contract.validate_request(header)
        assert payload[4+length:] == b'safe' and str(path).encode() not in payload
        calls.append((command, timeout))
        return json.dumps({'version': 1, 'job_id': header['job_id'], 'pages': ['safe']}).encode()
    monkeypatch.setattr(extraction, 'exchange', exchange)
    assert extraction.extract_isolated(settings, path, '.txt', 200, 1000000) == ['safe']
    assert calls == [(['fixed-runner'], 30)]


@pytest.mark.parametrize('failure', ['worker_failed', 'timeout', 'invalid_output', 'sandbox_unavailable', 'resource_limit'])
def test_broker_errors_are_controlled_and_no_fallback(tmp_path, monkeypatch, failure):
    path = tmp_path / 'input.part'; path.write_bytes(b'safe')
    monkeypatch.setattr(extraction, 'sandbox_command', lambda *a: ['fixed-runner'])
    def failed(*args): raise extraction.ExtractionFailure(failure)
    monkeypatch.setattr(extraction, 'exchange', failed)
    with pytest.raises(HTTPException) as error:
        extraction.extract_isolated(Settings(_env_file=None), path, '.txt', 200, 1000000)
    assert error.value.status_code == (503 if failure == 'sandbox_unavailable' else 422)
    assert failure not in str(error.value.detail)


def test_sandbox_default_and_production_settings_cannot_select_development():
    import yaml
    settings = Settings(_env_file=None)
    assert settings.extraction_mode == 'sandbox'
    production = yaml.safe_load(Path('compose.production.yaml').read_text())
    assert set(production['services']) == {'api', 'web', 'db'}
    environment = production['services']['api']['environment']
    assert environment['EXTRACTION_MODE'] == 'sandbox'
    assert environment['MAX_CONCURRENT_WORKERS'] == '2'
    assert production['services']['api']['volumes'] == ['production_documents:/app/var']


def test_failed_extraction_does_not_create_data_or_break_other_owner(client, app, monkeypatch):
    from tests.conftest import OTHER_KEY
    app.state.settings.extraction_mode = 'sandbox'
    def failed(*args): raise HTTPException(422, 'Extraction refusée')
    monkeypatch.setattr(extraction, 'extract_isolated', failed)
    response = client.post('/api/v1/documents', files={'file': ('fictitious.txt', b'only fictitious data')})
    assert response.status_code == 422
    assert not list(app.state.settings.storage_dir.iterdir())
    assert client.get('/api/v1/health').status_code == 200
    assert client.get('/api/v1/documents', headers={'X-API-Key': OTHER_KEY}).json()['total'] == 0


def test_startup_checks_fail_closed_before_starting_application(app, monkeypatch):
    from fastapi.testclient import TestClient
    app.state.settings.extraction_mode = 'sandbox'
    def unavailable(settings): raise RuntimeError('sandbox unavailable')
    monkeypatch.setattr(extraction, 'check_available', unavailable)
    with pytest.raises(RuntimeError, match='sandbox unavailable'):
        with TestClient(app): pass


def test_two_inflight_extractions_refuse_a_third_and_release_slots(client, app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock
    app.state.settings.extraction_mode = 'sandbox'
    both = Event(); release = Event(); lock = Lock(); entered = []
    def blocked(*args):
        with lock:
            entered.append(True)
            if len(entered) == 2: both.set()
        assert release.wait(10)
        return ['Safe fictitious text.']
    monkeypatch.setattr(extraction, 'extract_isolated', blocked)
    def send(index):
        return client.post('/api/v1/documents', files={'file': (f'{index}.txt', b'fictitious')}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(send, index) for index in (1, 2)]
        try:
            assert both.wait(5)
            assert send(3) == 503
        finally: release.set()
        assert [future.result() for future in pending] == [201, 201]
    assert client.get('/api/v1/documents').json()['total'] == 2
    assert not list(app.state.settings.storage_dir.glob('*.part'))
