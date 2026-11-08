import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
from types import SimpleNamespace

import pytest

from tools import preflight_recovery_compose as preflight
from tools import recovery_control_directory as contract
from tools import validate_recovery_candidate as validator

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_HOST_GUARD = contract.validate_host
ORIGINAL_READER = preflight._read_regular


def encoded(value):
    return json.dumps(value).encode()


def yaml_bytes(value):
    return validator.yaml.safe_dump(value, sort_keys=False).encode()


@pytest.fixture
def campaign(monkeypatch):
    source = (ROOT / 'lab' / 'compose.static.yaml').read_bytes()
    probe = (ROOT / 'lab' / 'docker_reader.py').read_bytes()
    values = {
        'LAB_IMAGE': 'sha256:' + 'a' * 64, 'LAB_PYTHON': '/opt/venv/bin/python',
        'LAB_READER_UID': '10001', 'LAB_READER_PRIMARY_GID': '10001',
        'RECOVERY_READER_GID': '42051',
        'RECOVERY_CONTROL_DIR': '/var/tmp/docnelo-rcd-' + 'b' * 32 + '/recovery-control',
        'LAB_PROBE': '/srv/qualification/candidate-r2/lab/docker_reader.py',
    }
    expanded = preflight._expand(validator.yaml.safe_load(source), values, set())
    expanded['name'] = 'docnelo-rcd-r2-test'
    expanded['services']['api']['mem_limit'] = 134217728
    for mount in expanded['services']['api']['volumes']:
        mount['bind'] = {}
    record = {'format': 1, 'synthetic_only': True, 'gid': 42051, 'device': 7, 'inode': 11}
    calls = []

    def host(source, gid, **kwargs):
        assert source == values['RECOVERY_CONTROL_DIR'] and gid == 42051
        assert kwargs['forbidden_roots'] == ('/var/lib/docker',)
        assert kwargs['expected'].identity == (7, 11)
        assert not kwargs.get('allow_missing', False)
        calls.append((source, gid))
        return contract.HostControl(PurePosixPath(source), gid, (7, 11))

    def read(path):
        assert path.as_posix() == values['LAB_PROBE']
        return probe

    monkeypatch.setattr(contract, 'validate_host', host)
    monkeypatch.setattr(preflight, '_read_regular', read)

    def validate(**overrides):
        arguments = {
            'source': source, 'rendered': encoded(expanded), 'parameters': encoded(values),
            'p2_record': encoded(record), 'expected_source_sha256': preflight.digest(source),
            'expected_probe_sha256': preflight.digest(probe),
            'project': expanded['name'], 'docker_root': '/var/lib/docker',
        }
        arguments.update(overrides)
        return preflight.validate_documents(**arguments)

    return SimpleNamespace(source=source, probe=probe, values=values, model=expanded,
                           record=record, calls=calls, validate=validate)


@pytest.mark.parametrize('representation', ['empty', 'explicit', 'mixed'])
def test_source_and_host_are_mandatory_even_when_compose_erases_false(campaign, representation):
    h = campaign
    model = copy.deepcopy(h.model)
    for index, mount in enumerate(model['services']['api']['volumes']):
        if representation == 'explicit' or representation == 'mixed' and index == 0:
            mount['bind'] = {'create_host_path': False}
    before = copy.deepcopy(model)
    result = h.validate(rendered=encoded(model))
    assert model == before
    assert len(result['reconstructed_false_from_source_only']) == {'empty': 2, 'explicit': 0, 'mixed': 1}[representation]
    assert result['directory_device_inode'] == (7, 11) and h.calls
    assert result['scope'] == 'REVIEW_ONLY_SOURCE_RENDER_HOST_PREFLIGHT'
    assert result['requires_engine_inspection_before_start'] is True
    assert result['p3_go'] is result['container_created'] is result['container_started'] is False


def test_empty_bind_still_fails_the_original_single_level_guard(campaign):
    with pytest.raises(contract.ContractError, match='strict read-only'):
        contract.validate_compose(campaign.model)


