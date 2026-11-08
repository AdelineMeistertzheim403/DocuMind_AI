import base64
import hashlib
import time
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select,func

from backend.auth import User,hash_password,verify_password
from backend.account_api import issue_token
from backend.account_models import AccountToken,Workspace,WorkspaceMembership,DeletionRequest
from backend.models import now,Document,DocumentChunk,DocumentPage
from tests.test_byok import accounts,login,PASSWORD,connect
from tests.test_ai import upload,ai,payload
from tests.test_rag import rag,index
from tests.conftest import KEY


def invite(app,email='new@example.test',ttl=600):
    with app.state.sessions() as db:
        value=issue_token(db,'invite',email,ttl);db.commit();return value


def test_invitation_only_registration_email_login_ownership_and_one_use(accounts):
    client,app=accounts
    client.headers['X-Documind-Secure']='1'
    token=invite(app)
    data={'email':'NEW@example.test','password':PASSWORD,'invitation':token}
    assert client.post('/api/v1/auth/register',json=data).status_code==403
    app.state.settings.registration_mode='invite'
    expired=invite(app,ttl=-1)
    assert client.post('/api/v1/auth/register',json={**data,'invitation':expired}).status_code==400
    assert client.post('/api/v1/auth/register',json={**data,'owner_id':str(UUID(int=101))}).status_code==422
    assert client.post('/api/v1/auth/register',json=data).status_code==201
    assert client.post('/api/v1/auth/register',json=data).status_code==400
    response=client.post('/api/v1/auth/login',json={'email':'new@example.test','password':PASSWORD})
    assert response.status_code==200
    client.headers['Authorization']='Bearer '+response.json()['session_token']
    profile=client.get('/api/v1/account').json()
    assert profile['email']=='new@example.test' and profile['owner_id']!=str(UUID(int=101))
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.email=='new@example.test'))
        assert user.password_hash.startswith('$argon2id$')
        assert db.get(Workspace,user.owner_id) and db.get(WorkspaceMembership,user.id)


def test_legacy_scrypt_upgrade_without_changing_owner(accounts):
    client,app=accounts
    raw=b'1234567890123456'
    digest=hashlib.scrypt(PASSWORD.encode(),salt=raw,n=16384,r=8,p=1,maxmem=128*1024*1024)
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='alice'))
        user.password_hash=base64.b64encode(raw+digest).decode();db.commit();identifier=user.owner_id
    login(client,'alice')
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='alice'))
        assert user.owner_id==identifier and user.password_hash.startswith('$argon2id$')


def test_wrong_password_generic_recovery_expired_and_single_use_reset(accounts):
    client,app=accounts;client.headers['X-Documind-Secure']='1'
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='alice'));user.email='alice@example.test';db.commit()
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.test','password':'wrong'}).status_code==401
    sent=[];app.state.mail_sender=lambda email,token:sent.append((email,token))
    known=client.post('/api/v1/auth/forgot-password',json={'email':'alice@example.test'})
    unknown=client.post('/api/v1/auth/forgot-password',json={'email':'unknown@example.test'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    app.state.mail_queue.join();assert len(sent)==1 and sent[0][1] not in known.text
    token=sent[0][1]
    login(client,'alice');old=client.headers['Authorization']
    with app.state.sessions() as db:
        expired=issue_token(db,'reset','alice@example.test',-1);db.commit()
    assert client.post('/api/v1/auth/reset-password',json={'token':expired,'password':PASSWORD}).status_code==400
    result=client.post('/api/v1/auth/reset-password',json={'token':token,'password':PASSWORD+'new'})
    assert result.status_code==200 and client.get('/api/v1/account',headers={'Authorization':old}).status_code==401
    assert client.post('/api/v1/auth/reset-password',json={'token':token,'password':PASSWORD}).status_code==400


def test_session_revocation_scoped_to_account_and_password_change(accounts):
    client,app=accounts
    first=login(client,'alice');second=login(client,'alice')
    # login rotates only a presented existing token; explicitly retain another independent session.
    with app.state.sessions() as db:
        alice=db.scalar(select(User).where(User.username=='alice'));other=app.state.session_vault.create(alice)
    values=client.get('/api/v1/account/sessions').json()['items']
    target=app.state.session_vault.digest(other)
    assert any(item['id']==target and not item['current'] for item in values)
    login(client,'bob')
    assert client.delete('/api/v1/account/sessions/'+target).status_code==404
    client.headers['Authorization']='Bearer '+second
    assert client.delete('/api/v1/account/sessions/'+target).status_code==200
    assert client.get('/api/v1/account',headers={'Authorization':'Bearer '+other}).status_code==401
    assert client.post('/api/v1/account/password',json={'password':PASSWORD,'new_password':PASSWORD+'changed'}).status_code==200
    assert client.get('/api/v1/account').status_code==401


def test_document_quota_legacy_switch_and_cross_owner_access(accounts):
    client,app=accounts
    login(client,'alice');identifier=upload(client)
    app.state.settings.max_documents_per_owner=1
    assert client.post('/api/v1/documents',files={'file':('other.txt',b'another text','text/plain')}).status_code==413
    login(client,'bob')
    for method,path in [('GET',''),('DELETE',''),('DELETE','/ai-results'),('DELETE','/embeddings')]:
        assert client.request(method,'/api/v1/documents/'+identifier+path).status_code==404
    app.state.settings.legacy_api_enabled=False
    assert client.get('/api/v1/documents',headers={'Authorization':'','X-API-Key':KEY}).status_code==401
    assert client.get('/api/v1/documents').status_code==200


def test_deletion_request_revokes_keys_and_purge_removes_content(accounts):
    from backend.account_admin import purge_account
    client,app=accounts
    login(client,'alice');connect(client);identifier=upload(client)
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='alice'));uid=user.id
    assert client.post('/api/v1/account/deletion-request',json={'password':'wrong'}).status_code==401
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD}).status_code==202
    assert client.get('/api/v1/documents').status_code==401
    assert not app.state.session_vault.sessions
    with app.state.sessions() as db:
        assert db.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id==uid))
        purge_account(db,app.state.settings,uid)
        assert db.get(User,uid) is None and db.get(Document,UUID(identifier)) is None
        assert db.scalar(select(func.count()).select_from(DocumentChunk))==0
    assert not list(app.state.settings.storage_dir.glob('*.txt'))


