"""Daily DocuMind snapshot orchestration. No deployment, database restart or retention commands."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

PROJECT = 'documind-prod'
HEALTH_URL = 'https://documind.adelinemeistertzheim.fr/bff/health'
SECRET_FILE = Path('/home/debian/.config/restic/documind.env')
RESTIC_KEYS = {'RESTIC_REPOSITORY', 'RESTIC_PASSWORD', 'RESTIC_PASSWORD_FILE', 'B2_ACCOUNT_ID', 'B2_ACCOUNT_KEY',
               'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'AWS_REGION'}


class BackupError(Exception):
    pass


def command(argv, env=None, timeout=300):
    try:
        result = subprocess.run(argv, env=env, timeout=timeout, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError('command_unavailable_or_timeout') from None
    if result.returncode:
        raise BackupError('command_failed')
    return result.stdout


def base_environment():
    # Never pass B2/Restic secrets to Docker, the app or an alert hook.
    return {key: value for key, value in os.environ.items()
            if key in {'PATH', 'HOME', 'USER', 'LOGNAME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG',
                       'XDG_RUNTIME_DIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}}


def private_file(path):
    if not path.is_file() or path.is_symlink():
        raise BackupError('private_file_required')
    if os.name == 'posix':
        mode = path.stat().st_mode
        if mode & 0o077 or not mode & 0o400:
            raise BackupError('private_file_required')


def restic_environment(path=SECRET_FILE):
    private_file(path)
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        declaration = re.fullmatch(r'\s*(?:export[ \t]+)?([A-Z][A-Z0-9_]*)=(.*)', line)
        if not declaration:
            raise BackupError('invalid_restic_configuration')
        key, value = declaration.groups()
        # A single literal token only: no concatenation, continuation, expansion or commands.
        literal = r'''\s*(?:'[^']*'|"(?:[^"\\]|\\.)*"|[^\s'"\\;|&<>()`#]+)(?:\s+\#.*)?\s*'''
        if key not in RESTIC_KEYS or key in values or not re.fullmatch(literal, value):
            raise BackupError('invalid_restic_configuration')
        try:
            tokens = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise BackupError('invalid_restic_configuration') from None
        if len(tokens) != 1 or any(char in tokens[0] for char in ('$', '`', '\x00', '\n', '\r')):
            raise BackupError('invalid_restic_configuration')
        if not tokens[0]:
            raise BackupError('invalid_restic_configuration')
        values[key] = tokens[0]
    methods = {'RESTIC_PASSWORD', 'RESTIC_PASSWORD_FILE'} & values.keys()
    if not values.get('RESTIC_REPOSITORY') or not methods:
        raise BackupError('missing_restic_configuration')
    if len(methods) != 1:
        raise BackupError('conflicting_restic_password_methods')
    if not values['RESTIC_REPOSITORY'].startswith(('b2:', 's3:https://')):
        raise BackupError('secure_b2_repository_required')
    if 'RESTIC_PASSWORD_FILE' in values:
        password_file = Path(values['RESTIC_PASSWORD_FILE'])
        allowed = path.absolute().parent
        if not password_file.is_absolute() or '..' in password_file.parts:
            raise BackupError('unauthorized_restic_password_path')
        try:
            password_file.relative_to(allowed)
        except ValueError:
            raise BackupError('unauthorized_restic_password_path') from None
        # Reject indirect symlinks too, including an alias of the authorized directory itself.
        if allowed.resolve() != allowed or password_file.resolve() != password_file:
            raise BackupError('unauthorized_restic_password_path')
        private_file(password_file)  # stat only: Restic reads the password; Python never opens it.
    # Literal values only: no shell, expansion, command substitution, password command or TLS bypass.
    return {**base_environment(), **values}


@contextmanager
def deployment_lock(root):
    import fcntl
    with (root / 'deployment.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError('deployment_or_backup_already_running') from None
        yield


def load_helper(bundle, name):
    sys.dont_write_bytecode = True  # Read the active bundle without creating __pycache__ files in it.
    spec = importlib.util.spec_from_file_location('documind_active_' + name, bundle / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActiveRelease:
    def __init__(self, root):
        self.root = root
        pointer = root / 'current'
        if not pointer.is_symlink() or not pointer.is_dir():
            raise BackupError('current_release_missing')
        self.bundle = pointer.resolve()
        if self.bundle.parent != root / 'releases':
            raise BackupError('current_release_outside_releases')
        for name in ('compose.production.yaml', 'backup_local.py', 'release_manifest.py', 'release.json', 'images.env'):
            path = self.bundle / name
            if not path.is_file() or path.is_symlink():
                raise BackupError('incomplete_current_release')
        private_file(root / '.env.production')
        validator = load_helper(self.bundle, 'release_manifest')
        self.release = validator.validate_release(json.loads((self.bundle / 'release.json').read_text()))
        pins = dict(line.split('=', 1) for line in (self.bundle / 'images.env').read_text().splitlines() if '=' in line)
        for component, variable in validator.COMPONENTS.items():
            if pins.get(variable) != self.release['images'][component]:
                raise BackupError('current_image_pins_inconsistent')
        self.env = {**base_environment(), **{key: pins[key] for key in validator.COMPONENTS.values()},
                    'BFF_TRUSTED_PROXY_IPS': pins.get('BFF_TRUSTED_PROXY_IPS', ''),
                    'PRODUCTION_ENV_FILE': str(root / '.env.production')}
        self.compose = ['docker', 'compose', '--project-directory', str(root), '-p', PROJECT,
                        '--env-file', str(root / '.env.production'), '--env-file', str(self.bundle / 'images.env'),
                        '-f', str(self.bundle / 'compose.production.yaml')]

    def call(self, *args):
        return command(self.compose + list(args), self.env)

    def preflight(self, require_healthy=True):
        config = json.loads(self.call('config', '--format', 'json'))
        services = config['services']
        if set(services) != {'db', 'api', 'web'} or config['name'] != PROJECT:
            raise BackupError('unexpected_compose_project')
        for service, component in (('db', 'postgres'), ('api', 'backend'), ('web', 'frontend')):
            if services[service]['image'] != self.release['images'][component] or services[service].get('ports') or services[service].get('build'):
                raise BackupError('unexpected_compose_image_or_exposure')
        for service, logical, target in (('api', 'production_documents', '/app/var'),
                                         ('db', 'production_database', '/var/lib/postgresql/data')):
            mounts = services[service].get('volumes', [])
            if (len(mounts) != 1 or mounts[0].get('type') != 'volume' or mounts[0].get('source') != logical
                    or mounts[0].get('target') != target or config['volumes'][logical]['name'] != PROJECT + '_' + logical):
                raise BackupError('unexpected_compose_mounts')
        if services['web'].get('volumes'):
            raise BackupError('unexpected_compose_mounts')
        ids = command(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + PROJECT], self.env).splitlines()
        if len(ids) != 3:
            raise BackupError('unexpected_service_count')
        containers = json.loads(command(['docker', 'inspect', *ids], self.env))
        report = json.loads((self.bundle / 'deployment-report.json').read_text())
        if report.get('status') != 'success' or report.get('git_sha') != self.release['git_sha']:
            raise BackupError('current_release_not_successful')
        seen = set()
        for container in containers:
            labels = container['Config'].get('Labels', {})
            service = labels.get('com.docker.compose.service')
            if (service not in services or service in seen or labels.get('com.docker.compose.project') != PROJECT
                    or labels.get('com.docker.compose.oneoff', 'false').lower() != 'false'):
                raise BackupError('unexpected_container_identity')
            seen.add(service)
            if service != 'db' and labels.get('com.docker.compose.project.config_files') != str(self.bundle / 'compose.production.yaml'):
                raise BackupError('container_release_mismatch')
            component = {'api': 'backend', 'web': 'frontend', 'db': 'postgres'}[service]
            image = self.release['images'][component]
            if service == 'db':
                image = report.get('retained_database_image', image)
                if not re.fullmatch(r'registry\.adelinemeistertzheim\.fr/documind-ai/postgres@sha256:[a-f0-9]{64}', image):
                    raise BackupError('invalid_database_image')
            actual = command(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], self.env).strip()
            if container['Image'] != actual:
                raise BackupError('container_image_mismatch')
            mounts = [mount for mount in container['Mounts'] if mount['Type'] != 'tmpfs']
            expected = {'db': ('database', '/var/lib/postgresql/data'), 'api': ('documents', '/app/var')}.get(service)
            if expected:
                if (len(mounts) != 1 or mounts[0]['Type'] != 'volume' or mounts[0].get('Name') != PROJECT + '_production_' + expected[0]
                        or mounts[0]['Destination'] != expected[1]):
                    raise BackupError('unexpected_container_mounts')
            elif mounts:
                raise BackupError('unexpected_container_mounts')
        self.healthy(('db', 'api', 'web') if require_healthy else ('db',))
        revision = self.call('exec', '-T', 'db', 'sh', '-c',
            'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT version_num FROM alembic_version"').strip()
        if revision != self.release['schema_revision']:
            raise BackupError('live_schema_mismatch')

    def healthy(self, services=('db', 'api', 'web')):
        for service in services:
            ids = self.call('ps', '-q', service).splitlines()
            if len(ids) != 1:
                raise BackupError('service_missing')
            data = json.loads(command(['docker', 'inspect', ids[0]], self.env))[0]
            if not data['State']['Running'] or data['State'].get('Health', {}).get('Status') != 'healthy':
                raise BackupError('service_not_healthy')

    def restart(self):
        # Existing containers only. Never apply a new config, pull images or start dependencies.
        self.call('up', '-d', '--no-deps', '--no-recreate', '--pull', 'never', '--wait', '--wait-timeout', '180', 'api', 'web')
        self.healthy()
        https_health()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def https_health():
    opener = urllib.request.build_opener(NoRedirect())
    deadline = time.monotonic() + 60
    while True:
        try:
            with opener.open(HEALTH_URL, timeout=5) as response:
                if response.status == 200:
                    return
                raise BackupError('https_health_failed')
        except urllib.error.HTTPError as error:
            error.close()
            if error.code not in {404,502,503,504}:
                raise BackupError('https_health_failed') from None
        except urllib.error.URLError:
            raise BackupError('https_network_or_tls_failed') from None
        if time.monotonic() >= deadline:
            raise BackupError('https_health_timeout')
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def restic_json(output):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError()
    try:
        return json.loads(output, object_pairs_hook=unique_keys, parse_constant=invalid_constant)
    except (ValueError, TypeError):
        raise BackupError('restic_snapshot_not_confirmed') from None


def upload(destination, run_id, env):
    # command() requires exit zero, including when a nonzero backup still created a snapshot.
    output = command(['restic', 'backup', '--json', '--tag', 'documind-ai', '--tag', run_id, str(destination)], env, 7200)
    messages = [restic_json(line) for line in output.splitlines() if line.strip()]
    for item in messages:
        if (not isinstance(item, dict) or not isinstance(item.get('message_type'), str)
                or item['message_type'] not in {'status', 'verbose_status', 'summary'}
                or ('error_count' in item and (type(item['error_count']) is not int or item['error_count'] != 0))):
            raise BackupError('restic_snapshot_not_confirmed')
    summaries = [item for item in messages if item['message_type'] == 'summary']
    if len(summaries) != 1 or messages[-1] is not summaries[0] or summaries[0].get('dry_run', False) is not False:
        raise BackupError('restic_snapshot_not_confirmed')
    reference = summaries[0].get('snapshot_id')
    # 0.14.0 calls ID.Str(): exactly 8 hex characters. Newer versions may emit all 64.
    if not isinstance(reference, str) or not re.fullmatch(r'(?:[a-f0-9]{8}|[a-f0-9]{64})', reference):
        raise BackupError('restic_snapshot_not_confirmed')
    found = restic_json(command(['restic', 'snapshots', '--json', reference], env, 300))
    if not isinstance(found, list) or len(found) != 1 or not isinstance(found[0], dict):
        raise BackupError('restic_snapshot_not_confirmed')
    snapshot = found[0].get('id')
    tags = found[0].get('tags')
    if (not isinstance(snapshot, str) or not re.fullmatch('[a-f0-9]{64}', snapshot) or not snapshot.startswith(reference)
            or not isinstance(tags, list) or len(tags) != 2 or not all(isinstance(tag, str) for tag in tags)
            or set(tags) != {'documind-ai', run_id} or found[0].get('paths') != [str(destination)]):
        raise BackupError('restic_snapshot_not_confirmed')
    return snapshot  # Always return/store the full confirmed ID, never the abbreviated reference.


@contextmanager
def local_backup_deadline():
    def expired(signum, frame):
        raise BackupError('local_backup_timeout')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(1800)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def marker_path(root):
    return root / 'var/backup-maintenance.json'


def resume(root, report):
    with deployment_lock(root):
        marker = marker_path(root)
        if not marker.exists():
            report.update(status='success', phase='no_maintenance')
            return
        active = ActiveRelease(root)
        if json.loads(marker.read_text()).get('bundle') != str(active.bundle):
            raise BackupError('maintenance_release_changed_manual_recovery_required')
        active.preflight(require_healthy=False)
        active.restart()
        marker.unlink()  # Only the maintenance marker; never archives, snapshots or volumes.
        report.update(status='success', phase='services_resumed')


def execute(root, report):
    with deployment_lock(root):
        marker = marker_path(root)
        if marker.exists():
            raise BackupError('pending_maintenance_run_resume_first')
        active = ActiveRelease(root)
        report['phase'] = 'preflight'
        active.preflight()
        restic_env = restic_environment()
        command(['restic', 'cat', 'config'], restic_env, 120)  # Existing repository; never init/unlock/forget.
        if shutil.disk_usage(root).free < 8 * 1024**3:
            raise BackupError('insufficient_disk_space')
        run_id = 'daily-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex
        destination = root / 'var/backups' / run_id
        report.update(run_id=run_id, git_sha=active.release['git_sha'], backup=str(destination.relative_to(root)))
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open('x', encoding='utf-8') as output:
            json.dump({'bundle': str(active.bundle), 'run_id': run_id}, output)
        stopped = False
        try:
            report['phase'] = 'stop'
            stopped = True  # A partially failed stop must still trigger restart.
            active.call('stop', '--timeout', '150', 'api', 'web')
            report['phase'] = 'local_backup'
            database_bytes = int(active.call('exec', '-T', 'db', 'sh', '-c',
                'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT pg_database_size(current_database())"'))
            document_bytes = int(active.call('run', '--rm', '--no-deps', '-T', '--entrypoint',
                'du', 'api', '-sb', '/app/var/documents').split()[0])
            if shutil.disk_usage(root).free < 8 * 1024**3 + int((database_bytes + document_bytes) * 1.25):
                raise BackupError('insufficient_snapshot_headroom')
            with local_backup_deadline():
                load_helper(active.bundle, 'backup_local').create_backup(active.compose, destination, env=active.env)
            manifest = json.loads((destination / 'manifest.json').read_text())
            if manifest['migration'] != active.release['schema_revision']:
                raise BackupError('backup_schema_mismatch')
            for name in ('database.dump', 'documents.tar.gz'):
                with (destination / name).open('rb') as source:
                    if hashlib.file_digest(source, 'sha256').hexdigest() != manifest['sha256'][name]:
                        raise BackupError('backup_checksum_mismatch')
        finally:
            if stopped:
                report['restart_attempted'] = True
                interrupted_phase = report['phase']
                report['phase'] = 'restart'
                active.restart()
                report['restart_healthy'] = True
                marker.unlink()
                report['phase'] = interrupted_phase
        # Keep the maintenance window short; transfer only after the app has recovered.
        report['phase'] = 'restic_upload'
        report['snapshot_id'] = upload(destination, run_id, restic_env)
        report.update(status='success', phase='complete')


def validate_root(root):
    if os.name != 'posix' or sys.version_info < (3,11) or not root.is_dir() or root.stat().st_mode & 0o022:
        raise BackupError('private_linux_deployment_root_required')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/srv/documind-ai'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--resume', action='store_true', help='Restart a marked active release, under the deployment lock')
    mode.add_argument('--alert', action='store_true', help='Invoke an optional local executable, with no secret environment')
    args = parser.parse_args()
    os.umask(0o077)
    report = {'status': 'failed', 'phase': 'validation', 'started_at': datetime.now(timezone.utc).isoformat()}
    def interrupted(signum, frame):
        # Ignore further termination requests while finally restores the app.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise BackupError('interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if args.alert:
            hook = os.environ.get('DOCUMIND_BACKUP_ALERT_HOOK', '')
            if hook:
                path = Path(hook)
                if not path.is_absolute() or not path.is_file() or path.stat().st_mode & 0o022:
                    raise BackupError('invalid_alert_hook')
                command([str(path), 'documind-backup-failed'], base_environment(), 30)
            report.update(status='success', phase='alert_hook_completed' if hook else 'alert_hook_not_configured')
        else:
            root = args.root.resolve()
            validate_root(root)
            (resume if args.resume else execute)(root, report)
    except BaseException as error:
        report['error'] = str(error) if isinstance(error, BackupError) else 'backup_operation_failed'
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    # Only explicitly controlled metadata, never subprocess output or secret configuration.
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0 if report['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
