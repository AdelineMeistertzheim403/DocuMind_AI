from contextlib import nullcontext
from datetime import datetime, timezone
import copy
import hashlib
import io
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
import sys
import os
import tempfile
from functools import lru_cache
from unittest.mock import patch

import pytest

from tools import retention_production as retention

NOW = datetime(2026,10,20,12,tzinfo=timezone.utc).timestamp()


@lru_cache(maxsize=1)
def lifecycle_archive():
    from backend.lifecycle_registry import Registry
    from backend.lifecycle_durability import ConfirmationStore
    from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
    from backend.lifecycle_holds import HoldStore
    from backend.lifecycle_admissions import AdmissionAnchor
    from backend.lifecycle_snapshot import STORES, write_snapshot_archive
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        variables = {'LIFECYCLE_DATA_ROOT': str(root), 'LIFECYCLE_BACKUP_LOCK_PATH': '',
                     'LIFECYCLE_CAPTURE_ID': '00000000-0000-4000-8000-000000000001'}
        paths = {}
        for name, (variable, _, _) in STORES.items():
            directory = root / name; directory.mkdir(mode=0o700)
            paths[name] = directory / (name + '.sqlite'); variables[variable] = str(paths[name])
        with patch.dict(os.environ, variables):
            Registry(paths['registry']).initialize()
            ConfirmationStore(paths['witness']).initialize()
            auth = AuthenticatedConfirmationStore(paths['authenticated'], os.urandom(32), 'documind-local-v2')
            auth.initialize(); HoldStore(paths['holds'], auth).initialize()
            AdmissionAnchor(paths['admission_anchor'], os.urandom(32)).initialize()
            os.environ['LIFECYCLE_BACKUP_LOCK_PATH'] = str(root / '.backup.lock')
            output = io.BytesIO(); metadata = write_snapshot_archive(output)
        return output.getvalue(), metadata


