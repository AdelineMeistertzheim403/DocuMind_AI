from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from tools import backup_production as backup
from tools import backup_local
from tests.test_deployment import release


@pytest.fixture
def run_backup(tmp_path, monkeypatch):
    events = []; state = {'environment_loader': backup.restic_environment}; root = tmp_path / 'vps'; root.mkdir()
    env = {'RESTIC_PASSWORD': 'never-log-password', 'B2_ACCOUNT_KEY': 'never-log-key'}
    class Active:
        bundle = root / 'releases' / 'active'
        compose = ['docker', 'compose', '-p', 'documind-prod']
        release = release()
        env = {'PATH': 'safe'}
        def __init__(self, path): assert path == root
        def preflight(self, require_healthy=True): events.append(('preflight', require_healthy))
        def call(self, *args):
            events.append(('compose', args))
            if args[0] == 'stop' and state.get('stop_fail'): raise backup.BackupError('command_failed')
            if args[0] == 'exec': return '1000'
            if 'du' in args: return '1000 /app/var/documents'
            return ''
        def restart(self):
            events.append(('restart',))
            if state.get('restart_fail'): raise backup.BackupError('service_not_healthy')
            if state.get('https_fail'): raise backup.BackupError('https_health_failed')
            events.append(('healthy',))
    @contextmanager
    def lock(path):
        if state.get('locked'): raise backup.BackupError('deployment_or_backup_already_running')
        events.append(('lock',))
        try: yield
        finally: events.append(('unlock',))
    def create(compose, destination, env):
        events.append(('snapshot',))
        if state.get('local_failure'):
            def actual_command(command, **kwargs):
                stage = 'pg_dump' if 'pg_dump' in ' '.join(command) else 'archive'
                events.append((stage,))
                if stage == state['local_failure']:
                    raise subprocess.CalledProcessError(1, command, stderr='never-log-password')
                kwargs['stdout'].write(b'dump')
            monkeypatch.setattr(backup_local.subprocess, 'check_output', lambda *a, **k: '')
            monkeypatch.setattr(backup_local.subprocess, 'run', actual_command)
            return backup_local.create_backup(compose, destination, env)
        destination.mkdir(parents=True)
        hashes = {}
        for name in ('database.dump', 'documents.tar.gz'):
            data = b'local test only'; (destination / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        (destination / 'manifest.json').write_text(json.dumps({'migration': '0006', 'sha256': hashes}))
    def command(argv, environment=None, timeout=300):
        assert argv[0] == 'restic'
        assert environment == env
        events.append(('restic', tuple(argv[1:])))
        if 'backup' in argv and state.get('upload_fail'): raise backup.BackupError('command_failed')
        if 'backup' in argv:
            state['run_id'] = argv[argv.index('documind-ai') + 2]
            state['destination'] = argv[-1]
            return json.dumps({'message_type': 'summary', 'snapshot_id': 'f'*64})
        if 'snapshots' in argv:
            return json.dumps([{'id': 'e'*64 if state.get('bad_snapshot') else 'f'*64,
                'tags': ['documind-ai', state['run_id']], 'paths': [state['destination']]}])
        return '{}'
    monkeypatch.setattr(backup, 'ActiveRelease', Active)
    monkeypatch.setattr(backup, 'deployment_lock', lock)
    monkeypatch.setattr(backup, 'local_backup_deadline', nullcontext)
    monkeypatch.setattr(backup, 'load_helper', lambda *a: SimpleNamespace(create_backup=create))
    monkeypatch.setattr(backup, 'restic_environment', lambda: env)
    monkeypatch.setattr(backup, 'command', command)
    monkeypatch.setattr(backup.shutil, 'disk_usage', lambda p: SimpleNamespace(free=100*1024**3))
    return root, events, state


def test_success_requires_restart_and_verified_restic_snapshot(run_backup):
    root, events, state = run_backup; report = {}
    backup.execute(root, report)
    assert report['status'] == 'success' and report['snapshot_id'] == 'f'*64
    assert report['restart_healthy'] is True and not backup.marker_path(root).exists()
    assert events.index(('snapshot',)) < events.index(('restart',))
    assert events.index(('healthy',)) < next(i for i, e in enumerate(events) if e[0] == 'restic' and e[1][0] == 'backup')
    assert events[0] == ('lock',) and events[-1] == ('unlock',)
    assert not any(word in json.dumps(report) for word in ('never-log-password', 'never-log-key'))


@pytest.mark.parametrize('failure', ['pg_dump', 'archive', 'upload_fail', 'bad_snapshot', 'restart_fail', 'https_fail', 'stop_fail'])
def test_failure_always_restarts_app_and_never_reports_success(run_backup, failure):
    root, events, state = run_backup; report = {'status': 'failed'}
    if failure in ('pg_dump', 'archive'): state['local_failure'] = failure
    else: state[failure] = True
    with pytest.raises((backup.BackupError, subprocess.CalledProcessError)):
        backup.execute(root, report)
    assert ('restart',) in events and report['status'] == 'failed'
    if failure in ('pg_dump', 'archive', 'restart_fail', 'https_fail', 'stop_fail'):
        assert not any(e[0] == 'restic' and e[1][0] == 'backup' for e in events)
    if failure in ('restart_fail', 'https_fail'):
        assert backup.marker_path(root).exists() and report['phase'] == 'restart'


def test_lock_conflict_touches_no_service(run_backup):
    root, events, state = run_backup; state['locked'] = True
    with pytest.raises(backup.BackupError, match='already_running'): backup.execute(root, {})
    assert events == []


def test_real_lock_uses_same_file_as_deployer(tmp_path, monkeypatch):
    def busy(*a): raise BlockingIOError()
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(flock=busy, LOCK_EX=1, LOCK_NB=2))
    with pytest.raises(backup.BackupError, match='already_running'):
        with backup.deployment_lock(tmp_path): pytest.fail('Lock acquired')
    assert (tmp_path / 'deployment.lock').exists()


