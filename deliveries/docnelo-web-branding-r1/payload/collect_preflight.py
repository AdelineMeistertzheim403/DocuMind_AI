"""VPS read-only collector. Never starts containers or changes configuration."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener, HTTPSHandler

BASE_ID = 'sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019'
APP_ROOT = Path('/opt/documind-public-beta/public-beta-candidate-20261030T234818Z')
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
NAMES = ['documind-public-beta-db-1', 'documind-public-beta-api-1', 'documind-public-beta-web-1']


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('redirect_refused')


def collect(origin):
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or parsed.netloc != 'documind.adelinemeistertzheim.fr' or parsed.path not in ('', '/'):
        raise ValueError('approved_https_origin_required')
    containers = json.loads(subprocess.check_output(DOCKER + ['inspect', *NAMES], text=True))
    report = {}
    for c in containers:
        name = c['Name'].lstrip('/')
        if name not in NAMES or c['Config']['Labels'].get('com.docker.compose.project') != 'documind-public-beta':
            raise ValueError('wrong_project')
        if not c['State']['Running'] or c['State'].get('Health', {}).get('Status') != 'healthy':
            raise ValueError('healthy_services_required')
        report[name] = {'id':c['Id'], 'image_id':c['Image'], 'started_at':c['State']['StartedAt'],
                        'volumes':sorted(m['Name'] for m in c.get('Mounts', []) if m.get('Type') == 'volume')}
    web = next(c for c in containers if c['Name'].lstrip('/') == NAMES[-1])
    if web['Image'] != BASE_ID:
        raise ValueError('active_web_does_not_match_reproduced_reference')
    image = json.loads(subprocess.check_output(DOCKER + ['image', 'inspect', BASE_ID], text=True))[0]
    if (image.get('Os'), image.get('Architecture')) != ('linux', 'amd64'):
        raise ValueError('platform_mismatch')
    files = (web['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files', '').split(',')
    allowed = {'compose.public-beta.vps.yaml', 'compose.public-beta.vps.registration-gate.override.yaml'}
    if not files or any(Path(p).parent != APP_ROOT or Path(p).name not in allowed
                        or Path(p).resolve() != Path(p) or not Path(p).is_file() for p in files):
        raise ValueError('compose_provenance_requires_review')
    api = next(c for c in containers if c['Name'].lstrip('/') == NAMES[1])
    env = dict(item.split('=', 1) for item in api['Config'].get('Env', []) if '=' in item)
    opener = build_opener(NoRedirect(), HTTPSHandler())
    with opener.open(origin.rstrip('/') + '/bff/auth/options', timeout=15) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('options_response_too_large')
    options = json.loads(raw)
    mode = options.get('registration_mode')
    if mode not in {'disabled', 'invite', 'public'}:
        raise ValueError('unknown_registration_mode')
    if mode == 'public' and options.get('public_registration_availability') not in {'closed', 'full'}:
        raise ValueError('public_registration_not_closed')
    keys = ('registration_mode', 'application_profile', 'public_capacity_configured',
            'public_registration_availability', 'terms_version', 'terms_url', 'privacy_url', 'legal_notice_url')
    return {'status':'passed', 'collected_at_utc':datetime.now(timezone.utc).isoformat(),
            'origin':origin, 'reference_image_id':BASE_ID, 'platform':'linux/amd64',
            'app_root':str(APP_ROOT), 'compose_files':files, 'containers':report,
            'options':{k:options.get(k) for k in keys},
            'api_flags':{k:env.get(k) for k in ('REGISTRATION_MODE', 'APPLICATION_PROFILE', 'PUBLIC_LEGAL_READY', 'AI_ENABLED')}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://documind.adelinemeistertzheim.fr')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = collect(args.origin)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        print('{"status":"passed","read_only":true}')
    except Exception:
        # No Docker Env, response bodies or exception traceback in the terminal.
        print('{"status":"NO-GO","reason":"preflight_unconfirmed_or_mismatch; inspect_safe_metadata_manually"}')
        sys.exit(2)