def make_daily(index, version=3):
    timestamp = NOW - index * 86400 - 3600
    stamp = datetime.fromtimestamp(timestamp,timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = 'daily-' + stamp + '-' + hashlib.md5(str(index).encode()).hexdigest()
    identifier = hashlib.sha256(name.encode()).hexdigest()
    archives = {'database.dump':f'dump-{index}'.encode(), 'documents.tar.gz':f'documents-{index}'.encode()}
    integrity = {name:{'count':2,'digest':'a'*32,'columns':['id']} for name in ('users','documents')}
    # Production's documents table contains the numeric identifier sha256.
    integrity['documents']['columns'] = ['id', 'owner_id', 'filename', 'sha256']
    manifest = {'database_major':17,'migration':'0006','files':list(archives),
        'sha256':{name:retention.digest(data) for name,data in archives.items()},
        'created_at':datetime.fromtimestamp(timestamp+60,timezone.utc).isoformat()}
    files = {**archives,'manifest.json':json.dumps(manifest,indent=2).encode(),'integrity.json':json.dumps(integrity,indent=2).encode()}
    if version == 3:
        payload, metadata = lifecycle_archive()
        files['lifecycle.sqlite.tar.gz'] = payload
        manifest.update(backup_format_version=3, capture_id=metadata['capture_id'], capture_complete=True,
            s2_recovery_authorized=False,
            recovery_disposition='quarantine_pending_independent_freshness_and_operator_review',
            capture_scope=['postgresql','documents','lifecycle_sqlite'],
            lifecycle_stores=metadata['stores'],
            lifecycle_store_sha256={name:item['sha256'] for name,item in metadata['stores'].items()},
            quiescence={**{name:True for name in ('api_web_stopped','only_database_service_running',
                'private_networks_exclusive','no_other_postgresql_clients','lifecycle_exclusive_lock_acquired')},
                'out_of_band_privileged_host_access':'trusted_operator_boundary_not_machine_verifiable'})
        payload_names = set(files) - {'manifest.json'}
        manifest['files'] = sorted(payload_names)
        manifest['sha256'] = {name:retention.digest(files[name]) for name in payload_names}
    elif version == 2:
        manifest['backup_format_version'] = 2
    files['manifest.json'] = json.dumps(manifest,indent=2).encode()
    row = {'id':identifier,'time':datetime.fromtimestamp(timestamp+120,timezone.utc).isoformat(),
        'tags':['documind-ai',name],'paths':['/srv/documind-ai/var/backups/'+name]}
    return row,files


@pytest.fixture
def inventory(tmp_path):
    root=tmp_path/'vps'; parent=root/'var/backups';parent.mkdir(parents=True)
    days=[make_daily(index) for index in range(65)]
    protected=[{'id':prefix+str(index+1)*56,'time':'2025-01-01T00:00:00Z',
                'tags':['manual-restore-validation'],'paths':['/private-legacy-path']} for index,prefix in enumerate(retention.PROTECTED)]
    rows=[row for row,_ in days]+protected
    other={'id':'f'*64,'time':'2026-10-01T00:00:00Z','tags':['other-app'],'paths':['/other-app-private']}
    rows.append(other)
    class Repo:
        calls=[]
        def inventory(self):return copy.deepcopy(rows),'repository-fingerprint'
        def metadata(self,identifier,path):
            self.calls.append(('metadata',identifier,path))
            files=next(files for row,files in days if row['id']==identifier)
            raw=files[path.rsplit('/',1)[1]]
            return raw,retention.backup.restic_json(raw)
        def file_hash(self,identifier,path):
            self.calls.append(('hash',identifier,path))
            files=next(files for row,files in days if row['id']==identifier)
            raw=files[path.rsplit('/',1)[1]]
            return retention.digest(raw),len(raw)
    for row,files in days[:20]:
        directory=parent/row['tags'][1];directory.mkdir()
        for name,data in files.items():(directory/name).write_bytes(data)
    return root,Repo(),rows,days


def test_default_plan_is_read_only_and_protects_copies(inventory):
    root,repo,rows,days=inventory
    before={str(path):path.read_bytes() for path in (root/'var/backups').rglob('*') if path.is_file()}
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['mode']=='simulation' and plan['real_execution_enabled'] is False and plan['status']=='simulated'
    assert plan['local']['examined']==20 and plan['local']['eligible']==20
    assert plan['local']['potential_bytes']==sum(item['bytes'] for item in plan['local']['would_remove'])
    local_ids={item['snapshot'] for item in plan['local']['would_remove']}
    remote_ids={item['snapshot'] for item in plan['remote']['would_remove']}
    assert not local_ids & remote_ids
    assert plan['latest_confirmed_snapshot'] not in remote_ids | local_ids
    assert not any(identifier.startswith(retention.PROTECTED) for identifier in remote_ids)
    assert rows[-1]['id'] not in remote_ids
    assert any(item['reason']=='other-usage' for item in plan['remote']['excluded'])
    assert before=={str(path):path.read_bytes() for path in (root/'var/backups').rglob('*') if path.is_file()}
    assert '/other-app-private' not in json.dumps(plan)


def test_policy_is_union_of_occupied_paris_days_iso_weeks_months():
    snapshots=[{'id':str(i),'time':NOW-i*86400} for i in range(270)]
    policy=retention.remote_policy(snapshots)
    assert sum('daily' in reasons for reasons in policy.values())==7
    assert sum('weekly' in reasons for reasons in policy.values())==4
    assert sum('monthly' in reasons for reasons in policy.values())==3
    assert 'latest-valid' in policy['0']
    # Multiple runs on the same day do not consume daily buckets.
    policy=retention.remote_policy([{'id':'new','time':NOW+60},*snapshots])
    assert 'daily' in policy['new'] and 'daily' not in policy['0']


@pytest.mark.parametrize('limits', [
    {'daily': 0, 'weekly': 4, 'monthly': 3},
    {'daily': 7, 'weekly': True, 'monthly': 3},
    {'daily': 7, 'weekly': 4, 'monthly': 366},
])
def test_policy_rejects_invalid_retention_limits(limits):
    with pytest.raises(retention.RetentionError, match='invalid_.*_retention'):
        retention.remote_policy([], **limits)


def test_plan_records_configured_retention_policy(inventory):
    root,repo,_,_=inventory
    plan=retention.build_plan(root,repo,'0006',NOW,daily=5,weekly=2,monthly=1)
    assert plan['retention_policy']=={'daily':5,'weekly':2,'monthly':1}
    assert all(item['reason'] != 'outside-7d-4w-3m' for item in plan['remote']['would_remove'])
    assert all(item['reason'] == 'outside-5d-2w-1m' for item in plan['remote']['would_remove'])


@pytest.mark.parametrize('change',['missing_file','unknown_file','checksum','integrity','migration','postgres','remote_archive','remote_metadata','remote_missing'])
def test_inconsistency_preserves_all_proposals(inventory,change,monkeypatch):
    root,repo,rows,days=inventory;row,files=days[12];directory=root/'var/backups'/row['tags'][1]
    if change=='missing_file':(directory/'database.dump').unlink()
    elif change=='unknown_file':(directory/'unexpected').write_text('unknown')
    elif change=='checksum':(directory/'database.dump').write_bytes(b'corrupt')
    elif change=='integrity':(directory/'integrity.json').write_text('{}')
    elif change in ('migration','postgres'):
        manifest=json.loads((directory/'manifest.json').read_text())
        manifest['migration' if change=='migration' else 'database_major']='0005' if change=='migration' else 16
        (directory/'manifest.json').write_text(json.dumps(manifest))
    elif change=='remote_archive':files['database.dump']=b'remote-corrupt'
    elif change=='remote_metadata':files['integrity.json']=files['integrity.json']+b' '
    elif change=='remote_missing':
        original=repo.file_hash
        def missing(identifier,path):
            if identifier==row['id']:raise retention.RetentionError('remote_file_not_verified')
            return original(identifier,path)
        monkeypatch.setattr(repo,'file_hash',missing)
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='attention-required' and plan['alerts']
    assert plan['local']['would_remove']==plan['remote']['would_remove']==[]
    assert directory.exists()


@pytest.mark.parametrize('change',['duplicate_id','duplicate_run','missing_restored','prefix_ambiguous','wrong_path','future','stale','unavailable'])
def test_ambiguous_repository_cannot_produce_plan(inventory,change,monkeypatch):
    root,repo,rows,days=inventory
    if change=='duplicate_id':rows.append(copy.deepcopy(rows[0]))
    elif change=='duplicate_run':
        duplicate=copy.deepcopy(rows[0]);duplicate['id']='a'*64;rows.append(duplicate)
    elif change=='missing_restored':rows[:]=[row for row in rows if not row['id'].startswith('51ac3259')]
    elif change=='prefix_ambiguous':
        protected=copy.deepcopy(rows[-3]);protected['id']='51ac3259'+'f'*56;rows.append(protected)
    elif change=='wrong_path':rows[0]['paths']=['/other-project']
    elif change=='future':rows[0]['time']='2030-01-01T00:00:00Z'
    elif change=='stale':rows[:]=rows[5:]
    elif change=='unavailable':
        monkeypatch.setattr(repo,'inventory',lambda:(_ for _ in ()).throw(retention.RetentionError('repository_unavailable_or_invalid')))
    with pytest.raises(retention.RetentionError):retention.build_plan(root,repo,'0006',NOW)


def test_special_tags_and_corresponding_local_archive_are_preserved(inventory):
    root,repo,rows,days=inventory;rows[12]['tags'].append('keep-forever')
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='simulated'
    assert any(item['snapshot']==rows[12]['id'] and item['reason']=='special-tags' for item in plan['remote']['excluded'])
    assert any(item['ref']==rows[12]['tags'][1] and item['reason']=='paired-protected-snapshot' for item in plan['local']['excluded'])


def test_protected_historical_daily_local_is_not_misclassified_as_missing(inventory):
    root,repo,rows,days=inventory
    row=rows[12];row['id']='3e6df673'+'a'*56
    rows[:]=[item for item in rows if not (item is not row and item['id'].startswith('3e6df673'))]
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='simulated'
    assert any(item['ref']==row['tags'][1] and item['reason']=='paired-protected-snapshot' for item in plan['local']['excluded'])


def test_manual_and_restore_directories_preserved_without_false_alert(inventory):
    root,repo,rows,days=inventory
    for name in ('sprint6-manual','restore-check','deploy-20261019-181649'):
        (root/'var/backups'/name).mkdir()
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='simulated' and len(plan['local']['excluded'])==3
    assert plan['local']['examined']==23


def test_symlink_path_is_refused(inventory,monkeypatch):
    root,repo,rows,days=inventory
    target=root/'var/backups'/rows[12]['tags'][1]
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda path:True if path==target else original(path))
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='attention-required' and not plan['local']['would_remove']


