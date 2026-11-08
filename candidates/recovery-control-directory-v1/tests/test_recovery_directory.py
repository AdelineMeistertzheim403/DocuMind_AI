import ast
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from types import SimpleNamespace

import pytest

from tools import recovery_control_directory as contract
from tools import validate_recovery_candidate as validator

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'


def model(name='compose.production.yaml'):
    return validator.render_synthetic(validator.load_yaml(SOURCE / name))


def control_mount(config):
    return next(m for m in config['services']['api']['volumes'] if m['target'] == contract.TARGET)


@pytest.mark.parametrize('name', validator.COMPOSE_FILES)
def test_complete_candidates_replace_file_bind_and_preserve_security(name):
    raw = validator.load_yaml(SOURCE / name)
    baseline = json.loads((ROOT / 'COMPOSE_SECURITY_BASELINE.json').read_text())
    assert validator.security_projection(raw) == baseline[name]
    spec = contract.validate_compose(validator.render_synthetic(raw))
    assert spec.source == validator.SYNTHETIC['RECOVERY_CONTROL_DIR']
    assert spec.gid == 42051


@pytest.mark.parametrize('fault', [
    'old-bind', 'old-short-bind', 'rw', 'auto-create', 'extra-bind-option',
    'duplicate', 'nested', 'ancestor-target', 'rw-alias', 'ro-alias',
    'other-service-alias', 'child-alias', 'relative', 'dot-dot', 'double-slash',
    'file-source', 'old-env', 'wrong-path', 'wrong-version', 'root-gid',
    'ambiguous-gid', 'missing-group', 'root-user', 'unknown-mount',
    'tmpfs-mask', 'inherited', 'secret-mount', 'driver-alias', 'normalized-relative-source',
])
def test_compose_rejects_legacy_aliases_and_ambiguity(fault):
    config = model()
    api = config['services']['api']
    mount = control_mount(config)
    if fault == 'old-bind':
        api['volumes'].append(dict(type='bind', source=mount['source'] + '/recovery-state.json',
                                   target='/run/documind/recovery-state.json', read_only=True))
    elif fault == 'old-short-bind':
        config['services']['web']['volumes'] = ['/srv/legacy:/app/recovery-state.json:ro']
    elif fault == 'rw':
        mount['read_only'] = False
    elif fault == 'auto-create':
        mount['bind']['create_host_path'] = True
    elif fault == 'extra-bind-option':
        mount['bind']['propagation'] = 'shared'
    elif fault == 'duplicate':
        api['volumes'].append(copy.deepcopy(mount))
    elif fault in ('nested', 'ancestor-target'):
        api['volumes'].append(dict(type='volume', source='mask',
                                   target=contract.STATE_PATH if fault == 'nested' else '/run'))
    elif fault in ('rw-alias', 'ro-alias', 'other-service-alias', 'child-alias'):
        service = config['services']['web'] if fault == 'other-service-alias' else api
        source = '/srv/qualification' if fault != 'child-alias' else mount['source'] + '/recovery-state.json'
        service.setdefault('volumes', []).append(dict(type='bind', source=source,
            target='/alias', read_only=fault == 'ro-alias'))
    elif fault in ('relative', 'dot-dot', 'double-slash', 'file-source'):
        mount['source'] = {
            'relative': 'relative/control', 'dot-dot': '/srv/a/../control',
            'double-slash': '/srv//control', 'file-source': '/srv/control/recovery-state.json',
        }[fault]
    elif fault == 'old-env':
        api['environment']['RECOVERY_CONTROL_FILE'] = '/srv/legacy'
    elif fault == 'wrong-path':
        api['environment']['RECOVERY_STATE_PATH'] = '/app/recovery-state.json'
    elif fault == 'wrong-version':
        api['environment']['RECOVERY_CONTROL_VERSION'] = '2'
    elif fault in ('root-gid', 'ambiguous-gid'):
        api['environment']['RECOVERY_READER_GID'] = '0' if fault == 'root-gid' else '042051'
    elif fault == 'missing-group':
        api.pop('group_add')
    elif fault == 'root-user':
        api['user'] = '0:42051'
    elif fault == 'unknown-mount':
        api['volumes'].append(dict(type='mystery', target='/mystery'))
    elif fault == 'tmpfs-mask':
        api['tmpfs'] = [contract.STATE_PATH]
    elif fault == 'inherited':
        api['volumes_from'] = ['unreviewed']
    elif fault == 'secret-mount':
        api['secrets'] = [{'source': 'mask', 'target': contract.STATE_PATH}]
    elif fault == 'driver-alias':
        config['volumes']['production_documents']['driver_opts'] = {
            'type': 'none', 'o': 'bind', 'device': mount['source']}
    elif fault == 'normalized-relative-source':
        api['environment']['RECOVERY_CONTROL_SOURCE_DIR'] = 'relative/control'
    with pytest.raises(contract.ContractError):
        contract.validate_compose(config)


