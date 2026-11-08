import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from test_compose_source_rendered import campaign, encoded, yaml_bytes, ORIGINAL_READER
from tools import preflight_recovery_compose as preflight
from tools import recovery_control_directory as contract
from tools import validate_recovery_candidate as validator


@pytest.mark.parametrize('memory', ['128m', 134217728, '134217728'])
def test_exact_approved_memory_representations_pass_the_complete_preflight(campaign, memory):
    model = copy.deepcopy(campaign.model)
    model['services']['api']['mem_limit'] = memory
    raw = encoded(model)
    result = campaign.validate(rendered=raw)
    assert len(campaign.calls) == 1
    assert result['rendered_sha256'] == preflight.digest(raw)
    assert result['revision'] == 'v1-r3' and result['p3_go'] is False


@pytest.mark.parametrize('memory', [
    134217727, 134217729, '134217727', '134217729', 0,
    134217728.0, True, False, None, [134217728], {'bytes': 134217728},
    '0134217728', '+134217728', ' 134217728', '134217728 ',
    '134217728.0', '1.34217728e8', '128M', '128MiB', '128.0m',
    '0.125g', '134_217_728', '128m\n', '\uff11\uff13\uff14\uff12\uff11\uff17\uff17\uff12\uff18',
])
def test_nearby_ambiguous_or_incorrectly_typed_memory_is_refused(campaign, memory):
    model = copy.deepcopy(campaign.model)
    model['services']['api']['mem_limit'] = memory
    with pytest.raises(contract.ContractError, match='rendered mem_limit'):
        campaign.validate(rendered=encoded(model))
    assert not campaign.calls


def test_missing_memory_limit_is_not_defaulted(campaign):
    model = copy.deepcopy(campaign.model)
    del model['services']['api']['mem_limit']
    with pytest.raises(contract.ContractError, match='rendered mem_limit'):
        campaign.validate(rendered=encoded(model))
    assert not campaign.calls


@pytest.mark.parametrize('number', [b'1.34217728e8', b'134217728e0'])
def test_scientific_json_numbers_are_not_coerced_to_integer(campaign, number):
    raw = encoded(campaign.model)
    rendered = raw.replace(b'"mem_limit": 134217728', b'"mem_limit": ' + number, 1)
    assert rendered != raw
    with pytest.raises(contract.ContractError, match='rendered mem_limit'):
        campaign.validate(rendered=rendered)
    assert not campaign.calls


@pytest.mark.parametrize('memory', [134217728, '134217728', 134217728.0])
def test_rendered_compatibility_does_not_change_the_approved_source(campaign, memory):
    source = validator.yaml.safe_load(campaign.source)
    source['services']['api']['mem_limit'] = memory
    raw = yaml_bytes(source)
    with pytest.raises(contract.ContractError, match='source differs'):
        campaign.validate(source=raw, expected_source_sha256=preflight.digest(raw))
    assert not campaign.calls


@pytest.mark.parametrize('fault', ['source-false', 'rw', 'p2', 'host'])
def test_decimal_string_never_bypasses_the_other_required_controls(campaign, monkeypatch, fault):
    model = copy.deepcopy(campaign.model)
    model['services']['api']['mem_limit'] = '134217728'
    arguments = {'rendered': encoded(model)}
    if fault == 'source-false':
        source = validator.yaml.safe_load(campaign.source)
        source['services']['api']['volumes'][0]['bind'] = {}
        raw = yaml_bytes(source)
        arguments.update(source=raw, expected_source_sha256=preflight.digest(raw))
    elif fault == 'rw':
        model['services']['api']['volumes'][0]['read_only'] = False
        arguments['rendered'] = encoded(model)
    elif fault == 'p2':
        arguments['p2_record'] = encoded(dict(campaign.record, gid=10001))
    else:
        def absent(*args, **kwargs):
            raise FileNotFoundError('synthetic source absent')
        monkeypatch.setattr(contract, 'validate_host', absent)
    with pytest.raises(contract.ContractError):
        campaign.validate(**arguments)
    assert not campaign.calls


def test_cli_preserves_native_decimal_string_in_new_evidence(campaign, monkeypatch, tmp_path):
    model = copy.deepcopy(campaign.model)
    model['services']['api']['mem_limit'] = '134217728'
    raw = encoded(model)
    for name, body in (
        ('source.yaml', campaign.source), ('rendered.json', raw),
        ('parameters.json', encoded(campaign.values)), ('p2.json', encoded(campaign.record)),
    ):
        (tmp_path / name).write_bytes(body)

    def read(path):
        return campaign.probe if path.as_posix() == campaign.values['LAB_PROBE'] else ORIGINAL_READER(path)
    monkeypatch.setattr(preflight, '_read_regular', read)
    output = tmp_path / 'evidence'
    monkeypatch.setattr(sys, 'argv', [
        'preflight', '--source', str(tmp_path / 'source.yaml'),
        '--rendered', str(tmp_path / 'rendered.json'),
        '--parameters', str(tmp_path / 'parameters.json'), '--p2-record', str(tmp_path / 'p2.json'),
        '--source-sha256', preflight.digest(campaign.source),
        '--probe-sha256', preflight.digest(campaign.probe),
        '--project', model['name'], '--docker-root', '/var/lib/docker',
        '--evidence', str(output),
    ])
    assert preflight.main() == 0
    assert (output / 'rendered.json').read_bytes() == raw
    result = json.loads((output / 'preflight.json').read_bytes())
    assert result['rendered_sha256'] == preflight.digest(raw)
    assert result['p3_go'] is result['container_created'] is result['container_started'] is False


def test_all_unaffected_r2_files_remain_byte_identical():
    root = Path(__file__).resolve().parents[1]
    original = json.loads((root / 'BASELINE_R3.json').read_bytes())['frozen_candidates_sha256'][
        'recovery-control-directory-v1-r2']
    changed = {
        'source/tools/preflight_recovery_compose.py', 'run_local.py', 'README.md',
        'DEBIAN_OFFLINE_PROTOCOL.md', 'INPUTS.json', 'SHA256SUMS',
        'REVISION_CHANGES.json', 'revision.patch', 'PRESERVATION_VERIFIED.json',
    }
    for name, expected in original.items():
        if name not in changed:
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