def test_emergency_resume_uses_marker_without_backup_or_transfer(run_backup):
    root, events, state = run_backup; marker = backup.marker_path(root)
    marker.parent.mkdir(); marker.write_text(json.dumps({'bundle': str(root / 'releases/active')}))
    report = {}; backup.resume(root, report)
    assert report['phase'] == 'services_resumed' and ('preflight', False) in events
    assert ('restart',) in events and not marker.exists()
    assert not any(e[0] in ('restic', 'snapshot') for e in events)


def test_resume_refuses_changed_current_release(run_backup):
    root, events, state = run_backup; marker = backup.marker_path(root)
    marker.parent.mkdir(); marker.write_text(json.dumps({'bundle': '/unexpected/release'}))
    with pytest.raises(backup.BackupError, match='release_changed'): backup.resume(root, {})
    assert ('restart',) not in events and marker.exists()


@pytest.mark.parametrize('text', ['RESTIC_PASSWORD=secret\n', 'RESTIC_REPOSITORY=b2:bucket\n',
    'RESTIC_REPOSITORY=b2:bucket\nRESTIC_PASSWORD_COMMAND=echo-secret',
    'RESTIC_REPOSITORY=b2:bucket\nRESTIC_PASSWORD=a b',
    'RESTIC_PASSWORD=secret\nRESTIC_PASSWORD=second'])
def test_invalid_secret_file_rejected_without_logging(tmp_path, text, capsys):
    file = tmp_path / 'secrets'; file.write_text(text); file.chmod(0o600)
    with pytest.raises(backup.BackupError): backup.restic_environment(file)
    assert capsys.readouterr().out == ''


def test_secrets_only_pass_to_restic_as_environment(tmp_path, monkeypatch):
    file = tmp_path / 'secrets'; file.write_text("RESTIC_REPOSITORY='b2:existing:repo'\nRESTIC_PASSWORD='literal # secret'\nB2_ACCOUNT_KEY=secret\n")
    file.chmod(0o600); monkeypatch.setenv('RESTIC_PASSWORD', 'ambient-secret')
    env = backup.restic_environment(file)
    assert env['RESTIC_PASSWORD'] == 'literal # secret'
    assert 'RESTIC_PASSWORD' not in backup.base_environment()


@pytest.mark.parametrize('state', ['missing', 'directory', 'outside', 'incomplete'])
def test_missing_or_incoherent_current_refused(tmp_path, state, monkeypatch):
    root = tmp_path / 'vps'; root.mkdir()
    if state == 'directory': (root / 'current').mkdir()
    elif state in ('outside', 'incomplete'):
        destination = tmp_path / 'outside' if state == 'outside' else root / 'releases/broken'
        destination.mkdir(parents=True)
        # Symlink permissions differ on Windows; emulate only the filesystem pointer for this unit test.
        pointer = root / 'current'
        original_link, original_dir, original_resolve = Path.is_symlink, Path.is_dir, Path.resolve
        monkeypatch.setattr(Path, 'is_symlink', lambda p: True if p == pointer else original_link(p))
        monkeypatch.setattr(Path, 'is_dir', lambda p: True if p == pointer else original_dir(p))
        monkeypatch.setattr(Path, 'resolve', lambda p: destination if p == pointer else original_resolve(p))
    with pytest.raises(backup.BackupError): backup.ActiveRelease(root)


