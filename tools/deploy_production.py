"""Approved Linux VPS deployment. No builds, volume removal, registry reconfiguration or DB downgrade."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import ipaddress
import socket
import urllib.error
import urllib.request

try:
    from .backup_local import create_backup
    from .release_manifest import COMPONENTS,validate_release
except ImportError:  # Flat, reviewed CI release bundle on the VPS.
    from backup_local import create_backup
    from release_manifest import COMPONENTS,validate_release

HOST='documind.adelinemeistertzheim.fr'
PROJECT='documind-prod'


class DeploymentError(Exception):pass


def run(command,env=None):
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    if result.returncode:
        # Never echo Docker config, subprocess output, credentials or provider errors to CI.
        raise DeploymentError('Command failed')
    return result.stdout.strip()


def images_env(release):
    return ''.join(f'{variable}={release["images"][name]}\n' for name,variable in COMPONENTS.items())


def can_rollback(release,revision):
    return revision in release['supported_schema_revisions']


class Stack:
    def __init__(self,root,bundle,release,proxy='127.0.0.1'):
        self.root,self.bundle,self.release=root,bundle,release
        self.env={**os.environ,'PRODUCTION_ENV_FILE':str(root/'.env.production'),'BFF_TRUSTED_PROXY_IPS':proxy}
        self.env.update({variable:release['images'][name] for name,variable in COMPONENTS.items()})
        (bundle/'images.env').write_text(images_env(release)+f'BFF_TRUSTED_PROXY_IPS={proxy}\n',encoding='utf-8')
        self.command=['docker','compose','--project-directory',str(root),'-p',PROJECT,
            '--env-file',str(root/'.env.production'),'--env-file',str(bundle/'images.env'),
            '-f',str(bundle/'compose.production.yaml')]

    def call(self,*arguments):return run(self.command+list(arguments),self.env)

    def sql(self,sql):
        return self.call('exec','-T','db','sh','-c',
            'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"','query',sql)

    def revision(self):
        if not self.sql("SELECT coalesce(to_regclass('public.alembic_version')::text,'')"):
            return None
        values=self.sql('SELECT version_num FROM alembic_version').splitlines()
        if len(values)!=1:raise DeploymentError('Exactly one live schema revision is required')
        return values[0]

    def check_health(self,*services):
        for service in services:
            identifiers=self.call('ps','-q',service).splitlines()
            if len(identifiers)!=1:raise DeploymentError('A single instance of each service is required')
            data=json.loads(run(['docker','inspect',identifiers[0]]))[0]
            if data['State'].get('Health',{}).get('Status')!='healthy':
                raise DeploymentError('Unhealthy service')


def resolve_proxy(stack):
    values=dict(line.split('=',1) for line in stack.call('config','--environment').splitlines() if '=' in line)
    name=values.get('TRAEFIK_CONTAINER','')
    if not name or name.startswith('-'):raise DeploymentError('Configure the exact existing TRAEFIK_CONTAINER')
    data=json.loads(run(['docker','inspect',name]))[0]
    address=data['NetworkSettings']['Networks'].get('web',{}).get('IPAddress')
    if not data['State']['Running'] or not address:raise DeploymentError('Existing Traefik must be running on web')
    stack.env['BFF_TRUSTED_PROXY_IPS']=address
    (stack.bundle/'images.env').write_text(images_env(stack.release)+f'BFF_TRUSTED_PROXY_IPS={address}\n',encoding='utf-8')
    return values


def check_config(stack):
    config=json.loads(stack.call('config','--format','json'))
    services=config['services']
    for service,component in (('api','backend'),('web','frontend'),('db','postgres')):
        if services[service]['image']!=stack.release['images'][component]:
            raise DeploymentError('Resolved images differ from the approved manifest')
    if set(services)!={'db','api','web'}:raise DeploymentError('Unexpected production services')
    for name in services:
        if services[name].get('ports') or services[name].get('build'):
            raise DeploymentError('Production must not publish ports or build images')
    if services['api']['environment'].get('REGISTRATION_MODE') not in ('disabled','invite'):
        raise DeploymentError('Public registration is forbidden')
    if services['api']['environment'].get('ACCOUNT_BASE_URL')!=f'https://{HOST}':
        raise DeploymentError('Unexpected account HTTPS origin')
    if set(services['web']['networks'])!={'application','web'}:
        raise DeploymentError('Only the BFF can join the external proxy network')
    for name in ('api','db'):
        if 'web' in services[name]['networks']:raise DeploymentError('Backend joined the proxy network')
    return config


def disk_check(root,minimum):
    docker_root=Path(run(['docker','info','--format','{{.DockerRootDir}}']))
    for path in (root,docker_root):
        if shutil.disk_usage(path).free < minimum:
            raise DeploymentError('Insufficient free disk space')


def secure_registry_config(info,addresses):
    name='registry.adelinemeistertzheim.fr'
    if info.get('IndexConfigs',{}).get(name,{}).get('Secure') is False:
        raise DeploymentError('Registry TLS validation is disabled in the Docker daemon')
    for cidr in info.get('InsecureRegistryCIDRs',[]):
        if any(ipaddress.ip_address(address) in ipaddress.ip_network(cidr) for address in addresses):
            raise DeploymentError('Registry address matches an insecure Docker registry CIDR')


def verify_registry_tls():
    name='registry.adelinemeistertzheim.fr'
    config=json.loads(run(['docker','info','--format','{{json .RegistryConfig}}']))
    addresses={value[4][0] for value in socket.getaddrinfo(name,443,type=socket.SOCK_STREAM)}
    secure_registry_config(config,addresses)
    try:
        with urllib.request.urlopen(f'https://{name}/v2/',timeout=20):pass
    except urllib.error.HTTPError as error:
        if error.code!=401:raise DeploymentError('Registry HTTPS endpoint is unavailable') from None


def check_volume_state(initialize):
    states=[]
    for name in ('production_database','production_documents'):
        result=subprocess.run(['docker','volume','inspect',f'{PROJECT}_{name}'],capture_output=True,text=True)
        if result.returncode and 'no such volume' not in result.stderr.lower():
            raise DeploymentError('Cannot inspect persistent volumes')
        states.append(result.returncode==0)
    if any(states)!=all(states):raise DeploymentError('Only one persistent volume exists; inspect before proceeding')
    if initialize and any(states):raise DeploymentError('Initialization refuses existing volumes')
    if not initialize and not all(states):raise DeploymentError('First installation requires explicit initialization approval')


def verify_images(stack):
    for name,image in stack.release['images'].items():
        labels=json.loads(run(['docker','image','inspect',image,'--format','{{json .Config.Labels}}'])) or {}
        if labels.get('org.opencontainers.image.revision')!=stack.release['git_sha']:
            raise DeploymentError('Image revision does not match the reviewed release')


def https_check():
    # Default SSL context verifies chain and hostname. Never use -k or insecure registries.
    for path in ('/login','/bff/health','/bff/auth/csrf'):
        with urllib.request.urlopen(f'https://{HOST}{path}',timeout=20) as response:
            if response.status!=200:raise DeploymentError('HTTPS probe failed')
            if path.endswith('/csrf'):
                cookie=response.headers.get('Set-Cookie','')
                if not all(value in cookie for value in ('HttpOnly','Secure','SameSite=Strict')):
                    raise DeploymentError('Secure CSRF cookie is missing')
    try:
        urllib.request.urlopen(f'https://{HOST}/bff/documents',timeout=20)
    except urllib.error.HTTPError as error:
        if error.code==401:return
    raise DeploymentError('Anonymous document access was not rejected')


def point_to(root,name,bundle):
    temporary=root/f'.{name}.next'
    if temporary.exists() or temporary.is_symlink():temporary.unlink()
    temporary.symlink_to(bundle,target_is_directory=True)
    os.replace(temporary,root/name)


def current_stack(root,proxy):
    if not os.path.lexists(root/'current'):return None
    if not (root/'current').is_symlink() or not (root/'current').is_dir():
        raise DeploymentError('Current release pointer is invalid; manual inspection required')
    prior=(root/'current').resolve()
    if prior.parent!=root/'releases':raise DeploymentError('Unexpected current release path')
    return Stack(root,prior,validate_release(json.loads((prior/'release.json').read_text())),proxy)


def recovery_source(root,bundle,path,release,proxy):
    """Adopt only an evidenced failed first start, without manufacturing a current pointer."""
    if os.path.lexists(root/'current') or os.path.lexists(root/'previous'):
        raise DeploymentError('Recovery requires no current or previous release pointer')
    source=path.resolve()
    if source.parent!=root/'releases' or source==bundle:
        raise DeploymentError('Recovery source must be a distinct existing release bundle')
    try:
        original=validate_release(json.loads((source/'release.json').read_text()))
        evidence=json.loads((source/'deployment-report.json').read_text())
    except (OSError,ValueError):
        raise DeploymentError('Recovery requires a valid source manifest and failure report') from None
    if not (evidence.get('status')=='failed' and evidence.get('phase')=='start'
            and evidence.get('git_sha')==original['git_sha'] and evidence.get('images')==original['images']
            and 'schema_before' in evidence and evidence['schema_before'] is None and not evidence.get('previous_sha')
            and evidence.get('schema_after')==original['schema_revision']):
        raise DeploymentError('Source report does not prove a failed first installation at start')
    if release['schema_revision']!=original['schema_revision']:
        raise DeploymentError('Recovery refuses schema changes; recover before a separate upgrade')
    source_stack=Stack(root,source,original,proxy)
    check_config(source_stack)
    verify_recovery_containers(source_stack)
    revision=source_stack.revision()
    if revision!=original['schema_revision'] or not can_rollback(release,revision):
        raise DeploymentError('Recovery requires the exact compatible live schema revision')
    return source_stack,revision


def verify_recovery_containers(stack):
    identifiers=run(['docker','ps','-aq','--filter',f'label=com.docker.compose.project={PROJECT}']).splitlines()
    if len(identifiers)!=3:raise DeploymentError('Recovery requires exactly the three original service containers')
    containers=json.loads(run(['docker','inspect',*identifiers]))
    seen=set()
    for container in containers:
        labels=container['Config'].get('Labels',{})
        service=labels.get('com.docker.compose.service')
        if (labels.get('com.docker.compose.project')!=PROJECT or service not in ('db','api','web')
                or service in seen or labels.get('com.docker.compose.oneoff','false').lower()!='false'
                or labels.get('com.docker.compose.project.config_files')!=str(stack.bundle/'compose.production.yaml')):
            raise DeploymentError('Ambiguous recovery container ownership or source bundle')
        seen.add(service)
        component={'db':'postgres','api':'backend','web':'frontend'}[service]
        image=run(['docker','image','inspect',stack.release['images'][component],'--format','{{.Id}}'])
        if container['Image']!=image:raise DeploymentError('Recovery container image differs from source manifest')
        if service=='db' and (not container['State']['Running'] or container['State'].get('Health',{}).get('Status')!='healthy'):
            raise DeploymentError('Recovery requires the existing healthy database')
        if service in ('db','api'):
            destination='/var/lib/postgresql/data' if service=='db' else '/app/var/documents'
            volume=f'{PROJECT}_production_'+('database' if service=='db' else 'documents')
            mounts=[mount for mount in container['Mounts'] if mount['Destination']==destination]
            if len(mounts)!=1 or mounts[0].get('Type')!='volume' or mounts[0].get('Name')!=volume:
                raise DeploymentError('Recovery refuses unexpected persistent mounts')


def execute(args,report):
    import fcntl
    root=args.root.resolve();bundle=Path(__file__).resolve().parent
    if bundle.parent!=root/'releases':raise DeploymentError('Release must be staged under the deployment releases directory')
    secret=root/'.env.production'
    if not secret.is_file() or (os.name=='posix' and secret.stat().st_mode & 0o077):
        raise DeploymentError('Production environment must exist and have mode 0600')
    lock=(root/'deployment.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    release=validate_release(json.loads((bundle/'release.json').read_text(encoding='utf-8')))
    report['git_sha']=release['git_sha'];report['images']=release['images']
    stack=Stack(root,bundle,release)
    report['phase']='preflight'
    recovery=getattr(args,'recover_from',None)
    if recovery and (args.initialize or args.rollback or args.allow_migration):
        raise DeploymentError('Recovery cannot be combined with initialization, rollback or migration approval')
    values=resolve_proxy(stack)
    check_config(stack)
    minimum=int(values.get('DEPLOY_MIN_FREE_GIB','8'))*(1024**3)
    if minimum<4*(1024**3):raise DeploymentError('Deployment disk threshold must be at least 4 GiB')
    disk_check(root,minimum)
    check_volume_state(args.initialize)
    previous=current_stack(root,stack.env['BFF_TRUSTED_PROXY_IPS'])
    source=None
    if recovery:
        source,before=recovery_source(root,bundle,recovery,release,stack.env['BFF_TRUSTED_PROXY_IPS'])
        report['recovered_from']=str(source.bundle.relative_to(root))
        report['source_sha']=source.release['git_sha']
        report['retained_database_image']=source.release['images']['postgres']
    if previous:
        report['previous_sha']=previous.release['git_sha']
    if not args.initialize and previous is None and not recovery:
        raise DeploymentError('Existing deployment must be adopted explicitly before automated updates')
    if args.initialize and previous is not None:raise DeploymentError('Initialization refuses an existing release')
    if args.rollback and args.initialize:raise DeploymentError('Cannot initialize a rollback')
    if not recovery:before=previous.revision() if previous else None
    if args.rollback and not can_rollback(release,before):
        raise DeploymentError('Rollback application does not support the current database schema')
    if before and before!=release['schema_revision'] and not (args.allow_migration or args.rollback):
        raise DeploymentError('A schema change requires explicit migration approval')
    report['schema_before']=before
    report['phase']='pull'
    stack.call('pull','db','api','web')
    verify_images(stack)
    report['phase']='settings'
    stack.call('run','--rm','--no-deps','-T','--entrypoint','python','api','-c',
        "from backend.config import Settings; s=Settings(); assert s.registration_mode in ('disabled','invite'); assert not s.legacy_api_enabled")
    try:
        snapshot=source or previous
        if snapshot:
            report['phase']='backup'
            snapshot.call('stop','--timeout','150','web','api')
            if recovery:
                # Recheck after quiescing writers; never migrate or replace PostgreSQL here.
                verify_recovery_containers(source)
                if source.revision()!=before:raise DeploymentError('Schema changed during recovery')
            # Budget enough uncompressed room for the full DB and document archive plus normal headroom.
            database_bytes=int(snapshot.sql('SELECT pg_database_size(current_database())'))
            document_bytes=int(snapshot.call('run','--rm','--no-deps','-T','--entrypoint','du','api','-sb','/app/var/documents').split()[0])
            disk_check(root,minimum+int((database_bytes+document_bytes)*1.25))
            destination=root/'var/backups'/('deploy-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
            create_backup(snapshot.command,destination,env=snapshot.env)
            report['backup']=str(destination.relative_to(root))
        if not args.rollback and not recovery:
            report['phase']='database'
            stack.call('up','-d','--no-deps','--wait','--wait-timeout','120','db')
            report['phase']='migration'
            stack.call('run','--rm','--no-deps','-T','--entrypoint','alembic','api','upgrade','head')
        report['schema_after']=stack.revision()
        if not can_rollback(release,report['schema_after']):raise DeploymentError('Unexpected database revision')
        report['phase']='start'
        stack.call('up','-d','--no-deps','--wait','--wait-timeout','180','--scale','api=1','--scale','web=1','api','web')
        stack.check_health('db','api','web')
        report['phase']='https'
        https_check()
        if previous:point_to(root,'previous',previous.bundle)
        point_to(root,'current',bundle)
        report['phase']='complete';report['status']='success'
    except Exception:
        # Never downgrade/restore the database automatically. Reopen the previous application only
        # when its declared, tested schema is still compatible; otherwise leave HTTP closed.
        try:stack.call('stop','--timeout','150','web','api')
        except Exception:pass
        if previous:
            try:
                actual=previous.revision()
                if can_rollback(previous.release,actual):
                    previous.call('up','-d','--no-deps','--wait','--wait-timeout','180','api','web')
                    report['previous_application_restarted']=True
            except Exception:report['previous_application_restarted']=False
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--allow-migration',action='store_true')
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--recover-from',type=Path,help='Explicit source bundle of a failed first installation at start; no migrations')
    parser.add_argument('--registry-login',action='store_true',help='Read ephemeral registry credentials from SSH stdin')
    args=parser.parse_args()
    os.umask(0o077)
    report={'status':'failed','phase':'validation','started_at':datetime.now(timezone.utc).isoformat()}
    try:
        if os.name!='posix' or sys.version_info<(3,11):raise DeploymentError('Linux VPS with Python 3.11+ required')
        if not args.root.is_dir() or args.root.stat().st_mode & 0o022:
            raise DeploymentError('Deployment root must exist and not be writable by other users')
        verify_registry_tls()
        if args.registry_login:
            credentials=json.load(sys.stdin)
            if not all(isinstance(credentials.get(key),str) and credentials[key] for key in ('username','password')):
                raise DeploymentError('Registry credentials missing')
            directory=args.root.resolve()/'var/deployment-auth'
            directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            with tempfile.TemporaryDirectory(dir=directory,prefix='registry-') as temporary:
                os.environ['DOCKER_CONFIG']=temporary
                login=subprocess.run(['docker','login','--username',credentials['username'],'--password-stdin',
                    'registry.adelinemeistertzheim.fr'],input=credentials.pop('password'),text=True,capture_output=True)
                if login.returncode:raise DeploymentError('Registry login failed; check credentials and trusted TLS')
                execute(args,report)
        else:execute(args,report)
    except Exception as error:
        report['error_category']=type(error).__name__
        # Only explicit, fixed deployment messages may appear; no subprocess output or traceback.
        if isinstance(error,DeploymentError):report['error']=str(error)
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    (Path(__file__).resolve().parent/'deployment-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Deployment {report["status"]}; phase={report["phase"]}')
    return 0 if report['status']=='success' else 1


if __name__=='__main__':sys.exit(main())
