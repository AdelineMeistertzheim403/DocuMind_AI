"""Attested overlay and host permissions: disposable native Linux only."""
import copy
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tools import deploy_production as deploy
from tools import release_security as security
from tools import backup_production as backup
from tests.test_release_security import approved_bundle
from tests.test_deployment import release
from tests.test_standard_erasure import lab

pytestmark = [
    pytest.mark.posix,
    pytest.mark.skipif(sys.platform != 'linux' or getattr(os, 'geteuid', lambda: -1)() != 0,
                       reason='Native root ownership qualification required'),
]


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / 'deployment'
    root.mkdir(mode=0o700)
    authority = tmp_path / 'authority'
    requests = tmp_path / 'requests'
    authority.mkdir(mode=0o755)
    requests.mkdir(mode=0o700)
    os.chown(requests, 65534, 65534)
    values = dict(zip(security.ERASURE_KEYS, (str(authority), str(requests), str(uuid4()), '65534')))
    trust = {'format': 1, 'releases': {}}
    bundle = root / 'releases' / 'candidate'
    candidate = approved_bundle(bundle, release('0008'), trust)
    trust_dir = tmp_path / 'independent-root-review'
    trust_dir.mkdir(mode=0o755)
    trust_path = trust_dir / 'trust.json'
    trust_path.write_text(json.dumps(trust))
    trust_path.chmod(0o644)
    monkeypatch.setattr(security, 'TRUST_PATH', trust_path)
    mounts = [
        {'type': 'volume', 'source': 'production_documents', 'target': '/app/var'},
        {'type': 'volume', 'source': 'production_lifecycle', 'target': '/app/lifecycle'},
    ]
    latch = tmp_path / 'recovery.json'
    latch.write_text('{"format":1,"state":"quarantined"}')
    mounts.append({'type': 'bind', 'source': str(latch), 'target': '/run/documind/recovery-state.json',
                   'read_only': True})
    for index, target in enumerate(security.ERASURE_TARGETS):
        mounts.append({'type': 'bind', 'source': values[security.ERASURE_KEYS[index]],
                       'target': target, 'read_only': index == 0, 'bind': {'create_host_path': False}})
    environment = dict(zip(('ERASURE_AUTHORITY_DIR', 'ERASURE_REQUESTS_DIR', 'ERASURE_INSTANCE_ID',
                            'ERASURE_APPLICATION_UID'),
                           (*security.ERASURE_TARGETS, values['ERASURE_INSTANCE_ID'], '65534')))
    config = {'services': {'api': {'volumes': mounts, 'environment': environment, 'read_only': True,
                                   'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true']}},
              'volumes': {name: {'name': deploy.PROJECT + '_' + name}
                          for name in ('production_documents', 'production_lifecycle')}}
    return SimpleNamespace(root=root, bundle=bundle, release=candidate, values=values, config=config,
                           authority=authority, requests=requests, trust=trust_path, latch=latch,
                           docker_root=tmp_path / 'docker')


def test_attested_overlay_is_one_compose_project_and_preserves_base(installation, monkeypatch):
    state = installation
    files, selected = security.erasure_compose_files(state.root, state.bundle, state.release, {})
    assert files == [state.bundle / 'compose.production.yaml'] and selected is None
    calls = []

    def run(command, env):
        calls.append(command)
        if command[-2:] == ['config', '--environment']:
            return '\n'.join(f'{key}={value}' for key, value in state.values.items())
        return '{}'

    monkeypatch.setattr(deploy, 'run', run)
    stack = deploy.Stack(state.root, state.bundle, state.release)
    stack.call('config', '--format', 'json')
    assert stack.compose_files == [state.bundle / name for name in ('compose.production.yaml', 'compose.erasure.yaml')]
    assert calls[-1].count('-p') == 1 and calls[-1][calls[-1].index('-p') + 1] == deploy.PROJECT
    assert calls[-1].count('-f') == 2 and not any('up' in call for call in calls)
    assert not (state.root / 'var/erasure-deployment.json').exists()


