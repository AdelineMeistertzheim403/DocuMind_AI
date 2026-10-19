"""Validate production inputs and image pins; never configure another Traefik."""
import argparse
import json
from pathlib import Path

from dotenv import dotenv_values
from release_manifest import validate_release, COMPONENTS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',required=True,type=Path,help='release.json downloaded from a successful CI run')
    args=parser.parse_args()
    env=dotenv_values('.env.production')
    if env.get('ACCOUNT_BASE_URL')!='https://documind.adelinemeistertzheim.fr':
        raise SystemExit('Configure the confirmed HTTPS account origin')
    for key in ('POSTGRES_PASSWORD','BFF_SERVICE_KEY','TRAEFIK_CONTAINER'):
        if not env.get(key):raise SystemExit(f'Configure {key} locally')
    if env.get('REGISTRATION_MODE','disabled') not in ('disabled','invite'):
        raise SystemExit('Only disabled or invitation registration is allowed')
    release=validate_release(json.loads(args.release.read_text(encoding='utf-8')))
    destination=args.release.parent/'images.env'
    destination.write_text(''.join(f'{variable}={release["images"][name]}\n' for name,variable in COMPONENTS.items()),encoding='utf-8')
    print('Image pins prepared. The deployer resolves the real Traefik IP on web. No services started.')


if __name__=='__main__':main()
