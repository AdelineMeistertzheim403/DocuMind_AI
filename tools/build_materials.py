"""Offline dependency/materials inventory, not an origin attestation or CVE scan.

No install, resolution, network, environment dump, direct URLs or host paths.
The project's own PEP 517 build and system packages are separate evidence gaps.
"""
import argparse
import base64
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
import tomllib
from urllib.parse import urlsplit
import zipfile
from email.parser import BytesParser

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def constraint_pins(path):
    pins = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement = Requirement(line)
        if requirement.url or requirement.extras:
            raise ValueError('unsupported_constraint')
        if requirement.marker and not requirement.marker.evaluate():
            continue
        specs = list(requirement.specifier)
        if len(specs) != 1 or specs[0].operator != '==' or '*' in specs[0].version:
            raise ValueError('constraint_not_exact')
        name = canonicalize_name(requirement.name)
        version = specs[0].version
        if name in pins and pins[name] != version:
            raise ValueError('conflicting_constraints')
        pins[name] = version
    return pins


def python_materials(project, pins, distribution=metadata.distribution):
    roots = project['project']['dependencies'] + project['project'].get('optional-dependencies', {}).get('test', [])
    queue = [Requirement(value) for value in roots]
    visited, rows, issues = set(), {}, set()
    while queue:
        requirement = queue.pop()
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        name = canonicalize_name(requirement.name)
        key = name, tuple(sorted(requirement.extras))
        if requirement.url:
            issues.add('direct_url_requirement')
            continue
        try:
            installed = distribution(name)
        except metadata.PackageNotFoundError:
            rows[name] = {'version': None, 'pin': pins.get(name), 'constraint_matches': False}
            issues.add('missing_distribution')
            continue
        matches = pins.get(name) == installed.version
        rows[name] = {'version': installed.version, 'pin': pins.get(name), 'constraint_matches': matches}
        if not matches:
            issues.add('unconstrained_or_mismatched_distribution')
        if not requirement.specifier.contains(installed.version):
            issues.add('incompatible_dependency')
        if key in visited:
            continue
        visited.add(key)
        for raw in installed.requires or []:
            child = Requirement(raw)
            if child.marker is None or any(child.marker.evaluate({'extra': extra})
                                          for extra in {''} | set(requirement.extras)):
                # Already evaluated against the parent's extras; do not evaluate
                # that marker a second time as if it belonged to the child.
                child.marker = None
                queue.append(child)
    tools = {}
    for name in ('pip', 'setuptools', 'wheel'):
        try:
            tools[name] = distribution(name).version
        except metadata.PackageNotFoundError:
            tools[name] = None
    return {'packages': dict(sorted(rows.items())), 'issues': sorted(issues), 'build_tools_installed': tools,
            'pep517_requires': project['build-system']['requires'],
            'pep517_environment_verified': False, 'constraint_coverage_complete': not issues}


def artifact_materials(directory):
    """Hash actual wheel bytes. Never mistake installed RECORD hashes for wheels."""
    rows = []
    for path in sorted(directory.iterdir()):
        if path.suffix != '.whl':
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('unsafe_artifact')
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            wheels = [name for name in archive.namelist() if name.endswith('.dist-info/WHEEL')]
            if len(names) != 1 or len(wheels) != 1:
                raise ValueError('ambiguous_wheel')
            if any(archive.getinfo(name).file_size > 2 * 1024 * 1024 for name in names + wheels):
                raise ValueError('oversized_wheel_metadata')
            meta = BytesParser().parsebytes(archive.read(names[0]))
            wheel = BytesParser().parsebytes(archive.read(wheels[0]))
            name = canonicalize_name(meta['Name'])
            # Requirement parsing validates name/version without emitting raw metadata.
            Requirement(f'{name}=={meta["Version"]}')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        rows.append({'name': name, 'version': meta['Version'], 'tags': wheel.get_all('Tag', []),
                     'sha256': digest, 'size_bytes': path.stat().st_size,
                     'origin_verified': False})
    return rows


def npm_materials(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('lockfileVersion') != 3:
        raise ValueError('unsupported_npm_lock')
    packages, scripts = 0, 0
    for key, row in data['packages'].items():
        if not key:
            continue
        source = urlsplit(row.get('resolved', ''))
        if (source.scheme != 'https' or source.hostname != 'registry.npmjs.org' or
                source.username or source.password or source.query or source.fragment or
                not row.get('integrity', '').startswith('sha512-')):
            raise ValueError('unverified_npm_material')
        if len(base64.b64decode(row['integrity'][7:], validate=True)) != 64:
            raise ValueError('invalid_npm_integrity')
        packages += 1
        scripts += int(bool(row.get('hasInstallScript')))
    return {'lock_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'packages': packages,
            'install_script_packages': scripts, 'downloaded_bytes_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path('pyproject.toml'))
    parser.add_argument('--constraints', type=Path, default=Path('requirements.lock'))
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--npm-lock', type=Path)
    parser.add_argument('--require-pins', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = {'format': 'documind-materials-v1', 'python': platform.python_version(),
                  'platform': sys.platform, 'machine': platform.machine(),
                  'constraints_sha256': hashlib.sha256(args.constraints.read_bytes()).hexdigest(),
                  'project_sha256': hashlib.sha256(args.project.read_bytes()).hexdigest()}
        report['python_dependencies'] = python_materials(
            tomllib.loads(args.project.read_text(encoding='utf-8')), constraint_pins(args.constraints))
        sources = ('Dockerfile', 'Dockerfile.db', 'frontend/Dockerfile', '.github/workflows/ci.yml',
                   '.github/workflows/deploy.yml', 'frontend/package-lock.json')
        report['source_sha256'] = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                   if Path(name).is_file() else None for name in sources}
        if args.artifacts:
            report['wheel_archives'] = artifact_materials(args.artifacts)
        if args.npm_lock:
            report['npm'] = npm_materials(args.npm_lock)
        code = int(args.require_pins and not report['python_dependencies']['constraint_coverage_complete'])
    except Exception:
        # Paths, metadata direct URLs and OS errors can contain private information.
        report, code = {'format': 'documind-materials-v1', 'error': 'materials_validation_failed'}, 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
