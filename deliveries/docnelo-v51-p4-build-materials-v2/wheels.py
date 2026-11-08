"""Verify and optionally copy the exact 43 observed wheels; never installs or resolves."""
import argparse
import base64
import csv
import email
import io
from pathlib import Path
import re
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, inventory, need, no_links, safe_name, sha, write_new

ARCHIVE_SHA256 = '55907b272e57a21e4815db2e7e65f4c211601eb911b6c864260002b192365026'


def checked_zip(data, directories=False):
    archive = zipfile.ZipFile(io.BytesIO(data))
    seen = set()
    for item in archive.infolist():
        name = item.filename[:-1] if directories and item.is_dir() else item.filename
        safe_name(name)
        mode = stat.S_IFMT(item.external_attr >> 16)
        need(item.filename == item.orig_filename and item.filename not in seen
             and not item.flag_bits & 1
             and mode in ((0, stat.S_IFDIR) if item.is_dir() else (0, stat.S_IFREG))
             and (not item.is_dir() or directories), 'Unsafe ZIP member')
        seen.add(item.filename)
    return archive


def verify_wheel(record, data):
    from packaging.specifiers import SpecifierSet
    from packaging.tags import compatible_tags, cpython_tags, parse_tag
    from packaging.utils import canonicalize_name, parse_wheel_filename

    need(sha(data) == record['sha256'] and len(data) == record['bytes'], 'Wheel bytes mismatch')
    name, version, _, tags = parse_wheel_filename(record['file'])
    with checked_zip(data, directories=True) as archive:
        names = {item.filename for item in archive.infolist() if not item.is_dir()}
        metas = [n for n in names if n.endswith('.dist-info/METADATA')]
        wheels = [n for n in names if n.endswith('.dist-info/WHEEL')]
        records = [n for n in names if n.endswith('.dist-info/RECORD')]
        need(len(metas) == len(wheels) == len(records) == 1, 'Ambiguous wheel metadata')
        meta = email.message_from_bytes(archive.read(metas[0]))
        wheel = email.message_from_bytes(archive.read(wheels[0]))
        need(canonicalize_name(meta['Name']) == name and str(version) == meta['Version']
             and canonicalize_name(record['distribution']) == name
             and meta['Version'] == record['version'], 'Filename/metadata name or version mismatch')
        need(meta.get_all('Requires-Dist', []) == record['requires_dist']
             and meta['Requires-Python'] == record['requires_python'],
             'Frozen inventory dependency metadata mismatch')
        declared_tags = set()
        for value in wheel.get_all('Tag', []):
            declared_tags.update(parse_tag(value))
        need(declared_tags == tags, 'Internal WHEEL/filename tags differ')
        need(not meta['Requires-Python'] or '3.11.18' in SpecifierSet(meta['Requires-Python']),
             'Requires-Python excludes the target')
        platforms = [f'manylinux_2_{n}_x86_64' for n in range(41, 4, -1)]
        platforms += ['manylinux2014_x86_64', 'manylinux2010_x86_64', 'manylinux1_x86_64']
        supported = set(cpython_tags((3, 11), abis=['cp311'], platforms=platforms))
        supported.update(compatible_tags((3, 11), interpreter='cp311', platforms=platforms))
        need(tags & supported, 'Wheel tags exclude CP311/glibc2.41/x86_64')
        checked = set()
        for filename, hash_field, size in csv.reader(io.StringIO(archive.read(records[0]).decode('utf-8'))):
            safe_name(filename)
            need(filename not in checked and filename in names, 'Duplicate/missing RECORD member')
            content = archive.read(filename)
            if hash_field:
                algorithm, value = hash_field.split('=', 1)
                expected = base64.urlsafe_b64encode(bytes.fromhex(sha(content))).decode().rstrip('=')
                need(algorithm == 'sha256' and value == expected, 'Internal RECORD hash mismatch')
                need(size.isdigit() and int(size) == len(content), 'Internal RECORD size mismatch')
            else:
                need(filename == records[0] and size == '', 'Unhashed wheel file refused')
            checked.add(filename)
        need(checked == names, 'Unlisted wheel files')
        return {'distribution': record['distribution'], 'version': record['version'],
                'file': record['file'], 'sha256': sha(data), 'bytes': len(data),
                'record_files_checked': len(checked), 'record_integrity': 'PASS',
                'tags': sorted(map(str, tags)), 'requires_python': meta['Requires-Python'],
                'target_tag_compatibility': 'PASS_STATIC_ONLY',
                'target_abi_and_imports': 'NOT_EXECUTED', 'independent_approval': False}


