"""Security signals must not become a new source of documents/credentials/PII."""
import json
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend import security_audit as audit
from backend.auth import User
from backend.models import now
from tests.conftest import BFF_KEY, KEY
from tests.test_byok import accounts, login, PASSWORD
from tests.test_upload_admission import raw_request, multipart, completed, session_token

SENTINEL = 'SENSITIVE-sentinel-DO-NOT-LOG-\n\r\x1b-password-document@example.test'


@pytest.fixture
def records(monkeypatch):
    values = []
    class Memory:
        def submit(self, line):
            values.append(json.loads(line))
            return True
    monkeypatch.setattr(audit, 'writer', Memory())
    return values


def assert_private(records, *sentinels):
    text = json.dumps(records)
    for value in (SENTINEL, KEY, BFF_KEY, PASSWORD, *sentinels):
        assert value not in text
    for row in records:
        assert set(row) <= {'timestamp','level','service','event','request_id','operation','outcome','http_status','reason_code'}
        assert row['timestamp'].endswith('Z')


def test_login_success_failure_and_logout_are_private(accounts, records, capfd, caplog):
    client, app = accounts
    response = client.post('/api/v1/auth/login', json={'username':'alice','password':SENTINEL},
                           headers={'X-Documind-Secure':'1'})
    assert response.status_code == 401 and SENTINEL not in response.text
    token = login(client, 'alice')
    assert client.post('/api/v1/auth/logout', json={}).status_code == 200
    assert [r['event'] for r in records] == ['auth.login.failure','auth.login.success','auth.logout']
    assert_private(records, token)
    output = capfd.readouterr()
    assert SENTINEL not in output.out + output.err + caplog.text


@pytest.mark.parametrize('state', ['absent','invented','revoked','expired','disabled'])
def test_invalid_session_events_preserve_early_admission(app, records, state):
    token = session_token(app, state) if state not in {'absent','invented'} else 'A'*43
    headers = {'X-API-Key':BFF_KEY, 'X-Documind-Secure':'1','content-type':'multipart/form-data; boundary=test'}
    if state != 'absent': headers['authorization']='Bearer '+token
    result = raw_request(app, headers, completed(multipart(SENTINEL.encode())))
    assert result['status'] == 401 and result['receive_calls'] == 0
    assert len(records) == 1
    assert records[0]['event'] in {'upload.admission.denied','auth.session.revoked'}
    assert_private(records, token)


@pytest.mark.parametrize('state', ['absent','invented','revoked'])
def test_private_routes_log_invalid_session_without_identifiers(app, client, records, state):
    token = session_token(app, 'revoked') if state == 'revoked' else 'A'*43
    headers = {'X-API-Key': BFF_KEY,'X-Documind-Secure':'1'}
    if state!='absent':headers['Authorization']='Bearer '+token
    assert client.get('/api/v1/account',headers=headers).status_code==401
    assert records[-1]['event']=='auth.session.invalid'
    assert_private(records, token)


def test_gateway_rejection_and_request_id_spoofing(client, records):
    spoof='f'*32
    response=client.get('/api/v1/account',headers={'X-Documind-Secure':'1','X-Request-ID':spoof})
    assert response.status_code==403
    assert response.headers['x-request-id']!=spoof
    assert records[-1]['event']=='gateway.authentication.failed'
    assert records[-1]['request_id']==response.headers['x-request-id']
    response=client.get('/api/v1/account',headers={'X-API-Key':BFF_KEY,'X-Documind-Secure':'1','X-Request-ID':spoof})
    assert response.status_code==401 and response.headers['x-request-id']==spoof
    assert_private(records)


@pytest.mark.parametrize('supplied', ['bad\r\nFORGED','x'*10000,'../private/password'])
def test_malformed_correlation_never_enters_events(app, records, supplied):
    result=raw_request(app,{'X-API-Key':BFF_KEY,'X-Request-ID':supplied},[],method='GET')
    assert result['status']==401
    assert audit.REQUEST_ID.fullmatch(records[-1]['request_id'])
    assert supplied not in json.dumps(records)


def test_cross_owner_denial_keeps_same_404_and_logs_no_document(client, records):
    response=client.post('/api/v1/documents',files={'file':('private-name.txt',b'PRIVATE DOCUMENT CONTENT')})
    assert response.status_code==201
    identifier=response.json()['id']
    from tests.conftest import OTHER_KEY
    denied=client.get('/api/v1/documents/'+identifier,headers={'X-API-Key':OTHER_KEY})
    assert denied.status_code==404
    assert records[-1]['event']=='access.cross_owner.denied'
    assert_private(records,identifier,'private-name.txt','PRIVATE DOCUMENT CONTENT',OTHER_KEY)


def test_rate_limit_and_document_quota_are_not_body_logs(app, client, records):
    app.state.settings.max_documents_per_owner=1
    assert client.post('/api/v1/documents',files={'file':('a.txt',b'fictitious content')}).status_code==201
    assert client.post('/api/v1/documents',files={'file':('b.txt',b'other fictitious content')}).status_code==413
    assert records[-1]['event']=='quota.exceeded'
    token=session_token(app)
    slots=app.state.authentication_slots
    held=0
    try:
        while slots.acquire(blocking=False):held+=1
        response=client.get('/api/v1/internal/upload-admission',headers={
            'X-API-Key':BFF_KEY,'X-Documind-Secure':'1','Authorization':'Bearer '+token})
        assert response.status_code==503 and records[-1]['event']=='upload.capacity.exceeded'
    finally:
        for _ in range(held):slots.release()
    app.state.settings.requests_per_minute=1
    assert client.get('/api/v1/documents').status_code==429
    assert records[-1]['event']=='rate_limit.exceeded'
    assert_private(records,'fictitious content')


