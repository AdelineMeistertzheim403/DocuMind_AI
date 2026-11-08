"""Compare a single scratch filesystem layer to a prepared tree; never invokes Docker."""
import argparse
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, load, need, safe_name, sha, write_new
from rootfs_check import resolve_virtual


def name_of(name):
    while name.startswith('./'):
        name = name[2:]
    name = name.rstrip('/')
    return '.' if name in ('', '.') else safe_name(name)


def layer_inventory(data):
    entries, links = {}, {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        members = archive.getmembers()
        need(len(members) <= 50000, 'Unexpected layer entry count')
        for item in members:
            name = name_of(item.name)
            need(name not in entries and not any(p.startswith('.wh.') for p in name.split('/')),
                 'Duplicate/whiteout layer entry')
            need(not item.mode & 0o6000 and not item.pax_headers, 'Unreviewed modes/PAX/xattrs')
            need(type(item.mtime) is int, 'Fractional mtime needs reviewed PAX support')
            row = {'mode': item.mode, 'uid': item.uid, 'gid': item.gid, 'mtime_ns': item.mtime * 1000000000}
            if item.isdir():
                row['type'] = 'directory'
            elif item.isfile():
                need(item.size <= 128 * 1024**2, 'Unexpected individual file size')
                value = archive.extractfile(item).read()
                row.update(type='file', sha256=sha(value), size=len(value))
            elif item.issym():
                row.update(type='symlink', target=item.linkname)
            elif item.islnk():
                row['type'] = 'hardlink'
                links[name] = name_of(item.linkname)
            else:
                raise ValueError('Special layer file refused')
            entries[name] = row
    groups = {}
    for name, row in list(entries.items()):
        if row['type'] not in ('file', 'hardlink'):
            continue
        target, seen = name, set()
        while target in links:
            need(target not in seen, 'Cyclic hardlink')
            seen.add(target)
            target = links[target]
        need(target in entries and entries[target]['type'] == 'file', 'Invalid hardlink target')
        entries[name] = dict(entries[target])
        groups.setdefault(target, []).append(name)
    need('.' in entries and entries['.']['type'] == 'directory', 'Root directory metadata absent; comparison incomplete')
    for name in entries:
        need(resolve_virtual(entries, name) in entries, 'Broken virtual path')
        parent = name.rsplit('/', 1)[0] if '/' in name else '.'
        need(parent in entries and entries[parent]['type'] == 'directory', 'Missing/aliased layer parent')
    return entries, sorted(sorted(group) for group in groups.values() if len(group) > 1)


def compare(prepared, entries, hardlinks):
    need(prepared['entries'] == entries and prepared['hardlinks'] == hardlinks,
         'Exact rootfs entries/bytes/modes/UID/GID/symlinks/hardlinks mismatch')


def verify(archive_path, expected_sha, image_id, prepared):
    need(digest(archive_path) == expected_sha, 'Docker-save archive SHA mismatch')
    with tarfile.open(archive_path, 'r:') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        need(len(names) == len(set(names)), 'Duplicate outer archive entry')

        def read(name, limit):
            safe_name(name)
            item = archive.getmember(name)
            need(item.isfile() and item.size <= limit, 'Nonregular/oversized Docker-save member')
            return archive.extractfile(item).read()

        manifests = json.loads(read('manifest.json', 1024**2))
        need(isinstance(manifests, list) and len(manifests) == 1, 'Exactly one image required')
        manifest = manifests[0]
        config_bytes = read(manifest['Config'], 2 * 1024**2)
        actual_id = 'sha256:' + sha(config_bytes)
        need(actual_id == image_id, 'Image config ID mismatch')
        config = json.loads(config_bytes)
        need(config['os'] == 'linux' and config['architecture'] == 'amd64', 'Wrong image architecture')
        need(config['rootfs']['type'] == 'layers' and len(manifest['Layers']) == 1
             and len(config['rootfs']['diff_ids']) == 1, 'Only single-layer scratch recipe supported')
        layer = read(manifest['Layers'][0], 512 * 1024**2)
        diff_id = 'sha256:' + sha(layer)
        need(config['rootfs']['diff_ids'] == [diff_id], 'Uncompressed layer diff ID mismatch')
        entries, hardlinks = layer_inventory(layer)
        compare(prepared, entries, hardlinks)
    return {'status': 'PASS_EXACT_STATIC_ROOTFS_LAYER_CONFIG_IDENTITY_ONLY',
            'archive_sha256': expected_sha, 'image_config_id': actual_id, 'layer_diff_id': diff_id,
            'entries': len(entries), 'rootfs_bytes_and_posix_metadata_equal': True,
            'signature_verified': False, 'native_abi_qualified': False,
            'config_runtime_hardening_approved': False, 'start_go': False, 'production_go': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--archive-sha256', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.archive, args.archive_sha256, args.image_id, load(args.prepared))
    result['prepared_inventory_sha256'] = digest(args.prepared)
    write_new(args.out, result)


if __name__ == '__main__':
    main()
