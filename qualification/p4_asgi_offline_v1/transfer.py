"""Package or verify/extract this supplement only. No dependency installation or Docker."""
import argparse
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import checked_zip, digest, files, manifest, no_links, require

ROOT = Path(__file__).resolve().parent
ARCHIVE = 'p4-asgi-offline-v1.zip'


def new_destination(path):
    path = no_links(path)
    require(path.is_absolute() and not path.exists() and path.parent.is_dir(), 'New absolute destination')
    require(not any(part.lower() in {'release', 'releases', 'fixtures', 'artifacts', '.git', 'candidates'}
                    for part in path.parts), 'Protected destination')
    require(not path.is_relative_to(ROOT), 'Never extract/package into the verified input tree')
    return path


def pack(destination):
    manifest(ROOT)
    destination = new_destination(destination)
    destination.mkdir(mode=0o700)
    with zipfile.ZipFile(destination / ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compresslevel=9)
    for name in ('offline.py', 'REFERENCES.json', 'transfer.py', 'TRANSFER.md'):
        shutil.copyfile(ROOT / name, destination / name)
    entries = files(destination)
    with (destination / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as stream:
        stream.write(''.join(f'{value}  {name}\n' for name, value in entries.items()))
    manifest(destination)
    return {'archive_sha256': digest(destination / ARCHIVE),
            'transfer_sha256sums_anchor': digest(destination / 'SHA256SUMS')}


def extract(transfer, anchor, destination):
    manifest(transfer, anchor)
    destination = new_destination(destination)
    with checked_zip((transfer / ARCHIVE).read_bytes()) as archive:
        require(sum(item.file_size for item in archive.infolist()) < 32 * 1024**2,
                'Unexpected supplement size')
        destination.mkdir(mode=0o700)
        for item in archive.infolist():
            path = destination / item.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as output:
                output.write(archive.read(item))
    manifest(destination)
    return {'extracted': str(destination), 'status': 'REVIEW_ONLY_NO_GO'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    package = sub.add_parser('pack')
    package.add_argument('--destination', type=Path, required=True)
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
