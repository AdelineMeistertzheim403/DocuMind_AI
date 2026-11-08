"""Destination-bound laboratory recovery; serving is distinct from admissions."""
from contextlib import contextmanager, closing
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from . import lite_reconciliation as recovery
from . import lite_snapshot as snapshots
from . import lite_deletions as deletions
from .account_models import AccountToken, PublicRegistrationQuota, WorkspaceMembership
from .auth import User
from .config import Settings
from .db import Base
from .lite_authority import (AuthorityError, DELETION_KINDS, RECOVERY_KINDS, DeletionOperation,
    LocalOperations, canonical, digest, hex64, read, secure_path,
    strict, uuid, view, write, file_lock)
from .models import Document
from .recovery_quarantine import read_recovery_state
from .security_audit import emit


def validate_operation(op):
    fields = {'operation_id', 'kind', 'context', 'inventory', 'basis', 'validation'}
    if op['kind'] == 'recovery_resolution':
        fields |= {'obsolete', 'outcome'}
    if set(op) != fields:
        raise AuthorityError('Exact recovery validation fields required')
    uuid(op['inventory']); hex64(op['validation'])
    if (set(op['basis']) != {'sequence', 'head'} or type(op['basis']['sequence']) is not int
            or op['basis']['sequence'] < 1):
        raise AuthorityError('Current independent validation basis required')
    hex64(op['basis']['head'])
    if op['kind'] == 'recovery_resolution':
        uuid(op['obsolete'])
        if op['outcome'] not in ('no_effect', 'effect_verified'):
            raise AuthorityError('Obsolete effect must be demonstrable')


def project_release(operations, op, phase, sequence, head):
    inventory = recovery.latest_inventory(operations, op['context'])
    if (op['operation_id'] in operations or inventory['operation_id'] != op['inventory']
            or op['basis'] != {'sequence': sequence, 'head': head}):
        raise AuthorityError('Validation must extend the exact current independent history')
    if op['kind'] == 'recovery_resolution':
        old = operations.get(op['obsolete'])
        if (phase != 'complete' or not old or old['phase'] != 'authorize' or old.get('resolved_by')
                or old['operation']['kind'] != 'recovery_reapplication'
                or old['operation']['context'] != op['context']
                or old['operation']['inventory'] == op['inventory']):
            raise AuthorityError('Only a matching obsolete uncompleted plan can be resolved')
        old['resolved_by'] = op['operation_id']
    elif phase != 'authorize':
        raise AuthorityError('Recovery release needs explicit operator authorization')
    operations[op['operation_id']] = {'operation': op, 'phase': phase, 'counter': 0}


def config_digest(settings):
    value = settings.model_dump(mode='json')
    value['bff_secret_sha256'] = hashlib.sha256(settings.bff_service_key.get_secret_value().encode()).hexdigest()
    value['smtp_secret_sha256'] = hashlib.sha256(settings.smtp_password.get_secret_value().encode()).hexdigest()
    return digest(value)


def code_digest():
    root = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(root)): snapshots.file_hash(p)
                   for name in ('backend', 'tools', 'documind_extractor')
                   for p in sorted((root/name).rglob('*.py'))})


@contextmanager
def api_identity(uid, gid, lock):
    previous_uid, previous_gid = os.geteuid(), os.getegid()
    previous_lock = os.environ.get('LIFECYCLE_BACKUP_LOCK_PATH')
    try:
        os.environ['LIFECYCLE_BACKUP_LOCK_PATH'] = str(lock)
        if previous_uid == 0:
            os.setegid(gid)
            os.seteuid(uid)
        elif previous_uid != uid or previous_gid != gid:
            raise AuthorityError('Wrong API identity')
        yield
    finally:
        if previous_uid == 0:
            os.seteuid(0)
            os.setegid(previous_gid)
        if previous_lock is None:
            os.environ.pop('LIFECYCLE_BACKUP_LOCK_PATH', None)
        else:
            os.environ['LIFECYCLE_BACKUP_LOCK_PATH'] = previous_lock


def laboratory(target, snapshot, engine):
    from tools.validate_restore import _validate_lab
    target, context, manifest, control = recovery.destination(target, snapshot, engine)
    _validate_lab(Path(snapshot), engine.url.database, target.parent)
    if engine.url.host not in ('127.0.0.1', '::1'):
        raise AuthorityError('Recovery release is isolated loopback laboratory only')
    return target, context, manifest, control


