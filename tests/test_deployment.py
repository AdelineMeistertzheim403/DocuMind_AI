import copy
import json
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

from tools.release_manifest import validate_release,schema_head,COMPONENTS
from tools import deploy_production as deploy


def release(revision='0006',sha='a'*40):
    return {'format':1,'git_sha':sha,'schema_revision':revision,'supported_schema_revisions':[revision],
            'images':{name:f'registry.adelinemeistertzheim.fr/documind-ai/{name}@sha256:'+str(index)*64
                      for index,name in enumerate(COMPONENTS,1)}}


@pytest.mark.parametrize('change', ['tag','host','component','sha','schema'])
def test_release_rejects_unreviewed_or_mutable_references(change):
    data=release()
    if change=='tag':data['images']['backend']='registry.adelinemeistertzheim.fr/documind-ai/backend:latest'
    if change=='host':data['images']['backend']=data['images']['backend'].replace('registry.adelinemeistertzheim.fr','evil.test')
    if change=='component':data['images'].pop('postgres')
    if change=='sha':data['git_sha']='main; command'
    if change=='schema':data['supported_schema_revisions']=['*']
    with pytest.raises(ValueError):validate_release(data)


def test_release_supports_only_tested_schema_and_real_head(tmp_path,monkeypatch):
    assert validate_release(release())['schema_revision']==schema_head(Path('.'))
    assert deploy.can_rollback(release(),'0006')
    assert not deploy.can_rollback(release(),'0007')
    assert ':latest' not in deploy.images_env(release())
    monkeypatch.setenv('BACKEND_IMAGE','unapproved:latest')
    stack=deploy.Stack(tmp_path,tmp_path,release())
    assert stack.env['BACKEND_IMAGE']==release()['images']['backend']


def test_registry_tls_cannot_be_disabled_explicitly_or_by_cidr():
    deploy.secure_registry_config({'InsecureRegistryCIDRs':['127.0.0.0/8']},{'203.0.113.5'})
    with pytest.raises(deploy.DeploymentError):
        deploy.secure_registry_config({'IndexConfigs':{'registry.adelinemeistertzheim.fr':{'Secure':False}}},{'203.0.113.5'})
    with pytest.raises(deploy.DeploymentError):
        deploy.secure_registry_config({'InsecureRegistryCIDRs':['203.0.113.0/24']},{'203.0.113.5'})


def test_production_reuses_confirmed_proxy_and_preserves_volumes():
    data=yaml.safe_load(Path('compose.production.yaml').read_text(encoding='utf-8'))
    assert data['name']=='documind-prod' and set(data['services'])=={'api','web','db'}
    assert set(data['volumes'])=={'production_database','production_documents'}
    assert data['services']['db']['volumes']==['production_database:/var/lib/postgresql/data']
    assert data['services']['api']['volumes']==['production_documents:/app/var']
    assert data['services']['api']['environment']['STORAGE_DIR']=='/app/var/documents'
    assert not data['services']['web'].get('volumes')
    assert data['networks']['web']=={'external':True,'name':'web'}
    for name,service in data['services'].items():
        assert not service.get('ports') and not service.get('build')
        assert service['logging']['options']=={'max-size':'10m','max-file':'3'}
        assert ('web' in service['networks'])==(name=='web')
    labels=data['services']['web']['labels']
    assert labels['traefik.docker.network']=='web'
    assert labels['traefik.http.routers.documind-ai.entrypoints']=='websecure'
    assert labels['traefik.http.routers.documind-ai.tls.certresolver']=='letsencrypt'
    assert labels['traefik.http.services.documind-ai.loadbalancer.server.port']=='3000'
    assert not any('gateway' in key.lower() or 'password' in key.lower() for key in labels)
    assert 'alembic' not in data['services']['api']['command']
    assert data['services']['api']['command'].count('--workers')==1
    assert data['services']['web']['healthcheck']['test']==['CMD','node','server/healthcheck.mjs']
    assert data['services']['web']['environment']['BFF_ALLOWED_HOSTS']==deploy.HOST
    assert data['services']['web']['environment']['BFF_PORT']==3000
    assert 'CMD node server/healthcheck.mjs' in Path('frontend/Dockerfile').read_text()


