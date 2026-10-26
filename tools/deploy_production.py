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
import ssl
import time
import errno
import hashlib
from http.cookies import SimpleCookie

try:
    from .backup_local import create_backup
    from .release_manifest import COMPONENTS,validate_release
    from .public_beta_policy import validate_registration_config, PublicBetaPolicyError, SETTINGS_PROBE
    from . import release_security as security
except ImportError:  # Flat, reviewed CI release bundle on the VPS.
    from backup_local import create_backup
    from release_manifest import COMPONENTS,validate_release
    from public_beta_policy import validate_registration_config, PublicBetaPolicyError, SETTINGS_PROBE
    import release_security as security

HOST='documind.adelinemeistertzheim.fr'
PROJECT='documind-prod'


class DeploymentError(Exception):pass


def registration_policy(environment,revision,approved=False):
    try:
        return validate_registration_config(environment,revision,approved)
    except PublicBetaPolicyError as error:
        raise DeploymentError(str(error)) from None


def check_public_quota(stack):
    """Read only. Operators must close explicitly; deployment never changes admissions."""
    raw=stack.sql("SELECT json_build_object('closed',closed,'issued_count',issued_count)::text "
                  "FROM public_registration_quota WHERE id='public'")
    try:
        quota=json.loads(raw)
    except (ValueError,TypeError):
        raise DeploymentError('Public beta requires an unambiguous closed SQL quota') from None
    if (not isinstance(quota,dict) or quota.get('closed') is not True
            or type(quota.get('issued_count')) is not int or not 0<=quota['issued_count']<=5):
        raise DeploymentError('Public beta requires a closed SQL quota with a valid cumulative counter')
    return {'closed':True,'issued_count':quota['issued_count']}


def run(command,env=None):
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    if result.returncode:
        # Never echo Docker config, subprocess output, credentials or provider errors to CI.
        raise DeploymentError('Command failed')
    return result.stdout.strip()


def images_env(release):
    return ''.join(f'{variable}={release["images"][name]}\n' for name,variable in COMPONENTS.items())


def schema_compatible(release,revision):
    return revision in release['supported_schema_revisions']


def can_rollback(release,revision,*,security_verified=False,require_security=True):
    return schema_compatible(release,revision) and (security_verified is True or not require_security)


def public_history(stack,revision):
    if revision!='0007':return False
    raw=stack.sql("SELECT json_build_object('has_public_users',EXISTS(SELECT 1 FROM users WHERE registration_kind='public'), "
                  "'issued_count',issued_count,'closed',closed)::text FROM public_registration_quota WHERE id='public'")
    try:data=security.strict_json(raw)
    except security.SecurityError:raise DeploymentError('Cannot establish public account history') from None
    if (not isinstance(data,dict) or type(data.get('has_public_users')) is not bool
            or type(data.get('issued_count')) is not int or not 0<=data['issued_count']<=5
            or type(data.get('closed')) is not bool):
        raise DeploymentError('Missing or incoherent public account history; manual review required')
    return data['has_public_users'] or data['issued_count']>0


def authorize_start(stack,revision,*,required=False,closed=False):
    history=public_history(stack,revision)
    if closed or history:check_public_quota(stack)
    required=required or history or 'security_profile' in stack.release
    if required:
        if not schema_compatible(stack.release,revision):raise DeploymentError('Incompatible secure application schema')
        try:evidence=security.authorize(stack.bundle,stack.release)
        except security.SecurityError as error:raise DeploymentError(str(error)) from None
        return evidence
    return {'profile':None,'independently_approved':False,'legacy_history_free':True}


def check_backup_guard(root,bundle):
    try:
        for name in ('backup_production.py','release_security.py'):
            actual=security.read_admin_file(root/'ops'/name)
            expected=security.read_file(bundle/name)
            if hashlib.sha256(actual).digest()!=hashlib.sha256(expected).digest():
                raise security.SecurityError('Installed backup restart guard differs from the approved release')
    except security.SecurityError as error:raise DeploymentError(str(error)) from None


