"""Offline primitives for the independent, review-only P4 materials package."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

INVENTORY_SHA256 = '60f0d9f0b668409bba75914b5ef40027036c54ac69de96b05b8e813032813c20'
V1_SUMS_SHA256 = '389f070088a0f56d626ebe04a8dbce686e253522a438f1950bdccd4bf0e8f1d1'
R3_SUMS_SHA256 = '5f3cc1598423107c5616d630d63d31b849b939cbd9f3ce9ce25fc0bf3440f8d4'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='ascii'), object_pairs_hook=unique)


def safe_name(name):
    need(isinstance(name, str) and name and '\\' not in name and ':' not in name
         and not PurePosixPath(name).is_absolute()
         and all(part not in ('', '.', '..') for part in name.split('/'))
         and all(32 <= ord(char) < 127 for char in name), 'Unsafe relative name')
    return name


def no_links(path):
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path refused')
    return path


def write_new(path, value):
    path = no_links(path)
    need(path.parent.is_dir(), 'Output parent must already exist')
    with path.open('x', encoding='ascii', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write('\n')


def files(root, exclude=()):
    root = no_links(root)
    need(root.is_dir(), 'Directory required')
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink() and (path.is_dir() or path.is_file()), 'Special inventory object')
        if path.is_file():
            name = safe_name(path.relative_to(root).as_posix())
            if name not in exclude:
                result[name] = digest(path)
    return result


def manifest(root, anchor):
    root = no_links(root)
    need(re.fullmatch('[a-f0-9]{64}', anchor) and digest(root / 'SHA256SUMS') == anchor,
         'Manifest anchor mismatch')
    expected = {}
    for line in (root / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        need(match is not None, 'Malformed SHA256SUMS')
        value, name = match.groups()
        safe_name(name)
        need(name not in expected and name != 'SHA256SUMS', 'Duplicate/self manifest entry')
        expected[name] = value
    need(expected and files(root, ('SHA256SUMS',)) == expected, 'Exact manifest mismatch')
    return expected


def inventory(path):
    need(digest(path) == INVENTORY_SHA256, 'P4 v1 / Debian inventory anchor mismatch')
    value = load(path)
    need(value['status'] == 'OBSERVED_NOT_APPROVED' and value['build_go'] is False
         and value['binary_closure_approved'] is False
         and len(value['distributions']) == 43 and not value['metadata_closure_errors'],
         'Unexpected frozen inventory state')
    return value


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    check = sub.add_parser('verify')
    check.add_argument('root', type=Path)
    check.add_argument('--anchor', required=True)
    seal = sub.add_parser('seal')
    seal.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        manifest(args.root, args.anchor)
    else:
        values = files(args.root)
        need(values and 'SHA256SUMS' not in values, 'Never overwrite a seal')
        with (args.root / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as stream:
            stream.write(''.join(f'{value}  {name}\n' for name, value in values.items()))
    print('REVIEW_ONLY; no build/create/start authorization')


if __name__ == '__main__':
    main()