def test_workflows_are_pinned_gated_and_never_deploy_on_push():
    ci=yaml.load(Path('.github/workflows/ci.yml').read_text(),Loader=yaml.BaseLoader)
    production=yaml.load(Path('.github/workflows/deploy.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(production['on'])=={'workflow_dispatch'}
    assert production['jobs']['deploy']['environment']['name']=='production'
    assert ci['jobs']['publish']['needs']==['python','frontend']
    assert "github.event_name != 'pull_request'" in ci['jobs']['publish']['if']
    import re
    for workflow in (ci,production):
        for job in workflow['jobs'].values():
            for step in job['steps']:
                if 'uses' in step:assert re.fullmatch(r'[^@]+@[a-f0-9]{40}',step['uses'])
    text=Path('.github/workflows/deploy.yml').read_text()
    assert 'required_reviewers' in text and 'StrictHostKeyChecking=yes' in text
    assert 'StrictHostKeyChecking=no' not in text and 'ssh-keyscan' not in text


@pytest.fixture
def simulation(tmp_path,monkeypatch):
    root=tmp_path/'vps';bundle=root/'releases'/'candidate';bundle.mkdir(parents=True)
    (root/'.env.production').write_text('TEST_ONLY=true');(root/'.env.production').chmod(0o600)
    (bundle/'release.json').write_text(json.dumps(release()))
    events=[];state={'revision':'0006','fail_migration':False,'fail_start':False}
    class FakeStack:
        def __init__(self,root,bundle,release,proxy='127.0.0.1'):
            self.root,self.bundle,self.release,self.env,self.command=root,bundle,release,{'BFF_TRUSTED_PROXY_IPS':proxy},['docker','compose']
        def call(self,*args):
            events.append((self.bundle.name,args))
            if args[0]=='config':return '{}'
            if args[0]=='run' and 'du' in args:return '1000 /app/var/documents'
            if args[0]=='run' and 'alembic' in args:
                state['revision']=self.release['schema_revision']
                if state['fail_migration']:raise deploy.DeploymentError('Simulated migration failure')
            if args[0]=='up' and 'api' in args and self.bundle.name=='candidate' and state['fail_start']:
                raise deploy.DeploymentError('Simulated startup failure')
            return ''
        def revision(self):return state['revision']
        def sql(self,sql):return '1000'
        def check_health(self,*args):events.append(('healthy',args))
    old=FakeStack(root,root/'releases'/'prior',release(sha='b'*40))
    monkeypatch.setattr(deploy,'__file__',str(bundle/'deploy_production.py'))
    monkeypatch.setitem(sys.modules,'fcntl',SimpleNamespace(flock=lambda *args:None,LOCK_EX=1,LOCK_NB=2))
    monkeypatch.setattr(deploy,'Stack',FakeStack)
    monkeypatch.setattr(deploy,'current_stack',lambda *args:old)
    for function in ('check_config','disk_check','check_volume_state','verify_images'):
        monkeypatch.setattr(deploy,function,lambda *args:None)
    monkeypatch.setattr(deploy,'resolve_proxy',lambda *args:{'DEPLOY_MIN_FREE_GIB':'8'})
    monkeypatch.setattr(deploy,'create_backup',lambda *args,**kwargs:events.append(('backup',())))
    monkeypatch.setattr(deploy,'https_check',lambda *args:events.append(('https',())))
    monkeypatch.setattr(deploy,'point_to',lambda *args:events.append(('activate',())))
    args=SimpleNamespace(root=root,initialize=False,allow_migration=False,rollback=False)
    return args,events,state,bundle


def test_backup_precedes_migration_and_release_activation(simulation):
    args,events,state,bundle=simulation;report={}
    deploy.execute(args,report)
    backup=next(i for i,event in enumerate(events) if event[0]=='backup')
    migration=next(i for i,event in enumerate(events) if 'alembic' in event[1])
    assert any(event[1][:1]==('stop',) for event in events[:backup])
    assert backup<migration<next(i for i,event in enumerate(events) if event[0]=='https')
    assert report['status']=='success' and report['schema_after']=='0006'


def test_failed_start_restarts_only_compatible_previous_application(simulation):
    args,events,state,bundle=simulation;state['fail_start']=True;report={}
    with pytest.raises(deploy.DeploymentError):deploy.execute(args,report)
    assert report['previous_application_restarted'] is True
    assert not any(event[0]=='activate' for event in events)
    assert not any('downgrade' in event[1] for event in events)


def test_schema_change_requires_approval_and_blocks_incompatible_rollback(simulation):
    args,events,state,bundle=simulation
    (bundle/'release.json').write_text(json.dumps(release('0007')))
    with pytest.raises(deploy.DeploymentError,match='migration approval'):deploy.execute(args,{})
    assert not events
    args.allow_migration=True;state['fail_start']=True;report={}
    with pytest.raises(deploy.DeploymentError):deploy.execute(args,report)
    assert not report.get('previous_application_restarted')
    assert not any(name=='prior' and 'up' in arguments for name,arguments in events)


def test_backup_failure_prevents_migration(simulation,monkeypatch):
    args,events,state,bundle=simulation
    monkeypatch.setattr(deploy,'create_backup',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('Simulated full disk')))
    with pytest.raises(OSError):deploy.execute(args,{})
    assert not any('alembic' in event[1] for event in events)


@pytest.fixture
def recovery(simulation,monkeypatch):
    args,events,state,bundle=simulation
    source=bundle.parent/'failed-first';source.mkdir()
    original=release(sha='2de68362d2fe0f4dece2d01da34dc5a06f00d4c8')
    (source/'release.json').write_text(json.dumps(original))
    evidence={'status':'failed','phase':'start','git_sha':original['git_sha'],'images':original['images'],
              'schema_before':None,'schema_after':'0006'}
    (source/'deployment-report.json').write_text(json.dumps(evidence))
    args.recover_from=source
    monkeypatch.setattr(deploy,'current_stack',lambda *args:None)
    monkeypatch.setattr(deploy,'verify_recovery_containers',lambda *args:None)
    return args,events,state,bundle,evidence


def test_recovery_backs_up_then_starts_without_migration_or_database_replacement(recovery):
    args,events,state,bundle,evidence=recovery;report={}
    deploy.execute(args,report)
    assert report['status']=='success' and report['schema_before']==report['schema_after']=='0006'
    assert report['source_sha']==evidence['git_sha'] and report['backup']
    backup=next(i for i,event in enumerate(events) if event[0]=='backup')
    assert any(name=='failed-first' and command[0]=='stop' for name,command in events[:backup])
    assert not any('alembic' in command or (command[0]=='up' and 'db' in command) for _,command in events if command)
    assert backup<next(i for i,(_,command) in enumerate(events) if command and command[0]=='up')
    assert next(i for i,event in enumerate(events) if event[0]=='https')<next(i for i,event in enumerate(events) if event[0]=='activate')
    assert json.loads((args.recover_from/'deployment-report.json').read_text())==evidence


@pytest.mark.parametrize('invalid',['schema','source_schema','phase','sha','images','previous','missing_report','missing_before','same_bundle','outside','current','previous_pointer','initialize','rollback','allow_migration'])
def test_recovery_refuses_ambiguous_or_incompatible_state(recovery,invalid):
    args,events,state,bundle,evidence=recovery
    if invalid=='schema':state['revision']='0005'
    elif invalid=='source_schema':(bundle/'release.json').write_text(json.dumps(release('0007')))
    elif invalid=='phase':evidence['phase']='migration'
    elif invalid=='sha':evidence['git_sha']='c'*40
    elif invalid=='images':evidence['images']={}
    elif invalid=='previous':evidence['previous_sha']='b'*40
    elif invalid=='missing_before':evidence.pop('schema_before')
    elif invalid=='same_bundle':args.recover_from=bundle
    elif invalid=='outside':args.recover_from=bundle.parent.parent
    elif invalid in ('current','previous_pointer'):(args.root/('current' if invalid=='current' else 'previous')).write_text('ambiguous')
    elif invalid in ('initialize','rollback','allow_migration'):setattr(args,invalid,True)
    source=bundle.parent/'failed-first'
    (source/'deployment-report.json').write_text(json.dumps(evidence))
    if invalid=='missing_report':(source/'deployment-report.json').unlink()
    with pytest.raises(deploy.DeploymentError):deploy.execute(args,{})
    assert not events


@pytest.mark.parametrize('failure',['backup','start','schema_drift','https'])
def test_recovery_failure_never_activates_or_reopens_failed_source(recovery,monkeypatch,failure):
    args,events,state,bundle,evidence=recovery
    if failure=='backup':
        monkeypatch.setattr(deploy,'create_backup',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('backup failed')))
    elif failure=='start':state['fail_start']=True
    elif failure=='https':
        monkeypatch.setattr(deploy,'https_check',lambda *args:(_ for _ in ()).throw(deploy.DeploymentError('HTTPS probe failed')))
    else:
        calls=[]
        def drift(*args):
            calls.append(True)
            if len(calls)==2:state['revision']='0007'
        monkeypatch.setattr(deploy,'verify_recovery_containers',drift)
    with pytest.raises((OSError,deploy.DeploymentError)):deploy.execute(args,{})
    assert not any(event[0]=='activate' for event in events)
    assert not any(name=='failed-first' and command and command[0]=='up' for name,command in events)
    if failure in ('backup','schema_drift'):assert not any(command and command[0]=='up' for _,command in events)