def test_yaml_duplicates_and_merges_fail(tmp_path):
    for document in ('services: {}\nservices: {}\n', 'services: {<<: {api: {}}}\n'):
        path = tmp_path / 'ambiguous.yaml'
        path.write_text(document)
        with pytest.raises((contract.ContractError, validator.yaml.constructor.ConstructorError)):
            validator.load_yaml(path)


def containers():
    config = model()
    api = config['services']['api']
    return [{
        'Config': {'Labels': {'com.docker.compose.service': 'api'}, 'User': 'app',
                   'Env': [key + '=' + str(value) for key, value in api['environment'].items()]},
        'HostConfig': {'GroupAdd': ['42051']},
        'Mounts': [
            {'Type': 'bind', 'Source': validator.SYNTHETIC['RECOVERY_CONTROL_DIR'],
             'Destination': contract.TARGET, 'RW': False},
            {'Type': 'volume', 'Source': '/var/lib/docker/volumes/documents/_data',
             'Destination': '/app/var', 'RW': True},
            {'Type': 'tmpfs', 'Destination': '/tmp', 'Source': '', 'RW': True},
        ],
    }]


def test_actual_inspect_model_and_diagnostic_only_legacy():
    config = model()
    contract.validate_containers(containers(), contract.validate_compose(config))
    config['services']['api']['volumes'].append({
        'type': 'bind', 'source': '/srv/old', 'target': '/run/documind/recovery-state.json'})
    assert contract.diagnose_legacy(config) == {
        'legacy_file_binds': ['api:/run/documind/recovery-state.json'], 'operationally_accepted': False}
    with pytest.raises(contract.ContractError):
        contract.validate_compose(config)


@pytest.mark.parametrize('fault', [
    'rw', 'old', 'nested', 'alias', 'other-container-alias', 'user', 'group',
    'environment', 'duplicate-env', 'missing-api', 'duplicate-api',
])
def test_inspect_model_rejects_unsafe_running_mounts(fault):
    values = containers()
    api = values[0]
    if fault == 'rw':
        api['Mounts'][0]['RW'] = True
    elif fault == 'old':
        api['Mounts'][0]['Destination'] = '/run/documind/recovery-state.json'
    elif fault == 'nested':
        api['Mounts'].append({'Type': 'tmpfs', 'Destination': contract.STATE_PATH})
    elif fault in ('alias', 'other-container-alias'):
        alias = {'Type': 'bind', 'Destination': '/alias', 'Source': '/srv/qualification', 'RW': True}
        if fault == 'alias':
            api['Mounts'].append(alias)
        else:
            values.append({'Config': {'Labels': {'com.docker.compose.service': 'web'}}, 'Mounts': [alias]})
    elif fault == 'user':
        api['Config']['User'] = 'root'
    elif fault == 'group':
        api['HostConfig']['GroupAdd'] = []
    elif fault == 'environment':
        api['Config']['Env'] = ['RECOVERY_CONTROL_VERSION=0']
    elif fault == 'duplicate-env':
        api['Config']['Env'].append('RECOVERY_STATE_PATH=' + contract.STATE_PATH)
    elif fault == 'missing-api':
        values.clear()
    elif fault == 'duplicate-api':
        values.append(copy.deepcopy(api))
    with pytest.raises(contract.ContractError):
        contract.validate_containers(values, contract.validate_compose(model()))


