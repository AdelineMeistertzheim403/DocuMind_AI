"""Consistent local Compose snapshot; run with API/web stopped. Never prints credentials."""
import json
import argparse
import hashlib
import os
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import PurePosixPath
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

if __package__:
    from .lifecycle_key_policy import validate_key_member
else:
    from lifecycle_key_policy import validate_key_member


BACKUP_FORMAT_VERSION = 4
BACKUP_FORMAT_VERSION_WITH_KEYS = 5
RECOVERY_STATE_MAX_BYTES = 1024
RECOVERY_STATE_ALLOWED = {'ready', 'quarantined', 'serving_closed'}

LIFECYCLE_KEYS_ARCHIVE = 'lifecycle-keys.tar.gz'
LIFECYCLE_KEY_PATHS = ('keys/authentication.key', 'keys/admission.key')


BACKUP_FILES = (
    'database.dump',
    'documents.tar.gz',
    'lifecycle.sqlite.tar.gz',
    'recovery-state.json',
    'integrity.json',
)


BACKUP_FILES_WITH_KEYS = BACKUP_FILES + (LIFECYCLE_KEYS_ARCHIVE,)


def _unique_keys(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError('duplicate key')
        values[key] = value
    return values


def _parse_recovery_state_payload(payload: bytes) -> dict[str, object]:
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError('Recovery state payload must be bytes')
    if len(payload) > RECOVERY_STATE_MAX_BYTES:
        raise ValueError('Recovery state payload is too large')
    try:
        data = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_keys)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('Recovery state payload must be valid JSON') from exc
    if (not isinstance(data, dict)
            or set(data) != {'format', 'state'}
            or type(data.get('format')) is not int
            or data['format'] != 1
            or not isinstance(data.get('state'), str)
            or data['state'] not in RECOVERY_STATE_ALLOWED):
        raise ValueError('Recovery state payload schema mismatch')
    return data

def _compose_command(compose, command):
    return compose + command[2:]


def _compose_config(compose, env):
    return json.loads(subprocess.check_output(
        _compose_command(compose, ['docker', 'compose', 'config', '--format', 'json']),
        text=True, env=env, stderr=subprocess.PIPE))


def _assert_quiescent(compose, env, config):
    running = set(subprocess.check_output(
        compose + ['ps', '--status', 'running', '--services'],
        text=True, env=env, stderr=subprocess.PIPE).splitlines())
    if running != {'db'}:
        raise ValueError('Only the database may run during lifecycle capture')

    project = config.get('name')
    expected_volumes = {}
    expected_targets = {
        'db': {'/var/lib/postgresql/data'},
        'api': {'/app/var', '/app/lifecycle'},
        # One-off privileged provisioning must be quiescent during capture, but it
        # is allowed to mount the lifecycle volume.
        'lifecycle-init': {'/app/lifecycle'},
    }
    services = config.get('services', {})
    for service, targets in expected_targets.items():
        definition = services.get(service)
        if definition is None:
            if service == 'lifecycle-init':
                continue
            raise ValueError('Expected service is missing from the Compose configuration')
        volumes = definition.get('volumes', [])
        for target in targets:
            matches = [item for item in volumes if item.get('target') == target]
            if len(matches) != 1 or matches[0].get('type') != 'volume':
                raise ValueError('Persistent backup volume mapping is missing')
            expected_volumes[(service, target)] = config['volumes'][matches[0]['source']]['name']

    allowed_services_by_volume = {}
    for (service, _), volume_name in expected_volumes.items():
        allowed_services_by_volume.setdefault(volume_name, set()).add(service)

    identifiers = subprocess.check_output(
        ['docker', 'ps', '-aq'], text=True, env=env, stderr=subprocess.PIPE).splitlines()
    if not identifiers:
        raise ValueError('Compose containers are unavailable')
    containers = json.loads(subprocess.check_output(
        ['docker', 'inspect', *identifiers], text=True, env=env, stderr=subprocess.PIPE))

    sensitive_volumes = set(expected_volumes.values())
    for container in containers:
        labels = container.get('Config', {}).get('Labels') or {}
        service = labels.get('com.docker.compose.service')
        attached = {mount.get('Name') for mount in container.get('Mounts', [])
                    if mount.get('Type') == 'volume'}
        sensitive = attached & sensitive_volumes
        if not sensitive:
            continue
        if (labels.get('com.docker.compose.project') != project
                or labels.get('com.docker.compose.oneoff', 'false').lower() != 'false'):
            raise ValueError('Uncontrolled container references a backup volume')
        for volume_name in sensitive:
            allowed = allowed_services_by_volume.get(volume_name, set())
            if service not in allowed:
                raise ValueError('Unexpected container references a backup volume')

    networks = config.get('networks', {})
    service_networks = {}
    for service in ('db', 'api', 'web'):
        values = config['services'][service].get('networks', {})
        service_networks[service] = set(values if isinstance(values, list) else values.keys())
    protected_networks = {
        name for name, details in networks.items()
        if details.get('internal') is True or 'db' in service_networks and name in service_networks['db']
    }
    for logical in protected_networks:
        network = networks.get(logical)
        if not network or not network.get('name'):
            raise ValueError('Private Compose network is not configured')
        details = json.loads(subprocess.check_output(
            ['docker', 'network', 'inspect', network['name']],
            text=True, env=env, stderr=subprocess.PIPE))[0]
        connected = set((details.get('Containers') or {}).keys())
        running_ids = {}
        for container in containers:
            labels = container.get('Config', {}).get('Labels') or {}
            if (labels.get('com.docker.compose.project') == project
                    and labels.get('com.docker.compose.service') in {'api', 'db', 'web'}
                    and container.get('State', {}).get('Running')):
                running_ids[labels['com.docker.compose.service']] = container['Id']
        expected_services = {'db'} if logical in service_networks['db'] else set()
        expected_ids = {running_ids[name] for name in expected_services if name in running_ids}
        if connected != expected_ids:
            raise ValueError('Uncontrolled container is connected to a private Compose network')