@pytest.mark.parametrize('invalid',[pytest.param(None,id='vps-observed-mounts'),
    'owner','duplicate','image','mount','unhealthy','source','oneoff',
    'documents_subdirectory','unauthorized_path','bind','extra_volume','duplicate_mount','web_volume',
    'database_volume','database_path','missing_mount'])
def test_recovery_inspects_actual_project_images_mounts_and_database(monkeypatch,tmp_path,invalid):
    stack=deploy.Stack(tmp_path,tmp_path,release())
    containers=[]
    for name in ('db','api','web'):
        destination='/var/lib/postgresql/data' if name=='db' else '/app/var'
        volume='database' if name=='db' else 'documents'
        containers.append({'Config':{'Labels':{'com.docker.compose.project':deploy.PROJECT,
            'com.docker.compose.service':name,'com.docker.compose.project.config_files':str(tmp_path/'compose.production.yaml')}},
            'Image':'sha256:verified','State':{'Running':True,'Health':{'Status':'healthy'}},
            'Mounts':([{'Type':'volume','Destination':destination,'Name':f'{deploy.PROJECT}_production_{volume}'}]
                      if name!='web' else [])})
        if name in ('api','web'):containers[-1]['Mounts'].append({'Type':'tmpfs','Destination':'/tmp'})
    if invalid=='owner':containers[0]['Config']['Labels']['com.docker.compose.project']='other-app'
    elif invalid=='duplicate':containers[1]['Config']['Labels']['com.docker.compose.service']='db'
    elif invalid=='image':containers[1]['Image']='sha256:unreviewed'
    elif invalid=='mount':containers[1]['Mounts'][0]['Name']='other-volume'
    elif invalid=='unhealthy':containers[0]['State']['Health']['Status']='unhealthy'
    elif invalid=='source':containers[0]['Config']['Labels']['com.docker.compose.project.config_files']='other-bundle'
    elif invalid=='oneoff':containers[1]['Config']['Labels']['com.docker.compose.oneoff']='True'
    elif invalid=='documents_subdirectory':containers[1]['Mounts'][0]['Destination']='/app/var/documents'
    elif invalid=='unauthorized_path':containers[1]['Mounts'][0]['Destination']='/unauthorized'
    elif invalid=='bind':containers[1]['Mounts'][0]['Type']='bind'
    elif invalid=='extra_volume':containers[1]['Mounts'].append({'Type':'volume','Name':'unexpected','Destination':'/extra'})
    elif invalid=='duplicate_mount':containers[1]['Mounts'].append(copy.deepcopy(containers[1]['Mounts'][0]))
    elif invalid=='web_volume':containers[2]['Mounts'].append({'Type':'volume','Name':'unexpected','Destination':'/extra'})
    elif invalid=='database_volume':containers[0]['Mounts'][0]['Name']='other-database'
    elif invalid=='database_path':containers[0]['Mounts'][0]['Destination']='/other-database'
    elif invalid=='missing_mount':containers[1]['Mounts']=[]
    def run(command):
        if command[:3]==['docker','ps','-aq']:return '1\n2\n3'
        if command[:2]==['docker','inspect']:return json.dumps(containers)
        if command[:3]==['docker','image','inspect']:return 'sha256:verified'
        pytest.fail('Unexpected Docker command')
    monkeypatch.setattr(deploy,'run',run)
    if invalid:
        mount_errors={'mount','documents_subdirectory','unauthorized_path','bind','extra_volume',
                      'duplicate_mount','web_volume','database_volume','database_path','missing_mount'}
        with pytest.raises(deploy.DeploymentError,match='unexpected persistent mounts' if invalid in mount_errors else None):
            deploy.verify_recovery_containers(stack)
    else:deploy.verify_recovery_containers(stack)


