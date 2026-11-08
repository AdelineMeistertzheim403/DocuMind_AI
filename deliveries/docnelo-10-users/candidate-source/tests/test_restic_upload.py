"""Restic 0.14.0 JSON shape reconstructed from its versioned Go source; no real repository."""
import copy
import json
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from tools import backup_production as backup


SNAPSHOT = '3e6df673348bbc1de1fdbb8937854a2e65ef53d6248510356e30a85826faabb1'
RUN = 'daily-20261020T085129Z-86ae029758044a928c56558af9cf17a5'
DESTINATION = PurePosixPath('/srv/documind-ai/var/backups') / RUN


@pytest.fixture
def restic(monkeypatch):
    # v0.14.0 JSONProgress.Finish uses snapshotID.Str() (4 bytes -> 8 hex chars).
    summary = {'message_type': 'summary', 'files_new': 4, 'files_changed': 0, 'files_unmodified': 0,
        'dirs_new': 1, 'dirs_changed': 0, 'dirs_unmodified': 0, 'data_blobs': 4, 'tree_blobs': 1,
        'data_added': 1024, 'total_files_processed': 4, 'total_bytes_processed': 1024,
        'total_duration': 1.5, 'snapshot_id': SNAPSHOT[:8]}
    found = [{'id': SNAPSHOT, 'short_id': SNAPSHOT[:8], 'tags': ['documind-ai', RUN], 'paths': [str(DESTINATION)]}]
    state = {'messages': [{'message_type': 'status', 'percent_done': 1.0}, summary],
             'found': found, 'backup_code': 0, 'snapshots_code': 0}
    calls = []
    env = {'RESTIC_PASSWORD': 'do-not-log-secret', 'B2_ACCOUNT_KEY': 'do-not-log-key'}
    def run(argv, **kwargs):
        assert argv[0] == 'restic' and kwargs['env'] == env
        assert kwargs['capture_output'] and kwargs['text']
        assert not any(secret in str(argv) for secret in env.values())
        calls.append(argv)
        if argv[1] == 'backup':
            output = state.get('raw_backup', '\n'.join(json.dumps(item) for item in state['messages']) + '\n')
            code = state['backup_code']
        else:
            assert argv[1:3] == ['snapshots', '--json']
            output = state.get('raw_snapshots', json.dumps(state['found']))
            code = state['snapshots_code']
        return SimpleNamespace(returncode=code, stdout=output, stderr='do-not-log-secret do-not-log-key')
    monkeypatch.setattr(backup.subprocess, 'run', run)
    return state, calls, env


@pytest.mark.parametrize('full_summary', [False, True])
def test_short_014_or_full_summary_requires_exact_confirmed_full_id(restic, full_summary, capsys):
    state, calls, env = restic
    if full_summary: state['messages'][-1]['snapshot_id'] = SNAPSHOT
    result = backup.upload(DESTINATION, RUN, env)
    assert result == SNAPSHOT and len(result) == 64
    assert calls == [
        ['restic', 'backup', '--json', '--tag', 'documind-ai', '--tag', RUN, str(DESTINATION)],
        ['restic', 'snapshots', '--json', SNAPSHOT if full_summary else SNAPSHOT[:8]]]
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('stage,code', [('backup', 1), ('backup', 3), ('snapshots', 1)])
def test_nonzero_exit_cannot_be_success_even_with_valid_snapshot(restic, stage, code):
    state, calls, env = restic; state[stage + '_code'] = code
    with pytest.raises(backup.BackupError, match='command_failed'):
        backup.upload(DESTINATION, RUN, env)
    assert len(calls) == (1 if stage == 'backup' else 2)


@pytest.mark.parametrize('invalid', ['missing_summary', 'duplicate_summary', 'after_summary', 'error', 'error_count',
    'dry_run', 'id_missing', 'id_null', 'id_number', 'id_nonhex', 'id_wrong_length', 'id_16_chars',
    'invalid_json', 'duplicate_json_key', 'nonobject', 'unknown_type', 'type_array', 'nan'])
