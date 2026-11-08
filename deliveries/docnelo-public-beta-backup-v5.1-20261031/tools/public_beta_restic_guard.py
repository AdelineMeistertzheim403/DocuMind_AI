'''Verify Restic configuration for DocuMind Public Beta.

This helper is intended for operator-run workflows on the VPS.
It never initializes, unlocks, forgets, prunes, or otherwise modifies a repository.

Security goals:
- Refuse to proceed without an explicit *Public Beta* repository id expectation when verifying uploads.
- Provide a safe way to *discover* the Public Beta repository id (no secrets printed).
- Provide a safe way to *record* the Public Beta repository id in the env file (no secrets printed).
- Refuse ambiguous or shell-interpreted secret configuration.
- Avoid printing any secret values.
'''

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess


PUBLIC_BETA_KEYS = {
    'RESTIC_REPOSITORY',
    'RESTIC_PASSWORD',
    'RESTIC_PASSWORD_FILE',
    'B2_ACCOUNT_ID',
    'B2_ACCOUNT_KEY',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_DEFAULT_REGION',
    'AWS_REGION',
    'DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID',
}


class ResticGuardError(RuntimeError):
    pass


def _private_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ResticGuardError('private_file_required')
    if os.name == 'posix':
        mode = path.stat().st_mode
        if mode & 0o077 or not mode & 0o400:
            raise ResticGuardError('private_file_required')


def _load_env_file(path: Path, *, require_repo_id: bool) -> tuple[dict[str, str], str | None]:
    '''Load a strict, literal Restic env file.

    Returns (env, expected_repo_id). If require_repo_id is False, expected_repo_id
    may be None.
    '''

    _private_file(path)

    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        declaration = re.fullmatch(r'\s*(?:export[ \t]+)?([A-Z][A-Z0-9_]*)=(.*)', line)
        if not declaration:
            raise ResticGuardError('invalid_restic_configuration')
        key, value = declaration.groups()

        # A single literal token only: no concatenation, continuation, expansion or commands.
        literal = r'\s*(?:\x27[^\x27]*\x27|\x22(?:[^\x22\\]|\\.)*\x22|[^\s\x27\x22\\;|&<>()`#]+)(?:\s+\#.*)?\s*'
        if key not in PUBLIC_BETA_KEYS or key in values or not re.fullmatch(literal, value):
            raise ResticGuardError('invalid_restic_configuration')
        try:
            tokens = shlex.split(value, comments=True, posix=True)
        except ValueError as exc:
            raise ResticGuardError('invalid_restic_configuration') from exc
        if len(tokens) != 1 or any(char in tokens[0] for char in ('$', '`', '\x00', '\n', '\r')):
            raise ResticGuardError('invalid_restic_configuration')
        if not tokens[0]:
            raise ResticGuardError('invalid_restic_configuration')
        values[key] = tokens[0]

    methods = {'RESTIC_PASSWORD', 'RESTIC_PASSWORD_FILE'} & values.keys()
    if not values.get('RESTIC_REPOSITORY') or len(methods) != 1:
        raise ResticGuardError('missing_restic_configuration')

    repository = values['RESTIC_REPOSITORY']
    if not repository.startswith(('b2:', 's3:https://')):
        raise ResticGuardError('secure_repository_required')

    if 'RESTIC_PASSWORD_FILE' in values:
        password_file = Path(values['RESTIC_PASSWORD_FILE'])
        allowed = path.absolute().parent
        if not password_file.is_absolute() or '..' in password_file.parts:
            raise ResticGuardError('unauthorized_restic_password_path')
        try:
            password_file.relative_to(allowed)
        except ValueError as exc:
            raise ResticGuardError('unauthorized_restic_password_path') from exc
        # Reject indirect symlinks too, including an alias of the authorized directory itself.
        if allowed.resolve() != allowed or password_file.resolve() != password_file:
            raise ResticGuardError('unauthorized_restic_password_path')
        _private_file(password_file)

    expected_repo_id = values.get('DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID')
    if expected_repo_id is None:
        if require_repo_id:
            raise ResticGuardError('missing_public_beta_repository_id')
    else:
        if not re.fullmatch(r'[a-f0-9]{64}', expected_repo_id):
            raise ResticGuardError('missing_public_beta_repository_id')

    env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            'PATH',
            'HOME',
            'USER',
            'LOGNAME',
            'DOCKER_HOST',
            'DOCKER_CONTEXT',
            'DOCKER_CONFIG',
            'XDG_RUNTIME_DIR',
            'SSL_CERT_FILE',
            'SSL_CERT_DIR',
        }
    }
    env.update(values)
    return env, expected_repo_id