@pytest.mark.parametrize('tamper', ['missing', 'changed', 'image', 'unapproved', 'unattested'])
def test_overlay_selection_refuses_untrusted_bundle_before_docker(installation, tamper):
    state = installation
    if tamper == 'missing':
        (state.bundle / 'compose.erasure.yaml').unlink()
    elif tamper == 'changed':
        with (state.bundle / 'compose.erasure.yaml').open('a') as output:
            output.write('\n# changed after attestation\n')
    elif tamper == 'image':
        state.release['images']['backend'] = state.release['images']['backend'][:-64] + 'f' * 64
    elif tamper == 'unapproved':
        state.trust.write_text('{"format":1,"releases":{}}')
    else:
        (state.bundle / security.STATEMENT).unlink()
    with pytest.raises(security.SecurityError):
        security.erasure_compose_files(state.root, state.bundle, state.release, state.values)
    assert not (state.root / 'var/erasure-deployment.json').exists()


@pytest.mark.parametrize('invalid', [None, 'authority-absent', 'authority-writable', 'authority-app-owned',
    'requests-public', 'requests-root-owned', 'symlink', 'wrong-source', 'writable-authority',
    'readonly-requests', 'auto-create', 'root-user', 'capability', 'privileged', 'missing-cap-drop',
    'wrong-instance', 'extra-mount'])
def test_native_mount_contract_preserves_existing_volumes_and_refuses_unsafe_provisioning(
        installation, monkeypatch, invalid):
    state = installation
    config = copy.deepcopy(state.config)
    api = config['services']['api']
    if invalid == 'authority-absent':
        state.authority.rmdir()
    elif invalid == 'authority-writable':
        state.authority.chmod(0o777)
    elif invalid == 'authority-app-owned':
        os.chown(state.authority, 65534, 65534)
    elif invalid == 'requests-public':
        state.requests.chmod(0o755)
    elif invalid == 'requests-root-owned':
        os.chown(state.requests, 0, 0)
    elif invalid == 'symlink':
        other = state.authority.with_name('other-authority')
        state.authority.rename(other)
        state.authority.symlink_to(other, target_is_directory=True)
    elif invalid == 'wrong-source':
        api['volumes'][3]['source'] = str(state.requests)
    elif invalid == 'writable-authority':
        api['volumes'][3]['read_only'] = False
    elif invalid == 'readonly-requests':
        api['volumes'][4]['read_only'] = True
    elif invalid == 'auto-create':
        api['volumes'][3]['bind']['create_host_path'] = True
    elif invalid == 'root-user':
        api['user'] = '0'
    elif invalid == 'capability':
        api['cap_add'] = ['SETUID']
    elif invalid == 'privileged':
        api['privileged'] = True
    elif invalid == 'missing-cap-drop':
        api.pop('cap_drop')
    elif invalid == 'wrong-instance':
        api['environment']['ERASURE_INSTANCE_ID'] = str(uuid4())
    elif invalid == 'extra-mount':
        api['volumes'].append({'type': 'bind', 'source': '/var/run/docker.sock', 'target': '/socket'})
    stack = SimpleNamespace(root=state.root, erasure=state.values)
    monkeypatch.setattr(deploy, 'run', lambda *_: str(state.docker_root))
    if invalid:
        with pytest.raises(deploy.DeploymentError):
            deploy.validate_recovery_control_config(stack, config)
    else:
        deploy.validate_recovery_control_config(stack, config)
        assert stack.recovery_control_path == state.latch
        assert not (state.root / 'var/erasure-deployment.json').exists()


