"""Real signatures, durable files, recovery and admissions; synthetic domains only."""
from dataclasses import replace
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update, select

from backend.lite_authority import (AuthorityError,canonical,digest,sign,verify,strict,project,operation_payload,
    OperatorLedger,LocalOperations,OperationalConfirmation,import_view,export_proposal,load_provision,write,read)
from backend.lite_admissions import AdmissionOperation
from backend.auth import hash_password,User
from backend.account_models import PublicRegistrationQuota
from backend.main import create_app
from tests.test_lite_admissions import lite_settings,invitation,send,PASSWORD,COHORT,count
from tests.conftest import BFF_KEY


def keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
    key=Ed25519PrivateKey.generate()
    return key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()),key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()


def operation():
    return AdmissionOperation(uuid4(),COHORT,'a'*64,'b'*64,'lite-test-v1','c'*64,
                              '2026-10-30T00:00:00+00:00',hash_password(PASSWORD))


def proposal(op,phase='reserve',counter=0,*,instance,challenge):
    return {'version':1,'instance':instance,'cohort':str(COHORT),'challenge':challenge,
            'operation':operation_payload(op),'phase':phase,'counter':counter,
            'facts':{'reserve':'invitation_and_counter_verified','result':'sql_commit_verified','cancel':'sql_absence_fenced'}[phase]}


def test_signatures_refuse_forgery_and_modified_exports():
    private,public=keypair();other,_=keypair();payload={'version':1,'cohort':str(COHORT)}
    assert verify(sign(payload,private),public)==payload
    for value in (sign(payload,other),{'payload':{**payload,'version':2},'signature':sign(payload,private)['signature']}):
        with pytest.raises(AuthorityError):verify(value,public)
    with pytest.raises(AuthorityError):strict(b'{"approved":true,"approved":false}')


def test_account_cli_configuration_error_does_not_echo_inputs(monkeypatch):
    from backend import account_admin
    def invalid():raise ValueError('synthetic-sensitive-dsn-never-real')
    monkeypatch.setattr(account_admin,'Settings',invalid)
    monkeypatch.setattr('sys.argv',['account-admin','invite','person@example.test'])
    with pytest.raises(SystemExit) as error:account_admin.main()
    assert 'synthetic-sensitive-dsn' not in str(error.value)


@pytest.fixture
def domains(tmp_path):
    if os.name!='posix':pytest.skip('Native POSIX authority domains required; Linux tests cover this')
    if os.geteuid()!=0:pytest.skip('Root/admin and API separation requires isolated Linux root')
    dirs={}
    for name in ('operator','recovery','operator_keys','recovery_keys','export_keys','application','control','outbox'):
        path=tmp_path/name;path.mkdir(mode=0o755 if name=='control' else 0o700);dirs[name]=path
    signing,public=keypair();export,export_public=keypair()
    for name,raw in [('operator_keys/signing',signing),('recovery_keys/key',os.urandom(32)),('export_keys/signing',export)]:
        p=tmp_path/name;p.write_bytes(raw);p.chmod(0o600)
    instance=str(uuid4())
    kwargs=dict(directory=dirs['operator'],recovery=dirs['recovery'],signing_key=dirs['operator_keys']/'signing',
                recovery_key=dirs['recovery_keys']/'key',instance=instance,cohort=str(COHORT),export_public_key=export_public)
    ledger=OperatorLedger(**kwargs);ledger.initialize()
    store=LocalOperations(dirs['application'],0)
    adapter=OperationalConfirmation(store=store,control=dirs['control'],instance=instance,cohort=str(COHORT),public_key=public)
    def install(envelope):
        import_view(envelope,control=dirs['control'],store=store,instance=instance,cohort=str(COHORT),public_key=public)
    install(ledger.refresh(adapter.nonce,confirmation=adapter.nonce))
    return dict(dirs=dirs,instance=instance,ledger=ledger,store=store,adapter=adapter,install=install,
                signing=signing,public=public,export=export,export_public=export_public,kwargs=kwargs)


def reserve(d,op=None):
    op=op or operation();d['adapter'].prepare(op)
    assert not d['adapter'].reservation_verified(op,0)
    request=proposal(op,instance=d['instance'],challenge=d['adapter'].nonce)
    signed=sign(request,d['export'])
    receipt=d['ledger'].approve(signed,confirmation=str(op.id),reference='synthetic-operator')
    d['install'](receipt)
    return op,signed,receipt


