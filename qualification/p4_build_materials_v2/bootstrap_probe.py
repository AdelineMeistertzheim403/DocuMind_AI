"""Probe only the hash-pinned pip wheel's --version, never an installer or network."""
import argparse
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, inventory, need, no_links, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    need(sys.flags.isolated and sys.flags.dont_write_bytecode, 'Use -I -B')
    expected = next(r for r in inventory(args.inventory)['distributions']
                    if r['distribution'].lower() == 'pip')
    wheel = no_links(args.wheel)
    need(wheel.name == expected['file'] and digest(wheel) == expected['sha256'], 'pip wheel mismatch')
    output = no_links(args.out)
    violations = []

    def audit(event, values):
        forbidden = event.startswith(('socket.', 'os.exec', 'os.spawn')) or event in {
            'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
            'sqlite3.connect', 'smtplib.connect', 'http.client.connect', 'urllib.Request',
        }
        if event == 'open':
            filename, mode, flags = values
            write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if write and (isinstance(filename, int) or Path(os.fsdecode(filename)).absolute() != output):
                forbidden = True
            if not isinstance(filename, int) and Path(os.fsdecode(filename)).name in ('pip.ini', 'pip.conf'):
                forbidden = True
        if forbidden:
            violations.append(event)
            raise RuntimeError('Forbidden bootstrap probe operation: ' + event)

    os.environ.clear()
    os.environ.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    sys.addaudithook(audit)
    need('pip' not in sys.modules, 'Do not reuse an installed pip')
    sys.path.insert(0, str(wheel))
    import pip
    need(pip.__version__ == '25.2' and pip.__file__.startswith(str(wheel) + os.sep), 'Wrong pip imported')
    from pip._internal.cli.main import main as pip_main
    stdout = io.StringIO()
    code = None
    exit_kind = 'returned'
    with redirect_stdout(stdout):
        try:
            code = pip_main(['--isolated', '--disable-pip-version-check', '--no-cache-dir', '--version'])
        except SystemExit as error:
            exit_kind = 'SystemExit(' + repr(error.code) + ')'
            code = 0 if error.code is None else error.code
    need(type(code) is int and code == 0 and not violations
         and stdout.getvalue().startswith('pip 25.2 from '), 'pip version probe failed')
    write_new(output, {
        'status': 'PASS_ZIP_BOOTSTRAP_PROBE_PREPARATION_ONLY',
        'python': sys.version, 'platform': sys.platform, 'pip_version': pip.__version__,
        'pip_import_file': pip.__file__, 'wheel_sha256': digest(wheel),
        'stdout': stdout.getvalue(), 'returncode': code, 'pip_exit_kind': exit_kind,
        'forbidden_events': violations,
        'packages_installed': 0, 'target_cp311_bootstrap_qualified': False,
        'build_go': False,
    })


if __name__ == '__main__':
    main()
