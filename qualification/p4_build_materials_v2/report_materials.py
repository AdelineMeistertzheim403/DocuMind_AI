"""Reproduce the v2 component inventory and wheel review matrix from local evidence."""
import argparse
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import INVENTORY_SHA256, digest, inventory, load, need, no_links, sha, write_new

ROOTS = {
    'pytest': 'lanceur r3', 'httpx': 'requetes ASGITransport',
    'sqlalchemy': 'garde du lanceur, modeles et harness', 'psycopg': 'garde du lanceur/harness, extra binary',
    'openai': 'garde du lanceur et imports SDK', 'alembic': 'harness, commandes migration interdites',
    'fastapi': 'application ASGI et routeurs reels', 'pydantic-settings': 'Settings',
    'argon2-cffi': 'backend.auth', 'psutil': 'backend.services.worker importe',
    'pgvector': 'modeles RAG SQLAlchemy', 'python-multipart': 'declarations des routes FastAPI',
    'pyyaml': 'controle statique seulement, pas le profil monte',
    'pip': 'bootstrap zip seulement, conserve dans la selection des 43',
}


def graph(records):
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    env = default_environment()
    env.update(implementation_name='cpython', implementation_version='3.11.18', os_name='posix',
               platform_machine='x86_64', platform_release='', platform_system='Linux',
               platform_version='', python_full_version='3.11.18',
               platform_python_implementation='CPython', python_version='3.11', sys_platform='linux')
    selected = {canonicalize_name(record['distribution']): record for record in records}
    parents = {name: [] for name in selected}
    for name, record in selected.items():
        for value in record['requires_dist']:
            req = Requirement(value)
            extras = ('', 'binary') if name == 'psycopg' else ('',)
            if req.marker and not any(req.marker.evaluate({**env, 'extra': extra}) for extra in extras):
                continue
            other = canonicalize_name(req.name)
            need(not req.url and not req.extras and other in selected
                 and selected[other]['version'] in req.specifier, 'Unclosed or unreviewed requirement')
            parents[other].append(name)
    reached = set(ROOTS)
    while True:
        more = {name for name, callers in parents.items() if any(parent in reached for parent in callers)}
        if more <= reached:
            break
        reached.update(more)
    need(reached == set(selected), 'Selection includes an unexplained distribution or misses a root')
    return {name: ROOTS.get(name) or 'transitif de ' + ', '.join(sorted(set(parents[name])))
            for name in selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path)
    args = parser.parse_args()
    root = args.root
    output = no_links(args.out_dir or root)
    need(output.is_dir() and (not (root / 'SHA256SUMS').exists()
         or not output.is_relative_to(root.absolute())), 'Existing output directory outside sealed input')
    observed = inventory(root / 'materials' / 'DEPENDENCIES_OBSERVED.json')
    wheel_check, native = load(root / 'P4_WHEEL_CHECKS.json'), load(root / 'P4_NATIVE_CLOSURE.json')
    upstream, bootstrap = load(root / 'P4_UPSTREAM_COMPARISONS.json'), load(root / 'P4_BOOTSTRAP_PROBE.json')
    catalog = load(root / 'LOCAL_IMAGE_ARCHIVES.json')
    reasons = graph(observed['distributions'])
    need(len(wheel_check['wheels']) == 43 and len(native['objects']) == 32, 'Wrong wheel/ELF scope')
    need(all(row['record_integrity'] == 'PASS' for row in wheel_check['wheels']), 'Wheel integrity failure')
    missing = lambda name, target: {'component': name, 'target': target, 'version_observed': None,
                                    'sha256': None, 'provenance': None, 'approved': False,
                                    'status': 'NOT_SUPPLIED_OR_VERIFIED_FOR_P4'}
    components = {
        'decision': 'BLOCKED', 'review_only': True, 'build_go': False,
        'create_go': False, 'start_go': False, 'production_go': False,
        'candidate_recipe_issued': False, 'inventory_sha256': INVENTORY_SHA256,
        'base': {'image_id': None, 'archive_sha256': None, 'provenance': None, 'approved': False,
                 'status': 'NO_COMPATIBLE_BASE_IDENTIFIED_IN_AVAILABLE_EVIDENCE'},
        'local_daemon_query': load(root / 'local-image-list' / 'receipt.json'),
        'archive_catalog_sha256': digest(root / 'LOCAL_IMAGE_ARCHIVES.json'),
        'archive_count': len(catalog['archives']),
        'components_missing': [
            missing('Debian base', 'Debian13/linux-amd64'),
            missing('CPython interpreter, libpython, stdlib and build configuration', 'CPython3.11.18'),
            missing('ELF PT_INTERP and glibc providers', 'actual loader and Debian13 glibc'),
            missing('recursive base libraries, symlinks, ld cache and version definitions', 'ELF64/x86_64'),
            missing('offline builder driver, frontend and local base resolution proof', 'Debian Docker toolchain'),
            missing('target bootstrap and native imports evidence', 'Debian13/CPython3.11.18'),
            missing('independently reviewed offline assembly recipe and authorizations', 'P4 only'),
        ],
        'wheels': {'count': 43, 'inventory_sha256': INVENTORY_SHA256,
                   'checks_sha256': digest(root / 'P4_WHEEL_CHECKS.json'),
                   'content_integrity': 'PASS', 'static_tags': 'PASS', 'target_abi': 'NOT_EXECUTED',
                   'approval': 'NOT_APPROVED'},
        'pyyaml': upstream['PyYAML'], 'pip': upstream['pip'],
        'bootstrap': {'probe_sha256': digest(root / 'P4_BOOTSTRAP_PROBE.json'),
                      'preparation_version_probe': bootstrap['status'],
                      'target_qualified': bootstrap['target_cp311_bootstrap_qualified']},
        'native': {'report_sha256': digest(root / 'P4_NATIVE_CLOSURE.json'),
                   'elf_files': 32, 'direct_edges': len(native['direct_edges']),
                   'unresolved': native['unresolved_library_names'], 'approved': False},
    }
    write_new(output / 'P4_IMAGE_COMPONENTS.json', components)
    with (output / 'P4_WHEEL_APPROVAL_MATRIX.md').open('x', encoding='ascii', newline='\n') as stream:
        stream.write('# Matrice de revue des 43 wheels P4\n\n'
                     '**43 contenus/RECORD/tags conformes statiquement ; 0 approbation P4.**\n\n'
                     'ABI/imports reels CPython3.11.18 : NON EXECUTES pour toutes les lignes.\n'
                     'Les tags supposent la cible glibc2.41 de v1, pas une base observee.\n'
                     'Les hashes exacts sont aussi dans materials/DEPENDENCIES_OBSERVED.json.\n\n'
                     '| Distribution | Version | Inclusion | Provenance observee | SHA256 wheel | Decision |\n'
                     '|---|---|---|---|---|---|\n')
        for record in observed['distributions']:
            name = re.sub(r'[-_.]+', '-', record['distribution']).lower()
            origin = 'PyPI HTTPS + fichier local' if name == 'pyyaml' else (
                'PyPI HTTPS + archive historique' if name == 'pip' else 'archive historique hashee')
            stream.write(f"| {record['distribution']} | {record['version']} | {reasons[name]} | "
                         f"{origin} | `{record['sha256']}` | NON APPROUVE |\n")
        stream.write('\nLe profil applicatif standard n\'active pas fastapi[standard]. '
                     'Seul psycopg[binary] est active. Aucun extra reseau/CLI/IA ne l\'est.\n')
    pip_wheel = next(record for record in observed['distributions'] if record['distribution'].lower() == 'pip')
    with zipfile.ZipFile(root / 'materials' / 'wheels' / pip_wheel['file']) as archive:
        vendors = archive.read('pip/_vendor/vendor.txt').decode('ascii')
    write_new(output / 'P4_PIP_BOOTSTRAP.json', {
        'version': '25.2', 'wheel_sha256': pip_wheel['sha256'], 'upstream': upstream['pip'],
        'vendor_txt': vendors, 'vendor_txt_sha256': sha(vendors.encode()),
        'vendored_components_covered_by_wheel_hash_not_individually_approved': True,
        'external_requires_dist': pip_wheel['requires_dist'], 'probe': bootstrap,
        'target_bootstrap_qualified': False, 'build_go': False,
        'limitations': ['Windows/CPython3.13 version probe only',
                        'No target venv installation, pip check or CPython3.11.18 execution',
                        'No independent approval or signature verification']})


if __name__ == '__main__':
    main()
