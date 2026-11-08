"""Executed inside the exact API, with its synthetic env and no source override.

HTTP tests use real Web/BFF/TLS/API. Helper tests below are explicitly partial;
they cannot qualify an admission refused by the durable lifecycle guard.
"""
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import socket
import ssl
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, func
from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.account_models import AccountToken, PublicRegistrationQuota
from backend.auth import User
from backend.account_api import issue_token, consume_token, send_verification
from backend.public_registration import increment_quota, RegistrationChallenges

settings=Settings(_env_file=None)
assert settings.database_url=='postgresql+psycopg://synthetic:lab-only-password@db:5432/synthetic'
assert settings.lifecycle_durable_receipts_required and not settings.lifecycle_synthetic_mutations_enabled
assert settings.public_terms_version=='lab-only-v1' and settings.public_registration_limit==5
assert settings.smtp_host=='smtp'
results=[]
def check(name,condition,detail=None):
    results.append(dict(test=name,status='PASS' if condition else 'FAIL',detail=detail))
    assert condition, name+': '+str(detail)

cookies={}; csrf=''
context=ssl.create_default_context(cafile='/certs/lab.crt')
def request(method,path,body=None,with_csrf=True):
    connection=http.client.HTTPSConnection('localhost',8443,context=context,timeout=10)
    connection._create_connection=lambda address,timeout,source_address=None: socket.create_connection(('proxy',8443),timeout)
    headers={'Host':'localhost:19446','Origin':'https://localhost:19446'}
    if cookies:headers['Cookie']='; '.join(k+'='+v for k,v in cookies.items())
    if with_csrf and csrf:headers['X-CSRF-Token']=csrf
    if body is not None:headers['Content-Type']='application/json'
    connection.request(method,path,json.dumps(body) if body is not None else None,headers)
    response=connection.getresponse(); data=response.read()
    for header,value in response.getheaders():
        if header.lower()=='set-cookie':
            k,v=value.split(';',1)[0].split('=',1);cookies[k]=v
    status=response.status; connection.close()
    try: data=json.loads(data)
    except ValueError:data=data.decode('utf-8',errors='replace')
    return status,data

engine=make_engine(settings.database_url); sessions=make_sessions(engine)
def projection():
    with sessions() as db:
        quota=db.get(PublicRegistrationQuota,'public')
        return dict(issued_count=quota.issued_count,closed=quota.closed,
            users=db.scalar(select(func.count()).select_from(User)),tokens=db.scalar(select(func.count()).select_from(AccountToken)))

before=projection()
check('fresh_synthetic_database',before==dict(issued_count=0,closed=True,users=0,tokens=0),before)
status,data=request('GET','/')
check('web_r2_html_over_verified_tls',status==200 and 'Docnelo' in data)
status,data=request('GET','/register')
check('registration_spa_served',status==200 and '<html' in data.lower())
status,data=request('GET','/lab-legal/terms')
check('synthetic_terms_served',status==200 and 'SYNTHÉTIQUE' in data)
status,options=request('GET','/bff/auth/options')
check('closed_quota_ui_availability',status==200 and options.get('public_registration_availability')=='closed'
    and not options.get('public_capacity_configured'),options)
status,data=request('GET','/bff/account')
check('anonymous_authenticated_access_rejected',status==401,dict(status=status))
status,data=request('GET','/bff/auth/csrf'); csrf=data.get('csrf_token','')
check('secure_csrf_cookie',status==200 and '__Host-documind-csrf' in cookies and bool(csrf))
body=dict(email='signup@example.test',password='Laboratory-password-908!',terms_accepted=True,terms_version='lab-only-v1')
status,data=request('POST','/bff/auth/register',body,with_csrf=False)
check('missing_csrf_rejected',status==403,dict(status=status))
status,data=request('POST','/bff/auth/register',dict(body,terms_accepted=False))
check('terms_refusal_rejected',status==400,dict(status=status))
status,data=request('POST','/bff/auth/register',dict(body,terms_version='wrong-version'))
check('stale_terms_rejected',status==400,dict(status=status))
status,data=request('GET','/bff/auth/registration-challenge')
check('challenge_issued',status==200,dict(status=status))
challenge=data['challenge'];difficulty=data['difficulty']
for proof in range(10**7):
    if int.from_bytes(hashlib.sha256(f'{challenge}:{proof}'.encode()).digest()[:3],'big')>>(24-difficulty)==0:break
