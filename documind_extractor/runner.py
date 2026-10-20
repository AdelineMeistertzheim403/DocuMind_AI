"""Fixed entrypoint: python -I -S runner.py; no application imports or startup hooks."""
import json
from pathlib import Path
import sys
import sysconfig

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import confine, SandboxUnavailable
from contract import MAX_HEADER, MAX_INPUT, MAX_OUTPUT, decode, validate_request


def main():
    job = None
    try:
        # Trusted CLI arguments, never supplied by document metadata or original filename.
        if len(sys.argv) not in (4, 5): return 1
        memory, timeout = int(sys.argv[1]), float(sys.argv[2])
        site = sys.argv[3]  # Interpreter library directory from the trusted broker, never input metadata.
        confine(memory, timeout, library_path=site)
        sys.path.append(site)
        from engine import extract
        if len(sys.argv) == 5:
            if sys.argv[4] != '--check': return 1
            extract(b'ready', '.txt', 1, 10)  # Imports the native library under the real policy.
            sys.stdout.write('{"status":"ready"}')
            return 0
        size = int.from_bytes(sys.stdin.buffer.read(4), 'big')
        if not 1 <= size <= MAX_HEADER: return 1
        header = sys.stdin.buffer.read(size)
        request = validate_request(decode(header))
        job = request['job_id']
        data = sys.stdin.buffer.read(min(MAX_INPUT, request['size']) + 1)
        if len(data) != request['size']: raise ValueError()
        pages = extract(data, request['extension'], request['max_pages'], request['max_chars'])
        value = {'version': 1, 'job_id': job, 'pages': pages}
    except SandboxUnavailable:
        return 78  # Never fall back to unconfined extraction.
    except MemoryError:
        value = {'version': 1, 'job_id': job, 'error': 'resource_limit'}
    except Exception:
        value = {'version': 1, 'job_id': job, 'error': 'invalid_document'}
    if job is None: return 1
    try:
        output = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(output) > MAX_OUTPUT: return 1
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