def test_ledger_persistence_sequence_duplicate_and_recovery(domains):
    d=domains;op,signed,receipt=reserve(d)
    reopened=OperatorLedger(**d['kwargs'])
    recovered=reopened.recover()
    assert len(recovered['events'])==1
    assert project(recovered['events'],d['instance'],str(COHORT))[1]==0
    again=reopened.approve(signed,confirmation=str(op.id),reference='synthetic-operator')
    assert again['payload']['sequence']==1
    assert reopened.recover()['events']==recovered['events']
    with pytest.raises(AuthorityError):
        reopened.approve(sign({**signed['payload'],'counter':1},d['export']),confirmation=str(op.id),reference='op')
    wrong={**signed['payload'],'cohort':str(uuid4())}
    with pytest.raises(AuthorityError):reopened.approve(sign(wrong,d['export']),confirmation=str(op.id),reference='op')
    assert d['adapter'].reservation_verified(op,0)
    # A new interpreter has no in-memory ledger or proposal cache to rely on.
    target=d['dirs']['outbox']/'recovered-by-new-process.json'
    command=[sys.executable,'-m','tools.lite_authority','--instance',d['instance'],'--cohort',str(COHORT),
        'operator-recover','--ledger',str(d['dirs']['operator']),'--recovery',str(d['dirs']['recovery']),
        '--signing-key',str(d['kwargs']['signing_key']),'--recovery-key',str(d['kwargs']['recovery_key']),
        '--export-public-key',d['export_public'],'--out',str(target)]
    environment={**os.environ,'PYTHONPATH':'/testdeps:/lab','PYTHONDONTWRITEBYTECODE':'1'}
    child=subprocess.run(command,capture_output=True,text=True,env=environment,cwd='/lab',timeout=15)
    assert child.returncode==0,child.stderr
    assert strict(target.read_bytes())==recovered
    child=subprocess.run([sys.executable,'-c',
        'import sys;from backend.lite_authority import LocalOperations;print(LocalOperations(sys.argv[1],0).all()[0].id)',
        str(d['dirs']['application'])],capture_output=True,text=True,env=environment,cwd='/lab',timeout=15)
    assert child.returncode==0 and child.stdout.strip()==str(op.id)


def test_operator_gesture_and_export_origin_required(domains):
    d=domains;op=operation();d['adapter'].prepare(op);d['adapter'].reservation_verified(op,0)
    payload=proposal(op,instance=d['instance'],challenge=d['adapter'].nonce)
    with pytest.raises(AuthorityError):d['ledger'].approve(sign(payload,d['export']),confirmation='',reference='op')
    with pytest.raises(AuthorityError):d['ledger'].approve(sign(payload,keypair()[0]),confirmation=str(op.id),reference='op')
    assert not list(d['dirs']['operator'].glob('event-*.json'))


def test_copy_failure_does_not_acknowledge_and_identical_retry_recovers(domains,monkeypatch):
    d=domains;op=operation();d['adapter'].prepare(op);d['adapter'].reservation_verified(op,0)
    signed=sign(proposal(op,instance=d['instance'],challenge=d['adapter'].nonce),d['export'])
    with monkeypatch.context() as patch:
        patch.setattr(d['ledger'],'_backup',lambda events: (_ for _ in ()).throw(OSError('synthetic disconnected recovery')))
        with pytest.raises(OSError):d['ledger'].approve(signed,confirmation=str(op.id),reference='op')
    assert len(list(d['dirs']['operator'].glob('event-*.json')))==1
    assert not d['adapter'].reservation_verified(op,0)
    with pytest.raises(AuthorityError):d['ledger'].refresh(d['adapter'].nonce,confirmation=d['adapter'].nonce)
    d['install'](d['ledger'].approve(signed,confirmation=str(op.id),reference='op'))
    assert d['adapter'].reservation_verified(op,0)


def test_old_registry_and_altered_registry_are_not_current(domains):
    d=domains;old=d['dirs']['operator'].parent/'old-registry';shutil.copytree(d['dirs']['operator'],old)
    op,_,_=reserve(d)
    kwargs={**d['kwargs'],'directory':old}
    with pytest.raises(AuthorityError):OperatorLedger(**kwargs).refresh(d['adapter'].nonce,confirmation=d['adapter'].nonce)
    # An altered copy never overwrites the original proof.
    altered=d['dirs']['operator'].parent/'altered';shutil.copytree(d['dirs']['operator'],altered)
    event=altered/'event-00000001.json';value=strict(event.read_bytes());value['payload']['sequence']=7
    event.write_bytes(canonical(value))
    with pytest.raises(AuthorityError):OperatorLedger(**{**d['kwargs'],'directory':altered}).refresh(d['adapter'].nonce,confirmation=d['adapter'].nonce)


