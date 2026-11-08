"""Read-only check after Web update/rollback; prove DB and API did not restart."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import build_opener, HTTPSHandler
from collect_preflight import NoRedirect


def verify(proof, expected_web_id):
    names = list(proof['containers'])
    containers = json.loads(subprocess.check_output(
        ['docker', '--host', 'unix:///var/run/docker.sock', 'inspect', *names], text=True))
    for c in containers:
        name = c['Name'].lstrip('/')
        if not c['State']['Running'] or c['State'].get('Health', {}).get('Status') != 'healthy':
            raise ValueError('services_not_healthy')
        old = proof['containers'][name]
        if name.endswith('-web-1'):
            if c['Image'] != expected_web_id:
                raise ValueError('wrong_web_image')
        elif (c['Id'], c['Image'], c['State']['StartedAt']) != (old['id'], old['image_id'], old['started_at']):
            raise ValueError('api_or_db_restarted')
        if sorted(m['Name'] for m in c.get('Mounts', []) if m.get('Type') == 'volume') != old['volumes']:
            raise ValueError('volume_mapping_changed')
    with build_opener(NoRedirect(), HTTPSHandler()).open(proof['origin'].rstrip('/') + '/bff/auth/options', timeout=15) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('options_response_too_large')
    options = json.loads(raw)
    for key in ('registration_mode', 'application_profile', 'terms_version', 'terms_url', 'privacy_url', 'legal_notice_url'):
        if options.get(key) != proof['options'].get(key):
            raise ValueError('registration_or_legal_contract_changed')
    if options.get('registration_mode') == 'public' and options.get('public_registration_availability') not in {'closed', 'full'}:
        raise ValueError('public_registration_opened')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--expected-web-id', required=True)
    args = parser.parse_args()
    try:
        verify(json.loads(args.proof.read_text(encoding='utf-8')), args.expected_web_id)
        print('{"status":"passed","db_api_unchanged":true,"registration_and_legal_contracts_preserved":true}')
    except Exception:
        print('{"status":"NO-GO","reason":"health_or_identity_or_contract_mismatch"}')
        sys.exit(2)
