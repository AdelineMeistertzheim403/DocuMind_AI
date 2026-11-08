"""Verify final isolation, strict guard after restart, then stop this lab only."""
import hashlib
import json
from pathlib import Path
import subprocess
from run_lab import LAB,C,D,config,audit,step

config['services']['proxy'].pop('ports',None)
(LAB/'compose.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
(LAB/'safety-preflight-final.json').write_text(json.dumps(audit(),indent=2),encoding='utf-8')
step('proxy-internal-only',['up','-d','proxy'])
prefix=(LAB/'probe.py').read_text(encoding='utf-8').split('# A separate synthetic message')[0]
program=prefix+'''
from backend.lifecycle_durability import require_synthetic_mutation
try:require_synthetic_mutation(settings)
except ValueError:check('durable_guard_direct_after_restart',True)
else:check('durable_guard_direct_after_restart',False)
import os
stats=[]
for path in [settings.lifecycle_registry_path,settings.lifecycle_confirmation_path,
 settings.lifecycle_authenticated_confirmation_path,settings.lifecycle_holds_path,settings.lifecycle_admission_anchor_path,
 settings.lifecycle_authentication_key_path,settings.lifecycle_admission_key_path]:
 st=os.stat(path)
 stats.append(dict(path=str(path),uid=st.st_uid,gid=st.st_gid,mode=oct(st.st_mode & 0o777)))
print(json.dumps(dict(tests=results,projection=projection(),lifecycle_permissions=stats)))
'''
result=subprocess.run(C+['exec','-T','api','python','-B','-'],input=program,capture_output=True,text=True,encoding='utf-8')
(LAB/'post-restart-probe.log').write_text(result.stdout+result.stderr,encoding='utf-8')
assert result.returncode==0,result.stderr
(LAB/'post-restart-proof.json').write_text(json.dumps(json.loads(result.stdout.strip().splitlines()[-1]),indent=2),encoding='utf-8')
network=json.loads(subprocess.check_output(D+['network','inspect',config['name']+'_isolated'],text=True))[0]
assert network['Internal']
records=[]
for cid in subprocess.check_output(C+['ps','-aq'],text=True).split():
    obj=json.loads(subprocess.check_output(D+['inspect',cid],text=True))[0]
    assert list(obj['NetworkSettings']['Networks'])==[config['name']+'_isolated']
    assert not obj['HostConfig']['PortBindings']
    mounts=[]
    for m in obj['Mounts']:
        if m['Type']=='volume':assert m['Name'].startswith(config['name']+'_')
        else:assert not m['RW']
        mounts.append(dict(type=m['Type'],source=m.get('Name',m['Source']),destination=m['Destination'],rw=m['RW']))
    # Inspect only inherited configuration names, never log environment values.
    raw=json.loads(subprocess.check_output(D+['image','inspect',obj['Image']],text=True))[0]
    env_names=[v.split('=',1)[0] for v in raw['Config'].get('Env',[])]
    suspicious=[name for name in env_names if any(word in name.upper() for word in ['PASSWORD','SECRET','TOKEN','SMTP','DATABASE_URL','API_KEY'])]
    assert not suspicious, 'Sensitive environment inherited from image: '+','.join(suspicious)
    records.append(dict(id=cid,image=obj['Image'],service=obj['Config']['Labels']['com.docker.compose.service'],
        networks=list(obj['NetworkSettings']['Networks']),mounts=mounts,ports=obj['NetworkSettings']['Ports'],
        configured_ports=obj['HostConfig']['PortBindings'],inherited_sensitive_env_names=suspicious))
(LAB/'runtime-isolation-final.json').write_text(json.dumps(dict(internal=True,containers=records),indent=2),encoding='utf-8')
subprocess.run(['git','-c','safe.directory='+str(LAB/'source').replace('\\','/'),'-C',str(LAB/'source'),'status','--porcelain'],
    check=True,stdout=(LAB/'worktree-status.txt').open('w'))
assert not (LAB/'worktree-status.txt').read_text().strip()
step('stop-lab',['stop','-t','15'])
(LAB/'final-state.json').write_text(json.dumps(dict(verdict='BLOCKED',project=config['name'],
    containers_stopped=True,loopback_relay_stopped=True,volumes_retained='synthetic lab only',
    vps_access=False,real_quota_modified=False,worktree_clean=True),indent=2),encoding='utf-8')
print('Final state: BLOCKED; strict isolated lab stopped; worktree clean')
