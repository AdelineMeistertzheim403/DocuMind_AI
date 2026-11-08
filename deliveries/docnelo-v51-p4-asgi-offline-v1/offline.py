"""Read-only material checks; sealing writes only an explicitly selected new manifest."""
import argparse
import email
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def safe_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name
            and not PurePosixPath(name).is_absolute()
            and not any(part in ('', '.', '..') for part in name.split('/'))
            and not any(ord(c) < 32 or ord(c) == 127 for c in name),
            'Unsafe relative name: ' + repr(name))
    return name


def no_links(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path refused')
    return path


def files(root, exclude=()):
    root = no_links(root)
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Symlink in inventory')
        require(path.is_file() or path.is_dir(), 'Non-regular inventory object')
        if path.is_file():
            name = safe_name(path.relative_to(root).as_posix())
            if name not in exclude:
                result[name] = digest(path)
    return result


def manifest(root, anchor=None):
    root = no_links(root)
    if anchor:
        require(digest(root / 'SHA256SUMS') == anchor, 'Untrusted SHA256SUMS anchor')
    expected = {}
    for line in (root / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        require(match is not None, 'Malformed SHA256SUMS')
        value, name = match.groups()
        safe_name(name)
        require(name != 'SHA256SUMS' and name not in expected, 'Duplicate/self manifest entry')
        expected[name] = value
    require(expected and files(root, ('SHA256SUMS',)) == expected, 'Exact inventory mismatch')
    return expected


def candidate(root):
    refs = load(ROOT / 'REFERENCES.json')
    entries = manifest(root, refs['candidate_sha256sums'])
    require(digest(Path(root) / 'INPUTS.json') == refs['candidate_inputs'], 'r3 INPUTS anchor')
    require(load(Path(root) / 'INPUTS.json') ==
            {name: value for name, value in entries.items() if name != 'INPUTS.json'},
            'r3 INPUTS/SHA256SUMS disagree')
    return entries


def write_new(path, value):
    path = no_links(path)
    require(path.parent.is_dir(), 'Output parent must already exist')
    with path.open('x', encoding='ascii', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write('\n')


def checked_zip(data, allow_directories=False):
    archive = zipfile.ZipFile(io.BytesIO(data))
    seen = set()
    for item in archive.infolist():
        directory = allow_directories and item.is_dir()
        safe_name(item.filename[:-1] if directory else item.filename)
        mode = item.external_attr >> 16
        require(item.filename == item.orig_filename and item.filename not in seen
                and (not item.is_dir() or directory) and not item.flag_bits & 1
                and stat.S_IFMT(mode) in ((0, stat.S_IFDIR) if directory else (0, stat.S_IFREG)),
                'Unsafe ZIP member')
        seen.add(item.filename)
    return archive


def elf(data):
    """ELF64/x86_64 DT_NEEDED without executing ldd or the untrusted library."""
    require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    machine = struct.unpack_from('<H', data, 18)[0]
    require(machine == 62, 'Expected x86_64 ELF')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 54)
    loads, dynamic = [], []
    for index in range(phnum):
        kind, _, offset, vaddr, _, size, _, _ = struct.unpack_from(
            '<IIQQQQQQ', data, phoff + index * phsize)
        if kind == 1:
            loads.append((vaddr, vaddr + size, offset))
        if kind == 2:
            dynamic.extend(struct.iter_unpack('<qQ', data[offset:offset + size]))
    strings = next((value for tag, value in dynamic if tag == 5), None)
    needed = []
    if strings is not None:
        offsets = [offset + strings - start for start, end, offset in loads if start <= strings < end]
        require(len(offsets) == 1, 'Ambiguous ELF string table')
        for tag, value in dynamic:
            if tag == 1:
                start = offsets[0] + value
                needed.append(data[start:data.index(b'\0', start)].decode('ascii'))
    return {'class': 'ELF64', 'machine': 'x86_64', 'needed': sorted(needed)}


def wheel_record(name, data, provenance):
    with checked_zip(data, allow_directories=True) as archive:
        metadata_names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        wheel_names = [n for n in archive.namelist() if n.endswith('.dist-info/WHEEL')]
        require(len(metadata_names) == len(wheel_names) == 1, 'Ambiguous wheel metadata')
        meta = email.message_from_bytes(archive.read(metadata_names[0]))
        wheel = email.message_from_bytes(archive.read(wheel_names[0]))
        binaries = []
        for item in archive.infolist():
            content = archive.read(item)
            if content.startswith(b'\x7fELF') or item.filename.endswith(('.dll', '.pyd')):
                binaries.append({'file': item.filename, 'sha256': sha(content),
                                 'bytes': len(content), **elf(content)})
        return {'distribution': meta['Name'], 'version': meta['Version'], 'file': name,
                'sha256': sha(data), 'bytes': len(data), 'provenance': provenance,
                'requires_python': meta['Requires-Python'],
                'requires_dist': meta.get_all('Requires-Dist', []),
                'tags': wheel.get_all('Tag', []), 'binaries': binaries}


def norm(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def closure(records):
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.tags import compatible_tags, cpython_tags
    from packaging.utils import parse_wheel_filename

    platforms = ['manylinux_2_%d_x86_64' % n for n in range(41, 4, -1)]
    platforms += ['manylinux2014_x86_64', 'manylinux2010_x86_64', 'manylinux1_x86_64']
    tags = set(cpython_tags((3, 11), platforms=platforms))
    tags.update(compatible_tags((3, 11), interpreter='cp311', platforms=platforms))
    env = default_environment()
    env.update(implementation_name='cpython', implementation_version='3.11.18',
               os_name='posix', platform_machine='x86_64', platform_release='',
               platform_system='Linux', platform_version='', python_full_version='3.11.18',
               platform_python_implementation='CPython', python_version='3.11', sys_platform='linux',
               extra='')
    selected = {norm(r['distribution']): r for r in records}
    require(len(selected) == len(records), 'Duplicate distributions')
    errors = []
    for record in records:
        name, version, _, wheel_tags = parse_wheel_filename(record['file'])
        if norm(name) != norm(record['distribution']) or str(version) != record['version']:
            errors.append('Filename/metadata mismatch: ' + record['file'])
        if not wheel_tags & tags:
            errors.append('Incompatible CP311/Debian13 x86_64 wheel: ' + record['file'])
        if record['requires_python'] and '3.11.18' not in SpecifierSet(record['requires_python']):
            errors.append('Requires-Python mismatch: ' + record['file'])
        extras = ('', 'binary') if norm(record['distribution']) == 'psycopg' else ('',)
        for raw in record['requires_dist']:
            requirement = Requirement(raw)
            if requirement.marker and not any(
                requirement.marker.evaluate({**env, 'extra': extra}) for extra in extras
            ):
                continue
            other = selected.get(norm(requirement.name))
            if other is None or other['version'] not in requirement.specifier:
                errors.append(record['distribution'] + ' requires ' + raw)
            if requirement.url or requirement.extras:
                errors.append('Extra/URL needs explicit review: ' + raw)
    return errors


def inventory(candidate_path, transfer, yaml_path):
    refs = load(ROOT / 'REFERENCES.json')
    candidate(candidate_path)
    manifest(transfer, refs['historical_transfer_sha256sums'])
    lock = Path(transfer) / 'requirements.lock'
    require(digest(lock) == refs['historical_cp311_lock'], 'Historical lock mismatch')
    archive_path = Path(transfer) / 'quarantine-wheels-cp311-linux-x86_64.zip'
    require(digest(archive_path) == refs['historical_wheel_archive'], 'Historical archive mismatch')
    records = []
    with checked_zip(archive_path.read_bytes()) as archive:
        entries = {}
        for line in archive.read('SHA256SUMS').decode('ascii').splitlines():
            value, name = line.split('  ', 1)
            require(name not in entries and re.fullmatch('[a-f0-9]{64}', value), 'ZIP manifest')
            entries[safe_name(name)] = value
        require(set(entries) == set(archive.namelist()) - {'SHA256SUMS'}, 'Wheel ZIP inventory')
        for name, expected in entries.items():
            data = archive.read(name)
            require(sha(data) == expected and name.endswith('.whl'), 'Historical wheel mismatch')
            records.append(wheel_record(name, data, 'historical transfer / ' + archive_path.name))
    pins = {}
    for line in lock.read_text(encoding='ascii').splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([\w.-]+)(?:\[binary\])?==(\S+) --hash=sha256:([a-f0-9]{64})', line)
        require(match is not None, 'Historical lock format')
        name, version, value = match.groups()
        pins[norm(name)] = (version, value)
    require(pins == {norm(r['distribution']): (r['version'], r['sha256']) for r in records},
            'Historical lock is not the exact wheel selection')
    require(digest(no_links(yaml_path)) == refs['pyyaml_cp311_wheel'], 'PyYAML observation mismatch')
    records.append(wheel_record(Path(yaml_path).name, Path(yaml_path).read_bytes(),
                                refs['pyyaml_provenance']))
    records.sort(key=lambda r: norm(r['distribution']))
    return {'status': 'OBSERVED_NOT_APPROVED', 'target': 'Debian13/x86_64/CPython3.11.18/glibc2.41',
            'extras': {'psycopg': ['binary']}, 'distributions': records,
            'metadata_closure_errors': closure(records),
            'binary_closure_approved': False, 'build_go': False,
            'blockers': ['No approved Debian13/CPython3.11.18 base archive and image ID',
                         'No native system libraries/loader/CPython binary provenance inventory',
                         'PyYAML hash observed locally, independent provenance/approval absent',
                         'P4 minimal selection and pip25.2 bootstrap not independently approved',
                         'No Debian P4 image import, ABI, pip check or mounted campaign evidence']}


def material_gate(inventory_path, approval_path):
    observed, approval = load(inventory_path), load(approval_path)
    require(approval.get('review_only') is False and approval.get('build_authorized') is True,
            'STOP BEFORE BUILD: approval absent')
    require(approval.get('inventory_sha256') == digest(inventory_path), 'Approval inventory binding')
    require(not observed['metadata_closure_errors'], 'Incomplete Python metadata closure')
    required = ('base_archive', 'cpython', 'native_closure', 'wheel_provenance',
                'bootstrap', 'recipe', 'independent_review')
    for field in required:
        record = approval.get(field)
        require(isinstance(record, dict) and record.get('approved') is True
                and re.fullmatch('[a-f0-9]{64}', str(record.get('sha256', ''))),
                'STOP BEFORE BUILD: missing ' + field)
    # This proposal deliberately has no approved image assembly recipe.
    raise ValueError('STOP BEFORE BUILD: review-only package; publish a separately reviewed build revision')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    check = sub.add_parser('verify')
    check.add_argument('root', type=Path)
    check.add_argument('--anchor', required=True)
    check = sub.add_parser('candidate')
    check.add_argument('root', type=Path)
    scan = sub.add_parser('inventory')
    scan.add_argument('--candidate', type=Path, required=True)
    scan.add_argument('--historical-transfer', type=Path, required=True)
    scan.add_argument('--pyyaml-wheel', type=Path, required=True)
    scan.add_argument('--out', type=Path, required=True)
    gate = sub.add_parser('build-gate')
    gate.add_argument('--inventory', type=Path, required=True)
    gate.add_argument('--approval', type=Path, required=True)
    seal = sub.add_parser('seal')
    seal.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        manifest(args.root, args.anchor)
    elif args.action == 'candidate':
        candidate(args.root)
    elif args.action == 'inventory':
        write_new(args.out, inventory(args.candidate, args.historical_transfer, args.pyyaml_wheel))
    elif args.action == 'build-gate':
        material_gate(args.inventory, args.approval)
    elif args.action == 'seal':
        entries = files(args.root)
        require('SHA256SUMS' not in entries and entries, 'Seal only once; never overwrite a seal')
        with (args.root / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as stream:
            stream.write(''.join(f'{value}  {name}\n' for name, value in entries.items()))
    print('OFFLINE_CHECK_ONLY; no execution authorization')


if __name__ == '__main__':
    main()