def metadata(mode, uid=0, gid=42051, inode=10, links=1, size=32):
    return SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid, st_dev=1,
                           st_ino=inode, st_nlink=links, st_size=size)


@pytest.fixture
def host_model(monkeypatch):
    directory = PurePosixPath('/srv/laboratory/control')
    file = directory / contract.LATCH
    entries = {
        str(directory): metadata(stat.S_IFDIR | 0o750),
        str(file): metadata(stat.S_IFREG | 0o440, inode=11),
    }

    def lstat(path):
        return entries.get(str(path), metadata(stat.S_IFDIR | 0o755))

    monkeypatch.setattr(contract, '_require_linux', lambda: None)
    monkeypatch.setattr(contract, 'Path', PurePosixPath)
    monkeypatch.setattr(contract, '_lstat', lstat)
    monkeypatch.setattr(contract.os, 'listdir', lambda path: [contract.LATCH])
    return SimpleNamespace(path=directory, file=file, entries=entries)


def test_posix_metadata_model_accepts_and_pins_directory(host_model):
    h = host_model
    control = contract.validate_host(str(h.path), 42051)
    assert control.identity == (1, 10)
    h.entries[str(h.path)].st_ino = 20
    with pytest.raises(contract.ContractError, match='identity'):
        contract.validate_host(str(h.path), 42051, expected=control)


@pytest.mark.parametrize('fault', [
    'dir-mode', 'dir-owner', 'dir-group', 'dir-symlink', 'file-mode',
    'file-owner', 'file-group', 'file-hardlink', 'file-symlink', 'fifo',
    'device', 'oversized', 'parent-symlink', 'parent-writable', 'parent-owner',
    'deployment', 'data-root', 'control-parent-of-release',
])
def test_posix_metadata_model_rejects_unsafe_sources(host_model, fault):
    h = host_model
    directory, file = h.entries[str(h.path)], h.entries[str(h.file)]
    roots = ()
    if fault == 'dir-mode':
        directory.st_mode = stat.S_IFDIR | 0o770
    elif fault == 'dir-owner':
        directory.st_uid = 1000
    elif fault == 'dir-group':
        directory.st_gid = 1000
    elif fault == 'dir-symlink':
        directory.st_mode = stat.S_IFLNK | 0o750
    elif fault == 'file-mode':
        file.st_mode = stat.S_IFREG | 0o600
    elif fault == 'file-owner':
        file.st_uid = 1000
    elif fault == 'file-group':
        file.st_gid = 1000
    elif fault == 'file-hardlink':
        file.st_nlink = 2
    elif fault in ('file-symlink', 'fifo', 'device'):
        file.st_mode = {'file-symlink': stat.S_IFLNK, 'fifo': stat.S_IFIFO, 'device': stat.S_IFCHR}[fault] | 0o440
    elif fault == 'oversized':
        file.st_size = 1025
    elif fault.startswith('parent-'):
        h.entries[str(h.path.parent)] = metadata(stat.S_IFDIR | 0o755)
        parent = h.entries[str(h.path.parent)]
        if fault == 'parent-symlink':
            parent.st_mode = stat.S_IFLNK | 0o755
        elif fault == 'parent-writable':
            parent.st_mode = stat.S_IFDIR | 0o777
        else:
            parent.st_uid = 1000
    elif fault in ('deployment', 'data-root'):
        roots = (str(h.path.parent),)
    elif fault == 'control-parent-of-release':
        roots = (str(h.path / 'release'),)
    with pytest.raises(contract.ContractError):
        contract.validate_host(str(h.path), 42051, forbidden_roots=roots)


def test_missing_source_and_extra_entries_fail(host_model, monkeypatch):
    h = host_model
    monkeypatch.setattr(contract.os, 'listdir', lambda path: [])
    with pytest.raises(contract.ContractError):
        contract.validate_host(str(h.path), 42051)
    control = contract.validate_host(str(h.path), 42051, allow_missing=True)
    monkeypatch.setattr(contract.os, 'listdir', lambda path: [contract.LATCH, '.old'])
    with pytest.raises(contract.ContractError):
        contract.validate_host(str(h.path), 42051, expected=control)


