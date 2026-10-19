import copy
import json
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
    monkeypatch.setattr(deploy,'https_check',lambda:events.append(('https',())))
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
