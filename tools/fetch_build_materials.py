"""Fetch reviewed pgvector build inputs. No registry, credentials or private cache.

Hashes authenticate bytes against the reviewed manifest; apk separately verifies
package signatures with its official base-image keys. This is not a CVE scan or
an independent attestation of upstream publishers.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_manifest_key')
        result[key] = value
    return result


def validate_entry(row, expected_url):
    if set(row) != {'filename', 'url', 'sha256', 'size'}:
        raise ValueError('unexpected_material_fields')
    if row['url'] != expected_url:
        raise ValueError('unapproved_origin')
    parsed = urlsplit(row['url'])
    if (parsed.scheme != 'https' or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError('unsafe_material_url')
    if not isinstance(row['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
        raise ValueError('invalid_material_hash')
    if type(row['size']) is not int or not 0 < row['size'] <= 128 * 1024 * 1024:
        raise ValueError('invalid_material_size')


def manifest_materials(manifest):
    if (set(manifest) != {'format', 'target', 'source', 'apk'} or
            manifest['format'] != 'documind-pgvector-build-v1' or
            manifest['target'] != 'postgres17-alpine3.24-linux-amd64'):
        raise ValueError('unsupported_build_manifest')
    source = manifest['source']
    if set(source) != {'version', 'commit', 'url', 'sha256', 'size'}:
        raise ValueError('unexpected_source_fields')
    if not re.fullmatch(r'\d+\.\d+\.\d+', source['version']) or not re.fullmatch('[a-f0-9]{40}', source['commit']):
        raise ValueError('invalid_source_identity')
    row = {'filename': 'pgvector.tar.gz', **{k: source[k] for k in ('url', 'sha256', 'size')}}
    validate_entry(row, 'https://codeload.github.com/pgvector/pgvector/tar.gz/' + source['commit'])
    result = [('pgvector.tar.gz', row)]
    packages = manifest['apk']
    if not isinstance(packages, list) or not 1 <= len(packages) <= 64:
        raise ValueError('invalid_package_count')
    seen = set()
    for package in packages:
        name = package.get('filename', '')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9+_.-]+\.apk', name) or name.startswith('.'):
            raise ValueError('invalid_package_filename')
        if name in seen:
            raise ValueError('duplicate_package')
        seen.add(name)
        validate_entry(package, 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/' + name)
        result.append(('apk/' + name, package))
    if sum(item['size'] for _, item in result) > 256 * 1024 * 1024:
        raise ValueError('materials_total_too_large')
    return result


def verify_source(path, source):
    prefix = 'pgvector-' + source['commit']
    with tarfile.open(path, mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) > 1024 or sum(m.size for m in members) > 16 * 1024 * 1024:
            raise ValueError('source_archive_too_large')
        names = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or '\\' in member.name or
                    not name.parts or name.parts[0] != prefix or
                    not (member.isfile() or member.isdir()) or member.name in names):
                raise ValueError('unsafe_source_archive')
            names.add(member.name)
        control = next((m for m in members if m.name == prefix + '/vector.control'), None)
        if control is None or control.size > 4096:
            raise ValueError('missing_source_version')
        content = archive.extractfile(control).read().decode('utf-8')
        if not re.search(r"^default_version\s*=\s*'" + re.escape(source['version']) + r"'\s*$", content, re.M):
            raise ValueError('source_version_mismatch')


def download(row, destination, opener):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as stream:
            temporary = Path(stream.name)
            digest, size = hashlib.sha256(), 0
            with opener.open(Request(row['url'], headers={'User-Agent': 'DocuMind-build-materials-v1'}), timeout=30) as response:
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > row['size']:
                        raise ValueError('material_size_mismatch')
                    digest.update(chunk)
                    stream.write(chunk)
        if size != row['size'] or digest.hexdigest() != row['sha256']:
            raise ValueError('material_integrity_mismatch')
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def acquire(manifest_path, output):
    raw = manifest_path.read_bytes()
    if len(raw) > 128 * 1024:
        raise ValueError('manifest_too_large')
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    entries = manifest_materials(manifest)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'apk').mkdir()
    opener = build_opener(NoRedirect)
    for filename, row in entries:
        download(row, output / filename, opener)
    verify_source(output / 'pgvector.tar.gz', manifest['source'])
    receipt = {'manifest_sha256': hashlib.sha256(raw).hexdigest(),
               'source_version': manifest['source']['version'], 'source_commit': manifest['source']['commit'],
               'files': {name: row['sha256'] for name, row in entries}}
    (output / 'receipts.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return len(entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        count = acquire(args.manifest, args.output)
    except Exception:
        # Do not log proxy configuration, HTTP headers, host paths or remote bodies.
        print(json.dumps({'error': 'build_materials_acquisition_failed'}))
        return 1
    print(json.dumps({'materials_verified': count}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
