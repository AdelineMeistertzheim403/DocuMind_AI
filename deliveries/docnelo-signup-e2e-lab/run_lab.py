"""Local lab only. No remote context, inherited env file, pulls or real mounts."""
import json
from pathlib import Path
import subprocess
import sys

LAB=Path(__file__).resolve().parent
D=['docker','--host','npipe:////./pipe/docker_engine']
config=json.loads((LAB/'compose.json').read_text())
project=config['name']
assert project.startswith('docnelo-signup-lab-')
C=D+['compose','--env-file',str(LAB/'empty.env'),'-p',project,'-f',str(LAB/'compose.json')]

def audit():
    assert config['networks']=={'isolated':{'internal':True,'labels':{'docnelo.lab':project}}}
    assert all(not v.get('external') and 'name' not in v for v in config['volumes'].values())
    for name,s in config['services'].items():
        assert s['image'].startswith('sha256:') and s['pull_policy']=='never'
        assert s['networks']==['isolated']
        assert not s.get('privileged') and not s.get('env_file')
        assert not s.get('network_mode') and not s.get('devices')
        assert s.get('ports',[])==[]
        for mount in s.get('volumes',[]):
            source=mount.split(':')[0]
            if source.startswith('./'):
                resolved=(LAB/source).resolve()
                assert resolved.is_relative_to(LAB) and resolved.exists()
                assert mount.endswith(':ro')
            else:
                assert source in config['volumes']
        env=s.get('environment',{})
        if 'DATABASE_URL' in env:
            assert env['DATABASE_URL']=='postgresql+psycopg://synthetic:lab-only-password@db:5432/synthetic'
            assert env['LIFECYCLE_DURABLE_RECEIPTS_REQUIRED']=='true'
            assert env['LIFECYCLE_SYNTHETIC_MUTATIONS_ENABLED']=='false'
            assert env['SMTP_HOST']=='smtp' and env['PUBLIC_REGISTRATION_LIMIT']=='5'
    return dict(passed=True,project=project,internal_network=True,immutable_images=True,
        new_volumes_only=True,real_env_files=False,real_credentials=False,loopback_only=True,
        durable_receipts_required=True,synthetic_mutations_enabled=False)

def step(name,args):
    result=subprocess.run(C+args,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (LAB/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    print(name,result.returncode,(result.stdout+result.stderr)[-1800:],flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)

if __name__=='__main__':
    (LAB/'safety-preflight.json').write_text(json.dumps(audit(),indent=2),encoding='utf-8')
    # Ensure no same-name project resources exist on first launch.
    for resource in ('volume','network','container'):
        existing=subprocess.check_output(D+[resource,'ls','-q','--filter',f'label=com.docker.compose.project={project}'],text=True)
        assert not existing.strip(), 'Refuse to reuse project resources'
    step('compose-validation',['config','--quiet'])
    step('dependencies-up',['up','-d','db','smtp','legal'])
    step('migration',['run','--rm','migrate'])
    step('lifecycle-init',['run','--rm','lifecycle-init'])
    step('application-up',['up','-d','api','web','proxy'])
