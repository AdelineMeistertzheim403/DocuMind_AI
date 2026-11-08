"""Static synthetic rendering only: no Compose, environment, dotenv or Docker access."""
import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import re
import sys

import yaml

try:
    from . import recovery_control_directory as contract
except ImportError:
    import recovery_control_directory as contract

COMPOSE_FILES = (
    'compose.yaml', 'compose.production.yaml',
    'compose.public-beta.vps.yaml', 'compose.public-beta-test.yaml',
)
SYNTHETIC = {
    'RECOVERY_CONTROL_DIR': '/srv/qualification/recovery-control',
    'RECOVERY_READER_GID': '42051',
    'BETA_RECIPE_DIR': '/srv/qualification/recipe',
}


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in values or key == '<<':
            raise contract.ContractError('duplicate YAML key or merge forbidden')
        values[key] = loader.construct_object(value_node)
    return values


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_yaml(path):
    result = yaml.load(Path(path).read_text(encoding='utf-8-sig'), Loader=UniqueLoader)
    if not isinstance(result, dict):
        raise contract.ContractError('complete Compose document required')
    return result


def _render(value):
    if isinstance(value, dict):
        return {key: _render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item) for item in value]
    if isinstance(value, str):
        def substitute(match):
            name, operation, default = match.groups()
            return SYNTHETIC.get(name, default if operation == ':-' else 'synthetic-only')
        return re.sub(r'\$\{([A-Z_0-9]+)(:[-?])?([^}]*)\}', substitute, value)
    return value


def render_synthetic(raw):
    """Minimal model for contract tests, deliberately NOT a Compose implementation."""
    config = _render(copy.deepcopy(raw))
    config.setdefault('name', 'synthetic-only')
    for logical, definition in list(config.get('volumes', {}).items()):
        definition = definition or {}
        definition.setdefault('name', config['name'] + '_' + logical)
        config['volumes'][logical] = definition
    for definition in config['services'].values():
        normalized = []
        for entry in definition.get('volumes', []):
            entry = contract._short_bind(entry) if isinstance(entry, str) else entry
            if entry.get('type') == 'bind' and entry.get('source', '').startswith('.'):
                entry['source'] = str(PurePosixPath('/srv/qualification/source') / entry['source'])
            normalized.append(entry)
        if 'volumes' in definition:
            definition['volumes'] = normalized
    return config


def security_projection(raw):
    result = copy.deepcopy(raw)
    api = result['services']['api']
    for key in ('RECOVERY_STATE_PATH', 'RECOVERY_CONTROL_VERSION', 'RECOVERY_CONTROL_DIR',
                'RECOVERY_CONTROL_SOURCE_DIR', 'RECOVERY_READER_GID'):
        api.get('environment', {}).pop(key, None)
    api.pop('group_add', None)
    api['volumes'] = [
        mount for mount in api.get('volumes', [])
        if (contract._short_bind(mount) if isinstance(mount, str) else mount).get('target')
        not in contract.OLD_TARGETS | {contract.TARGET}
    ]
    result['services'].get('lifecycle-init', {}).get('environment', {}).pop('RECOVERY_STATE_PATH', None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compose', type=Path, nargs='+')
    args = parser.parse_args()
    report = {}
    for path in args.compose:
        spec = contract.validate_compose(render_synthetic(load_yaml(path)))
        report[path.name] = {'static_synthetic_only': True, 'source': spec.source, 'gid': spec.gid}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
