import hashlib
import queue
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import func, select, update

from backend.account_models import AccountToken, PublicRegistrationQuota, Workspace, WorkspaceMembership
from backend.auth import User
from backend.config import Settings
from backend.models import now
from backend.public_registration import RegistrationChallenges
from tests.conftest import BFF_KEY, KEY
from tests.test_upload_admission import raw_request, multipart, completed

PASSWORD='Fictitious-public-password-123!'
PUBLIC={'registration_mode':'public','legacy_api_enabled':False,'owner_demo_enabled':False,
    'public_registration_limit':4,'public_registration_per_hour':10,'public_challenge_difficulty':10,
    'public_legal_ready':True,'public_operator_name':'Fictitious operator','public_contact_email':'contact@example.test',
    'public_legal_notice_url':'https://documind.example.test/legal','public_privacy_url':'https://documind.example.test/privacy',
    'public_terms_url':'https://documind.example.test/terms','public_terms_version':'beta-test-v1',
    'smtp_host':'smtp.example.test','smtp_from':'noreply@example.test'}


@pytest.fixture
def beta(gateway_client,app):
    app.state.settings=Settings(_env_file=None,**{**app.state.settings.model_dump(),**PUBLIC})
    sent=queue.Queue()
    app.state.mail_sender=lambda email,token:sent.put((email,token))
    gateway_client.headers['X-Documind-Secure']='1'
    return gateway_client,app,sent


def proof(challenge,difficulty):
    for value in range(1000000):
        if int.from_bytes(hashlib.sha256(f'{challenge}:{value}'.encode()).digest()[:3],'big')>>(24-difficulty)==0:return str(value)
    raise AssertionError('Fictitious proof search exceeded safety bound')


def signup_body(client,email='alice@example.test',**extra):
    challenge=client.get('/api/v1/auth/registration-challenge')
    assert challenge.status_code==200,challenge.text
    data=challenge.json()
    return {'email':email,'password':PASSWORD,'terms_accepted':True,'terms_version':'beta-test-v1',
            'challenge':data['challenge'],'proof':proof(data['challenge'],data['difficulty']),**extra}


def enroll(beta,email='alice@example.test'):
    client,app,sent=beta
    response=client.post('/api/v1/auth/register',json=signup_body(client,email))
    assert response.status_code==202,response.text
    address,token=sent.get(timeout=3);assert address==email
    return token


def verify_and_login(beta,email='alice@example.test'):
    client,app,sent=beta;token=enroll(beta,email)
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==200
    response=client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD},headers={'Authorization':''})
    assert response.status_code==200,response.text
    client.headers['Authorization']='Bearer '+response.json()['session_token']
    return token


def test_public_requires_explicit_safe_configuration():
    assert Settings(_env_file=None).registration_mode=='disabled'
    with pytest.raises(ValidationError):Settings(_env_file=None,registration_mode='public')
    config={**PUBLIC,'bff_service_key':BFF_KEY}
    assert Settings(_env_file=None,**config).registration_mode=='public'
    for changed in ({'owner_demo_enabled':True},{'legacy_api_enabled':True},{'smtp_host':''},{'public_legal_ready':False},
                    {'public_privacy_url':'http://unsafe.example.test'},{'public_terms_version':''}):
        with pytest.raises(ValidationError):Settings(_env_file=None,**{**config,**changed})


def test_pending_account_email_and_password_proof_atomic_workspace_and_one_use(beta):
    client,app,sent=beta;token=enroll(beta)
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD}).status_code==401
    with app.state.sessions() as db:
        user=db.scalar(select(User));assert user.disabled_at and user.email_verified_at is None
        assert db.get(Workspace,user.owner_id) and db.get(WorkspaceMembership,user.id)
        owner=user.owner_id
        manufactured=app.state.session_vault.create(user)
        stored=db.scalar(select(AccountToken).where(AccountToken.kind=='verify'))
        assert stored.digest!=token and token not in stored.digest
    result=raw_request(app,{'X-API-Key':BFF_KEY,'Authorization':'Bearer '+manufactured},completed(multipart()))
    assert result['status']==401 and result['receive_calls']==0
    # Someone initiating signup for another mailbox cannot activate it just by inducing a click.
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD+'wrong'}).status_code==400
    app.state.settings.registration_mode='disabled'
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==200
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==400
    with app.state.sessions() as db:
        user=db.scalar(select(User));assert user.owner_id==owner and user.disabled_at is None and user.email_verified_at
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD}).status_code==200