def test_atomic_publisher_order_and_failure_boundaries(monkeypatch):
    """Descriptor/POSIX operations are modeled, not claimed as Windows DAC proof."""
    control = contract.HostControl(Path('/srv/laboratory/control'), 42051, (1, 10))
    raw = b'{"format":1,"state":"quarantined"}\n'
    for boundary in (None, 'metadata', 'file-fsync', 'replace', 'dir-fsync'):
        events = []
        published = [b'{"format":1,"state":"ready"}']
        pending = [b'']

        def event(name):
            events.append(name)
            if name == boundary:
                raise OSError('synthetic interruption')

        @contextmanager
        def lock(*args):
            event('lock')
            yield
            event('unlock')

        @contextmanager
        def directory(*args):
            yield 100

        class File:
            def __init__(self, mode):
                self.mode = mode

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def fileno(self):
                return 101

            def write(self, payload):
                event('write')
                pending[0] = payload

            def flush(self):
                event('flush')

            def read(self, size):
                event('readback')
                return published[0]

        def replace(*args, **kwargs):
            event('replace')
            published[0] = pending[0]

        def fsync(descriptor):
            event('dir-fsync' if descriptor == 100 else 'file-fsync')

        def unlink(*args, **kwargs):
            event('cleanup')

        with monkeypatch.context() as patch:
            patch.setattr(contract, '_require_linux', lambda: None)
            patch.setattr(contract.os, 'geteuid', lambda: 0, raising=False)
            patch.setattr(contract, 'operator_lock', lock)
            patch.setattr(contract, 'validate_host', lambda *a, **k: control)
            patch.setattr(contract, '_directory', directory)
            patch.setattr(contract, '_metadata', lambda fd, gid: event('metadata'))
            patch.setattr(contract, '_check_file', lambda info, gid: None)
            patch.setattr(contract.os, 'open', lambda *a, **k: 101)
            patch.setattr(contract.os, 'fdopen', lambda fd, mode: File(mode))
            patch.setattr(contract.os, 'fstat', lambda fd: None)
            patch.setattr(contract.os, 'fsync', fsync)
            patch.setattr(contract.os, 'replace', replace)
            patch.setattr(contract.os, 'unlink', unlink)
            for name in ('O_NOFOLLOW', 'O_NONBLOCK'):
                patch.setattr(contract.os, name, getattr(contract.os, name, 0), raising=False)
            if boundary:
                with pytest.raises(OSError):
                    contract.publish_quarantine(control, lock_path='/srv/laboratory/.operator.lock', lock_owner_uid=0)
            else:
                result = contract.publish_quarantine(control, lock_path='/srv/laboratory/.operator.lock', lock_owner_uid=0)
                assert result['state'] == 'quarantined'
        if boundary in ('metadata', 'file-fsync', 'replace'):
            assert b'"ready"' in published[0]
        else:
            assert published[0] == raw
        if 'replace' in events:
            assert events.index('metadata') < events.index('file-fsync') < events.index('replace')
        if 'dir-fsync' in events:
            assert events.index('replace') < events.index('dir-fsync')
        assert events[0] == 'lock' and 'cleanup' in events


def test_publisher_sets_owner_then_mode_before_accepting_metadata(monkeypatch):
    events = []
    monkeypatch.setattr(contract.os, 'fchown', lambda fd, uid, gid: events.append(('owner', uid, gid)), raising=False)
    monkeypatch.setattr(contract.os, 'fchmod', lambda fd, mode: events.append(('mode', mode)), raising=False)
    monkeypatch.setattr(contract.os, 'fstat', lambda fd: metadata(stat.S_IFREG | 0o440))
    contract._metadata(101, 42051)
    assert events == [('owner', 0, 42051), ('mode', 0o440)]