def test_replay_old_boot_and_wrong_operation_refused(domains):
    d=domains;op,_,receipt=reserve(d)
    with pytest.raises(AuthorityError):d['install'](receipt)
    changed={**receipt['payload'],'cohort':str(uuid4())}
    with pytest.raises(AuthorityError):d['install'](sign(changed,d['signing']))
    other=replace(op,id=uuid4())
    with pytest.raises(AuthorityError):d['adapter'].reservation_verified(other,0)
    restarted=OperationalConfirmation(store=d['store'],control=d['dirs']['control'],instance=d['instance'],
        cohort=str(COHORT),public_key=d['public'])
    assert not restarted.ready()
    with pytest.raises(AuthorityError):d['install'](receipt)
    d['install'](d['ledger'].refresh(restarted.nonce,confirmation=restarted.nonce))
    assert restarted.ready() and restarted.reservation_verified(op,0)


def test_local_store_duplicate_conflict_and_no_credentials_export(domains):
    d=domains;op=operation();d['adapter'].prepare(op)
    assert d['adapter'].prepare(op).id==op.id
    with pytest.raises(AuthorityError):d['adapter'].prepare(replace(op,terms_version='different'))
    with pytest.raises(AuthorityError):d['store'].save(replace(op,owner_id=uuid4()))
    opened=LocalOperations(d['dirs']['application'],0)
    assert opened.all()[0].password_hash==op.password_hash
    raw=canonical(proposal(op,instance=d['instance'],challenge=d['adapter'].nonce))
    for secret in (PASSWORD,op.password_hash,op.invitation_digest,op.email_digest):assert secret.encode() not in raw


def test_links_and_permissions_refused(domains):
    d=domains;root=d['dirs']['outbox'];source=root/'source';write(source,b'{}',0)
    link=root/'link';link.symlink_to(source)
    hard=root/'hard';os.link(source,hard)
    for path in (link,hard,source):
        with pytest.raises(AuthorityError):read(path,0)
    unsafe=root/'unsafe';write(unsafe,b'{}',0);unsafe.chmod(0o666)
    with pytest.raises(AuthorityError):read(unsafe,0)
    # A root-owned file below an API-owned directory can be renamed by the API.
    parent=root/'api-owned-parent';parent.mkdir(mode=0o700)
    evidence=parent/'root-file';evidence.write_bytes(b'{}');evidence.chmod(0o644)
    os.chown(parent,10001,10001)
    with pytest.raises(AuthorityError):read(evidence,0,private=False)


@pytest.fixture
def real_admissions(app,domains):
    d=domains
    settings=lite_settings(app.state.settings,lite_instance_id=UUID(d['instance']))
    application=create_app(settings,lite_confirmation=d['adapter']);application.state.mail_sender=lambda *args:None
    with application.state.sessions() as db:
        db.execute(update(PublicRegistrationQuota).values(closed=False));db.commit()
    with TestClient(application) as client:
        client.headers.update({'X-API-Key':BFF_KEY,'X-Documind-Secure':'1'})
        yield client,application,d


def prepare_http(env):
    client,app,d=env;body=invitation(app)
    result=send(client,body);assert result.status_code==202,result.text
    identifier=result.json()['operation_id'];op=next(o for o in d['store'].all() if str(o.id)==identifier)
    return {**body,'operation_id':identifier},op


def confirm_phase(env,op,phase):
    client,app,d=env
    with app.state.sessions() as session:
        request=export_proposal(d['adapter'],op.id,phase,session,d['export'])
    receipt=d['ledger'].approve(request,confirmation=str(op.id),reference='synthetic-operator')
    d['install'](receipt)


