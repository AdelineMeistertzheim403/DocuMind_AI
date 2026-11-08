"""Opt-in actual browser/HTTPS/BFF/FastAPI/PostgreSQL/SMTP integration, fictitious data only.

Requires an empty dedicated TEST_DATABASE_URL, TEST_PUBLIC_BETA_E2E=1, local Node,
cached Playwright Chromium, OpenSSL and `npm run build`. Never starts Docker itself.
"""
import base64
import hashlib
import json
import os
import queue
import re
import socket
import ssl
import subprocess
import threading
import time
from datetime import timedelta
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy import select

from backend.config import Settings
from backend.main import create_app
from backend.account_models import AccountToken, PublicRegistrationQuota
from backend.auth import User
from backend.models import now
from tests.conftest import BFF_KEY
from tests.fake_smtp import FakeSMTP, mail_certificate
from tests.test_public_beta import PUBLIC, PASSWORD, proof
from tests.test_security_audit import records

pytestmark=pytest.mark.skipif(os.environ.get('TEST_PUBLIC_BETA_E2E')!='1',
                            reason='Opt-in disposable PostgreSQL + local browser integration')
ROOT=Path(__file__).resolve().parents[1]


def line_with_deadline(process, seconds=35):
    result=queue.Queue()
    threading.Thread(target=lambda:result.put(process.stdout.readline()),daemon=True).start()
    line=result.get(timeout=seconds)
    assert line, 'Local test process exited before the expected event'
    return line.strip()