def test_clear_ai_results_and_embeddings_preserves_document_and_billing(rag):
    from tests.test_byok import PASSWORD
    from backend.ai.models import AIBudget,AIUsage,AISummary
    client,app,embedding,provider=rag
    with app.state.sessions() as db:
        db.add(User(username='owner',owner_id=UUID(int=1),password_hash=hash_password(PASSWORD)))
        db.add(AIBudget(id=f'byok:{UUID(int=1)}:openai'));db.commit()
    login(client,'owner')
    client.put('/api/v1/ai/settings',json={'mode':'OWNER_DEMO','limit_usd':4})
    identifier=upload(client)
    assert client.post(f'/api/v1/documents/{identifier}/summarize',json=payload()).status_code==200
    index_body=payload()
    assert client.post(f'/api/v1/documents/{identifier}/index',json=index_body).status_code==202
    from backend.rag.models import ChunkEmbedding,IndexJob
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ChunkEmbedding))>0
        billed=db.scalar(select(func.count()).select_from(AIUsage))
    assert client.delete(f'/api/v1/documents/{identifier}/ai-results').status_code==204
    assert client.delete(f'/api/v1/documents/{identifier}/embeddings').status_code==204
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AISummary))==0
        assert db.scalar(select(func.count()).select_from(AIUsage))==billed
        assert db.scalar(select(func.count()).select_from(ChunkEmbedding))==0
        assert db.scalar(select(func.count()).select_from(IndexJob))==0
        assert db.get(Document,UUID(identifier))
    assert client.post(f'/api/v1/documents/{identifier}/index',json=index_body).status_code==202
    assert client.get(f'/api/v1/documents/{identifier}/index').json()[0]['status']=='completed'


def test_concurrent_imports_cannot_bypass_personal_document_quota(accounts,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client,app=accounts;login(client,'alice')
    # Exercise the DB quota race independently of the new default one-upload admission.
    app.state.settings.upload_max_per_owner=2
    app.state.settings.max_documents_per_owner=1
    barrier=Barrier(2)
    def extraction(*args):
        barrier.wait(timeout=10)
        return ['Safe text for quota test.']
    monkeypatch.setattr('backend.services.documents.run_worker',extraction)
    def send(number):
        return client.post('/api/v1/documents',files={'file':(f'{number}.txt',b'safe text','text/plain')}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(send,[1,2]))
    assert sorted(results)==[201,413]
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Document))==1
    assert not list(app.state.settings.storage_dir.glob('*.part'))


def test_login_ip_limit_applies_across_different_usernames(accounts):
    client,app=accounts;client.headers['X-Documind-Secure']='1'
    statuses=[client.post('/api/v1/auth/login',json={'email':f'unknown{n}@example.test','password':PASSWORD}).status_code for n in range(11)]
    assert statuses[:10]==[401]*10 and statuses[-1]==429


def test_general_user_rate_limit_is_enforced(accounts):
    client,app=accounts;login(client,'alice')
    app.state.settings.requests_per_minute=1
    assert client.get('/api/v1/documents').status_code==200
    assert client.get('/api/v1/documents').status_code==429