def test_real_authority_sql_commit_activation_and_crash(real_admissions):
    client,app,d=real_admissions;body,op=prepare_http(real_admissions)
    with app.state.sessions() as session:
        with pytest.raises(AuthorityError):export_proposal(d['adapter'],op.id,'result',session,d['export'])
    confirm_phase(real_admissions,op,'reserve')
    assert send(client,body).json()['state']=='result_pending' and count(app)==1
    assert client.post('/api/v1/auth/login',json={'email':body['email'],'password':PASSWORD}).status_code==401
    confirm_phase(real_admissions,op,'result')
    assert send(client,body).status_code==201
    assert client.post('/api/v1/auth/login',json={'email':body['email'],'password':PASSWORD}).status_code==200
    restarted=OperationalConfirmation(store=LocalOperations(d['dirs']['application'],0),control=d['dirs']['control'],
        instance=d['instance'],cohort=str(COHORT),public_key=d['public'])
    app.state.lite_confirmation=restarted
    assert send(client,body).status_code==503
    d['install'](d['ledger'].refresh(restarted.nonce,confirmation=restarted.nonce))
    assert send(client,body).status_code==201 and count(app)==1


def test_five_and_concurrent_last_admission_with_durable_authority(real_admissions):
    client,app,d=real_admissions
    for _ in range(4):
        body,op=prepare_http(real_admissions);confirm_phase(real_admissions,op,'reserve')
        assert send(client,body).status_code==202
        confirm_phase(real_admissions,op,'result');assert send(client,body).status_code==201
    body,op=prepare_http(real_admissions);confirm_phase(real_admissions,op,'reserve')
    other_body,other_op=prepare_http(real_admissions)
    with pytest.raises(AuthorityError):confirm_phase(real_admissions,other_op,'reserve')
    barrier=__import__('threading').Barrier(2)
    def request(payload):barrier.wait(timeout=10);return send(client,payload)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(request,[body,other_body]))
    assert results[0].status_code==202 and results[1].status_code in (202,403) and count(app)==5
    if results[1].status_code==202:assert results[1].json()['created'] is False
    confirm_phase(real_admissions,op,'result');assert send(client,body).status_code==201
    assert send(client,other_body).status_code==403
    assert send(client,invitation(app)).status_code==403


def test_uncertain_reservation_and_signed_cancellation(real_admissions):
    client,app,d=real_admissions;body,op=prepare_http(real_admissions)
    confirm_phase(real_admissions,op,'reserve')
    with pytest.raises(AuthorityError):d['adapter'].reconcile(op,{'account_absent':True})
    confirm_phase(real_admissions,op,'cancel')
    assert send(client,body).status_code==409 and count(app)==0
    body2,op2=prepare_http(real_admissions);confirm_phase(real_admissions,op2,'reserve')
    assert send(client,body2).status_code==202 and count(app)==1