@pytest.mark.parametrize('approval', [False, True])
def test_report_hash_and_real_mode_are_locked(tmp_path,monkeypatch,capsys,approval):
    report={'mode':'simulation','status':'simulated'}
    name=retention.persist_report(tmp_path,report)
    saved=json.loads((tmp_path/name).read_text());checksum=saved.pop('plan_sha256')
    assert checksum==retention.digest(retention.canonical(saved))
    argv = ['retention_production.py', '--execute']
    if approval: argv += ['--approved-plan', str(tmp_path/name), '--plan-sha256', checksum]
    monkeypatch.setattr(sys,'argv',argv)
    monkeypatch.setattr(retention,'run',lambda *a:pytest.fail('Real execution must refuse before any probe'))
    assert retention.main()==2
    assert json.loads(capsys.readouterr().out)['real_execution_enabled'] is False


def test_coordination_lock_conflict_touches_no_backup(tmp_path,monkeypatch):
    root=tmp_path/'vps';root.mkdir();directory=tmp_path/'state';directory.mkdir()
    lock=root/'deployment.lock';lock.write_text('unchanged')
    def busy(*a):raise BlockingIOError()
    monkeypatch.setitem(sys.modules,'fcntl',SimpleNamespace(flock=busy,LOCK_EX=1,LOCK_SH=2,LOCK_NB=4))
    with pytest.raises(retention.RetentionError,match='busy'):
        with retention.planning_lock(root,directory):pytest.fail('Should not enter')
    assert lock.read_text()=='unchanged'


