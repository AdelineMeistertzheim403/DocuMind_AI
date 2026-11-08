import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from tools import retention_age_simulation as age


NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def ident(number):
    return f'{number:064x}'


def inventory():
    backups, objects = [], []
    for kind, offset in (('local', 100), ('remote', 200)):
        for day in range(34):
            backup_id = ident(offset + day)
            object_id = ident(1000 + day)
            backups.append({
                'id': backup_id, 'kind': kind, 'created_at': age.utc(NOW - timedelta(days=day)),
                'classification': 'ordinary', 'metadata': 'verified',
                'restore_evidence': day == 0,
                'dependencies': [object_id] if kind == 'remote' else [],
            })
            if kind == 'remote':
                objects.append({'id': object_id, 'snapshot_ids': [backup_id], 'replicated': False,
                                'locked': False, 'versions': [{'id': ident(2000 + day),
                                'logical_deleted': False, 'physical_present': True}]})
    return {'format': 1, 'synthetic_only': True, 'scope_id': ident(9999), 'inventory_complete': True,
            'exceptions_complete': True, 'dependencies_complete': True,
            'backups': backups, 'objects': objects, 'exceptions': []}


def simulate(data, now=NOW):
    return age.build_plan(data, age.utc(now), copy.deepcopy(data))


def row(plan, key):
    return next(item for item in plan['items'] if item['id'] == key)


@pytest.mark.parametrize(('kind', 'day', 'nominal', 'target'), [
    ('local', 6, False, False), ('local', 7, True, False), ('local', 8, True, True),
    ('remote', 29, False, False), ('remote', 30, True, False), ('remote', 32, True, True),
])
def test_nominal_and_margin_boundaries(kind, day, nominal, target):
    data = inventory()
    item = row(simulate(data), ident((100 if kind == 'local' else 200) + day))
    assert item['age_due'] is nominal
    assert item['target_deadline_reached'] is target
    assert item['decision'] == ('theoretical_candidate' if nominal else 'preserve')


@pytest.mark.parametrize(('kind', 'days'), [('local', 7), ('remote', 30)])
def test_exact_boundaries_and_utc_offsets(kind, days):
    data = inventory()
    key = ident((100 if kind == 'local' else 200) + days)
    item = next(item for item in data['backups'] if item['id'] == key)
    item['created_at'] = (NOW - timedelta(days=days) + timedelta(microseconds=1)).isoformat()
    assert not row(simulate(data), key)['age_due']
    item['created_at'] = (NOW - timedelta(days=days) - timedelta(microseconds=1)).astimezone(
        timezone(timedelta(hours=2))).isoformat()
    assert row(simulate(data), key)['age_due']
    # Both sides of the European clock change represent the same UTC instant.
    item['created_at'] = '2026-10-25T02:30:00+02:00'
    assert row(simulate(data), key)['created_at'] == '2026-10-25T00:30:00Z'
    item['created_at'] = '2026-10-25T02:30:00+01:00'
    assert row(simulate(data), key)['created_at'] == '2026-10-25T01:30:00Z'


@pytest.mark.parametrize(('kind', 'days'), [('local', 8), ('remote', 32)])
def test_target_deadline_exact_microsecond(kind, days):
    data = inventory()
    key = ident((100 if kind == 'local' else 200) + days)
    item = next(item for item in data['backups'] if item['id'] == key)
    item['created_at'] = age.utc(NOW - timedelta(days=days) + timedelta(microseconds=1))
    assert not row(simulate(data), key)['target_deadline_reached']
    item['created_at'] = age.utc(NOW - timedelta(days=days))
    assert row(simulate(data), key)['target_deadline_reached']


@pytest.mark.parametrize('bad', [None, '', 'not-a-date', '2026-10-01T00:00:00',
                                  '2030-01-01T00:00:00Z'])
def test_invalid_or_future_timestamps_are_refused(bad):
    data = inventory()
    data['backups'][0]['created_at'] = bad
    with pytest.raises(age.SimulationError):
        simulate(data)


@pytest.mark.parametrize('field', ['inventory_complete', 'dependencies_complete', 'exceptions_complete'])
def test_incomplete_inventories_refused(field):
    data = inventory()
    data[field] = False
    with pytest.raises(age.SimulationError, match='incomplete_inventory'):
        simulate(data)


@pytest.mark.parametrize('metadata', ['invalid', 'checksum_mismatch', 'unknown'])
def test_inconsistent_metadata_blocks_every_candidate(metadata):
    data = inventory()
    data['backups'][2]['metadata'] = metadata
    plan = simulate(data)
    assert plan['status'] == 'blocked'
    assert all(item['decision'] == 'preserve' for item in plan['items'])