def _assert_no_database_clients(compose, env):
    query = ("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
             "AND backend_type='client backend' AND pid<>pg_backend_pid()")
    for _ in range(10):
        count = subprocess.check_output(
            compose + ['exec', '-T', 'db', 'sh', '-c',
                       'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
                       '-d "$POSTGRES_DB" -At -c "$1"', 'backup-quiescence', query],
            text=True, env=env, stderr=subprocess.PIPE).strip()
        if count == '0':
            return
        __import__('time').sleep(0.5)
    raise ValueError('Uncontrolled PostgreSQL client session prevents backup')


@contextmanager
def _offline_api_compose(compose, env):
    """Compose run has no --network flag; reset service networks explicitly.

    Validate the resolved override before any capture container is started.
    This changes only one-off capture configuration, never the source service.
    """
    base = list(compose)
    if not any(item in {'-f', '--file'} or item.startswith('--file=') for item in base):
        # Adding the first -f suppresses Compose's default-file discovery.
        # Materialize that default explicitly before adding the offline override.
        if (os.environ if env is None else env).get('COMPOSE_FILE'):
            raise ValueError('Explicit Compose files required when COMPOSE_FILE is set')
        project_root = Path.cwd()
        if '--project-directory' in base:
            project_root = Path(base[base.index('--project-directory') + 1])
        candidates = [project_root / name for name in (
            'compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml')]
        selected = next((path for path in candidates if path.is_file()), None)
        if selected is None:
            raise ValueError('Explicit Compose file required for offline capture')
        base += ['-f', str(selected.absolute())]
        for name in ('compose.override.yaml', 'compose.override.yml', 'docker-compose.override.yaml', 'docker-compose.override.yml'):
            override_path = project_root / name
            if override_path.is_file():
                base += ['-f', str(override_path.absolute())]
                break
    with tempfile.TemporaryDirectory(prefix='documind-offline-capture-') as directory:
        override = Path(directory) / 'offline.yaml'
        override.write_text('services:\n  api:\n    networks: !reset []\n    network_mode: none\n', encoding='utf-8')
        offline = base + ['-f', str(override)]
        service = _compose_config(offline, env).get('services', {}).get('api', {})
        if service.get('network_mode') != 'none' or service.get('networks'):
            raise ValueError('Offline capture network isolation could not be established')
        yield offline


