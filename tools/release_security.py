"""CI statements + independently administered root trust. Hashes are NOT signatures."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from uuid import UUID

PROFILE='public-beta-2026-10-v1'
LABEL='io.documind.security-profile'
TRUST_PATH=Path('/etc/documind-ai/release-security-trust.json')
STATEMENT='security-attestation.json'
LEGACY_BUNDLE_FILES=frozenset(('release.json','compose.production.yaml','deploy_production.py',
    'backup_local.py','backup_production.py','release_manifest.py','public_beta_policy.py','release_security.py'))
PRE_ERASURE_BUNDLE_FILES=frozenset(('release.json','compose.production.yaml','deploy_production.py',
    'backup_local.py','backup_production.py','verify_snapshot.py','validate_restore.py',
    'retention_production.py','monitor_production.py','gmail_monitor_alert.py',
    'documind-backup.service','documind-backup.timer','documind-backup-alert.service',
    'documind-monitor.service','documind-monitor.timer',
    'documind-retention.service','documind-retention.timer',
    'release_manifest.py','public_beta_policy.py','release_security.py'))
BUNDLE_FILES=PRE_ERASURE_BUNDLE_FILES|{'compose.erasure.yaml'}
ERASURE_TARGETS=('/run/docnelo-erasure/authority','/run/docnelo-erasure/requests')
ERASURE_KEYS=('ERASURE_AUTHORITY_HOST_DIR','ERASURE_REQUESTS_HOST_DIR',
              'ERASURE_INSTANCE_ID','ERASURE_APPLICATION_UID')


class SecurityError(ValueError):pass


def strict_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise SecurityError('Ambiguous security metadata')
            result[key]=value
        return result
    try:return json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,TypeError,UnicodeError):raise SecurityError('Invalid security metadata') from None


def read_file(path):
    try:
        descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(descriptor,'rb') as source:
            info=os.fstat(source.fileno())
            if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_size>1024*1024:
                raise SecurityError('Invalid security evidence file')
            raw=source.read(1024*1024+1)
            if len(raw)>1024*1024:raise SecurityError('Oversized security evidence')
            return raw
    except OSError:raise SecurityError('Missing security evidence') from None


def read_admin_file(path):
    """Root-owned metadata/code in a root-owned non-writable directory; no symlink."""
    if sys.platform!='linux':raise SecurityError('Security trust requires Linux ownership checks')
    try:
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            directory=os.fstat(parent)
            if directory.st_uid!=0 or directory.st_mode&0o022:raise SecurityError('Untrusted security directory')
            descriptor=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
            with os.fdopen(descriptor,'rb') as source:
                info=os.fstat(source.fileno())
                if info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISREG(info.st_mode) or info.st_size>262144:
                    raise SecurityError('Untrusted security registry')
                raw=source.read(262145)
                if len(raw)>262144:raise SecurityError('Oversized security registry')
        finally:os.close(parent)
    except OSError:raise SecurityError('Security registry unavailable; administrator approval required') from None
    return raw


def load_trust():
    # No CLI/env override: this trust anchor is outside all writable release bundles.
    return strict_json(read_admin_file(TRUST_PATH))


def validate_statement(bundle,release):
    if release.get('security_profile')!=PROFILE:raise SecurityError('Release has no recognized security profile')
    if not isinstance(release.get('git_sha'),str) or not re.fullmatch('[a-f0-9]{40}',release['git_sha']):
        raise SecurityError('Invalid attested SHA')
    images=release.get('images')
    if not isinstance(images,dict) or set(images)!={'backend','frontend','postgres'}:
        raise SecurityError('Invalid attested image set')
    for component,reference in images.items():
        if not isinstance(reference,str) or not re.fullmatch(re.escape('registry.adelinemeistertzheim.fr/documind-ai/'+component+'@sha256:')+'[a-f0-9]{64}',reference):
            raise SecurityError('Invalid attested image digest')
    raw=read_file(bundle/STATEMENT);data=strict_json(raw)
    if not isinstance(data,dict) or set(data)!={'format','profile','git_sha','schema_revision','images','bundle_sha256','producer'}:
        raise SecurityError('Invalid security statement structure')
    if (type(data['format']) is not int or data['format']!=1 or data['profile']!=PROFILE
            or data['git_sha']!=release['git_sha'] or data['schema_revision'] not in ('0007','0008')
            or release['schema_revision']!=data['schema_revision'] or data['images']!=release['images']):
        raise SecurityError('Security statement identity mismatch')
    if strict_json(read_file(bundle/'release.json'))!=release:raise SecurityError('Security manifest mismatch')
    hashes=data['bundle_sha256']
    if not isinstance(hashes,dict) or set(hashes) not in (BUNDLE_FILES,PRE_ERASURE_BUNDLE_FILES,LEGACY_BUNDLE_FILES):
        raise SecurityError('Incomplete security bundle')
    for name,digest in hashes.items():
        if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) or hashlib.sha256(read_file(bundle/name)).hexdigest()!=digest:
            raise SecurityError('Security bundle checksum mismatch')
    producer=data['producer']
    if (not isinstance(producer,dict) or set(producer)!={'repository','workflow','run_id','run_attempt'}
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',str(producer['repository']))
            or producer['workflow']!='.github/workflows/ci.yml'
            or any(not re.fullmatch('[1-9][0-9]*',str(producer[key])) for key in ('run_id','run_attempt'))):
        raise SecurityError('Invalid CI statement provenance')
    return data,hashlib.sha256(raw).hexdigest()


def validate_operational_bundle(bundle,release,*,rollback=False):
    data,digest=validate_statement(bundle,release)
    names=set(data['bundle_sha256'])
    legacy=names==LEGACY_BUNDLE_FILES
    if names not in (BUNDLE_FILES,PRE_ERASURE_BUNDLE_FILES,LEGACY_BUNDLE_FILES):
        raise SecurityError('Unrecognized operational bundle inventory')
    if names!=BUNDLE_FILES and not rollback:
        raise SecurityError('Pre-erasure and legacy release bundles are rollback-only')
    actual={path.name for path in bundle.iterdir()}
    if actual!=names|{STATEMENT}:
        raise SecurityError('Operational bundle contains missing or unverified files')
    if not legacy:
        required_units={
            'documind-backup.service':('backup_production.py',''),
            'documind-backup-alert.service':('backup_production.py','--alert'),
            'documind-monitor.service':('monitor_production.py','--reminder-hours 72'),
            'documind-retention.service':('retention_production.py','--simulate'),
        }
        for unit, (script, arguments) in required_units.items():
            lines=(bundle/unit).read_text(encoding='utf-8').splitlines()
            commands=[line.partition('=')[2] for line in lines if line.startswith('ExecStart=')]
            expected=f'/usr/bin/python3 /srv/documind-ai/current/{script}'
            if len(commands)!=1 or not commands[0].startswith(expected):
                raise SecurityError('Systemd unit does not target its attested current-release script')
            if arguments and arguments not in commands[0]:
                raise SecurityError('Systemd unit arguments do not match the release contract')
        backup=(bundle/'documind-backup.service').read_text(encoding='utf-8')
        stop_commands=[line.partition('=')[2] for line in backup.splitlines()
                       if line.startswith('ExecStopPost=')]
        if stop_commands!=['/usr/bin/python3 /srv/documind-ai/current/backup_production.py --resume']:
            raise SecurityError('Backup resume guard does not target the attested current release')
        timers={
            'documind-backup.timer':'documind-backup.service',
            'documind-monitor.timer':'documind-monitor.service',
            'documind-retention.timer':'documind-retention.service',
        }
        for timer,service in timers.items():
            if f'Unit={service}' not in (bundle/timer).read_text(encoding='utf-8').splitlines():
                raise SecurityError('Systemd timer does not target its attested service')
    return data,digest


def erasure_configuration(values):
    selected={key:values.get(key) for key in ERASURE_KEYS}
    runtime=[values.get(key) for key in ('ERASURE_AUTHORITY_DIR','ERASURE_REQUESTS_DIR')]
    if not any(value is not None for value in (*selected.values(),*runtime)):
        return None
    if not all(isinstance(value,str) and value for value in selected.values()):
        raise SecurityError('Complete explicit erasure deployment configuration required')
    for key in ERASURE_KEYS[:2]:
        path=PurePosixPath(selected[key])
        if (path.root!='/' or '..' in path.parts or str(path)!=selected[key]
                or any(ord(char)<32 or char==',' for char in selected[key])):
            raise SecurityError('Canonical absolute erasure host paths required')
    try:
        if str(UUID(selected['ERASURE_INSTANCE_ID']))!=selected['ERASURE_INSTANCE_ID']:
            raise ValueError()
        uid=selected['ERASURE_APPLICATION_UID']
        if not re.fullmatch('[1-9][0-9]{0,9}',uid) or int(uid)>2147483647:
            raise ValueError()
    except (ValueError,TypeError):
        raise SecurityError('Invalid erasure instance or non-root application UID') from None
    if any(value is not None and value!=target for value,target in zip(runtime,ERASURE_TARGETS)):
        raise SecurityError('Unexpected erasure application paths')
    return selected


def erasure_binding(root):
    path=root/'var/erasure-deployment.json'
    for directory in (root/'var',):
        if os.path.lexists(directory) and (directory.is_symlink() or not directory.is_dir()):
            raise SecurityError('Unsafe erasure deployment binding directory')
    if not os.path.lexists(path):return None
    directory=(root/'var').stat()
    if os.name=='posix' and (directory.st_mode&0o077 or directory.st_uid not in (0,root.stat().st_uid)):
        raise SecurityError('Unsafe erasure deployment binding directory')
    info=path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
            or os.name=='posix' and (info.st_mode&0o077 or info.st_uid not in (0,root.stat().st_uid))):
        raise SecurityError('Unsafe erasure deployment binding')
    data=strict_json(read_file(path))
    if not isinstance(data,dict) or set(data)!=set(ERASURE_KEYS) or erasure_configuration(data)!=data:
        raise SecurityError('Invalid erasure deployment binding')
    return data


def erasure_compose_files(root,bundle,release,values):
    configuration=erasure_configuration(values)
    pinned=erasure_binding(root)
    if pinned is not None and pinned!=configuration:
        raise SecurityError('Erasure deployment binding changed or removed; maintenance review required')
    files=[bundle/'compose.production.yaml']
    if configuration is not None:
        data,_=validate_operational_bundle(bundle,release)
        if set(data['bundle_sha256'])!=BUNDLE_FILES or release['schema_revision']!='0008':
            raise SecurityError('Erasure requires the current schema 0008 attested bundle')
        authorize(bundle,release)
        files.append(bundle/'compose.erasure.yaml')
    return files,configuration


def pin_erasure_configuration(root,configuration):
    if configuration is None:
        if erasure_binding(root) is not None:
            raise SecurityError('Cannot remove the erasure deployment binding')
        return
    existing=erasure_binding(root)
    if existing is not None:
        if existing!=configuration:raise SecurityError('Erasure deployment binding changed')
        return
    directory=root/'var'
    directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink() or os.name=='posix' and directory.stat().st_mode&0o077:
        raise SecurityError('Erasure deployment binding directory must be private')
    path=directory/'erasure-deployment.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as output:
        json.dump(configuration,output,sort_keys=True)
        output.write('\n');output.flush();os.fsync(output.fileno())
    for parent in (directory,root):
        fd=os.open(parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
        try:os.fsync(fd)
        finally:os.close(fd)


def validate_erasure_mounts(root,config,configuration,docker_root):
    api=config['services']['api']
    mounts=api.get('volumes',[])
    selected=[mount for mount in mounts if mount.get('target') in ERASURE_TARGETS]
    environment=api.get('environment',{})
    runtime_keys=('ERASURE_AUTHORITY_DIR','ERASURE_REQUESTS_DIR','ERASURE_INSTANCE_ID','ERASURE_APPLICATION_UID')
    if configuration is None:
        if selected or any(key in environment for key in runtime_keys):
            raise SecurityError('Unselected erasure application configuration')
        return mounts
    if sys.platform!='linux':raise SecurityError('Native Linux erasure deployment required')
    if not docker_root or not Path(docker_root).is_absolute():
        raise SecurityError('Docker data root required for erasure mount validation')
    expected=(*ERASURE_TARGETS,configuration['ERASURE_INSTANCE_ID'],configuration['ERASURE_APPLICATION_UID'])
    if any(str(environment.get(key))!=value for key,value in zip(runtime_keys,expected)):
        raise SecurityError('Erasure environment differs from its approved binding')
    uid=int(configuration['ERASURE_APPLICATION_UID'])
    if (api.get('privileged') or api.get('cap_add') or api.get('devices')
            or api.get('user') not in (None,str(uid),f'{uid}:{uid}')
            or api.get('read_only') is not True or 'ALL' not in api.get('cap_drop',[])
            or 'no-new-privileges:true' not in api.get('security_opt',[])):
        raise SecurityError('Erasure API must retain its unprivileged read-only runtime')
    paths=[Path(configuration[key]) for key in ERASURE_KEYS[:2]]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a,b in [(paths[0],paths[1])]):
        raise SecurityError('Erasure directories must be independent')
    for index,(path,target,owner) in enumerate(zip(paths,ERASURE_TARGETS,(0,uid))):
        matches=[mount for mount in selected if mount.get('target')==target]
        if (len(matches)!=1 or matches[0].get('type')!='bind' or matches[0].get('source')!=str(path)
                or bool(matches[0].get('read_only'))!=(index==0)
                or matches[0].get('bind',{}).get('create_host_path') is not False):
            raise SecurityError('Unexpected erasure bind mount')
        try:
            for parent in path.parents:
                info=parent.lstat()
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,owner)
                        or info.st_mode&0o022 and not (info.st_uid==0 and info.st_mode&stat.S_ISVTX)):
                    raise SecurityError('Unsafe erasure directory ancestry')
            info=path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=owner
                    or info.st_mode&(0o077 if index else 0o022)):
                raise SecurityError('Unsafe erasure directory permissions')
        except OSError:raise SecurityError('Erasure authority or request directory unavailable') from None
        if any(path.is_relative_to(base.resolve()) or base.resolve().is_relative_to(path)
               for base in (root,Path(docker_root))):
            raise SecurityError('Erasure evidence must be outside deployment and Docker data')
    return [mount for mount in mounts if mount.get('target') not in ERASURE_TARGETS]


def validate_erasure_container(container,configuration):
    mounts=[mount for mount in container.get('Mounts',[]) if mount.get('Destination') in ERASURE_TARGETS]
    if configuration is None:
        if mounts:raise SecurityError('Unexpected live erasure mounts')
        return
    host=container.get('HostConfig',{})
    if (host.get('Privileged') or host.get('CapAdd')
            or host.get('ReadonlyRootfs') is not True
            or 'ALL' not in host.get('CapDrop',[])
            or 'no-new-privileges:true' not in host.get('SecurityOpt',[])):
        raise SecurityError('Unexpected live erasure API privileges')
    uid=configuration['ERASURE_APPLICATION_UID']
    if container.get('Config',{}).get('User') not in ('app',uid,f'{uid}:{uid}'):
        raise SecurityError('Unexpected live erasure API identity')
    environment=dict(value.split('=',1) for value in container['Config'].get('Env',[]) if '=' in value)
    expected=(*ERASURE_TARGETS,configuration['ERASURE_INSTANCE_ID'],uid)
    for key,value in zip(('ERASURE_AUTHORITY_DIR','ERASURE_REQUESTS_DIR','ERASURE_INSTANCE_ID',
                          'ERASURE_APPLICATION_UID'),expected):
        if environment.get(key)!=value:raise SecurityError('Unexpected live erasure environment')
    for index,target in enumerate(ERASURE_TARGETS):
        matches=[mount for mount in mounts if mount.get('Destination')==target]
        if (len(matches)!=1 or matches[0].get('Type')!='bind'
                or matches[0].get('Source')!=configuration[ERASURE_KEYS[index]]
                or matches[0].get('RW') is not (index==1)):
            raise SecurityError('Unexpected live erasure bind mount')


def authorize(bundle,release):
    data,digest=validate_statement(bundle,release)
    trust=load_trust()
    if not isinstance(trust,dict) or set(trust)!={'format','releases'} or type(trust['format']) is not int or trust['format']!=1 or not isinstance(trust['releases'],dict):
        raise SecurityError('Invalid security registry structure')
    expected={'profile':PROFILE,'attestation_sha256':digest,**data['producer']}
    if trust['releases'].get(release['git_sha'])!=expected:
        raise SecurityError('Release is not independently approved for secure rollback')
    return {'profile':PROFILE,'attestation_sha256':digest,'independently_approved':True}


def make_statement(bundle,release,producer):
    data={'format':1,'profile':PROFILE,'git_sha':release['git_sha'],'schema_revision':release['schema_revision'],
          'images':release['images'],'producer':producer,
          'bundle_sha256':{name:hashlib.sha256(read_file(bundle/name)).hexdigest() for name in sorted(BUNDLE_FILES)}}
    # Never overwrite an existing statement or silently attest a legacy manifest.
    with (bundle/STATEMENT).open('x',encoding='utf-8') as output:output.write(json.dumps(data,indent=2)+'\n')
    validate_statement(bundle,release)
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['create','check','propose-trust'])
    parser.add_argument('bundle',type=Path)
    args=parser.parse_args()
    release=strict_json(read_file(args.bundle/'release.json'))
    if args.operation=='create':
        make_statement(args.bundle,release,{'repository':os.environ['GITHUB_REPOSITORY'],
            'workflow':'.github/workflows/ci.yml','run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT']})
    data,digest=validate_statement(args.bundle,release)
    if args.operation=='propose-trust':
        # Proposal only: no write to /etc, no approval, no claim of verified CI origin.
        print(json.dumps({'format':1,'releases':{release['git_sha']:{
            'profile':PROFILE,'attestation_sha256':digest,**data['producer']}}},indent=2))
    else:print(json.dumps({'structure_and_checksums_valid':True,'independent_approval_checked':False}))


if __name__=='__main__':main()
