"""Offline age-based backup retention planning for synthetic inventories only."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4


class SimulationError(ValueError):
    pass


def fail(code):
    raise SimulationError(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError):
        fail('invalid_json_value')


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        fail('invalid_full_identifier')
    return value


def timestamp(value):
    if not isinstance(value, str):
        fail('invalid_timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        fail('invalid_timestamp')
    if result.tzinfo is None or result.utcoffset() is None:
        fail('timezone_required')
    return result.astimezone(timezone.utc)


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        fail('invalid_fields')


def boolean(value):
    if type(value) is not bool:
        fail('invalid_boolean')
    return value


def choices(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        fail('invalid_classification')
    return value


def unique_ids(values):
    if not isinstance(values, list):
        fail('invalid_identifier_list')
    ids = [identifier(item) for item in values]
    if len(set(ids)) != len(ids):
        fail('ambiguous_identifier')
    return ids


def validate_inventory(inventory, now):
    fields(inventory, ('format', 'synthetic_only', 'scope_id', 'inventory_complete',
                       'exceptions_complete', 'dependencies_complete', 'backups', 'objects', 'exceptions'))
    if inventory['format'] != 1 or type(inventory['format']) is not int or inventory['synthetic_only'] is not True:
        fail('synthetic_inventory_required')
    identifier(inventory['scope_id'])
    if not all(boolean(inventory[key]) for key in ('inventory_complete', 'exceptions_complete', 'dependencies_complete')):
        fail('incomplete_inventory')
    if not all(isinstance(inventory[key], list) for key in ('backups', 'objects', 'exceptions')):
        fail('invalid_inventory')
    if not inventory['backups']:
        fail('missing_backups')

    backups = {}
    for item in inventory['backups']:
        fields(item, ('id', 'kind', 'created_at', 'classification', 'metadata',
                      'restore_evidence', 'dependencies'))
        key = identifier(item['id'])
        if key in backups:
            fail('ambiguous_identifier')
        choices(item['kind'], {'local', 'remote'})
        created = timestamp(item['created_at'])
        if created > now:
            fail('future_backup')
        choices(item['classification'], {'ordinary', 'historical', 'protected', 'inconsistent'})
        choices(item['metadata'], {'verified', 'historical_schema', 'invalid', 'checksum_mismatch', 'unknown'})
        boolean(item['restore_evidence'])
        unique_ids(item['dependencies'])
        if item['kind'] == 'local' and item['dependencies']:
            fail('invalid_local_dependencies')
        backups[key] = item

    objects = {}
    version_ids = set()
    for item in inventory['objects']:
        fields(item, ('id', 'snapshot_ids', 'versions', 'replicated', 'locked'))
        key = identifier(item['id'])
        if key in objects or key in backups:
            fail('ambiguous_identifier')
        refs = unique_ids(item['snapshot_ids'])
        boolean(item['replicated'])
        boolean(item['locked'])
        if not isinstance(item['versions'], list) or not item['versions']:
            fail('missing_object_versions')
        for version in item['versions']:
            fields(version, ('id', 'logical_deleted', 'physical_present'))
            version_id = identifier(version['id'])
            if version_id in version_ids or version_id in backups:
                fail('ambiguous_identifier')
            version_ids.add(version_id)
            boolean(version['logical_deleted'])
            boolean(version['physical_present'])
        if any(ref not in backups or backups[ref]['kind'] != 'remote' for ref in refs):
            fail('unknown_snapshot_dependency')
        if refs and not any(version['physical_present'] for version in item['versions']):
            fail('referenced_object_missing')
        objects[key] = item

    if set(objects) & version_ids:
        fail('ambiguous_identifier')
    for key, item in backups.items():
        if item['kind'] == 'remote':
            if not item['dependencies']:
                fail('missing_snapshot_dependencies')
            for dep in item['dependencies']:
                if dep not in objects or key not in objects[dep]['snapshot_ids']:
                    fail('inconsistent_dependency_graph')
    for key, item in objects.items():
        for ref in item['snapshot_ids']:
            if key not in backups[ref]['dependencies']:
                fail('inconsistent_dependency_graph')

    exceptions = {}
    for item in inventory['exceptions']:
        fields(item, ('id', 'reason', 'responsible_id', 'backup_ids', 'ends_at', 'end_event',
                      'reviewed_at', 'review_at'))
        key = identifier(item['id'])
        identifier(item['responsible_id'])
        if key in exceptions or key in backups or key in objects or key in version_ids:
            fail('ambiguous_identifier')
        choices(item['reason'], {'legal_hold', 'security', 'historical_review', 'recovery'})
        refs = unique_ids(item['backup_ids'])
        if not refs or any(ref not in backups for ref in refs):
            fail('invalid_exception_scope')
        if (item['ends_at'] is None) == (item['end_event'] is None):
            fail('invalid_exception_end')
        if item['ends_at'] is not None and timestamp(item['ends_at']) <= now:
            fail('exception_expired_without_decision')
        if item['end_event'] is not None:
            choices(item['end_event'], {'legal_hold_lifted', 'incident_closed', 'review_decision'})
        reviewed = timestamp(item['reviewed_at'])
        review = timestamp(item['review_at'])
        if reviewed > now or review <= reviewed or review > reviewed + timedelta(days=30):
            fail('invalid_exception_review')
        if review <= now:
            fail('exception_review_overdue')
        exceptions[key] = item
    return backups, objects, exceptions


def build_plan(inventory, reference_time, observed_inventory):
    now = timestamp(reference_time)
    inventory = json.loads(canonical(inventory))
    observed_inventory = json.loads(canonical(observed_inventory))
    backups, objects, exceptions = validate_inventory(inventory, now)
    validate_inventory(observed_inventory, now)
    inventory_hash = sha256(inventory)
    if sha256(observed_inventory) != inventory_hash:
        fail('inventory_changed')

    blocks = []
    latest_verified = {}
    for kind in ('local', 'remote'):
        selected = [item for item in backups.values() if item['kind'] == kind]
        verified = [item for item in selected if item['classification'] == 'ordinary'
                    and item['metadata'] == 'verified' and item['restore_evidence']]
        if not selected or not verified:
            blocks.append('missing_verified_recovery_' + kind)
        else:
            latest = max(verified, key=lambda item: (timestamp(item['created_at']), item['id']))
            latest_verified[kind] = latest['id']
        ordered = sorted(timestamp(item['created_at']) for item in selected if item['classification'] == 'ordinary')
        if not ordered or now - ordered[-1] > timedelta(hours=36) or any(
                later - earlier > timedelta(hours=36) for earlier, later in zip(ordered, ordered[1:])):
            blocks.append('irregular_backups_' + kind)
    if any(item['classification'] == 'inconsistent' or item['metadata'] in
           {'invalid', 'checksum_mismatch', 'unknown'} for item in backups.values()):
        blocks.append('unverified_metadata')

    rows = []
    for key, item in sorted(backups.items()):
        created = timestamp(item['created_at'])
        nominal = timedelta(days=7 if item['kind'] == 'local' else 30)
        margin = timedelta(hours=24 if item['kind'] == 'local' else 48)
        age_seconds = (now - created).total_seconds()
        reasons = []
        if item['classification'] != 'ordinary':
            reasons.append(item['classification'])
        if key.startswith(('51ac3259', '3e6df673')):
            reasons.append('protected_historical_prefix')
        if item['metadata'] != 'verified':
            reasons.append('metadata_' + item['metadata'])
        if latest_verified.get(item['kind']) == key:
            reasons.append('latest_verified_recovery')
        applicable = sorted(exc_id for exc_id, exc in exceptions.items() if key in exc['backup_ids'])
        if applicable:
            reasons.append('active_exception')
        dependencies = []
        for dep in sorted(item['dependencies']):
            obj = objects[dep]
            dependency = {'id': dep, 'shared': len(obj['snapshot_ids']) > 1,
                          'locked': obj['locked'], 'replicated': obj['replicated'],
                          'versions': obj['versions']}
            dependencies.append(dependency)
            if (dependency['shared'] or dependency['locked'] or dependency['replicated'] or
                    any(version['logical_deleted'] or not version['physical_present']
                        for version in dependency['versions'])):
                reasons.append('restic_dependency_requires_review')
        due = now >= created + nominal
        if not due:
            reasons.append('within_nominal_period')
        if blocks:
            reasons.append('global_evidence_block')
        rows.append({
            'id': key, 'kind': item['kind'], 'created_at': utc(created), 'age_seconds': age_seconds,
            'classification': item['classification'], 'metadata': item['metadata'],
            'nominal_due_at': utc(created + nominal), 'target_deadline_at': utc(created + nominal + margin),
            'age_due': due, 'target_deadline_reached': now >= created + nominal + margin,
            'decision': 'preserve' if reasons else 'theoretical_candidate',
            'reasons': sorted(set(reasons)), 'dependencies': dependencies,
            'exceptions': applicable,
            'evidence_level': 'synthetic_restore_declared' if item['restore_evidence'] else 'synthetic_only',
        })
    plan = {
        'format': 1, 'mode': 'synthetic_simulation', 'real_execution_enabled': False,
        'human_approval': False, 'created_at': utc(now), 'expires_at': utc(now + timedelta(minutes=15)),
        'scope_id': inventory['scope_id'], 'inventory_sha256': inventory_hash,
        'status': 'blocked' if blocks else 'simulated', 'blocks': sorted(set(blocks)),
        'policy': {'local_days': 7, 'local_margin_hours': 24, 'remote_days': 30, 'remote_margin_hours': 48},
        'exceptions': [exceptions[key] for key in sorted(exceptions)], 'items': rows,
        'physical_disappearance_proven': False,
    }
    plan['plan_sha256'] = sha256(plan)
    return plan


def verify_plan(plan, inventory, reference_time):
    now = timestamp(reference_time)
    if not isinstance(plan, dict) or 'plan_sha256' not in plan:
        fail('invalid_plan')
    checksum = plan['plan_sha256']
    identifier(checksum)
    content = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if sha256(content) != checksum:
        fail('plan_hash_mismatch')
    created = timestamp(plan.get('created_at'))
    if now < created or now >= timestamp(plan.get('expires_at')) or timestamp(plan['expires_at']) != created + timedelta(minutes=15):
        fail('plan_expired_or_clock_invalid')
    validate_inventory(inventory, now)
    if sha256(inventory) != plan.get('inventory_sha256'):
        fail('inventory_changed')
    if build_plan(inventory, plan['created_at'], inventory) != plan:
        fail('plan_not_reproducible')
    return True


def write_private_plan(directory, plan):
    if os.name != 'posix':
        fail('posix_private_directory_required')
    if not hasattr(os, 'O_NOFOLLOW'):
        fail('secure_open_unavailable')
    path = Path(directory)
    if not path.is_absolute() or path.resolve() != path:
        fail('private_directory_required')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        attrs = os.fstat(fd)
        if not stat.S_ISDIR(attrs.st_mode) or attrs.st_uid != os.geteuid() or attrs.st_mode & 0o077:
            fail('private_directory_required')
        name = 'synthetic-plan-' + uuid4().hex + '.json'
        output_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(output_fd, 'wb') as output:
            output.write(canonical(plan) + b'\n')
            output.flush()
            os.fsync(output.fileno())
        return name
    finally:
        os.close(fd)


def load_inventory(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail('duplicate_json_key')
            result[key] = value
        return result

    def invalid_constant(_):
        fail('invalid_json_value')

    with path.open('r', encoding='utf-8') as source:
        return json.load(source, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline synthetic retention simulation; never executes deletion.')
    parser.add_argument('--synthetic-inventory', type=Path, required=True)
    parser.add_argument('--reference-time', required=True)
    parser.add_argument('--private-directory', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inventory = load_inventory(args.synthetic_inventory)
        plan = build_plan(inventory, args.reference_time, inventory)
        observed = load_inventory(args.synthetic_inventory)
        verify_plan(plan, observed, args.reference_time)
        write_private_plan(args.private_directory, plan)
        print(json.dumps({'status': plan['status'], 'mode': plan['mode'],
                          'real_execution_enabled': False, 'item_count': len(plan['items'])}))
        return 1 if plan['status'] == 'blocked' else 0
    except SimulationError as error:
        print(json.dumps({'status': 'simulation_refused', 'reason': str(error),
                          'real_execution_enabled': False}), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError):
        print(json.dumps({'status': 'simulation_refused', 'reason': 'input_or_output_failure',
                          'real_execution_enabled': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