def load_public_beta_restic_env(path: Path) -> tuple[dict[str, str], str]:
    env, expected = _load_env_file(path, require_repo_id=True)
    assert expected is not None
    return env, expected


def discover_public_beta_repository_id(env: dict[str, str]) -> str:
    '''Return the Restic repository id from restic cat config.

    The repository id is not a secret, but it is used as a strong safety guard
    to prevent uploading to the wrong repository.
    '''

    try:
        result = subprocess.run(
            ['restic', 'cat', 'config'],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise ResticGuardError('restic_unavailable') from exc

    try:
        config = json.loads(result.stdout, object_pairs_hook=_unique_json_keys)
    except ValueError as exc:
        raise ResticGuardError('invalid_restic_response') from exc

    if not isinstance(config, dict) or result.stderr.strip():
        raise ResticGuardError('invalid_restic_response')
    repo_id = config.get('id')
    if not isinstance(repo_id, str) or not re.fullmatch(r'[a-f0-9]{64}', repo_id):
        raise ResticGuardError('invalid_restic_response')
    return repo_id


def _unique_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def verify_public_beta_repository(env: dict[str, str], expected_repo_id: str) -> None:
    '''Refuse to proceed unless restic cat config matches expected_repo_id.'''

    repo_id = discover_public_beta_repository_id(env)
    if repo_id != expected_repo_id:
        raise ResticGuardError('repository_id_mismatch')


def validate_public_beta_destination(env: dict[str, str], bucket: str, prefix: str) -> None:
    """Compare with independently approved B2 coordinates, before trusting an ID."""
    if (not re.fullmatch(r'[A-Za-z0-9-]+', bucket)
            or not re.fullmatch(r'[A-Za-z0-9_/-]+', prefix)
            or any(part in {'', '.', '..'} for part in prefix.removeprefix('/').split('/'))
            or 'public-beta' not in (bucket + '/' + prefix).lower()
            or 'prod' in (bucket + '/' + prefix).lower()):
        raise ResticGuardError('invalid_public_beta_destination')
    if env.get('RESTIC_REPOSITORY') != f'b2:{bucket}:{prefix}':
        raise ResticGuardError('public_beta_destination_mismatch')
    if not all(env.get(key) for key in ('B2_ACCOUNT_ID', 'B2_ACCOUNT_KEY', 'RESTIC_PASSWORD_FILE')):
        raise ResticGuardError('missing_b2_configuration')


def record_public_beta_repository_id(env_file: Path, *, bucket: str, prefix: str) -> None:
    '''Record DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID in the env file.

    This is intended to be executed once during setup on the VPS.

    - Refuses if the env file is not private.
    - Refuses if the env file already contains a different repo id.
    - Never prints secrets (and does not print the repo id).
    '''

    _private_file(env_file)
    # Append under an inode lock on the VPS; never truncate/replace the secret file.
    fd = os.open(env_file, os.O_RDWR | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'r+', encoding='utf-8') as stream:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        env, existing_repo_id = _load_env_file(env_file, require_repo_id=False)
        validate_public_beta_destination(env, bucket, prefix)
        repo_id = discover_public_beta_repository_id(env)
        if existing_repo_id is not None:
            if existing_repo_id == repo_id:
                return
            raise ResticGuardError('public_beta_repository_id_conflict')
        raw = stream.read()
        newline = '' if raw.endswith('\n') or not raw else '\n'
        stream.seek(0, os.SEEK_END)
        stream.write(newline + f'DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID={repo_id}\n')
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--expected-bucket')
    parser.add_argument('--expected-prefix')
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--discover-repo-id',
        action='store_true',
        help='Print the Restic repository id (no secrets) so it can be recorded as DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID.',
    )
    group.add_argument(
        '--record-repo-id',
        action='store_true',
        help='Record DOCUMIND_PUBLIC_BETA_RESTIC_REPO_ID in the env file (no secrets printed).',
    )
    args = parser.parse_args()

    if args.discover_repo_id:
        env, _ = _load_env_file(args.env_file, require_repo_id=False)
        repo_id = discover_public_beta_repository_id(env)
        print(repo_id)
        return

    if args.record_repo_id:
        if not args.expected_bucket or not args.expected_prefix:
            parser.error('--record-repo-id requires --expected-bucket and --expected-prefix')
        record_public_beta_repository_id(args.env_file, bucket=args.expected_bucket, prefix=args.expected_prefix)
        print('Public Beta Restic repository id recorded.')
        return

    env, expected_repo_id = load_public_beta_restic_env(args.env_file)
    verify_public_beta_repository(env, expected_repo_id)
    print('Public Beta Restic repository verified.')


if __name__ == '__main__':
    main()
