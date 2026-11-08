"""V5.1 preflight: synthetic temporary keys only; no services or real secrets."""
import ast
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SOURCES = (
    'tools/public_beta_backup.py', 'tools/public_beta_restic_guard.py',
    'tools/backup_local.py', 'tools/verify_snapshot.py', 'tools/validate_restore.py',
    'tools/lifecycle_key_policy.py', 'backend/__init__.py',
    'backend/lifecycle_snapshot.py', 'backend/lifecycle_backup_lock.py',
)


def main():
    if sys.version_info[:2] != (3, 11) or sys.platform != 'linux':
        raise RuntimeError('Python 3.11 on Linux required')
    for distribution, version in (('SQLAlchemy', '2.0.55'), ('psycopg', '3.3.6')):
        if importlib.metadata.version(distribution) != version:
            raise RuntimeError('Unexpected dependency version: ' + distribution)
    import fcntl
    import psycopg
    from sqlalchemy import create_engine
    engine = create_engine('postgresql+psycopg://')
    engine.dispose()  # Dialect import only: no connection.
    for name in SOURCES:
        source = ROOT / name
        compile(ast.parse(source.read_bytes(), feature_version=(3, 11)), name, 'exec')
        module = name.removesuffix('.py').replace('/', '.').removesuffix('.__init__')
        imported = importlib.import_module(module)
        if Path(imported.__file__).resolve() != source.resolve():
            raise RuntimeError('Import outside this release: ' + module)
    from tools.lifecycle_key_policy import validate_key_permissions
    from tools.validate_restore import _extract_lifecycle_keys
    if not hasattr(os, 'O_NOFOLLOW'):
        raise RuntimeError('O_NOFOLLOW required')
    with tempfile.TemporaryFile() as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        stream.write(b'v51-preflight')
        stream.seek(0)
        if hashlib.file_digest(stream, 'sha256').hexdigest() != hashlib.sha256(b'v51-preflight').hexdigest():
            raise RuntimeError('file_digest check failed')
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    for mode in (0o444, 0o644, 0o660, 0o777):
        try:
            validate_key_permissions(mode, 0, 1000)
        except ValueError:
            pass
        else:
            raise RuntimeError('Unsafe mode accepted')
    for mode in (0o400, 0o440, 0o600, 0o640):
        with tempfile.TemporaryDirectory(prefix='docnelo-v51-preflight-') as directory:
            root = Path(directory).resolve()
            snapshot = root / 'snapshot'
            snapshot.mkdir(mode=0o700)
            lifecycle = root / 'lifecycle'
            lifecycle.mkdir(mode=0o700)
            inventory = {}
            with tarfile.open(snapshot / 'lifecycle-keys.tar.gz', 'w:gz') as archive:
                for index, name in enumerate(('keys/authentication.key', 'keys/admission.key')):
                    payload = bytes([index + 1]) * 32
                    item = tarfile.TarInfo(name)
                    item.mode, item.uid, item.gid, item.size = mode, 0, 1000, len(payload)
                    archive.addfile(item, io.BytesIO(payload))
                    inventory[name] = {'mode': mode, 'uid': 0, 'gid': 1000, 'size': len(payload),
                                       'sha256': hashlib.sha256(payload).hexdigest()}
            _extract_lifecycle_keys(snapshot, {'lifecycle_keys': inventory}, lifecycle)
            for index, name in enumerate(inventory):
                target = lifecycle / name
                info = target.stat()
                if (stat.S_IMODE(info.st_mode) != 0o400 or info.st_uid != os.geteuid()
                        or stat.S_IMODE(target.parent.stat().st_mode) != 0o700
                        or target.read_bytes() != bytes([index + 1]) * 32):
                    raise RuntimeError('Restored synthetic key identity/permissions mismatch')
    print(json.dumps({'status': 'passed', 'tooling_version': '5.1', 'python': sys.version.split()[0],
                      'source_files': len(SOURCES), 'restore_modes_exercised': 4,
                      'services_or_real_keys_accessed': False}))


if __name__ == '__main__':
    main()