def create_backup(compose, destination, env=None, *, include_lifecycle_keys=False):
    """Reusable by the approved VPS deployment; compose contains no credential arguments."""
    config = _compose_config(compose, env)
    try:
        from . import recovery_control_directory as recovery_control
    except ImportError:
        import recovery_control_directory as recovery_control
    recovery_control.validate_compose(config)
    _assert_quiescent(compose, env, config)
    _assert_no_database_clients(compose, env)
    capture_id = str(uuid4())
    destination.mkdir(parents=True, mode=0o700)

    recovery_path = (config.get('services', {}).get('api', {}).get('environment', {}) or {}).get('RECOVERY_STATE_PATH')
    if not isinstance(recovery_path, str):
        raise ValueError('RECOVERY_STATE_PATH is not configured')
    recovery_posix = PurePosixPath(recovery_path)
    if (not recovery_posix.is_absolute() or '..' in recovery_posix.parts
            or '\\' in recovery_path or '\x00' in recovery_path):
        raise ValueError('RECOVERY_STATE_PATH must be a canonical absolute path')

    commands = {
        'database.dump': ['docker', 'compose', 'exec', '-T', 'db', 'sh', '-c',
            'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
        'documents.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',
            '--entrypoint', 'tar', 'api', '-C', '/app/var', '-czf', '-', 'documents'],
        'lifecycle.sqlite.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',
            '-e', 'LIFECYCLE_CAPTURE_ID=' + capture_id,
            '--entrypoint', 'python', 'api', '-m', 'backend.lifecycle_snapshot'],
        'recovery-state.json': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',
            '--entrypoint', 'cat', 'api', recovery_path],
    }
    if include_lifecycle_keys:
        commands[LIFECYCLE_KEYS_ARCHIVE] = ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',
            '--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',
            '-czf', '-', '--no-recursion', *LIFECYCLE_KEY_PATHS]
    with _offline_api_compose(compose, env) as offline:
        for name, command in commands.items():
            with (destination / name).open('wb') as output:
                selected = compose if name == 'database.dump' else offline
                try:
                    subprocess.run(_compose_command(selected, command), stdout=output, stderr=subprocess.PIPE,
                                   check=True, env=env)
                except subprocess.CalledProcessError as error:
                    stderr = error.stderr
                    if isinstance(stderr, (bytes, bytearray)):
                        stderr = stderr.decode(errors='replace')
                    raise RuntimeError(f"Offline capture failed: {name}\n{stderr or ''}") from None
    with (destination/'database.dump').open('rb') as dump:
        subprocess.run(compose+['exec','-T','db','pg_restore','--list'],stdin=dump,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,env=env)
    with tarfile.open(destination/'documents.tar.gz') as archive:
        for member in archive:
            if member.issym() or member.islnk() or PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts:
                raise ValueError('Unexpected archive member')
    with tarfile.open(destination/'lifecycle.sqlite.tar.gz', 'r:gz') as archive:
        members = archive.getmembers()
        expected_names = {'metadata.json'} | {
            f'stores/{name}.sqlite' for name in ('registry', 'witness', 'authenticated', 'holds', 'admission_anchor')
        }
        if ({member.name for member in members} != expected_names
                or any(not member.isfile() or member.issym() or member.islnk() for member in members)):
            raise ValueError('Incomplete lifecycle SQLite snapshot set')
        lifecycle_metadata = json.load(archive.extractfile('metadata.json'))
    if lifecycle_metadata.get('capture_id') != capture_id or set(lifecycle_metadata.get('stores', {})) != {
        'registry', 'witness', 'authenticated', 'holds', 'admission_anchor'
    }:
        raise ValueError('Lifecycle capture identity or store inventory mismatch')

    lifecycle_keys = None
    if include_lifecycle_keys:
        lifecycle_keys = {}
        with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            if (names != set(LIFECYCLE_KEY_PATHS) or len(members) != len(LIFECYCLE_KEY_PATHS)
                    or any(not member.isfile() or member.issym() or member.islnk() for member in members)):
                raise ValueError('Lifecycle key archive must contain exactly the two key files')
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts:
                    raise ValueError('Unsafe lifecycle key archive member')
                validate_key_member(member)
                mode = member.mode
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('Lifecycle key archive entry is unreadable')
                payload = source.read()
                if member.size < 1 or len(payload) != member.size:
                    raise ValueError('Lifecycle key archive payload size mismatch')
                lifecycle_keys[member.name] = {
                    'size': int(member.size),
                    'mode': int(mode),
                    'uid': member.uid,
                    'gid': member.gid,
                    'sha256': hashlib.sha256(payload).hexdigest(),
                }


    recovery_payload = (destination / 'recovery-state.json').read_bytes()
    recovery_state = _parse_recovery_state_payload(recovery_payload)

    tables = ['documents', 'document_pages', 'document_chunks', 'analyses', 'users', 'ai_budgets',
              'ai_reservations', 'ai_usage', 'ai_summaries', 'ai_interactions', 'ai_sources']
    existing=subprocess.check_output(compose+['exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT tablename FROM pg_tables WHERE schemaname=\'public\'"'],text=True,env=env,stderr=subprocess.PIPE).splitlines()
    tables += [name for name in ['chunk_embeddings','index_jobs','rag_results','rag_documents',
        'ai_operation_documents','long_summary_jobs','summary_steps','workspaces','workspace_memberships','account_tokens','account_deletion_requests','public_registration_quota'] if name in existing]
    integrity = {}
    for table in tables:
        columns_sql=f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND table_schema='public' ORDER BY ordinal_position"
        columns=subprocess.check_output(compose+['exec','-T','db','sh','-c','exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"','columns',columns_sql],text=True,env=env,stderr=subprocess.PIPE).splitlines()
        order='row_to_json(t)::text'
        sql = f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY {order}),'')) FROM (SELECT {','.join(columns)} FROM {table}) t"
        result = subprocess.check_output(compose+['exec','-T','db','sh','-c',
            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"', 'backup-check', sql], text=True,env=env,stderr=subprocess.PIPE)
        count, digest = result.strip().split('|')
        integrity[table] = {'count': int(count), 'digest': digest, 'columns':columns}
    (destination / 'integrity.json').write_text(json.dumps(integrity, indent=2), encoding='utf-8')
    revision=subprocess.check_output(compose+['exec','-T','db','sh','-c',
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT version_num FROM alembic_version"'],text=True,env=env,stderr=subprocess.PIPE).strip()
    if revision=='0007' and 'public_registration_quota' not in integrity:
        raise ValueError('Schema 0007 requires the public registration quota inventory')
    _assert_quiescent(compose, env, config)
    _assert_no_database_clients(compose, env)
    sqlite_metadata_hashes = {}
    with tarfile.open(destination/'lifecycle.sqlite.tar.gz', 'r:gz') as archive:
        for name, details in lifecycle_metadata['stores'].items():
            payload = archive.extractfile(details['snapshot']).read()
            sqlite_metadata_hashes[name] = hashlib.sha256(payload).hexdigest()
            if sqlite_metadata_hashes[name] != details['sha256']:
                raise ValueError('Lifecycle SQLite file checksum mismatch')
    checksums={}
    for name in (*commands, 'integrity.json'):
        with (destination/name).open('rb') as source:
            checksums[name]=hashlib.file_digest(source,'sha256').hexdigest()
    (destination / 'manifest.json').write_text(json.dumps({
        'backup_format_version': (BACKUP_FORMAT_VERSION_WITH_KEYS if include_lifecycle_keys else BACKUP_FORMAT_VERSION),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'capture_id': capture_id,
        'database_major': 17,
        'migration': revision,
        'integrity_version': 2,
        'capture_complete': True,
        's2_recovery_authorized': False,
        'recovery_disposition': 'quarantine_pending_independent_freshness_and_operator_review',
        'capture_scope': (['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state']
                         if include_lifecycle_keys
                         else ['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state']),
        'recovery_state': {
            'path': recovery_path,
            'state': recovery_state['state'],
            'sha256': checksums['recovery-state.json'],
        },
        'quiescence': {
            'api_web_stopped': True,
            'only_database_service_running': True,
            'private_networks_exclusive': True,
            'no_other_postgresql_clients': True,
            'lifecycle_exclusive_lock_acquired': True,
            'out_of_band_privileged_host_access': 'trusted_operator_boundary_not_machine_verifiable',
        },
        'lifecycle_stores': lifecycle_metadata['stores'],
        'lifecycle_store_sha256': sqlite_metadata_hashes,
        **({'lifecycle_keys': lifecycle_keys} if include_lifecycle_keys else {}),
        'files': list(BACKUP_FILES_WITH_KEYS if include_lifecycle_keys else BACKUP_FILES),
        'sha256': checksums,
    }, indent=2), encoding='utf-8')
    return destination


def main():
    try:
        from . import recovery_control_directory as recovery_control
    except ImportError:
        import recovery_control_directory as recovery_control
    recovery_control.deny_operational_execution()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True,
                        help='Docker Compose project name to target (e.g. documind-public-beta).')
    parser.add_argument('--env-file', action='append', default=[],
                        help='Repeatable --env-file arguments passed to docker compose.')
    parser.add_argument('--compose-file', action='append', default=[],
                        help='Repeatable -f/--file arguments passed to docker compose.')
    parser.add_argument('--destination', type=Path, default=None,
                        help='Backup output directory (default var/backups/<timestamp>).')
    parser.add_argument('--include-lifecycle-keys', action='store_true',
                        help='Capture lifecycle keys into lifecycle-keys.tar.gz (format v5)')
    args = parser.parse_args()

    compose = ['docker', 'compose', '--project-directory', str(Path.cwd()), '-p', args.project]
    for env_file in args.env_file:
        compose += ['--env-file', str(env_file)]
    for compose_file in args.compose_file:
        compose += ['-f', str(compose_file)]

    destination = args.destination or (Path('var/backups') / datetime.now(timezone.utc).strftime('sprint6-%Y%m%d-%H%M%S'))
    create_backup(compose, destination, include_lifecycle_keys=args.include_lifecycle_keys)
    print(f'Backup created: {destination}')


if __name__ == '__main__':
    main()