@pytest.mark.parametrize('fault', [
    'missing-false', 'true', 'numeric-zero', 'string-false', 'missing-bind',
    'probe-missing-false', 'direct-latch', 'rw', 'alias', 'inherited',
    'root-user', 'network', 'additional-service',
])
def test_invalid_source_cannot_be_authorized_by_rendered_empty_bind(campaign, fault):
    h = campaign
    source = validator.yaml.safe_load(h.source)
    api = source['services']['api']
    mount = api['volumes'][0]
    if fault == 'missing-false':
        mount['bind'] = {}
    elif fault in ('true', 'numeric-zero', 'string-false'):
        mount['bind']['create_host_path'] = {'true': True, 'numeric-zero': 0, 'string-false': 'false'}[fault]
    elif fault == 'missing-bind':
        mount.pop('bind')
    elif fault == 'probe-missing-false':
        api['volumes'][1]['bind'] = {}
    elif fault == 'direct-latch':
        mount['target'] = contract.STATE_PATH
    elif fault == 'rw':
        mount['read_only'] = False
    elif fault == 'alias':
        api['volumes'].append({'type': 'bind', 'source': '${RECOVERY_CONTROL_DIR:?}/..',
                              'target': '/alias', 'read_only': False, 'bind': {'create_host_path': False}})
    elif fault == 'inherited':
        api['volumes_from'] = ['unreviewed']
    elif fault == 'root-user':
        api['user'] = '0:0'
    elif fault == 'network':
        api['network_mode'] = 'bridge'
    elif fault == 'additional-service':
        source['services']['extra'] = copy.deepcopy(api)
    raw = yaml_bytes(source)
    with pytest.raises(contract.ContractError):
        h.validate(source=raw, expected_source_sha256=preflight.digest(raw))
    assert not h.calls


@pytest.mark.parametrize('fault', [
    'rw', 'probe-rw', 'direct-latch', 'source-mismatch', 'alias',
    'true', 'missing-bind', 'unknown-bind-option', 'root-user',
    'primary-gid', 'reader-group', 'env-path', 'network', 'ports', 'rootfs-rw',
    'inherited', 'unlimited-memory', 'different-image',
])
def test_rendered_model_cannot_override_valid_source(campaign, fault):
    h = campaign
    model = copy.deepcopy(h.model)
    api = model['services']['api']
    mount = api['volumes'][0]
    if fault == 'rw':
        mount['read_only'] = False
    elif fault == 'probe-rw':
        api['volumes'][1]['read_only'] = False
    elif fault == 'direct-latch':
        mount['target'] = contract.STATE_PATH
    elif fault == 'source-mismatch':
        mount['source'] += '-other'
    elif fault == 'alias':
        api['volumes'].append({'type': 'bind', 'source': h.values['RECOVERY_CONTROL_DIR'],
                              'target': '/alias', 'read_only': False, 'bind': {}})
    elif fault == 'true':
        mount['bind'] = {'create_host_path': True}
    elif fault == 'missing-bind':
        mount.pop('bind')
    elif fault == 'unknown-bind-option':
        mount['bind'] = {'propagation': 'shared'}
    elif fault == 'root-user':
        api['user'] = '0:10001'
    elif fault == 'primary-gid':
        api['user'] = '10001:0'
    elif fault == 'reader-group':
        api['group_add'] = ['10001']
    elif fault == 'env-path':
        api['environment']['RECOVERY_STATE_PATH'] = '/app/recovery-state.json'
    elif fault == 'network':
        api['network_mode'] = 'host'
    elif fault == 'ports':
        api['ports'] = [{'target': 8000, 'published': '8000'}]
    elif fault == 'rootfs-rw':
        api['read_only'] = False
    elif fault == 'inherited':
        api['volumes_from'] = ['extra']
    elif fault == 'unlimited-memory':
        api['mem_limit'] = 0
    elif fault == 'different-image':
        api['image'] = 'sha256:' + 'c' * 64
    with pytest.raises(contract.ContractError):
        h.validate(rendered=encoded(model))
    assert not h.calls


@pytest.mark.parametrize('key,value', [
    ('LAB_IMAGE', 'python:latest'), ('LAB_READER_UID', '0'),
    ('LAB_READER_PRIMARY_GID', '0'), ('RECOVERY_READER_GID', '0'),
    ('RECOVERY_CONTROL_DIR', '/home/adeline/production/recovery-control'),
    ('RECOVERY_CONTROL_DIR', 'relative/control'),
    ('LAB_PROBE', '/var/tmp/docnelo-rcd-' + 'b' * 32 + '/recovery-control/probe.py'),
])
def test_parameters_are_explicit_nonroot_and_cannot_alias_the_control(campaign, key, value):
    h = campaign
    values = dict(h.values, **{key: value})
    model = preflight._expand(validator.yaml.safe_load(h.source), values, set())
    model['name'] = h.model['name']
    with pytest.raises(contract.ContractError):
        h.validate(parameters=encoded(values), rendered=encoded(model))


def test_absent_directory_uses_the_real_host_guard_and_never_creates_it(campaign, monkeypatch):
    h = campaign
    # Real guard code, synthetic Linux stat responses; no namespace is accessed on Windows.
    monkeypatch.setattr(contract, 'validate_host', ORIGINAL_HOST_GUARD)
    monkeypatch.setattr(contract, '_require_linux', lambda: None)
    monkeypatch.setattr(contract, 'Path', PurePosixPath)

    def lstat(path):
        if str(path) == h.values['RECOVERY_CONTROL_DIR']:
            raise FileNotFoundError('synthetic absent source')
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)

    monkeypatch.setattr(contract, '_lstat', lstat)
    with pytest.raises(contract.ContractError, match='unavailable; no creation'):
        h.validate()
    assert not h.calls