def sql_checks(session, operations, count, cache, settings):
    if settings.application_profile != 'beta_lite' or settings.ai_enabled:
        raise AuthorityError('Recovered SQL requires the strict Lite profile')
    quota = session.get(PublicRegistrationQuota, 'public')
    if not quota or not quota.closed or quota.issued_count != count:
        raise AuthorityError('Serving requires a closed settled cumulative quota')
    if session.scalar(text("SELECT count(*) FROM pg_constraint WHERE NOT convalidated")):
        raise AuthorityError('Unvalidated SQL constraints prevent release')
    inspector = inspect(session.connection())
    for table in Base.metadata.sorted_tables:
        actual = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']))
                  for f in inspector.get_foreign_keys(table.name)}
        expected = {(tuple(e.parent.name for e in f.elements), f.referred_table.name,
                     tuple(e.column.name for e in f.elements)) for f in table.foreign_key_constraints}
        if actual != expected:
            raise AuthorityError('Restored foreign-key structure differs from the application')
    users = list(session.scalars(select(User)))
    for user in users:
        deletions.no_workers(session, user.owner_id)
        deletions.sql_inventory(session, user.id, user.owner_id)
        closed = any(e['operation']['kind'] == 'account_closure_request'
                     and e['operation']['user_id'] == str(user.id) for e in operations.values())
        if closed:
            if user.disabled_at is None or session.scalar(select(AccountToken.id).where(
                    AccountToken.email == user.email).limit(1)):
                raise AuthorityError('Closed account credentials remain usable')
        else:
            op = next((o for o in cache.all() if o.user_id == user.id), None)
            entry = operations.get(str(op.id)) if op else None
            if (not entry or entry['phase'] != 'result' or user.disabled_at is not None
                    or user.password_hash != op.password_hash or user.owner_id != op.owner_id
                    or user.registration_kind != 'invite' or user.terms_version != op.terms_version
                    or op.issued_count != entry['counter'] or op.state == 'uncertain'
                    or not user.terms_accepted_at or not op.terms_accepted or not op.adult_declared
                    or not session.scalar(select(WorkspaceMembership.user_id).where(
                        WorkspaceMembership.user_id == user.id, WorkspaceMembership.owner_id == user.owner_id,
                        WorkspaceMembership.role == 'owner'))):
                raise AuthorityError('Active account/admission/credentials not corroborated')
    for doc in session.scalars(select(Document)):
        if not any(u.owner_id == doc.owner_id for u in users):
            raise AuthorityError('Document without a corroborated owner')
    local = cache.payloads()
    if set(local) != {key for key, entry in operations.items() if entry['operation']['kind'] not in RECOVERY_KINDS}:
        raise AuthorityError('Unsigned or unknown cached operation prevents release')
    for key, entry in operations.items():
        op = entry['operation']
        if op['kind'] not in RECOVERY_KINDS and local.get(key) != op:
            raise AuthorityError('Surviving acceptance/operation proof is missing')
        if op['kind'] in DELETION_KINDS and entry['phase'] != 'complete':
            raise AuthorityError('Unfinished source lifecycle operation blocks release')
        if op['kind'] == 'admission' and entry['phase'] == 'reserve':
            raise AuthorityError('Uncertain admission blocks release')


def cursor_checks(target, operations, context):
    from types import SimpleNamespace
    for path in (target/'control').iterdir():
        if not snapshots.CONTROL_NAME.fullmatch(path.name):
            raise AuthorityError('Unknown restored administrative control')
        secure_path(path, 0)
        if path.name.startswith('effect-'):
            identifier = path.name[7:-5]
            entry = operations.get(identifier)
            if not entry or entry['operation']['kind'] not in DELETION_KINDS:
                raise AuthorityError('Unattributed historical effect cursor')
            value = deletions.cursor(SimpleNamespace(control=path.parent), DeletionOperation(**entry['operation']))
            if entry['phase'] != 'complete' or not value['effect_verified'] or value['failed']:
                raise AuthorityError('Unfinished historical effect cursor')
        elif path.name.startswith('fence-'):
            value = strict(read(path, 0))
            entry = operations.get(path.name[6:-5])
            if not entry or value != {'instance': context['instance'], 'cohort': context['cohort'],
                                      'operation': entry['operation']} or entry['phase'] != 'cancel':
                raise AuthorityError('Unresolved historical admission fence')


