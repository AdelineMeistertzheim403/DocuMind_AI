"""No Docker, B2, credentials or network: simulate the orchestration boundary."""
import json
import subprocess
from pathlib import Path

import pytest

from tools import public_beta_backup as backup
from tools import public_beta_restic_guard as guard

REPO = 'a' * 64
SNAPSHOT = 'b' * 64


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    root = tmp_path / 'release'
    root.mkdir()
    control = tmp_path / 'recovery-state.json'
    control.write_text('{"format":1,"state":"ready"}', encoding='utf-8')
    password = tmp_path / 'password'
    password.write_text('synthetic-password', encoding='utf-8')
    password.chmod(0o600)
    env_file = tmp_path / 'public-beta.env'
    env_file.write_text(
        f"RESTIC_REPOSITORY=b2:test-bucket:/public-beta\nRESTIC_PASSWORD_FILE='{password.as_posix()}'\n"
        f'B2_ACCOUNT_ID=synthetic-id\nB2_ACCOUNT_KEY=synthetic-key\n'
        f'DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID={REPO}\n', encoding='utf-8')
    env_file.chmod(0o600)
    for name in ('.env.public-beta', '.env.public-beta.images'):
        (root / name).write_text('SYNTHETIC=true\n', encoding='utf-8')
    monkeypatch.setattr(backup, 'CONTROL', control)
    monkeypatch.setattr(backup, 'RESTIC_ENV', env_file)
    monkeypatch.setenv('RESTIC_PASSWORD', 'ambient-secret-must-not-propagate')
    monkeypatch.setenv('COMPOSE_PROJECT_NAME', 'documind-prod')
    config = {'name': backup.PROJECT, 'services': {'db': {'volumes': [], 'environment': {
        'POSTGRES_DB': 'documind_public_beta'}}, 'api': {
        'environment': {'RECOVERY_STATE_PATH': '/run/documind/recovery-state.json'},
        'volumes': [{'type': 'bind', 'source': str(control), 'target': '/run/documind/recovery-state.json',
                     'read_only': True}]}}, 'volumes': {}}
    for service, target, volume in (
        ('db', '/var/lib/postgresql/data', 'public_beta_database'),
        ('api', '/app/var', 'public_beta_documents'),
        ('api', '/app/lifecycle', 'public_beta_lifecycle'),
    ):
        config['services'][service]['volumes'].append({'type': 'volume', 'source': volume, 'target': target})
        config['volumes'][volume] = {'name': f'{backup.PROJECT}_{volume}'}
    state = {'calls': [], 'config': config, 'repo': REPO, 'version': 5, 'keys': backup.KEYS,
             'remote': True, 'error': False, 'summary': SNAPSHOT, 'env_file': env_file,
             'root': root, 'control': control}

    def run(argv, **kwargs):
        state['calls'].append(argv)
        env = kwargs['env']
        assert 'RESTIC_PASSWORD' not in env
        assert 'COMPOSE_PROJECT_NAME' not in env
        if argv[0] == 'restic':
            assert env['B2_ACCOUNT_ID'] == 'synthetic-id'
            assert env['B2_ACCOUNT_KEY'] == 'synthetic-key'
            assert env['RESTIC_REPOSITORY'] == 'b2:test-bucket:/public-beta'
            assert Path(env['RESTIC_PASSWORD_FILE']) == password
            stage = argv[1]
            if state.get('network') == stage:
                return subprocess.CompletedProcess(argv, 1, 'synthetic-key', 'synthetic-password')
            if stage == 'cat':
                output = json.dumps({'id': state['repo']})
            elif stage == 'backup':
                state['uploaded_paths'] = argv[7:]
                state['tags'] = [argv[4], argv[6]]
                output = json.dumps({'message_type': 'summary', 'snapshot_id': state['summary']})
                if state['error']:
                    output += '\n' + json.dumps({'message_type': 'error', 'error': 'synthetic-key'})
            elif stage == 'snapshots':
                output = json.dumps([{'id': state.get('remote_id', SNAPSHOT),
                                      'tags': state['tags'], 'paths': state['uploaded_paths']}]
                                    if state['remote'] else [])
            else:
                pytest.fail('Unexpected Restic command')
        else:
            assert env['RECOVERY_CONTROL_FILE'] == str(control)
            output = json.dumps(config) if 'config' in argv else ''
        return subprocess.CompletedProcess(argv, 0, output, state.get('stderr', '') if argv[0] == 'restic' else '')

    def capture(compose, destination, env, *, include_lifecycle_keys):
        assert include_lifecycle_keys is True
        destination.mkdir(parents=True)
        state['destination'] = destination
        (destination / 'manifest.json').write_text(json.dumps({
            'backup_format_version': state['version'],
            'lifecycle_keys': {k: {} for k in state['keys']}}), encoding='utf-8')
        (destination / 'recovery-state.json').write_bytes(control.read_bytes())
        if state.get('capture_fail'):
            raise ValueError('synthetic capture failure')
        return destination

    def verify(destination, **kwargs):
        assert kwargs['require_s2'] is True
        assert kwargs['compose'][kwargs['compose'].index('-p') + 1] == backup.PROJECT
        state['verified'] = True
        if state.get('invalid_s2'):
            raise SystemExit('synthetic invalid archive/hash')
        return {'capture_complete': True, 'quota_certified': True}

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(backup.backup_local, 'create_backup', capture)
    monkeypatch.setattr(backup.verify_snapshot, 'verify_snapshot', verify)
    return state


