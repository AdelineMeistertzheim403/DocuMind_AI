"""Recovery Control Directory v1. Candidate only; no automatic ready publication."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid

VERSION = '1'
TARGET = '/run/documind-control'
LATCH = 'recovery-state.json'
STATE_PATH = TARGET + '/' + LATCH
OLD_TARGETS = {
    '/run/documind/recovery-state.json', '/app/recovery-state.json',
    '/control/recovery.json',
}


class ContractError(ValueError):
    pass


def deny_operational_execution():
    raise ContractError('CANDIDATE_ONLY: deployment, backup and restart execution disabled')


def absolute_path(value):
    if (not isinstance(value, str) or not value.startswith('/')
            or value.startswith('//') or '\\' in value or any(ord(char) < 32 for char in value)
            or any(part in ('.', '..') for part in value.split('/'))
            or str(PurePosixPath(value)) != value or value == '/'):
        raise ContractError('noncanonical absolute control path')
    return PurePosixPath(value)


def overlaps(first, second):
    return first == second or first in second.parents or second in first.parents


def reader_gid(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value):
        raise ContractError('explicit nonzero numeric reader GID required')
    number = int(value)
    if number > 2147483647:
        raise ContractError('reader GID out of range')
    return number


@dataclass(frozen=True)
class Spec:
    source: str
    gid: int


def environment(values):
    if isinstance(values, dict):
        return values
    if not isinstance(values, list):
        raise ContractError('ambiguous container environment')
    result = {}
    for item in values:
        if not isinstance(item, str) or '=' not in item:
            raise ContractError('invalid container environment')
        key, value = item.split('=', 1)
        if key in result:
            raise ContractError('duplicate container environment')
        result[key] = value
    return result


def _validate_environment(env, gid, source):
    if (env.get('RECOVERY_CONTROL_VERSION') != VERSION
            or env.get('RECOVERY_CONTROL_DIR') != TARGET
            or env.get('RECOVERY_STATE_PATH') != STATE_PATH
            or env.get('RECOVERY_CONTROL_SOURCE_DIR') != source
            or env.get('RECOVERY_READER_GID') != str(gid)
            or 'RECOVERY_CONTROL_FILE' in env):
        raise ContractError('recovery directory v1 environment required')


def _short_bind(mount):
    if not isinstance(mount, str):
        raise ContractError('invalid mount')
    parts = re.split(r':(?![^{}]*\})', mount)
    if len(parts) not in (2, 3):
        raise ContractError('ambiguous short mount')
    source, target = parts[:2]
    return {'type': 'bind' if source.startswith(('/', '.')) else 'volume',
            'source': source, 'target': target,
            'read_only': len(parts) == 3 and parts[2] == 'ro'}


def validate_compose(config):
    try:
        services = config['services']
        if config.get('configs') or config.get('secrets'):
            raise ContractError('additional config/secret mounts require separate review')
        for definition in config.get('volumes', {}).values():
            definition = definition or {}
            if (definition.get('driver', 'local') != 'local'
                    or definition.get('driver_opts') or definition.get('external')):
                raise ContractError('external or host-backed named volumes forbidden')
        api = services['api']
        mounts = api.get('volumes', [])
        if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
            raise ContractError('normalized long API mounts required')
        controls = [m for m in mounts if m.get('target') == TARGET]
        if len(controls) != 1:
            raise ContractError('exactly one control directory bind required')
        control = controls[0]
        if (control.get('type') != 'bind' or control.get('read_only') is not True
                or control.get('bind', {}).get('create_host_path') is not False
                or set(control) - {'type', 'source', 'target', 'read_only', 'bind'}
                or set(control.get('bind', {})) != {'create_host_path'}):
            raise ContractError('strict read-only directory bind required')
        source = absolute_path(control.get('source'))
        if source.name == LATCH:
            raise ContractError('legacy file source forbidden')
        env = environment(api['environment'])
        gid = reader_gid(env.get('RECOVERY_READER_GID'))
        _validate_environment(env, gid, str(source))
        if api.get('group_add') != [str(gid)]:
            raise ContractError('explicit reader group required')
        if 'user' in api and str(api['user']).split(':')[0] in ('', '0', 'root'):
            raise ContractError('root API forbidden')
        for service, definition in services.items():
            if definition.get('volumes_from') or definition.get('configs') or definition.get('secrets'):
                raise ContractError('inherited/config/secret mounts require separate review')
            targets = set()
            for entry in definition.get('volumes', []):
                mount = _short_bind(entry) if isinstance(entry, str) else entry
                if not isinstance(mount, dict):
                    raise ContractError('invalid mount')
                target = str(absolute_path(mount.get('target')))
                if target in targets or target in OLD_TARGETS:
                    raise ContractError('duplicate target or legacy file bind')
                targets.add(target)
                expected = service == 'api' and entry is control
                if service == 'api' and overlaps(PurePosixPath(target), PurePosixPath(TARGET)) and not expected:
                    raise ContractError('control target masked or aliased')
                if mount.get('type') == 'bind':
                    bind_source = absolute_path(mount.get('source'))
                    if overlaps(source, bind_source) and not expected:
                        raise ContractError('control source alias forbidden, including read-only aliases')
                elif mount.get('type') != 'volume' and not expected:
                    raise ContractError('unknown mount type')
            temporary = definition.get('tmpfs', [])
            temporary = [temporary] if isinstance(temporary, str) else temporary
            if not isinstance(temporary, list):
                raise ContractError('ambiguous tmpfs configuration')
            for entry in temporary:
                if not isinstance(entry, str):
                    raise ContractError('ambiguous tmpfs mount')
                target = str(absolute_path(entry.split(':', 1)[0]))
                if (target in targets or target in OLD_TARGETS
                        or service == 'api' and overlaps(PurePosixPath(target), PurePosixPath(TARGET))):
                    raise ContractError('tmpfs masks a declared or control mount')
                targets.add(target)
        return Spec(str(source), gid)
    except (KeyError, TypeError, AttributeError) as error:
        raise ContractError('incomplete or ambiguous Compose configuration') from error


def diagnose_legacy(config):
    """Diagnostic only. This never returns an authorization."""
    findings = []
    for service, definition in config.get('services', {}).items():
        for entry in definition.get('volumes', []):
            mount = _short_bind(entry) if isinstance(entry, str) else entry
            if mount.get('target') in OLD_TARGETS:
                findings.append(service + ':' + mount['target'])
    return {'legacy_file_binds': findings, 'operationally_accepted': False}


def validate_containers(containers, spec):
    source = absolute_path(spec.source)
    api_count = 0
    for container in containers:
        service = container['Config'].get('Labels', {}).get('com.docker.compose.service')
        if service == 'api':
            api_count += 1
            _validate_environment(environment(container['Config']['Env']), spec.gid, spec.source)
            user = container['Config'].get('User', '').split(':')[0]
            if not user or user in ('0', 'root'):
                raise ContractError('non-root image USER must be explicit')
            if container['HostConfig'].get('GroupAdd') != [str(spec.gid)]:
                raise ContractError('running reader group mismatch')
        count = 0
        targets = set()
        for mount in container.get('Mounts', []):
            target = str(absolute_path(mount.get('Destination')))
            if target in targets or target in OLD_TARGETS:
                raise ContractError('legacy or duplicate running mount')
            targets.add(target)
            expected = (service == 'api' and target == TARGET
                        and mount.get('Type') == 'bind'
                        and mount.get('Source') == spec.source and mount.get('RW') is False)
            if expected:
                count += 1
            if service == 'api' and overlaps(PurePosixPath(target), PurePosixPath(TARGET)) and not expected:
                raise ContractError('running control mount masked')
            if mount.get('Type') != 'tmpfs':
                actual_source = absolute_path(mount.get('Source'))
                if overlaps(source, actual_source) and not expected:
                    raise ContractError('running source alias forbidden')
        if service == 'api' and count != 1:
            raise ContractError('running control directory bind required')
    if api_count != 1:
        raise ContractError('exactly one running API required')


def _require_linux():
    if sys.platform != 'linux':
        raise ContractError('host ownership validation requires Linux')


def _lstat(path):
    return path.lstat()


def _trusted_parents(path):
    for parent in path.parents:
        info = _lstat(parent)
        writable = info.st_mode & 0o022
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or writable and not sticky_root):
            raise ContractError('untrusted or symlinked ancestor')


def _check_file(info, gid):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o440
            or info.st_nlink != 1 or info.st_size > 1024):
        raise ContractError('latch must be root:reader 0440, regular and single-link')


@dataclass(frozen=True)
class HostControl:
    path: Path
    gid: int
    identity: tuple


def validate_host(source, gid, *, forbidden_roots=(), expected=None, allow_missing=False):
    _require_linux()
    reader_gid(str(gid))
    absolute_path(str(source))
    path = Path(source)
    _trusted_parents(path)
    info = _lstat(path)
    identity = (info.st_dev, info.st_ino)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o750
            or expected is not None and identity != expected.identity):
        raise ContractError('control directory identity/ownership/mode invalid')
    for root in (*forbidden_roots, '/proc', '/sys', '/dev'):
        if overlaps(absolute_path(str(path)), PurePosixPath(str(root))):
            raise ContractError('control overlaps deployment, data or special filesystem')
    names = set(os.listdir(path))
    if names - {LATCH} or (not allow_missing and LATCH not in names):
        raise ContractError('dedicated directory must contain only the latch')
    if LATCH in names:
        _check_file(_lstat(path / LATCH), gid)
    return HostControl(path, gid, identity)


@contextmanager
def operator_lock(path, control, owner_uid):
    import fcntl
    path = Path(path)
    absolute_path(str(path))
    _trusted_parents(path)
    if overlaps(PurePosixPath(str(path)), PurePosixPath(str(control.path))):
        raise ContractError('operator lock must remain outside control directory')
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                or (info.st_dev, info.st_ino) != (_lstat(path).st_dev, _lstat(path).st_ino)):
            raise ContractError('untrusted or replaced operator lock')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _metadata(descriptor, gid):
    os.fchown(descriptor, 0, gid)
    os.fchmod(descriptor, 0o440)
    _check_file(os.fstat(descriptor), gid)


@contextmanager
def _directory(control):
    descriptor = os.open(control.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != control.identity:
            raise ContractError('control directory was replaced')
        yield descriptor
    finally:
        os.close(descriptor)


def publish_quarantine(control, *, lock_path, lock_owner_uid):
    """Close only; caller must provision a new runtime directory, never a proof folder."""
    _require_linux()
    if os.geteuid() != 0:
        raise ContractError('privileged operator required')
    raw = b'{"format":1,"state":"quarantined"}\n'
    temporary = '.recovery-' + uuid.uuid4().hex + '.tmp'
    with operator_lock(lock_path, control, lock_owner_uid):
        validate_host(str(control.path), control.gid, expected=control, allow_missing=True)
        with _directory(control) as directory:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    _metadata(output.fileno(), control.gid)
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, LATCH, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
                validate_host(str(control.path), control.gid, expected=control)
                descriptor = os.open(LATCH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(descriptor, 'rb') as published:
                    _check_file(os.fstat(published.fileno()), control.gid)
                    if published.read(1025) != raw:
                        raise ContractError('quarantine publication readback mismatch')
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
    return {'state': json.loads(raw)['state'], 'directory_identity': control.identity}