def lifecycle_checks(settings, operations, inventory):
    from .lifecycle_durability import configured_coordinator
    from .lifecycle_registry import configured_registry
    from .lifecycle_admissions import configured_admissions
    from .lifecycle_holds import HoldStore
    coordinator = configured_coordinator(settings, configured_registry(settings))
    coordinator.verify_recovery_receipts()
    holds = HoldStore(settings.lifecycle_holds_path, coordinator.authenticated)
    with holds.store.connection() as connection:
        actual = holds._snapshots(connection)
        coordinator.authenticated.verify_holds(actual)
    if actual != inventory['holds']:
        raise AuthorityError('Current authenticated holds do not match signed inventory')
    entries = coordinator.store.admission_entries()
    anchor = configured_admissions(settings, coordinator).anchor
    if anchor.check(entries)['state'] != 'settled':
        raise AuthorityError('Unsettled historical admission anchor')
    admitted = {e['counter']: e['operation']['user_id'] for e in operations.values()
                if e['operation']['kind'] == 'admission' and e['phase'] == 'result'}
    if any(admitted.get(e['sequence']) != e['user_id'] for e in entries):
        raise AuthorityError('Historical witness contradicts Lite admissions')
    # Lite confirmations live in 3A, not fabricated into the older five stores.
    return {'native_witness_entries': len(entries), 'lite_admissions': len(admitted)}