else:raise AssertionError('Challenge solver exhausted')
status,data=request('POST','/bff/auth/register',dict(body,challenge=challenge,proof=str(proof)))
check('strict_durable_admission_refused',status==503,dict(status=status))
status,data=request('POST','/bff/auth/verify-email',dict(token=secrets.token_urlsafe(32),password=body['password']))
check('unknown_verification_token_rejected',status==400,dict(status=status))
status,data=request('POST','/bff/auth/login',dict(email=body['email'],password=body['password']))
check('unadmitted_login_rejected',status==401,dict(status=status))
check('no_admission_or_token_after_rejection',projection()==before,projection())

# A separate synthetic message exercises the real TLS SMTP sender, not admission.
send_verification(settings,'capture-only@example.test',secrets.token_urlsafe(32))
check('standalone_smtp_tls_send',True,'Synthetic message only; no admitted user')

# Direct helper contracts, each using this fresh laboratory database only.
# All quota mutations are rolled back; no durable admissions are manufactured.
with sessions() as db:
    quota=db.get(PublicRegistrationQuota,'public');quota.closed=True;db.flush()
    check('helper_closed_quota_denies',increment_quota(db,5) is None)
    db.rollback()
with sessions() as db:
    quota=db.get(PublicRegistrationQuota,'public');quota.closed=False;quota.issued_count=5;db.flush()
    check('helper_full_quota_denies',increment_quota(db,5) is None)
    db.rollback()
with sessions() as db:
    token=issue_token(db,'verify','token-helper@example.test',300);db.flush()
    check('helper_token_first_use',consume_token(db,token,'verify')=='token-helper@example.test')
    try:consume_token(db,token,'verify')
    except HTTPException as error:check('helper_token_replay_rejected',error.status_code==400)
    else:check('helper_token_replay_rejected',False)
    db.rollback()
with sessions() as db:
    token=issue_token(db,'verify','expired-helper@example.test',-1);db.flush()
    try:consume_token(db,token,'verify')
    except HTTPException as error:check('helper_expired_token_rejected',error.status_code==400)
    else:check('helper_expired_token_rejected',False)
    db.rollback()
clock=[0];challenges=RegistrationChallenges(clock=lambda:clock[0]);item=challenges.issue('synthetic',10)
clock[0]=301
check('helper_expired_challenge_rejected',not challenges.consume(item['challenge'],'0','synthetic'))
challenges=RegistrationChallenges();item=challenges.issue('synthetic',10)
for proof in range(10**6):
    if int.from_bytes(hashlib.sha256(f"{item['challenge']}:{proof}".encode()).digest()[:3],'big')>>(24-10)==0:break
check('helper_challenge_first_use',challenges.consume(item['challenge'],str(proof),'synthetic'))
check('helper_challenge_replay_rejected',not challenges.consume(item['challenge'],str(proof),'synthetic'))
try:Settings(_env_file=None,public_legal_ready=False)
except ValueError:check('legal_approval_guard_preserved',True)
else:check('legal_approval_guard_preserved',False)
check('projection_unchanged_after_helper_rollbacks',projection()==before,projection())
source={}
for name in ['config.py','public_registration.py','account_api.py','lifecycle_durability.py']:
    file=Path('/app/backend')/name
    source[name]=hashlib.sha256(file.read_bytes()).hexdigest()
print(json.dumps(dict(verdict='BLOCKED',tests=results,projection=projection(),runtime_source_sha256=source,
    reason='Exact API refuses durable signup; no bypass enabled',
    not_qualified=['successful signup','email issued by admission','successful verification','successful login',
        'authenticated account access','successful user journey after restart','browser form interaction']),ensure_ascii=True))
