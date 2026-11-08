"""Create or verify/extract only this independent materials delivery. No Docker or network."""
import argparse
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, files, manifest, need, no_links
from wheels import checked_zip

ROOT = Path(__file__).resolve().parent
ARCHIVE = 'p4-build-materials-v2.zip'


def new_destination(path):
    result = no_links(path)
    need(path.is_absolute() and not result.exists() and result.parent.is_dir(), 'New absolute destination')
    need(not result.is_relative_to(ROOT) and not any(
        p.lower() in {'release', 'releases', 'fixtures', 'artifacts', '.git', 'candidates'} for p in result.parts),
        'Protected destination')
    return result


def seal(root):
    entries = files(root)
    need(entries and 'SHA256SUMS' not in entries, 'Never overwrite a manifest')
    with (root / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as stream:
        stream.write(''.join(f'{value}  {name}\n' for name, value in entries.items()))


def pack(destination):
    manifest(ROOT, digest(ROOT / 'SHA256SUMS'))
    destination = new_destination(destination)
    destination.mkdir(mode=0o700)
    with zipfile.ZipFile(destination / ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file():
                item = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (1980, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                archive.writestr(item, path.read_bytes(), compresslevel=9)
    for name in ('transfer.py', 'common.py', 'wheels.py', 'TRANSFER.md'):
        shutil.copyfile(ROOT / name, destination / name)
    seal(destination)
    return {'archive_sha256': digest(destination / ARCHIVE),
            'transfer_sha256sums_anchor': digest(destination / 'SHA256SUMS')}


def extract(transfer, anchor, destination):
    manifest(transfer, anchor)
    destination = new_destination(destination)
    with checked_zip((transfer / ARCHIVE).read_bytes()) as archive:
        need(sum(item.file_size for item in archive.infolist()) < 128 * 1024**2, 'Unexpected delivery size')
        destination.mkdir(mode=0o700)
        for item in archive.infolist():
            path = destination / item.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(archive.read(item))
    # The archive's exact file list/hashes include all43 wheel bytes.
    manifest(destination, digest(destination / 'SHA256SUMS'))
    return {'status': 'REVIEW_ONLY_BLOCKED', 'destination': str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    make = sub.add_parser('pack')
    make.add_argument('--destination', type=Path, required=True)
    unpack = sub.add_parser('extract')
    unpack.add_argument('--transfer', type=Path, required=True)
    unpack.add_argument('--anchor', required=True)
    unpack.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = (pack(args.destination) if args.action == 'pack' else
              extract(args.transfer, args.anchor, args.destination))
    import json
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
