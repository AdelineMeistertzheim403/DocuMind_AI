from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from tools import monitor_production as monitor
from tools import gmail_monitor_alert as gmail

NOW = datetime(2026, 10, 20, 6, tzinfo=timezone.utc).timestamp()


def snapshot(age=1, suffix='a', **changes):
    timestamp = datetime.fromtimestamp(NOW - age * 3600, timezone.utc)
    run = 'daily-' + timestamp.strftime('%Y%m%dT%H%M%SZ') + '-' + suffix * 32
    row = {'id': suffix * 64, 'time': timestamp.isoformat(), 'tags': ['documind-ai', run],
           'paths': ['/srv/documind-ai/var/backups/' + run]}
    return {**row, **changes}


@pytest.mark.parametrize('gib,level', [(20,'normal'),(39,'normal'),(19.9,'warning'),(10,'warning'),(9.9,'critical'),(8,'critical'),(7.9,'emergency')])
def test_disk_thresholds(gib, level):
    assert monitor.disk_level(gib * monitor.GIB) == level


@pytest.mark.parametrize('same', [True, False])
def test_statvfs_bavail_and_dedup_by_device(monkeypatch, same):
    calls = []; paths = [Path('/documind'), Path('/docker')]
    monkeypatch.setattr(Path, 'stat', lambda path: SimpleNamespace(st_dev=1 if same or path == paths[0] else 2))
    def statvfs(path):
        calls.append(path)
        return SimpleNamespace(f_bavail=9*monitor.GIB, f_bfree=30*monitor.GIB, f_frsize=1)
    monkeypatch.setattr(monitor.os, 'statvfs', statvfs, raising=False)
    event, count = monitor.disks(paths)
    assert event['event'] == 'disk-critical' and count == (1 if same else 2) and len(calls) == count


@pytest.mark.parametrize('rows,expected,reason', [([], 'backup-missing','normal'),
    ([snapshot()], None, None), ([snapshot(36)], None, None), ([snapshot(36.01)], 'backup-stale','normal'),
    ([snapshot(id='not-an-id')], 'restic-unavailable','invalid-response'),
    ([snapshot(paths=['/other-project'])], 'restic-unavailable','invalid-response'),
    ([snapshot(tags=['documind-ai','manual'])], 'restic-unavailable','invalid-response'),
    ([snapshot(), snapshot()], 'restic-unavailable','invalid-response'),
    ([snapshot(-1)], 'backup-timer-failed','clock-inconsistent'),
    ([snapshot(48), snapshot(id='invalid')], 'backup-stale','normal'),
    ([snapshot(1), snapshot(48, suffix='b', tags=['documind-ai'])], None, None),
    ([snapshot(2), snapshot(1,suffix='b',tags=['documind-ai'])], 'restic-unavailable','invalid-response'),
    ({'id':'not-an-array'}, 'restic-unavailable','invalid-response')])
def test_snapshots_need_full_id_run_path_and_freshness(rows, expected, reason):
    result = monitor.backup_status(json.dumps(rows), NOW)
    assert (result['event'] if result else None) == expected
    if result: assert result['reason'] == reason


def test_invalid_json_and_raw_error_never_leak():
    result = monitor.backup_status('secret-response', NOW)
    assert result['reason'] == 'invalid-response' and 'secret' not in json.dumps(result)


def test_restic_only_reads_snapshots_and_inaccessible_repo_is_distinct(monkeypatch):
    monkeypatch.setattr(monitor.backup, 'restic_environment', lambda: {'RESTIC_PASSWORD':'secret'})
    calls=[]
    def read(argv, env):
        calls.append(argv)
        assert env['RESTIC_PASSWORD']=='secret'
        assert argv == ['restic','--no-lock','snapshots','--json','--tag','documind-ai']
        raise RuntimeError('secret repository URL')
    monkeypatch.setattr(monitor, 'read_command', read)
    assert monitor.restic_status(NOW)['reason']=='repository-unavailable' and len(calls)==1


@pytest.fixture
def systemd(monkeypatch):
    timer = {'LoadState':'loaded','UnitFileState':'enabled','ActiveState':'active'}
    service = {'LoadState':'loaded','ActiveState':'inactive','Result':'success','ExecMainStatus':'0', 'ExecMainStartTimestampMonotonic':'1000000000'}
    next_time = datetime(2026,10,21,1,tzinfo=timezone.utc).timestamp()  # 03:00 Paris
    values={'next':int(next_time * 1_000_000)}
    def props(unit,names): return timer if unit.endswith('.timer') else service
    monkeypatch.setattr(monitor,'properties',props)
    monkeypatch.setattr(monitor,'read_command',lambda argv:'t '+str(values['next'])+'\n')
    return timer,service,values