@contextmanager
def application_server(application):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(64)
    server=uvicorn.Server(uvicorn.Config(application,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:
            threading.Event().wait(.01)
        assert server.started, 'Local API failed to start'
        yield f'http://127.0.0.1:{sock.getsockname()[1]}'
    finally:
        server.should_exit=True;thread.join(15);sock.close()
        assert not thread.is_alive(), 'Local API failed to stop'


@pytest.mark.parametrize('mobile',[False,True],ids=['desktop','mobile-emulation'])
def test_browser_signup_smtp_verify_login_document_and_ai_denied(app,mail_certificate,monkeypatch,tmp_path,mobile):
    assert app.state.engine.dialect.name=='postgresql', 'Only an empty disposable PostgreSQL DB is allowed'
    assert (ROOT/'frontend/dist/index.html').is_file(), 'Build frontend before integration'
    cert,key=mail_certificate
    original=ssl.create_default_context
    monkeypatch.setattr('backend.account_api.ssl.create_default_context',lambda:original(cafile=str(cert)))
    with FakeSMTP(mail_certificate,starttls=True) as smtp:
        settings=Settings(_env_file=None,**{**app.state.settings.model_dump(),**PUBLIC,
            'public_registration_limit':5,'public_registration_per_hour':3,'public_challenge_difficulty':12,
            'ai_enabled':False,'smtp_host':'127.0.0.1','smtp_port':smtp.port,'smtp_starttls':True,
            'account_base_url':'https://localhost','storage_dir':tmp_path/'documents'})
        application=create_app(settings)
        with application_server(application) as api:
            gateway_log=tmp_path/'gateway-errors.log'
            with gateway_log.open('w',encoding='utf-8') as errors:
                gateway=subprocess.Popen(['node',str(ROOT/'tests/fixtures/public_beta_gateway.mjs')],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,cwd=ROOT)
                browser=None
                try:
                    gateway.stdin.write(json.dumps({'api':api,'key':BFF_KEY,'certificate':str(cert),'privateKey':str(key)}))
                    gateway.stdin.close()
                    origin=json.loads(line_with_deadline(gateway))['origin']
                    # Bind links to this ephemeral HTTPS origin before issuing any token.
                    settings.account_base_url=origin
                    with httpx.Client(base_url=origin,verify=original(cafile=str(cert)),trust_env=False,timeout=10) as http:
                        assert http.get('/bff/health').status_code==200
                        assert http.post('/bff/auth/register',json={}).status_code==403  # CSRF
                        assert http.get('/bff/auth/options',headers={'Origin':'https://evil.invalid'}).status_code==403
                    openssl='C:/Program Files/Git/usr/bin/openssl.exe' if os.name=='nt' else 'openssl'
                    public=subprocess.run([openssl,'x509','-in',str(cert),'-pubkey','-noout'],capture_output=True,check=True,timeout=5).stdout
                    der=subprocess.run([openssl,'pkey','-pubin','-outform','DER'],input=public,capture_output=True,check=True,timeout=5).stdout
                    spki=base64.b64encode(hashlib.sha256(der).digest()).decode()
                    browser=subprocess.Popen(['node',str(ROOT/'tests/fixtures/public_beta_browser.mjs')],
                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,cwd=ROOT)
                    browser.stdin.write(json.dumps({'origin':origin,'spki':spki,'mobile':mobile,'password':PASSWORD})+'\n');browser.stdin.flush()
                    assert line_with_deadline(browser)=='registered'
                    raw=smtp.messages.get(timeout=10)
                    message=BytesParser(policy=policy.default).parsebytes(raw)
                    assert str(message['To'])=='browser@example.test'
                    token=re.search(r'#token=([A-Za-z0-9_-]{43})',message.get_content()).group(1)
                    browser.stdin.write(json.dumps({'token':token})+'\n');browser.stdin.flush()
                    assert line_with_deadline(browser)=='completed'
                    assert browser.wait(timeout=10)==0
                    assert smtp.tls_connections==1
                    # Events and safe diagnostics only; stdout must contain no credentials/tokens.
                    gateway.terminate();gateway.wait(timeout=10)
                    output=gateway.stdout.read()+gateway_log.read_text(encoding='utf-8')
                    for secret in (token,PASSWORD,BFF_KEY,'browser@example.test'):
                        assert secret not in output
                finally:
                    for process in (browser,gateway):
                        if process and process.poll() is None:
                            process.terminate();process.wait(timeout=10)


@pytest.fixture
def live_beta(app,mail_certificate,monkeypatch,tmp_path):
    assert app.state.engine.dialect.name=='postgresql'
    cert,key=mail_certificate
    original=ssl.create_default_context
    monkeypatch.setattr('backend.account_api.ssl.create_default_context',lambda:original(cafile=str(cert)))
    with FakeSMTP(mail_certificate,starttls=True) as smtp:
        settings=Settings(_env_file=None,**{**app.state.settings.model_dump(),**PUBLIC,
            'public_registration_limit':5,'public_registration_per_hour':3,'public_challenge_difficulty':12,
            'ai_enabled':False,'smtp_host':'127.0.0.1','smtp_port':smtp.port,'smtp_starttls':True,
            'storage_dir':tmp_path/'documents'})
        application=create_app(settings)
        with application_server(application) as api, (tmp_path/'gateway-errors.log').open('w',encoding='utf-8') as errors:
            gateway=subprocess.Popen(['node',str(ROOT/'tests/fixtures/public_beta_gateway.mjs')],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,cwd=ROOT)
            try:
                gateway.stdin.write(json.dumps({'api':api,'key':BFF_KEY,'certificate':str(cert),'privateKey':str(key)}))
                gateway.stdin.close()
                origin=json.loads(line_with_deadline(gateway))['origin']
                settings.account_base_url=origin
                with httpx.Client(base_url=origin,verify=original(cafile=str(cert)),trust_env=False,timeout=10) as http:
                    def post(path,body):
                        csrf=http.get('/bff/auth/csrf');assert csrf.status_code==200
                        return http.post('/bff'+path,json=body,headers={'X-CSRF-Token':csrf.json()['csrf_token'],'Origin':origin})
                    def body():
                        data=http.get('/bff/auth/registration-challenge').json()
                        assert data['difficulty']==12
                        return {'email':'http@example.test','password':PASSWORD,'terms_accepted':True,
                            'terms_version':'beta-test-v1','challenge':data['challenge'],
                            'proof':proof(data['challenge'],12)}
                    def token():
                        message=BytesParser(policy=policy.default).parsebytes(smtp.messages.get(timeout=5))
                        assert str(message['To'])=='http@example.test'
                        return re.search(r'#token=([A-Za-z0-9_-]{43})',message.get_content()).group(1)
                    yield application,http,post,body,token,smtp
            finally:
                if gateway.poll() is None:gateway.terminate();gateway.wait(timeout=10)


@pytest.mark.parametrize('scenario',['closed','full','duplicate','expired-resend','smtp-failure','queue-full'])
def test_https_account_recovery_and_admission_states(live_beta,monkeypatch,scenario,records):
    app,http,post,body,token,smtp=live_beta
    if scenario in ('closed','full'):
        # Seed only this disposable fixture's admission history; no quota is reset.
        with app.state.sessions() as db:
            quota=db.get(PublicRegistrationQuota,'public')
            if scenario=='closed':quota.closed=True
            else:quota.issued_count=5
            db.commit()
        assert post('/auth/register',body()).status_code==202
        assert http.get('/bff/auth/options').json()['public_registration_availability']==scenario
        assert smtp.messages.empty()
        with app.state.sessions() as db:assert db.scalar(select(User)) is None
        return
    if scenario=='smtp-failure':smtp.reject=True
    with monkeypatch.context() as patch:
        if scenario=='queue-full':
            def full(item):raise queue.Full
            patch.setattr(app.state.mail_queue,'put_nowait',full)
        first=post('/auth/register',body());assert first.status_code==202
    old=None
    if scenario in ('duplicate','expired-resend'):old=token()
    if scenario=='duplicate':
        duplicate=post('/auth/register',body())
        assert duplicate.status_code==202 and duplicate.json()==first.json() and smtp.messages.empty()
    else:
        if scenario=='expired-resend':
            with app.state.sessions() as db:
                db.scalar(select(AccountToken).where(AccountToken.kind=='verify')).expires_at=now()-timedelta(seconds=1);db.commit()
            assert post('/auth/verify-email',{'token':old,'password':PASSWORD}).status_code==400
        if scenario=='smtp-failure':
            assert smtp.failed.wait(5)
            smtp.reject=False
        assert post('/auth/resend-verification',body()).status_code==202
        fresh=token()
        if old:assert post('/auth/verify-email',{'token':old,'password':PASSWORD}).status_code==400
        assert post('/auth/verify-email',{'token':fresh,'password':PASSWORD}).status_code==200
        assert post('/auth/verify-email',{'token':fresh,'password':PASSWORD}).status_code==400
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota,'public').issued_count==1
    for row in records:
        assert 'http@example.test' not in json.dumps(row) and PASSWORD not in json.dumps(row)
