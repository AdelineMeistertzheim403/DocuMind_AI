"""Inspect local Docker-save archive metadata without extraction, loading or execution."""
import argparse
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, need, no_links, safe_name, sha, write_new


def small_member(archive, name, maximum):
    safe_name(name)
    entries = [item for item in archive.getmembers() if item.name == name]
    need(len(entries) == 1 and entries[0].isfile() and entries[0].size <= maximum,
         'Missing/duplicate/non-regular/oversized archive metadata')
    with archive.extractfile(entries[0]) as stream:
        return stream.read()


def inspect_archive(path):
    path = no_links(path)
    with tarfile.open(path, 'r:*') as archive:
        manifest = json.loads(small_member(archive, 'manifest.json', 4 * 1024**2))
        need(isinstance(manifest, list) and manifest, 'Docker-save manifest required')
        images = []
        for item in manifest:
            config_name = safe_name(item['Config'])
            raw = small_member(archive, config_name, 2 * 1024**2)
            config = json.loads(raw)
            runtime = config.get('config') or {}
            python_values = [value.split('=', 1)[1] for value in runtime.get('Env', [])
                             if value.startswith('PYTHON_VERSION=')]
            version = python_values[0] if len(python_values) == 1 else None
            image_id = 'sha256:' + sha(raw)
            if config_name.startswith('blobs/sha256/'):
                need(config_name.rsplit('/', 1)[1] == sha(raw), 'Config content address mismatch')
            elif config_name.endswith('.json') and len(config_name) == 69:
                need(config_name[:-5] == sha(raw), 'Config filename hash mismatch')
            compatible_hint = (config.get('os') == 'linux' and config.get('architecture') == 'amd64'
                               and version == '3.11.18')
            images.append({
                'image_id_from_config': image_id, 'config_sha256': sha(raw),
                'repo_tags_observed_not_trusted': item.get('RepoTags'),
                'os': config.get('os'), 'architecture': config.get('architecture'),
                'python_version_env_hint_only': version,
                'target_version_hint_matches': compatible_hint,
                'status': 'UNVERIFIED_CANDIDATE' if compatible_hint else 'NOT_A_TARGET_BASE',
                'debian13_verified': False, 'layer_diff_ids_verified': False,
                'provenance_approved': False,
                'layers': item.get('Layers'), 'rootfs_diff_ids': config.get('rootfs', {}).get('diff_ids'),
                'note': 'No layer extraction, app files, full ENV, history commands or service data read',
            })
    return {'path': str(path), 'bytes': path.stat().st_size, 'archive_sha256': digest(path),
            'images': images}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'BLOCKED', 'approved_base_image_id': None, 'archives': []}
    for path in args.archive:
        try:
            result['archives'].append(inspect_archive(path))
        except (ValueError, KeyError, tarfile.TarError, OSError) as error:
            result['archives'].append({'path': str(path), 'status': 'UNVERIFIABLE',
                                       'error': str(error), 'provenance_approved': False})
    write_new(args.out, result)


if __name__ == '__main__':
    main()
