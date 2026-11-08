"""Produce a material readiness decision, never permission to build/create/start."""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, load, need, write_new


def decision(root):
    components = load(root / 'P4_IMAGE_COMPONENTS.json')
    native = load(root / 'P4_NATIVE_CLOSURE.json')
    wheels = load(root / 'P4_WHEEL_CHECKS.json')
    bootstrap = load(root / 'P4_PIP_BOOTSTRAP.json')
    blockers = []
    base = components['base']
    if not (base.get('approved') is True and re.fullmatch(r'sha256:[a-f0-9]{64}', str(base.get('image_id')))
            and re.fullmatch('[a-f0-9]{64}', str(base.get('archive_sha256'))) and base.get('provenance')):
        blockers.append('B1: verified Debian13/CPython3.11.18 base bytes, provenance and image ID absent')
    if components['components_missing']:
        blockers.append('B2: base interpreter/stdlib/native providers/recipe evidence incomplete')
    need(components['native']['report_sha256'] == digest(root / 'P4_NATIVE_CLOSURE.json')
         and components['wheels']['checks_sha256'] == digest(root / 'P4_WHEEL_CHECKS.json'),
         'Component report binding mismatch')
    if not native['binary_closure_approved'] or any(
        edge['status'] != 'WHEEL_LOCAL_DIRECT_EDGE_MATCH' for edge in native['direct_edges']
    ):
        blockers.append('B3: recursive native closure and ABI not verified/approved')
    if len(wheels['wheels']) != 43 or not wheels['target_binary_compatibility_approved'] or any(
        row['independent_approval'] is not True or row['target_abi_and_imports'] != 'PASS'
        for row in wheels['wheels']
    ):
        blockers.append('B4: 43 wheel target compatibility/provenance approvals incomplete')
    if bootstrap['target_bootstrap_qualified'] is not True:
        blockers.append('B5: pip25.2 CPython3.11.18 offline installation/pip check not qualified')
    if components['candidate_recipe_issued'] is not True:
        blockers.append('B6: no sufficiently justified Docker build recipe issued')
    return {'decision': 'BLOCKED' if blockers else 'READY_FOR_INDEPENDENT_REVIEW',
            'blockers': blockers, 'review_only': True, 'build_go': False,
            'create_go': False, 'start_go': False, 'production_go': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = decision(args.root)
    except (ValueError, KeyError, OSError) as error:
        result = {'decision': 'BLOCKED', 'blockers': [str(error)], 'review_only': True,
                  'build_go': False, 'create_go': False, 'start_go': False, 'production_go': False}
    write_new(args.out, result)
    print(result['decision'])
    sys.exit(2 if result['decision'] == 'BLOCKED' else 0)


if __name__ == '__main__':
    main()