def sqlite_seal(path, *, name=None):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        if name:
            snapshots._schema(db, name)
        else:
            snapshots.validate_local(db)
        tables = sorted(r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        return digest({t: sorted((list(r) for r in db.execute('SELECT * FROM "'+t+'"')), key=canonical)
                       for t in tables})


def seal(settings, root, engine):
    uid = Path(settings.storage_dir).stat().st_uid
    metadata = {}
    for directory in ('documents', 'lite', 'locks', *snapshots.STORE_ATTRIBUTES):
        path = secure_path(root/directory, uid, directory=True)
        metadata[directory] = [path.stat().st_uid, path.stat().st_gid, stat.S_IMODE(path.stat().st_mode)]
    paths = snapshots.store_paths(settings)
    files = {str(p.relative_to(root)): sqlite_seal(p, name=name) for name, p in paths.items()}
    files['lite/operations.sqlite'] = sqlite_seal(secure_path(root/'lite/operations.sqlite', uid))
    for key in snapshots.KEY_ATTRIBUTES:
        path = Path(getattr(settings, key))
        secure_path(path, 0, private=False)
        if path.stat().st_mode & 0o227:
            raise AuthorityError('Lifecycle key must be administrator-owned and read-only')
        files[str(path.relative_to(root))] = snapshots.file_hash(path)
    for path in sorted(Path(settings.storage_dir).iterdir()):
        secure_path(path, uid)
        files[str(path.relative_to(root))] = snapshots.file_hash(path)
    with engine.connect() as connection:
        snapshots.no_clients(connection)
        sql = snapshots.sql_fingerprints(connection)
    return {'sql': digest(sql), 'files': files, 'permissions': metadata,
            'settings': config_digest(settings), 'code': code_digest()}


def state(root, value):
    write(root/'recovery-state.json', canonical({'format': 1, 'state': value}), 0, replace=True, public=True)


def prepare_runtime(target, runtime, template, operations, context, inventory, uid, gid):
    runtime = Path(runtime)
    secure_path(runtime.parent, 0, private=False, directory=True)
    if (runtime == target or target in runtime.parents or os.path.lexists(runtime)
            or type(uid) is not int or uid <= 0 or type(gid) is not int or gid <= 0):
        raise AuthorityError('Fresh separate laboratory runtime and non-root UID/GID required')
    runtime.mkdir(mode=0o755)
    write(runtime/'recovery-state.json', canonical({'format': 1, 'state': 'quarantined'}), 0, public=True)
    for name in ('documents', 'lite', 'locks', 'control'):
        (runtime/name).mkdir(mode=0o755 if name == 'control' else 0o700)
    (runtime/'keys').mkdir(mode=0o750)
    os.chown(runtime/'keys', 0, gid)
    for key in snapshots.KEY_ATTRIBUTES:
        directory = runtime/'keys'/key
        directory.mkdir(mode=0o750); os.chown(directory, 0, gid)
        path = directory/'key'
        path.write_bytes(read(target/'application_keys'/key, 0))
        os.chown(path, 0, gid); path.chmod(0o440)
    for path in (target/'documents').iterdir():
        snapshots.write_blob(runtime/'documents'/path.name, snapshots.read_blob(path))
    settings, _ = recovery.effect_environment(target, operations)
    recovery.synchronize_holds(target, inventory, settings)
    updates = {}
    for name, attribute in snapshots.STORE_ATTRIBUTES.items():
        directory = runtime/name; directory.mkdir(mode=0o700)
        path = directory/(name+'.sqlite')
        with snapshots.sqlite_copy(getattr(settings, attribute), name=name) as copied:
            snapshots.write_blob(path, copied.read_bytes())
        updates[attribute] = path
    with snapshots.sqlite_copy(target/'lite/operations.sqlite', local=True) as copied:
        snapshots.write_blob(runtime/'lite/operations.sqlite', copied.read_bytes())
    cache = LocalOperations(runtime/'lite', 0)
    for entry in operations.values():
        if entry['operation']['kind'] in DELETION_KINDS:
            cache.save_deletion(DeletionOperation(**entry['operation']))
    for name in ('documents', 'lite', 'locks', *snapshots.STORE_ATTRIBUTES):
        directory = runtime/name
        for path in directory.iterdir():
            secure_path(path, 0)
            os.chown(path, uid, gid); path.chmod(0o600)
        os.chown(directory, uid, gid); directory.chmod(0o700)
    for key in snapshots.KEY_ATTRIBUTES:
        updates[key] = runtime/'keys'/key/'key'
    settings = template.model_copy(update={
        **updates, 'storage_dir': runtime/'documents', 'recovery_state_path': runtime/'recovery-state.json',
        'lite_authority_manifest': runtime/'manifest.json'})
    Settings(_env_file=None, **settings.model_dump())
    if (settings.application_profile != 'beta_lite' or settings.ai_enabled
            or settings.lifecycle_synthetic_mutations_enabled or not settings.lifecycle_durable_receipts_required
            or settings.extraction_mode != 'sandbox' or str(settings.lite_instance_id) != context['instance']
            or str(settings.lite_cohort_id) != context['cohort']):
        raise AuthorityError('Strict Lite sandbox profile required for recovered API')
    return settings


def validate(target, snapshot, engine, envelope, template, runtime, *, candidate, api_uid, api_gid,
             confirmation, export_key, offline_confirmed=False):
    target, context, manifest, control = laboratory(target, snapshot, engine)
    if candidate != context['candidate'] or template.database_url != engine.url.render_as_string(hide_password=False):
        raise AuthorityError('Candidate or runtime database does not match destination')
    result = recovery.diagnose(target, snapshot, engine, envelope, confirmation=confirmation,
                               offline_confirmed=offline_confirmed)
    if result['status'] != 'reconciled_quarantined':
        raise AuthorityError('Unresolved reconciliation prevents release validation')
    with file_lock(control, 0):
        current = strict(read(control/'current.json', 0))
        value, operations, count = view(current, manifest['authority_public_key'],
            context['instance'], context['cohort'], current['payload']['challenge'])
        inventory = recovery.latest_inventory(operations, context)
        cursor_checks(target, operations, context)
        settings = prepare_runtime(target, runtime, template, operations, context, inventory, api_uid, api_gid)
        runtime = Path(runtime)
        with api_identity(api_uid, api_gid, runtime/'locks/backup.lock'):
            cache = LocalOperations(runtime/'lite', api_uid)
            with Session(engine) as session:
                sql_checks(session, operations, count, cache, settings)
            lifecycle_checks(settings, operations, inventory)
            measurements = seal(settings, runtime, engine)
        record = {'context': context, 'inventory': inventory['operation_id'], 'runtime': str(runtime),
                  'database': engine.url.database,
                  'uid': api_uid, 'gid': api_gid, 'seal': measurements,
                  'basis': {'sequence': value['sequence'], 'head': value['head']},
                  'nonce': secrets.token_hex(32), 'scope': 'laboratory', 'status': 'recovery_validated'}
        op = {'operation_id': str(uuid4()), 'kind': 'recovery_release', 'context': context,
              'inventory': inventory['operation_id'], 'basis': record['basis'], 'validation': digest(record)}
        write(runtime/'validation.json', canonical({'record': record, 'operation': op}), 0, public=True)
        # Settings remain local, root-owned, and readable only by the API group.
        data = settings.model_dump(mode='json')
        data['bff_service_key'] = settings.bff_service_key.get_secret_value()
        data['smtp_password'] = settings.smtp_password.get_secret_value()
        write(runtime/'settings.json', canonical(data), 0, public=True)
        os.chown(runtime/'settings.json', 0, api_gid); (runtime/'settings.json').chmod(0o640)
        return recovery.request(op, 'authorize', count, value['challenge'], export_key)


def authorize(target, snapshot, engine, envelope, runtime, *, confirmation, offline_confirmed=False):
    target, context, manifest, control = laboratory(target, snapshot, engine)
    if not offline_confirmed or confirmation != context['destination']:
        raise AuthorityError('Explicit frozen destination confirmation required')
    runtime = secure_path(runtime, 0, private=False, directory=True)
    saved = strict(read(runtime/'validation.json', 0, private=False))
    op, record = saved['operation'], saved['record']
    with file_lock(control, 0):
        value, operations, count = recovery.current(envelope, context, manifest, control, consume=True)
        entry = operations.get(op['operation_id'])
        inventory = recovery.latest_inventory(operations, context)
        if (not entry or entry['operation'] != op or entry['phase'] != 'authorize'
                or op['context'] != context or digest(record) != op['validation']
                or record['runtime'] != str(runtime) or op['inventory'] != inventory['operation_id']
                or value['sequence'] != op['basis']['sequence']+1
                or value['events'][-1]['request']['operation'] != op
                or read_recovery_state(runtime/'recovery-state.json') != 'quarantined'):
            raise AuthorityError('Current exact independent release authorization required')
        # Consumed durably before any transition. Failure requires a new validation.
        write(runtime/'consumed.json', canonical({'operation': op['operation_id']}), 0, public=True)
        settings = Settings(_env_file=None, **strict(read(runtime/'settings.json', 0, private=False)))
        try:
            with api_identity(record['uid'], record['gid'], runtime/'locks/backup.lock'):
                if seal(settings, runtime, engine) != record['seal']:
                    raise AuthorityError('Destination changed after final validation')
                lifecycle_checks(settings, operations, inventory)
                cache = LocalOperations(runtime/'lite', record['uid'])
                with Session(engine) as session:
                    sql_checks(session, operations, count, cache, settings)
                nonce = cache.challenge()
            # A startup proof uses the existing cache challenge; it remains a
            # signed CURRENT view, never an old snapshot receipt or app boolean.
            if value['challenge'] == nonce:
                raise AuthorityError('Distinct final administrative consultation required')
            provision = {'purpose': 'laboratory_recovery', 'version': 2, 'instance': context['instance'],
                'cohort': context['cohort'], 'api_uid': record['uid'], 'api_gid': record['gid'],
                'store': str(runtime/'lite'), 'control': str(runtime/'control'),
                'authority_public_key': manifest['authority_public_key'],
                'database_sha256': hashlib.sha256(settings.database_url.encode()).hexdigest(),
                'settings_sha256': config_digest(settings), 'release': saved,
                'current': envelope, 'cache_challenge': nonce}
            write(runtime/'manifest.json', canonical(provision), 0, public=True)
            write(runtime/'control/accepted.json', canonical(envelope), 0, public=True)
            write(runtime/'release-state.json', canonical({'status': 'release_authorized',
                'operation': op['operation_id'], 'opening_authorized': False}), 0, public=True)
            state(runtime, 'serving_closed')
            return {'status': 'release_authorized', 'runtime': str(runtime), 'opening_authorized': False}
        except BaseException:
            state(runtime, 'quarantined')
            raise


def runtime_manifest(settings, manifest, *, administrative=False):
    if administrative or os.name != 'posix' or os.geteuid() != manifest['api_uid'] or os.getegid() != manifest['api_gid']:
        raise AuthorityError('Only the authorized non-root laboratory API may use this manifest')
    root = Path(settings.lite_authority_manifest).parent
    from tools.validate_restore import LAB_MARKER, LAB_MARKER_CONTENT
    record, op = manifest['release']['record'], manifest['release']['operation']
    if (os.environ.get('DOCUMIND_RESTORE_LAB') != 'isolated'
            or read(root.parent/LAB_MARKER, 0, private=False) != LAB_MARKER_CONTENT
            or manifest['version'] != 2 or root != Path(record['runtime'])
            or record['scope'] != 'laboratory' or record['context'] != op['context']
            or settings.storage_dir != root/'documents' or settings.recovery_state_path != root/'recovery-state.json'
            or hashlib.sha256(settings.database_url.encode()).hexdigest() != manifest['database_sha256']
            or config_digest(settings) != manifest['settings_sha256'] or digest(record) != op['validation']
            or str(settings.lite_instance_id) != manifest['instance'] or str(settings.lite_cohort_id) != manifest['cohort']
            or read_recovery_state(settings.recovery_state_path) != 'serving_closed'):
        raise AuthorityError('Invalid laboratory recovery runtime')
    value, operations, _ = view(manifest['current'], manifest['authority_public_key'],
        manifest['instance'], manifest['cohort'], manifest['current']['payload']['challenge'])
    if (value['sequence'] != op['basis']['sequence']+1 or operations[op['operation_id']]['operation'] != op
            or manifest['store'] != str(root/'lite') or manifest['control'] != str(root/'control')
            or strict(read(root/'consumed.json', 0, private=False)) != {'operation': op['operation_id']}):
        raise AuthorityError('Missing destination-specific release decision')
    return manifest


def startup(app):
    settings = app.state.settings
    manifest = runtime_manifest(settings, strict(read(settings.lite_authority_manifest, 0, private=False)))
    root = Path(settings.lite_authority_manifest).parent
    launch = strict(read(root/'launch.json', 0, private=False))
    if launch != {'pid': os.getpid(), 'supervisor': os.getppid(), 'operation': manifest['release']['operation']['operation_id']}:
        raise AuthorityError('Recovery authorization requires its controlled fresh API process')
    if settings.extraction_mode != 'sandbox' or settings.ai_enabled or settings.lifecycle_synthetic_mutations_enabled:
        raise AuthorityError('Unsafe recovered application profile')
    with app.state.engine.connect() as connection:
        if (connection.engine.url.host not in ('127.0.0.1', '::1')
                or connection.engine.url.database != manifest['release']['record']['database']
                or connection.scalar(text("SHOW cluster_name")) != 'documind-restore-lab'):
            raise AuthorityError('Only marked synthetic restored PostgreSQL is allowed')
        snapshots.schema(connection)
    record = manifest['release']['record']
    if seal(settings, root, app.state.engine) != record['seal']:
        raise AuthorityError('Recovered subsystem changed before API startup')
    _, operations, count = view(manifest['current'], manifest['authority_public_key'],
        manifest['instance'], manifest['cohort'], manifest['current']['payload']['challenge'])
    with Session(app.state.engine) as session:
        sql_checks(session, operations, count, app.state.lite_confirmation.store, settings)
    lifecycle_checks(settings, operations, recovery.latest_inventory(operations, record['context']))
    app.state.recovery_release = {'manifest': digest(manifest), 'launch': launch}


def serving_gate(app):
    try:
        released = getattr(app.state, 'recovery_release', None)
        if not released:
            return False
        settings = app.state.settings
        manifest = strict(read(settings.lite_authority_manifest, 0, private=False))
        if (digest(manifest) != released['manifest'] or os.getppid() != released['launch']['supervisor']
                or config_digest(settings) != manifest['settings_sha256']):
            return False
        snapshots.store_paths(settings)
        secure_path(Path(manifest['store'])/'operations.sqlite', manifest['api_uid'])
        for key in snapshots.KEY_ATTRIBUTES:
            secure_path(getattr(settings, key), 0, private=False)
        with app.state.sessions() as session:
            quota = session.get(PublicRegistrationQuota, 'public')
            return bool(quota and quota.closed and not settings.ai_enabled
                        and not settings.lifecycle_synthetic_mutations_enabled)
    except (OSError, ValueError):
        emit('system.recovery.quarantine', reason_code='recovery_quarantined')
        return False


def resolve_obsolete(target, snapshot, engine, envelope, obsolete, *, confirmation, export_key,
                     offline_confirmed=False):
    target, context, manifest, control = laboratory(target, snapshot, engine)
    if not offline_confirmed or confirmation != obsolete:
        raise AuthorityError('Explicit obsolete-plan decision required')
    with file_lock(control, 0):
        value, operations, count = recovery.current(envelope, context, manifest, control, consume=True)
        inventory = recovery.latest_inventory(operations, context)
        entry = operations.get(obsolete)
        if (not entry or entry['operation']['kind'] != 'recovery_reapplication' or entry['phase'] != 'authorize'
                or entry.get('resolved_by') or entry['operation']['context'] != context
                or entry['operation']['inventory'] == inventory['operation_id']):
            raise AuthorityError('Matching obsolete authorized plan required')
        old = entry['operation']
        if strict(read(control/('plan-'+obsolete+'.json'), 0)) != old:
            raise AuthorityError('Obsolete signed plan changed')
        effect = DeletionOperation(**old['effect'])
        recovery.check_hold_history(target, inventory)
        recovery.check_current_holds(inventory, effect)
        settings, adapter = recovery.effect_environment(target, operations)
        cursor = deletions.cursor(adapter, effect)
        with Session(engine) as session:
            if cursor['started']:
                recovery.verify_reapplication(session, settings, adapter, effect)
                outcome = 'effect_verified'
            else:
                if effect.kind not in ('document_deletion_execution', 'account_purge_execution'):
                    raise AuthorityError('Non-destructive intent remains explicitly unresolved')
                if deletions.sql_inventory(session, UUID(effect.user_id), UUID(effect.owner_id),
                        UUID(effect.target_id) if effect.kind.startswith('document_') else None) != effect.plan['sql_sha256']:
                    raise AuthorityError('Absence of SQL effect cannot be proved')
                for doc in effect.plan['documents']:
                    deletions.verify_source(settings, doc)
                outcome = 'no_effect'
        evidence = {'obsolete': old, 'cursor': cursor, 'outcome': outcome, 'inventory': inventory['operation_id']}
        op = {'operation_id': str(uuid4()), 'kind': 'recovery_resolution', 'context': context,
              'inventory': inventory['operation_id'], 'basis': {'sequence': value['sequence'], 'head': value['head']},
              'obsolete': obsolete, 'outcome': outcome, 'validation': digest(evidence)}
        write(control/('resolution-'+op['operation_id']+'.json'), canonical(evidence), 0)
        from .lite_authority import sign
        return sign({'version': 1, 'instance': context['instance'], 'cohort': context['cohort'],
                     'challenge': value['challenge'], 'operation': op, 'phase': 'complete',
                     'counter': count, 'facts': 'recovery_obsolete_plan_verified'}, export_key)


def serve(runtime, *, confirmation, port):
    """Supervise exactly one non-root loopback API; every exit rolls back closed."""
    snapshots.root_required()
    root = secure_path(runtime, 0, private=False, directory=True)
    manifest = strict(read(root/'manifest.json', 0, private=False))
    op = manifest['release']['operation']
    if (confirmation != op['operation_id'] or read_recovery_state(root/'recovery-state.json') != 'serving_closed'
            or os.path.lexists(root/'launch.json') or not 1024 <= port <= 65535):
        raise AuthorityError('Fresh targeted release and unprivileged loopback port required')
    process = None
    try:
        env = {**os.environ, 'LIFECYCLE_BACKUP_LOCK_PATH': str(root/'locks/backup.lock')}
        process = subprocess.Popen([sys.executable, '-m', 'tools.lite_restore', 'serve-api',
            '--runtime', str(root), '--port', str(port)], env=env,
            user=manifest['api_uid'], group=manifest['api_gid'], extra_groups=[])
        write(root/'launch.json', canonical({'pid': process.pid, 'supervisor': os.getpid(),
              'operation': op['operation_id']}), 0, public=True)
        code = process.wait()
        if code:
            raise AuthorityError('Recovered API refused startup or terminated abnormally')
        return {'status': 'quarantined', 'opening_authorized': False}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        state(root, 'quarantined')


def serve_api(runtime, port):
    root = Path(runtime)
    for _ in range(100):
        if (root/'launch.json').exists():
            break
        time.sleep(.05)
    settings = Settings(_env_file=None, **strict(read(root/'settings.json', 0, private=False)))
    from .main import create_app
    import uvicorn
    app = create_app(settings)
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)