def test_historical_schema_and_protected_prefix_never_become_candidates():
    data = inventory()
    historical = data['backups'][10]
    historical.update(classification='historical', metadata='historical_schema')
    protected = data['backups'][11]
    protected['id'] = '51ac3259' + 'a' * 56
    plan = simulate(data)
    assert 'historical' in row(plan, historical['id'])['reasons']
    assert 'metadata_historical_schema' in row(plan, historical['id'])['reasons']
    assert 'protected_historical_prefix' in row(plan, protected['id'])['reasons']


def test_latest_recovery_is_preserved_and_absence_blocks():
    data = inventory()
    for kind in ('local', 'remote'):
        assert 'latest_verified_recovery' in row(simulate(data), ident(100 if kind == 'local' else 200))['reasons']
    for item in data['backups']:
        item['restore_evidence'] = False
    plan = simulate(data)
    assert plan['status'] == 'blocked'
    assert all(item['decision'] == 'preserve' for item in plan['items'])


@pytest.mark.parametrize('mode', ['shared', 'locked', 'replicated'])
def test_restic_dependencies_hold_snapshot(mode):
    data = inventory()
    old = data['backups'][34 + 31]
    obj = data['objects'][31]
    if mode == 'shared':
        other = data['backups'][34 + 30]
        obj['snapshot_ids'].append(other['id'])
        other['dependencies'].append(obj['id'])
    else:
        obj[mode] = True
    item = row(simulate(data), old['id'])
    assert item['decision'] == 'preserve'
    assert 'restic_dependency_requires_review' in item['reasons']


def test_logical_deletion_does_not_prove_physical_disappearance():
    data = inventory()
    version = data['objects'][31]['versions'][0]
    version['logical_deleted'] = True
    version['physical_present'] = True
    plan = simulate(data)
    dependency = row(plan, ident(231))['dependencies'][0]
    assert dependency['versions'][0]['physical_present']
    assert row(plan, ident(231))['decision'] == 'preserve'
    assert plan['physical_disappearance_proven'] is False


@pytest.mark.parametrize('mutation', ['missing_object', 'unknown_snapshot', 'empty_dependencies',
                                      'duplicate_id', 'missing_physical_object'])
def test_ambiguous_dependency_graph_refused(mutation):
    data = inventory()
    if mutation == 'missing_object':
        data['objects'].pop()
    elif mutation == 'unknown_snapshot':
        data['objects'][0]['snapshot_ids'] = [ident(99998)]
    elif mutation == 'empty_dependencies':
        data['backups'][34]['dependencies'] = []
    elif mutation == 'duplicate_id':
        data['backups'][1]['id'] = data['backups'][0]['id']
    else:
        data['objects'][0]['versions'][0]['physical_present'] = False
    with pytest.raises(age.SimulationError):
        simulate(data)


def exception(data):
    return {'id': ident(3000), 'reason': 'legal_hold', 'responsible_id': ident(4000),
            'backup_ids': [data['backups'][8]['id']], 'ends_at': age.utc(NOW + timedelta(days=2)),
            'end_event': None, 'reviewed_at': age.utc(NOW - timedelta(days=1)),
            'review_at': age.utc(NOW + timedelta(days=2))}


def test_active_exceptions_and_multiple_protections():
    data = inventory()
    hold = exception(data)
    data['exceptions'].append(hold)
    data['backups'][8]['classification'] = 'historical'
    item = row(simulate(data), hold['backup_ids'][0])
    assert item['decision'] == 'preserve'
    assert {'active_exception', 'historical'} <= set(item['reasons'])
    assert item['exceptions'] == [hold['id']]


@pytest.mark.parametrize('issue', ['expired', 'missing_responsible', 'empty_scope', 'overdue',
                                   'too_late_review', 'unknown_scope', 'missing_end'])
def test_invalid_holds_refuse_all_plans(issue):
    data = inventory()
    hold = exception(data)
    data['exceptions'].append(hold)
    if issue == 'expired': hold['ends_at'] = age.utc(NOW)
    elif issue == 'missing_responsible': hold['responsible_id'] = ''
    elif issue == 'empty_scope': hold['backup_ids'] = []
    elif issue == 'overdue': hold['review_at'] = age.utc(NOW)
    elif issue == 'too_late_review': hold['review_at'] = age.utc(NOW + timedelta(days=31))
    elif issue == 'unknown_scope': hold['backup_ids'] = [ident(99998)]
    else: hold['ends_at'] = None
    with pytest.raises(age.SimulationError):
        simulate(data)