def maintenance(root,release):
    path=root/'var/security-maintenance.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not os.path.lexists(path):
        with path.open('x',encoding='utf-8') as output:
            output.write(json.dumps({'format':1,'kind':'secure-release-maintenance','candidate_sha':release['git_sha']}))
        path.chmod(0o600)
    raw=security.read_file(path)
    data=security.strict_json(raw)
    if not isinstance(data,dict) or data.get('kind')!='secure-release-maintenance' or data.get('format')!=1:
        raise DeploymentError('Ambiguous security maintenance state')
    return path,hashlib.sha256(raw).hexdigest()


def finish_maintenance(marker):
    if marker:
        path,digest=marker
        if hashlib.sha256(security.read_file(path)).hexdigest()!=digest:
            raise DeploymentError('Security maintenance changed; manual inspection required')
        path.unlink()


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


def check_config(stack,approve_public_beta=False):
    config=json.loads(stack.call('config','--format','json'))
    services=config['services']
    for service,component in (('api','backend'),('web','frontend'),('db','postgres')):
        if services[service]['image']!=stack.release['images'][component]:
            raise DeploymentError('Resolved images differ from the approved manifest')
    if set(services)!={'db','api','web'}:raise DeploymentError('Unexpected production services')
    for name in services:
        if services[name].get('ports') or services[name].get('build'):
            raise DeploymentError('Production must not publish ports or build images')
    registration_policy(services['api']['environment'],stack.release['schema_revision'],approve_public_beta)
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
        if stack.release.get('security_profile') and labels.get(security.LABEL)!=security.PROFILE:
            raise DeploymentError('Image security profile does not match approved evidence')


class HTTPSProbeError(DeploymentError):pass


class NoProbeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def https_network_failure(error):
    """Only allowlisted classifications and numeric codes; never serialize exception messages."""
    reason=error.reason if isinstance(error,urllib.error.URLError) else error
    details={}
    if isinstance(reason,ssl.SSLCertVerificationError):
        if isinstance(getattr(reason,'verify_code',None),int):details['tls_verify_code']=reason.verify_code
        return 'certificate_verification_failed',False,details
    if isinstance(reason,ssl.SSLError):return 'tls_error',False,details
    if isinstance(reason,socket.gaierror):
        details['network_errno']=reason.errno
        return 'dns_error',reason.errno==socket.EAI_AGAIN,details
    if isinstance(reason,TimeoutError):return 'network_timeout',True,details
    if isinstance(reason,OSError):
        if isinstance(reason.errno,int):details['network_errno']=reason.errno
        retry=reason.errno in {errno.ECONNREFUSED,errno.ECONNRESET,errno.ETIMEDOUT,errno.EHOSTUNREACH,errno.ENETUNREACH}
        return 'connection_error',retry,details
    return 'network_error',False,details


def secure_csrf_cookie(headers):
    for value in headers.get_all('Set-Cookie',[]):
        cookies=SimpleCookie()
        try:cookies.load(value)
        except Exception:continue
        cookie=cookies.get('__Host-documind-csrf')
        if (cookie and cookie.value and cookie['secure'] and cookie['httponly']
                and cookie['samesite'].lower()=='strict' and cookie['path']=='/' and not cookie['domain']):return True
    return False