def payloads(observed, archive_path, yaml_path):
    need(digest(no_links(archive_path)) == ARCHIVE_SHA256, 'Historical archive anchor mismatch')
    result = {}
    with checked_zip(Path(archive_path).read_bytes()) as archive:
        expected = {r['file'] for r in observed['distributions']
                    if r['distribution'].lower() != 'pyyaml'}
        need(set(archive.namelist()) == expected | {'SHA256SUMS'}, 'Historical archive selection differs')
        for name in expected:
            result[name] = archive.read(name)
    yaml_record = next(r for r in observed['distributions'] if r['distribution'].lower() == 'pyyaml')
    need(Path(yaml_path).name == yaml_record['file'], 'Exact PyYAML filename required')
    result[yaml_record['file']] = no_links(yaml_path).read_bytes()
    return result


def verify_upstream(record, metadata_path, receipt_path, endpoint):
    from common import load
    receipt = load(receipt_path)
    need(receipt.get('complete') is True and type(receipt.get('returncode')) is int
         and receipt['returncode'] == 0
         and receipt['argv'][-1] == endpoint
         and receipt['sha256']['stdout'] == digest(metadata_path), 'Unverifiable metadata capture')
    value = load(metadata_path)
    need(value['info']['name'].lower() == record['distribution'].lower()
         and value['info']['version'] == record['version'], 'Wrong PyPI release metadata')
    matches = [item for item in value['urls'] if item['filename'] == record['file']]
    need(len(matches) == 1, 'Artifact not uniquely published by this release')
    item = matches[0]
    need(item['packagetype'] == 'bdist_wheel' and not item['yanked']
         and item['digests']['sha256'] == record['sha256']
         and item['size'] == record['bytes']
         and item['url'].startswith('https://files.pythonhosted.org/packages/'), 'PyPI artifact mismatch')
    return {'status': 'MATCHED_PYPI_HTTPS_METADATA_NOT_SIGNED_APPROVAL',
            'endpoint': endpoint, 'metadata_sha256': digest(metadata_path),
            'receipt_sha256': digest(receipt_path), 'artifact_url': item['url'],
            'filename': item['filename'], 'sha256': item['digests']['sha256'],
            'bytes': item['size'], 'published_at': item['upload_time_iso_8601'],
            'original_download_receipt_available': False,
            'artifact_signature_verified': False, 'independent_approval': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--pyyaml', type=Path)
    parser.add_argument('--wheel-dir', type=Path)
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    observed = inventory(args.inventory)
    if args.wheel_dir:
        need(not args.archive and not args.pyyaml and not args.stage, 'Do not mix input/staging modes')
        directory = no_links(args.wheel_dir)
        need({p.name for p in directory.iterdir()} == {r['file'] for r in observed['distributions']}
             and all(p.is_file() and not p.is_symlink() for p in directory.iterdir()), 'Exact43 wheel files required')
        data = {r['file']: no_links(directory / r['file']).read_bytes() for r in observed['distributions']}
    else:
        need(args.archive and args.pyyaml, 'Explicit historical archive and PyYAML required')
        data = payloads(observed, args.archive, args.pyyaml)
    result = [verify_wheel(record, data[record['file']]) for record in observed['distributions']]
    if args.stage:
        stage = no_links(args.stage)
        need(args.stage.is_absolute() and not stage.exists() and stage.parent.is_dir(), 'New stage required')
        stage.mkdir(mode=0o700)
        (stage / 'wheels').mkdir(mode=0o700)
        for name, content in data.items():
            with (stage / 'wheels' / name).open('xb') as stream:
                stream.write(content)
        with (stage / 'DEPENDENCIES_OBSERVED.json').open('xb') as stream:
            stream.write(args.inventory.read_bytes())
        with (stage / 'requirements.p4.proposed.lock').open('x', encoding='ascii', newline='\n') as stream:
            stream.write('# REVIEW ONLY. Exact observed wheels, no installation/build approval.\n')
            for record in observed['distributions']:
                extra = '[binary]' if record['distribution'].lower() == 'psycopg' else ''
                stream.write(f"{record['distribution']}{extra}=={record['version']} --hash=sha256:{record['sha256']}\n")
    write_new(args.out, {'status': 'STATIC_WHEEL_INTEGRITY_PASS_NOT_APPROVED',
                         'inventory_sha256': digest(args.inventory), 'wheels': result,
                         'target_binary_compatibility_approved': False, 'build_go': False})


if __name__ == '__main__':
    main()