def test_restart_command_cannot_modify_database_or_pull_images(monkeypatch,tmp_path):
    active = object.__new__(backup.ActiveRelease); events = []
    active.root = tmp_path
    active.preflight = lambda **kwargs: None
    active.call = lambda *args: events.append(args)
    active.healthy = lambda: events.append(('healthy',))
    monkeypatch.setattr(backup, 'https_health', lambda: events.append(('https',)))
    active.restart()
    assert events[0] == ('up', '-d', '--no-deps', '--no-recreate', '--pull', 'never', '--wait', '--wait-timeout', '180', 'api', 'web')
    assert events[1:] == [('healthy',), ('https',)]


@pytest.mark.parametrize('failure', [False, True])
def test_snapshot_deadline_is_always_cancelled(monkeypatch, failure):
    events = []; handlers = []
    monkeypatch.setattr(backup.signal, 'SIGALRM', 14, raising=False)
    def handler(number, action): handlers.append(action); return 'previous-handler'
    monkeypatch.setattr(backup.signal, 'signal', handler)
    monkeypatch.setattr(backup.signal, 'alarm', lambda delay: events.append(delay), raising=False)
    if failure:
        with pytest.raises(backup.BackupError, match='local_backup_timeout'):
            with backup.local_backup_deadline(): handlers[0](14, None)
    else:
        with backup.local_backup_deadline(): pass
    assert events == [1800, 0] and handlers[-1] == 'previous-handler'