@pytest.mark.parametrize('failure', ['permission', 'identity', 'mode'])
def test_host_policy_failures_are_never_downgraded_to_empty_bind_acceptance(campaign, monkeypatch, failure):
    def fail(*args, **kwargs):
        if failure == 'permission':
            raise PermissionError('synthetic permission denied')
        raise contract.ContractError('synthetic ' + failure + ' mismatch')
    monkeypatch.setattr(contract, 'validate_host', fail)
    with pytest.raises(contract.ContractError):
        campaign.validate()


def test_source_probe_and_p2_identity_must_be_bound_to_reviewed_inputs(campaign):
    h = campaign
    with pytest.raises(contract.ContractError, match='source YAML checksum'):
        h.validate(expected_source_sha256='0' * 64)
    with pytest.raises(contract.ContractError, match='probe checksum'):
        h.validate(expected_probe_sha256='0' * 64)
    record = dict(h.record, gid=10001)
    with pytest.raises(contract.ContractError, match='P2 identity'):
        h.validate(p2_record=encoded(record))


def test_duplicate_json_and_source_yaml_are_rejected(campaign):
    with pytest.raises(contract.ContractError):
        campaign.validate(rendered=b'{"name":"a","name":"b","services":{}}')
    raw = campaign.source + b'\nservices: {}\n'
    with pytest.raises(contract.ContractError):
        campaign.validate(source=raw, expected_source_sha256=preflight.digest(raw))


def test_cli_writes_only_new_evidence_and_never_overwrites(campaign, monkeypatch, tmp_path):
    h = campaign
    for name, raw in (
        ('source.yaml', h.source), ('rendered.json', encoded(h.model)),
        ('parameters.json', encoded(h.values)), ('p2.json', encoded(h.record)),
    ):
        (tmp_path / name).write_bytes(raw)
    # The fixture reader serves only the virtual probe. All CLI documents are real scratch files.
    def read(path):
        if path.as_posix() == h.values['LAB_PROBE']:
            return h.probe
        return ORIGINAL_READER(path)
    monkeypatch.setattr(preflight, '_read_regular', read)
    output = tmp_path / 'evidence'
    argv = ['preflight', '--source', str(tmp_path / 'source.yaml'),
            '--rendered', str(tmp_path / 'rendered.json'), '--parameters', str(tmp_path / 'parameters.json'),
            '--p2-record', str(tmp_path / 'p2.json'), '--source-sha256', preflight.digest(h.source),
            '--probe-sha256', preflight.digest(h.probe), '--project', h.model['name'],
            '--docker-root', '/var/lib/docker', '--evidence', str(output)]
    monkeypatch.setattr(sys, 'argv', argv)
    assert preflight.main() == 0
    assert (output / 'rendered.json').read_bytes() == encoded(h.model)
    assert all(mount['bind'] == {} for mount in json.loads(
        (output / 'rendered.json').read_bytes())['services']['api']['volumes'])
    assert json.loads((output / 'preflight.json').read_bytes())['p3_go'] is False
    before = {path.name: preflight.digest(path.read_bytes()) for path in output.iterdir()}
    assert preflight.main() == 1
    assert before == {path.name: preflight.digest(path.read_bytes()) for path in output.iterdir()}


def test_new_evidence_cannot_be_nested_under_a_previously_sealed_artifact(tmp_path):
    protected = tmp_path / 'sealed-artifact'
    protected.mkdir()
    marker = protected / 'SHA256SUMS'
    marker.write_bytes(b'unchanged synthetic seal\n')
    with pytest.raises(contract.ContractError, match='sealed evidence'):
        preflight._new_evidence(protected / 'new-child')
    assert not (protected / 'new-child').exists()
    assert marker.read_bytes() == b'unchanged synthetic seal\n'


def test_original_119_sources_and_p2_controls_remain_byte_identical():
    frozen = json.loads((ROOT / 'BASELINE_REVISION.json').read_text())['frozen_files_sha256']
    for name in (
        'tests/test_recovery_directory.py', 'tests/test_fastapi_directory_transitions.py',
        'source/tests/test_recovery_quarantine_inprocess.py', 'source/tools/recovery_control_directory.py',
        'lab/control.py', 'lab/compose.static.yaml', 'lab/docker_reader.py', 'lab/test_mounted_latch.py',
    ):
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == frozen[name]
