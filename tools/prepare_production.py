"""Validate production inputs and image pins; never configure another Traefik."""
import argparse
import json
from pathlib import Path

from dotenv import dotenv_values
try:
    from .release_manifest import validate_release, COMPONENTS
    from .public_beta_policy import validate_registration_config, PublicBetaPolicyError
except ImportError:  # Direct script execution or flat release bundle.
    from release_manifest import validate_release, COMPONENTS
    from public_beta_policy import validate_registration_config, PublicBetaPolicyError


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',required=True,type=Path,help='release.json downloaded from a successful CI run')
    parser.add_argument('--approve-public-beta',action='store_true',help='Approve preparation only; the existing SQL admission gate must stay closed')
    args=parser.parse_args()
    env=dotenv_values('.env.production')
    if env.get('ACCOUNT_BASE_URL')!='https://documind.adelinemeistertzheim.fr':
        raise SystemExit('Configure the confirmed HTTPS account origin')
    for key in ('POSTGRES_PASSWORD','BFF_SERVICE_KEY','TRAEFIK_CONTAINER'):
        if not env.get(key):raise SystemExit(f'Configure {key} locally')
    release=validate_release(json.loads(args.release.read_text(encoding='utf-8')))
    try:
        validate_registration_config(env,release['schema_revision'],args.approve_public_beta)
    except PublicBetaPolicyError as error:
        raise SystemExit(str(error)) from None
    destination=args.release.parent/'images.env'
    destination.write_text(''.join(f'{variable}={release["images"][name]}\n' for name,variable in COMPONENTS.items()),encoding='utf-8')
    print('Image pins prepared. The deployer resolves the real Traefik IP on web. No services started.')


if __name__=='__main__':main()