def test_repository_only_runs_read_commands_with_hidden_secrets(monkeypatch):
    calls=[]
    def command(argv,env,timeout):
        calls.append(argv)
        assert 'private-key' not in argv and env['B2_ACCOUNT_KEY']=='private-key'
        return json.dumps({'id':'a'*64}) if 'config' in argv else '[]'
    monkeypatch.setattr(retention.backup,'command',command)
    repo=retention.Repository({'B2_ACCOUNT_KEY':'private-key'})
    rows,fingerprint=repo.inventory()
    assert rows==[] and len(fingerprint)==64
    assert calls==[['restic','--no-lock','cat','config'],['restic','--no-lock','snapshots','--json']]


@pytest.mark.parametrize('failure',[False,True])
def test_remote_dumps_are_streamed_and_nonzero_is_not_verified(monkeypatch,failure):
    calls=[]
    class Process:
        stdout=io.BytesIO(b'contents')
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def wait(self):return 1 if failure else 0
        def kill(self):pass
    def popen(argv,**kwargs):
        calls.append(argv);assert kwargs['stderr']==retention.subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(retention.subprocess,'Popen',popen)
    repo=retention.Repository({})
    if failure:
        with pytest.raises(retention.RetentionError):repo.file_hash('a'*64,'/known/daily/database.dump')
    else:assert repo.file_hash('a'*64,'/known/daily/database.dump')==(retention.digest(b'contents'),8)
    assert calls[0][:3]==['restic','--no-lock','dump']


