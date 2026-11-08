"""DEFERRED operator capture. No command is run unless explicitly passed after --."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import digest, no_links, require, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    require(command and args.timeout > 0, 'Explicit bounded command required')
    out = no_links(args.out)
    require(out.is_absolute() and not out.exists() and out.parent.is_dir(), 'New absolute capture directory')
    out.mkdir(mode=0o700)
    receipt = {'argv': command, 'start_ns': time.time_ns(), 'monotonic_start_ns': time.monotonic_ns(),
               'uid': os.geteuid() if hasattr(os, 'geteuid') else None,
               'gid': os.getegid() if hasattr(os, 'getegid') else None,
               'groups': os.getgroups() if hasattr(os, 'getgroups') else None,
               'returncode': None, 'complete': False}
    write_new(out / 'started.json', receipt)
    code = 125
    try:
        with (out / 'stdout').open('xb') as stdout, (out / 'stderr').open('xb') as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            try:
                code = process.wait(timeout=args.timeout)
                receipt.update(returncode=code, complete=True)
            except BaseException:
                process.kill()
                process.wait()
                raise
    except BaseException as error:
        receipt['capture_error'] = type(error).__name__ + ': ' + str(error)
    finally:
        receipt.update(end_ns=time.time_ns(), monotonic_end_ns=time.monotonic_ns())
        receipt['sha256'] = {name: digest(out / name) for name in ('stdout', 'stderr')
                             if (out / name).is_file()}
        write_new(out / 'receipt.json', receipt)
    # A refused command remains nonzero, including a negative test expected by an operator.
    sys.exit(code if receipt['complete'] and 0 <= code <= 255 else 125)


if __name__ == '__main__':
    main()