@pytest.mark.parametrize('initialize,states',[(True,[True,True]),(True,[True,False]),(False,[True,False]),(False,[False,False])])
def test_partial_volumes_never_enable_implicit_initialization(monkeypatch,initialize,states):
    results=iter(states)
    monkeypatch.setattr(deploy.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(
        returncode=0 if next(results) else 1,stderr='no such volume'))
    with pytest.raises(deploy.DeploymentError):deploy.check_volume_state(initialize)


@pytest.fixture
def post_https(recovery):
    args,events,state,bundle,initial_report=recovery
    origin=args.recover_from
    original=json.loads((origin/'release.json').read_text())
    failed=bundle.parent/'failed-https';failed.mkdir()
    replaced=release(sha='334a40ec76c69c582a4f25c8a6237351f3c2357d')
    replaced['images']={name:value.split('@')[0]+'@sha256:'+str(index)*64
                        for index,(name,value) in enumerate(replaced['images'].items(),4)}
    (failed/'release.json').write_text(json.dumps(replaced))
    backup=args.root/'var/backups/deploy-20261019-181649';backup.mkdir(parents=True)
    hashes={}
    for name in ('database.dump','documents.tar.gz'):
        content=b'local unit-test snapshot, never restored';(backup/name).write_bytes(content)
        hashes[name]=hashlib.sha256(content).hexdigest()
    (backup/'manifest.json').write_text(json.dumps({'migration':'0006','database_major':17,
                                                  'files':list(hashes),'sha256':hashes}))
    evidence={'status':'failed','phase':'https','git_sha':replaced['git_sha'],'images':replaced['images'],
        'schema_before':'0006','schema_after':'0006','recovered_from':str(origin.relative_to(args.root)),
        'source_sha':original['git_sha'],'retained_database_image':original['images']['postgres'],
        'backup':str(backup.relative_to(args.root))}
    (failed/'deployment-report.json').write_text(json.dumps(evidence))
    args.recover_from=None;args.recover_after_https=failed
    return args,events,state,bundle,evidence,origin