def https_check(report=None,timeout_seconds=60,interval_seconds=2):
    if not 0<timeout_seconds<=120 or interval_seconds<=0:raise DeploymentError('Invalid HTTPS probe deadline')
    # Verify chain/hostname, refuse redirects, and retain no cookies between anonymous probes.
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoProbeRedirect())
    probes=[]
    if report is not None:report['https_probes']=probes
    deadline=time.monotonic()+timeout_seconds;attempt=0
    checks=(('/login',200),('/bff/health',200),('/bff/auth/csrf',200),('/bff/documents',401))
    while True:
        attempt+=1
        for path,expected in checks:
            event={'url':f'https://{HOST}{path}','attempt':attempt,'expected_status':expected}
            retry=False;remaining=deadline-time.monotonic()
            if remaining<=0:
                event['cause']='deadline_exceeded';probes.append(event)
                raise HTTPSProbeError(f'HTTPS deadline exceeded: {event["url"]}')
            try:
                try:
                    with opener.open(event['url'],timeout=min(5,remaining)) as response:
                        status,headers=response.status,response.headers
                except urllib.error.HTTPError as error:
                    status,headers=error.code,error.headers
                    error.close()
                event['http_status']=status
                if status!=expected:
                    event['cause']='unexpected_http_status'
                    retry=status in {404,408,425,429,502,503,504}
                elif path.endswith('/csrf') and not secure_csrf_cookie(headers):event['cause']='invalid_csrf_cookie'
                else:
                    event['result']='ok';probes.append(event);continue
            except (urllib.error.URLError,OSError) as error:
                event['cause'],retry,details=https_network_failure(error)
                event.update(details)
            event['retryable']=retry;probes.append(event)
            if not retry or time.monotonic()>=deadline:
                raise HTTPSProbeError(f'HTTPS probe failed: {event["url"]}; {event["cause"]}; HTTP {event.get("http_status","none")}') from None
            time.sleep(min(interval_seconds,max(0,deadline-time.monotonic())))
            break
        else:return


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
    if revision!=original['schema_revision'] or not schema_compatible(release,revision):
        raise DeploymentError('Recovery requires the exact compatible live schema revision')
    return source_stack,revision


