"""Read-only DocuMind monitoring. No Docker commands and no repository maintenance."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

try:
    from . import backup_production as backup
    from . import gmail_monitor_alert as gmail
except ImportError:
    import backup_production as backup
    import gmail_monitor_alert as gmail

UTC = timezone.utc
GIB = 1024**3
ROOT = Path('/srv/documind-ai')
STATE = Path('/var/lib/documind-monitor')
TIMER_BUS = '/org/freedesktop/systemd1/unit/documind_2dbackup_2etimer'


class MonitorError(Exception):
    pass


def epoch(value):
    if not isinstance(value, str):
        raise MonitorError('invalid_timestamp')
    # Restic Go timestamps can carry nanoseconds. Python accepts/truncates excess precision.
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, OverflowError):
        raise MonitorError('invalid_timestamp') from None


def event(name, resource, severity='critical', reason='normal'):
    return {'event': name, 'resource': resource, 'severity': severity, 'reason': reason}


def disk_level(free):
    if free < 8 * GIB: return 'emergency'
    if free < 10 * GIB: return 'critical'
    if free < 20 * GIB: return 'warning'
    return 'normal'


def disks(paths=(ROOT, Path('/var/lib/docker'))):
    filesystems = {}
    for path in paths:
        device = path.stat().st_dev
        if device in filesystems: continue
        stats = os.statvfs(path)
        # f_bavail: blocks really available to the unprivileged monitoring account.
        available = stats.f_bavail * stats.f_frsize
        filesystems[device] = min(available, filesystems.get(device, available))
    # Aggregate the worst filesystem. Mount paths/device IDs never enter notifications/state.
    free = min(filesystems.values())
    level = disk_level(free)
    return (None if level == 'normal' else event('disk-' + level, 'stockage', level)), len(filesystems)


def read_command(argv, env=None, allow_missing=False):
    try:
        result = subprocess.run(argv, env=env or {**backup.base_environment(), 'LC_ALL': 'C', 'TZ': 'UTC'},
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        raise MonitorError('read_command_failed') from None
    if result.returncode and not (allow_missing and 'LoadState=not-found' in result.stdout.splitlines()):
        raise MonitorError('read_command_failed')
    return result.stdout


def backup_status(output, now):
    try:
        rows = backup.restic_json(output)
        if not isinstance(rows, list): raise ValueError()
        if not rows: return event('backup-missing', 'sauvegardes')
        valid = []; invalid_times = []; seen = set()
        for row in rows:
            snapshot_time = None
            try:
                snapshot_time = epoch(row['time'])
                if snapshot_time > now + 300:
                    return event('backup-timer-failed', 'horloge', reason='clock-inconsistent')
                identifier, tags, paths = row['id'], row['tags'], row['paths']
                if (not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{64}', identifier)
                        or identifier in seen or not isinstance(tags, list) or len(tags) != 2
                        or not all(isinstance(tag, str) for tag in tags) or len(set(tags)) != 2
                        or 'documind-ai' not in tags or not isinstance(paths, list) or len(paths) != 1):
                    raise ValueError()
                seen.add(identifier)
                run = next(tag for tag in tags if tag != 'documind-ai')
                match = re.fullmatch(r'daily-(\d{8}T\d{6}Z)-[a-f0-9]{32}', run)
                if not match or paths != [str(PurePosixPath('/srv/documind-ai/var/backups') / run)]:
                    raise ValueError()
                run_time = datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC).timestamp()
                if snapshot_time > now + 300 or run_time > now + 300:
                    return event('backup-timer-failed', 'horloge', reason='clock-inconsistent')
                # A daily run must refer to its own snapshot, not a newer snapshot with reused old tags.
                if not 0 <= snapshot_time - run_time <= 4 * 3600: raise ValueError()
                valid.append(snapshot_time)
            except (ValueError, TypeError, KeyError, StopIteration, MonitorError, AttributeError):
                invalid_times.append(snapshot_time)
        if not valid:
            return event('restic-unavailable', 'sauvegardes', reason='invalid-response')
        # Never let old valid snapshots hide newer malformed entries or missing current backups.
        if now - max(valid) > 36 * 3600:
            return event('backup-stale', 'sauvegardes')
        if any(value is None or value >= max(valid) for value in invalid_times):
            return event('restic-unavailable', 'sauvegardes', reason='invalid-response')
        return None
    except (ValueError, TypeError, backup.BackupError):
        return event('restic-unavailable', 'sauvegardes', reason='invalid-response')


def restic_status(now):
    try:
        env = backup.restic_environment()
        env['RESTIC_CACHE_DIR'] = str(STATE / 'restic-cache')
        output = read_command(['restic', '--no-lock', 'snapshots', '--json', '--tag', 'documind-ai'], env)
    except Exception:
        return event('restic-unavailable', 'sauvegardes', reason='repository-unavailable')
    return backup_status(output, now)


def properties(unit, names):
    argv = ['systemctl', 'show', unit, '--no-pager'] + ['--property=' + name for name in names]
    return dict(line.split('=', 1) for line in read_command(argv, allow_missing=True).splitlines() if '=' in line)


def systemd_status(now, monotonic):
    try:
        timer = properties('documind-backup.timer', ('LoadState', 'UnitFileState', 'ActiveState'))
        service = properties('documind-backup.service', ('LoadState', 'ActiveState', 'Result', 'ExecMainStatus', 'ExecMainStartTimestampMonotonic'))
        running = service.get('ActiveState') in {'activating', 'active', 'deactivating'}
        if running:
            start = int(service.get('ExecMainStartTimestampMonotonic', '0')) / 1_000_000
            if start <= 0 or monotonic - start < -5:
                return event('backup-timer-failed', 'horloge', reason='clock-inconsistent'), False
            if monotonic - start <= 4 * 3600:
                return None, True
            return event('backup-timer-failed', 'planification', reason='service-running-too-long'), False
        reason = None
        if timer.get('LoadState') != 'loaded': reason = 'timer-missing'
        elif timer.get('UnitFileState') != 'enabled': reason = 'timer-disabled'
        elif timer.get('ActiveState') != 'active': reason = 'timer-inactive'
        if reason: return event('backup-timer-failed', 'planification', reason=reason), False
        raw = read_command(['busctl', 'get-property', 'org.freedesktop.systemd1', TIMER_BUS,
                            'org.freedesktop.systemd1.Timer', 'NextElapseUSecRealtime'])
        value = re.fullmatch(r't\s+(\d+)\s*', raw)
        next_run = int(value[1]) / 1_000_000 if value else 0
        if not 0 < next_run - now <= 26 * 3600:
            return event('backup-timer-failed', 'planification', reason='next-run-invalid'), False
        local = datetime.fromtimestamp(next_run, UTC).astimezone(ZoneInfo('Europe/Paris'))
        if (local.hour, local.minute, local.second) != (3, 0, 0):
            return event('backup-timer-failed', 'planification', reason='next-run-invalid'), False
        if service.get('LoadState') != 'loaded' or service.get('Result') != 'success' or service.get('ExecMainStatus') != '0':
            return event('backup-timer-failed', 'planification', reason='service-failed'), False
        return None, False
    except Exception:
        return event('backup-timer-failed', 'planification', reason='systemd-unavailable'), False


def operation_busy(root):
    import fcntl
    # Probe only: never hold a lock long enough to cause a deployment/backup failure.
    with (root / 'deployment.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False


@contextmanager
def monitor_lock(directory):
    import fcntl
    with (directory / 'monitor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MonitorError('monitor_already_running') from None
        yield


def load_state(path):
    if not path.exists(): return {'version': 1, 'last_check': 0, 'alerts': {}}
    backup.private_file(path)
    state = backup.restic_json(path.read_text())
    if (not isinstance(state, dict) or set(state) - {'version', 'last_check', 'alerts', 'busy_since'}
            or state.get('version') != 1 or not isinstance(state.get('alerts'), dict)
            or type(state.get('last_check')) not in (int, float) or not math.isfinite(state['last_check'])):
        raise MonitorError('invalid_monitor_state')
    for channel, alert in state['alerts'].items():
        if (channel not in {'disk', 'backup', 'systemd', 'clock'} or not isinstance(alert, dict)
                or set(alert) != {'event', 'sent_at'}): raise MonitorError('invalid_monitor_state')
        gmail.message(alert['event'])
        if type(alert.get('sent_at')) not in (int, float) or not math.isfinite(alert['sent_at']): raise MonitorError('invalid_monitor_state')
    if state.get('busy_since') is not None and (type(state['busy_since']) not in (int, float) or not math.isfinite(state['busy_since'])):
        raise MonitorError('invalid_monitor_state')
    return state


def save_state(path, state):
    descriptor, name = tempfile.mkstemp(prefix='.state-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(state, output, sort_keys=True)
            output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)  # Only this invocation's private temporary state file.
    if os.name == 'posix':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)


def planned_maintenance(path, now):
    if not path.exists(): return set()
    backup.private_file(path)
    data = backup.restic_json(path.read_text())
    until = epoch(data['until'])
    scopes = data['scopes']
    if not isinstance(scopes, list) or not set(scopes) <= {'backup', 'systemd'} or until - now > 24 * 3600:
        raise MonitorError('invalid_maintenance_window')
    return set(scopes) if until > now else set()


def notify_changes(outcomes, state, now, reminder, send, persist):
    failed = False
    for channel, current in outcomes.items():
        if current == 'deferred': continue
        previous = state['alerts'].get(channel)
        if current is None:
            if previous is None: continue
            outgoing = event('recovery', previous['event']['resource'], 'normal')
        else:
            unchanged = previous and previous['event'] == current
            critical = current['severity'] in {'critical', 'emergency'}
            elapsed = now - previous['sent_at'] if previous else 0
            if unchanged and not (critical and reminder > 0 and elapsed >= reminder): continue
            outgoing = current
        try:
            send(outgoing)
        except Exception:
            failed = True
            continue  # Keep the previous delivered state so the next run retries.
        if current is None: state['alerts'].pop(channel)
        else: state['alerts'][channel] = {'event': current, 'sent_at': now}
        persist()  # Commit each successful delivery before attempting the next one.
    return failed


def run(root, directory, reminder, now=None, send=gmail.send):
    now = time.time() if now is None else now
    if not math.isfinite(now): raise MonitorError('invalid_system_clock')
    if not directory.is_dir() or directory.is_symlink() or (os.name == 'posix' and directory.stat().st_mode & 0o077):
        raise MonitorError('private_state_directory_required')
    with monitor_lock(directory):
        path = directory / 'state.json'; state = load_state(path)
        clock_invalid = (not math.isfinite(now) or now < 1704067200 or state['last_check'] > now + 300
                         or any(alert['sent_at'] > now + 300 for alert in state['alerts'].values()))
        disk, count = disks()
        outcomes = {'disk': disk, 'clock': None}
        if clock_invalid:
            outcomes.update(clock=event('backup-timer-failed', 'horloge', reason='clock-inconsistent'),
                            backup='deferred', systemd='deferred')
        else:
            maintenance = planned_maintenance(directory / 'maintenance.json', now)
            systemd, running = systemd_status(now, time.monotonic())
            busy = operation_busy(root)
            if running or busy:
                if state.get('busy_since') is None: state['busy_since'] = now
            else: state['busy_since'] = None
            too_long = (state.get('busy_since') is not None and now - state['busy_since'] > 4 * 3600)
            too_long = too_long or bool(systemd and systemd['reason'] == 'service-running-too-long')
            deferred = (running or busy) and not too_long
            outcomes['systemd'] = 'deferred' if deferred or 'systemd' in maintenance else systemd
            outcomes['backup'] = 'deferred' if deferred or 'backup' in maintenance else restic_status(now)
            if busy and too_long:
                outcomes['systemd'] = event('backup-timer-failed', 'planification', reason='service-running-too-long')
            for channel in ('backup', 'systemd'):
                value = outcomes[channel]
                if isinstance(value, dict) and value['reason'] == 'clock-inconsistent':
                    outcomes.update(clock=value, backup='deferred', systemd='deferred')
                    break
        def persist(): save_state(path, state)
        delivery_failed = notify_changes(outcomes, state, now, reminder, send, persist)
        if not clock_invalid: state['last_check'] = max(state['last_check'], now)
        persist()
        abnormal = any(value is not None and value != 'deferred' for value in outcomes.values())
        report = {'status': 'notification-failed' if delivery_failed else 'incident' if abnormal else 'deferred' if 'deferred' in outcomes.values() else 'normal',
                  'filesystems_checked': count, 'channels': {key: 'deferred' if value == 'deferred' else 'incident' if value else 'normal' for key, value in outcomes.items()},
                  'events': {key: value['event'] for key, value in outcomes.items() if isinstance(value, dict)},
                  'reasons': {key: value['reason'] for key, value in outcomes.items() if isinstance(value, dict)}}
        return report, 1 if delivery_failed or abnormal else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reminder-hours', type=int, default=72)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if os.name != 'posix' or not 0 <= args.reminder_hours <= 8760:
            raise MonitorError('invalid_monitor_runtime_or_configuration')
        report, code = run(ROOT, STATE, args.reminder_hours * 3600)
        print(json.dumps(report, sort_keys=True))
        return code
    except Exception:
        print('{"status":"monitor-error"}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
