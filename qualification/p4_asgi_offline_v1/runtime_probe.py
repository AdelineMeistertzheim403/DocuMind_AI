"""DEFERRED image probe: no backend import, sockets, subprocesses or service startup."""
import argparse
import base64
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import digest, load, no_links, norm, require, write_new


def deny_io(event, args):
    if event.startswith(('socket.', 'os.exec', 'os.spawn')) or event in {
        'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
        'sqlite3.connect', 'smtplib.connect', 'http.client.connect', 'urllib.Request',
    }:
        raise RuntimeError('Forbidden runtime-probe I/O: ' + event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.dont_write_bytecode, 'Use -I -B')
    require(sys.platform == 'linux' and platform.machine() == 'x86_64'
            and platform.python_implementation() == 'CPython'
            and sys.version_info[:3] == (3, 11, 18)
            and sys.prefix == '/opt/p4-venv' and sys.prefix != sys.base_prefix,
            'Dedicated CPython3.11.18/x86_64 venv required')
    release = platform.freedesktop_os_release()
    require(release['ID'] == 'debian' and release['VERSION_ID'] == '13', 'Debian13 required')
    require(os.geteuid() != 0 and args.out.parent == Path('/evidence'), 'Non-root /evidence observation only')
    observed = load(args.inventory)
    expected = {norm(r['distribution']): r['version'] for r in observed['distributions']}
    actual, record_checks = {}, {}
    sys.addaudithook(deny_io)
    for distribution in importlib.metadata.distributions():
        name = norm(distribution.metadata['Name'])
        require(name not in actual, 'Duplicate installed distribution')
        actual[name] = distribution.version
        checked = {}
        require(distribution.files is not None, 'Missing installed RECORD')
        for item in distribution.files:
            path = Path(distribution.locate_file(item)).absolute()
            require(path.resolve().is_relative_to(Path(sys.prefix)), 'Distribution escaped venv')
            no_links(path)
            require(path.is_file(), 'Missing installed file')
            if item.hash:
                require(item.hash.mode == 'sha256', 'Unexpected RECORD hash algorithm')
                value = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip('=')
                require(value == item.hash.value, 'Installed RECORD mismatch: ' + str(item))
            else:
                require(path.name == 'RECORD', 'Unhashed installed file (including bytecode) refused')
            checked[str(item)] = digest(path)
        record_checks[name] = checked
    require(actual == expected, 'Installed selection differs from the exact observed 43-wheel selection')
    for module in ('pytest', 'yaml', 'fastapi', 'starlette', 'httpx', 'sqlalchemy', 'psycopg',
                   'psycopg_binary', 'openai', 'alembic', 'argon2', 'psutil', 'pgvector.sqlalchemy',
                   'pydantic_settings', 'python_multipart', 'ssl', 'sqlite3', 'ctypes', 'zlib', 'bz2', 'lzma'):
        importlib.import_module(module)
    from psycopg import pq
    require(pq.__impl__ == 'binary', 'Psycopg binary implementation required; no system libpq fallback')
    status = Path('/proc/self/status').read_text()
    fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
    require(all(int(fields[key].strip(), 16) == 0 for key in
                ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))
            and fields['NoNewPrivs'].strip() == '1' and fields['Seccomp'].strip() == '2',
            'Effective capability/no-new-privileges/seccomp mismatch')
    maps_ids = {name: Path('/proc/self/' + name).read_text() for name in ('uid_map', 'gid_map')}
    require(all([list(map(int, row.split())) for row in text.splitlines()] ==
                [[0, 0, 4294967295]] for text in maps_ids.values()), 'Remapped identity is not approved')
    limits = {name: (Path('/sys/fs/cgroup') / name).read_text().strip() for name in
              ('cpu.max', 'memory.max', 'memory.swap.max', 'pids.max', 'pids.current')}
    quota, period = map(int, limits['cpu.max'].split())
    require(quota * 2 == period and limits['memory.max'] == '536870912'
            and limits['memory.swap.max'] == '0' and limits['pids.max'] == '64',
            'Effective cgroup v2 limits mismatch')
    network = Path('/proc/net/dev').read_text()
    require({line.split(':', 1)[0].strip() for line in network.splitlines() if ':' in line} == {'lo'},
            'Unexpected network interface')
    maps = Path('/proc/self/maps').read_text(encoding='ascii')
    binaries = {}
    for line in maps.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith('/'):
            path = Path(parts[5])
            require(path.is_file(), 'Missing/deleted mapped binary')
            binaries[str(path)] = digest(path)
    result = {
        'verdict': 'PASS_RUNTIME_OBSERVATION_ONLY_NOT_P4', 'p4_go': False,
        'python': sys.version, 'python_executable': sys.executable,
        'python_binary_sha256': digest(Path(sys.executable).resolve()),
        'base_prefix': sys.base_prefix, 'os_release': release,
        'uid': os.geteuid(), 'gid': os.getegid(), 'groups': os.getgroups(),
        **maps_ids, 'proc_status': status,
        'pid1_status': Path('/proc/1/status').read_text(),
        'mountinfo': Path('/proc/self/mountinfo').read_text(),
        'cgroup': Path('/proc/self/cgroup').read_text(),
        'cgroup_v2_limits': limits, 'network_interfaces': network,
        'installed': actual, 'installed_files_sha256': record_checks,
        'mapped_binaries_sha256': binaries, 'inventory_sha256': digest(args.inventory),
        'probe_sha256': digest(Path(__file__)), 'helper_sha256': digest(Path(__file__).with_name('offline.py')),
        'native_provenance_approved': False,
    }
    write_new(args.out, result)


if __name__ == '__main__':
    main()