def test_real_commit_uncertainty_preserves_capacity(real_admissions,monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import SQLAlchemyError
    from backend.account_models import WorkspaceMembership
    client,app,d=real_admissions;body,op=prepare_http(real_admissions);confirm_phase(real_admissions,op,'reserve')
    original=Session.commit
    def commit(session):
        admitting=any(isinstance(o,WorkspaceMembership) for o in session.new)
        original(session)
        if admitting:raise SQLAlchemyError('synthetic lost acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',commit)
        assert send(client,body).status_code==503
    assert count(app)==1 and send(client,body).status_code==409
    with app.state.sessions() as session:
        with pytest.raises(AuthorityError):export_proposal(d['adapter'],op.id,'cancel',session,d['export'])
    confirm_phase(real_admissions,op,'result')
    assert send(client,body).status_code==201 and count(app)==1


def test_cli_requires_explicit_gesture_and_does_not_leak(domains,capsys):
    from tools.lite_authority import main
    d=domains;op=operation();d['adapter'].prepare(op);d['adapter'].reservation_verified(op,0)
    path=d['dirs']['outbox']/'request.json'
    write(path,canonical(sign(proposal(op,instance=d['instance'],challenge=d['adapter'].nonce),d['export'])),0)
    flags=['--instance',d['instance'],'--cohort',str(COHORT)]
    common=['--ledger',str(d['dirs']['operator']),'--recovery',str(d['dirs']['recovery']),
        '--signing-key',str(d['kwargs']['signing_key']),'--recovery-key',str(d['kwargs']['recovery_key']),
        '--export-public-key',d['export_public']]
    assert main([*flags,'operator-review',*common,'--input',str(path)])==0
    assert not list(d['dirs']['operator'].glob('event-*.json'))
    assert main([*flags,'operator-confirm',*common,'--input',str(path),'--confirm','wrong','--reference','op',
                 '--out',str(d['dirs']['outbox']/'receipt.json')])==1
    assert main([*flags,'operator-confirm',*common,'--input',str(path),'--confirm',str(op.id),'--reference','op',
                 '--out',str(d['dirs']['outbox']/'receipt.json')])==0
    assert main([*flags,'operator-recover',*common,'--out',str(d['dirs']['outbox']/'recovered.json')])==0
    assert len(strict((d['dirs']['outbox']/'recovered.json').read_bytes())['events'])==1
    output=capsys.readouterr().out
    assert PASSWORD not in output and d['signing'].hex() not in output


def test_real_application_uid_cannot_sign_import_or_edit_authority(domains,tmp_path,monkeypatch):
    d=domains;uid=10001
    # Only new pytest/lab ancestors, never an existing workspace or system directory.
    for parent in (tmp_path,*tmp_path.parents):
        if parent in (Path('/tmp'),Path('/')):break
        parent.chmod(0o755)
    store_path=tmp_path/'api-uid-store';store_path.mkdir(mode=0o700);os.chown(store_path,uid,uid)
    from backend.config import Settings
    base=Settings(_env_file=None,recovery_state_path=tmp_path/'ready')
    settings=lite_settings(base,lite_instance_id=UUID(d['instance']),lite_authority_manifest=d['dirs']['control']/'manifest.json')
    manifest={'version':1,'instance':d['instance'],'cohort':str(COHORT),'api_uid':uid,
        'store':str(store_path),'control':str(d['dirs']['control']),'authority_public_key':d['public'],
        'export_private_key':str(d['dirs']['export_keys']/'signing'),'export_public_key':d['export_public'],
        'database_sha256':hashlib.sha256(settings.database_url.encode()).hexdigest()}
    # Simulated deployment REVIEW for validating the loader in this lab only.
    manifest['independence']=d['ledger'].attest_domains(str(uuid4()),str(uuid4()),str(uuid4()),
        reference=str(uuid4()),scope='deployment',confirmation=d['instance'])
    write(settings.lite_authority_manifest,canonical(manifest),0,public=True)
    unsuitable={**manifest,'independence':sign({**manifest['independence']['payload'],'scope':'laboratory'},d['signing'])}
    write(settings.lite_authority_manifest,canonical(unsuitable),0,replace=True,public=True)
    with pytest.raises(AuthorityError):load_provision(settings,administrative=True)
    write(settings.lite_authority_manifest,canonical(manifest),0,replace=True,public=True)
    # Root must not select the API runtime even with a valid manifest.
    with pytest.raises(AuthorityError):load_provision(settings)
    script='''import sys,json
from backend.config import Settings
from backend.lite_authority import provisioned_adapter,load_provision
s=Settings(_env_file=None,**json.loads(sys.stdin.readline()))
a=provisioned_adapter(s)
print(json.dumps({'nonce':a.nonce}),flush=True)
sys.stdin.readline()
denied=[]
for name,path,mode in [('edit',str(a.control/'accepted.json'),'wb'),('sign',sys.argv[1],'rb')]:
 try:
  with open(path,mode):pass
 except PermissionError:denied.append(name)
try:load_provision(s,administrative=True)
except ValueError:denied.append('administrative_import')
print(json.dumps({'ready':a.ready(),'denied':denied}),flush=True)
'''
    environment={**os.environ,'PYTHONPATH':'/testdeps:/lab','PYTHONDONTWRITEBYTECODE':'1'}
    child=subprocess.Popen([sys.executable,'-c',script,str(d['kwargs']['signing_key'])],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        user=uid,group=uid,env=environment,cwd='/lab')
    try:
        values=settings.model_dump(mode='json');values['bff_service_key']=BFF_KEY;values['smtp_password']=''
        child.stdin.write(json.dumps(values)+'\n');child.stdin.flush()
        line=child.stdout.readline()
        assert line,child.stderr.read()
        nonce=json.loads(line)['nonce']
        store=LocalOperations(store_path,uid)
        from tools.lite_authority import main
        monkeypatch.setattr('backend.config.Settings',lambda **kwargs:settings)
        inbox=d['dirs']['control']/'inbox';inbox.mkdir(mode=0o700)
        incoming=inbox/'incoming.json'
        write(incoming,canonical(d['ledger'].refresh(nonce,confirmation=nonce)),0)
        flags=['--instance',d['instance'],'--cohort',str(COHORT)]
        assert main([*flags,'app-challenge','--manifest',str(settings.lite_authority_manifest),
                     '--out',str(d['dirs']['outbox']/'challenge.json')])==0
        assert main([*flags,'app-import','--manifest',str(settings.lite_authority_manifest),'--input',str(incoming)])==0
        assert main([*flags,'app-import','--manifest',str(settings.lite_authority_manifest),'--input',str(incoming)])==1
        child.stdin.write('verify\n');child.stdin.flush()
        result=json.loads(child.stdout.readline());child.wait(timeout=10)
        assert result=={'ready':True,'denied':['edit','sign','administrative_import']}
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)