def test_freshness_hash_clock_inventory_and_recovery_after_error():
    data = inventory()
    plan = simulate(data)
    assert age.verify_plan(plan, data, age.utc(NOW + timedelta(minutes=14)))
    with pytest.raises(age.SimulationError, match='plan_expired'):
        age.verify_plan(plan, data, age.utc(NOW + timedelta(minutes=15)))
    with pytest.raises(age.SimulationError, match='clock'):
        age.verify_plan(plan, data, age.utc(NOW - timedelta(seconds=1)))
    changed = copy.deepcopy(data)
    changed['backups'][1]['restore_evidence'] = True
    with pytest.raises(age.SimulationError, match='inventory_changed'):
        age.build_plan(data, age.utc(NOW), changed)
    with pytest.raises(age.SimulationError, match='inventory_changed'):
        age.verify_plan(plan, changed, age.utc(NOW))
    edited = copy.deepcopy(plan)
    edited['items'][0]['decision'] = 'theoretical_candidate'
    edited['plan_sha256'] = '0' * 64
    with pytest.raises(age.SimulationError, match='plan_hash_mismatch'):
        age.verify_plan(edited, data, age.utc(NOW))
    assert simulate(data)['plan_sha256'] == plan['plan_sha256']


def test_irregular_backups_block_candidates():
    data = inventory()
    for item in data['backups']:
        if item['kind'] == 'local' and item['id'] == ident(102):
            item['created_at'] = age.utc(NOW - timedelta(days=4, hours=1))
    plan = simulate(data)
    assert plan['status'] == 'blocked' and 'irregular_backups_local' in plan['blocks']


def test_no_execution_or_sensitive_output(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        age.main(['--execute'])
    assert exc.value.code == 2
    fixture = tmp_path / 'fixture.json'
    data = inventory()
    data['backups'][0]['secret-content'] = 'synthetic-secret-must-not-leak'
    fixture.write_text(json.dumps(data), encoding='utf-8')
    assert age.main(['--synthetic-inventory', str(fixture), '--reference-time', age.utc(NOW),
                     '--private-directory', str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert 'synthetic-secret-must-not-leak' not in captured.err + captured.out
    assert list(tmp_path.iterdir()) == [fixture]


def test_cli_refuses_inventory_changed_during_calculation(tmp_path, monkeypatch, capsys):
    fixture = tmp_path / 'fixture.json'
    data = inventory()
    fixture.write_text(json.dumps(data), encoding='utf-8')
    original = age.build_plan

    def concurrent_change(*args):
        plan = original(*args)
        changed = copy.deepcopy(data)
        changed['backups'][1]['restore_evidence'] = True
        fixture.write_text(json.dumps(changed), encoding='utf-8')
        return plan

    monkeypatch.setattr(age, 'build_plan', concurrent_change)
    assert age.main(['--synthetic-inventory', str(fixture), '--reference-time', age.utc(NOW),
                     '--private-directory', str(tmp_path)]) == 2
    assert 'inventory_changed' in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [fixture]


def test_duplicate_json_keys_are_rejected(tmp_path):
    fixture = tmp_path / 'ambiguous.json'
    fixture.write_text('{"format":1,"format":1}', encoding='utf-8')
    with pytest.raises(age.SimulationError, match='duplicate_json_key'):
        age.load_inventory(fixture)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permission checks')
@pytest.mark.posix
def test_private_plan_is_exclusive_and_not_public(tmp_path, capsys):
    tmp_path.chmod(0o700)
    fixture = tmp_path / 'fixture.json'
    fixture.write_text(json.dumps(inventory()), encoding='utf-8')
    assert age.main(['--synthetic-inventory', str(fixture), '--reference-time', age.utc(NOW),
                     '--private-directory', str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert ident(9999) not in output
    plans = list(tmp_path.glob('synthetic-plan-*.json'))
    assert len(plans) == 1 and plans[0].stat().st_mode & 0o777 == 0o600
    saved = json.loads(plans[0].read_text())
    assert age.verify_plan(saved, inventory(), age.utc(NOW))
    tmp_path.chmod(0o755)
    with pytest.raises(age.SimulationError, match='private_directory_required'):
        age.write_private_plan(tmp_path, saved)


def test_module_has_no_external_process_or_delete_primitives():
    source = Path(age.__file__).read_text(encoding='utf-8')
    assert all(word not in source for word in ('subprocess', '.unlink(', 'rmtree', 'restic forget', 'restic prune'))