def test_simulation_runner_persists_report_and_sends_only_changes(inventory,tmp_path,monkeypatch):
    root,repo,rows,days=inventory;directory=tmp_path/'state';directory.mkdir(mode=0o700);sent=[]
    monkeypatch.setattr(retention.monitor,'monitor_lock',lambda *a:nullcontext())
    monkeypatch.setattr(retention,'planning_lock',lambda *a:nullcontext())
    monkeypatch.setattr(retention.backup,'restic_environment',lambda:{})
    monkeypatch.setattr(retention,'Repository',lambda *a:repo)
    monkeypatch.setattr(retention,'expected_schema',lambda *a:'0006')
    monkeypatch.setattr(retention.monitor,'disks',lambda:(None,1))
    monkeypatch.setattr(retention.monitor.gmail,'send',sent.append)
    report,name,code=retention.run(root,directory,NOW)
    assert code==0 and sent==[] and (directory/name).is_file()
    (root/'var/backups'/rows[12]['tags'][1]/'database.dump').write_bytes(b'corrupt')
    for offset in (1,2):
        report,name,code=retention.run(root,directory,NOW+offset)
        assert code==1 and report['local']['would_remove']==[]
    assert len(sent)==1 and sent[0]['event']=='retention-failed'


def test_systemd_simulates_only_and_contains_no_destructive_tools():
    unit=Path('ops/systemd/documind-retention.service').read_text()
    timer=Path('ops/systemd/documind-retention.timer').read_text()
    assert ' --simulate' in unit and '--execute' not in unit
    assert 'User=debian' in unit and 'ReadWritePaths=/var/lib/documind-retention' in unit
    assert '09:00:00 Europe/Paris' in timer
    assert 'ExecStart=/usr/bin/python3 /srv/documind-ai/current/retention_production.py --simulate' in unit
    code=Path('tools/retention_production.py').read_text()
    assert "'forget'" not in code and "'prune'" not in code and "'restore'" not in code
    assert 'rmtree' not in code and '.unlink(' not in code and "['docker'" not in code


@pytest.mark.parametrize('count', [0, 1, 7, 8, 30])
def test_local_archive_counts(inventory, count):
    root, repo, rows, days = inventory
    parent = root / 'var/backups'
    # Only generated pytest fixtures are removed here, never operational archives.
    for path in parent.iterdir():
        shutil.rmtree(path)
    for row, files in days[:count]:
        directory = parent / row['tags'][1]; directory.mkdir()
        for name, data in files.items(): (directory / name).write_bytes(data)
    plan = retention.build_plan(root, repo, '0006', NOW)
    assert plan['status'] == 'simulated'
    assert plan['local']['examined'] == plan['local']['eligible'] == count
    assert len(plan['local']['keep']) >= min(count, 7)
    assert len(plan['local']['keep']) + len(plan['local']['would_remove']) == count
    assert plan['restored_copy_guard'].startswith('51ac3259-present')


def test_zero_daily_snapshots_refuses_plan(inventory):
    root, repo, rows, days = inventory
    rows[:] = [row for row in rows if not any(retention.DAILY.fullmatch(tag) for tag in row['tags'])]
    with pytest.raises(retention.RetentionError, match='no_current_daily_snapshot'):
        retention.build_plan(root, repo, '0006', NOW)


def test_local_archive_without_snapshot_blocks_proposals(inventory):
    root, repo, rows, days = inventory
    rows.remove(rows[12])
    plan = retention.build_plan(root, repo, '0006', NOW)
    assert plan['status'] == 'attention-required'
    assert any(item['reason'] == 'daily_snapshot_not_confirmed' for item in plan['local']['excluded'])
    assert not plan['local']['would_remove'] and not plan['remote']['would_remove']


def test_remote_snapshot_without_local_is_verified_before_proposal(inventory):
    root, repo, rows, days = inventory
    plan = retention.build_plan(root, repo, '0006', NOW)
    local_names = {path.name for path in (root / 'var/backups').iterdir()}
    remote_only = [item for item in plan['remote']['would_remove'] if item['name'] not in local_names]
    assert remote_only
    assert all(item['snapshot'] in plan['verified_files'] for item in remote_only)


@pytest.mark.parametrize('change', ['add', 'metadata', 'repository'])
def test_inventory_change_during_analysis_refuses_plan(inventory, monkeypatch, change):
    root, repo, rows, days = inventory
    original = repo.inventory; calls = []
    def changing_inventory():
        values, repository = original(); calls.append(True)
        if len(calls) == 2:
            if change == 'add': values.append({'id': 'b'*64, 'tags': [], 'paths': [], 'time': '2026-10-01T00:00:00Z'})
            elif change == 'metadata': values[-1]['hostname'] = 'changed-host'
            else: repository = 'different-repository'
        return values, repository
    monkeypatch.setattr(repo, 'inventory', changing_inventory)
    with pytest.raises(retention.RetentionError, match='repository_changed_during_analysis'):
        retention.build_plan(root, repo, '0006', NOW)
    assert len(calls) == 2


