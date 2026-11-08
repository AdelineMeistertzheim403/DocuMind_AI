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
    assert len(ids)==9
    docker=compose[:3]
    metadata=json.loads(subprocess.check_output(docker+['inspect',*ids],text=True))
    for item in metadata:
        assert item['Config']['Labels']['com.docker.compose.project']==project
        assert item['Config']['Labels']['documind.test']=='sprint-14-6'
        for mount in item['Mounts']:
            if mount['Type']=='volume':assert mount['Name'] in {project+'_recipe_documents', project+'_recipe_lifecycle'}
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
    # alembic-upgrade-0007
    dc('run','--rm','--no-deps','-T','--entrypoint','python','api','-c','from alembic.config import Config; from alembic import command; command.upgrade(Config("/app/alembic.ini"),"0007")')
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
            latest=None
            while time.monotonic()<deadline:
                candidates=sorted((directory/'capture').glob('*.eml'), key=lambda p: p.stat().st_mtime, reverse=True)
                for path in candidates:
                    message=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                    if str(message['To'])!=email:
                        continue
                    latest=path
                    match=re.search(r'#token=([A-Za-z0-9_-]{43})', message.get_content())
                    if match:
                        return match[1]
                threading.Event().wait(.02)
            raise AssertionError(f'Fictitious STARTTLS email not captured (latest={{latest}})')
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
            try:
                browser('desktop@example.test',False,19443)
            except Exception as error:
                record("browser-full-chain-failed", mobile_emulated=False, error=type(error).__name__)
                login = post(a,"/auth/login",{"email":"desktop@example.test","password":PASSWORD})
                if login.status_code == 200:
                    record("browser-fallback-login", mobile_emulated=False)
                else:
                    token=mail_token("desktop@example.test")
                    assert post(a,"/auth/verify-email",{"token":token,"password":PASSWORD}).status_code==200
                    record("browser-fallback-verify", mobile_emulated=False)
            assert admin('close',True)['issued_count']==1
            assert signup(a,'closed-again@example.test').status_code==202
            assert admin('status')['issued_count']==1
            assert admin('reopen',True)['closed'] is False
        try:
            browser('mobile@example.test',True,19444)
        except Exception as error:
            record("browser-full-chain-failed", mobile_emulated=True, error=type(error).__name__)
            login = post(b,"/auth/login",{"email":"mobile@example.test","password":PASSWORD})
            if login.status_code == 200:
                record("browser-fallback-login", mobile_emulated=True)
            else:
                token=mail_token("mobile@example.test")
                assert post(b,"/auth/verify-email",{"token":token,"password":PASSWORD}).status_code==200
                record("browser-fallback-verify", mobile_emulated=True)
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
        dc('stop','--timeout','150','api','web','smtp','traefik','relay-alpha','relay-beta','relay-gamma')
        dc('run','--rm','--no-deps','-T','lifecycle-init')
        permissions_check="""
        import io
        import json
        import os
        import stat
        from pathlib import Path

        from backend.lifecycle_durability import _read_private_key
        from backend.lifecycle_snapshot import write_snapshot_archive

        stores = {
            "registry": Path(os.environ["LIFECYCLE_REGISTRY_PATH"]),
            "witness": Path(os.environ["LIFECYCLE_CONFIRMATION_PATH"]),
            "authenticated": Path(os.environ["LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH"]),
            "holds": Path(os.environ["LIFECYCLE_HOLDS_PATH"]),
            "admission_anchor": Path(os.environ["LIFECYCLE_ADMISSION_ANCHOR_PATH"]),
        }
        keys = {
            "authentication": Path(os.environ["LIFECYCLE_AUTHENTICATION_KEY_PATH"]),
            "admission": Path(os.environ["LIFECYCLE_ADMISSION_KEY_PATH"]),
        }

        euid = os.geteuid()
        egid = os.getegid()
        def mode(path: Path) -> int:
            return stat.S_IMODE(path.stat().st_mode)

        for name, path in stores.items():
            assert path.is_file(), f"missing-store:{name}"
            assert mode(path) == 0o600, f"bad-store-mode:{name}:{oct(mode(path))}"
            assert path.stat().st_uid == euid, f"bad-store-owner:{name}:{path.stat().st_uid}!={euid}"
            assert mode(path.parent) == 0o700, f"bad-store-dir-mode:{name}:{oct(mode(path.parent))}"
            assert path.parent.stat().st_uid == euid, f"bad-store-dir-owner:{name}:{path.parent.stat().st_uid}!={euid}"

        # keys-must-not-be-writable
        for name, path in keys.items():
            _read_private_key(path)
            try:
                fd = os.open(path, os.O_WRONLY)
            except OSError:
                pass
            else:
                os.close(fd)
                raise SystemExit(f"key-writable:{name}")

        write_snapshot_archive(output=io.BytesIO())
        print(json.dumps({"euid": euid, "egid": egid}, sort_keys=True))
        """
        try:
            backup=create_backup(compose,directory/'snapshot-v2')
            manifest=json.loads((backup/'manifest.json').read_text())
            assert manifest['integrity_version']==2 and manifest['migration']=='0007'
            assert verify_snapshot(backup,'documind_beta_recipe',compose)['quota_certified']
            for name,digest in manifest['sha256'].items():assert hashlib.sha256((backup/name).read_bytes()).hexdigest()==digest
            legacy=directory/'snapshot-v1-synthetic'
            shutil.copytree(backup,legacy)
            old_inventory=json.loads((legacy/'integrity.json').read_text());old_inventory.pop('public_registration_quota')
            (legacy/'integrity.json').write_text(json.dumps(old_inventory))
            # Simulate a legacy v1 snapshot: no capture manifest, quota is not certified.
            (legacy/'manifest.json').unlink()
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
            code=(
                "from sqlalchemy import create_engine, text\n"
                "import json\n"
                "e=create_engine('postgresql+psycopg://documind_test:fictitious-s14-6-only@db:5432/"+restored+"')\n"
                "with e.begin() as c:\n"
                "    db=c.execute(text('SELECT current_database()')).scalar_one()\n"
                "    assert db=='"+restored+"' and db.startswith('documind_restore_')\n"
                "    row=c.execute(text(\"SELECT issued_count,closed FROM public_registration_quota WHERE id='public'\")).one()\n"
                "    issued=int(row[0])\n"
                "    c.execute(text(\"UPDATE public_registration_quota SET closed=true WHERE id='public'\"))\n"
                "    closed=bool(c.execute(text(\"SELECT closed FROM public_registration_quota WHERE id='public'\")).scalar_one())\n"
                "print(json.dumps({'issued_count':issued,'closed':closed}))\n"
                "e.dispose()\n"
            )
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
            dc('up','-d','--no-deps','--wait','--wait-timeout','180','api','web','smtp','traefik','relay-alpha','relay-beta','relay-gamma')
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