def test_post_https_recovery_validates_chain_and_retains_original_database(post_https,monkeypatch):
    args,events,state,bundle,evidence,origin=post_https;checks=[];report={}
    def verify(stack):
        checks.append((stack.bundle,stack.database_source.bundle,stack.release['git_sha']))
    monkeypatch.setattr(deploy,'verify_recovery_containers',verify)
    deploy.execute(args,report)
    assert len(checks)==2 and all(value==(args.recover_after_https,origin,evidence['git_sha']) for value in checks)
    assert report['status']=='success' and report['source_sha']==evidence['git_sha']
    assert report['retained_database_image']==evidence['retained_database_image']
    assert not any('alembic' in command or (command[0]=='up' and 'db' in command) for _,command in events if command)
    backup=next(i for i,event in enumerate(events) if event[0]=='backup')
    assert backup<next(i for i,(_,command) in enumerate(events) if command and command[0]=='up')
    assert json.loads((args.recover_after_https/'deployment-report.json').read_text())==evidence


@pytest.mark.parametrize('invalid',['source_sha','images','database','phase','schema','live_schema',
    'backup_missing','backup_corrupt','backup_schema','backup_outside','backup_hash',
    'parent_missing','cycle','current','previous','same_target','both_modes','initialize','allow_migration','rollback','target_schema'])