@pytest.mark.parametrize('invalid',['expired','corrupt'])
def test_invalid_verification_does_not_activate(beta,invalid):
    client,app,sent=beta;token=enroll(beta)
    if invalid=='expired':
        with app.state.sessions() as db:
            db.scalar(select(AccountToken).where(AccountToken.kind=='verify')).expires_at=now()-timedelta(seconds=1);db.commit()
    else:token='B'*43
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==400
    with app.state.sessions() as db:assert db.scalar(select(User)).email_verified_at is None


def test_duplicate_and_capacity_responses_do_not_enumerate_or_overwrite(beta):
    client,app,sent=beta
    original=client.post('/api/v1/auth/register',json=signup_body(client));assert original.status_code==202
    sent.get(timeout=3)
    duplicate=client.post('/api/v1/auth/register',json=signup_body(client,password=PASSWORD+'other'))
    app.state.settings.public_registration_limit=1
    full=client.post('/api/v1/auth/register',json=signup_body(client,'bob@example.test'))
    assert duplicate.status_code==full.status_code==202 and original.json()==duplicate.json()==full.json()
    assert sent.empty()
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.get(PublicRegistrationQuota,'public').issued_count==1


@pytest.mark.parametrize('invalid',['honeypot','proof','terms'])
def test_anti_abuse_and_terms_fail_without_account_creation(beta,invalid):
    client,app,sent=beta;body=signup_body(client)
    if invalid=='honeypot':body['website']='https://robot.example.test'
    elif invalid=='proof':body['proof']='invalid'
    else:body['terms_accepted']=False
    response=client.post('/api/v1/auth/register',json=body)
    assert response.status_code==(400 if invalid=='terms' else 202)
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(User))==0
        assert db.get(PublicRegistrationQuota,'public').issued_count==0
    assert sent.empty()


def test_nonce_expiry_binding_reuse_and_memory_bound():
    clock=[0.0];store=RegistrationChallenges(clock=lambda:clock[0],capacity=1)
    first=store.issue('ip-one',10)
    with pytest.raises(Exception):store.issue('ip-two',10)
    assert not store.consume(first['challenge'],proof(first['challenge'],10),'ip-two')
    assert not store.consume(first['challenge'],proof(first['challenge'],10),'ip-one')
    second=store.issue('ip-one',10);clock[0]=301
    assert not store.consume(second['challenge'],proof(second['challenge'],10),'ip-one')


def test_simultaneous_registration_never_exceeds_global_cap(beta):
    client,app,sent=beta;app.state.settings.public_registration_limit=1
    bodies=[signup_body(client,f'user{n}@example.test') for n in (1,2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda body:client.post('/api/v1/auth/register',json=body).status_code,bodies))
    assert all(code in (202,503) for code in codes) and 202 in codes
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.get(PublicRegistrationQuota,'public').issued_count==1


def test_quota_update_is_atomic_even_without_process_local_semaphore(beta):
    client,app,sent=beta
    def reserve(_):
        with app.state.sessions() as db:
            granted=db.execute(update(PublicRegistrationQuota).where(PublicRegistrationQuota.id=='public',
                PublicRegistrationQuota.issued_count<1).values(issued_count=PublicRegistrationQuota.issued_count+1)
                .returning(PublicRegistrationQuota.issued_count)).scalar_one_or_none();db.commit();return granted
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve,range(2)),key=lambda n:n is None)==[1,None]


