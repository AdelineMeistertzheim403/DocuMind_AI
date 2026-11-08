"""Verify exact scoped historical bytes; never alters or recreates historical evidence."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import files, load, need, safe_name, write_new


def verify(repository, baseline):
    observed = {}
    for name in baseline['scope']:
        safe_name(name)
        for relative, value in files(repository / name).items():
            observed[name + '/' + relative] = value
    need(observed == baseline['files'], 'Historical file added, removed or changed')
    return {'status': 'PASS_SCOPED_REPOSITORY_BYTES_UNCHANGED', 'files': len(observed),
            'scope': baseline['scope'], 'remote_debian_evidence_accessed': False,
            'posix_metadata_qualified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, verify(args.repository, load(args.baseline)))


if __name__ == '__main__':
    main()