def test_post_https_recovery_refuses_ambiguous_state(post_https,invalid):
    args,events,state,bundle,evidence,origin=post_https
    backup=args.root/evidence['backup']
    if invalid=='source_sha':evidence['source_sha']='c'*40
    elif invalid=='images':evidence['images']={}
    elif invalid=='database':evidence['retained_database_image']=evidence['images']['postgres']
    elif invalid=='phase':evidence['phase']='start'
    elif invalid=='schema':evidence['schema_before']='0005'
    elif invalid=='live_schema':state['revision']='0007'
    elif invalid=='backup_missing':(backup/'manifest.json').unlink()
    elif invalid=='backup_corrupt':(backup/'database.dump').write_bytes(b'corrupt')
    elif invalid in ('backup_schema','backup_hash'):
        manifest=json.loads((backup/'manifest.json').read_text())
        if invalid=='backup_schema':manifest['migration']='0005'
        else:manifest['sha256'].pop('documents.tar.gz')
        (backup/'manifest.json').write_text(json.dumps(manifest))
    elif invalid=='backup_outside':evidence['backup']='../outside'
    elif invalid=='parent_missing':(origin/'deployment-report.json').unlink()
    elif invalid=='cycle':evidence['recovered_from']=str(args.recover_after_https.relative_to(args.root))
    elif invalid in ('current','previous'):(args.root/invalid).write_text('invalid pointer')
    elif invalid=='both_modes':args.recover_from=origin
    elif invalid in ('initialize','allow_migration','rollback'):setattr(args,invalid,True)
    elif invalid=='target_schema':(bundle/'release.json').write_text(json.dumps(release('0007')))
    failed=args.recover_after_https
    (failed/'deployment-report.json').write_text(json.dumps(evidence))
    if invalid=='same_target':args.recover_after_https=bundle
    with pytest.raises(deploy.DeploymentError):deploy.execute(args,{})
    assert not events


def test_post_https_failure_preserves_diagnostics_and_never_activates(post_https,monkeypatch):
    args,events,state,bundle,evidence,origin=post_https;report={}
    def failed_https(report):
        report['https_probes']=[{'url':f'https://{deploy.HOST}/login','cause':'dns_error'}]
        raise deploy.HTTPSProbeError('HTTPS probe failed')
    monkeypatch.setattr(deploy,'https_check',failed_https)
    with pytest.raises(deploy.HTTPSProbeError):deploy.execute(args,report)
    assert report['phase']=='https' and report['backup']
    assert report['https_probes'][0]['cause']=='dns_error'
    assert any(name=='candidate' and command[0]=='stop' for name,command in events if command)
    assert not any(name=='activate' for name,_ in events)
    assert not any(name=='failed-https' and command[0]=='up' for name,command in events if command)


def test_post_https_new_backup_failure_blocks_application_start(post_https,monkeypatch):
    args,events,state,bundle,evidence,origin=post_https
    def fail(*args,**kwargs):raise OSError('simulated backup failure')
    monkeypatch.setattr(deploy,'create_backup',fail)
    with pytest.raises(OSError):deploy.execute(args,{})
    assert not any(command and command[0]=='up' for _,command in events)
    assert not any(name=='activate' for name,_ in events)