@pytest.mark.parametrize('change', ['removed', 'partial', 'uid', 'instance', 'authority'])
def test_durable_binding_forbids_silent_downgrade_or_rebinding(installation, change):
    state = installation
    security.pin_erasure_configuration(state.root, state.values)
    security.pin_erasure_configuration(state.root, state.values)
    values = dict(state.values)
    if change == 'removed':
        values = {}
    elif change == 'partial':
        values.pop('ERASURE_INSTANCE_ID')
    elif change == 'uid':
        values['ERASURE_APPLICATION_UID'] = '1000'
    elif change == 'instance':
        values['ERASURE_INSTANCE_ID'] = str(uuid4())
    else:
        values['ERASURE_AUTHORITY_HOST_DIR'] += '-other'
    with pytest.raises(security.SecurityError):
        security.erasure_compose_files(state.root, state.bundle, state.release, values)
    assert security.erasure_binding(state.root) == state.values


@pytest.mark.parametrize('invalid', [None, 'rw', 'source', 'privilege', 'uid', 'environment'])
def test_live_container_must_match_attested_mounts_identity_and_privileges(installation, invalid):
    state = installation
    api = state.config['services']['api']
    container = {'Config': {'User': 'app', 'Env': [f'{key}={value}' for key, value in api['environment'].items()]},
                 'HostConfig': {'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
                                'SecurityOpt': ['no-new-privileges:true']},
                 'Mounts': [{'Type': 'bind', 'Source': mount['source'], 'Destination': mount['target'],
                             'RW': not mount['read_only']} for mount in api['volumes'][3:]]}
    if invalid == 'rw':
        container['Mounts'][0]['RW'] = True
    elif invalid == 'source':
        container['Mounts'][1]['Source'] = '/other'
    elif invalid == 'privilege':
        container['HostConfig']['CapAdd'] = ['DAC_OVERRIDE']
    elif invalid == 'uid':
        container['Config']['User'] = '0'
    elif invalid == 'environment':
        container['Config']['Env'] = []
    if invalid:
        with pytest.raises(security.SecurityError):
            security.validate_erasure_container(container, state.values)
    else:
        security.validate_erasure_container(container, state.values)


