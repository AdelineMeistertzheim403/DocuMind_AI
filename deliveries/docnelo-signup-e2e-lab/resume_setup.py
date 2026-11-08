"""Repair the laboratory's read-only PostgreSQL socket and wait for readiness."""
import json
from run_lab import LAB, C, config, step, audit

config['services']['db']['tmpfs'].append('/var/run/postgresql:uid=70,gid=70,mode=0700')
config['services']['db']['volumes']=['database_retry:/var/lib/postgresql/data']
config['volumes']['database_retry']={'labels':{'docnelo.lab':config['name']}}
config['services']['migrate']['depends_on']={'db':{'condition':'service_healthy'}}
(LAB/'compose.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
(LAB/'safety-preflight-retry.json').write_text(json.dumps(audit(),indent=2),encoding='utf-8')
step('dependencies-up-retry',['up','-d','db'])
step('migration-retry',['run','--rm','migrate'])
step('lifecycle-init',['run','--rm','lifecycle-init'])
step('application-up',['up','-d','api','web','proxy'])
