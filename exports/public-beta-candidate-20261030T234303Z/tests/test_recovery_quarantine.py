from fastapi.testclient import TestClient


def test_relative_local_latch_path_is_resolved_from_the_process_directory(tmp_path, monkeypatch):
    from backend.recovery_quarantine import read_recovery_state

    latch = tmp_path / 'var' / 'recovery-state.json'
    latch.parent.mkdir()
    latch.write_text('{"format":1,"state":"ready"}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert read_recovery_state('var/recovery-state.json') == 'ready'


def test_missing_invalid_or_quarantined_latch_denies_every_http_route(app):
    latch = app.state.settings.recovery_state_path
    for contents in (None, b'not-json', b'{"format":1,"state":"ready","state":"quarantined"}\n',
                     b'{"format":1,"state":"ready","extra":false}\n', b'{"format":1,"state":"quarantined"}\n',
                     b'{"format":true,"state":"ready"}\n', b'{"format":1,"state":[]}\n'):
        if contents is None:
            latch.unlink(missing_ok=True)
        else:
            latch.write_bytes(contents)
        with TestClient(app) as client:
            assert client.get('/api/v1/health').status_code == 503
            assert client.get('/api/v1/documents').status_code == 503
            assert client.post('/api/v1/auth/register', json={}).status_code == 503
        latch.write_text('{"format":1,"state":"ready"}\n', encoding='utf-8')


def test_quarantine_at_startup_skips_recovery_and_background_workers(app, monkeypatch):
    import backend.ai.long_summary as long_summary
    import backend.rag.indexing as indexing

    calls = []
    monkeypatch.setattr(indexing, 'recover_jobs', lambda _: calls.append('indexing'))
    monkeypatch.setattr(long_summary, 'recover', lambda _: calls.append('summary'))
    latch = app.state.settings.recovery_state_path
    latch.write_text('{"format":1,"state":"quarantined"}\n', encoding='utf-8')

    with TestClient(app) as client:
        assert client.get('/api/v1/health').status_code == 503
        assert calls == []
        assert not app.state.summary_worker.thread.is_alive()
        latch.write_text('{"format":1,"state":"ready"}\n', encoding='utf-8')
        assert client.get('/api/v1/health').status_code == 503


def test_ready_process_fails_closed_when_latch_changes_to_quarantine(client, app):
    assert client.get('/api/v1/health').status_code == 200
    app.state.settings.recovery_state_path.write_text(
        '{"format":1,"state":"quarantined"}\n', encoding='utf-8')
    assert client.get('/api/v1/health').status_code == 503
    assert client.get('/api/v1/documents').status_code == 503
