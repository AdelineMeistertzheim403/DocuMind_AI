"""ELF64 offline inspection. Never executes ldd, a loader, an image or a library."""
import argparse
from pathlib import Path, PurePosixPath
import posixpath
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, inventory, need, sha, write_new

SITE = '/opt/p4-venv/lib/python3.11/site-packages'


def elf(data):
    need(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    need(len(data) >= 64 and struct.unpack_from('<H', data, 18)[0] == 62, 'Expected x86_64 ELF')

    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        need(0 <= offset <= len(data) - size, 'Truncated ELF table')
        return struct.unpack_from(fmt, data, offset)

    def cstring(table, offset):
        need(0 <= offset < len(table), 'ELF string offset outside table')
        return table[offset:table.index(b'\0', offset)].decode('ascii')

    phoff, shoff = unpack('<QQ', 32)
    phsize, phnum, shsize, shnum, _ = unpack('<HHHHH', 54)
    need(phsize >= 56 and shsize >= 64 and shnum > 0, 'ELF headers unavailable; cannot prove versions')
    loads, dynamic, interpreter = [], [], None
    for index in range(phnum):
        kind, _, offset, vaddr, _, size, _, _ = unpack('<IIQQQQQQ', phoff + index * phsize)
        need(offset + size <= len(data), 'Truncated ELF segment')
        if kind == 1:
            loads.append((vaddr, vaddr + size, offset))
        elif kind == 2:
            need(size % 16 == 0, 'Invalid ELF dynamic table')
            for tag, value in struct.iter_unpack('<qQ', data[offset:offset + size]):
                if tag == 0:
                    break
                dynamic.append((tag, value))
        elif kind == 3:
            interpreter = cstring(data[offset:offset + size], 0)
    strings = next((value for tag, value in dynamic if tag == 5), None)
    dynamic_strings = b''
    if strings is not None:
        offsets = [offset + strings - start for start, end, offset in loads if start <= strings < end]
        need(len(offsets) == 1, 'Ambiguous ELF DT_STRTAB')
        dynamic_strings = data[offsets[0]:]
    needed = [cstring(dynamic_strings, value) for tag, value in dynamic if tag == 1]
    rpath = [cstring(dynamic_strings, value) for tag, value in dynamic if tag == 15]
    runpath = [cstring(dynamic_strings, value) for tag, value in dynamic if tag == 29]
    soname = [cstring(dynamic_strings, value) for tag, value in dynamic if tag == 14]
    sections = [unpack('<IIQQQQIIQQ', shoff + index * shsize) for index in range(shnum)]
    requires, provides = {}, set()
    for section in sections:
        _, kind, _, _, offset, size, link, _, _, _ = section
        if kind not in (0x6ffffffe, 0x6ffffffd):
            continue
        need(link < len(sections) and offset + size <= len(data), 'ELF version section bounds')
        table = sections[link]
        strings_table = data[table[4]:table[4] + table[5]]
        cursor, seen = offset, set()
        while cursor < offset + size:
            need(cursor not in seen, 'Cyclic ELF version table')
            seen.add(cursor)
            if kind == 0x6ffffffe:
                version, count, filename, aux, following = unpack('<HHIII', cursor)
                need(version == 1, 'Unsupported verneed format')
                library = cstring(strings_table, filename)
                values = requires.setdefault(library, [])
                item, visited = cursor + aux, set()
                for _ in range(count):
                    need(item not in visited, 'Cyclic vernaux')
                    visited.add(item)
                    _, _, _, name, next_aux = unpack('<IHHII', item)
                    values.append(cstring(strings_table, name))
                    item += next_aux
            else:
                version, _, _, count, _, aux, following = unpack('<HHHHIII', cursor)
                need(version == 1 and count >= 1, 'Unsupported verdef format')
                name, _ = unpack('<II', cursor + aux)
                provides.add(cstring(strings_table, name))
            if not following:
                break
            cursor += following
    return {'class': 'ELF64', 'machine': 'x86_64', 'interpreter': interpreter,
            'needed': needed, 'rpath': rpath, 'runpath': runpath,
            'soname': soname, 'version_requires': {k: sorted(set(v)) for k, v in requires.items()},
            'version_defines': sorted(provides)}


def local_candidates(obj, library):
    need('/' not in library, 'Slash in DT_NEEDED needs separate review')
    # This proves direct wheel-local edges only, not the complete glibc search algorithm.
    paths = obj['runpath'] or obj['rpath']
    result = []
    for value in paths:
        for folder in value.split(':'):
            folder = folder.replace('${ORIGIN}', str(PurePosixPath(obj['path']).parent))
            folder = folder.replace('$ORIGIN', str(PurePosixPath(obj['path']).parent))
            need(folder.startswith('/') and '$' not in folder, 'Unreviewed dynamic search path')
            result.append(posixpath.normpath(folder + '/' + library))
    return result


def scan(wheel_directory, observed):
    objects = []
    for record in observed['distributions']:
        wheel = wheel_directory / record['file']
        need(digest(wheel) == record['sha256'], 'Wheel hash changed before ELF scan')
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                if data.startswith(b'\x7fELF'):
                    objects.append({'path': SITE + '/' + name, 'wheel': record['file'],
                                    'distribution': record['distribution'], 'version': record['version'],
                                    'file': name, 'sha256': sha(data), **elf(data)})
    by_path = {obj['path']: obj for obj in objects}
    need(len(by_path) == len(objects), 'Ambiguous installed ELF paths')
    edges = []
    for obj in objects:
        for library in obj['needed']:
            candidates = local_candidates(obj, library)
            found = [by_path[path] for path in candidates if path in by_path]
            need(len(found) <= 1, 'Ambiguous wheel-local dependency')
            target = found[0] if found else None
            versions = obj['version_requires'].get(library, [])
            missing = sorted(set(versions) - set(target['version_defines'])) if target else versions
            edges.append({'object': obj['path'], 'needed': library, 'search_paths': candidates,
                          'resolved_wheel_path': target['path'] if target else None,
                          'required_versions': versions, 'unprovided_versions': missing,
                          'status': 'WHEEL_LOCAL_DIRECT_EDGE_MATCH' if target and not missing else
                                    'VERSION_MISMATCH' if target else 'BASE_NOT_AVAILABLE'})
    unresolved = sorted({edge['needed'] for edge in edges if edge['status'] != 'WHEEL_LOCAL_DIRECT_EDGE_MATCH'})
    return {'status': 'BLOCKED', 'binary_closure_approved': False, 'build_go': False,
            'objects': objects, 'direct_edges': edges, 'unresolved_library_names': unresolved,
            'base_image_id': None, 'base_interpreter': None, 'base_glibc': None,
            'not_covered': ['No base rootfs/loader/glibc/CPython/stdlib native files supplied',
                            'Direct RPATH/RUNPATH matches are not full inherited RPATH/cache/system resolution',
                            'No recursive base symbol/relocation, dlopen, CPU ISA or runtime ABI proof',
                            'No x86_64/CPython3.11.18 target execution'],
            'approval': 'Independent review and target execution still required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, scan(args.wheels, inventory(args.inventory)))


if __name__ == '__main__':
    main()
