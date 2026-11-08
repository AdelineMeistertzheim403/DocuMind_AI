"""Inventory a new synthetic P4 Linux tree without executing its files or following host symlinks."""
import argparse
import os
from pathlib import Path
import posixpath
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, need, no_links, safe_name, sha, write_new
from elf_audit import compare_symbols, inspect


def resolve_virtual(entries, name):
    remaining = name.split('/')
    resolved, hops = [], 0
    while remaining:
        part = remaining.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            need(resolved, 'Symlink escapes virtual root')
            resolved.pop()
            continue
        resolved.append(part)
        key = '/'.join(resolved)
        need(key in entries, 'Missing virtual path: ' + key)
        row = entries[key]
        if row['type'] == 'symlink':
            hops += 1
            need(hops <= 40, 'Symlink cycle/chain')
            target = row['target']
            resolved.pop()
            if target.startswith('/'):
                resolved = []
            remaining = target.split('/') + remaining
        elif remaining:
            need(row['type'] == 'directory', 'Non-directory virtual ancestor')
    return '/'.join(resolved) or '.'


def metadata(info):
    need(not stat.S_IMODE(info.st_mode) & 0o6000, 'setuid/setgid requires separate review')
    return {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid,
            'mtime_ns': info.st_mtime_ns}


def inventory_tree(root):
    need(sys.platform == 'linux', 'POSIX/Linux inventory required; Windows modes are not evidence')
    root = no_links(root)
    need(root.name.startswith('p4-rootfs-') and root.is_dir(), 'Dedicated synthetic p4-rootfs-* tree required')
    entries, objects, identities = {}, {}, {}

    def visit(directory):
        for path in sorted(directory.iterdir()):
            info = path.lstat()
            name = safe_name(path.relative_to(root).as_posix())
            attrs = os.listxattr(path, follow_symlinks=False)
            need(not attrs, 'Unreviewed xattrs/capabilities/ACLs: ' + name)
            row = metadata(info)
            if stat.S_ISLNK(info.st_mode):
                row.update(type='symlink', target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                row['type'] = 'directory'
            elif stat.S_ISREG(info.st_mode):
                row.update(type='file', sha256=digest(path), size=info.st_size)
                data = path.read_bytes()
                need(len(data) == info.st_size and sha(data) == row['sha256'], 'Tree changed during inventory')
                if data.startswith(b'\x7fELF'):
                    objects['/' + name] = {'sha256': row['sha256'], **inspect(data)}
                group = identities.setdefault((info.st_dev, info.st_ino), {'paths': [], 'links': info.st_nlink})
                group['paths'].append(name)
            else:
                raise ValueError('Device/FIFO/socket/special object: ' + name)
            entries[name] = row
            if row['type'] == 'directory':
                visit(path)

    need(not os.listxattr(root, follow_symlinks=False), 'Unreviewed root xattrs')
    entries['.'] = {'type': 'directory', **metadata(root.lstat())}
    visit(root)
    hardlinks = []
    for group in identities.values():
        need(group['links'] == len(group['paths']), 'External hardlink: no sharing with historical trees')
        if len(group['paths']) > 1:
            hardlinks.append(sorted(group['paths']))
    for name, row in entries.items():
        if row['type'] == 'symlink':
            resolve_virtual(entries, name)
    return {'status': 'OBSERVED_NOT_APPROVED', 'entries': entries,
            'hardlinks': sorted(hardlinks), 'elf_objects': objects,
            'root_path_observed': str(root), 'no_files_executed': True,
            'native_closure_approved': False,
            'not_proven': ['Tree must be frozen/read-only; this is not an atomic filesystem snapshot',
                           'Provenance, global loader scopes, recursive symbol resolution and target ABI']}


def candidates(report):
    objects = report['elf_objects']
    names = {}
    for path, obj in objects.items():
        for name in set(obj['soname'] + [posixpath.basename(path)]):
            names.setdefault(name, []).append(path)
    edges = []
    for path, obj in objects.items():
        for needed in obj['needed']:
            edges.append({'object': path, 'needed': needed, 'candidate_paths': names.get(needed, []),
                          'required_versions': obj['version_requires'].get(needed, []),
                          'direct_candidate_symbol_comparisons': [
                              {'provider': candidate, **compare_symbols(obj, objects[candidate], needed)}
                              for candidate in names.get(needed, [])],
                          'status': 'CANDIDATES_ONLY_NOT_LOADER_RESOLUTION' if names.get(needed)
                          else 'MISSING_PROVIDER_CANDIDATE'})
        if obj['interpreter']:
            resolved = resolve_virtual(report['entries'], obj['interpreter'])
            need('/' + resolved in objects, 'PT_INTERP does not resolve to an inventoried ELF')
    return {'status': 'BLOCKED_PENDING_LOADER_AND_SYMBOL_REVIEW', 'edges': edges,
            'note': 'SONAME presence is not DT_NEEDED resolution; no libc substitution or host fallback'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = no_links(args.rootfs)
    need(args.rootfs.is_absolute() and not no_links(args.out).is_relative_to(root), 'Output outside rootfs required')
    report = inventory_tree(root)
    report['recursive_elf_candidate_review'] = candidates(report)
    write_new(args.out, report)
    print('OBSERVED_NOT_APPROVED; no native closure or execution GO')


if __name__ == '__main__':
    main()
