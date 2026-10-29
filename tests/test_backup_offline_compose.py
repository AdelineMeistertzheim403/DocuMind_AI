"""Fail closed if Compose cannot resolve network_mode:none for capture."""
from pathlib import Path
import pytest
from tools import backup_local


def test_capture_override_resets_networks_without_changing_source(monkeypatch):
    original = ['docker', 'compose', '--env-file', 'synthetic.env', '-f', 'synthetic.yaml']
    def resolve(command, env):
        override = Path(command[-1])
        assert override.read_text() == 'services:\n  api:\n    networks: !reset []\n    network_mode: none\n'
        assert command[:-2] == original
        return {'services': {'api': {'network_mode': 'none'}}}
    monkeypatch.setattr(backup_local, '_compose_config', resolve)
    with backup_local._offline_api_compose(original, None) as command:
        path = Path(command[-1])
        assert path.exists()
    assert not path.exists()
    assert original[-1] == 'synthetic.yaml'


@pytest.mark.parametrize('service', [{'networks': {'data': {}}},
                                   {'network_mode': 'none', 'networks': {'data': {}}},
                                   {'network_mode': 'host'}])
def test_capture_refuses_an_override_without_effective_isolation(monkeypatch, service):
    monkeypatch.setattr(backup_local, '_compose_config', lambda *_: {'services': {'api': service}})
    with pytest.raises(ValueError, match='network isolation'):
        with backup_local._offline_api_compose(['docker', 'compose', '-f', 'synthetic.yaml'], None):
            pytest.fail('Capture must never start')


def test_default_compose_file_is_preserved_before_offline_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('COMPOSE_FILE', raising=False)
    (tmp_path / 'compose.yaml').write_text('services: {}\n')
    (tmp_path / 'compose.override.yaml').write_text('services: {}\n')
    observed = []
    def resolve(command, env):
        observed.extend(command)
        return {'services': {'api': {'network_mode': 'none'}}}
    monkeypatch.setattr(backup_local, '_compose_config', resolve)
    with backup_local._offline_api_compose(['docker', 'compose'], None):
        pass
    assert observed[2:6] == ['-f', str(tmp_path / 'compose.yaml'), '-f', str(tmp_path / 'compose.override.yaml')]
