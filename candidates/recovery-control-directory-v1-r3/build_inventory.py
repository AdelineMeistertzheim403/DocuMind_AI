"""Generate traceability artifacts only; never edits source or executes services."""
import argparse
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or path.as_posix() != name:
        raise RuntimeError('Unsafe inventory member')
    return path


def write_json(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin-root', type=Path, required=True)
    parser.add_argument('--compose-inventory', type=Path, required=True)
    args = parser.parse_args()
    origin = json.loads((ROOT / 'ORIGIN.json').read_text())
    old = origin['files_sha256']
    for name, digest in old.items():
        path = args.origin_root / safe_relative(name)
        if not re.fullmatch('[a-f0-9]{64}', digest) or sha(path) != digest:
            raise RuntimeError('Original source changed: ' + name)
    historical = json.loads(args.compose_inventory.read_text())
    for row in historical:
        if sha(args.origin_root / safe_relative(row['file'].replace('\\', '/'))) != row['sha256']:
            raise RuntimeError('Historical Compose changed: ' + row['file'])
    changes, unchanged, patch = [], [], []
    for path in sorted((ROOT / 'source').rglob('*')):
        if not path.is_file():
            continue
        if any(parent.is_symlink() for parent in (path, *path.parents)) or '__pycache__' in path.parts:
            raise RuntimeError('Unexpected source symlink/cache')
        name = path.relative_to(ROOT / 'source').as_posix()
        digest = sha(path)
        if digest == old.get(name):
            unchanged.append(name)
            continue
        before = args.origin_root / safe_relative(name)
        changes.append({'file': 'source/' + name, 'status': 'modified' if name in old else 'added',
                        'origin_sha256': old.get(name), 'candidate_sha256': digest})
        previous = before.read_bytes().decode('utf-8-sig').splitlines(keepends=True) if name in old else []
        current = path.read_bytes().decode('utf-8-sig').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(previous, current,
                     fromfile='a/' + name if name in old else '/dev/null', tofile='b/' + name))
    campaign = [
        path.relative_to(ROOT).as_posix() for path in sorted(ROOT.rglob('*')) if path.is_file()
        and not path.is_relative_to(ROOT / 'source')
        and path.name not in {'INPUTS.json', 'SHA256SUMS', 'CHANGES.json', 'DEPENDENCIES.json',
                              'ORIGINALS_VERIFIED.json', 'candidate.patch'}
    ]
    write_json('CHANGES.json', {'scope': 'isolated source snapshot; never apply to a sealed release',
                               'source_changes': changes, 'source_unchanged': unchanged,
                               'campaign_assets': campaign})
    (ROOT / 'candidate.patch').write_bytes(''.join(patch).encode('utf-8'))
    write_json('ORIGINALS_VERIFIED.json', {
        'original_source_files_verified': len(old),
        'historical_compose_documents_verified': len(historical),
        'historical_compose_inventory_sha256': sha(args.compose_inventory),
        'result': 'byte-identical to preparation baselines; no original edits',
    })
    locks = {
        path.relative_to(ROOT).as_posix(): sha(path)
        for path in sorted((ROOT / 'source').rglob('*')) if path.is_file()
        and (path.name.startswith('requirements') or path.name in {'pyproject.toml', 'package.json', 'package-lock.json'})
    }
    installed = {}
    for dist in importlib.metadata.distributions():
        record = dist.read_text('RECORD') or ''
        installed[dist.metadata['Name']] = {'version': dist.version,
                                          'RECORD_sha256': hashlib.sha256(record.encode()).hexdigest()}
    write_json('DEPENDENCIES.json', {
        'platform': sys.platform, 'python': sys.version, 'installed_python_metadata': installed,
        'source_dependency_files_sha256': locks,
        'debian_cp311_wheel_closure_supplied': False, 'docker_images_supplied': False,
        'note': 'Metadata/lock hashes, not signatures or a hash of every installed binary',
    })
    manifest = {}
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name not in {'INPUTS.json', 'SHA256SUMS'}:
            if '__pycache__' in path.parts or path.suffix == '.pyc' or path.is_symlink():
                raise RuntimeError('Unexpected generated input')
            manifest[path.relative_to(ROOT).as_posix()] = sha(path)
    write_json('INPUTS.json', manifest)
    sums = dict(manifest)
    sums['INPUTS.json'] = sha(ROOT / 'INPUTS.json')
    (ROOT / 'SHA256SUMS').write_text(''.join(
        digest + '  ' + name + '\n' for name, digest in sorted(sums.items())), encoding='utf-8')
    print(json.dumps({'source_modified_or_added': len(changes), 'source_unchanged': len(unchanged),
                      'candidate_inputs': len(manifest), 'historical_originals_verified': len(historical),
                      'SHA256SUMS_sha256': sha(ROOT / 'SHA256SUMS')}, indent=2))


if __name__ == '__main__':
    main()
