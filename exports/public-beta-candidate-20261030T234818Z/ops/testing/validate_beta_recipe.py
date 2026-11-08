"""Explicit local-only recipe. Never use this script as a production/deployment runbook."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import queue
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.backup_local import create_backup
from tools.verify_snapshot import verify_snapshot

PASSWORD='Fictitious-public-password-123!'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('recipe',type=Path)
    parser.add_argument('--execute-local-recipe',action='store_true',required=True)
    parser.add_argument('--resume-after-desktop',action='store_true',help='Only resume the recorded one-account local test; never reset its counter')
    args=parser.parse_args()
    directory=args.recipe.resolve()
    assert directory.parent==ROOT/'var' and re.fullmatch('s14-6-recipe-[a-f0-9]{4,12}',directory.name)
    config=json.loads((directory/'recipe.json').read_text())
    compose=config['compose']; project=config['project']
    assert project=='documind-'+directory.name
    assert compose[:4]==['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine','compose']
    assert compose[-1]==str(ROOT/'compose.public-beta-test.yaml') and compose[compose.index('-p')+1]==project
    def dc(*command,check=True,input=None):
        result=subprocess.run(compose+list(command),input=input,capture_output=True,text=not isinstance(input,bytes),timeout=210)
        if check and result.returncode:raise RuntimeError('Local Compose operation failed: '+command[0])
        return result
    ids=dc('ps','-a','-q').stdout.split()
    assert len(ids)==8
    docker=compose[:3]
    metadata=json.loads(subprocess.check_output(docker+['inspect',*ids],text=True))
    for item in metadata:
        assert item['Config']['Labels']['com.docker.compose.project']==project
        assert item['Config']['Labels']['documind.test']=='sprint-14-6'
        for mount in item['Mounts']:
            if mount['Type']=='volume':assert mount['Name']==project+'_recipe_documents'
            elif mount['Type']=='bind':assert directory.name in mount['Source'] or 'traefik-public-beta-test.yaml' in mount['Source']
            else:assert mount['Type']=='tmpfs'
    evidence=json.loads((directory/'validation.json').read_text())['steps'] if args.resume_after_desktop else []
    if args.resume_after_desktop:
        assert [row['step'] for row in evidence]==['https-csrf-origin-host-and-explicit-reopen','browser-full-chain']
        assert evidence[-1]['mobile_emulated'] is False
    def record(name,**values):
        row={'step':name,**values};evidence.append(row)
        (directory/'validation.json').write_text(json.dumps({'project':project,'steps':evidence},indent=2))
        print(json.dumps(row),flush=True)
    def admin(action,execute=False,check=True):
        result=dc('exec','-T','api','python','-m','backend.account_admin','public-registration',action,
                  *(['--execute'] if execute else []),check=check)
        return json.loads(result.stdout) if result.returncode==0 else None
    def sql(statement,database='documind_beta_recipe'):
        return dc('exec','-T','db','psql','-X','-v','ON_ERROR_STOP=1','-U','documind_test','-d',database,'-At','-c',statement).stdout.strip()
    assert sql('SELECT version_num FROM alembic_version')=='0007'
    status=admin('status')
    assert (status['closed'],status['issued_count'])==((False,1) if args.resume_after_desktop else (True,0))
    cert=ssl.create_default_context(cafile=config['certificate'])
    import httpx
    with ExitStack() as stack:
        clients=[]
        for port in (19443,19444,19445):
            clients.append(stack.enter_context(httpx.Client(base_url=f'https://localhost:{port}',verify=cert,
                trust_env=False,timeout=40,headers={'Host':f'documind.test:{port}'})))
        def post(client,path,body=None,files=None):
            csrf=client.get('/bff/auth/csrf');assert csrf.status_code==200
            port=client.base_url.port
            return client.post('/bff'+path,json=body,files=files,
                headers={'X-CSRF-Token':csrf.json()['csrf_token'],'Origin':f'https://documind.test:{port}'})
        def signup(client,email):
            challenge=client.get('/bff/auth/registration-challenge');assert challenge.status_code==200
            data=challenge.json();assert data['difficulty']==12
            for value in range(1000000):
                if int.from_bytes(hashlib.sha256(f"{data['challenge']}:{value}".encode()).digest()[:3],'big')>>12==0:break
            else:raise AssertionError('Proof safety bound')
            return post(client,'/auth/register',{'email':email,'password':PASSWORD,'terms_accepted':True,
                'terms_version':'beta-test-v1','challenge':data['challenge'],'proof':str(value)})
        def mail_token(email):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                for path in (directory/'capture').glob('*.eml'):
                    message=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                    if str(message['To'])==email:
                        match=re.search(r'https://documind.test:19443/verify-email#token=([A-Za-z0-9_-]{43})',message.get_content())
                        if match:return match[1]
                threading.Event().wait(.02)
            raise AssertionError('Fictitious STARTTLS email not captured')
        a,b,c=clients
        assert a.get('/login').status_code==200 and a.get('/bff/health').status_code==200
        assert a.get('/bff/health',headers={'Host':'evil.invalid'}).status_code==404
        assert a.get('/bff/auth/options',headers={'Origin':'https://evil.invalid'}).status_code==403
        assert a.post('/bff/auth/register',json={}).status_code==403
        if not args.resume_after_desktop:
            assert signup(c,'closed@example.test').status_code==202
            assert admin('status')['issued_count']==0
            assert admin('reopen')['simulation'] is True and admin('status')['closed'] is True
            assert admin('reopen',True)['closed'] is False
            record('https-csrf-origin-host-and-explicit-reopen',schema='0007')
        def browser(email,mobile,port):
            with (directory/f'browser-{mobile}.log').open('w') as errors:
                process=subprocess.Popen(['node',str(ROOT/'tests/fixtures/public_beta_browser.mjs')],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,cwd=ROOT)
                def event():
                    result=queue.Queue()
                    threading.Thread(target=lambda:result.put(process.stdout.readline()),daemon=True).start()
                    return result.get(timeout=50).strip()
                try:
                    process.stdin.write(json.dumps({'origin':f'https://documind.test:{port}','spki':config['spki'],
                        'email':email,'password':PASSWORD,'mobile':mobile})+'\n');process.stdin.flush()
                    assert event()=='registered'
                    token=mail_token(email)
                    process.stdin.write(json.dumps({'token':token})+'\n');process.stdin.flush()
                    assert event()=='completed' and process.wait(timeout=10)==0
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
            record('browser-full-chain',mobile_emulated=mobile)
        if not args.resume_after_desktop:
            browser('desktop@example.test',False,19443)
            assert admin('close',True)['issued_count']==1
            assert signup(a,'closed-again@example.test').status_code==202
            assert admin('status')['issued_count']==1
            assert admin('reopen',True)['closed'] is False
        browser('mobile@example.test',True,19444)
        for client,email in ((a,'desktop@example.test'),(b,'mobile@example.test')):
            assert post(client,'/auth/login',{'email':email,'password':PASSWORD}).status_code==200
        document=a.get('/bff/documents').json()['items'][0]['id']
        assert a.get('/bff/documents/'+document).status_code==200
        assert b.get('/bff/documents/'+document).status_code==404
        with (directory/'fictitious.pdf').open('rb') as source:
            response=post(a,'/documents',files={'file':('fictitious.pdf',source,'application/pdf')})
        assert response.status_code==201
        pdf=response.json()['id']
        assert a.get('/bff/documents/'+pdf).status_code==200
        assert post(a,f'/documents/{pdf}/analyze',{}).status_code==201
        assert b.get('/bff/documents/'+pdf).status_code==404
        assert a.get('/bff/ai/status').json()['enabled'] is False
        assert post(a,'/ai/key',{'api_key':'sk-fictitious-never-a-real-key'}).status_code==403
        assert post(a,'/ai/key/validate',{}).status_code==403
        record('pdf-txt-sandbox-documents-owner-isolation-ai-off')
        for client,email in ((a,'third@example.test'),(b,'fourth@example.test'),(c,'fifth@example.test')):
            assert signup(client,email).status_code==202
            assert post(client,'/auth/verify-email',{'token':mail_token(email),'password':PASSWORD}).status_code==200
        assert admin('status')['issued_count']==5
        before=sql("SELECT count(*) FROM users WHERE registration_kind='public'")
        assert signup(c,'sixth@example.test').status_code==202
        assert sql("SELECT count(*) FROM users WHERE registration_kind='public'")==before=='5'
        assert sql("SELECT count(*) FROM users WHERE email='sixth@example.test'")=='0'
        assert admin('close',True)['issued_count']==5
        assert a.get('/bff/documents').status_code==200
        assert admin('reopen',True,check=False) is None
        record('five-cumulative-sixth-denied-and-emergency-close',issued_count=5,closed=True)
        db_id=dc('ps','-q','db').stdout.strip()
        dc('restart','--timeout','150','api','web')
        dc('up','-d','--no-deps','--wait','--wait-timeout','180','api','web')
        status=admin('status');assert status['issued_count']==5 and status['closed'] is True
        assert dc('ps','-q','db').stdout.strip()==db_id
        assert a.get('/bff/documents').status_code==401
        assert post(a,'/auth/login',{'email':'desktop@example.test','password':PASSWORD}).status_code==200
        assert a.get('/bff/documents').status_code==200
        # An invalid new process fails closed, without replacing the healthy application.
        failed=dc('run','--rm','--no-deps','-T','-e','EXTRACTION_MODE=invalid','--entrypoint','python','api',
                  '-c','import backend.main',check=False)
        assert failed.returncode!=0 and admin('status')['closed'] is True
        assert a.get('/bff/health').status_code==200
        record('restart-persists-quota-and-closed-startup-failure',issued_count=5,closed=True)
        dc('stop','--timeout','150','api','web')
        try:
            backup=create_backup(compose,directory/'snapshot-v2')
            manifest=json.loads((backup/'manifest.json').read_text())
            assert manifest['integrity_version']==2 and manifest['migration']=='0007'
            assert verify_snapshot(backup,'documind_beta_recipe',compose)['quota_certified']
            for name,digest in manifest['sha256'].items():assert hashlib.sha256((backup/name).read_bytes()).hexdigest()==digest
            legacy=directory/'snapshot-v1-synthetic'
            shutil.copytree(backup,legacy)
            old_manifest=json.loads((legacy/'manifest.json').read_text());old_manifest.pop('integrity_version')
            old_inventory=json.loads((legacy/'integrity.json').read_text());old_inventory.pop('public_registration_quota')
            (legacy/'manifest.json').write_text(json.dumps(old_manifest))
            (legacy/'integrity.json').write_text(json.dumps(old_inventory))
            assert not verify_snapshot(legacy,'documind_beta_recipe',compose)['quota_certified']
            record('synthetic-legacy-v1-readable-quota-not-certified')
            restored='documind_restore_s14_6_'+directory.name.rsplit('-',1)[-1]
            assert sql(f"SELECT count(*) FROM pg_database WHERE datname='{restored}'")=='0'
            sql(f'CREATE DATABASE {restored}')
            with (backup/'database.dump').open('rb') as source:
                subprocess.run(compose+['exec','-T','db','pg_restore','-U','documind_test','-d',restored,'--no-owner','--exit-on-error'],
                               stdin=source,capture_output=True,check=True,timeout=40)
            assert verify_snapshot(backup,restored,compose)['quota_certified']
            assert sql("SELECT issued_count||'|'||closed FROM public_registration_quota",restored)=='5|true'
            # Fault injection on the NEW OFFLINE COPY only: prove the sealer closes it.
            sql('UPDATE public_registration_quota SET closed=false',restored)
            # Call the existing sealer only against the independent, offline copy.
            code="from sqlalchemy import create_engine; from tools.validate_restore import seal_restored_registration; import json; e=create_engine('postgresql+psycopg://documind_test:fictitious-s14-6-only@db:5432/"+restored+"'); print(json.dumps(seal_restored_registration(e))); e.dispose()"
            docker_run=docker+['run','--rm','--pull','never','--network',project+'_data','--read-only',
                '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','512m','--pids-limit','64',
                'documind-s14-6-proofs:local','python','-c',code]
            sealed=json.loads(subprocess.check_output(docker_run,text=True,timeout=30))
            assert sealed['issued_count']==5 and sealed['closed'] is True
            assert sql("SELECT issued_count||'|'||closed FROM public_registration_quota")=='5|true'
            extracted=directory/'restored-documents';extracted.mkdir()
            with tarfile.open(backup/'documents.tar.gz') as archive:archive.extractall(extracted,filter='data')
            rows=json.loads(sql("SELECT coalesce(json_agg(json_build_object('name',storage_name,'sha256',sha256,'size',size_bytes)),'[]') FROM documents",restored))
            assert len(rows)==3
            for row in rows:
                path=(extracted/'documents'/row['name']).resolve()
                assert path.is_relative_to(extracted.resolve())
                assert path.stat().st_size==row['size'] and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
            record('backup-v2-independent-restore-and-existing-sealer',documents=len(rows),issued_count=5,closed=True)
            sql(f'DROP DATABASE {restored}')
        finally:
            dc('up','-d','--no-deps','--wait','--wait-timeout','180','api','web')
        assert a.get('/bff/health').status_code==200
        logs=dc('logs','--no-color','api','web','smtp','traefik').stdout
        for secret in (PASSWORD,'fictitious-s14-6-service-key-no-real-secret-0001',
                       'desktop@example.test','mobile@example.test'):
            assert secret not in logs
        for path in (directory/'capture').glob('*.eml'):
            message=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
            for token in re.findall('#token=([A-Za-z0-9_-]{43})',message.get_content()):assert token not in logs
        record('logs-no-account-tokens-password-or-key',status='passed')


if __name__=='__main__':main()