@pytest.mark.parametrize('case,reason', [('normal',None),('missing','timer-missing'),('disabled','timer-disabled'),
    ('inactive','timer-inactive'),('no-next','next-run-invalid'),('far-next','next-run-invalid'),
    ('wrong-hour','next-run-invalid'),('failed-service','service-failed'),('running',None),('long','service-running-too-long')])
def test_systemd_timer_and_last_result(systemd,case,reason):
    timer,service,values=systemd
    if case=='missing': timer['LoadState']='not-found'
    elif case=='disabled': timer['UnitFileState']='disabled'
    elif case=='inactive': timer['ActiveState']='inactive'
    elif case=='no-next': values['next']=0
    elif case=='far-next': values['next']=int((NOW+50*3600)*1_000_000)
    elif case=='wrong-hour': values['next']-=3600*1_000_000
    elif case=='failed-service': service['Result']='exit-code';service['ExecMainStatus']='1'
    elif case in ('running','long'): service['ActiveState']='activating'
    result,running=monitor.systemd_status(NOW, 1001 if case=='running' else 20000 if case=='long' else 10000)
    assert (result['reason'] if result else None)==reason
    assert running == (case=='running')


@pytest.fixture
def runner(tmp_path,monkeypatch):
    directory=tmp_path/'state';directory.mkdir(mode=0o700)
    values={'disk':None,'systemd':None,'running':False,'busy':False,'backup':None}
    sent=[]
    monkeypatch.setattr(monitor,'monitor_lock',lambda directory:nullcontext())
    monkeypatch.setattr(monitor,'disks',lambda:(values['disk'],1))
    monkeypatch.setattr(monitor,'systemd_status',lambda *args:(values['systemd'],values['running']))
    monkeypatch.setattr(monitor,'operation_busy',lambda *args:values['busy'])
    monkeypatch.setattr(monitor,'restic_status',lambda *args:values['backup'])
    def run(now=NOW,send=None,reminder=72*3600):
        return monitor.run(tmp_path,directory,reminder,now,send=send or sent.append)
    return run,values,sent,directory


def test_levels_deduplicate_escalate_and_recover(runner):
    run,values,sent,directory=runner
    assert run()[1]==0 and sent==[]
    for index,level in enumerate(('warning','warning','critical','emergency')):
        values['disk']=monitor.event('disk-'+level,'stockage',level)
        assert run(now=NOW+index*60)[1]==1
    assert [e['event'] for e in sent]==['disk-warning','disk-critical','disk-emergency']
    values['disk']=None
    assert run(now=NOW+300)[1]==0 and sent[-1]['event']=='recovery'
    run(now=NOW+400)
    assert len(sent)==4


def test_failed_smtp_is_not_committed_and_next_pass_retries(runner):
    run,values,sent,directory=runner
    values['backup']=monitor.event('backup-stale','sauvegardes')
    def fail(event): raise RuntimeError('smtp-password secret')
    report,code=run(send=fail)
    assert code==1 and report['status']=='notification-failed'
    assert monitor.load_state(directory/'state.json')['alerts']=={}
    run(now=NOW+60)
    assert len(sent)==1
    assert monitor.load_state(directory/'state.json')['alerts']['backup']['event']==values['backup']


def test_critical_reminder_and_disabled_reminders(runner):
    run,values,sent,directory=runner
    values['disk']=monitor.event('disk-critical','stockage')
    run();run(now=NOW+2*3600,reminder=0);run(now=NOW+72*3600)
    assert len(sent)==2


def test_busy_or_backup_running_defers_without_false_recovery(runner):
    run,values,sent,directory=runner
    values['backup']=monitor.event('backup-stale','sauvegardes');run()
    values['running']=True; values['backup']=None
    report,code=run(now=NOW+60)
    assert report['channels']['backup']=='deferred' and code==0 and len(sent)==1
    values['running']=False;values['busy']=True
    run(now=NOW+120)
    assert len(sent)==1
    values['busy']=False;run(now=NOW+180)
    assert sent[-1]['event']=='recovery'


def test_stuck_operation_cannot_suppress_monitoring_indefinitely(runner):
    run,values,sent,directory=runner;values['busy']=True
    run();report,code=run(now=NOW+5*3600)
    assert code==1 and sent[-1]['reason']=='service-running-too-long'


