"""Read-only Debian preflight: imports/APIs and a temporary fcntl lock only."""
import ast
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SOURCES = (
    'tools/public_beta_backup.py', 'tools/public_beta_restic_guard.py',
    'tools/backup_local.py', 'tools/verify_snapshot.py', 'tools/validate_restore.py',
    'backend/__init__.py', 'backend/lifecycle_snapshot.py', 'backend/lifecycle_backup_lock.py',
)


def main():
    if sys.version_info[:2] != (3, 11) or sys.platform != 'linux':
        raise RuntimeError('Python 3.11 on Linux required')
    for distribution, expected in (('SQLAlchemy', '2.0.55'), ('psycopg', '3.3.6')):
        if importlib.metadata.version(distribution) != expected:
            raise RuntimeError('Unexpected dependency version: ' + distribution)
    import fcntl
    import psycopg
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    # Construct a dialect without opening a connection or using credentials.
    engine = create_engine('postgresql+psycopg://')
    engine.dispose()
    assert make_url('postgresql+psycopg://').get_driver_name() == 'psycopg'
    assert hasattr(os, 'O_NOFOLLOW')
    with tempfile.TemporaryFile() as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        stream.write(b'compatibility-test')
        stream.seek(0)
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == hashlib.sha256(b'compatibility-test').hexdigest()
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    assert Path('/tmp/child').is_relative_to('/tmp')
    assert '/prefix'.removeprefix('/') == 'prefix'
    for name in SOURCES:
        source = ROOT / name
        tree = ast.parse(source.read_bytes(), filename=name, feature_version=(3, 11))
        compile(tree, name, 'exec')
        module = name.removesuffix('.py').replace('/', '.')
        if module.endswith('.__init__'):
            module = module.removesuffix('.__init__')
        imported = importlib.import_module(module)
        if Path(imported.__file__).resolve() != source.resolve():
            raise RuntimeError('Import resolved outside the bundle: ' + module)
    print(json.dumps({'status': 'passed', 'python': sys.version.split()[0],
                      'source_files': len(SOURCES), 'network_or_services_called': False}))


if __name__ == '__main__':
    main()
