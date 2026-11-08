"""Generate r3 manifests and an r2 delta without changing frozen inputs."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
GENERATED = {'INPUTS.json', 'SHA256SUMS', 'REVISION_CHANGES.json',
             'revision.patch', 'PRESERVATION_VERIFIED.json'}
MODIFIED = {'source/tools/preflight_recovery_compose.py', 'run_local.py',
            'README.md', 'DEBIAN_OFFLINE_PROTOCOL.md'}
ADDED = {'BASELINE_R3.json', 'build_r3_inventory.py',
         'tests/test_compose_memory_normalization.py', 'REPORT_R3.md'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or '__pycache__' in path.parts or path.suffix == '.pyc':
            raise RuntimeError('Unexpected symlink/cache: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def write_json(name, data):
    (ROOT / name).write_bytes((json.dumps(data, indent=2) + '\n').encode('ascii'))


def verify_preservation():
    baseline = json.loads((ROOT / 'BASELINE_R3.json').read_bytes())
    for name, expected in baseline['frozen_candidates_sha256'].items():
        if files(ROOT.parent / name) != expected:
            raise RuntimeError('Frozen candidate changed: ' + name)
    for name, expected in baseline['protected_scopes_sha256'].items():
        if files(REPOSITORY / name) != expected:
            raise RuntimeError('Historical evidence/transfer file set changed: ' + name)
    for name, expected in baseline['protected_previous_artifacts_sha256'].items():
        if sha(REPOSITORY / name) != expected:
            raise RuntimeError('Historical artifact changed: ' + name)
    return baseline


def main():
    baseline = verify_preservation()
    previous = baseline['frozen_candidates_sha256'][baseline['baseline']]
    current = files(ROOT)
    if set(previous) - set(current):
        raise RuntimeError('Missing inherited r2 file')
    changed, unchanged, patch = [], [], []
    for name, digest in sorted(current.items()):
        if name in GENERATED:
            continue
        if digest == previous.get(name):
            unchanged.append(name)
            continue
        if name not in (MODIFIED if name in previous else ADDED):
            raise RuntimeError('Change outside r3 scope: ' + name)
        changed.append({'file': name, 'status': 'modified' if name in previous else 'added',
                        'r2_sha256': previous.get(name), 'r3_sha256': digest})
        old = ((ROOT.parent / baseline['baseline'] / name).read_bytes().decode('utf-8-sig')
               .splitlines(keepends=True)) if name in previous else []
        new = (ROOT / name).read_bytes().decode('utf-8-sig').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(old, new, fromfile='a/' + name if name in previous else '/dev/null',
                                         tofile='b/' + name))
    write_json('REVISION_CHANGES.json', {
        'baseline': baseline['baseline'], 'revision': baseline['revision'],
        'scope': 'REVIEW_ONLY_NO_P3_GO', 'changed': changed,
        'unchanged_from_r2': unchanged, 'regenerated_metadata': sorted(GENERATED),
    })
    (ROOT / 'revision.patch').write_bytes(''.join(patch).encode('utf-8'))
    write_json('PRESERVATION_VERIFIED.json', {
        'frozen_candidates_files_verified': {
            name: len(data) for name, data in baseline['frozen_candidates_sha256'].items()},
        'previous_artifacts_verified': len(baseline['protected_previous_artifacts_sha256']),
        'unaffected_r2_files_byte_identical': len(unchanged),
        'original_119_P1_and_51_r2_tests_unchanged': all(name in unchanged for name in (
            'tests/test_recovery_directory.py', 'tests/test_fastapi_directory_transitions.py',
            'tests/test_compose_source_rendered.py')),
        'docker_commands_executed': False, 'debian_namespaces_accessed': False,
        'existing_permissions_changed': False, 'p3_go': False,
    })
    manifest = {name: digest for name, digest in files(ROOT).items()
                if name not in {'INPUTS.json', 'SHA256SUMS'}}
    write_json('INPUTS.json', manifest)
    (ROOT / 'SHA256SUMS').write_bytes(''.join(
        digest + '  ' + name + '\n' for name, digest in sorted({
            **manifest, 'INPUTS.json': sha(ROOT / 'INPUTS.json')}.items())).encode('ascii'))
    print(json.dumps({'changed_or_added': len(changed), 'unchanged_r2_files': len(unchanged),
                      'candidate_inputs': len(manifest),
                      'candidate_SHA256SUMS_sha256': sha(ROOT / 'SHA256SUMS')}, indent=2))


if __name__ == '__main__':
    main()
