"""Reproduce the v3 static wheel-native review; never grants an execution authorization."""
import argparse
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, inventory, load, need, sha, write_new
from elf_audit import compare_symbols, inspect

P3_ID = 'sha256:bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd'
PRESENT = {'ld-linux-x86-64.so.2', 'libc.so.6', 'libm.so.6', 'libz.so.1'}
PACKAGES = {'ld-linux-x86-64.so.2': 'libc6:amd64', 'libc.so.6': 'libc6:amd64',
            'libm.so.6': 'libc6:amd64', 'libdl.so.2': 'libc6:amd64',
            'libpthread.so.0': 'libc6:amd64', 'libresolv.so.2': 'libc6:amd64',
            'librt.so.1': 'libc6:amd64', 'libgcc_s.so.1': 'libgcc-s1:amd64',
            'libstdc++.so.6': 'libstdc++6:amd64', 'libz.so.1': 'zlib1g:amd64'}
SITE = '/opt/p4-venv/lib/python3.11/site-packages/'


def review(root):
    observed = inventory(root / 'inputs' / 'DEPENDENCIES_OBSERVED.json')
    previous = load(root / 'inputs' / 'V2_NATIVE_CLOSURE.json')
    objects = {}
    for row in observed['distributions']:
        wheel = root / 'inputs' / 'wheels' / row['file']
        need(digest(wheel) == row['sha256'], 'Wheel identity changed')
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                if data.startswith(b'\x7fELF'):
                    path = SITE + name
                    need(path not in objects, 'Duplicate virtual ELF path')
                    objects[path] = {'path': path, 'file': name, 'wheel': row['file'],
                                     'distribution': row['distribution'], 'sha256': sha(data),
                                     **inspect(data)}
    need(len(objects) == 32 and len(previous['direct_edges']) == 120, 'Unexpected v2 scope')
    need({o['path']: o['sha256'] for o in previous['objects']}
         == {p: o['sha256'] for p, o in objects.items()}, 'ELF bytes differ from v2')
    edges, system = [], {}
    for edge in previous['direct_edges']:
        obj = objects[edge['object']]
        library = edge['needed']
        need(library in obj['needed'] and edge['required_versions'] == obj['version_requires'].get(library, []),
             'v2 edge/version disagreement')
        target = edge['resolved_wheel_path']
        if target:
            result = compare_symbols(obj, objects[target], library)
            edges.append({'object': obj['path'], 'needed': library, 'provider': target, **result,
                          'status': 'FAIL_STATIC_SYMBOL_OR_VERSION' if result['missing_strong']
                          or result['missing_versions'] else 'MATCH_STATIC_VERSIONED_SYMBOLS_ONLY'})
        else:
            group = system.setdefault(library, {'consumers': [], 'required_versions': set(),
                                                'versioned_imports': []})
            group['consumers'].append(obj['path'])
            group['required_versions'].update(obj['version_requires'].get(library, []))
            group['versioned_imports'].extend({'object': obj['path'], **s}
                                             for s in obj['undefined_symbols'] if s['library'] == library)
    requirements = []
    for library, group in sorted(system.items()):
        requirements.append({'soname_required': library, 'candidate_debian_package_not_verified': PACKAGES[library],
                             'p3_operator_report_only': 'PRESENT_NAME_ONLY' if library in PRESENT else 'ABSENT_NAME',
                             'file_sha256': None, 'file_version': None, 'package_version': None,
                             'architecture_target': 'amd64', 'provenance_verified': False,
                             'approved': False, 'status': 'PROVIDER_BYTES_NOT_SUPPLIED',
                             **{k: sorted(v) if isinstance(v, set) else v for k, v in group.items()}})
    need(len(requirements) == 10 and len(edges) == 31, 'Unexpected system/local edge split')
    native = {'decision': 'BLOCKED', 'review_only': True, 'build_go': False,
              'binary_closure_approved': False, 'objects': list(objects.values()),
              'wheel_local_versioned_symbol_review': edges, 'system_requirements': requirements,
              'counts': {'wheels': 43, 'elf_objects': 32, 'direct_needed_edges': 120,
                         'wheel_local_edges': 31, 'system_edges': 89, 'system_sonames': 10,
                         'versioned_local_symbol_references': sum(e['versioned_symbols_checked'] for e in edges),
                         'unversioned_process_scope_references_not_resolved':
                             sum(s['version'] is None for o in objects.values() for s in o['undefined_symbols'])},
              'not_proven': ['P3 corrected rootfs bytes and9771-entry manifest not supplied here',
                             'Actual base loader, CPython3.11.18, libc6 and recursive base dependencies',
                             'Global load order, inherited RPATH/cache, unversioned process scope',
                             'Relocations/TLS/IFUNC, CPU ISA, dlopen/NSS/stdlib and target execution']}
    components = {'decision': 'BLOCKED', 'review_only': True, 'build_go': False, 'create_go': False,
                  'start_go': False, 'production_go': False, 'dockerfile_issued': False,
                  'target': {'os': 'Debian13', 'architecture': 'linux/amd64', 'python': 'CPython3.11.18'},
                  'p3': {'operator_reported_image_id': P3_ID, 'independently_inspected_here': False,
                         'operator_reported_rootfs_entries': 9771, 'rootfs_manifest_sha256': None,
                         'image_archive_sha256': None, 'rootfs_supplied_here': False,
                         'base_for_p4_approved': False},
                  'system_requirements': [{k: v for k, v in row.items()
                                           if k not in ('consumers', 'versioned_imports')}
                                          for row in requirements],
                  'cpython': {'target_version': '3.11.18', 'observed_version': None,
                              'binary_sha256': None, 'source_archive_sha256': None,
                              'build_recipe_sha256': None, 'provenance_verified': False,
                              'status': 'ARTIFACT_NOT_SUPPLIED'},
                  'conditional_stdlib_provider_families_not_a_closed_list':
                      ['libssl3t64', 'libffi8', 'libbz2-1.0', 'liblzma5', 'libsqlite3-0',
                       'libexpat1', 'libreadline8t64', 'libncursesw6'],
                  'p4_image_id': None, 'p4_rootfs_manifest_sha256': None}
    decision = {'decision': 'BLOCKED', 'review_only': True, 'build_go': False,
                'create_go': False, 'start_go': False, 'production_go': False,
                'blockers': ['B1: corrected P3 rootfs bytes,9771-entry manifest and its anchor absent locally',
                             'B2: exact coherent Debian13 libc6/libgcc-s1/libstdc++6/zlib1g packages not supplied',
                             'B3: CPython3.11.18 runtime/source/build/stdlib provenance not supplied',
                             'B4: recursive system closure, loader scopes, symbols/ABI/ISA not qualified',
                             'B5: target bootstrap/imports/pip check/ASGI not executed or authorized',
                             'B6: rootfs/layer/image identity proof and offline builder qualification absent',
                             'B7: no independent component approval or executable recipe issued']}
    return native, components, decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    need(args.out_dir.is_dir() and not any(args.out_dir.iterdir()), 'Empty evidence output directory required')
    native, components, decision = review(args.root)
    for name, value in (('P4_NATIVE_CLOSURE_REVIEW.json', native),
                        ('P4_RUNTIME_COMPONENTS.json', components), ('P4_PREPARATION_DECISION.json', decision)):
        write_new(args.out_dir / name, value)
    print('BLOCKED; static observations only; no build/create/start authorization')
    sys.exit(2)


if __name__ == '__main__':
    main()
