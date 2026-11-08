"""Review-only P3 source/render/host preflight. Never invokes Docker or creates sources."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

try:
    from . import recovery_control_directory as contract
    from . import validate_recovery_candidate as validator
except ImportError:
    import recovery_control_directory as contract
    import validate_recovery_candidate as validator

PARAMETERS = {
    'LAB_IMAGE', 'LAB_PYTHON', 'LAB_READER_UID', 'LAB_READER_PRIMARY_GID',
    'RECOVERY_READER_GID', 'RECOVERY_CONTROL_DIR', 'LAB_PROBE',
}
LIMIT = 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise contract.ContractError('duplicate JSON key')
            result[key] = value
        return result

    def constant(value):
        raise contract.ContractError('nonfinite JSON value')

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as error:
        raise contract.ContractError('invalid JSON document') from error
    if not isinstance(value, dict):
        raise contract.ContractError('JSON object required')
    return value


def _read_regular(path):
    path = Path(path)
    if not path.is_absolute() or path.name.startswith('.env'):
        raise contract.ContractError('absolute non-dotenv input required')
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise contract.ContractError('symlinked preflight input')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT or before.st_nlink != 1:
            raise contract.ContractError('bounded single-link regular input required')
        raw = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        if (len(raw) > LIMIT or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise contract.ContractError('input changed during read')
    return raw


def _parameters(raw):
    values = strict_json(raw)
    if set(values) != PARAMETERS or not all(isinstance(value, str) for value in values.values()):
        raise contract.ContractError('only the seven explicit synthetic P3 parameters are allowed')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', values['LAB_IMAGE']):
        raise contract.ContractError('already-loaded image ID required, never a tag or registry reference')
    for key in ('LAB_READER_UID', 'LAB_READER_PRIMARY_GID', 'RECOVERY_READER_GID'):
        contract.reader_gid(values[key])
    for key in ('LAB_PYTHON', 'RECOVERY_CONTROL_DIR', 'LAB_PROBE'):
        contract.absolute_path(values[key])
    directory = PurePosixPath(values['RECOVERY_CONTROL_DIR'])
    if (directory.name != 'recovery-control' or directory.parent.parent != PurePosixPath('/var/tmp')
            or not re.fullmatch(r'docnelo-rcd-[a-f0-9]{32}', directory.parent.name)):
        raise contract.ContractError('only an existing marked P2 synthetic namespace is allowed')
    return values


def _expand(value, parameters, used, depth=0):
    if depth > 12:
        raise contract.ContractError('deep or recursive YAML forbidden')
    if isinstance(value, dict):
        return {key: _expand(item, parameters, used, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, parameters, used, depth + 1) for item in value]
    if isinstance(value, str):
        def substitute(match):
            name = match[1]
            if name not in parameters:
                raise contract.ContractError('unapproved source interpolation')
            used.add(name)
            return parameters[name]
        result = re.sub(r'\$\{([A-Z_][A-Z_0-9]*):\?[^{}]*\}', substitute, value)
        if '$' in result:
            raise contract.ContractError('unsupported source interpolation')
        return result
    return value


def _expected_api(values):
    def mount(source, target):
        return {'type': 'bind', 'source': source, 'target': target, 'read_only': True,
                'bind': {'create_host_path': False}}
    return {
        'image': values['LAB_IMAGE'], 'pull_policy': 'never',
        'user': values['LAB_READER_UID'] + ':' + values['LAB_READER_PRIMARY_GID'],
        'group_add': [values['RECOVERY_READER_GID']],
        'environment': {
            'RECOVERY_CONTROL_VERSION': '1', 'RECOVERY_CONTROL_DIR': contract.TARGET,
            'RECOVERY_CONTROL_SOURCE_DIR': values['RECOVERY_CONTROL_DIR'],
            'RECOVERY_READER_GID': values['RECOVERY_READER_GID'],
            'RECOVERY_STATE_PATH': contract.STATE_PATH,
        },
        'entrypoint': [values['LAB_PYTHON'], '-I', '-B', '/probe.py'],
        'command': ['--idle'], 'network_mode': 'none', 'read_only': True,
        'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'pids_limit': 64, 'mem_limit': '128m', 'cpus': 0.5,
        'volumes': [mount(values['RECOVERY_CONTROL_DIR'], contract.TARGET),
                    mount(values['LAB_PROBE'], '/probe.py')],
    }


def _validate_source(raw, values):
    try:
        document = validator.yaml.load(raw.decode('utf-8-sig'), Loader=validator.UniqueLoader)
    except (validator.yaml.YAMLError, UnicodeError) as error:
        raise contract.ContractError('invalid or ambiguous source YAML') from error
    try:
        if (set(document) != {'name', 'services'} or document['name'] != 'docnelo-rcd-static'
                or set(document['services']) != {'api'}):
            raise contract.ContractError('only the complete single-reader P3 source is supported')
        api = document['services']['api']
        mounts = api.get('volumes')
        if not isinstance(mounts, list) or len(mounts) != 2:
            raise contract.ContractError('exactly two source binds required')
        for mount in mounts:
            if (not isinstance(mount, dict) or mount.get('type') != 'bind'
                    or mount.get('read_only') is not True
                    or mount.get('bind') != {'create_host_path': False}
                    or mount.get('bind', {}).get('create_host_path') is not False):
                raise contract.ContractError('source YAML must explicitly declare every bind RO/create_host_path: false')
        used = set()
        expanded = _expand(document, values, used)
        if (used != PARAMETERS or expanded['services']['api']['read_only'] is not True
                or expanded['services']['api'] != _expected_api(values)):
            raise contract.ContractError('source differs from the approved static-reader security profile')
        return contract.validate_compose(expanded)
    except (TypeError, KeyError, AttributeError) as error:
        raise contract.ContractError('incomplete source YAML') from error


def _validate_rendered(raw, values, project):
    rendered = strict_json(raw)
    if not re.fullmatch(r'docnelo-rcd-[a-z0-9][a-z0-9_-]*', project):
        raise contract.ContractError('explicit isolated P3 project name required')
    if (rendered.get('name') != project or not isinstance(rendered.get('services'), dict)
            or set(rendered['services']) != {'api'}
            or set(rendered) - {'name', 'services', 'networks', 'volumes', 'configs', 'secrets'}
            or any(rendered.get(key) for key in ('networks', 'volumes', 'configs', 'secrets'))):
        raise contract.ContractError('unexpected rendered project, service or inherited resource')
    normalized = copy.deepcopy(rendered)
    api = normalized['services']['api']
    if not isinstance(api, dict):
        raise contract.ContractError('invalid rendered API')
    mounts = api.get('volumes')
    if not isinstance(mounts, list) or len(mounts) != 2:
        raise contract.ContractError('exactly two rendered binds required')
    reconstructed = []
    for mount in mounts:
        if not isinstance(mount, dict) or 'bind' not in mount or not isinstance(mount['bind'], dict):
            raise contract.ContractError('rendered bind mapping required')
        if mount['bind'] == {}:
            reconstructed.append(mount.get('target'))
            mount['bind'] = {'create_host_path': False}
        elif (set(mount['bind']) != {'create_host_path'}
                or mount['bind']['create_host_path'] is not False):
            raise contract.ContractError('rendered bind contradicts source or adds unreviewed options')
    spec = contract.validate_compose(normalized)
    if (api.get('read_only') is not True or
            any(mount.get('read_only') is not True for mount in mounts)):
        raise contract.ContractError('rendered reader and mounts must remain read-only')
    memory = api.get('mem_limit')
    if not ((type(memory) is int and memory == 134217728)
            or (type(memory) is str and memory in ('128m', '134217728'))):
        raise contract.ContractError('rendered mem_limit requires exactly 128m or 134217728 (string), or 134217728 (integer)')
    api['mem_limit'] = '128m'
    if isinstance(api.get('cpus'), str) and api['cpus'] == '0.5':
        api['cpus'] = 0.5
    expected = _expected_api(values)
    api['volumes'] = sorted(mounts, key=lambda mount: mount['target'])
    expected['volumes'] = sorted(expected['volumes'], key=lambda mount: mount['target'])
    if api != expected:
        raise contract.ContractError('rendered model differs from the validated source/parameters/security profile')
    return spec, reconstructed


def validate_documents(source, rendered, parameters, p2_record, *, expected_source_sha256,
                       expected_probe_sha256, project, docker_root):
    """All stages are mandatory. Empty bind dictionaries alone never authorize anything."""
    for expected in (expected_source_sha256, expected_probe_sha256):
        if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
            raise contract.ContractError('independently reviewed input hashes required')
    if any(len(raw) > LIMIT for raw in (source, rendered, parameters, p2_record)):
        raise contract.ContractError('oversized preflight document')
    if digest(source) != expected_source_sha256:
        raise contract.ContractError('source YAML checksum mismatch')
    values = _parameters(parameters)
    declared = _validate_source(source, values)
    observed, reconstructed = _validate_rendered(rendered, values, project)
    if declared != observed:
        raise contract.ContractError('source/rendered contract mismatch')
    record = strict_json(p2_record)
    if (set(record) != {'format', 'synthetic_only', 'gid', 'device', 'inode'}
            or type(record['format']) is not int or record['format'] != 1
            or record['synthetic_only'] is not True or type(record['gid']) is not int
            or record['gid'] != observed.gid
            or type(record['device']) is not int or record['device'] < 0
            or type(record['inode']) is not int or record['inode'] <= 0):
        raise contract.ContractError('valid pre-existing P2 identity record required')
    contract.absolute_path(docker_root)
    expected = contract.HostControl(Path(observed.source), observed.gid, (record['device'], record['inode']))
    try:
        host = contract.validate_host(observed.source, observed.gid,
                                      forbidden_roots=(docker_root,), expected=expected)
        probe = _read_regular(Path(values['LAB_PROBE']))
    except OSError as error:
        raise contract.ContractError('host source/probe unavailable; no creation is permitted') from error
    if digest(probe) != expected_probe_sha256:
        raise contract.ContractError('probe checksum mismatch')
    return {
        'revision': 'v1-r3', 'scope': 'REVIEW_ONLY_SOURCE_RENDER_HOST_PREFLIGHT',
        'source_sha256': digest(source), 'rendered_sha256': digest(rendered),
        'parameters_sha256': digest(parameters), 'p2_record_sha256': digest(p2_record),
        'probe_sha256': digest(probe), 'source': observed.source, 'reader_gid': observed.gid,
        'directory_device_inode': host.identity, 'project': project,
        'operator_supplied_docker_root': docker_root,
        'reconstructed_false_from_source_only': reconstructed,
        'container_created': False, 'container_started': False, 'p3_go': False,
        'requires_engine_inspection_before_start': True,
    }


def _new_evidence(path):
    path = Path(path)
    candidate = Path(__file__).resolve().parents[2]
    if (not path.is_absolute() or path.exists() or not path.parent.is_dir()
            or path.resolve().is_relative_to(candidate)
            or any(parent.is_symlink() for parent in (path, *path.parents))
            or any((parent / marker).exists() for parent in path.parents
                   for marker in ('INPUTS.json', 'SHA256SUMS', '.candidate-lab.json'))
            or any(part.lower() in {'releases', 'release', 'artifacts', 'fixtures', 'deliveries', 'source'}
                   or re.fullmatch(r'docnelo-rcd-[a-f0-9]{32}', part) for part in path.parts)):
        raise contract.ContractError('new evidence directory outside candidates/sealed evidence/namespaces required')
    path.mkdir(mode=0o700)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'rendered', 'parameters', 'p2-record', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('source-sha256', 'probe-sha256', 'project', 'docker-root'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        inputs = {name: _read_regular(getattr(args, name)) for name in
                  ('source', 'rendered', 'parameters', 'p2_record')}
        result = validate_documents(**inputs, expected_source_sha256=args.source_sha256,
                                    expected_probe_sha256=args.probe_sha256,
                                    project=args.project, docker_root=args.docker_root)
        evidence = _new_evidence(args.evidence)
        files = {
            'source.yaml': inputs['source'], 'rendered.json': inputs['rendered'],
            'parameters.json': inputs['parameters'], 'p2-record.json': inputs['p2_record'],
            'preflight.json': (json.dumps(result, indent=2) + '\n').encode(),
        }
        for name, raw in files.items():
            with (evidence / name).open('xb') as output:
                output.write(raw)
        (evidence / 'SHA256SUMS').write_text(''.join(
            digest(raw) + '  ' + name + '\n' for name, raw in sorted(files.items())), encoding='ascii')
        print(json.dumps(result, indent=2))
        return 0
    except (contract.ContractError, OSError) as error:
        print(json.dumps({'scope': 'REFUSED_NO_DOCKER_ACTION', 'error': str(error), 'p3_go': False}),
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
