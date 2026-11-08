"""DEFERRED stdlib-only reader. No server, network, database or external library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time


def report(path, descriptor=None):
    owned = descriptor is None
    try:
        if owned:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return {'error': 'nonregular'}
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 1025)
        try:
            state = json.loads(raw).get('state')
        except (ValueError, AttributeError):
            state = 'invalid'
        return {'inode': metadata.st_ino, 'device': metadata.st_dev,
                'uid': metadata.st_uid, 'gid': metadata.st_gid,
                'mode': oct(stat.S_IMODE(metadata.st_mode)), 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'state': state}
    except OSError as error:
        return {'error': type(error).__name__, 'errno': error.errno}
    finally:
        if owned and descriptor is not None:
            os.close(descriptor)


def writes(path):
    parent = Path(path).parent
    results = {}
    attempts = {
        'write': lambda: os.close(os.open(path, os.O_WRONLY | os.O_NOFOLLOW)),
        'truncate': lambda: os.close(os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)),
        'unlink': lambda: os.unlink(path),
        'rename': lambda: os.rename(path, parent / '.forbidden-rename'),
        'create': lambda: os.close(os.open(parent / '.forbidden-create', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)),
    }
    for label, operation in attempts.items():
        try:
            operation()
            results[label] = 'UNEXPECTED_SUCCESS'
        except OSError as error:
            results[label] = {'error': type(error).__name__, 'errno': error.errno}
    if any(value == 'UNEXPECTED_SUCCESS' for value in results.values()):
        raise RuntimeError('write isolation failed: ' + json.dumps(results))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', default='/run/documind-control/recovery-state.json')
    parser.add_argument('--writes', action='store_true')
    parser.add_argument('--hold', action='store_true')
    parser.add_argument('--idle', action='store_true')
    args = parser.parse_args()
    if args.idle:
        while True:
            time.sleep(3600)
    identity = {'uid': os.geteuid(), 'gid': os.getegid(), 'groups': os.getgroups()}
    if identity['uid'] == 0:
        raise RuntimeError('reader must be non-root')
    if args.writes and args.path != '/run/documind-control/recovery-state.json':
        raise RuntimeError('write attempts are limited to the synthetic lab control target')
    print(json.dumps({'identity': identity, 'fresh': report(args.path)}), flush=True)
    if args.writes:
        print(json.dumps({'writes': writes(args.path)}), flush=True)
    if args.hold:
        descriptor = os.open(args.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            print(json.dumps({'held_before': report(args.path, descriptor)}), flush=True)
            if sys.stdin.readline().strip() != 'COMMIT_PUBLISHED':
                raise RuntimeError('explicit publication barrier required on stdin')
            print(json.dumps({'held_after': report(args.path, descriptor), 'fresh_after': report(args.path)}), flush=True)
        finally:
            os.close(descriptor)


if __name__ == '__main__':
    main()