def test_root_provisioning_cannot_be_app_owned_or_ambiguous(domains,tmp_path):
    from backend.config import Settings
    d=domains
    settings=lite_settings(Settings(_env_file=None,recovery_state_path=tmp_path/'ready'),
        lite_instance_id=UUID(d['instance']),lite_authority_manifest=d['dirs']['control']/'bad.json')
    write(settings.lite_authority_manifest,b'{}',0,public=True)
    with pytest.raises(AuthorityError):load_provision(settings,administrative=True)
    settings.lite_authority_manifest.chmod(0o666)
    with pytest.raises(AuthorityError):load_provision(settings,administrative=True)


def test_old_duplicate_cannot_roll_back_recovery_anchor(domains):
    d=domains;op,request,receipt=reserve(d)
    old=d['dirs']['operator'].parent/'old-reserved';shutil.copytree(d['dirs']['operator'],old)
    result=sign(proposal(op,'result',1,instance=d['instance'],challenge=d['adapter'].nonce),d['export'])
    d['ledger'].approve(result,confirmation=str(op.id),reference='op')
    before=(d['dirs']['recovery']/'current.json').read_bytes()
    with pytest.raises(AuthorityError):
        OperatorLedger(**{**d['kwargs'],'directory':old}).approve(request,confirmation=str(op.id),reference='op')
    assert (d['dirs']['recovery']/'current.json').read_bytes()==before


def test_forged_view_and_wrong_state_never_authorize(domains):
    d=domains;op=operation();d['adapter'].prepare(op);d['adapter'].reservation_verified(op,0)
    request=sign(proposal(op,'result',1,instance=d['instance'],challenge=d['adapter'].nonce),d['export'])
    with pytest.raises(AuthorityError):d['ledger'].approve(request,confirmation=str(op.id),reference='op')
    value=d['ledger'].refresh(d['adapter'].nonce,confirmation=d['adapter'].nonce)['payload']
    with pytest.raises(AuthorityError):d['install'](sign(value,d['export']))
    with pytest.raises(AuthorityError):OperatorLedger(**{**d['kwargs'],'export_public_key':d['public']})


def test_corrupt_or_wrong_key_recovery_is_not_acquitted(domains,tmp_path):
    d=domains;reserve(d)
    recovery=tmp_path/'corrupted-copy';shutil.copytree(d['dirs']['recovery'],recovery)
    current=verify(strict((recovery/'current.json').read_bytes()),d['public'])
    cipher=recovery/current['file'];raw=cipher.read_bytes();cipher.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    broken=OperatorLedger(**{**d['kwargs'],'recovery':recovery})
    with pytest.raises(AuthorityError):broken.recover()
    other=tmp_path/'other-key';other.mkdir(mode=0o700);key=other/'key';key.write_bytes(os.urandom(32));key.chmod(0o600)
    with pytest.raises(AuthorityError):OperatorLedger(**{**d['kwargs'],'recovery_key':key}).recover()


def test_independent_recovery_rebuilds_only_a_new_registry(domains,tmp_path):
    d=domains;reserve(d)
    original=d['ledger']._events()
    fresh=tmp_path/'rebuilt-operator';fresh.mkdir(mode=0o700)
    recovered=OperatorLedger(**{**d['kwargs'],'directory':fresh})
    with pytest.raises(AuthorityError):recovered.restore_empty(confirmation='not-confirmed')
    assert recovered.restore_empty(confirmation=d['instance'])=={
        'status':'registry_recovered','sequence':1,'opening_authorized':False}
    assert recovered._events()==original and d['ledger']._events()==original
    with pytest.raises(AuthorityError):recovered.restore_empty(confirmation=d['instance'])


def test_domain_attestation_requires_distinct_domains_and_explicit_review(domains):
    d=domains;identity=str(uuid4())
    with pytest.raises(AuthorityError):d['ledger'].attest_domains(identity,identity,str(uuid4()),
        reference=str(uuid4()),scope='deployment',confirmation=d['instance'])
    with pytest.raises(AuthorityError):d['ledger'].attest_domains(str(uuid4()),str(uuid4()),str(uuid4()),
        reference=str(uuid4()),scope='deployment',confirmation='')