def test_operational_entry_points_are_disabled_and_helpers_attested():
    from tools import deploy_production, backup_production, public_beta_backup, backup_local, release_security
    for function, args in (
        (deploy_production.main, ()), (deploy_production.execute, (None, None)),
        (backup_production.main, ()), (backup_production.execute, (None, None)),
        (public_beta_backup.main, ()), (public_beta_backup.execute, (None, None, None)),
        (backup_local.main, ()),
    ):
        with pytest.raises(contract.ContractError, match='CANDIDATE_ONLY'):
            function(*args)
    assert 'recovery_control_directory.py' in deploy_production.CONTROLLER_FILES
    assert 'recovery_control_directory.py' in release_security.BUNDLE_FILES
    assert 'recovery_control_directory.py' not in release_security.LEGACY_BUNDLE_FILES


def test_beta_lock_location_is_independent_of_control_directory(monkeypatch):
    from tools import public_beta_backup as backup
    historical = Path('/opt/documind-public-beta/.public-beta-backup.lock')
    assert backup.OPERATOR_LOCK == historical
    monkeypatch.setattr(backup, 'CONTROL', Path('/different/control/recovery-state.json'))
    monkeypatch.setattr(backup, 'CONTROL_DIR', Path('/different/control'))
    assert backup.OPERATOR_LOCK == historical
    assert backup.DEPLOYMENT_BASE == historical.parent
    tree = ast.parse((SOURCE / 'tools' / 'public_beta_backup.py').read_text())
    lock = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'operator_lock')
    assert 'CONTROL' not in {node.id for node in ast.walk(lock) if isinstance(node, ast.Name)}
    assert not any(isinstance(node, ast.Attribute) and node.attr in ('replace', 'unlink') for node in ast.walk(lock))


def test_backup_local_rejects_old_contract_before_external_work(monkeypatch, tmp_path):
    from tools import backup_local
    config = model()
    control_mount(config)['target'] = '/run/documind/recovery-state.json'
    monkeypatch.setattr(backup_local, '_compose_config', lambda *args: config)
    monkeypatch.setattr(backup_local, '_assert_quiescent', lambda *args: pytest.fail('must reject before external work'))
    with pytest.raises(contract.ContractError):
        backup_local.create_backup([], tmp_path / 'must-not-exist')
    assert not (tmp_path / 'must-not-exist').exists()


def test_deploy_and_beta_guards_accept_new_shape_and_reject_old(monkeypatch):
    from tools import deploy_production as deploy, public_beta_backup as beta
    config = model()
    stack = SimpleNamespace()
    monkeypatch.setattr(deploy, '_validate_recovery_control_source', lambda stack, source: Path(source))
    deploy.validate_recovery_control_config(stack, config)
    assert stack.recovery_control_path == Path(validator.SYNTHETIC['RECOVERY_CONTROL_DIR'])
    control_mount(config)['target'] = '/run/documind/recovery-state.json'
    with pytest.raises(deploy.DeploymentError):
        deploy.validate_recovery_control_config(stack, config)
    config = model('compose.public-beta.vps.yaml')
    control = PurePosixPath(validator.SYNTHETIC['RECOVERY_CONTROL_DIR']) / contract.LATCH
    assert beta.validate_config(config, control).gid == 42051
    control_mount(config)['read_only'] = False
    with pytest.raises(beta.BackupError):
        beta.validate_config(config, control)


def test_candidate_backend_and_harness_unchanged():
    origin = json.loads((ROOT / 'ORIGIN.json').read_text())['files_sha256']
    for name in origin:
        if name.startswith('backend/') or name == 'tests/test_recovery_quarantine_inprocess.py':
            assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == origin[name]


def test_static_lab_recipe_cannot_start_application_or_network():
    raw = validator.load_yaml(ROOT / 'lab' / 'compose.static.yaml')
    assert set(raw['services']) == {'api'}
    api = raw['services']['api']
    assert api['network_mode'] == 'none'
    assert api['pull_policy'] == 'never'
    assert not api.get('ports') and not api.get('networks') and not api.get('build')
    assert api['read_only'] is True and api['cap_drop'] == ['ALL']
    assert api['command'] == ['--idle']
    assert all(mount['read_only'] is True for mount in api['volumes'])
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(validator.SYNTHETIC, 'LAB_PROBE', '/srv/qualification/candidate/lab/docker_reader.py')
        patch.setitem(validator.SYNTHETIC, 'LAB_READER_UID', '10001')
        patch.setitem(validator.SYNTHETIC, 'LAB_READER_PRIMARY_GID', '10001')
        contract.validate_compose(validator.render_synthetic(raw))


