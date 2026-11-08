"""Read-only comparison: only Web image and pull policy may differ."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']


def check(proof_path, release):
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    manifest = json.loads((release / 'RELEASE.json').read_text(encoding='utf-8'))
    if proof.get('status') != 'passed' or proof['reference_image_id'] != manifest['reference_image_id']:
        raise ValueError('reference_unconfirmed')
    app = Path(proof['app_root'])
    base = DOCKER + ['compose', '--project-directory', str(app), '-p', 'documind-public-beta',
                     '--env-file', str(app / '.env.public-beta'), '--env-file', str(app / '.env.public-beta.images')]
    for file in proof['compose_files']:
        if Path(file).resolve() != Path(file) or Path(file).parent != app:
            raise ValueError('unsafe_compose_file')
        base += ['-f', file]
    a = json.loads(subprocess.check_output(base + ['config', '--format', 'json'], text=True))
    b = json.loads(subprocess.check_output(base + ['-f', str(release / 'web.r1.override.yaml'),
                                              'config', '--format', 'json'], text=True))
    if a.get('name') != 'documind-public-beta' or b.get('name') != a['name']:
        raise ValueError('wrong_project')
    aweb = a['services']['web'].copy()
    bweb = b['services']['web'].copy()
    for item in (aweb, bweb):
        item.pop('image', None)
        item.pop('pull_policy', None)
    if aweb != bweb:
        raise ValueError('web_configuration_changed')
    del a['services']['web']; del b['services']['web']
    if a != b:
        raise ValueError('non_web_configuration_changed')
    current = json.loads(subprocess.check_output(DOCKER + ['inspect', 'documind-public-beta-web-1'], text=True))[0]
    if current['Image'] != proof['reference_image_id'] or current['Id'] != proof['containers']['documind-public-beta-web-1']['id']:
        raise ValueError('web_changed_after_proof')
    current_files = current['Config']['Labels'].get('com.docker.compose.project.config_files', '').split(',')
    if current_files != proof['compose_files']:
        raise ValueError('compose_overrides_changed')
    env = dict(v.split('=', 1) for v in current['Config'].get('Env', []) if '=' in v)
    if any(env.get(k) != str(v) for k, v in aweb.get('environment', {}).items()):
        raise ValueError('resolved_web_environment_drift')
    expected = manifest['new_image_id']
    actual = subprocess.check_output(DOCKER + ['image', 'inspect', manifest['new_image_tag'], '--format', '{{.Id}}'], text=True).strip()
    if actual != expected:
        raise ValueError('new_image_id_mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', required=True, type=Path)
    parser.add_argument('--release', required=True, type=Path)
    args = parser.parse_args()
    try:
        check(args.proof, args.release)
        print('{"status":"passed","only_web_image_changes":true}')
    except Exception:
        print('{"status":"NO-GO","reason":"reference_or_compose_or_image_mismatch"}')
        sys.exit(2)
