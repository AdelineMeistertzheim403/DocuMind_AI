"""Operator-run V5 Public Beta capture and encrypted upload. Never restarts or deletes.

Run as python3 -m tools.public_beta_backup from the deployed release.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from tools import backup_local, verify_snapshot
from tools import recovery_control_directory as recovery_control
from tools.public_beta_restic_guard import (
    load_public_beta_restic_env,
    record_public_beta_repository_id, validate_public_beta_destination,
    verify_public_beta_repository,
)

RESTIC_ENV = Path('/home/debian/.config/restic/documind-public-beta.env')
DEPLOYMENT_BASE = Path('/opt/documind-public-beta')
CONTROL_DIR = DEPLOYMENT_BASE / 'recovery-control'
CONTROL = CONTROL_DIR / recovery_control.LATCH
OPERATOR_LOCK = DEPLOYMENT_BASE / '.public-beta-backup.lock'
PROJECT = 'documind-public-beta'
KEYS = {'keys/authentication.key', 'keys/admission.key'}


class BackupError(RuntimeError):
    pass


def command(argv, env, *, timeout=300):
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError('command_unavailable_or_timeout') from None
    if result.returncode:
        # Never expose subprocess output: Docker and Restic may echo credentials.
        raise BackupError('command_failed')
    if argv[0] == 'restic' and result.stderr.strip():
        raise BackupError('restic_stderr_requires_review')
    return result.stdout


def strict_json(raw):
    return json.loads(raw, object_pairs_hook=backup_local._unique_keys)


def latch_bytes(control):
    if not control.is_file() or control.is_symlink() or control.resolve() != control:
        raise BackupError('invalid_operator_latch')
    payload = control.read_bytes()
    backup_local._parse_recovery_state_payload(payload)
    return payload


def validate_config(config, control):
    if config.get('name') != PROJECT:
        raise BackupError('wrong_compose_project')
    for service, target, volume in (
        ('db', '/var/lib/postgresql/data', 'public_beta_database'),
        ('api', '/app/var', 'public_beta_documents'),
        ('api', '/app/lifecycle', 'public_beta_lifecycle'),
    ):
        mounts = config['services'][service].get('volumes', [])
        matches = [m for m in mounts if m.get('target') == target]
        if (len(matches) != 1 or matches[0].get('type') != 'volume'
                or matches[0].get('source') != volume
                or config['volumes'][volume].get('name') != f'{PROJECT}_{volume}'):
            raise BackupError('wrong_public_beta_volume')
    try:
        spec = recovery_control.validate_compose(config)
    except recovery_control.ContractError as error:
        raise BackupError(str(error)) from error
    if spec.source != str(control.parent) or control.name != recovery_control.LATCH:
        raise BackupError('wrong_operator_latch_mount')
    return spec


def validate_v5(destination, compose, env, control_payload, database):
    manifest = strict_json((destination / 'manifest.json').read_text(encoding='utf-8'))
    if (type(manifest.get('backup_format_version')) is not int
            or manifest['backup_format_version'] != 5
            or set(manifest.get('lifecycle_keys', {})) != KEYS):
        raise BackupError('v5_and_both_keys_required')
    if (destination / 'recovery-state.json').read_bytes() != control_payload:
        raise BackupError('captured_latch_mismatch')
    # Includes archive member/hash/mode verification and live DB fingerprints.
    result = verify_snapshot.verify_snapshot(
        destination, database=database, compose=compose, env=env, require_s2=True)
    if result.get('capture_complete') is not True or result.get('quota_certified') is not True:
        raise BackupError('s2_validation_failed')


def upload(destination, extra_paths, run_id, env):
    tags = [PROJECT, run_id]
    paths = [str(destination), *map(str, extra_paths)]
    output = command(['restic', 'backup', '--json', '--tag', PROJECT, '--tag', run_id,
                      *paths], env, timeout=7200)
    messages = [strict_json(line) for line in output.splitlines() if line.strip()]
    if any(not isinstance(m, dict) or m.get('message_type') not in {'status', 'verbose_status', 'summary'}
           or m.get('error') for m in messages):
        raise BackupError('restic_error_message')
    summaries = [m for m in messages if m.get('message_type') == 'summary']
    if len(summaries) != 1 or summaries[0].get('total_errors', 0) != 0:
        raise BackupError('restic_summary_invalid')
    sid = summaries[0].get('snapshot_id')
    if not isinstance(sid, str) or not re.fullmatch(r'(?:[a-f0-9]{8}|[a-f0-9]{64})', sid):
        raise BackupError('restic_snapshot_id_missing')
    found = strict_json(command(['restic', 'snapshots', '--json', sid], env))
    if not isinstance(found, list) or len(found) != 1 or not isinstance(found[0], dict):
        raise BackupError('remote_snapshot_missing_or_ambiguous')
    snapshot = found[0]
    full_id = snapshot.get('id')
    if (not isinstance(full_id, str) or not re.fullmatch(r'[a-f0-9]{64}', full_id)
            or (full_id != sid if len(sid) == 64 else not full_id.startswith(sid))
            or set(snapshot.get('tags', [])) != set(tags)
            or set(snapshot.get('paths', [])) != set(paths)):
        raise BackupError('remote_snapshot_mismatch')
    return full_id


@contextmanager
def operator_lock():
    # Stable path shared by all releases; file retained to avoid lock inode races.
    import fcntl
    path = OPERATOR_LOCK
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def execute(root, bucket, prefix):
    recovery_control.deny_operational_execution()
    root = root.absolute()
    if root.resolve() != root or root.parent != DEPLOYMENT_BASE:
        raise BackupError('public_beta_release_path_required')
    restic_env, repo_id = load_public_beta_restic_env(RESTIC_ENV)
    validate_public_beta_destination(restic_env, bucket, prefix)
    verify_public_beta_repository(restic_env, repo_id)
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME') if k in os.environ}
    env['RECOVERY_CONTROL_DIR'] = str(CONTROL_DIR)
    compose = ['docker', 'compose', '--project-directory', str(root), '-p', PROJECT]
    extras = [CONTROL, root / '.env.public-beta', root / '.env.public-beta.images']
    for path in extras[1:]:
        if not path.is_file() or path.is_symlink():
            raise BackupError('public_beta_env_file_required')
        compose += ['--env-file', str(path)]
    compose += ['-f', str(root / 'compose.public-beta.vps.yaml')]
    config = strict_json(command(compose + ['config', '--format', 'json'], env))
    spec = validate_config(config, CONTROL)
    docker_root = command(['docker', 'info', '--format', '{{.DockerRootDir}}'], env).strip()
    if not docker_root or not Path(docker_root).is_absolute():
        raise BackupError('unknown_docker_data_root')
    try:
        identity = recovery_control.validate_host(
            str(CONTROL_DIR), spec.gid, forbidden_roots=(str(root), docker_root))
        identifiers = command(['docker', 'ps', '-aq', '--filter',
                               'label=com.docker.compose.project=' + PROJECT], env).splitlines()
        if not identifiers:
            raise BackupError('missing_public_beta_containers')
        containers = strict_json(command(['docker', 'inspect', *identifiers], env))
        recovery_control.validate_containers(containers, spec)
    except recovery_control.ContractError as error:
        raise BackupError(str(error)) from error
    control_payload = latch_bytes(CONTROL)
    database = config['services']['db'].get('environment', {}).get('POSTGRES_DB')
    if not isinstance(database, str) or not re.fullmatch(r'[A-Za-z0-9_]+', database):
        raise BackupError('invalid_public_beta_database')
    run_id = 'public-beta-v5-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex
    destination = root / 'var' / 'backups' / run_id
    if destination.parent.resolve() != destination.parent:
        raise BackupError('unsafe_backup_parent')
    command(compose + ['stop', 'api', 'web'], env)
    command(compose + ['start', 'db'], env)
    # create_backup refuses existing destinations; its return value is checked.
    created = backup_local.create_backup(compose, destination, env=env, include_lifecycle_keys=True)
    if created != destination:
        raise BackupError('unexpected_capture_directory')
    validate_v5(destination, compose, env, control_payload, database)
    if latch_bytes(CONTROL) != control_payload:
        raise BackupError('operator_latch_changed')
    recovery_control.validate_host(str(CONTROL_DIR), spec.gid,
                                   forbidden_roots=(str(root), docker_root), expected=identity)
    verify_public_beta_repository(restic_env, repo_id)
    snapshot_id = upload(destination, extras, run_id, restic_env)
    return {'status': 'remote_verified', 'backup_dir': str(destination),
            'snapshot_id': snapshot_id, 'services': 'api_web_stopped'}


def main():
    recovery_control.deny_operational_execution()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--expected-bucket', required=True)
    parser.add_argument('--expected-prefix', required=True)
    parser.add_argument('--record-repo-id', action='store_true',
                        help='Setup only: validate destination and pin ID; no capture or upload.')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        with operator_lock():
            if args.record_repo_id:
                record_public_beta_repository_id(RESTIC_ENV, bucket=args.expected_bucket,
                                                prefix=args.expected_prefix)
                print('{"status":"repository_id_recorded"}')
            else:
                print(json.dumps(execute(args.root, args.expected_bucket, args.expected_prefix)))
    except (Exception, SystemExit, KeyboardInterrupt):
        # No traceback, subprocess output, exception text, cleanup or restart.
        print('{"status":"failed","action":"keep_local_backups_and_review_services"}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