def test_sql_and_unexpected_exceptions_never_serialize_messages(app, client, records, monkeypatch, capfd, caplog):
    def fail(*args,**kwargs):raise SQLAlchemyError(SENTINEL)
    monkeypatch.setattr('backend.services.documents.owned_document',fail)
    # The API imported the function; patch its reference too.
    monkeypatch.setattr('backend.api.owned_document',fail)
    response=client.get('/api/v1/documents/00000000-0000-0000-0000-000000000001')
    assert response.status_code==503 and SENTINEL not in response.text
    assert records[-1]['event']=='system.database.unavailable'
    def broken(*args,**kwargs):raise RuntimeError(SENTINEL)
    monkeypatch.setattr('backend.api.owned_document',broken)
    response=client.get('/api/v1/documents/00000000-0000-0000-0000-000000000001')
    assert response.status_code==500 and SENTINEL not in response.text
    assert records[-1]['event']=='system.worker.failed'
    assert_private(records)
    output=capfd.readouterr()
    assert SENTINEL not in output.out+output.err+caplog.text


def test_allowlist_and_failed_logger_do_not_affect_authentication(accounts, records, monkeypatch):
    audit.emit('access.denied',password=SENTINEL,reason_code=SENTINEL,request_id=SENTINEL,operation=SENTINEL)
    assert_private(records)
    assert records[-1]['operation']=='other'
    class Broken:
        def submit(self,line):raise OSError(SENTINEL)
    monkeypatch.setattr(audit,'writer',Broken())
    client,app=accounts
    login(client,'alice')
    assert client.get('/api/v1/account').status_code==200


def test_writer_queue_overflow_and_sink_errors_are_bounded():
    entered, release=Event(),Event()
    lines=[]
    def slow(line):
        entered.set()
        assert release.wait(2)
        lines.append(json.loads(line))
    writer=audit.AuditWriter(sink=slow,capacity=1,per_second=100)
    assert writer.submit('{}')
    assert entered.wait(2)
    try:
        assert writer.submit('{}')
        assert not writer.submit('{}')
        assert writer.dropped==1
    finally:release.set()
    assert writer.flush(2)
    def broken(line):raise OSError(SENTINEL)
    failed=audit.AuditWriter(sink=broken)
    assert failed.submit('{}') and failed.flush(2)
    assert failed.failed>=1


def test_request_context_does_not_leak_across_requests(client, records):
    first=client.get('/api/v1/account',headers={'X-Documind-Secure':'1'})
    second=client.get('/api/v1/account',headers={'X-Documind-Secure':'1'})
    assert first.headers['x-request-id']!=second.headers['x-request-id']
    assert audit.current.get() is None


def test_password_change_deletion_and_administrative_purge_are_logged(accounts, records):
    from backend.account_admin import purge_account
    client,app=accounts
    token=login(client,'alice')
    assert client.post('/api/v1/account/password',json={'password':PASSWORD,'new_password':PASSWORD+'changed'}).status_code==200
    assert records[-1]['event']=='auth.password.changed'
    assert client.get('/api/v1/account').status_code==401
    response=client.post('/api/v1/auth/login',json={'username':'alice','password':PASSWORD+'changed'},headers={'Authorization':''})
    assert response.status_code==200
    client.headers['Authorization']='Bearer '+response.json()['session_token']
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD+'changed'}).status_code==202
    assert records[-1]['event']=='account.deletion.requested'
    with app.state.sessions() as db:
        identifier=db.scalar(select(User.id).where(User.username=='alice'))
        purge_account(db,app.state.settings,identifier)
    assert records[-1]['event']=='account.deletion.completed'
    assert_private(records,token,PASSWORD+'changed',response.json()['session_token'])


def test_reset_genericity_and_registration_do_not_log_mail_tokens_or_invitations(accounts, records):
    from tests.test_accounts_saas import invite
    client,app=accounts
    client.headers['X-Documind-Secure']='1'
    mail='sentinel-mail@example.test'
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='alice'));user.email=mail;db.commit()
    delivered=Event();sent=[]
    def send(email,token):sent.append(token);delivered.set()
    app.state.mail_sender=send
    known=client.post('/api/v1/auth/forgot-password',json={'email':mail})
    unknown=client.post('/api/v1/auth/forgot-password',json={'email':'unknown@example.test'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    assert delivered.wait(2)
    assert [r['event'] for r in records]==['auth.password_reset.requested']*2
    assert client.post('/api/v1/auth/reset-password',json={'token':sent[0],'password':PASSWORD+'new'}).status_code==200
    assert records[-1]['event']=='auth.password_reset.completed'
    app.state.settings.registration_mode='invite'
    invitation=invite(app)
    assert client.post('/api/v1/auth/register',json={'email':'new@example.test','password':PASSWORD,'invitation':invitation}).status_code==201
    assert records[-1]['event']=='account.created'
    assert_private(records,mail,'new@example.test',invitation,sent[0])


def test_failed_error_response_cannot_escape_with_sensitive_exception_chain(app, records, capfd, caplog):
    import asyncio
    from backend.audit_middleware import SecurityAudit
    async def broken(scope, receive, send):raise RuntimeError(SENTINEL)
    async def receive():raise AssertionError('No body may be requested')
    async def send(message):raise OSError(SENTINEL)
    scope={'type':'http','app':app,'method':'GET','path':'/api/v1/documents',
           'headers':[],'query_string':b'','client':('127.0.0.1',1234)}
    asyncio.run(SecurityAudit(broken)(scope,receive,send))
    assert len(records)==1 and records[0]['event']=='system.worker.failed'
    assert records[0]['http_status']==499
    assert_private(records)
    output=capfd.readouterr()
    assert SENTINEL not in output.out+output.err+caplog.text