def execute(state):
    return backup.execute(state['root'], 'test-bucket', '/public-beta')


def assert_preserved(state):
    assert all('down' not in c and 'prune' not in c and 'forget' not in c for c in state['calls'])
    assert not any(c[-3:] == ['start', 'api', 'web'] for c in state['calls'])
    if 'destination' in state:
        assert (state['destination'] / 'manifest.json').exists()


def test_success_uses_current_capture_and_confirms_remote(scenario):
    old = scenario['root'] / 'var/backups/old'
    old.mkdir(parents=True)
    result = execute(scenario)
    assert result['snapshot_id'] == SNAPSHOT
    assert result['backup_dir'] == str(scenario['destination'])
    assert str(old) not in scenario['uploaded_paths']
    assert str(scenario['control']) in scenario['uploaded_paths']
    assert scenario['verified']
    assert_preserved(scenario)


@pytest.mark.parametrize('stage', ['cat', 'backup', 'snapshots'])
def test_network_failure_preserves_local_and_never_restarts(scenario, stage):
    scenario['network'] = stage
    with pytest.raises((backup.BackupError, guard.ResticGuardError)):
        execute(scenario)
    assert_preserved(scenario)


def test_wrong_repository_refused_before_stop(scenario):
    scenario['repo'] = 'c' * 64
    with pytest.raises(guard.ResticGuardError, match='repository_id_mismatch'):
        execute(scenario)
    assert not any('stop' in c for c in scenario['calls'])


@pytest.mark.parametrize('mutation', ['version', 'keys', 'invalid_s2', 'capture_fail'])
def test_invalid_backup_never_uploaded(scenario, mutation):
    scenario[mutation] = {'version': 4, 'keys': {'keys/admission.key'},
                          'invalid_s2': True, 'capture_fail': True}[mutation]
    with pytest.raises((backup.BackupError, ValueError, SystemExit)):
        execute(scenario)
    assert not any(c[:2] == ['restic', 'backup'] for c in scenario['calls'])
    assert_preserved(scenario)


@pytest.mark.parametrize('mutation,value', [('remote', False), ('error', True), ('summary', None),
                                          ('remote_id', 'c' * 64), ('stderr', 'synthetic-key')])
def test_remote_proof_and_restic_errors_fail_closed(scenario, mutation, value):
    scenario[mutation] = value
    with pytest.raises((backup.BackupError, guard.ResticGuardError)):
        execute(scenario)
    assert_preserved(scenario)


def test_wrong_bucket_cannot_be_pinned(scenario):
    original = scenario['env_file'].read_bytes()
    with pytest.raises(guard.ResticGuardError, match='destination_mismatch'):
        guard.record_public_beta_repository_id(scenario['env_file'], bucket='wrong', prefix='/public-beta')
    assert scenario['env_file'].read_bytes() == original
    assert not scenario['calls']


def test_existing_id_never_replaced(scenario):
    original = scenario['env_file'].read_bytes()
    scenario['repo'] = 'c' * 64
    with pytest.raises(guard.ResticGuardError, match='conflict'):
        guard.record_public_beta_repository_id(scenario['env_file'], bucket='test-bucket', prefix='/public-beta')
    assert scenario['env_file'].read_bytes() == original


def test_existing_matching_id_is_not_rewritten(scenario):
    original = scenario['env_file'].read_bytes()
    guard.record_public_beta_repository_id(scenario['env_file'], bucket='test-bucket', prefix='/public-beta')
    assert scenario['env_file'].read_bytes() == original


def test_short_restic_id_resolves_to_full_remote_id(scenario):
    scenario['summary'] = SNAPSHOT[:8]
    assert execute(scenario)['snapshot_id'] == SNAPSHOT


@pytest.mark.parametrize('prefix', ['/other-public-beta', '/public-beta/../prod', '//public-beta'])
def test_wrong_or_unsafe_prefix_refused_before_any_command(scenario, prefix):
    with pytest.raises(guard.ResticGuardError):
        backup.execute(scenario['root'], 'test-bucket', prefix)
    assert not scenario['calls']


@pytest.mark.parametrize('problem', ['volume', 'latch_mount', 'latch_content'])
def test_unsafe_local_configuration_refused_before_stop(scenario, problem):
    if problem == 'volume':
        scenario['config']['volumes']['public_beta_database']['name'] = 'documind-prod_database'
    elif problem == 'latch_mount':
        scenario['config']['services']['api']['volumes'][0]['source'] = '/wrong/recovery-state.json'
    else:
        scenario['control'].write_text('{"state":"ready"}', encoding='utf-8')
    with pytest.raises((backup.BackupError, ValueError)):
        execute(scenario)
    assert not any('stop' in c for c in scenario['calls'])


def test_cli_failure_never_prints_secret_or_traceback(scenario, monkeypatch, capsys):
    from contextlib import nullcontext
    scenario['network'] = 'backup'
    monkeypatch.setattr(backup, 'operator_lock', nullcontext)
    monkeypatch.setattr('sys.argv', ['backup', '--root', str(scenario['root']),
                                   '--expected-bucket', 'test-bucket', '--expected-prefix', '/public-beta'])
    assert backup.main() == 1
    captured = capsys.readouterr()
    assert 'synthetic' not in captured.out + captured.err
    assert 'Traceback' not in captured.out + captured.err
    assert_preserved(scenario)
