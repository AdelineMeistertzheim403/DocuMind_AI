"""Trusted broker: bounded pipes, isolated exec, strict output and guaranteed reaping."""
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import sysconfig
import time
from uuid import uuid4

from fastapi import HTTPException

from documind_extractor import contract

RUNNER = Path(__file__).resolve().parents[2] / 'documind_extractor' / 'runner.py'


class ExtractionFailure(Exception):
    pass


def sandbox_command(settings, check=False):
    if sys.platform != 'linux': raise ExtractionFailure('sandbox_unavailable')
    return [sys.executable, '-I', '-S', str(RUNNER), str(min(settings.worker_memory_mb, 512)),
            str(min(settings.worker_timeout_seconds, 30)), sysconfig.get_path('purelib'),
            *(['--check'] if check else [])]


def exchange(command, payload, timeout, maximum=contract.MAX_OUTPUT):
    """Nonblocking I/O prevents an untrusted stdout from growing memory without bound."""
    process = None
    try:
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, cwd=str(RUNNER.parent))
        output = bytearray(); sent = 0
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            if payload: selector.register(process.stdin, selectors.EVENT_WRITE)
            else: process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise ExtractionFailure('timeout')
                for key, event in selector.select(min(remaining, .1)):
                    if event & selectors.EVENT_WRITE:
                        try: sent += os.write(key.fileobj.fileno(), memoryview(payload)[sent:sent + 65536])
                        except BrokenPipeError:
                            selector.unregister(key.fileobj); key.fileobj.close(); continue
                        if sent == len(payload):
                            selector.unregister(key.fileobj); key.fileobj.close()
                    else:
                        data = os.read(key.fileobj.fileno(), min(65536, maximum + 1 - len(output)))
                        if not data:
                            selector.unregister(key.fileobj)
                        else:
                            output.extend(data)
                            if len(output) > maximum: raise ExtractionFailure('invalid_output')
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ExtractionFailure('timeout')
            code = process.wait(timeout=remaining)
        if code == 78: raise ExtractionFailure('sandbox_unavailable')
        if code != 0: raise ExtractionFailure('worker_failed')
        return bytes(output)
    except (OSError, subprocess.SubprocessError):
        raise ExtractionFailure('worker_failed') from None
    finally:
        if process is not None:
            # The runner cannot fork after seccomp. Also reap its whole group on failures
            # before policy installation; never signal an unrelated process/group.
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream and not stream.closed: stream.close()


def check_available(settings):
    try:
        result = exchange(sandbox_command(settings, check=True), b'', min(settings.worker_timeout_seconds, 5), 128)
        if contract.decode(result) != {'status': 'ready'}: raise ExtractionFailure('sandbox_unavailable')
    except Exception:
        raise RuntimeError('Confinement Linux indisponible : extraction non autorisée') from None


def extract_isolated(settings, path, extension, max_pages, max_chars):
    try:
        # Only the trusted API opens its generated temporary file. No path enters the child protocol.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as source:
            attributes = os.fstat(source.fileno())
            if not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1:
                raise ExtractionFailure('invalid_document')
            data = source.read(min(settings.max_upload_bytes, contract.MAX_INPUT) + 1)
        if len(data) > min(settings.max_upload_bytes, contract.MAX_INPUT):
            raise HTTPException(413, 'Fichier trop volumineux pour une extraction confinée')
        request = contract.validate_request({'version': 1, 'job_id': uuid4().hex, 'extension': extension,
            'size': len(data), 'max_pages': min(max_pages, contract.MAX_PAGES),
            'max_chars': min(max_chars, contract.MAX_CHARS)})
        header = json.dumps(request, separators=(',', ':')).encode('utf-8')
        payload = len(header).to_bytes(4, 'big') + header + data
        raw = exchange(sandbox_command(settings), payload, min(settings.worker_timeout_seconds, 30))
        result = contract.validate_response(contract.decode(raw), request)
        if 'error' in result: raise ExtractionFailure(result['error'])
        return result['pages']
    except HTTPException:
        raise
    except ExtractionFailure as error:
        if str(error) in {'sandbox_unavailable', 'worker_failed', 'invalid_output'}:
            from ..security_audit import mark
            mark('system.worker.failed', 'worker_failed')
        if str(error) == 'sandbox_unavailable':
            raise HTTPException(503, 'Extraction confinée indisponible') from None
        raise HTTPException(422, 'Document illisible ou limite de traitement atteinte') from None
    except Exception:
        raise HTTPException(422, 'Réponse ou document d’extraction invalide') from None