def test_inventory_order_and_untagged_other_usage_do_not_authorize_deletion(inventory, monkeypatch):
    root, repo, rows, days = inventory
    rows[-1].pop('tags'); rows[-1].pop('paths')
    original = repo.inventory; calls = []
    def reordered():
        values, repository = original(); calls.append(True)
        return (values if len(calls) == 1 else list(reversed(values))), repository
    monkeypatch.setattr(repo, 'inventory', reordered)
    plan = retention.build_plan(root, repo, '0006', NOW)
    assert plan['status'] == 'simulated'
    assert rows[-1]['id'] not in {item['snapshot'] for item in plan['remote']['would_remove']}


def test_file_symlink_is_refused(inventory, monkeypatch):
    root, repo, rows, days = inventory
    target = root / 'var/backups' / rows[12]['tags'][1] / 'database.dump'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == target or original(path))
    plan = retention.build_plan(root, repo, '0006', NOW)
    assert any(item['reason'] == 'unexpected_local_file' for item in plan['local']['excluded'])
    assert not plan['local']['would_remove']


@pytest.mark.parametrize('path', ['/srv/documind-ai/var/backups/../private', '/other-project/backup'])
def test_suspicious_snapshot_path_refused(inventory, path):
    root, repo, rows, days = inventory; rows[12]['paths'] = [path]
    with pytest.raises(retention.RetentionError, match='ambiguous_daily_snapshot'):
        retention.build_plan(root, repo, '0006', NOW)


def test_invalid_repository_response_is_sanitized(monkeypatch):
    monkeypatch.setattr(retention.backup, 'command', lambda *a: 'invalid-secret-output')
    with pytest.raises(retention.RetentionError, match='^repository_unavailable_or_invalid$'):
        retention.Repository({'B2_ACCOUNT_KEY': 'private-key'}).inventory()