def test_planned_maintenance_never_hides_disk_problem(runner):
    run,values,sent,directory=runner
    (directory/'maintenance.json').write_text(json.dumps({'until':datetime.fromtimestamp(NOW+3600,timezone.utc).isoformat(), 'scopes':['backup','systemd']}))
    (directory/'maintenance.json').chmod(0o600)
    values['disk']=monitor.event('disk-warning','stockage','warning')
    values['backup']=monitor.event('backup-stale','sauvegardes')
    run()
    assert [e['event'] for e in sent]==['disk-warning']


def test_backwards_clock_has_one_alert_and_no_spurious_recovery(runner):
    run,values,sent,directory=runner
    values['backup']=monitor.event('backup-stale','sauvegardes');run()
    values['backup']=None
    report,code=run(now=NOW-3600)
    assert code==1 and report['channels']['backup']=='deferred'
    assert sent[-1]['reason']=='clock-inconsistent'
    run(now=NOW-3500)
    assert len(sent)==2
    run(now=NOW+60)
    assert [e['event'] for e in sent[-2:]]==['recovery','recovery']


def test_monitor_lock_already_held_does_not_run(tmp_path,monkeypatch):
    def busy(*args): raise BlockingIOError()
    monkeypatch.setitem(sys.modules,'fcntl',SimpleNamespace(flock=busy,LOCK_EX=1,LOCK_NB=2))
    with pytest.raises(monitor.MonitorError,match='already_running'):
        with monitor.monitor_lock(tmp_path): pytest.fail('should not run')


def test_state_is_atomic_private_and_contains_no_source_paths(runner):
    run,values,sent,directory=runner;values['disk']=monitor.event('disk-warning','stockage','warning');run()
    text=(directory/'state.json').read_text()
    assert 'snapshot' not in text and '/srv/' not in text and 'password' not in text
    assert not (directory/'state.next').exists()
    assert monitor.load_state(directory/'state.json')['version']==1


def test_read_command_hides_stderr_and_only_uses_readers(monkeypatch,capsys):
    monkeypatch.setattr(monitor.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='secret',stderr='secret'))
    with pytest.raises(monitor.MonitorError) as error:monitor.read_command(['systemctl','show'])
    assert 'secret' not in str(error.value) and capsys.readouterr().out==''


@pytest.fixture
def smtp(tmp_path,monkeypatch):
    config=tmp_path/'gmail.env'
    config.write_text("export SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USERNAME=sender@example.com\n"
                      "SMTP_PASSWORD='private-app-password'\nALERT_FROM=sender@example.com\nALERT_TO=recipient@example.com\n")
    config.chmod(0o600)
    calls=[];state={'fail':False}
    class SMTP:
        def __init__(self,host,port,timeout):calls.append(('connect',host,port))
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):calls.append(('ehlo',))
        def starttls(self,context):
            assert context.check_hostname and context.verify_mode==2
            calls.append(('tls',))
            if state.get('tls_fail'):raise RuntimeError('private TLS details')
        def login(self,user,password):
            assert password=='private-app-password';calls.append(('login',))
        def send_message(self,message,**kwargs):
            assert 'private-app-password' not in str(message)
            calls.append(('send',message))
            if state['fail']:raise RuntimeError('private-app-password')
            return {}
    monkeypatch.setattr(gmail.smtplib,'SMTP',SMTP)
    return config,calls,state


def test_gmail_reuses_existing_variables_and_requires_starttls(smtp,capsys):
    config,calls,state=smtp
    gmail.send(monitor.event('backup-stale','sauvegardes'),config)
    assert [c[0] for c in calls]==['connect','ehlo','tls','ehlo','login','send']
    assert '36 heures' in calls[-1][1].get_content()
    assert capsys.readouterr().out==''


def test_gmail_failure_is_sanitized(smtp):
    config,calls,state=smtp;state['fail']=True
    with pytest.raises(gmail.NotificationError) as error:gmail.send(monitor.event('backup-stale','sauvegardes'),config)
    assert str(error.value)=='notification_delivery_failed'


def test_gmail_cannot_login_without_successful_starttls(smtp):
    config,calls,state=smtp;state['tls_fail']=True
    with pytest.raises(gmail.NotificationError):gmail.send(monitor.event('backup-stale','sauvegardes'),config)
    assert [call[0] for call in calls]==['connect','ehlo','tls']


def test_messages_only_use_allowlisted_structured_data():
    with pytest.raises(gmail.NotificationError):gmail.message({'event':'disk-warning','resource':'stockage','severity':'warning','body':'secret'})
    subject,body=gmail.message(monitor.event('test-notification','test','normal'))
    assert 'aucune panne' in body and '/srv/' not in body