def test_backup_preflight_reaches_new_host_policy_before_container_commands(monkeypatch):
    from tools import backup_production as backup
    config = model()
    subject = object.__new__(backup.ActiveRelease)
    subject.env = {}
    subject.release = {'images': {
        component: config['services'][service]['image']
        for service, component in (('db', 'postgres'), ('api', 'backend'), ('web', 'frontend'))
    }}
    subject.call = lambda *args: json.dumps(config)

    class VirtualPath(PurePosixPath):
        def is_symlink(self):
            return False

        def is_dir(self):
            return True

        def resolve(self):
            return self

    class ReachedHostPolicy(Exception):
        pass

    subject.root = VirtualPath('/srv/release')

    def host(source, gid, **kwargs):
        assert source == validator.SYNTHETIC['RECOVERY_CONTROL_DIR'] and gid == 42051
        assert kwargs['forbidden_roots'] == ('/srv/release', '/var/lib/docker')
        raise ReachedHostPolicy()

    monkeypatch.setattr(backup, 'Path', VirtualPath)
    monkeypatch.setattr(backup, 'check_security_maintenance', lambda *args: None)
    monkeypatch.setattr(backup, 'command', lambda argv, env: '/var/lib/docker' if argv == [
        'docker', 'info', '--format', '{{.DockerRootDir}}'] else pytest.fail('unexpected external command'))
    monkeypatch.setattr(contract, 'validate_host', host)
    with pytest.raises(ReachedHostPolicy):
        subject.preflight()
    control_mount(config)['target'] = '/run/documind/recovery-state.json'
    with pytest.raises(backup.BackupError):
        subject.preflight()


def test_legacy_bundle_cannot_authorize_even_candidate_rollback(monkeypatch, tmp_path):
    from tools import release_security as security
    monkeypatch.setattr(security, 'validate_statement', lambda *args: (
        {'bundle_sha256': {name: '0' * 64 for name in security.LEGACY_BUNDLE_FILES}}, 'synthetic'))
    with pytest.raises(security.SecurityError, match='diagnostic-only'):
        security.validate_operational_bundle(tmp_path, {}, rollback=True)


def test_operator_lock_model_never_creates_truncates_or_unlinks(monkeypatch):
    events = []
    lock = PurePosixPath('/srv/deployment/.public-beta-backup.lock')
    control = contract.HostControl(PurePosixPath('/srv/deployment/recovery-control'), 42051, (1, 10))
    info = metadata(stat.S_IFREG | 0o600, uid=1000, inode=77)
    monkeypatch.setattr(contract, 'Path', PurePosixPath)
    monkeypatch.setattr(contract, '_trusted_parents', lambda path: None)
    monkeypatch.setattr(contract, '_lstat', lambda path: info)
    monkeypatch.setattr(contract.os, 'O_NOFOLLOW', getattr(os, 'O_NOFOLLOW', 0x10000000), raising=False)

    def open_lock(path, flags):
        assert path == lock
        assert not flags & (os.O_CREAT | os.O_TRUNC)
        assert flags & os.O_NOFOLLOW
        events.append('open')
        return 101

    monkeypatch.setattr(contract.os, 'open', open_lock)
    monkeypatch.setattr(contract.os, 'fstat', lambda fd: info)
    monkeypatch.setattr(contract.os, 'close', lambda fd: events.append('close'))
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(
        LOCK_EX=1, LOCK_NB=2, flock=lambda fd, flags: events.append(('flock', fd, flags))))
    with contract.operator_lock(lock, control, owner_uid=1000):
        events.append('held')
    assert events == ['open', ('flock', 101, 3), 'held', 'close']
