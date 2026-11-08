"""DEFERRED Linux/root: a new P4-only synthetic namespace, never the P2/P3 namespace."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import candidate, digest, load, no_links, require, sha

MARKER = '.p4-synthetic.json'
KINDS = {
    'ready': b'{"format":1,"state":"ready"}\n',
    'invalid-json': b'not-json', 'invalid-utf8': b'\xff',
    'duplicate': b'{"format":1,"state":"ready","state":"quarantined"}',
    'boolean': b'{"format":true,"state":"ready"}',
    'unknown': b'{"format":1,"state":"unknown"}',
    'extra': b'{"format":1,"state":"ready","extra":true}', 'oversized': b'x' * 1025,
}


def scope(root):
    require(sys.platform == 'linux' and os.geteuid() == 0, 'Explicit Linux laboratory root required')
    require(root.is_absolute() and root.parent == Path('/var/tmp')
            and re.fullmatch(r'docnelo-p4-[0-9a-f]{32}', root.name), 'P4 namespace only')
    no_links(root)
    for path in root.parents:
        info = path.stat()
        require(info.st_uid == 0 and stat.S_ISDIR(info.st_mode)
                and (not info.st_mode & 0o022 or info.st_mode & stat.S_ISVTX),
                'Untrusted P4 ancestor')


def exclusive(path, data, mode, uid=0, gid=0):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, mode)
    with os.fdopen(fd, 'wb') as output:
        os.fchown(output.fileno(), uid, gid)
        os.fchmod(output.fileno(), mode)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def directory(path, uid, gid, mode):
    path.mkdir(mode=mode)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def contract_module(path):
    candidate(path)
    spec = importlib.util.spec_from_file_location('p4_frozen_contract',
                                                path / 'source' / 'tools' / 'recovery_control_directory.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def existing(root, contract):
    scope(root)
    for path, mode in ((root, 0o750), (root / MARKER, 0o600), (root / '.operator.lock', 0o600)):
        info = path.lstat()
        require(not path.is_symlink() and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode,
                'P4 marker/root/lock metadata')
        require(stat.S_ISDIR(info.st_mode) if path == root else
                stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'P4 marker/lock type')
    require((root / MARKER).stat().st_size <= 4096, 'P4 marker size')
    record = load(root / MARKER)
    require(record['format'] == 1 and record['synthetic_only'] is True
            and record['namespace'] == root.name and record['purpose'] == 'P4_ASGI_ONLY',
            'P4 marker binding')
    require(root.stat().st_gid == record['reader_gid'], 'P4 namespace reader group changed')
    info = (root / 'control').lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and info.st_gid == record['reader_gid']
            and [info.st_dev, info.st_ino] == record['control_identity'], 'P4 control identity changed')
    evidence = (root / 'evidence').lstat()
    require(stat.S_ISDIR(evidence.st_mode) and evidence.st_uid == record['uid']
            and evidence.st_gid == record['primary_gid'] and stat.S_IMODE(evidence.st_mode) == 0o700,
            'Evidence must be private to the test UID')
    return record, contract.HostControl(root / 'control', record['reader_gid'],
                                       tuple(record['control_identity']))


def metadata(path, read=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'exists': False}
    result = {'exists': True, 'device': info.st_dev, 'inode': info.st_ino,
              'uid': info.st_uid, 'gid': info.st_gid, 'mode': oct(stat.S_IMODE(info.st_mode)),
              'size': info.st_size, 'nlink': info.st_nlink,
              'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
              'type': stat.S_IFMT(info.st_mode)}
    if read and stat.S_ISREG(info.st_mode):
        require(info.st_size <= 4096 and info.st_nlink == 1, 'Unexpected synthetic latch size/links')
        result['sha256'] = digest(path)
    return result


def snapshot(root):
    return {'time_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(),
            'control': metadata(root / 'control'),
            'latch': metadata(root / 'control' / 'recovery-state.json', read=True),
            'evidence': metadata(root / 'evidence'),
            'entries': sorted(p.name for p in (root / 'control').iterdir())}


@contextmanager
def locked(contract, root, control):
    with contract.operator_lock(root / '.operator.lock', control, 0):
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--authorize-new-p4-synthetic-only', action='store_true', required=True)
    parser.add_argument('action', choices=('provision', 'check', 'snapshot', 'publish', 'remove', 'mode', 'symlink'))
    parser.add_argument('--uid', type=int)
    parser.add_argument('--primary-gid', type=int)
    parser.add_argument('--reader-gid', type=int)
    parser.add_argument('--kind', choices=('quarantined', *KINDS), default='quarantined')
    parser.add_argument('--object', choices=('latch', 'directory'), default='latch')
    parser.add_argument('--mode', choices=('000', '0440', '0700', '0750'))
    args = parser.parse_args()
    root = args.root
    scope(root)
    contract = contract_module(args.candidate)
    if args.action == 'provision':
        require(all(type(n) is int and 0 < n <= 2147483647 for n in
                    (args.uid, args.primary_gid, args.reader_gid)), 'Explicit nonzero identities')
        require(args.primary_gid != args.reader_gid, 'Separate reader group required')
        require(not root.exists(), 'Never reuse an existing namespace')
        directory(root, 0, args.reader_gid, 0o750)
        directory(root / 'control', 0, args.reader_gid, 0o750)
        directory(root / 'evidence', args.uid, args.primary_gid, 0o700)
        directory(root / 'operator', 0, 0, 0o700)
        info = (root / 'control').stat()
        record = {'format': 1, 'synthetic_only': True, 'purpose': 'P4_ASGI_ONLY',
                  'namespace': root.name, 'uid': args.uid, 'primary_gid': args.primary_gid,
                  'reader_gid': args.reader_gid, 'control_identity': [info.st_dev, info.st_ino]}
        exclusive(root / MARKER, json.dumps(record).encode(), 0o600)
        exclusive(root / '.operator.lock', b'', 0o600)
        control = contract.validate_host(str(root / 'control'), args.reader_gid, allow_missing=True)
        contract.publish_quarantine(control, lock_path=root / '.operator.lock', lock_owner_uid=0)
    record, control = existing(root, contract)
    before = snapshot(root)
    start = time.time_ns()
    if args.action == 'check':
        contract.validate_host(str(control.path), control.gid, expected=control)
    elif args.action == 'publish' and args.kind == 'quarantined':
        contract.publish_quarantine(control, lock_path=root / '.operator.lock', lock_owner_uid=0)
    elif args.action in ('publish', 'remove', 'mode', 'symlink'):
        with locked(contract, root, control):
            latch = control.path / contract.LATCH
            if args.action == 'mode':
                require(args.mode is not None, 'Explicit mode required')
                target = control.path if args.object == 'directory' else latch
                require(not target.is_symlink(), 'Never chmod a symlink')
                os.chmod(target, int(args.mode, 8), follow_symlinks=False)
            else:
                require(stat.S_IMODE(control.path.stat().st_mode) == 0o750,
                        'Restore the P4 directory mode before publication')
                with contract._directory(control) as fd:
                    if args.action in ('remove', 'symlink'):
                        os.unlink(contract.LATCH, dir_fd=fd)
                        if args.action == 'symlink':
                            os.symlink('synthetic-missing.json', contract.LATCH, dir_fd=fd)
                    else:
                        name = '.p4-' + uuid.uuid4().hex + '.tmp'
                        # Interrupted temporaries are evidence: never silently remove them.
                        exclusive(control.path / name, KINDS[args.kind], 0o440, gid=control.gid)
                        os.replace(name, contract.LATCH, src_dir_fd=fd, dst_dir_fd=fd)
                    os.fsync(fd)
    after = snapshot(root)
    require((before['control']['device'], before['control']['inode']) ==
            (after['control']['device'], after['control']['inode']), 'Control directory replaced')
    print(json.dumps({'scope': 'P4_SYNTHETIC_ONLY', 'action': args.action, 'kind': args.kind,
                      'object': args.object, 'mode': args.mode, 'record': record,
                      'start_ns': start, 'commit_return_ns': time.time_ns(),
                      'before': before, 'after': after}, sort_keys=True))


if __name__ == '__main__':
    main()
