"""Refuse accidental reuse of a SHA tag. Docker handles the registry authentication scheme."""
import os
import re
import subprocess


def main():
    sha=os.environ['RELEASE_SHA']
    if not re.fullmatch(r'[a-f0-9]{40}',sha):raise SystemExit('Invalid release SHA')
    for name in ('backend','frontend','postgres'):
        result=subprocess.run(['docker','buildx','imagetools','inspect',
            f'registry.adelinemeistertzheim.fr/documind-ai/{name}:sha-{sha}'],capture_output=True,text=True)
        if result.returncode==0:
            raise SystemExit('A release tag already exists; it will not be overwritten. Use its existing release artifact.')
        if not any(message in result.stderr.lower() for message in ('manifest unknown','not found','404')):
            raise SystemExit('Registry verification failed; check authentication and TLS. Nothing published.')


if __name__=='__main__':main()