def verify_recovery_backup(root,evidence,revision):
    relative=Path(evidence.get('backup',''))
    destination=(root/relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or destination.parent!=root/'var/backups':
        raise DeploymentError('Recovery requires an existing private backup under var/backups')
    try:
        manifest=json.loads((destination/'manifest.json').read_text())
        names={'database.dump','documents.tar.gz'}
        if (manifest['migration']!=revision or manifest['database_major']!=17
                or set(manifest['files'])!=names or set(manifest['sha256'])!=names):
            raise ValueError()
        for name in names:
            path=destination/name
            if path.is_symlink() or path.resolve().parent!=destination:raise ValueError()
            with path.open('rb') as source:
                if hashlib.file_digest(source,'sha256').hexdigest()!=manifest['sha256'][name]:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise DeploymentError('Recovery backup is missing, incompatible or has invalid checksums') from None


def recovery_after_https(root,bundle,path,release,proxy):
    """Follow an immutable failure chain: replaced apps from latest source, DB from first start."""
    if os.path.lexists(root/'current') or os.path.lexists(root/'previous'):
        raise DeploymentError('Recovery requires no current or previous release pointer')
    latest=path.resolve();source=latest;visited=set();chain=[]
    while True:
        if source.parent!=root/'releases' or source==bundle or source in visited or len(visited)>=8:
            raise DeploymentError('Recovery source chain is ambiguous, cyclic or outside releases')
        visited.add(source)
        try:
            original=validate_release(json.loads((source/'release.json').read_text()))
            evidence=json.loads((source/'deployment-report.json').read_text())
        except (OSError,ValueError):
            raise DeploymentError('Recovery requires every source manifest and failure report') from None
        if (evidence.get('status')!='failed' or evidence.get('git_sha')!=original['git_sha']
                or evidence.get('images')!=original['images'] or evidence.get('previous_sha')
                or evidence.get('schema_after')!=original['schema_revision']
                or original['schema_revision']!=release['schema_revision']):
            raise DeploymentError('Recovery source chain identity or schema does not match')
        chain.append((source,original,evidence))
        if evidence.get('phase')=='start' and 'schema_before' in evidence and evidence['schema_before'] is None:
            if len(chain)==1:raise DeploymentError('Post-HTTPS recovery requires a failed HTTPS source')
            break
        if evidence.get('phase')!='https' or evidence.get('schema_before')!=original['schema_revision']:
            raise DeploymentError('Recovery source must prove a failed HTTPS recovery without migration')
        verify_recovery_backup(root,evidence,original['schema_revision'])
        relative=Path(evidence.get('recovered_from',''))
        if relative.is_absolute() or '..' in relative.parts:
            raise DeploymentError('Invalid recovery parent path')
        source=(root/relative).resolve()
    origin_path,origin_release,_=chain[-1]
    for index,(_,_,evidence) in enumerate(chain[:-1]):
        if (evidence.get('source_sha')!=chain[index+1][1]['git_sha']
                or evidence.get('retained_database_image')!=origin_release['images']['postgres']):
            raise DeploymentError('Recovery chain does not prove the retained database image')
    stack=Stack(root,latest,chain[0][1],proxy)
    stack.database_source=Stack(root,origin_path,origin_release,proxy)
    check_config(stack);check_config(stack.database_source)
    verify_recovery_containers(stack)
    revision=stack.revision()
    if revision!=release['schema_revision'] or not schema_compatible(release,revision):
        raise DeploymentError('Recovery requires the exact compatible live schema revision')
    return stack,revision


def verify_recovery_containers(stack):
    identifiers=run(['docker','ps','-aq','--filter',f'label=com.docker.compose.project={PROJECT}']).splitlines()
    if len(identifiers)!=3:raise DeploymentError('Recovery requires exactly the three original service containers')
    containers=json.loads(run(['docker','inspect',*identifiers]))
    seen=set()
    for container in containers:
        labels=container['Config'].get('Labels',{})
        service=labels.get('com.docker.compose.service')
        owner=getattr(stack,'database_source',stack) if service=='db' else stack
        if (labels.get('com.docker.compose.project')!=PROJECT or service not in ('db','api','web')
                or service in seen or labels.get('com.docker.compose.oneoff','false').lower()!='false'
                or labels.get('com.docker.compose.project.config_files')!=str(owner.bundle/'compose.production.yaml')):
            raise DeploymentError('Ambiguous recovery container ownership or source bundle')
        seen.add(service)
        component={'db':'postgres','api':'backend','web':'frontend'}[service]
        image=run(['docker','image','inspect',owner.release['images'][component],'--format','{{.Id}}'])
        if container['Image']!=image:raise DeploymentError('Recovery container image differs from source manifest')
        if service=='db' and (not container['State']['Running'] or container['State'].get('Health',{}).get('Status')!='healthy'):
            raise DeploymentError('Recovery requires the existing healthy database')
        # Match the Compose volume root, not STORAGE_DIR (a subdirectory of /app/var).
        # tmpfs mounts are ephemeral; all other mounts must be explicitly expected.
        mounts=[mount for mount in container['Mounts'] if mount.get('Type')!='tmpfs']
        if service in ('db','api'):
            destination='/var/lib/postgresql/data' if service=='db' else '/app/var'
            volume=f'{PROJECT}_production_'+('database' if service=='db' else 'documents')
            if (len(mounts)!=1 or mounts[0].get('Type')!='volume' or mounts[0].get('Name')!=volume
                    or mounts[0].get('Destination')!=destination):
                raise DeploymentError('Recovery refuses unexpected persistent mounts')
        elif mounts:raise DeploymentError('Recovery refuses unexpected persistent mounts')


def execute(args,report):
    import fcntl
    root=args.root.resolve();bundle=(getattr(args,'bundle',None) or Path(__file__).resolve().parent).resolve()
    if bundle.parent!=root/'releases':raise DeploymentError('Release must be staged under the deployment releases directory')
    secret=root/'.env.production'
    if not secret.is_file() or (os.name=='posix' and secret.stat().st_mode & 0o077):
        raise DeploymentError('Production environment must exist and have mode 0600')
    lock=(root/'deployment.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (root/'var/backup-maintenance.json').exists():
        raise DeploymentError('Backup maintenance is pending; resume services before deployment')
    release=validate_release(json.loads((bundle/'release.json').read_text(encoding='utf-8')))
    report['git_sha']=release['git_sha'];report['images']=release['images']
    stack=Stack(root,bundle,release)
    report['phase']='preflight'
    recovery=getattr(args,'recover_from',None)
    after_https=getattr(args,'recover_after_https',None)
    if recovery and after_https:raise DeploymentError('Choose exactly one recovery procedure')
    recovery=recovery or after_https
    if recovery and (args.initialize or args.rollback or args.allow_migration):
        raise DeploymentError('Recovery cannot be combined with initialization, rollback or migration approval')
    values=resolve_proxy(stack)
    approval=getattr(args,'approve_public_beta',False)
    config=check_config(stack,approval)
    mode=config['services']['api']['environment'].get('REGISTRATION_MODE','disabled')
    minimum=int(values.get('DEPLOY_MIN_FREE_GIB','8'))*(1024**3)
    if minimum<4*(1024**3):raise DeploymentError('Deployment disk threshold must be at least 4 GiB')
    disk_check(root,minimum)
    check_volume_state(args.initialize)
    previous=current_stack(root,stack.env['BFF_TRUSTED_PROXY_IPS'])
    source=None
    if recovery:
        recover=recovery_after_https if after_https else recovery_source
        source,before=recover(root,bundle,recovery,release,stack.env['BFF_TRUSTED_PROXY_IPS'])
        report['recovered_from']=str(source.bundle.relative_to(root))
        report['source_sha']=source.release['git_sha']
        report['retained_database_image']=getattr(source,'database_source',source).release['images']['postgres']
    if previous:
        report['previous_sha']=previous.release['git_sha']
    if mode=='public' and (args.initialize or recovery or previous is None):
        raise DeploymentError('Public beta requires an existing closed schema 0007 installation')
    if not args.initialize and previous is None and not recovery:
        raise DeploymentError('Existing deployment must be adopted explicitly before automated updates')
    if args.initialize and previous is not None:raise DeploymentError('Initialization refuses an existing release')
    if args.rollback and args.initialize:raise DeploymentError('Cannot initialize a rollback')
    if not recovery:before=previous.revision() if previous else None
    if args.rollback and not schema_compatible(release,before):
        raise DeploymentError('Rollback application does not support the current database schema')
    if before and before!=release['schema_revision'] and not (args.allow_migration or args.rollback):
        raise DeploymentError('A schema change requires explicit migration approval')
    report['schema_before']=before
    previous_mode='disabled'
    if previous:
        previous_mode=check_config(previous,approval)['services']['api']['environment'].get('REGISTRATION_MODE','disabled')
    if mode=='public':
        if before!='0007':raise DeploymentError('Public beta requires an existing closed schema 0007 installation')
        report['public_beta']={'approved':True,'preparation_only':True,'limit':5,
                               'quota_before':check_public_quota(previous)}
    history=public_history(source or previous,before) if source or previous else False
    strict=bool(args.rollback or mode=='public' or previous_mode=='public' or history or os.path.lexists(root/'var/security-maintenance.json') or 'security_profile' in release
                or (previous and 'security_profile' in previous.release))
    closed=mode=='public' or previous_mode=='public' or history
    report['release_security']={'required':strict,'public_history':history}
    # Authenticate immutable metadata before pulling, quiescing services or migrations.
    # Initial installs/approved upgrades check the target schema here and the live schema again below.
    if strict:
        try:report['release_security']['candidate']=security.authorize(bundle,release)
        except security.SecurityError as error:raise DeploymentError(str(error)) from None
        check_backup_guard(root,bundle)
    if closed:check_public_quota(source or previous)
    report['phase']='pull'
    stack.call('pull','db','api','web')
    verify_images(stack)
    report['phase']='settings'
    effective=stack.call('run','--rm','--no-deps','-T','--entrypoint','python','api','-c',SETTINGS_PROBE)
    try:effective=json.loads(effective)
    except (ValueError,TypeError):raise DeploymentError('Invalid effective registration settings probe') from None
    if (not isinstance(effective,dict) or effective.get('LEGACY_API_ENABLED') is not False
            or registration_policy(effective,release['schema_revision'],approval)!=mode):
        raise DeploymentError('Effective registration mode differs from resolved configuration')
    marker=None
    try:
        if strict:marker=maintenance(root,release)
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
        if mode=='public' and check_public_quota(stack)!=report['public_beta']['quota_before']:
            raise DeploymentError('Public quota changed during preparation; operator review required')
        if not args.rollback and not recovery:
            report['phase']='database'
            stack.call('up','-d','--no-deps','--wait','--wait-timeout','120','db')
            report['phase']='migration'
            stack.call('run','--rm','--no-deps','-T','--entrypoint','alembic','api','upgrade','head')
        report['schema_after']=stack.revision()
        if not schema_compatible(release,report['schema_after']):raise DeploymentError('Unexpected database revision')
        if mode=='public' and check_public_quota(stack)!=report['public_beta']['quota_before']:
            raise DeploymentError('Public quota changed before application startup')
        report['phase']='start'
        authorize_start(stack,report['schema_after'],required=strict,closed=closed)
        if strict:check_backup_guard(root,bundle)
        verify_images(stack)
        stack.call('up','-d','--no-deps','--wait','--wait-timeout','180','--scale','api=1','--scale','web=1','api','web')
        stack.check_health('db','api','web')
        report['phase']='https'
        https_check(report)
        if mode=='public':
            report['public_beta']['quota_after']=check_public_quota(stack)
            if report['public_beta']['quota_after']!=report['public_beta']['quota_before']:
                raise DeploymentError('Public quota changed before release activation')
        authorize_start(stack,report['schema_after'],required=strict,closed=closed)
        if previous:point_to(root,'previous',previous.bundle)
        point_to(root,'current',bundle)
        finish_maintenance(marker)
        report['phase']='complete';report['status']='success'
    except Exception:
        # Never downgrade/restore the database automatically. Reopen the previous application only
        # when its declared, tested schema is still compatible; otherwise leave HTTP closed.
        try:stack.call('stop','--timeout','150','web','api')
        except Exception:pass
        report['previous_application_restarted']=False
        if previous:
            try:
                actual=previous.revision()
                previous_mode=check_config(previous,approval)['services']['api']['environment'].get('REGISTRATION_MODE','disabled')
                required_previous=strict or previous_mode=='public' or public_history(previous,actual)
                if required_previous and marker is None:marker=maintenance(root,release)
                previous_evidence=authorize_start(previous,actual,required=required_previous,closed=closed or previous_mode=='public')
                if can_rollback(previous.release,actual,security_verified=previous_evidence['independently_approved'],require_security=required_previous):
                    if required_previous:check_backup_guard(root,previous.bundle)
                    verify_images(previous)
                    previous.call('up','-d','--no-deps','--wait','--wait-timeout','180','api','web')
                    previous.check_health('db','api','web')
                    report['previous_application_restarted']=True
                    finish_maintenance(marker)
            except Exception:
                report['release_security']['previous_refused']=True
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--bundle',type=Path,help='Candidate data bundle; execute the trusted controller, never an old candidate script')
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--allow-migration',action='store_true')
    parser.add_argument('--approve-public-beta',action='store_true',help='Approve public/5 preparation with an already closed SQL gate; never opens admissions')
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--recover-from',type=Path,help='Explicit source bundle of a failed first installation at start; no migrations')
    parser.add_argument('--recover-after-https',type=Path,help='Explicit failed HTTPS recovery source; verify original DB and replaced apps; no migrations')
    parser.add_argument('--registry-login',action='store_true',help='Read ephemeral registry credentials from SSH stdin')
    args=parser.parse_args()
    os.umask(0o077)
    bundle=(args.bundle or Path(__file__).resolve().parent).resolve()
    if bundle.parent!=args.root.resolve()/'releases':
        print('Candidate bundle must be staged directly under releases')
        return 1
    report_path=bundle/'deployment-report.json'
    if os.path.lexists(report_path):
        print('Existing deployment report preserved; stage a new reviewed bundle for this attempt')
        return 1
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
    try:
        with report_path.open('x',encoding='utf-8') as output:output.write(json.dumps(report,indent=2)+'\n')
    except FileExistsError:
        print('Deployment report already exists; refusing to overwrite evidence')
        return 1
    print(f'Deployment {report["status"]}; phase={report["phase"]}')
    return 0 if report['status']=='success' else 1


if __name__=='__main__':sys.exit(main())