def test_post_https_recovery_can_follow_a_second_failed_https_attempt(post_https,monkeypatch):
    args,events,state,bundle,evidence,origin=post_https
    prior=args.recover_after_https
    later=bundle.parent/'failed-again';later.mkdir()
    metadata=release(sha='c'*40)
    (later/'release.json').write_text(json.dumps(metadata))
    report={**evidence,'git_sha':metadata['git_sha'],'images':metadata['images'],
            'source_sha':evidence['git_sha'],'recovered_from':str(prior.relative_to(args.root))}
    # An independently named snapshot with the same unit-test contents and valid hashes.
    old=args.root/evidence['backup'];new=args.root/'var/backups/retry-snapshot';new.mkdir()
    for file in old.iterdir():(new/file.name).write_bytes(file.read_bytes())
    report['backup']=str(new.relative_to(args.root))
    (later/'deployment-report.json').write_text(json.dumps(report))
    args.recover_after_https=later
    checks=[]
    monkeypatch.setattr(deploy,'verify_recovery_containers',lambda stack:checks.append((stack.bundle,stack.database_source.bundle)))
    result={};deploy.execute(args,result)
    assert checks==[(later,origin)]*2
    assert result['status']=='success' and result['source_sha']=='c'*40
    assert json.loads((prior/'deployment-report.json').read_text())==evidence


@pytest.mark.parametrize('wrong',[None,'db_image','db_bundle','app_bundle'])
def test_recovery_matches_split_database_and_application_owners(tmp_path,monkeypatch,wrong):
    origin=tmp_path/'initial';candidate=tmp_path/'apps';origin.mkdir();candidate.mkdir()
    original=release(sha='b'*40);replaced=release()
    replaced['images']['postgres']=replaced['images']['postgres'].split('@')[0]+'@sha256:'+'9'*64
    stack=deploy.Stack(tmp_path,candidate,replaced)
    stack.database_source=deploy.Stack(tmp_path,origin,original)
    containers=[]
    for service in ('db','api','web'):
        owner=origin if service=='db' else candidate
        mounts=[]
        if service!='web':mounts=[{'Type':'volume','Destination':'/app/var' if service=='api' else '/var/lib/postgresql/data',
            'Name':f'{deploy.PROJECT}_production_'+('documents' if service=='api' else 'database')}]
        containers.append({'Config':{'Labels':{'com.docker.compose.project':deploy.PROJECT,'com.docker.compose.service':service,
            'com.docker.compose.project.config_files':str(owner/'compose.production.yaml')}},
            'Image':'original-db' if service=='db' else 'replaced-app','State':{'Running':True,'Health':{'Status':'healthy'}},'Mounts':mounts})
    if wrong=='db_image':containers[0]['Image']='replaced-app'
    elif wrong=='db_bundle':containers[0]['Config']['Labels']['com.docker.compose.project.config_files']=str(candidate/'compose.production.yaml')
    elif wrong=='app_bundle':containers[1]['Config']['Labels']['com.docker.compose.project.config_files']=str(origin/'compose.production.yaml')
    def run(command):
        if command[:3]==['docker','ps','-aq']:return '1\n2\n3'
        if command[:2]==['docker','inspect']:return json.dumps(containers)
        if command[:3]==['docker','image','inspect']:
            assert command[3]!=replaced['images']['postgres']
            return 'original-db' if command[3]==original['images']['postgres'] else 'replaced-app'
        pytest.fail('Unexpected Docker command')
    monkeypatch.setattr(deploy,'run',run)
    if wrong:
        with pytest.raises(deploy.DeploymentError):deploy.verify_recovery_containers(stack)
    else:deploy.verify_recovery_containers(stack)


def test_existing_report_is_never_overwritten_or_reused_as_candidate(tmp_path,monkeypatch):
    report=tmp_path/'deployment-report.json';report.write_text('immutable prior failure')
    monkeypatch.setattr(deploy,'__file__',str(tmp_path/'deploy_production.py'))
    monkeypatch.setattr(sys,'argv',['deploy_production.py','--root',str(tmp_path),'--recover-after-https',str(tmp_path)])
    monkeypatch.setattr(deploy,'verify_registry_tls',lambda:pytest.fail('No network preflight before preserving old evidence'))
    assert deploy.main()==1
    assert report.read_text()=='immutable prior failure'


def test_deployment_refuses_pending_backup_maintenance(simulation):
    args,events,state,bundle=simulation
    marker=args.root/'var/backup-maintenance.json';marker.parent.mkdir();marker.write_text('{}')
    with pytest.raises(deploy.DeploymentError,match='Backup maintenance is pending'):deploy.execute(args,{})
    assert events==[]
