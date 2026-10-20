"""Read-only retention planning. Real execution is deliberately unavailable in this release."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

try:
    from . import backup_production as backup
    from . import monitor_production as monitor
except ImportError:
    import backup_production as backup
    import monitor_production as monitor

ROOT = Path('/srv/documind-ai')
STATE = Path('/var/lib/documind-retention')
FILES = {'manifest.json', 'integrity.json', 'database.dump', 'documents.tar.gz'}
ARCHIVES = {'database.dump', 'documents.tar.gz'}
PROTECTED = ('51ac3259', '3e6df673')
DAILY = re.compile(r'daily-(\d{8}T\d{6}Z)-[a-f0-9]{32}')
PARIS = ZoneInfo('Europe/Paris')


class RetentionError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def inventory_digest(rows):
    return digest(canonical(sorted(rows, key=lambda row: row['id'])))


def full_id(value):
    return isinstance(value, str) and bool(re.fullmatch('[a-f0-9]{64}', value))


def run_time(name):
    match = DAILY.fullmatch(name)
    if not match: raise RetentionError('unexpected_daily_name')
    try: return datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
    except ValueError: raise RetentionError('unexpected_daily_name') from None


class Repository:
    """Only read commands. Dump data is hashed in memory in bounded chunks, never restored."""
    def __init__(self, env):
        self.env = {**env, 'RESTIC_CACHE_DIR': str(STATE / 'restic-cache')}

    def json(self, *args):
        try:
            output = backup.command(['restic', '--no-lock', *args], self.env, 300)
            return backup.restic_json(output)
        except Exception: raise RetentionError('repository_unavailable_or_invalid') from None

    def inventory(self):
        config = self.json('cat', 'config')
        rows = self.json('snapshots', '--json')
        if not isinstance(config, dict) or not full_id(config.get('id')):
            raise RetentionError('repository_identity_invalid')
        return rows, digest(config['id'].encode())

    def _read(self, identifier, path, metadata=False):
        if not full_id(identifier): raise RetentionError('invalid_snapshot_id')
        argv = ['restic', '--no-lock', 'dump', identifier, path]
        try:
            with subprocess.Popen(argv, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
                expired = threading.Event()
                def timeout():
                    expired.set()
                    try: process.kill()
                    except OSError: pass
                timer = threading.Timer(300, timeout)
                timer.daemon = True
                timer.start()
                hasher = hashlib.sha256(); size = 0; captured = bytearray()
                try:
                    while chunk := process.stdout.read(1024 * 1024):
                        hasher.update(chunk); size += len(chunk)
                        if metadata:
                            if size > 1024 * 1024:
                                process.kill()
                                raise RetentionError('remote_metadata_too_large')
                            captured.extend(chunk)
                    code = process.wait()
                finally: timer.cancel()
                if code or expired.is_set(): raise RetentionError('remote_file_not_verified')
                return hasher.hexdigest(), size, bytes(captured)
        except (OSError, subprocess.SubprocessError):
            raise RetentionError('remote_file_not_verified') from None

    def file_hash(self, identifier, path):
        checksum, size, _ = self._read(identifier, path)
        return checksum, size

    def metadata(self, identifier, path):
        try:
            _, _, raw = self._read(identifier, path, metadata=True)
            return raw, backup.restic_json(raw)
        except Exception: raise RetentionError('remote_metadata_not_verified') from None


def validate_metadata(manifest, integrity, revision, timestamp, now):
    try:
        if (not isinstance(manifest, dict) or type(manifest['database_major']) is not int
                or manifest['database_major'] != 17 or manifest['migration'] != revision
                or set(manifest['files']) != ARCHIVES or len(manifest['files']) != 2
                or set(manifest['sha256']) != ARCHIVES
                or not all(full_id(value) for value in manifest['sha256'].values())): raise ValueError()
        created = monitor.epoch(manifest['created_at'])
        if not timestamp <= created <= min(timestamp + 4 * 3600, now + 300): raise ValueError()
        if not isinstance(integrity, dict) or not {'documents', 'users'} <= integrity.keys(): raise ValueError()
        for name, data in integrity.items():
            if (not re.fullmatch('[a-z_][a-z0-9_]*', name) or not isinstance(data, dict) or type(data['count']) is not int
                    or data['count'] < 0 or not re.fullmatch('[a-f0-9]{32}', data['digest'])
                    or not isinstance(data['columns'], list) or not data['columns']
                    or not all(isinstance(column, str) and re.fullmatch('[a-z_][a-z0-9_]*', column) for column in data['columns'])):
                raise ValueError()
    except Exception: raise RetentionError('archive_metadata_inconsistent') from None


def local_archive(path, parent, revision, now):
    if path.parent != parent or path.is_symlink() or not path.is_dir() or path.resolve() != path:
        raise RetentionError('unexpected_local_path')
    timestamp = run_time(path.name)
    if timestamp > now + 300: raise RetentionError('archive_time_inconsistent')
    if {item.name for item in path.iterdir()} != FILES:
        raise RetentionError('incomplete_or_unknown_local_files')
    hashes = {}; sizes = {}; data = {}
    for name in sorted(FILES):
        file = path / name
        attributes = file.lstat()
        if not stat.S_ISREG(attributes.st_mode) or file.is_symlink() or attributes.st_nlink != 1:
            raise RetentionError('unexpected_local_file')
        with file.open('rb') as source: hashes[name] = hashlib.file_digest(source, 'sha256').hexdigest()
        sizes[name] = attributes.st_size
        if name in ARCHIVES and not sizes[name]: raise RetentionError('empty_local_archive')
        if name.endswith('.json'):
            if attributes.st_size > 1024 * 1024: raise RetentionError('local_metadata_too_large')
            data[name] = backup.restic_json(file.read_bytes())
    validate_metadata(data['manifest.json'], data['integrity.json'], revision, timestamp, now)
    if any(hashes[name] != data['manifest.json']['sha256'][name] for name in ARCHIVES):
        raise RetentionError('local_checksum_mismatch')
    return {'name': path.name, 'time': timestamp, 'hashes': hashes, 'sizes': sizes, 'bytes': sum(sizes.values())}


def snapshot_inventory(rows, now):
    if not isinstance(rows, list): raise RetentionError('ambiguous_repository')
    candidates = []; exclusions = []; ids = set(); runs = set()
    for row in rows:
        try:
            identifier, tags, paths = row['id'], row.get('tags'), row.get('paths')
            if tags is None: tags = []  # Untagged snapshots in a shared repository are legitimate.
            if paths is None: paths = []
            timestamp = monitor.epoch(row['time'])
            if (not full_id(identifier) or identifier in ids or not isinstance(tags, list)
                    or not all(isinstance(tag, str) for tag in tags) or len(set(tags)) != len(tags)
                    or not isinstance(paths, list) or not all(isinstance(path, str) for path in paths)
                    or timestamp > now + 300): raise ValueError()
            ids.add(identifier)
        except Exception: raise RetentionError('ambiguous_repository') from None
        daily = [tag for tag in tags if DAILY.fullmatch(tag)]
        if 'documind-ai' in tags and len(daily) == 1:
            if daily[0] in runs: raise RetentionError('ambiguous_daily_snapshot')
            runs.add(daily[0])
        if identifier.startswith(PROTECTED):
            exclusions.append({'snapshot': identifier, 'reason': 'protected-historical'})
            continue
        if 'documind-ai' not in tags:
            exclusions.append({'ref': digest(identifier.encode())[:16], 'reason': 'other-usage'})
            continue
        if len(daily) != 1:
            exclusions.append({'snapshot': identifier, 'reason': 'historical-or-unknown-tags'})
            continue
        name = daily[0]
        expected = str(PurePosixPath('/srv/documind-ai/var/backups') / name)
        if paths != [expected]: raise RetentionError('ambiguous_daily_snapshot')
        start = run_time(name)
        if not 0 <= timestamp - start <= 4 * 3600: raise RetentionError('inconsistent_snapshot_time')
        if set(tags) != {'documind-ai', name}:
            exclusions.append({'snapshot': identifier, 'reason': 'special-tags'})
            continue
        candidates.append({'id': identifier, 'name': name, 'time': timestamp, 'run_time': start, 'path': expected})
    for prefix in PROTECTED:
        if len([identifier for identifier in ids if identifier.startswith(prefix)]) != 1:
            raise RetentionError('protected_copy_missing_or_ambiguous')
    return candidates, exclusions


def verify_remote(repo, snapshot, revision, now, local=None):
    hashes = {}; sizes = {}; metadata = {}
    for name in ('manifest.json', 'integrity.json'):
        raw, parsed = repo.metadata(snapshot['id'], snapshot['path'] + '/' + name)
        hashes[name], sizes[name], metadata[name] = digest(raw), len(raw), parsed
    validate_metadata(metadata['manifest.json'], metadata['integrity.json'], revision, snapshot['run_time'], now)
    for name in sorted(ARCHIVES):
        hashes[name], sizes[name] = repo.file_hash(snapshot['id'], snapshot['path'] + '/' + name)
        if not sizes[name] or hashes[name] != metadata['manifest.json']['sha256'][name]:
            raise RetentionError('remote_checksum_mismatch')
    if local and (hashes != local['hashes'] or sizes != local['sizes']):
        raise RetentionError('local_remote_mismatch')
    return {'hashes': hashes, 'sizes': sizes}


def remote_policy(snapshots):
    """One global DocuMind group: union of latest occupied Paris days/ISO weeks/months."""
    reasons = {item['id']: [] for item in snapshots}
    ordered = sorted(snapshots, key=lambda item: (item['time'], item['id']), reverse=True)
    for label, limit in (('daily', 7), ('weekly', 4), ('monthly', 6)):
        buckets = set()
        for item in ordered:
            date = datetime.fromtimestamp(item['time'], timezone.utc).astimezone(PARIS)
            key = date.date() if label == 'daily' else tuple(date.isocalendar()[:2]) if label == 'weekly' else (date.year, date.month)
            if key not in buckets and len(buckets) < limit:
                buckets.add(key); reasons[item['id']].append(label)
    if ordered: reasons[ordered[0]['id']].append('latest-valid')
    return reasons


def build_plan(root, repo, revision, now):
    parent = root / 'var/backups'
    if not parent.is_dir() or parent.is_symlink() or parent.resolve() != parent:
        raise RetentionError('unexpected_backup_directory')
    rows, repository = repo.inventory()
    snapshots, remote_exclusions = snapshot_inventory(rows, now)
    initial_inventory = inventory_digest(rows)
    if not snapshots: raise RetentionError('no_current_daily_snapshot')
    newest = max(snapshots, key=lambda item: item['time'])
    if now - newest['time'] > 36 * 3600: raise RetentionError('latest_daily_snapshot_stale')
    # Require a complete current copy, beyond its name/date/tags, before proposing expiry.
    verified = {newest['id']: verify_remote(repo, newest, revision, now)}
    local = []; local_exclusions = []; alerts = []
    entries = sorted(parent.iterdir(), key=lambda path: path.name)
    by_run = {item['name']: item for item in snapshots}
    protected_runs = set()
    for row in rows:
        tags = row.get('tags') or []
        daily = [tag for tag in tags if DAILY.fullmatch(tag)]
        if ('documind-ai' in tags and len(daily) == 1
                and (row['id'].startswith(PROTECTED) or set(tags) != {'documind-ai', daily[0]})):
            protected_runs.add(daily[0])
    for path in entries:
        ref = path.name if DAILY.fullmatch(path.name) else digest(path.name.encode())[:16]
        if not DAILY.fullmatch(path.name):
            local_exclusions.append({'ref': ref, 'reason': 'manual-historical-or-unknown'})
            if path.is_symlink(): alerts.append('unexpected-local-path')
            continue
        if path.name in protected_runs:
            local_exclusions.append({'ref': ref, 'reason': 'paired-protected-snapshot'})
            continue
        try:
            archive = local_archive(path, parent, revision, now)
            snapshot = by_run.get(path.name)
            if snapshot is None: raise RetentionError('daily_snapshot_not_confirmed')
            # Compare all four files, including integrity.json not covered by the old manifest.
            if snapshot['id'] in verified:
                if verified[snapshot['id']] != {'hashes': archive['hashes'], 'sizes': archive['sizes']}:
                    raise RetentionError('local_remote_mismatch')
            else:
                verified[snapshot['id']] = verify_remote(repo, snapshot, revision, now, archive)
            archive['snapshot'] = snapshot['id']; local.append(archive)
        except Exception as error:
            reason = str(error) if isinstance(error, RetentionError) else 'local_archive_unverified'
            local_exclusions.append({'ref': ref, 'reason': reason})
            alerts.append('archive-inconsistency')
    policy = remote_policy(snapshots)
    remote_remove = []; remote_keep = []
    for item in snapshots:
        identifier = item['id']
        if policy[identifier]:
            remote_keep.append({'snapshot': identifier, 'reasons': policy[identifier]})
            continue
        try:
            if identifier not in verified: verified[identifier] = verify_remote(repo, item, revision, now)
            remote_remove.append({'snapshot': identifier, 'name': item['name'], 'reason': 'outside-7d-4w-6m'})
        except Exception:
            remote_keep.append({'snapshot': identifier, 'reasons': ['unverified-remote-preserved']})
            alerts.append('snapshot-inconsistency')
    removed_ids = {item['snapshot'] for item in remote_remove}
    local_keep = []; local_remove = []
    for index, item in enumerate(sorted(local, key=lambda item: (item['time'], item['name']), reverse=True)):
        public = {key: item[key] for key in ('name', 'snapshot', 'bytes')}
        if index < 7:
            public['reason'] = 'latest-local' if index == 0 else 'last-seven-local'; local_keep.append(public)
        elif item['snapshot'] in removed_ids:
            public['reason'] = 'paired-remote-also-selected'; local_keep.append(public)
        else:
            public['reason'] = 'outside-last-seven-with-verified-remote'; local_remove.append(public)
    # Always preserve the newest named daily directory, even if its content/time is inconsistent.
    names = [path.name for path in entries if DAILY.fullmatch(path.name)]
    if names:
        latest = max(names)
        for item in list(local_remove):
            if item['name'] == latest:
                local_remove.remove(item); local_keep.append({**item, 'reason': 'latest-local-name'})
    if alerts:
        # Any inconsistent archive/snapshot blocks all proposals, not just its own deletion.
        local_keep += [{**item, 'reason': 'global-inconsistency-guard'} for item in local_remove]; local_remove = []
        remote_keep += [{'snapshot': item['snapshot'], 'reasons': ['global-inconsistency-guard']} for item in remote_remove]; remote_remove = []
    # A concurrent writer outside our deployment lock must invalidate the entire plan.
    final_rows, final_repository = repo.inventory()
    snapshot_inventory(final_rows, now)
    if final_repository != repository or inventory_digest(final_rows) != initial_inventory:
        raise RetentionError('repository_changed_during_analysis')
    return {'format': 1, 'mode': 'simulation', 'real_execution_enabled': False,
        'created_at': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'expected_schema': revision, 'postgres_major': 17,
        'repository_fingerprint': repository, 'inventory_sha256': initial_inventory,
        'status': 'attention-required' if alerts else 'simulated', 'alerts': sorted(set(alerts)),
        'local': {'examined': len(entries), 'eligible': len(local), 'keep': local_keep, 'would_remove': local_remove,
                  'potential_bytes': sum(item['bytes'] for item in local_remove), 'excluded': local_exclusions},
        'remote': {'examined': len(rows), 'eligible': len(snapshots), 'keep': remote_keep, 'would_remove': remote_remove,
                   'excluded': remote_exclusions},
        'latest_confirmed_snapshot': newest['id'], 'restored_copy_guard': '51ac3259-present-admin-restoration-declared',
        'future_execution_guards': {'administrator_approval_required': True, 'fresh_unchanged_plan_required': True,
            'independent_restore_evidence_required': True, 'exclusive_deployment_lock_required': True,
            'recheck_before_each_deletion_required': True, 'mass_deletion_review_required': True,
            'no_prune_authorized': True},
        'verified_files': verified, 'local_inventory_sha256': digest(canonical(local))}


@contextmanager
def planning_lock(root, directory):
    import fcntl
    # Same coordination file as backup/deploy; no creation or modification under production root.
    with (directory / 'retention.lock').open('a') as own, (root / 'deployment.lock').open('rb') as common:
        try:
            fcntl.flock(own, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(common, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError: raise RetentionError('backup_deployment_or_retention_busy') from None
        yield


def expected_schema(root):
    current = root / 'current'
    if not current.is_symlink() or not current.is_dir() or current.resolve().parent != root / 'releases':
        raise RetentionError('active_release_unavailable')
    bundle = current.resolve()
    release = backup.load_helper(bundle, 'release_manifest').validate_release(backup.restic_json((bundle / 'release.json').read_bytes()))
    return release['schema_revision']


def persist_report(directory, report):
    report['plan_sha256'] = digest(canonical(report))
    name = 'plan-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex + '.json'
    with (directory / name).open('x', encoding='utf-8') as output:
        os.chmod(directory / name, 0o600)
        json.dump(report, output, indent=2, sort_keys=True); output.flush(); os.fsync(output.fileno())
    return name


def run(root, directory, now=None):
    now = time.time() if now is None else now
    report = {'format': 1, 'mode': 'simulation', 'real_execution_enabled': False,
              'status': 'simulation-impossible', 'alerts': [], 'created_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
              'local': {'examined': None, 'eligible': 0, 'keep': [], 'would_remove': [], 'potential_bytes': 0, 'excluded': []},
              'remote': {'examined': None, 'eligible': 0, 'keep': [], 'would_remove': [], 'excluded': []}}
    if not directory.is_dir() or directory.is_symlink() or (os.name == 'posix' and directory.stat().st_mode & 0o077):
        raise RetentionError('private_report_directory_required')
    with monitor.monitor_lock(directory):
        try:
            with planning_lock(root, directory):
                if (root / 'var/backup-maintenance.json').exists(): raise RetentionError('backup_maintenance_pending')
                repo = Repository(backup.restic_environment())
                report = build_plan(root, repo, expected_schema(root), now)
        except Exception as error:
            report['alerts'] = [str(error) if isinstance(error, RetentionError) else 'simulation_failed']
        # Alerts reuse Sprint 8 delivery tracking, in a separate private state directory.
        outcomes = {'backup': None, 'disk': None}
        if report['alerts']:
            reason = 'repository-unavailable' if report['alerts'][0].startswith('repository_') else 'retention-inconsistent'
            outcomes['backup'] = monitor.event('retention-failed', 'conservation', reason=reason)
        try:
            disk, _ = monitor.disks()
            if disk and disk['severity'] in {'critical', 'emergency'}:
                outcomes['disk'] = disk
                report['alerts'].append('high_disk_risk')
        except Exception:
            report['alerts'].append('disk_probe_failed')
            outcomes['backup'] = monitor.event('retention-failed', 'conservation', reason='retention-inconsistent')
        state_path = directory / 'state.json'; state = monitor.load_state(state_path)
        # Sprint 9 emails are for problems only; clear resolved incidents without a normal-day mail.
        for channel, current in outcomes.items():
            if current is None: state['alerts'].pop(channel, None)
        failed = monitor.notify_changes(outcomes, state, now, 0, monitor.gmail.send,
                                        lambda: monitor.save_state(state_path, state))
        monitor.save_state(state_path, state)
        report['notification_failed'] = failed
        if report['status'] == 'simulated' and (report['alerts'] or failed):
            report['status'] = 'attention-required'
        name = persist_report(directory, report)
        return report, name, 1 if failed or report['alerts'] or outcomes['disk'] else 0


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--simulate', action='store_true')
    modes.add_argument('--execute', action='store_true')
    parser.add_argument('--approved-plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.execute:
        print('{"status":"execution-disabled","real_execution_enabled":false}')
        return 2  # No environment variable, report or confirmation can enable deletion in this version.
    os.umask(0o077)
    try:
        if os.name != 'posix' or args.approved_plan or args.plan_sha256: raise RetentionError('invalid_simulation_runtime')
        report, name, code = run(ROOT, STATE)
        print(json.dumps({'status': report['status'], 'mode': 'simulation', 'report': name,
                          'plan_sha256': report['plan_sha256'], 'alerts': report['alerts']}))
        return code
    except Exception:
        print('{"status":"simulation-impossible","mode":"simulation"}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