@pytest.mark.parametrize('invalid', [None, 'live-authority-writable', 'binding-removed'])
def test_daily_backup_preflight_uses_the_same_approved_overlay_without_changing_services(
        installation, monkeypatch, invalid):
    state = installation
    (state.root / '.env.production').write_text('REGISTRATION_MODE=disabled\n')
    (state.root / '.env.production').chmod(0o600)
    (state.root / 'var').mkdir(mode=0o700)
    deploy.persist_runtime_state(state.root, state.bundle, state.release, '192.0.2.10')
    security.pin_erasure_configuration(state.root, state.values)
    deploy.point_to(state.root, 'current', state.bundle)
    report = deploy.deployment_report_path(state.root, state.bundle)
    report.parent.mkdir(mode=0o700)
    report.write_text(json.dumps({'status': 'success', 'git_sha': state.release['git_sha']}))
    report.chmod(0o600)
    config = copy.deepcopy(state.config)
    config['name'] = deploy.PROJECT
    config['services']['api']['environment'].update({
        'LIFECYCLE_DATA_ROOT': '/app/lifecycle', 'LIFECYCLE_BACKUP_LOCK_PATH': '/app/lifecycle/.backup.lock'})
    config['volumes']['production_database'] = {'name': deploy.PROJECT + '_production_database'}
    config['services']['db'] = {'volumes': [
        {'type': 'volume', 'source': 'production_database', 'target': '/var/lib/postgresql/data'}]}
    config['services']['web'] = {}
    containers = []
    for service, component in (('db', 'postgres'), ('api', 'backend'), ('web', 'frontend')):
        settings = config['services'][service]
        settings['image'] = state.release['images'][component]
        mounts = []
        for mount in settings.get('volumes', []):
            item = {'Type': mount['type'], 'Destination': mount['target']}
            if mount['type'] == 'volume':
                item['Name'] = deploy.PROJECT + '_' + mount['source']
            else:
                item.update(Source=mount['source'], RW=not mount.get('read_only', False))
            mounts.append(item)
        containers.append({
            'Image': component + '-id', 'State': {'Running': True, 'Health': {'Status': 'healthy'}},
            'Config': {'User': 'app', 'Env': [f'{key}={value}' for key, value in settings.get('environment', {}).items()],
                       'Labels': {'com.docker.compose.project': deploy.PROJECT, 'com.docker.compose.service': service,
                                  'com.docker.compose.project.config_files': ','.join(
                                      str(state.bundle / name) for name in ('compose.production.yaml', 'compose.erasure.yaml'))}},
            'HostConfig': {'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true']},
            'Mounts': mounts})
    if invalid == 'live-authority-writable':
        containers[1]['Mounts'][3]['RW'] = True
    original_helper = backup.load_helper
    monkeypatch.setattr(backup, 'load_helper', lambda bundle, name:
                        security if name == 'release_security' else original_helper(bundle, name))
    calls = []

    def command(argv, env=None, **kwargs):
        calls.append(argv)
        if argv[-2:] == ['config', '--environment']:
            return '' if invalid == 'binding-removed' else '\n'.join(
                f'{key}={value}' for key, value in state.values.items())
        if argv[-3:] == ['config', '--format', 'json']:
            return json.dumps(config)
        if argv[:2] == ['docker', 'info']:
            return str(state.docker_root)
        if argv[:3] == ['docker', 'ps', '-aq']:
            return 'db\napi\nweb'
        if argv[:2] == ['docker', 'inspect']:
            return json.dumps(containers if len(argv) == 5 else [
                next(item for item in containers if item['Config']['Labels']['com.docker.compose.service'] == argv[-1])])
        if argv[:3] == ['docker', 'image', 'inspect']:
            if argv[-1] == '{{json .Config.Labels}}':
                return json.dumps({'org.opencontainers.image.revision': state.release['git_sha'],
                                   security.LABEL: security.PROFILE})
            return next(component + '-id' for component, image in state.release['images'].items() if image == argv[3])
        if 'exec' in argv:
            return '0008'
        if 'ps' in argv:
            return argv[-1]
        pytest.fail('Unexpected backup command')

    monkeypatch.setattr(backup, 'command', command)
    active = backup.ActiveRelease(state.root)
    if invalid:
        with pytest.raises(backup.BackupError):
            active.preflight()
    else:
        active.preflight()
        assert active.compose.count('-f') == 2
    assert not any(word in argv for argv in calls for word in ('up', 'stop', 'run', 'down'))


@pytest.mark.parametrize('invalid', [None, 'root', 'uid', 'authority-absent'])
def test_real_non_root_runtime_probe_checks_provisioning_without_writing(lab, invalid):
    environment = dict(os.environ)
    for key, value in lab.settings.model_dump(mode='json').items():
        if value is not None:
            environment[key.upper()] = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
    environment['BFF_SERVICE_KEY'] = lab.settings.bff_service_key.get_secret_value()
    if invalid == 'uid':
        environment['ERASURE_APPLICATION_UID'] = '1000'
    elif invalid == 'authority-absent':
        (lab.paths['control'] / 'instance.json').unlink()
    before = sorted(path.name for path in lab.paths['control'].iterdir())
    prefix = 'import os; os.setgroups([]); os.setgid(65534); os.setuid(65534)\n' if invalid != 'root' else ''
    result = subprocess.run([sys.executable, '-c', prefix + deploy.ERASURE_PROBE],
                            env=environment, capture_output=True, text=True, timeout=20)
    assert (result.returncode == 0) is (invalid is None)
    if invalid is None:
        assert json.loads(result.stdout) == {'authority_checked': True, 'uid': 65534}
    assert sorted(path.name for path in lab.paths['control'].iterdir()) == before