def test_units_are_independent_and_code_never_runs_mutating_commands():
    service=Path('ops/systemd/documind-monitor.service').read_text()
    timer=Path('ops/systemd/documind-monitor.timer').read_text()
    assert 'OnCalendar=*-*-* 08:00:00 Europe/Paris' in timer and 'Persistent=true' in timer
    assert 'User=debian' in service and 'CapabilityBoundingSet=' in service
    assert 'Requires=documind-backup' not in service and 'ExecStartPre=' not in service
    assert 'ReadWritePaths=/var/lib/documind-monitor' in service and 'docker.sock' in service
    code=Path('tools/monitor_production.py').read_text()
    assert "['docker'" not in code
    assert "'stop'" not in code and "'restart'" not in code
    assert "'prune'" not in code and "'forget'" not in code and "'restore'" not in code


def test_smtp_failure_on_recovery_is_retried(runner):
    run,values,sent,directory=runner
    values['disk']=monitor.event('disk-critical','stockage');run()
    values['disk']=None
    def fail(event): raise RuntimeError('private SMTP failure')
    assert run(now=NOW+60,send=fail)[1]==1
    assert 'disk' in monitor.load_state(directory/'state.json')['alerts']
    run(now=NOW+120)
    assert sent[-1]['event']=='recovery'
    assert 'disk' not in monitor.load_state(directory/'state.json')['alerts']


def test_failed_atomic_write_keeps_previous_state(tmp_path,monkeypatch):
    path=tmp_path/'state.json'
    original={'version':1,'last_check':NOW,'alerts':{}}
    monitor.save_state(path,original)
    def fail(*args): raise OSError('disk full, secret path')
    monkeypatch.setattr(monitor.os,'replace',fail)
    with pytest.raises(OSError):monitor.save_state(path,{**original,'last_check':NOW+60})
    assert json.loads(path.read_text())==original
    assert not list(tmp_path.glob('.state-*.tmp'))


def test_nonfinite_clock_fails_without_delivery(runner):
    run,values,sent,directory=runner
    with pytest.raises(monitor.MonitorError):run(now=float('nan'))
    assert sent==[]


def test_future_snapshot_uses_clock_channel_without_false_recovery(runner):
    run,values,sent,directory=runner
    values['backup']=monitor.event('backup-timer-failed','horloge',reason='clock-inconsistent')
    run();run(now=NOW+60)
    assert len(sent)==1 and 'clock' in monitor.load_state(directory/'state.json')['alerts']
    values['backup']=None;run(now=NOW+120)
    assert sent[-1]['event']=='recovery' and len(sent)==2


def test_systemd_read_failure_is_an_incident(monkeypatch):
    def fail(*a):raise RuntimeError('secret systemd output')
    monkeypatch.setattr(monitor,'properties',fail)
    result,running=monitor.systemd_status(NOW,10000)
    assert result['reason']=='systemd-unavailable' and not running
    assert 'secret' not in json.dumps(result)


def test_read_lock_probe_never_writes_production_lock(tmp_path,monkeypatch):
    lock=tmp_path/'deployment.lock';lock.write_text('unchanged')
    calls=[]
    def flock(file,mode):calls.append(mode)
    monkeypatch.setitem(sys.modules,'fcntl',SimpleNamespace(flock=flock,LOCK_SH=1,LOCK_NB=2,LOCK_UN=4))
    assert not monitor.operation_busy(tmp_path)
    assert calls==[3,4] and lock.read_text()=='unchanged'


def test_main_failures_never_print_private_exception(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['monitor_production.py'])
    monkeypatch.setattr(monitor,'os',SimpleNamespace(name='posix',umask=lambda *a:None))
    def fail(*args):raise RuntimeError('SMTP_PASSWORD=secret /private/archive.pdf')
    monkeypatch.setattr(monitor,'run',fail)
    assert monitor.main()==1
    output=capsys.readouterr()
    assert output.out.strip()=='{"status":"monitor-error"}' and output.err==''


@pytest.mark.parametrize('argument,event', [('--test','test-notification'),('documind-backup-failed','documind-backup-failed')])
def test_dedicated_notifier_accepts_test_and_legacy_arguments(monkeypatch,capsys,argument,event):
    sent=[]
    monkeypatch.setattr(sys,'argv',['gmail_monitor_alert.py',argument])
    monkeypatch.setattr(gmail,'send',sent.append)
    assert gmail.main()==0 and sent[0]['event']==event
    assert capsys.readouterr().out.strip()=='notification_sent'


def test_not_found_unit_metadata_is_preserved_on_nonzero_show(monkeypatch):
    monkeypatch.setattr(monitor.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='LoadState=not-found\n',stderr='private-message'))
    assert monitor.properties('documind-backup.timer',('LoadState',))=={'LoadState':'not-found'}
