"""Verify the explicitly inventoried repository histories without modifying them."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import files, load, no_links, require, safe_name, write_new


def verify(repository, baseline):
    repository = no_links(repository)
    observed = {}
    for name in baseline['scope']:
        safe_name(name)
        root = repository / name
        require(root.is_dir(), 'Historical scope missing: ' + name)
        for relative, value in files(root).items():
            observed[name + '/' + relative] = value
    require(observed == baseline['files'], 'Historical file added, removed or changed')
    return {'verdict': 'PASS_REPOSITORY_BYTES_PRESERVED', 'files': len(observed),
            'scope': baseline['scope'],
            'debian_namespaces_inspected': False, 'debian_p4_executed': False,
            'note': 'Repository bytes only, not POSIX metadata or remote Debian evidence'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, verify(args.repository, load(args.baseline)))


if __name__ == '__main__':
    main()
