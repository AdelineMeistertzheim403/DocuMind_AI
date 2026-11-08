"""Local Docker Desktop synthetic capture/restore laboratory. No pull or cleanup.

Run with the repository Python, from its root. Existing resources are never reused.
The Linux payload calls the production restore/verification implementations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    docker = ['docker', '--context', 'desktop-linux']
    def run(arguments, **kwargs):
        result = subprocess.run(arguments, capture_output=True, **kwargs)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace') if isinstance(result.stderr, bytes) else result.stderr)
        return result.stdout
    context = json.loads(run(docker + ['context', 'inspect', 'desktop-linux']))[0]
    if context['Endpoints']['docker']['Host'] != 'npipe:////./pipe/dockerDesktopLinuxEngine':
        raise RuntimeError('Only local Docker Desktop Linux is allowed')
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise RuntimeError('Docker overrides are not allowed')
    images = ['documind-phase152-proofs:local', 'documind-s14-8-postgres:local']
    image_info = json.loads(run(docker + ['image', 'inspect', *images]))
    existing = {kind: run(docker + command).decode().splitlines() for kind, command in {
        'containers': ['ps', '-a', '--format', '{{.Names}}'],
        'volumes': ['volume', 'ls', '-q'], 'networks': ['network', 'ls', '--format', '{{.Name}}'],
    }.items()}
    wheel_hash = hashlib.sha256(args.wheel.read_bytes()).hexdigest()
    if wheel_hash != '9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079':
        raise RuntimeError('Offline wheel does not match requirements.test.lock')
    name = 'documind-restore-lab-' + uuid4().hex[:12]
    if any(any(item.startswith(name) for item in items) for items in existing.values()):
        raise RuntimeError('Laboratory resource collision')
    root = repo / 'var' / name
    root.mkdir(exist_ok=False)
    (root / '.synthetic-only').write_text('documind-isolated-restore-lab-v1\n', encoding='utf-8')
    (root / 'preflight.json').write_text(json.dumps({
        'name': name, 'endpoint': context['Endpoints']['docker']['Host'],
        'images': [{k: image[k] for k in ('Id', 'RepoTags', 'Architecture', 'Os')} for image in image_info],
        'existing_resources': existing, 'wheel_sha256': wheel_hash,
        'env_files_loaded': False,
    }, indent=2))
    # Allowlist prevents mounting .env, .git, backups or any host credentials.
    source = root / 'source'
    source.mkdir()
    for directory in ('backend', 'tools', 'ops', 'tests', 'alembic', 'migrations', 'analyseur_documents', 'documind_extractor'):
        if (repo / directory).is_dir():
            shutil.copytree(repo / directory, source / directory,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'node_modules', '.env*'))
    for filename in ('alembic.ini', 'pyproject.toml', 'requirements.test.lock', 'compose.production.yaml'):
        shutil.copy2(repo / filename, source / filename)
    materials = root / 'materials'
    materials.mkdir()
    shutil.copy2(args.wheel, materials / args.wheel.name)
    # A never-started PostgreSQL image container supplies its local musl runtime.
    # chroot gives pg_restore its matching libraries inside the Linux runner.
    export_name = name + '-client-image'
    run(docker + ['create', '--pull', 'never', '--name', export_name, '--network', 'none',
                  '--mount', 'type=volume,src=' + name + '-client-image-data,dst=/var/lib/postgresql/data',
                  '--entrypoint', '/bin/true', images[1]])
    run(docker + ['export', '-o', str(materials / 'pg-rootfs.tar'), export_name])
    compose_file = root / 'compose.json'
    env = {'PYTHONPATH': '/src', 'PYTHONDONTWRITEBYTECODE': '1',
           'AI_ENABLED': 'false', 'REGISTRATION_MODE': 'disabled', 'PUBLIC_LEGAL_READY': 'false',
           'DATABASE_URL': 'postgresql+psycopg://synthetic:synthetic@db:5432/documind_source',
           'LIFECYCLE_DATA_ROOT': '/app/lifecycle', 'LIFECYCLE_BACKUP_LOCK_PATH': '/app/lifecycle/.backup.lock'}
    variables = {'registry': 'REGISTRY', 'witness': 'CONFIRMATION', 'authenticated': 'AUTHENTICATED_CONFIRMATION',
                 'holds': 'HOLDS', 'admission_anchor': 'ADMISSION_ANCHOR'}
    for store, variable in variables.items():
        env['LIFECYCLE_' + variable + '_PATH'] = '/app/lifecycle/' + store + '/' + store + '.sqlite'
    bind = lambda src, target, readonly=False: {'type': 'bind', 'source': str(src), 'target': target, 'read_only': readonly}
    api = {'image': images[0], 'user': '0:0', 'pull_policy': 'never', 'working_dir': '/src', 'entrypoint': ['python'],
           'environment': env, 'networks': ['isolated'], 'volumes': [
               bind(source, '/src', True), bind(root, '/evidence'), bind(materials, '/materials', True),
               {'type': 'volume', 'source': 'documents', 'target': '/app/var'},
               {'type': 'volume', 'source': 'lifecycle', 'target': '/app/lifecycle'}]}
    config = {'name': name, 'services': {
        'db': {'image': images[1], 'pull_policy': 'never',
               'command': ['postgres', '-c', 'cluster_name=documind-restore-lab'],
               'environment': {'POSTGRES_USER': 'synthetic', 'POSTGRES_PASSWORD': 'synthetic', 'POSTGRES_DB': 'documind_source'},
               'networks': ['isolated'], 'volumes': [{'type': 'volume', 'source': 'postgres', 'target': '/var/lib/postgresql/data'}]},
        'api': api,
        'web': {'image': images[0], 'pull_policy': 'never', 'networks': ['isolated']}},
        'volumes': {key: {'name': name + '-' + key} for key in ('postgres', 'documents', 'lifecycle')},
        'networks': {'isolated': {'internal': True, 'name': name + '-isolated'}}}
    compose_file.write_text(json.dumps(config, indent=2))
    empty = root / 'empty.env'
    empty.write_text('# Synthetic laboratory; no external environment files.\n')
    compose = docker + ['compose', '--env-file', str(empty), '--project-directory', str(root), '-p', name, '-f', str(compose_file)]
    (root / 'commands.json').write_text(json.dumps({'compose': compose, 'root': str(root)}, indent=2))
    print('LAB_ROOT=' + str(root), flush=True)
    run(compose + ['up', '-d', '--pull', 'never', 'db'])
    import time
    for _ in range(40):
        probe = subprocess.run(compose + ['exec', '-T', 'db', 'pg_isready', '-h', '127.0.0.1', '-U', 'synthetic'], capture_output=True)
        if probe.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Synthetic PostgreSQL did not start')
    output = run(compose + ['run', '--rm', '--no-deps', '-T', 'api', '/src/ops/testing/combined_restore_payload.py', 'seed'])
    (root / 'seed.log').write_bytes(output)
    sys.path.insert(0, str(repo))
    from tools.backup_local import create_backup, _assert_no_database_clients
    extra = subprocess.Popen(compose + ['exec', '-T', '-e', 'PGAPPNAME=synthetic-negative-session',
        'db', 'psql', '-U', 'synthetic', '-d', 'documind_source', '-c', 'SELECT pg_sleep(10)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(30):
            active = run(compose + ['exec', '-T', 'db', 'psql', '-U', 'synthetic', '-d', 'documind_source', '-At', '-c',
                "SELECT count(*) FROM pg_stat_activity WHERE application_name='synthetic-negative-session'"]).strip()
            if active == b'1': break
            time.sleep(0.1)
        else: raise RuntimeError('Synthetic extra session not observed')
        try:
            _assert_no_database_clients(compose, os.environ.copy())
        except ValueError as error:
            session_evidence = {'id': 11, 'scenario': 'Session PostgreSQL supplémentaire', 'status': 'PASS', 'evidence': str(error)}
        else: raise RuntimeError('Extra PostgreSQL session was incorrectly accepted')
    finally:
        extra.communicate(timeout=20)
    (root / 'negative-session.json').write_text(json.dumps(session_evidence))
    capture = create_backup(compose, root / 'snapshot', env={**os.environ, 'DOCKER_CONTEXT': 'desktop-linux'})
    print('CAPTURE_COMPLETE=' + str(capture), flush=True)
    db_id = run(compose + ['ps', '-q', 'db']).decode().strip()
    runner = name + '-runner'
    run(docker + ['run', '-d', '--pull', 'never', '--user', '0:0', '--name', runner, '--network', 'container:' + db_id,
                  '--mount', 'type=volume,src=' + name + '-recovery,dst=/lab',
                  '--mount', 'type=bind,src=' + str(source) + ',dst=/src,readonly',
                  '--mount', 'type=bind,src=' + str(root) + ',dst=/evidence',
                  '--mount', 'type=bind,src=' + str(materials) + ',dst=/materials,readonly',
                  '-e', 'PYTHONPATH=/src', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                  '-w', '/src', '--entrypoint', 'sleep', images[0], 'infinity'])
    result = subprocess.run(docker + ['exec', runner, 'python', '/src/ops/testing/combined_restore_payload.py', 'restore'], capture_output=True)
    (root / 'restore.stdout.log').write_bytes(result.stdout)
    (root / 'restore.stderr.log').write_bytes(result.stderr)
    print(result.stdout.decode(errors='replace'), flush=True)
    print(result.stderr.decode(errors='replace'), flush=True)
    print('RESTORE_EXIT=' + str(result.returncode), flush=True)
    # Stop only the newly-created laboratory. Keep all evidence and synthetic volumes.
    run(docker + ['stop', runner])
    run(compose + ['stop', 'db'])
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
