"""Package only this B1 review supplement. No Docker, network, rootfs or image extraction."""
import argparse
import io
from pathlib import Path
import shutil
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, files, manifest, need, no_links, safe_name

ROOT = Path(__file__).resolve().parent
ARCHIVE = 'p4-b1-consolidation-20261103.zip'


def destination(path):
    need(path.is_absolute(), 'New absolute destination required')
    path = no_links(path)
    need(not path.exists() and path.parent.is_dir(), 'New absolute destination required')
    need(not path.is_relative_to(ROOT) and not any(p.lower() in {
        '.git', 'candidates', 'release', 'releases', 'fixtures', 'artifacts'} for p in path.parts),
        'Protected destination')
    return path


def checked_zip(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    seen = set()
    for item in archive.infolist():
        safe_name(item.filename)
        need(item.filename == item.orig_filename and item.filename not in seen and not item.is_dir()
             and not item.flag_bits & 1 and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG),
             'Unsafe ZIP member')
        seen.add(item.filename)
    need(sum(item.file_size for item in archive.infolist()) < 16 * 1024**2, 'Unexpected supplement size')
    return archive


def seal(root):
    values = files(root)
    need(values and 'SHA256SUMS' not in values, 'Never overwrite a seal')
    with (root / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as stream:
        stream.write(''.join(f'{value}  {name}\n' for name, value in values.items()))


def pack(target):
    manifest(ROOT, digest(ROOT / 'SHA256SUMS'))
    target = destination(target)
    target.mkdir(mode=0o700)
    with zipfile.ZipFile(target / ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files(ROOT):
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, (ROOT / name).read_bytes())
    for name in ('transfer.py', 'common.py', 'TRANSFER.md'):
        shutil.copyfile(ROOT / name, target / name)
    seal(target)
    return {'archive_sha256': digest(target / ARCHIVE),
            'source_sha256sums_anchor': digest(ROOT / 'SHA256SUMS'),
            'delivery_sha256sums_anchor': digest(target / 'SHA256SUMS')}


def extract(delivery, anchor, target):
    manifest(delivery, anchor)
    target = destination(target)
    with checked_zip((delivery / ARCHIVE).read_bytes()) as archive:
        target.mkdir(mode=0o700)
        for item in archive.infolist():
            path = target / item.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(archive.read(item))
    manifest(target, digest(target / 'SHA256SUMS'))
    return {'status': 'REVIEW_ONLY_BLOCKED', 'destination': str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    make = sub.add_parser('pack')
    make.add_argument('--destination', type=Path, required=True)
    unpack = sub.add_parser('extract')
    unpack.add_argument('--delivery', type=Path, required=True)
    unpack.add_argument('--anchor', required=True)
    unpack.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = pack(args.destination) if args.action == 'pack' else extract(
        args.delivery, args.anchor, args.destination)
    import json
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
