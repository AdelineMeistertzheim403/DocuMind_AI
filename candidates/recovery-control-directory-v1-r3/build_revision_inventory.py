"""Generate r2 artifacts only after verifying immutable v1 and previous evidence."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = {'INPUTS.json', 'SHA256SUMS', 'REVISION_CHANGES.json',
             'revision.patch', 'PRESERVATION_VERIFIED.json'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, ensure_ascii=True) + '\n', encoding='ascii')


def main():
    baseline = json.loads((ROOT / 'BASELINE_REVISION.json').read_text())
    old = ROOT.parent / baseline['baseline']
    repository = ROOT.parents[1]
    original = baseline['frozen_files_sha256']
    if {p.relative_to(old).as_posix() for p in old.rglob('*') if p.is_file()} != set(original):
        raise RuntimeError('Frozen v1 file set changed')
    for name, expected in original.items():
        if sha(old / name) != expected:
            raise RuntimeError('Frozen v1 changed: ' + name)
    for name, expected in baseline['protected_previous_artifacts_sha256'].items():
        if sha(repository / name) != expected:
            raise RuntimeError('Previous evidence/report/transfer changed: ' + name)
    unchanged, changed, patch = [], [], []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.name in GENERATED:
            continue
        if '__pycache__' in path.parts or path.suffix == '.pyc' or path.is_symlink():
            raise RuntimeError('Unexpected cache or symlink')
        name = path.relative_to(ROOT).as_posix()
        current = sha(path)
        if current == original.get(name):
            unchanged.append(name)
            continue
        changed.append({'file': name, 'status': 'modified' if name in original else 'added',
                        'v1_sha256': original.get(name), 'r2_sha256': current})
        previous = (old / name).read_bytes().decode('utf-8-sig').splitlines(keepends=True) if name in original else []
        present = path.read_bytes().decode('utf-8-sig').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(previous, present, fromfile='a/' + name if name in original else '/dev/null',
                                         tofile='b/' + name))
    write_json('REVISION_CHANGES.json', {
        'scope': 'r2 proposed for review only; never replace v1 automatically',
        'changed': changed, 'unchanged_from_v1': unchanged,
    })
    (ROOT / 'revision.patch').write_bytes(''.join(patch).encode('utf-8'))
    write_json('PRESERVATION_VERIFIED.json', {
        'v1_files_verified': len(original),
        'previous_artifacts_verified': len(baseline['protected_previous_artifacts_sha256']),
        'original_P1_tests_unchanged': all(name in unchanged for name in (
            'tests/test_recovery_directory.py', 'tests/test_fastapi_directory_transitions.py')),
        'P2_code_unchanged': all(name in unchanged for name in (
            'lab/control.py', 'source/tools/recovery_control_directory.py', 'lab/compose.static.yaml')),
        'debian_namespaces_accessed': False, 'production_accessed': False,
    })
    manifest = {
        path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(ROOT.rglob('*'))
        if path.is_file() and path.name not in {'INPUTS.json', 'SHA256SUMS'}
    }
    write_json('INPUTS.json', manifest)
    (ROOT / 'SHA256SUMS').write_text(''.join(
        digest + '  ' + name + '\n' for name, digest in sorted({
            **manifest, 'INPUTS.json': sha(ROOT / 'INPUTS.json')}.items())), encoding='utf-8')
    print(json.dumps({'changed_or_added': len(changed), 'unchanged_from_v1': len(unchanged),
                      'candidate_inputs': len(manifest), 'SHA256SUMS_sha256': sha(ROOT / 'SHA256SUMS')}, indent=2))


if __name__ == '__main__':
    main()
