"""Local Docker only. Own internal network + tmpfs PostgreSQL; no VPS/host ports/volumes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

LAB = Path(__file__).resolve().parent
CANDIDATE = '--candidate' in sys.argv
RESTART = '--restart-only' in sys.argv
SOURCE = LAB / ('candidate-source' if CANDIDATE else 'source')
PREFIX = ('candidate-' if CANDIDATE else '') + ('restart-' if RESTART else '')
D = ['docker', '--context', 'desktop-linux']
label = 'docnelo-ten-' + uuid4().hex[:12]
network = label + '-net'
dbid = None
networkid = None

def docker(*args):
    return subprocess.check_output(D + list(args), text=True, stderr=subprocess.PIPE).strip()

try:
    networkid = docker('network', 'create', '--internal', '--label', 'docnelo.test=ten-users', network)
    dbid = docker('run', '-d', '--name', label+'-db', '--network', network, '--network-alias', 'db',
        '--pull', 'never', '--user', '70:70', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--label', 'docnelo.test=ten-users', '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,size=768m,uid=70,gid=70,mode=0700',
        '-e', 'POSTGRES_USER=synthetic', '-e', 'POSTGRES_PASSWORD=fictitious-lab-only', '-e', 'POSTGRES_DB=synthetic',
        'documind-postgres-vector:17')
    for attempt in range(40):
        check = subprocess.run(D + ['exec', dbid, 'pg_isready', '-U', 'synthetic', '-d', 'synthetic'], capture_output=True)
        if check.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Synthetic PostgreSQL not ready')
    tests = ['tests/test_ten_users_preparation.py', 'tests/test_public_beta.py', 'tests/test_public_beta_state.py',
        'tests/test_public_beta_postgresql_concurrency.py', 'tests/test_public_beta_email_abuse.py',
        'tests/test_accounts_saas.py', 'tests/test_documents.py', 'tests/test_public_beta_authorization.py',
        'tests/test_upload_admission.py']
    if RESTART:
        tests = ['tests/test_ten_users_process_restart.py']
    # No host environment or .env file is supplied to the test container.
    argv = D + ['run', '--rm', '--name', label+'-tests', '--network', network, '--pull', 'never',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--tmpfs', '/tmp:rw,nosuid,size=768m,mode=1777', '--workdir', '/work',
        '--mount', f'type=bind,source={SOURCE},target=/work,readonly',
        '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONPATH=/work',
        '-e', 'TEST_DATABASE_URL=postgresql+psycopg://synthetic:fictitious-lab-only@db:5432/synthetic',
        'documind-s14-6-proofs:local', 'python', '-B', '-m', 'pytest', '-p', 'no:cacheprovider',
        '--require-no-skips', '-q', *tests]
    # Fail before running the suite if a requested regression module is absent.
    assert all((SOURCE / test).is_file() for test in tests)
    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (LAB / (PREFIX + 'pytest.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    (LAB / (PREFIX + 'result.json')).write_text(json.dumps({'exit_code': result.returncode, 'network': 'internal-only',
        'postgres': '17/vector, fresh tmpfs, no host ports or volumes', 'tests': tests,
        'scope': 'exported candidate API' if CANDIDATE else 'canonical R2 source, not attested active API',
        'strict_lifecycle_ten_qualified': False}, indent=2), encoding='utf-8')
    print((result.stdout + result.stderr)[-5500:])
    if result.returncode:
        raise SystemExit(result.returncode)
finally:
    # Captured IDs belong exclusively to this invocation; no volume delete or prune.
    if dbid:
        subprocess.run(D + ['stop', '-t', '5', dbid], capture_output=True)
        subprocess.run(D + ['rm', dbid], capture_output=True)
    if networkid:
        subprocess.run(D + ['network', 'rm', networkid], capture_output=True)
