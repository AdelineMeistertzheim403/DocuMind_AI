"""Execute probes and collect narrow Docker evidence without dumping env secrets."""
import json
import subprocess
import time
from run_lab import LAB,D,C,config,audit

def execute(service,program):
    result=subprocess.run(C+['exec','-T',service,'python','-B','-'],input=program,
        capture_output=True,text=True,encoding='utf-8',errors='replace')
    return result

audit()
result=execute('api',(LAB/'probe.py').read_text(encoding='utf-8'))
(LAB/'probe.log').write_text(result.stdout+result.stderr,encoding='utf-8')
print(result.stdout[-14000:]+result.stderr[-3000:])
if result.returncode:raise SystemExit(result.returncode)
proof=json.loads(result.stdout.strip().splitlines()[-1])
(LAB/'test-results.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
capture=execute('smtp',"import json;from pathlib import Path;print(json.dumps({'captured_messages':len(list(Path('/capture').glob('*.eml')))}))")
assert capture.returncode==0
(LAB/'smtp-proof.json').write_text(capture.stdout,encoding='utf-8')
assert json.loads(capture.stdout)['captured_messages']==1
print('SMTP capture:',capture.stdout)
network=json.loads(subprocess.check_output(D+['network','inspect',config['name']+'_isolated'],text=True))[0]
assert network['Internal']
records=[]
for cid in subprocess.check_output(C+['ps','-aq'],text=True).split():
    obj=json.loads(subprocess.check_output(D+['inspect',cid],text=True))[0]
    networks=list(obj['NetworkSettings']['Networks'])
    assert networks==[config['name']+'_isolated']
    mounts=[dict(type=m['Type'],source=m.get('Name',m['Source']),destination=m['Destination'],rw=m['RW']) for m in obj['Mounts']]
    records.append(dict(id=cid,image=obj['Image'],service=obj['Config']['Labels']['com.docker.compose.service'],
        networks=networks,mounts=mounts,ports=obj['NetworkSettings']['Ports'],configured_ports=obj['HostConfig']['PortBindings']))
(LAB/'runtime-isolation.json').write_text(json.dumps(dict(internal=network['Internal'],containers=records),indent=2),encoding='utf-8')
# Restart exact app and database; retain only these new laboratory volumes.
subprocess.run(C+['restart','-t','15','db','api','web'],check=True,capture_output=True)
for attempt in range(30):
    result=execute('api',"import json,urllib.request; print(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=2).read()))")
    if result.returncode==0:break
    time.sleep(1)
else:raise RuntimeError('API not healthy after lab restart')
program='''
import json
from sqlalchemy import select,func
from backend.config import Settings
from backend.db import make_engine,make_sessions
from backend.account_models import PublicRegistrationQuota,AccountToken
from backend.auth import User
s=Settings(_env_file=None)
with make_sessions(make_engine(s.database_url))() as db:
 q=db.get(PublicRegistrationQuota,'public')
 proof=dict(issued_count=q.issued_count,closed=q.closed,users=db.scalar(select(func.count()).select_from(User)),tokens=db.scalar(select(func.count()).select_from(AccountToken)))
 assert proof==dict(issued_count=0,closed=True,users=0,tokens=0)
 print(json.dumps(dict(status='PASS',scope='restart of strict blocked stack only; no admitted account',projection=proof)))
'''
result=execute('api',program)
assert result.returncode==0,result.stderr
(LAB/'restart-proof.json').write_text(result.stdout,encoding='utf-8')
print('Restart:',result.stdout)