def test_ambiguous_or_incomplete_backup_output_is_rejected_before_lookup(restic, invalid, capsys):
    state, calls, env = restic; summary = state['messages'][-1]
    if invalid == 'missing_summary': state['messages'].pop()
    elif invalid == 'duplicate_summary': state['messages'].append(copy.deepcopy(summary))
    elif invalid == 'after_summary': state['messages'].append({'message_type': 'status'})
    elif invalid == 'error': state['messages'].insert(0, {'message_type': 'error', 'error': 'do-not-log-secret'})
    elif invalid == 'error_count': state['messages'][0]['error_count'] = 1
    elif invalid == 'dry_run': summary['dry_run'] = True
    elif invalid == 'id_missing': summary.pop('snapshot_id')
    elif invalid == 'id_null': summary['snapshot_id'] = None
    elif invalid == 'id_number': summary['snapshot_id'] = 123
    elif invalid == 'id_nonhex': summary['snapshot_id'] = 'not-hex!'
    elif invalid == 'id_wrong_length': summary['snapshot_id'] = 'abc'
    elif invalid == 'id_16_chars': summary['snapshot_id'] = SNAPSHOT[:16]
    elif invalid == 'invalid_json': state['raw_backup'] = 'do-not-log-secret'
    elif invalid == 'duplicate_json_key':
        state['raw_backup'] = '{"message_type":"summary","snapshot_id":"3e6df673","snapshot_id":"00000000"}'
    elif invalid == 'nonobject': state['messages'] = [None]
    elif invalid == 'unknown_type': state['messages'][0]['message_type'] = 'unexpected'
    elif invalid == 'type_array': state['messages'][0]['message_type'] = []
    elif invalid == 'nan': state['raw_backup'] = '{"message_type":"summary","total_duration":NaN}'
    with pytest.raises(backup.BackupError, match='restic_snapshot_not_confirmed') as error:
        backup.upload(DESTINATION, RUN, env)
    assert len(calls) == 1 and 'do-not-log' not in str(error.value)
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('invalid', ['empty', 'two_prefix_matches', 'different_id', 'short_confirmed_id',
    'invalid_confirmed_id', 'wrong_run_tag', 'missing_app_tag', 'extra_tag', 'duplicate_tag', 'tags_string',
    'tag_object', 'wrong_path', 'extra_path', 'nonarray', 'nondict', 'invalid_json', 'duplicate_key'])
def test_snapshot_lookup_must_be_unique_and_exact(restic, invalid, capsys):
    state, calls, env = restic; item = state['found'][0]
    if invalid == 'empty': state['found'] = []
    elif invalid == 'two_prefix_matches':
        other = copy.deepcopy(item); other['id'] = SNAPSHOT[:8] + '0'*56
        state['found'].append(other)
    elif invalid == 'different_id': item['id'] = 'a'*64
    elif invalid == 'short_confirmed_id': item['id'] = SNAPSHOT[:8]
    elif invalid == 'invalid_confirmed_id': item['id'] = 'z'*64
    elif invalid == 'wrong_run_tag': item['tags'] = ['documind-ai', 'daily-wrong-run']
    elif invalid == 'missing_app_tag': item['tags'] = [RUN]
    elif invalid == 'extra_tag': item['tags'].append('unrelated-app')
    elif invalid == 'duplicate_tag': item['tags'] = ['documind-ai', 'documind-ai']
    elif invalid == 'tags_string': item['tags'] = 'documind-ai ' + RUN
    elif invalid == 'tag_object': item['tags'] = ['documind-ai', {}]
    elif invalid == 'wrong_path': item['paths'] = ['/other-project']
    elif invalid == 'extra_path': item['paths'].append('/other-project')
    elif invalid == 'nonarray': state['found'] = item
    elif invalid == 'nondict': state['found'] = [None]
    elif invalid == 'invalid_json': state['raw_snapshots'] = 'do-not-log-secret'
    elif invalid == 'duplicate_key':
        state['raw_snapshots'] = '[{"id":"bad","id":"' + SNAPSHOT + '"}]'
    with pytest.raises(backup.BackupError, match='restic_snapshot_not_confirmed') as error:
        backup.upload(DESTINATION, RUN, env)
    assert len(calls) == 2 and 'do-not-log' not in str(error.value)
    assert capsys.readouterr().out == ''


def test_full_summary_cannot_resolve_to_a_different_id_with_same_prefix(restic):
    state, calls, env = restic
    state['messages'][-1]['snapshot_id'] = SNAPSHOT
    state['found'][0]['id'] = SNAPSHOT[:8] + '0'*56
    with pytest.raises(backup.BackupError): backup.upload(DESTINATION, RUN, env)


def test_exact_tags_can_be_returned_in_either_order(restic):
    state, calls, env = restic
    state['found'][0]['tags'].reverse()
    assert backup.upload(DESTINATION, RUN, env) == SNAPSHOT
