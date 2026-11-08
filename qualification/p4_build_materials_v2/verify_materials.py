"""Reproduce static material checks from this package only; no native execution or network."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, inventory, load, need, write_new
from gate import decision
from native import scan
from report_materials import graph
from wheels import verify_upstream, verify_wheel


def verify(root):
    observed = inventory(root / 'materials' / 'DEPENDENCIES_OBSERVED.json')
    directory = root / 'materials' / 'wheels'
    need({p.name for p in directory.iterdir()} == {r['file'] for r in observed['distributions']}
         and all(p.is_file() and not p.is_symlink() for p in directory.iterdir()), 'Exact43 regular wheels')
    checks = [verify_wheel(row, (directory / row['file']).read_bytes()) for row in observed['distributions']]
    need(checks == load(root / 'P4_WHEEL_CHECKS.json')['wheels'], 'Wheel report differs from actual bytes')
    need(load(root / 'P4_WHEEL_CHECKS.json') == load(root / 'P4_STAGED_WHEEL_RECHECK.json'),
         'Archive/staged input checks disagree')
    reasons = graph(observed['distributions'])
    need(scan(directory, observed) == load(root / 'P4_NATIVE_CLOSURE.json'), 'Native report differs')
    upstream = {}
    for distribution, folder, endpoint in (
        ('PyYAML', 'pyyaml-upstream', 'https://pypi.org/pypi/PyYAML/6.0.3/json'),
        ('pip', 'pip-upstream', 'https://pypi.org/pypi/pip/25.2/json'),
    ):
        row = next(r for r in observed['distributions'] if r['distribution'].lower() == distribution.lower())
        upstream[distribution] = verify_upstream(
            row, root / folder / 'stdout', root / folder / 'receipt.json', endpoint)
    need(upstream == load(root / 'P4_UPSTREAM_COMPARISONS.json'), 'Upstream comparison differs')
    receipts = {}
    for path in sorted(root.glob('*/receipt.json')):
        value = load(path)
        need(value['complete'] is True and type(value['returncode']) is int
             and value['start_ns'] <= value['end_ns'], 'Incomplete/non-numeric command capture')
        for name, expected in value['sha256'].items():
            need(name in {'stdout', 'stderr', 'headers'} and digest(path.parent / name) == expected,
                 'Capture bytes changed')
        receipts[path.parent.name] = value['returncode']
    components = load(root / 'P4_IMAGE_COMPONENTS.json')
    need(components['bootstrap']['probe_sha256'] == digest(root / 'P4_BOOTSTRAP_PROBE.json'),
         'Bootstrap probe binding changed')
    final = decision(root)
    need(final == load(root / 'P4_PREPARATION_DECISION.json'), 'Readiness decision changed')
    return {'status': 'PASS_STATIC_REPRODUCTION_ONLY', 'decision': final,
            'wheel_count': len(checks), 'selection_explanations': len(reasons),
            'captured_returncodes_not_build_results': receipts,
            'network_requests': 0, 'packages_installed': 0,
            'docker_operations': 0, 'target_abi_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, verify(args.root))


if __name__ == '__main__':
    main()
