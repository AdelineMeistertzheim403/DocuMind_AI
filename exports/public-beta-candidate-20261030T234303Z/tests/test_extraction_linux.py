"""Native Linux proofs with harmless code; never use host/production secrets or exploit PDFs."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.config import Settings
from backend.services import extraction
from documind_extractor import contract

pytestmark = [pytest.mark.posix,
              pytest.mark.skipif(sys.platform != 'linux', reason='Requires native Linux Landlock/seccomp')]


def require_sandbox():
    # Deliberately fail on Linux when protections are missing; never turn these proofs into skips.
    extraction.check_available(Settings(_env_file=None))


def confined_probe(code, timeout=5, maximum=4096, library_path=None):
    directory = str(extraction.RUNNER.parent)
    script = (
        'import sys; sys.path.insert(0,' + repr(directory) + '); '
        'from sandbox import confine; import os,socket,ctypes,json,resource; '
        f'confine(512,2,library_path={library_path!r});\n' + code
    )
    return extraction.exchange([sys.executable, '-I', '-S', '-c', script], b'', timeout, maximum)


def test_native_policy_available():
    require_sandbox()


@pytest.mark.parametrize('name', ['other-user-document.pdf', 'api.env', 'postgres.env', 'smtp.env', 'restic.env'])
def test_other_documents_and_fictitious_secrets_unreadable(tmp_path, name):
    path = tmp_path / name; path.write_text('FAKE-SECRET-MUST-NOT-BE-READ')
    code = f'''
try:
    open({str(path)!r}, 'rb').read()
except PermissionError:
    print('denied')
else:
    raise AssertionError('Unexpected file access')
'''
    assert confined_probe(code).strip() == b'denied'
    assert path.read_text() == 'FAKE-SECRET-MUST-NOT-BE-READ'


def test_environment_and_inherited_descriptor_not_available(tmp_path, monkeypatch):
    path = tmp_path / 'postgres-password'; path.write_text('FAKE-PG-PASSWORD')
    monkeypatch.setenv('POSTGRES_PASSWORD', 'FAKE-PG-PASSWORD')
    monkeypatch.setenv('OPENAI_API_KEY', 'FAKE-OPENAI-KEY')
    with path.open('rb') as secret:
        os.set_inheritable(secret.fileno(), True)
        code = f'''
assert 'POSTGRES_PASSWORD' not in os.environ and 'OPENAI_API_KEY' not in os.environ
try:
    os.read({secret.fileno()}, 100)
except OSError:
    print('closed')
else:
    raise AssertionError('Inherited descriptor')
'''
        assert confined_probe(code).strip() == b'closed'


@pytest.mark.parametrize('family,address', [
    ('AF_INET', ('203.0.113.1',443)),  # Reserved address: no Internet packets may be emitted.
    ('AF_INET', ('127.0.0.1',5432)),
    ('AF_INET6', ('::1',5432)),
    ('AF_UNIX', '/var/run/docker.sock'),
])
def test_all_socket_families_are_blocked_before_connection(family, address):
    code = f'''
try:
    client=socket.socket(socket.{family},socket.SOCK_STREAM)
except PermissionError:
    print('denied')
else:
    raise AssertionError('Socket creation permitted; no connection attempted')
'''
    assert confined_probe(code).strip() == b'denied'


def test_docker_socket_and_proc_cannot_be_opened_as_files():
    assert confined_probe("\nfor path in ['/proc/self/environ','/proc/1/mem','/var/run/docker.sock']:\n try:\n  open(path,'rb')\n except (PermissionError,FileNotFoundError):\n  pass\n else:\n  raise AssertionError('Unexpected access')\nprint('denied')").strip() == b'denied'


def test_new_processes_are_blocked():
    assert confined_probe("\ntry:\n os.fork()\nexcept PermissionError:\n print('denied')\nelse:\n raise AssertionError('Unexpected fork')").strip() == b'denied'


def test_ptrace_and_process_vm_access_are_blocked():
    code = "libc=ctypes.CDLL(None,use_errno=True)\nassert libc.ptrace(0,0,0,0)==-1 and ctypes.get_errno()==1\nassert libc.process_vm_readv(os.getppid(),0,0,0,0,0)==-1 and ctypes.get_errno()==1\nassert libc.kill(os.getppid(),0)==-1 and ctypes.get_errno()==1\nprint('denied')"
    assert confined_probe(code).strip() == b'denied'


def test_fcntl_cannot_arrange_asynchronous_signals_to_parent():
    code = "import fcntl\ntry:\n fcntl.fcntl(1,fcntl.F_SETOWN,os.getppid())\nexcept PermissionError:\n print('denied')\nelse:\n raise AssertionError('Unexpected descriptor control')"
    assert confined_probe(code).strip() == b'denied'


def test_filesystem_writes_and_temporary_files_blocked(tmp_path):
    path = tmp_path / 'must-not-exist'
    code = f"\ntry:\n open({str(path)!r},'wb')\nexcept PermissionError:\n print('denied')\nelse:\n raise AssertionError('Unexpected write')"
    assert confined_probe(code).strip() == b'denied'
    assert not path.exists()


def test_file_descriptors_have_a_hard_limit():
    path = str(extraction.RUNNER.parent / 'sandbox.py')
    code = f'''\nfiles=[]
try:
    for index in range(100): files.append(os.open({path!r},os.O_RDONLY))
except OSError as error:
    assert error.errno==24 and len(files)<32
    print('limited')
else:
    raise AssertionError('Unexpected descriptor capacity')
finally:
    for descriptor in files: os.close(descriptor)
'''
    assert confined_probe(code).strip() == b'limited'


def test_allowed_runtime_files_remain_read_only(tmp_path):
    path = tmp_path / 'fictitious-library-data'; path.write_text('PUBLIC FAKE DATA')
    code = f'''\nassert open({str(path)!r}).read()=='PUBLIC FAKE DATA'
try:
    open({str(path)!r},'wb')
except PermissionError:
    print('read-only')
else:
    raise AssertionError('Unexpected write to runtime')
'''
    assert confined_probe(code, library_path=str(tmp_path)).strip() == b'read-only'
    assert path.read_text() == 'PUBLIC FAKE DATA'


@pytest.mark.parametrize('operation', ['open', 'openat', 'truncate', 'ftruncate'])
def test_runtime_truncation_is_denied_and_content_preserved(tmp_path, operation):
    path = tmp_path / 'fictitious-library-data'; path.write_bytes(b'PUBLIC FAKE DATA')
    code = f'''
libc=ctypes.CDLL(None,use_errno=True)
path={os.fsencode(path)!r}
if {operation!r} == 'open':
    result=libc.open(path,os.O_RDONLY|os.O_TRUNC)
elif {operation!r} == 'openat':
    result=libc.openat(-100,path,os.O_RDONLY|os.O_TRUNC)
elif {operation!r} == 'truncate':
    result=libc.truncate(path,ctypes.c_longlong(0))
else:
    descriptor=os.open(path,os.O_RDONLY)
    result=libc.ftruncate(descriptor,ctypes.c_longlong(0))
    saved_errno=ctypes.get_errno()
    os.close(descriptor)
    ctypes.set_errno(saved_errno)
assert result == -1 and ctypes.get_errno() in (1,13)
print('denied')
'''
    assert confined_probe(code, library_path=str(tmp_path)).strip() == b'denied'
    assert path.read_bytes() == b'PUBLIC FAKE DATA'


def test_resource_limit_syscalls_are_blocked():
    # Even harmless queries/invalid pointers must hit seccomp, not just the hard rlimit.
    code = '''
libc=ctypes.CDLL(None,use_errno=True)
assert libc.setrlimit(resource.RLIMIT_CPU,None)==-1 and ctypes.get_errno()==1
assert libc.prlimit64(0,resource.RLIMIT_CPU,None,None)==-1 and ctypes.get_errno()==1
print('denied')
'''
    assert confined_probe(code).strip() == b'denied'


@pytest.mark.parametrize('failure', ['abi_two', 'seccomp_load'])
def test_runner_exits_closed_when_native_policy_installation_fails(failure):
    # Fault injection affects this disposable child only. The production policy is unchanged.
    script = f'''
import ctypes,runpy,sys
real_cdll=ctypes.CDLL
class Library:
    def __init__(self,library,name):
        self.library=library
        if {failure!r}=='abi_two' and name is None:
            actual=library.syscall
            self.syscall=lambda *args: 2 if args==(444,0,0,1) else actual(*args)
        if {failure!r}=='seccomp_load' and name=='libseccomp.so.2':
            self.seccomp_load=lambda context: -1
    def __getattr__(self,name):
        return getattr(self.library,name)
ctypes.CDLL=lambda name,*args,**kwargs: Library(real_cdll(name,*args,**kwargs),name)
sys.argv={extraction.sandbox_command(Settings(_env_file=None))[3:]!r}
runpy.run_path({str(extraction.RUNNER)!r},run_name='__main__')
'''
    with pytest.raises(extraction.ExtractionFailure, match='sandbox_unavailable'):
        extraction.exchange([sys.executable, '-I', '-S', '-c', script], b'invalid input', 5)


def test_excess_memory_is_denied_and_parent_remains_healthy():
    code = "\ntry:\n data=bytearray(600*1024*1024)\nexcept MemoryError:\n print('limited')\nelse:\n raise AssertionError('Unexpected allocation')"
    assert confined_probe(code).strip() == b'limited'
    assert confined_probe("print('healthy')").strip() == b'healthy'


@pytest.mark.parametrize('failure', ['timeout', 'output', 'crash', 'cpu'])
def test_untrusted_child_is_stopped_and_reaped(failure, monkeypatch):
    code = {'timeout': 'import time; time.sleep(10)', 'output': "os.write(1,b'x'*100000)",
            'crash': 'os._exit(9)', 'cpu': 'while True: pass'}[failure]
    if failure == 'cpu': code = '\n' + code
    real = subprocess.Popen; children = []
    def popen(*args, **kwargs):
        child = real(*args, **kwargs); children.append(child); return child
    monkeypatch.setattr(extraction.subprocess, 'Popen', popen)
    expected = {'timeout': 'timeout', 'output': 'invalid_output', 'crash': 'worker_failed', 'cpu': 'worker_failed'}[failure]
    with pytest.raises(extraction.ExtractionFailure, match=expected):
        confined_probe(code, timeout=.2 if failure == 'timeout' else 5, maximum=128)
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.parametrize('kind', ['txt', 'pdf', 'encrypted', 'malformed', 'empty'])
def test_real_isolated_extraction(tmp_path, kind):
    import pymupdf as fitz
    extension = '.txt' if kind in ['txt','empty'] else '.pdf'
    path = tmp_path / ('input' + extension)
    if kind == 'txt': path.write_bytes(b'Fictitious safe UTF-8 text.')
    elif kind == 'empty': path.write_bytes(b'')
    elif kind == 'malformed': path.write_bytes(b'%PDF-1.7\ninvalid')
    else:
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72,72),'Fictitious PDF page one.')
            pdf.new_page().insert_text((72,72),'Fictitious PDF page two.')
            options = {'encryption':fitz.PDF_ENCRYPT_AES_256,'owner_pw':'fake-owner','user_pw':'fake-reader'} if kind == 'encrypted' else {}
            path.write_bytes(pdf.tobytes(**options))
    from fastapi import HTTPException
    settings = Settings(_env_file=None)
    if kind in ['encrypted','malformed','empty']:
        with pytest.raises(HTTPException) as error:
            extraction.extract_isolated(settings,path,extension,200,1000000)
        assert error.value.status_code == 422
    else:
        pages = extraction.extract_isolated(settings,path,extension,200,1000000)
        assert 'Fictitious' in pages[0] and len(pages) == (2 if kind == 'pdf' else 1)


def test_linux_http_failures_preserve_isolation_and_api(client, app):
    app.state.settings.extraction_mode = 'sandbox'
    from tests.conftest import OTHER_KEY
    for data,name in [(b'%PDF-1.7\ninvalid','bad.pdf'), (b'','empty.txt')]:
        assert client.post('/api/v1/documents',files={'file':(name,data)}).status_code == 422
        assert client.get('/api/v1/health').status_code == 200
    assert client.post('/api/v1/documents',files={'file':('safe.txt',b'Fictitious safe text.')}).status_code == 201
    assert client.get('/api/v1/documents',headers={'X-API-Key':OTHER_KEY}).json()['total'] == 0
    assert not list(app.state.settings.storage_dir.glob('*.part'))


def test_real_output_contract_limit_kills_worker():
    with pytest.raises(extraction.ExtractionFailure, match='invalid_output'):
        confined_probe(f"os.write(1,b'x'*{contract.MAX_OUTPUT + 1})", maximum=contract.MAX_OUTPUT)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_broker_rejects_indirect_document_paths(tmp_path, kind):
    from fastapi import HTTPException
    secret = tmp_path / 'fictitious-private.txt'; secret.write_bytes(b'FAKE PRIVATE TEXT')
    indirect = tmp_path / 'generated.part'
    if kind == 'symlink': indirect.symlink_to(secret)
    else: os.link(secret, indirect)
    with pytest.raises(HTTPException) as error:
        extraction.extract_isolated(Settings(_env_file=None), indirect, '.txt', 200, 1000000)
    assert error.value.status_code == 422
    assert secret.read_bytes() == b'FAKE PRIVATE TEXT'


def test_native_crash_during_upload_does_not_kill_api(client, app, monkeypatch):
    app.state.settings.extraction_mode = 'sandbox'
    original = extraction.sandbox_command
    monkeypatch.setattr(extraction, 'sandbox_command', lambda *args: [sys.executable, '-I', '-S', '-c', 'import os; os._exit(9)'])
    assert client.post('/api/v1/documents', files={'file': ('safe.txt', b'fictitious')}).status_code == 422
    assert client.get('/api/v1/health').status_code == 200
    assert not list(app.state.settings.storage_dir.iterdir())
    monkeypatch.setattr(extraction, 'sandbox_command', original)
    assert client.post('/api/v1/documents', files={'file': ('safe.txt', b'fictitious')}).status_code == 201