def test_closed_reopened_resend_and_budgets_are_isolated(beta):
    client,app,sent=beta;first=enroll(beta)
    app.state.settings.registration_mode='disabled'
    assert client.post('/api/v1/auth/register',json=signup_body(client,'no@example.test')).status_code==403
    assert client.post('/api/v1/auth/resend-verification',json=signup_body(client)).status_code==202
    _,fresh=sent.get(timeout=3)
    assert client.post('/api/v1/auth/verify-email',json={'token':first,'password':PASSWORD}).status_code==400
    assert client.post('/api/v1/auth/verify-email',json={'token':fresh,'password':PASSWORD}).status_code==200
    response=client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD})
    client.headers['Authorization']='Bearer '+response.json()['session_token']
    assert client.put('/api/v1/ai/settings',json={'mode':'OWNER_DEMO','limit_usd':1}).status_code==403
    assert client.put('/api/v1/ai/settings',json={'mode':'USER_BYOK','limit_usd':2}).status_code==403
    assert client.put('/api/v1/ai/settings',json={'mode':'USER_BYOK','limit_usd':1}).status_code==200
    app.state.settings.owner_demo_enabled=True
    app.state.session_vault.resolve(response.json()['session_token']).mode='OWNER_DEMO'
    assert client.get('/api/v1/ai/status').status_code==403
    app.state.settings.registration_mode='public';app.state.settings.owner_demo_enabled=False
    assert client.post('/api/v1/auth/register',json=signup_body(client,'bob@example.test')).status_code==202


def test_public_owner_cannot_use_legacy_identity(beta):
    client,app,sent=beta;verify_and_login(beta)
    with app.state.sessions() as db:owner=db.scalar(select(User.owner_id))
    app.state.settings.registration_mode='disabled';app.state.settings.legacy_api_enabled=True
    app.state.settings.api_keys={KEY:owner}
    assert client.get('/api/v1/documents',headers={'Authorization':'','X-API-Key':KEY}).status_code==403


def test_full_fictitious_user_lifecycle_and_owner_isolation(beta):
    from backend.account_admin import purge_account
    client,app,sent=beta;verify_and_login(beta)
    document=client.post('/api/v1/documents',files={'file':('fake.txt',b'Fictitious Docker document.')})
    assert document.status_code==201
    identifier=document.json()['id']
    assert client.post(f'/api/v1/documents/{identifier}/analyze',json={}).status_code==201
    assert client.post('/api/v1/auth/logout',json={}).status_code==200
    response=client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD},headers={'Authorization':''})
    assert response.status_code==200
    client.headers['Authorization']='Bearer '+response.json()['session_token']
    app.state.settings.max_documents_per_owner=1
    assert client.post('/api/v1/documents',files={'file':('other.txt',b'Fictitious second document.')}).status_code==413
    assert client.post('/api/v1/auth/forgot-password',json={'email':'alice@example.test'}).status_code==202
    _,reset=sent.get(timeout=3)
    assert client.post('/api/v1/auth/reset-password',json={'token':reset,'password':PASSWORD+'new'}).status_code==200
    response=client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD+'new'},headers={'Authorization':''})
    client.headers['Authorization']='Bearer '+response.json()['session_token'];alice=client.headers['Authorization']
    verify_and_login(beta,'bob@example.test')
    assert client.get('/api/v1/documents/'+identifier).status_code==404
    client.headers['Authorization']=alice
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD+'new'}).status_code==202
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.email=='alice@example.test'));purge_account(db,app.state.settings,user.id)
        assert db.scalar(select(User).where(User.email=='alice@example.test')) is None
    assert not list(app.state.settings.storage_dir.glob('*.txt'))


def test_pending_cleanup_dry_run_expiry_and_counter_preserved(beta):
    from backend.account_admin import purge_pending
    client,app,sent=beta;enroll(beta)
    with app.state.sessions() as db:
        db.scalar(select(User)).created_at=now()-timedelta(days=3);db.commit()
        assert purge_pending(db,app.state.settings)==0  # active mail link protects the account
        db.scalar(select(AccountToken).where(AccountToken.kind=='verify')).expires_at=now()-timedelta(seconds=1);db.commit()
        assert purge_pending(db,app.state.settings)==1
        assert db.scalar(select(func.count()).select_from(User))==1
        assert purge_pending(db,app.state.settings,execute=True)==1
        assert db.scalar(select(func.count()).select_from(User))==0
        assert db.get(PublicRegistrationQuota,'public').issued_count==1


def test_database_kill_switch_closes_only_new_admissions_and_reopens(beta):
    client,app,sent=beta;token=enroll(beta)
    with app.state.sessions() as db:
        db.get(PublicRegistrationQuota,'public').closed=True;db.commit()
    assert client.get('/api/v1/auth/options').json()['public_capacity_configured'] is False
    closed=client.post('/api/v1/auth/register',json=signup_body(client,'blocked@example.test'))
    assert closed.status_code==202 and sent.empty()
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==200
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD}).status_code==200
    with app.state.sessions() as db:
        quota=db.get(PublicRegistrationQuota,'public');assert quota.issued_count==1
        quota.closed=False;db.commit()
    assert client.get('/api/v1/auth/options').json()['public_capacity_configured'] is True
    assert client.post('/api/v1/auth/register',json=signup_body(client,'reopened@example.test')).status_code==202
    assert sent.get(timeout=3)[0]=='reopened@example.test'