@pytest.mark.parametrize('failure', [None, 'transient', 'permanent', 'tls'])
def test_real_https_health_probe_is_secure_and_bounded(monkeypatch, failure):
    events = []; clock = [0]
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    class Opener:
        def open(self, url, timeout):
            assert url == backup.HEALTH_URL and timeout == 5
            events.append(url)
            if failure == 'tls': raise backup.urllib.error.URLError('untrusted certificate, secret')
            if failure == 'permanent' or (failure == 'transient' and len(events) == 1):
                raise backup.urllib.error.HTTPError(url, 403 if failure == 'permanent' else 503, 'secret', {}, None)
            return Response()
    monkeypatch.setattr(backup.urllib.request, 'build_opener', lambda *a: Opener())
    monkeypatch.setattr(backup.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(backup.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    if failure in ('permanent', 'tls'):
        with pytest.raises(backup.BackupError) as error: backup.https_health()
        assert 'secret' not in str(error.value)
        assert len(events) == 1
    else:
        backup.https_health()
        assert len(events) == (2 if failure else 1)


def test_systemd_timer_and_no_retention_or_destructive_commands():
    timer = Path('ops/systemd/documind-backup.timer').read_text()
    service = Path('ops/systemd/documind-backup.service').read_text()
    assert 'OnCalendar=*-*-* 03:00:00 Europe/Paris' in timer and 'Persistent=true' in timer
    assert 'ExecStopPost=' in service and '--resume' in service and 'OnFailure=documind-backup-alert.service' in service
    assert 'EnvironmentFile' not in service  # Secrets are read only by the Restic environment loader.
    assert 'ExecStart=/usr/bin/python3 /srv/documind-ai/ops/backup_production.py' in service
    assert 'deploy_production.py' not in service and 'alembic' not in service
    assert backup.SECRET_FILE == Path('/home/debian/.config/restic/documind.env')
    text = Path('tools/backup_production.py').read_text()
    assert "'forget'" not in text and "'prune'" not in text and "'down'" not in text


def test_subprocess_failures_never_echo_secrets(monkeypatch, capsys):
    monkeypatch.setattr(backup.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='secret', stderr='secret'))
    with pytest.raises(backup.BackupError) as error: backup.command(['restic', 'backup'])
    assert str(error.value) == 'command_failed' and capsys.readouterr().out == ''


def test_main_returns_failure_and_redacts_external_exception(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['backup_production.py', '--root', str(tmp_path)])
    monkeypatch.setattr(backup, 'validate_root', lambda *a: None)
    monkeypatch.setattr(backup.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(backup.os, 'umask', lambda *a: 0)
    def failed(*a): raise RuntimeError('never-log-password never-log-key')
    monkeypatch.setattr(backup, 'execute', failed)
    assert backup.main() == 1
    output = capsys.readouterr()
    assert 'never-log' not in output.out + output.err
    assert json.loads(output.out)['error'] == 'backup_operation_failed'


@pytest.mark.parametrize('invalid', [None, 'pins', 'compose_image', 'compose_volume', 'container_image',
    'container_volume', 'other_project', 'extra_service', 'schema', 'failed_release'])
def test_real_active_preflight_confirms_release_and_project_boundaries(tmp_path, monkeypatch, invalid):
    root = tmp_path / 'vps'; bundle = root / 'releases/active'; bundle.mkdir(parents=True)
    pointer = root / 'current'
    original_link, original_dir, original_resolve = Path.is_symlink, Path.is_dir, Path.resolve
    monkeypatch.setattr(Path, 'is_symlink', lambda p: True if p == pointer else original_link(p))
    monkeypatch.setattr(Path, 'is_dir', lambda p: True if p == pointer else original_dir(p))
    monkeypatch.setattr(Path, 'resolve', lambda p: bundle if p == pointer else original_resolve(p))
    (root / '.env.production').write_text('private=true'); (root / '.env.production').chmod(0o600)
    data = release()
    for name in ('backup_local.py', 'release_manifest.py'):
        (bundle / name).write_bytes((Path('tools') / name).read_bytes())
    (bundle / 'compose.production.yaml').write_bytes(Path('compose.production.yaml').read_bytes())
    (bundle / 'release.json').write_text(json.dumps(data))
    pins = {name: data['images'][component] for component, name in
            [('backend', 'BACKEND_IMAGE'), ('frontend', 'FRONTEND_IMAGE'), ('postgres', 'POSTGRES_IMAGE')]}
    if invalid == 'pins': pins['BACKEND_IMAGE'] = 'unreviewed:latest'
    (bundle / 'images.env').write_text(''.join(f'{k}={v}\n' for k, v in pins.items()))
    (bundle / 'deployment-report.json').write_text(json.dumps({'status': 'failed' if invalid == 'failed_release' else 'success', 'git_sha': data['git_sha']}))
    config = {'name': backup.PROJECT, 'services': {}, 'volumes': {}}
    containers = []
    for service, component in [('db', 'postgres'), ('api', 'backend'), ('web', 'frontend')]:
        volumes, mounts = [], []
        if service != 'web':
            logical = 'production_database' if service == 'db' else 'production_documents'
            target = '/var/lib/postgresql/data' if service == 'db' else '/app/var'
            volumes = [{'type': 'volume', 'source': logical, 'target': target}]
            config['volumes'][logical] = {'name': backup.PROJECT + '_' + logical}
            mounts = [{'Type': 'volume', 'Name': backup.PROJECT + '_' + logical, 'Destination': target}]
        config['services'][service] = {'image': data['images'][component], 'volumes': volumes}
        containers.append({'Image': service + '-id', 'Config': {'Labels': {
            'com.docker.compose.project': backup.PROJECT, 'com.docker.compose.service': service,
            'com.docker.compose.project.config_files': str(bundle / 'compose.production.yaml')}},
            'Mounts': mounts, 'State': {'Running': True, 'Health': {'Status': 'healthy'}}})
    if invalid == 'compose_image': config['services']['api']['image'] = 'unreviewed:latest'
    elif invalid == 'compose_volume': config['volumes']['production_documents']['name'] = 'other-project-volume'
    elif invalid == 'container_image': containers[1]['Image'] = 'other-image'
    elif invalid == 'container_volume': containers[1]['Mounts'][0]['Name'] = 'other-project-volume'
    elif invalid == 'other_project': containers[1]['Config']['Labels']['com.docker.compose.project'] = 'other-project'
    elif invalid == 'extra_service': config['services']['other-app'] = {}
    calls = []
    def command(argv, env=None, timeout=300):
        calls.append(argv)
        assert not (set(env or {}) & backup.RESTIC_KEYS)
        if 'config' in argv: return json.dumps(config)
        if argv[:3] == ['docker', 'ps', '-aq']: return 'db\napi\nweb'
        if argv[:2] == ['docker', 'inspect']:
            return json.dumps(containers if len(argv) == 5 else [next(c for c in containers if c['Config']['Labels']['com.docker.compose.service'] == argv[-1])])
        if argv[:3] == ['docker', 'image', 'inspect']:
            return {'postgres': 'db-id', 'backend': 'api-id', 'frontend': 'web-id'}[next(k for k, v in data['images'].items() if v == argv[3])]
        if 'ps' in argv: return argv[-1]
        if 'exec' in argv: return '0005' if invalid == 'schema' else '0006'
        pytest.fail('Unexpected Docker operation')
    monkeypatch.setattr(backup, 'command', command)
    if invalid:
        with pytest.raises(backup.BackupError): backup.ActiveRelease(root).preflight()
    else:
        backup.ActiveRelease(root).preflight()
        assert not (bundle / 'deploy_production.py').exists()  # No new app release/helper required.
    # Preflight must stay read-only, always explicitly scoped to the named project.
    assert not any('stop' in argv or 'up' in argv or 'run' in argv or 'down' in argv for argv in calls)


@pytest.fixture
def exported_restic(tmp_path):
    password = tmp_path / 'password'
    password.write_text('never-read-or-log-password'); password.chmod(0o600)
    config = tmp_path / 'documind.env'
    config.write_text("export RESTIC_REPOSITORY='b2:existing-bucket:documind'\n"
        f"export RESTIC_PASSWORD_FILE='{password}'\n"
        "export B2_ACCOUNT_ID='existing-id'\nB2_ACCOUNT_KEY='never-log-b2-key'\n")
    config.chmod(0o600)
    return config, password


def test_existing_export_password_file_config_is_loaded_without_opening_password(exported_restic, monkeypatch, capsys):
    config, password = exported_restic
    original = Path.open
    def opened(path, *args, **kwargs):
        assert path != password, 'Only Restic is allowed to read the password file'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opened)
    env = backup.restic_environment(config)
    assert env['RESTIC_PASSWORD_FILE'] == str(password)
    assert 'RESTIC_PASSWORD' not in env
    assert env['B2_ACCOUNT_ID'] == 'existing-id' and env['B2_ACCOUNT_KEY'] == 'never-log-b2-key'
    assert capsys.readouterr().out == ''


def test_existing_password_file_config_works_with_simulated_backup_confirmation(run_backup, exported_restic, monkeypatch):
    root, events, state = run_backup
    config, password = exported_restic
    environment = state['environment_loader'](config)
    monkeypatch.setattr(backup, 'restic_environment', lambda: environment)
    run_id = {}; calls = []
    def restic(argv, env=None, timeout=300):
        assert env == environment and 'RESTIC_PASSWORD' not in env
        assert str(password) not in argv and 'never-log-b2-key' not in argv
        calls.append(argv)
        if argv[1] == 'backup':
            run_id['tag'], run_id['path'] = argv[-2], argv[-1]
            return json.dumps({'message_type': 'summary', 'snapshot_id': 'a'*64})
        if argv[1] == 'snapshots':
            return json.dumps([{'id': 'a'*64, 'tags': ['documind-ai', run_id['tag']], 'paths': [run_id['path']]}])
        return '{}'
    monkeypatch.setattr(backup, 'command', restic)
    report = {}; backup.execute(root, report)
    assert report['status'] == 'success' and report['snapshot_id'] == 'a'*64
    assert ('restart',) in events and [argv[1] for argv in calls] == ['cat', 'backup', 'snapshots']
    assert 'never-log' not in json.dumps(report)


@pytest.mark.parametrize('invalid', ['missing', 'directory', 'outside', 'relative', 'traversal', 'both', 'duplicate'])
def test_password_file_invalid_or_ambiguous_configuration_refused(exported_restic, tmp_path, invalid, capsys):
    config, password = exported_restic
    text = config.read_text()
    if invalid == 'missing': password.unlink()
    elif invalid == 'directory': password.unlink(); password.mkdir()
    elif invalid == 'outside': text = text.replace(str(password), str(tmp_path.parent / 'password'))
    elif invalid == 'relative': text = text.replace(str(password), 'password')
    elif invalid == 'traversal': text = text.replace(str(password), str(tmp_path / 'nested') + '/../password')
    elif invalid == 'both': text += "RESTIC_PASSWORD='conflicting-secret'\n"
    elif invalid == 'duplicate': text += f"RESTIC_PASSWORD_FILE='{password}'\n"
    config.write_text(text)
    with pytest.raises(backup.BackupError) as error: backup.restic_environment(config)
    assert 'never-log' not in str(error.value)
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('mode', [0o644, 0o640, 0o604, 0o666, 0o000, 0o200])
def test_password_file_posix_permissions_are_private(exported_restic, monkeypatch, mode):
    config, password = exported_restic
    original = Path.stat
    def stat(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == password: return SimpleNamespace(st_mode=0o100000 | mode)
        if path == config: return SimpleNamespace(st_mode=0o100600)
        return result
    # Simulate POSIX checks on Windows too without changing pathlib's OS implementation.
    monkeypatch.setattr(backup, 'os', SimpleNamespace(name='posix', environ={}))
    monkeypatch.setattr(Path, 'stat', stat)
    with pytest.raises(backup.BackupError, match='private_file_required'): backup.restic_environment(config)


@pytest.mark.parametrize('mode', [0o400, 0o600])
def test_private_readable_password_modes_are_accepted(exported_restic, monkeypatch, mode):
    config, password = exported_restic
    original = Path.stat
    def stat(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == password: return SimpleNamespace(st_mode=0o100000 | mode)
        if path == config: return SimpleNamespace(st_mode=0o100600)
        return result
    monkeypatch.setattr(backup, 'os', SimpleNamespace(name='posix', environ={}))
    monkeypatch.setattr(Path, 'stat', stat)
    assert backup.restic_environment(config)['RESTIC_PASSWORD_FILE'] == str(password)


@pytest.mark.parametrize('indirect', [False, True])
def test_password_file_symlink_or_symlink_parent_refused(exported_restic, monkeypatch, indirect):
    config, password = exported_restic
    original = Path.resolve
    if indirect:
        replacement = password.parent / 'linked' / 'password'
        config.write_text(config.read_text().replace(str(password), str(replacement)))
    else: replacement = password
    monkeypatch.setattr(Path, 'resolve', lambda path: password.parent.parent / 'elsewhere/password'
                        if path == replacement else original(path))
    with pytest.raises(backup.BackupError, match='unauthorized_restic_password_path'):
        backup.restic_environment(config)


def test_password_file_itself_must_not_be_a_symlink(exported_restic, monkeypatch):
    config, password = exported_restic
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: True if path == password else original(path))
    with pytest.raises(backup.BackupError, match='private_file_required'): backup.restic_environment(config)


@pytest.mark.parametrize('line', [
    'export RESTIC_PASSWORD=$(cat /secret)',
    'RESTIC_PASSWORD="$(cat /secret)"',
    'RESTIC_PASSWORD=`cat /secret`',
    'RESTIC_PASSWORD="${OTHER_SECRET}"',
    'RESTIC_PASSWORD=$OTHER_SECRET',
    'RESTIC_PASSWORD=literal;id',
    'RESTIC_PASSWORD=literal && id',
    'RESTIC_PASSWORD=literal | id',
    'RESTIC_PASSWORD=literal > /tmp/file',
    "RESTIC_PASSWORD='one''two'",
    'RESTIC_PASSWORD="unterminated',
    'RESTIC_PASSWORD=abc#ambiguous-comment',
    'export RESTIC_PASSWORD_COMMAND=print-secret',
    'RESTIC_INSECURE_TLS=true',
    'RESTIC_OPTIONS=--insecure-tls',
    'B2_ALLOW_HTTP=true',
    'SSL_CERT_FILE=/untrusted/ca',
    'source /other/file',
    'export B2_ACCOUNT_ID=id B2_ACCOUNT_KEY=secret',
])
def test_shell_expressions_unknown_keys_and_tls_bypass_refused(tmp_path, line, capsys):
    config = tmp_path / 'documind.env'
    config.write_text("RESTIC_REPOSITORY=b2:existing:documind\n" + line + '\n')
    config.chmod(0o600)
    with pytest.raises(backup.BackupError): backup.restic_environment(config)
    assert capsys.readouterr().out == ''


def test_insecure_repository_scheme_refused(tmp_path):
    config = tmp_path / 'documind.env'
    config.write_text('RESTIC_REPOSITORY=s3:http://insecure.example/bucket\nRESTIC_PASSWORD=literal\n')
    config.chmod(0o600)
    with pytest.raises(backup.BackupError, match='secure_b2_repository_required'): backup.restic_environment(config)
