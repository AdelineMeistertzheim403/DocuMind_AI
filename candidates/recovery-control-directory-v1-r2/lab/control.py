"""DEFERRED Linux/root lab utility. Writes only a new, marked /var/tmp namespace."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from tools import recovery_control_directory as contract

MARKER = '.candidate-lab.json'
KINDS = {
    'ready': b'{"format":1,"state":"ready"}\n',
    'invalid-json': b'not-json', 'invalid-utf8': b'\xff',
    'duplicate': b'{"format":1,"state":"ready","state":"quarantined"}',
    'boolean': b'{"format":true,"state":"ready"}', 'unknown': b'{"format":1,"state":"unknown"}',
    'extra': b'{"format":1,"state":"ready","extra":true}', 'oversized': b'x' * 1025,
}


def scope(root):
    contract._require_linux()
    if os.geteuid() != 0:
        raise contract.ContractError('explicit isolated-laboratory root authorization required')
    contract.absolute_path(str(root))
    if root.parent != Path('/var/tmp') or not re.fullmatch(r'docnelo-rcd-[a-f0-9]{32}', root.name):
        raise contract.ContractError('only a new /var/tmp/docnelo-rcd-<32 hex> namespace is permitted')
    contract._trusted_parents(root)


def exclusive(path, payload, mode):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, 'wb') as output:
        os.fchmod(output.fileno(), mode)
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def provision(root, gid):
    scope(root)
    contract.reader_gid(str(gid))
    root.mkdir(mode=0o750)
    os.chown(root, 0, gid)
    os.chmod(root, 0o750)
    directory = root / 'recovery-control'
    directory.mkdir(mode=0o750)
    os.chown(directory, 0, gid)
    os.chmod(directory, 0o750)
    info = directory.stat()
    exclusive(root / '.operator.lock', b'', 0o600)
    record = {'format': 1, 'synthetic_only': True, 'gid': gid,
              'device': info.st_dev, 'inode': info.st_ino}
    exclusive(root / MARKER, json.dumps(record).encode(), 0o600)
    control = contract.validate_host(str(directory), gid, allow_missing=True)
    contract.publish_quarantine(control, lock_path=root / '.operator.lock', lock_owner_uid=0)
    return record


def existing(root):
    scope(root)
    info = root.lstat()
    marker = root / MARKER
    meta = marker.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o750
            or not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
            or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_nlink != 1 or meta.st_size > 1024):
        raise contract.ContractError('untrusted laboratory marker')
    record = json.loads(marker.read_bytes())
    if record.get('format') != 1 or record.get('synthetic_only') is not True:
        raise contract.ContractError('not a synthetic candidate laboratory')
    directory = root / 'recovery-control'
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != record['gid']
            or (info.st_dev, info.st_ino) != (record['device'], record['inode'])):
        raise contract.ContractError('laboratory control directory identity changed')
    return contract.HostControl(directory, record['gid'], (info.st_dev, info.st_ino))


def inject_interruption(boundary):
    if boundary is None:
        return
    original_metadata, original_fsync, original_replace = contract._metadata, os.fsync, os.replace

    def metadata(fd, gid):
        original_metadata(fd, gid)
        if boundary == 'after-metadata':
            os._exit(91)

    def fsync(fd):
        original_fsync(fd)
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if boundary == ('after-directory-fsync' if is_directory else 'after-file-fsync'):
            os._exit(91)

    def replace(*args, **kwargs):
        if boundary == 'before-replace':
            os._exit(91)
        original_replace(*args, **kwargs)
        if boundary == 'after-replace':
            os._exit(91)

    contract._metadata, os.fsync, os.replace = metadata, fsync, replace


def mutate(root, control, args):
    latch = control.path / contract.LATCH
    with contract.operator_lock(root / '.operator.lock', control, 0):
        if args.action == 'mode':
            target = control.path if args.object == 'directory' else latch
            if target.is_symlink():
                raise contract.ContractError('refusing chmod through symlink')
            os.chmod(target, int(args.mode, 8), follow_symlinks=False)
            return
        if stat.S_IMODE(control.path.stat().st_mode) != 0o750:
            raise contract.ContractError('restore synthetic directory mode before publication')
        with contract._directory(control) as directory:
            if args.action in ('remove', 'symlink', 'fifo'):
                try:
                    os.unlink(contract.LATCH, dir_fd=directory)
                except FileNotFoundError:
                    pass
                if args.action == 'symlink':
                    os.symlink('../synthetic-decoy.json', contract.LATCH, dir_fd=directory)
                elif args.action == 'fifo':
                    os.mkfifo(contract.LATCH, 0o600, dir_fd=directory)
                return
            temporary = '.synthetic-' + uuid.uuid4().hex + '.tmp'
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY,
                                 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    contract._metadata(output.fileno(), control.gid)
                    output.write(KINDS[args.kind])
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, contract.LATCH, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=('provision', 'publish', 'remove', 'symlink', 'fifo', 'mode', 'check'))
    parser.add_argument('--reader-gid', type=int)
    parser.add_argument('--kind', choices=('quarantined', *KINDS), default='quarantined')
    parser.add_argument('--authorize-synthetic-only', action='store_true')
    parser.add_argument('--object', choices=('latch', 'directory'), default='latch')
    parser.add_argument('--mode', choices=('000', '0440', '0600', '0664', '0700', '0750'))
    parser.add_argument('--interrupt', choices=(
        'after-metadata', 'after-file-fsync', 'before-replace', 'after-replace', 'after-directory-fsync'))
    args = parser.parse_args()
    if args.action == 'provision':
        if args.reader_gid is None:
            parser.error('--reader-gid required')
        print(json.dumps(provision(args.root, args.reader_gid)))
        return
    control = existing(args.root)
    if args.action == 'check':
        contract.validate_host(str(control.path), control.gid, expected=control)
    elif args.action == 'publish' and args.kind == 'quarantined':
        if args.interrupt and not args.authorize_synthetic_only:
            parser.error('interruption requires explicit synthetic-only authorization')
        inject_interruption(args.interrupt)
        contract.publish_quarantine(control, lock_path=args.root / '.operator.lock', lock_owner_uid=0)
    else:
        if not args.authorize_synthetic_only:
            parser.error('deliberate fault/ready requires --authorize-synthetic-only')
        if args.interrupt:
            parser.error('interruption is supported only by the actual quarantine publisher')
        if args.action == 'mode' and args.mode is None:
            parser.error('--mode required')
        mutate(args.root, control, args)
    print(json.dumps({'action': args.action, 'synthetic_only': True,
                      'directory_device_inode': control.identity, 'kind': args.kind}))


if __name__ == '__main__':
    main()
