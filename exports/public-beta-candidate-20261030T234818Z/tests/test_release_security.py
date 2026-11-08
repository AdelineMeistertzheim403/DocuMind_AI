"""Security authorization is independent of schema compatibility. Fictitious releases only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest
import yaml

from tools import deploy_production as deploy
from tools import release_security as security
from tools.release_manifest import validate_release
from tests.test_deployment import release, simulation


def approved_bundle(bundle,candidate,trust):
    bundle.mkdir(parents=True,exist_ok=True)
    candidate={**candidate,'security_profile':security.PROFILE}
    (bundle/'release.json').write_text(json.dumps(candidate))
    for name in security.BUNDLE_FILES-{'release.json'}:
        if name=='compose.production.yaml':
            source=Path(name)
        elif name.endswith(('.service','.timer')):
            source=Path('ops/systemd')/name
        else:
            source=Path('tools')/name
        shutil.copyfile(source,bundle/name)
    security.make_statement(bundle,candidate,{'repository':'example/documind','workflow':'.github/workflows/ci.yml',
        'run_id':'123','run_attempt':'1'})
    data,digest=security.validate_statement(bundle,candidate)
    trust['releases'][candidate['git_sha']]={'profile':security.PROFILE,'attestation_sha256':digest,**data['producer']}
    return candidate


@pytest.fixture
def approved(tmp_path,monkeypatch):
    trust={'format':1,'releases':{}}
    bundle=tmp_path/'release'
    candidate=approved_bundle(bundle,release('0007'),trust)
    monkeypatch.setattr(security,'load_trust',lambda:trust)
    return bundle,candidate,trust


def test_controller_from_another_release_is_rejected(tmp_path):
    trust={'format':1,'releases':{}}
    first=tmp_path/'release-a'
    second=tmp_path/'release-b'
    first_release=approved_bundle(first,release('0007','a'*40),trust)
    second_release=approved_bundle(second,release('0007','b'*40),trust)
    (first/'backup_local.py').write_text('different historical backup helper')
    (first/security.STATEMENT).unlink()
    security.make_statement(first,first_release,{'repository':'example/documind',
        'workflow':'.github/workflows/ci.yml','run_id':'123','run_attempt':'1'})
    controller=tmp_path/'controller'
    controller.mkdir()
    for name in deploy.CONTROLLER_FILES:
        shutil.copyfile(first/name,controller/name)
    with pytest.raises(deploy.DeploymentError,match='Incompatible deployment controller'):
        deploy.verify_controller_bundle_compatibility(controller,second,second_release)


def test_controller_helper_must_match_attested_bundle(approved,tmp_path):
    bundle,candidate,_=approved
    controller=tmp_path/'controller'
    controller.mkdir()
    for name in deploy.CONTROLLER_FILES:
        shutil.copyfile(bundle/name,controller/name)
    (controller/'backup_local.py').write_text('unattested helper')
    with pytest.raises(deploy.DeploymentError,match='differs from the attested candidate'):
        deploy.verify_controller_bundle_compatibility(controller,bundle,candidate)


@pytest.mark.parametrize('tamper',['missing_file','systemd_missing_script'])
def test_operational_inventory_requires_every_attested_file_and_unit_target(approved,tamper):
    bundle,candidate,_=approved
    if tamper=='missing_file':
        (bundle/'verify_snapshot.py').unlink()
    else:
        unit=bundle/'documind-backup.service'
        unit.write_text(unit.read_text().replace(
            '/srv/documind-ai/current/backup_production.py',
            '/srv/documind-ai/current/absent_backup.py'))
        (bundle/security.STATEMENT).unlink()
        security.make_statement(bundle,candidate,{'repository':'example/documind',
            'workflow':'.github/workflows/ci.yml','run_id':'123','run_attempt':'1'})
    with pytest.raises(security.SecurityError):
        security.validate_operational_bundle(bundle,candidate)


@pytest.mark.parametrize('claim',[None,'public-beta-2026-10-v1','invented-profile'])
def test_schema_or_self_declared_profile_does_not_authorize_rollback(claim):
    candidate=release('0007')
    if claim:candidate['security_profile']=claim
    assert not deploy.can_rollback(candidate,'0007')


def test_attested_rollback_requires_schema_and_independent_approval(approved):
    bundle,candidate,_=approved
    assert security.authorize(bundle,candidate)['independently_approved'] is True
    assert deploy.can_rollback(candidate,'0007',security_verified=True)
    assert not deploy.can_rollback(candidate,'0006',security_verified=True)


@pytest.mark.parametrize('tamper',['sha','images','profile','file','missing','statement','unknown','no-trust','producer','duplicate'])
def test_security_evidence_refuses_missing_inconsistent_or_unapproved(approved,tamper):
    bundle,candidate,trust=approved
    if tamper=='sha':candidate['git_sha']='c'*40
    elif tamper=='images':candidate['images']['backend']=candidate['images']['backend'][:-64]+'f'*64
    elif tamper=='profile':candidate.pop('security_profile')
    elif tamper=='file':(bundle/'deploy_production.py').write_text('self-certified old deployer')
    elif tamper=='missing':(bundle/'public_beta_policy.py').unlink()
    elif tamper=='statement':(bundle/security.STATEMENT).unlink()
    elif tamper=='unknown':candidate['security_profile']='unknown'
    elif tamper=='no-trust':trust['releases'].clear()
    elif tamper=='producer':trust['releases'][candidate['git_sha']]['run_id']='999'
    elif tamper=='duplicate':(bundle/security.STATEMENT).write_text('{"format":1,"format":1}')
    with pytest.raises(security.SecurityError):security.authorize(bundle,candidate)


def test_self_authored_statement_does_not_grant_root_approval(approved):
    bundle,candidate,trust=approved
    (bundle/'deploy_production.py').write_text('old code with a forged new marker')
    (bundle/security.STATEMENT).unlink()
    security.make_statement(bundle,candidate,{'repository':'example/documind','workflow':'.github/workflows/ci.yml','run_id':'123','run_attempt':'1'})
    with pytest.raises(security.SecurityError,match='independently approved'):
        security.authorize(bundle,candidate)


def test_legacy_attestation_remains_valid_for_approved_rollback_only(tmp_path,monkeypatch):
    bundle=tmp_path/'legacy-release'
    bundle.mkdir()
    candidate={**release('0007'),'security_profile':security.PROFILE}
    (bundle/'release.json').write_text(json.dumps(candidate))
    for name in security.LEGACY_BUNDLE_FILES-{'release.json'}:
        source=Path(name) if name=='compose.production.yaml' else Path('tools')/name
        shutil.copyfile(source,bundle/name)
    producer={'repository':'example/documind','workflow':'.github/workflows/ci.yml',
              'run_id':'123','run_attempt':'1'}
    statement={'format':1,'profile':security.PROFILE,'git_sha':candidate['git_sha'],
        'schema_revision':candidate['schema_revision'],'images':candidate['images'],
        'producer':producer,'bundle_sha256':{
            name:hashlib.sha256(security.read_file(bundle/name)).hexdigest()
            for name in sorted(security.LEGACY_BUNDLE_FILES)}}
    (bundle/security.STATEMENT).write_text(json.dumps(statement))
    _,digest=security.validate_statement(bundle,candidate)
    trust={'format':1,'releases':{candidate['git_sha']:{
        'profile':security.PROFILE,'attestation_sha256':digest,**producer}}}
    monkeypatch.setattr(security,'load_trust',lambda:trust)
    assert security.authorize(bundle,candidate)['independently_approved'] is True


@pytest.mark.parametrize('label',['missing','wrong','valid'])
def test_images_require_actual_revision_and_security_label(approved,monkeypatch,label):
    _,candidate,_=approved
    labels={'org.opencontainers.image.revision':candidate['git_sha']}
    if label!='missing':labels[security.LABEL]=security.PROFILE if label=='valid' else 'old'
    calls=[]
    def inspect(command):calls.append(command);return json.dumps(labels)
    monkeypatch.setattr(deploy,'run',inspect)
    stack=type('Stack',(),{'release':candidate})()
    if label=='valid':
        deploy.verify_images(stack)
        assert {cmd[3] for cmd in calls}==set(candidate['images'].values())
    else:
        with pytest.raises(deploy.DeploymentError,match='security profile'):deploy.verify_images(stack)


@pytest.mark.parametrize('manual,history',[(True,False),(False,True)])
def test_old_schema_0007_target_rejected_before_service_changes(simulation,monkeypatch,manual,history):
    args,events,state,bundle=simulation
    args.rollback=manual;state.update(revision='0007',public_users=history,issued_count=int(history),closed=True)
    (bundle/'release.json').write_text(json.dumps(release('0007')))
    old=deploy.Stack(args.root,bundle.parent/'prior',release('0007',sha='b'*40))
    monkeypatch.setattr(deploy,'current_stack',lambda *args:old)
    monkeypatch.setattr(deploy,'check_public_quota',lambda stack:{'closed':True,'issued_count':int(history)})
    with pytest.raises(deploy.DeploymentError,match='security profile'):deploy.execute(args,{})
    assert not events


@pytest.mark.parametrize('flag',['allow_migration','initialize','approve_public_beta'])
def test_flags_cannot_authorize_a_legacy_manual_rollback(simulation,flag):
    args,events,state,bundle=simulation
    args.rollback=True;setattr(args,flag,True)
    with pytest.raises(deploy.DeploymentError):deploy.execute(args,{})
    assert not events


@pytest.mark.parametrize('safe_previous',[False,True])
def test_automatic_restart_requires_independent_approval_even_disabled(simulation,monkeypatch,safe_previous):
    args,events,state,bundle=simulation
    state.update(revision='0007',public_users=True,issued_count=2,closed=True,fail_start=True)
    trust={'format':1,'releases':{}}
    candidate=approved_bundle(bundle,release('0007'),trust)
    prior=bundle.parent/'prior';prior_release=release('0007',sha='b'*40)
    if safe_previous:prior_release=approved_bundle(prior,prior_release,trust)
    old=deploy.Stack(args.root,prior,prior_release)
    monkeypatch.setattr(deploy,'current_stack',lambda *args:old)
    monkeypatch.setattr(security,'load_trust',lambda:trust)
    monkeypatch.setattr(deploy,'check_public_quota',lambda stack:{'closed':True,'issued_count':2})
    report={}
    with pytest.raises(deploy.DeploymentError,match='Simulated startup'):deploy.execute(args,report)
    assert report['previous_application_restarted'] is safe_previous
    assert (args.root/'var/security-maintenance.json').exists() is not safe_previous
    assert any(name=='prior' and cmd and cmd[0]=='up' for name,cmd in events) is safe_previous
    assert not any(cmd and ('downgrade' in cmd or 'down' in cmd) for _,cmd in events)


def test_approved_manual_rollback_disabled_public_history_keeps_database(simulation,monkeypatch):
    args,events,state,bundle=simulation
    args.rollback=True;state.update(revision='0007',public_users=True,issued_count=2,closed=True)
    trust={'format':1,'releases':{}};approved_bundle(bundle,release('0007'),trust)
    monkeypatch.setattr(security,'load_trust',lambda:trust)
    monkeypatch.setattr(deploy,'check_public_quota',lambda stack:{'closed':True,'issued_count':2})
    old=deploy.Stack(args.root,bundle.parent/'prior',release('0007',sha='b'*40))
    monkeypatch.setattr(deploy,'current_stack',lambda *_:old)
    report={};deploy.execute(args,report)
    assert report['status']=='success' and report['release_security']['required']
    assert not any(cmd and ('alembic' in cmd or ('up' in cmd and 'db' in cmd)) for _,cmd in events)


def test_revocation_before_automatic_restart_is_effective(simulation,monkeypatch):
    args,events,state,bundle=simulation
    state.update(revision='0007',fail_start=True)
    trust={'format':1,'releases':{}};approved_bundle(bundle,release('0007'),trust)
    prior=bundle.parent/'prior';candidate=approved_bundle(prior,release('0007',sha='b'*40),trust)
    monkeypatch.setattr(security,'load_trust',lambda:trust)
    old=deploy.Stack(args.root,prior,candidate)
    monkeypatch.setattr(deploy,'current_stack',lambda *_:old)
    def fail_backup(*args,**kwargs):
        trust['releases'].pop(candidate['git_sha'])
        raise OSError('fictitious backup failure')
    monkeypatch.setattr(deploy,'create_backup',fail_backup)
    report={}
    with pytest.raises(OSError):deploy.execute(args,report)
    assert report['previous_application_restarted'] is False


def test_bundle_choice_is_independent_of_the_controller(simulation,monkeypatch):
    args,events,state,bundle=simulation
    args.bundle=bundle
    monkeypatch.setattr(deploy,'__file__',str(args.root/'deploy-controls'/'trusted'/'deploy_production.py'))
    deploy.execute(args,{})
    assert any(name=='candidate' for name,_ in events)


@pytest.mark.parametrize('users,count',[(False,2),(True,0)])
def test_disabled_policy_detects_counter_or_public_identity_independently(simulation,monkeypatch,users,count):
    args,events,state,bundle=simulation
    state.update(revision='0007',public_users=users,issued_count=count,closed=True)
    (bundle/'release.json').write_text(json.dumps(release('0007')))
    prior=deploy.Stack(args.root,bundle.parent/'prior',release('0007',sha='b'*40))
    monkeypatch.setattr(deploy,'current_stack',lambda *_:prior)
    monkeypatch.setattr(deploy,'check_public_quota',lambda stack:{'closed':True,'issued_count':count})
    with pytest.raises(deploy.DeploymentError,match='security profile'):deploy.execute(args,{})
    assert not events


@pytest.mark.parametrize('invalid',[None,{}, {'has_public_users':False,'issued_count':-1,'closed':True},
    {'has_public_users':'false','issued_count':0,'closed':True}])
def test_history_failure_never_falls_back_to_legacy(invalid):
    stack=type('Stack',(),{'sql':lambda self,query:json.dumps(invalid)})()
    with pytest.raises(deploy.DeploymentError):deploy.public_history(stack,'0007')


def test_existing_security_maintenance_cannot_be_bypassed_by_ordinary_deploy(simulation):
    args,events,state,bundle=simulation
    path=args.root/'var/security-maintenance.json';path.parent.mkdir();path.write_text('{}')
    with pytest.raises(deploy.DeploymentError,match='security profile'):deploy.execute(args,{})
    assert path.exists() and not events


def test_beta_approval_cannot_restart_a_public_legacy_source_behind_disabled_target(simulation,monkeypatch):
    args,events,state,bundle=simulation
    args.approve_public_beta=True
    state.update(revision='0007',issued_count=0,closed=True)
    (bundle/'release.json').write_text(json.dumps(release('0007')))
    prior=deploy.Stack(args.root,bundle.parent/'prior',release('0007',sha='b'*40))
    monkeypatch.setattr(deploy,'current_stack',lambda *_:prior)
    control_file=args.root.parent/'recovery-state.json'
    control_file.write_text('{"format":1,"state":"ready"}\n',encoding='utf-8')
    from tests.test_public_beta_authorization import configuration, PUBLIC
    monkeypatch.setattr(deploy,'check_config',lambda *args:configuration(PUBLIC,control_file))
    with pytest.raises(deploy.DeploymentError,match='security profile'):deploy.execute(args,{})
    assert not events


def test_backup_resume_and_restart_refuse_security_maintenance(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from tools import backup_production as backup
    marker=tmp_path/'var/security-maintenance.json';marker.parent.mkdir();marker.write_text('{}')
    monkeypatch.setattr(backup,'deployment_lock',lambda root:nullcontext())
    with pytest.raises(backup.BackupError,match='secure_release_recovery_required'):backup.resume(tmp_path,{})
    with pytest.raises(backup.BackupError,match='secure_release_recovery_required'):backup.execute(tmp_path,{})
    active=object.__new__(backup.ActiveRelease);active.root=tmp_path
    active.call=lambda *args:pytest.fail('No application may restart behind the guard')
    with pytest.raises(backup.BackupError):active.restart()
    with pytest.raises(backup.BackupError):active.preflight()


@pytest.mark.parametrize('valid',[True,False])
def test_installed_backup_guard_must_match_approved_bundle(approved,tmp_path,monkeypatch,valid):
    bundle,_,_=approved
    expected=(bundle/'backup_production.py').read_bytes()
    monkeypatch.setattr(security,'read_admin_file',lambda path:(bundle/path.name).read_bytes() if valid else b'old backup code')
    if valid:deploy.check_backup_guard(tmp_path,bundle)
    else:
        with pytest.raises(deploy.DeploymentError,match='backup restart guard'):deploy.check_backup_guard(tmp_path,bundle)


@pytest.mark.parametrize('certified,mode',[(False,'disabled'),(False,'public'),(True,'public'),(True,'disabled')])
def test_routine_backup_rechecks_current_security_without_changing_gate(approved,monkeypatch,certified,mode):
    from tools import backup_production as backup
    bundle,candidate,_=approved
    active=object.__new__(backup.ActiveRelease)
    active.bundle=bundle;active.release=candidate if certified else release('0007');active.env={}
    queries=[]
    def call(*args):
        queries.append(args)
        return json.dumps({'has_public_users':True,'issued_count':2,'closed':False})
    active.call=call
    monkeypatch.setattr(backup,'load_helper',lambda directory,name:security)
    monkeypatch.setattr(backup,'command',lambda *args:json.dumps({'org.opencontainers.image.revision':candidate['git_sha'],security.LABEL:security.PROFILE}))
    config={'services':{'api':{'environment':{'REGISTRATION_MODE':mode}}}}
    if certified:active.authorize_restart(config,'0007')
    else:
        with pytest.raises(backup.BackupError,match='secure_release_approval_required'):active.authorize_restart(config,'0007')
    assert queries and all('UPDATE ' not in str(command) and command[0]=='exec' for command in queries)


@pytest.fixture
def open_synthetic_public_gate(app):
    # This test injects the unsafe state it must reject; fresh migrations stay closed.
    if app.state.engine.dialect.name == 'postgresql':
        from backend.account_models import PublicRegistrationQuota
        with app.state.sessions() as db:
            quota = db.get(PublicRegistrationQuota, 'public')
            assert quota.closed is True
            quota.closed = False
            db.commit()


@pytest.mark.usefixtures('open_synthetic_public_gate')
def test_real_postgresql_history_and_disabled_account_guard(app,approved):
    if app.state.engine.dialect.name!='postgresql':pytest.skip('Requires a new dedicated PostgreSQL database')
    from sqlalchemy import text, event
    from backend.auth import User,hash_password
    from backend.models import now
    from backend.account_models import PublicRegistrationQuota
    from backend.account_admin import registration_control
    from uuid import uuid4
    bundle,candidate,_=approved
    class Live:
        release=candidate
        def sql(self,query):
            with app.state.engine.connect() as connection:return connection.scalar(text(query))
    live=Live();live.bundle=bundle
    assert not deploy.public_history(live,'0007')
    with app.state.sessions() as db:
        # A fictitious blocked pending identity still requires protection, independent of count.
        db.add(User(owner_id=uuid4(),username='blocked-fictitious',email='blocked@example.test',
            password_hash=hash_password('Fictitious-only-password'),registration_kind='public',disabled_at=now()))
        db.commit()
        assert db.get(PublicRegistrationQuota,'public').issued_count==0
    assert deploy.public_history(live,'0007')
    with pytest.raises(deploy.DeploymentError,match='closed'):deploy.authorize_start(live,'0007')
    with app.state.sessions() as db:registration_control(db,app.state.settings,'close',execute=True)
    queries=[]
    def observe(connection,cursor,statement,*args):queries.append(statement)
    event.listen(app.state.engine,'before_cursor_execute',observe)
    try:assert deploy.authorize_start(live,'0007')['independently_approved']
    finally:event.remove(app.state.engine,'before_cursor_execute',observe)
    assert queries and all(query.lstrip().upper().startswith('SELECT') for query in queries)


def test_workflows_use_current_controller_and_bind_ci_statement():
    ci=yaml.load(Path('.github/workflows/ci.yml').read_text(),Loader=yaml.BaseLoader)
    workflow=yaml.load(Path('.github/workflows/deploy.yml').read_text(),Loader=yaml.BaseLoader)
    publish=ci['jobs']['publish']
    assert publish['needs']==['python','windows','frontend']
    builds=[s for s in publish['steps'] if s.get('uses','').startswith('docker/build-push-action@')]
    assert len(builds)==3 and all(security.PROFILE in s['with']['labels'] for s in builds)
    creation=next(s['run'] for s in publish['steps'] if s.get('name')=='Create digest-pinned release bundle')
    assert 'release_security.py create release-bundle' in creation
    for name in ('verify_snapshot.py','validate_restore.py','retention_production.py',
                 'monitor_production.py','gmail_monitor_alert.py',
                 'documind-backup.service','documind-monitor.service','documind-retention.service'):
        assert name in security.BUNDLE_FILES and name in creation
    rollout=next(s['run'] for s in workflow['jobs']['deploy']['steps'] if s.get('id')=='rollout')
    staging=next(s['run'] for s in workflow['jobs']['deploy']['steps']
                 if s.get('name')=='Stage reviewed release without touching other applications')
    assert 'cp release-bundle/deploy_production.py' in staging
    assert "python3 '$CONTROL/deploy_production.py' --bundle '$TARGET'" in rollout
    assert 'deployment-reports/$RELEASE_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT.json' in workflow['jobs']['deploy']['steps'][-2]['run']
    assert "python3 '$TARGET/deploy_production.py'" not in rollout


def test_systemd_release_templates_target_atomic_current_release():
    for name,script in (
        ('documind-backup.service','backup_production.py'),
        ('documind-backup-alert.service','backup_production.py'),
        ('documind-monitor.service','monitor_production.py'),
        ('documind-retention.service','retention_production.py'),
    ):
        unit=(Path('ops/systemd')/name).read_text()
        assert f'/srv/documind-ai/current/{script}' in unit
        assert '/srv/documind-ai/ops/' not in unit


def test_actual_workflow_artifact_validation_on_generated_bundle(approved,tmp_path,monkeypatch):
    bundle,candidate,_=approved
    shutil.copytree(bundle,tmp_path/'release-bundle')
    workflow=yaml.load(Path('.github/workflows/deploy.yml').read_text(),Loader=yaml.BaseLoader)
    step=next(s for s in workflow['jobs']['deploy']['steps'] if s.get('name')=='Validate the immutable release')
    code='\n'.join(step['run'].splitlines()[1:-1])
    monkeypatch.chdir(tmp_path)
    for key,value in {'RELEASE_SHA':candidate['git_sha'],'CI_RUN_ID':'123','GITHUB_REPOSITORY':'example/documind',
                      'OPERATION':'rollback','APPROVE_PUBLIC_BETA':'true'}.items():monkeypatch.setenv(key,value)
    exec(compile(code,'reviewed-workflow-validation','exec'),{})


def test_actual_workflow_allows_legacy_attestation_only_for_rollback(tmp_path,monkeypatch):
    bundle=tmp_path/'release-bundle'
    bundle.mkdir()
    candidate={**release('0007'),'security_profile':security.PROFILE}
    (bundle/'release.json').write_text(json.dumps(candidate))
    for name in security.LEGACY_BUNDLE_FILES-{'release.json'}:
        source=Path(name) if name=='compose.production.yaml' else Path('tools')/name
        shutil.copyfile(source,bundle/name)
    producer={'repository':'example/documind','workflow':'.github/workflows/ci.yml',
              'run_id':'123','run_attempt':'1'}
    statement={'format':1,'profile':security.PROFILE,'git_sha':candidate['git_sha'],
        'schema_revision':candidate['schema_revision'],'images':candidate['images'],
        'producer':producer,'bundle_sha256':{
            name:hashlib.sha256(security.read_file(bundle/name)).hexdigest()
            for name in sorted(security.LEGACY_BUNDLE_FILES)}}
    (bundle/security.STATEMENT).write_text(json.dumps(statement))
    workflow=yaml.load(Path('.github/workflows/deploy.yml').read_text(),Loader=yaml.BaseLoader)
    step=next(s for s in workflow['jobs']['deploy']['steps'] if s.get('name')=='Validate the immutable release')
    code='\n'.join(step['run'].splitlines()[1:-1])
    monkeypatch.chdir(tmp_path)
    values={'RELEASE_SHA':candidate['git_sha'],'CI_RUN_ID':'123','GITHUB_REPOSITORY':'example/documind',
            'OPERATION':'rollback','APPROVE_PUBLIC_BETA':'false'}
    for key,value in values.items():monkeypatch.setenv(key,value)
    exec(compile(code,'reviewed-legacy-rollback-validation','exec'),{})
    monkeypatch.setenv('OPERATION','deploy')
    with pytest.raises((AssertionError,security.SecurityError)):
        exec(compile(code,'reviewed-legacy-deploy-validation','exec'),{})


@pytest.mark.skipif(sys.platform!='linux' or os.geteuid()==0,reason='Actual non-root ownership proof requires local Linux non-root process')
@pytest.mark.posix
def test_non_root_registry_is_not_an_authority(tmp_path,monkeypatch):
    parent=tmp_path/'unprivileged';parent.mkdir(mode=0o755)
    target=parent/'trust.json';target.write_text('{"format":1,"releases":{}}');target.chmod(0o644)
    monkeypatch.setattr(security,'TRUST_PATH',target)
    with pytest.raises(security.SecurityError):security.load_trust()


@pytest.mark.skipif(sys.platform!='linux' or os.geteuid()!=0,reason='Real root-owned registry proof requires a disposable Linux root test process')
@pytest.mark.posix
def test_real_root_registry_permissions_and_symlinks(tmp_path,monkeypatch):
    parent=tmp_path/'root-policy';parent.mkdir(mode=0o755)
    target=parent/'trust.json';target.write_text('{"format":1,"releases":{}}');target.chmod(0o644)
    monkeypatch.setattr(security,'TRUST_PATH',target)
    assert security.load_trust()=={'format':1,'releases':{}}
    target.chmod(0o666)
    with pytest.raises(security.SecurityError):security.load_trust()
    target.chmod(0o644);link=parent/'link.json';link.symlink_to(target)
    monkeypatch.setattr(security,'TRUST_PATH',link)
    with pytest.raises(security.SecurityError):security.load_trust()
    monkeypatch.setattr(security,'TRUST_PATH',target);parent.chmod(0o777)
    with pytest.raises(security.SecurityError):security.load_trust()


@pytest.mark.skipif(sys.platform!='linux' or os.geteuid()!=0,reason='Real root approval requires disposable Linux root process')
@pytest.mark.posix
def test_real_approval_and_installed_backup_guard_end_to_end(tmp_path,monkeypatch):
    trust={'format':1,'releases':{}}
    bundle=tmp_path/'bundle';candidate=approved_bundle(bundle,release('0007'),trust)
    parent=tmp_path/'root-policy';parent.mkdir(mode=0o755)
    path=parent/'trust.json';path.write_text(json.dumps(trust));path.chmod(0o644)
    monkeypatch.setattr(security,'TRUST_PATH',path)
    assert security.authorize(bundle,candidate)['independently_approved']
    installed=tmp_path/'ops';installed.mkdir(mode=0o755)
    shutil.copyfile(bundle/'backup_production.py',installed/'backup_production.py')
    shutil.copyfile(bundle/'release_security.py',installed/'release_security.py')
    (installed/'backup_production.py').chmod(0o644)
    (installed/'release_security.py').chmod(0o644)
    deploy.check_backup_guard(tmp_path,bundle)
    (installed/'backup_production.py').write_text('stale resume code')
    with pytest.raises(deploy.DeploymentError):deploy.check_backup_guard(tmp_path,bundle)
    path.write_text(json.dumps({'format':1,'releases':{}}))
    with pytest.raises(security.SecurityError):security.authorize(bundle,candidate)