@pytest.mark.parametrize('cause', ['busy', 'maintenance', 'invalid-secret-output'])
def test_runner_failure_has_no_sensitive_output_or_production_change(inventory, tmp_path, monkeypatch, cause):
    root, repo, rows, days = inventory
    directory = tmp_path / 'state'; directory.mkdir(mode=0o700)
    before = {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    monkeypatch.setattr(retention.monitor, 'monitor_lock', lambda *a: nullcontext())
    def locked(*args):
        if cause == 'busy': raise retention.RetentionError('backup_deployment_or_retention_busy')
        if cause == 'maintenance': raise retention.RetentionError('backup_maintenance_pending')
        raise RuntimeError('invalid-secret-output')
    monkeypatch.setattr(retention, 'planning_lock', locked)
    monkeypatch.setattr(retention.monitor, 'disks', lambda: (None, 1))
    sent = []; monkeypatch.setattr(retention.monitor.gmail, 'send', sent.append)
    report, name, code = retention.run(root, directory, NOW)
    assert code == 1 and report['status'] == 'simulation-impossible'
    assert report['local']['would_remove'] == report['remote']['would_remove'] == []
    assert 'invalid-secret-output' not in (directory / name).read_text()
    assert 'invalid-secret-output' not in json.dumps(sent)
    assert before == {str(path): path.read_bytes() for path in root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('current', ['missing', 'directory'])
def test_invalid_current_refused(tmp_path, current):
    if current == 'directory': (tmp_path / 'current').mkdir()
    with pytest.raises(retention.RetentionError, match='active_release_unavailable'):
        retention.expected_schema(tmp_path)


def test_default_cli_selects_simulation_only(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['retention_production.py'])
    monkeypatch.setattr(retention.os, 'name', 'posix')
    monkeypatch.setattr(retention.os, 'umask', lambda *a: 0o077)
    calls = []
    def run(*args):
        calls.append(args)
        return {'status':'simulated','alerts':[],'plan_sha256':'a'*64}, 'safe-report.json', 0
    monkeypatch.setattr(retention, 'run', run)
    assert retention.main() == 0 and len(calls) == 1
    assert calls[0][2:] == (None, 7, 4, 3)
    assert json.loads(capsys.readouterr().out)['mode'] == 'simulation'


def test_cli_passes_retention_policy_to_simulation(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['retention_production.py', '--daily-retention', '5',
                                      '--weekly-retention', '2', '--monthly-retention', '1'])
    monkeypatch.setattr(retention.os, 'name', 'posix')
    monkeypatch.setattr(retention.os, 'umask', lambda *a: 0o077)
    calls = []

    def run(*args):
        calls.append(args)
        return {'status':'simulated','alerts':[],'plan_sha256':'a'*64}, 'safe-report.json', 0

    monkeypatch.setattr(retention, 'run', run)
    assert retention.main() == 0
    assert calls[0][2:] == (None, 5, 2, 1)


def test_empty_archive_even_with_matching_hash_is_refused(inventory):
    root, repo, rows, days = inventory
    row, files = days[12]; directory = root / 'var/backups' / row['tags'][1]
    files['database.dump'] = b''
    manifest = json.loads(files['manifest.json'])
    manifest['sha256']['database.dump'] = retention.digest(b'')
    files['manifest.json'] = json.dumps(manifest).encode()
    for name, data in files.items(): (directory / name).write_bytes(data)
    plan = retention.build_plan(root, repo, '0006', NOW)
    assert plan['status'] == 'attention-required' and not plan['local']['would_remove']
    assert any(item['reason'] == 'empty_local_archive' for item in plan['local']['excluded'])


@pytest.mark.parametrize('blocked', [1, 2])
def test_both_retention_and_deployment_locks_exclude_concurrent_work(tmp_path, monkeypatch, blocked):
    root = tmp_path / 'vps'; root.mkdir(); (root / 'deployment.lock').write_text('original')
    directory = tmp_path / 'state'; directory.mkdir(); calls = []
    def flock(file, flags):
        calls.append(flags)
        if len(calls) == blocked: raise BlockingIOError()
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(flock=flock, LOCK_EX=1, LOCK_SH=2, LOCK_NB=4))
    with pytest.raises(retention.RetentionError, match='busy'):
        with retention.planning_lock(root, directory): pytest.fail('Busy lock entered')
    assert calls[0] == 1 | 4
    if blocked == 2: assert calls[1] == 2 | 4
    assert (root / 'deployment.lock').read_text() == 'original'


@pytest.mark.parametrize('issue', ['disk', 'smtp'])
def test_disk_risk_and_smtp_failure_are_reported_without_secrets(inventory, tmp_path, monkeypatch, issue):
    root, repo, rows, days = inventory; directory = tmp_path / 'state'; directory.mkdir(mode=0o700)
    monkeypatch.setattr(retention.monitor, 'monitor_lock', lambda *a: nullcontext())
    monkeypatch.setattr(retention, 'planning_lock', lambda *a: nullcontext())
    monkeypatch.setattr(retention.backup, 'restic_environment', lambda: {})
    monkeypatch.setattr(retention, 'Repository', lambda *a: repo)
    monkeypatch.setattr(retention, 'expected_schema', lambda *a: '0006')
    monkeypatch.setattr(retention.monitor, 'disks', lambda: (retention.monitor.event('disk-critical', 'stockage'), 1))
    sent = []
    def send(event):
        sent.append(event)
        if issue == 'smtp': raise RuntimeError('smtp-private-password')
    monkeypatch.setattr(retention.monitor.gmail, 'send', send)
    for offset in (0, 1):
        report, name, code = retention.run(root, directory, NOW + offset)
        assert code == 1 and report['status'] == 'attention-required'
        assert report['notification_failed'] == (issue == 'smtp')
        assert 'high_disk_risk' in report['alerts']
        assert 'smtp-private-password' not in (directory / name).read_text()
    assert len(sent) == (2 if issue == 'smtp' else 1)