def test_mailbox_owner_can_recover_an_unrequested_pending_signup(beta):
    client,app,sent=beta;enroll(beta)
    assert client.post('/api/v1/auth/forgot-password',json={'email':'alice@example.test'}).status_code==202
    _,reset=sent.get(timeout=3)
    assert client.post('/api/v1/auth/reset-password',json={'token':reset,'password':PASSWORD+'owner'}).status_code==200
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD+'owner'}).status_code==401
    body=signup_body(client,password=PASSWORD+'owner')
    assert client.post('/api/v1/auth/resend-verification',json=body).status_code==202
    _,fresh=sent.get(timeout=3)
    assert client.post('/api/v1/auth/verify-email',json={'token':fresh,'password':PASSWORD+'owner'}).status_code==200
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':PASSWORD+'owner'}).status_code==200


def test_migration_downgrade_refuses_to_erase_public_admission_history(beta):
    client,app,sent=beta;enroll(beta)
    with pytest.raises(RuntimeError,match='Downgrade refusé'):command.downgrade(Config('alembic.ini'),'0006')
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota,'public').issued_count==1
        assert db.scalar(select(User)).registration_kind=='public'


def test_registration_rate_is_enforced_before_hash_work(beta,monkeypatch):
    client,app,sent=beta;app.state.settings.public_registration_per_hour=1
    body=signup_body(client,website='bot')
    assert client.post('/api/v1/auth/register',json=body).status_code==202
    def forbidden(*args,**kwargs):raise AssertionError('Password work after rate rejection')
    monkeypatch.setattr('backend.public_registration.hash_password',forbidden)
    assert client.post('/api/v1/auth/register',json=body).status_code==429


def test_public_registration_audit_never_contains_email_password_or_tokens(beta, monkeypatch, capfd, caplog):
    import json
    from backend import security_audit
    values=[]
    class Memory:
        def submit(self, line):
            values.append(json.loads(line));return True
    monkeypatch.setattr(security_audit,'writer',Memory())
    client,app,sent=beta;token=enroll(beta)
    assert client.post('/api/v1/auth/verify-email',json={'token':token,'password':PASSWORD}).status_code==200
    assert {'account.registration.requested','account.email.verified'} <= {row['event'] for row in values}
    output=capfd.readouterr()
    serialized=json.dumps(values)+output.out+output.err+caplog.text
    for secret in ('alice@example.test',PASSWORD,token,BFF_KEY):assert secret not in serialized


def test_migration_0007_preserves_0006_identity_and_disabled_state(tmp_path,monkeypatch):
    from sqlalchemy import text
    from backend.db import make_engine
    url=f'sqlite:///{(tmp_path/"preserve.db").as_posix()}'
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config('alembic.ini');command.upgrade(config,'0006')
    engine=make_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users(id,owner_id,username,password_hash,ai_limit_usd,created_at,email,disabled_at) VALUES (:id,:owner,'existing','original-hash',4,CURRENT_TIMESTAMP,'existing@example.test',CURRENT_TIMESTAMP)"),{'id':'1'*32,'owner':'2'*32})
            before=tuple(connection.execute(text('SELECT * FROM users')).one())
        command.upgrade(config,'0007')
        with engine.connect() as connection:
            assert tuple(connection.execute(text('SELECT id,owner_id,username,password_hash,ai_limit_usd,created_at,email,disabled_at FROM users')).one())==before
            assert tuple(connection.execute(text('SELECT registration_kind,email_verified_at,terms_version,terms_accepted_at FROM users')).one())==('legacy',None,None,None)
            assert tuple(connection.execute(text('SELECT id,issued_count,closed FROM public_registration_quota')).one())==('public',0,False)
        command.downgrade(config,'0006')
        with engine.connect() as connection:assert tuple(connection.execute(text('SELECT * FROM users')).one())==before
    finally:engine.dispose()
