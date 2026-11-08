"""Manual destination-bound reconciliation under the existing Lite authority.

No application writer, readiness latch or invitation is enabled here.
"""
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .account_models import PublicRegistrationQuota
from .auth import User
from .lite_authority import (AuthorityError, DELETION_KINDS, RECOVERY_KINDS, DeletionOperation,
    LocalOperations, canonical, digest, file_lock, hex64, read,
    secure_path, sign, strict, timestamp, uuid, validate_operation, view, write)
from . import lite_deletions as deletions
from . import lite_snapshot as snapshots
from .models import Document
from .recovery_quarantine import read_recovery_state
from .security_audit import emit


CONTEXT_FIELDS = {'destination', 'capture_id', 'manifest_sha256', 'candidate', 'instance', 'cohort'}
DOCUMENT_FIELDS = {'id', 'owner', 'name', 'size', 'sha256', 'state', 'reference'}


def validate_context(context):
    if not isinstance(context, dict) or set(context) != CONTEXT_FIELDS:
        raise AuthorityError('Exact recovery context required')
    for key in ('destination', 'capture_id', 'instance', 'cohort'):
        uuid(context[key])
    for key in ('manifest_sha256', 'candidate'):
        hex64(context[key])


def validate_recovery_operation(op):
    common = {'operation_id', 'kind', 'context'}
    uuid(op['operation_id'])
    validate_context(op['context'])
    if op['kind'] in ('recovery_release', 'recovery_resolution'):
        from .lite_release import validate_operation as validate_release
        validate_release(op)
        return
    if op['kind'] == 'recovery_inventory':
        if set(op) != common | {'basis', 'holds', 'documents', 'accounts'}:
            raise AuthorityError('Incomplete current inventory')
        if (set(op['basis']) != {'sequence', 'head'} or type(op['basis']['sequence']) is not int
                or op['basis']['sequence'] < 0):
            raise AuthorityError('Invalid inventory basis')
        if op['basis']['sequence']:
            hex64(op['basis']['head'])
        elif op['basis']['head'] != '':
            raise AuthorityError('Invalid genesis basis')
        if not isinstance(op['holds'], dict) or not isinstance(op['accounts'], list):
            raise AuthorityError('Complete holds/account inventory required')
        seen = set()
        for doc in op['documents']:
            if not isinstance(doc, dict) or set(doc) != DOCUMENT_FIELDS:
                raise AuthorityError('Invalid current document inventory')
            uuid(doc['id']); uuid(doc['owner']); hex64(doc['sha256'])
            if (doc['id'] in seen or doc['state'] not in ('active', 'restricted', 'deleted')
                    or not deletions.STORAGE_NAME.fullmatch(doc['name'])
                    or type(doc['size']) is not int or doc['size'] < 0):
                raise AuthorityError('Conflicting current document')
            seen.add(doc['id'])
            if doc['reference'] is not None:
                uuid(doc['reference'])
        seen = set()
        for account in op['accounts']:
            if (set(account) != {'user', 'owner', 'state', 'admission'}
                    or account['state'] not in ('active', 'closed', 'purged')
                    or account['user'] in seen):
                raise AuthorityError('Invalid current account inventory')
            seen.add(uuid(account['user'])); uuid(account['owner']); uuid(account['admission'])
    elif op['kind'] == 'recovery_reapplication':
        if set(op) != common | {'inventory', 'origin', 'effect'}:
            raise AuthorityError('Exact destination reapplication required')
        uuid(op['inventory']); uuid(op['origin'])
        if op['effect'].get('kind') not in DELETION_KINDS:
            raise AuthorityError('Unsupported recovery effect')
        validate_operation(op['effect'])
        if op['effect']['operation_id'] != op['operation_id']:
            raise AuthorityError('Recovery cursor identity mismatch')
    else:
        raise AuthorityError('Unsupported recovery operation')


def project_recovery(operations, op, phase, counter, count, sequence, head):
    if counter != count:
        raise AuthorityError('Recovery cannot alter authority admissions')
    if op['kind'] in ('recovery_release', 'recovery_resolution'):
        from .lite_release import project_release
        project_release(operations, op, phase, sequence, head)
        return
    before = operations.get(op['operation_id'])
    if op['kind'] == 'recovery_inventory':
        if before or phase != 'complete' or op['basis'] != {'sequence': sequence, 'head': head}:
            raise AuthorityError('Inventory must attest the current complete authority prefix')
        validate_holds(op['holds'])
        admitted = {key: entry['operation'] for key, entry in operations.items()
                    if entry['operation']['kind'] == 'admission' and entry['phase'] == 'result'}
        if {a['admission'] for a in op['accounts']} != set(admitted):
            raise AuthorityError('Inventory omits a committed admission')
        for account in op['accounts']:
            admission = admitted[account['admission']]
            if account['user'] != admission['user_id'] or account['owner'] != admission['owner_id']:
                raise AuthorityError('Inventory account conflicts with admission')
            purged = any(e['operation']['kind'] == 'account_purge_execution' and e['phase'] == 'complete'
                         and e['operation']['user_id'] == account['user'] for e in operations.values())
            closed = any(e['operation']['kind'] == 'account_closure_request'
                         and e['operation']['user_id'] == account['user'] for e in operations.values())
            if account['state'] != ('purged' if purged else 'closed' if closed else 'active'):
                raise AuthorityError('Inventory account state contradicts signed lifecycle')
        for doc in op['documents']:
            if doc['reference']:
                original = operations.get(doc['reference'])
                closure_scope = (original and original['operation']['kind'] == 'account_closure_request'
                                 and original['operation']['owner_id'] == doc['owner']
                                 and doc['state'] == 'restricted')
                if (not original or original['operation']['kind'] not in DELETION_KINDS
                        or not closure_scope and not any(
                            all(d[k] == doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256'))
                            for d in original['operation']['plan']['documents'])
                        or doc['state'] == 'deleted' and (original['phase'] != 'complete'
                            or not original['operation']['kind'].endswith('_execution'))):
                    raise AuthorityError('Inventory document lacks the signed lifecycle reference')
            elif doc['state'] != 'active':
                raise AuthorityError('Restricted inventory document lacks intent')
        operations[op['operation_id']] = {'operation': op, 'phase': phase, 'counter': count}
        return
    inventory = operations.get(op['inventory'])
    origin = operations.get(op['origin'])
    if (not inventory or inventory['operation']['kind'] != 'recovery_inventory'
            or inventory['operation']['context'] != op['context'] or not origin
            or origin['operation']['kind'] not in DELETION_KINDS):
        raise AuthorityError('Recovery requires confirmed matching inventory and original intent')
    original, effect = origin['operation'], op['effect']
    if any(effect[k] != original[k] for k in ('kind', 'user_id', 'owner_id', 'target_id', 'parent_id')):
        raise AuthorityError('Recovery changes original logical scope')
    if effect['kind'].endswith('_execution') and origin['phase'] != 'complete':
        raise AuthorityError('Only a confirmed historical execution can be reapplied')
    for doc in effect['plan']['documents']:
        if (not any(all(old[k] == doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256'))
                    for old in original['plan']['documents'])
                or not any(all(item[k] == doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256'))
                           and item['state'] != 'active' for item in inventory['operation']['documents'])):
            raise AuthorityError('Reapplication is not covered by original and current logical identities')
    if phase == 'authorize':
        if before or any(e['operation']['kind'] == 'recovery_reapplication'
                and e['operation']['context'] == op['context'] and e['operation']['origin'] == op['origin']
                and e['operation']['inventory'] == op['inventory']
                for e in operations.values()):
            raise AuthorityError('Duplicate or contradictory destination authorization')
        operations[op['operation_id']] = {'operation': op, 'phase': phase, 'counter': count}
    elif phase == 'complete' and before and before['phase'] == 'authorize':
        before['phase'] = 'complete'
    else:
        raise AuthorityError('Invalid destination effect transition')


def destination(target, snapshot, engine):
    snapshots.root_required()
    target = secure_path(target, 0, directory=True)
    identity = strict(read(target/'destination.json', 0))
    if read_recovery_state(target/'recovery-state.json') != 'quarantined':
        raise AuthorityError('Reconciliation requires quarantine')
    if engine.url.database != identity['database'] or engine.dialect.name != 'postgresql':
        raise AuthorityError('Wrong destination SQL identity')
    manifest = snapshots.verify_capture(snapshot, expected_sha256=identity['manifest_sha256'],
        instance=identity['instance'], cohort=identity['cohort'], candidate=identity['candidate'])
    with engine.connect() as connection:
        snapshots.no_clients(connection)
        if snapshots.schema(connection) != manifest['schema']:
            raise AuthorityError('Destination schema changed')
        if connection.scalar(text("SHOW cluster_name")) != 'documind-restore-lab':
            raise AuthorityError('Only the marked laboratory is authorized')
        if connection.scalar(text("SELECT closed FROM public_registration_quota WHERE id='public'")) is not True:
            raise AuthorityError('Destination admissions must remain closed')
    context = {key: identity[key] for key in CONTEXT_FIELDS - {'capture_id'}}
    context['capture_id'] = manifest['capture_id']
    validate_context(context)
    control = target/'reconciliation'
    control.mkdir(mode=0o700, exist_ok=True)
    secure_path(control, 0, directory=True)
    return target, context, manifest, control


def challenge(target, snapshot, engine, *, confirmation):
    target, context, _, control = destination(target, snapshot, engine)
    if confirmation != context['destination']:
        raise AuthorityError('Explicit destination confirmation required')
    with file_lock(control, 0):
        nonce = secrets.token_hex(32)
        write(control/'challenge.json', canonical({'nonce': nonce, 'consumed': False}), 0, replace=True)
    return {'context': context, 'challenge': nonce, 'opening_authorized': False}


def current(envelope, context, manifest, control, *, consume):
    pending = strict(read(control/'challenge.json', 0))
    if pending['consumed']:
        raise AuthorityError('A new independent current-history consultation is required')
    value, operations, count = view(envelope, manifest['authority_public_key'],
        context['instance'], context['cohort'], pending['nonce'])
    sequence = manifest['authority_sequence']
    if (value['sequence'] < sequence
            or (digest(value['events'][sequence-1]) if sequence else '') != manifest['authority_head']):
        raise AuthorityError('Authority does not extend the restored snapshot')
    previous = control/'current.json'
    if previous.exists():
        old = strict(read(previous, 0))['payload']
        if value['events'][:len(old['events'])] != old['events']:
            raise AuthorityError('Current authority regressed or forked')
    if consume:
        write(control/'challenge.json', canonical({'nonce': pending['nonce'], 'consumed': True}), 0, replace=True)
        write(previous, canonical(envelope), 0, replace=True)
    return value, operations, count


def request(op, phase, count, nonce, key):
    facts = ('recovery_inventory_verified' if op['kind'] == 'recovery_inventory' else
             'recovery_validation_verified' if op['kind'] == 'recovery_release' else
             'recovery_plan_verified' if phase == 'authorize' else 'recovery_effect_verified')
    return sign({'version': 1, 'instance': op['context']['instance'], 'cohort': op['context']['cohort'],
                 'challenge': nonce, 'operation': op, 'phase': phase, 'counter': count, 'facts': facts}, key)


def validate_holds(snapshots_value):
    """Validate the full existing hold decision history, not an absence boolean."""
    from .lifecycle_holds import HoldStore
    for identifier, item in snapshots_value.items():
        if set(item) != {'id', 'hold', 'created', 'release'} or item['id'] != identifier:
            raise AuthorityError('Incomplete hold snapshot')
        hold = item['hold'].copy()
        if hold['id'] != identifier:
            raise AuthorityError('Hold identity conflict')
        for field in ('reviewed_at', 'review_at', 'ends_at'):
            if hold[field] is not None:
                hold[field] = datetime.fromisoformat(hold[field])
        HoldStore._validate(hold, datetime.fromisoformat(item['created']['at']))
        if item['release']:
            for key in ('actor', 'decision_id'):
                uuid(item['release'][key])
            hex64(item['release']['evidence_sha256'])


def export_inventory(settings, adapter, session, context, envelope, *, export_key,
                     confirmation, offline_confirmed=False):
    """Source-side complete read after verified offline freeze, signed by the SQL administrator."""
    from .lifecycle_durability import configured_coordinator
    from .lifecycle_registry import configured_registry
    from .lifecycle_holds import HoldStore
    snapshots.root_required()
    validate_context(context)
    if not offline_confirmed or confirmation != context['destination']:
        raise AuthorityError('Explicit source freeze and destination confirmation required')
    deletions.require_profile(settings, adapter)
    if context['instance'] != adapter.instance or context['cohort'] != str(adapter.cohort_id):
        raise AuthorityError('Wrong source identity')
    value, operations, count = view(envelope, adapter.public_key, adapter.instance,
                                   str(adapter.cohort_id), envelope['payload']['challenge'])
    with adapter.exclusive():
        snapshots.no_clients(session.connection())
        quota = session.get(PublicRegistrationQuota, 'public', populate_existing=True)
        if not quota or not quota.closed or not adapter.counter_verified(quota.issued_count):
            raise AuthorityError('Source quota must be closed and corroborated')
        documents, users = snapshots.document_inventory(session, settings)
        for user in session.scalars(select(User)):
            deletions.no_workers(session, user.owner_id)
            closed = any(e['operation']['kind'] == 'account_closure_request'
                         and e['operation']['user_id'] == str(user.id) for e in operations.values())
            if closed != (user.disabled_at is not None):
                raise AuthorityError('Source account state is not explained by signed lifecycle history')
        with deletions.application_identity(adapter):
            coordinator = configured_coordinator(settings, configured_registry(settings))
            holds = HoldStore(settings.lifecycle_holds_path, coordinator.authenticated)
            with holds.store.connection() as connection:
                connection.execute('BEGIN IMMEDIATE')
                held = holds._snapshots(connection)
                holds.authenticated.verify_holds(held)
                validate_holds(held)
                inventory = build_inventory(documents, users, operations)
        # A snapshot of every relevant hold (including releases), not just active ones.
        op = {'operation_id': str(uuid4()), 'kind': 'recovery_inventory', 'context': context,
              'basis': {'sequence': value['sequence'], 'head': value['head']},
              'holds': held, **inventory}
        validate_recovery_operation(op)
        snapshots.no_clients(session.connection())
        session.rollback()
        return request(op, 'complete', count, value['challenge'], export_key)


def build_inventory(documents, users, operations):
    accounts = []
    for key, entry in operations.items():
        op = entry['operation']
        if op['kind'] != 'admission' or entry['phase'] != 'result':
            continue
        related = [e for e in operations.values() if e['operation']['kind'] in DELETION_KINDS
                   and e['operation']['user_id'] == op['user_id']]
        purged = any(e['operation']['kind'] == 'account_purge_execution' and e['phase'] == 'complete' for e in related)
        closed = any(e['operation']['kind'] == 'account_closure_request' for e in related)
        present = users.get(op['user_id']) == op['owner_id']
        if present == purged or (op['user_id'] in users and not present):
            raise AuthorityError('Source account contradicts signed admission/purge')
        accounts.append({'user': op['user_id'], 'owner': op['owner_id'],
                         'admission': key, 'state': 'purged' if purged else 'closed' if closed else 'active'})
    if set(users) - {a['user'] for a in accounts}:
        raise AuthorityError('Source has an account without confirmed admission')
    result = {d['id']: {k: d[k] for k in ('id', 'owner', 'name', 'size', 'sha256')} |
              {'state': 'active', 'reference': None} for d in documents}
    for key, entry in operations.items():
        op = entry['operation']
        if op['kind'] == 'account_closure_request':
            for doc in result.values():
                if doc['owner'] == op['owner_id']:
                    doc.update(state='restricted', reference=key)
    for key, entry in operations.items():
        op = entry['operation']
        if op['kind'] not in DELETION_KINDS:
            continue
        for doc in op['plan']['documents']:
            logical = {k: doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256')}
            existing = result.get(doc['id'])
            if existing and any(existing[k] != v for k, v in logical.items()):
                raise AuthorityError('Source document differs from signed historical identity')
            deleted = op['kind'].endswith('_execution') and entry['phase'] == 'complete'
            if deleted:
                if existing and existing['state'] != 'deleted':
                    raise AuthorityError('Confirmed source erasure still contains data')
                result[doc['id']] = {**logical, 'state': 'deleted', 'reference': key}
            elif existing and existing['state'] != 'deleted':
                existing.update(state='restricted', reference=key)
    # A missing original without a completed execution is not a proven deletion.
    for entry in operations.values():
        op = entry['operation']
        if op['kind'] == 'document_deletion_request' and op['target_id'] not in result:
            raise AuthorityError('Unqualified missing source document')
    return {'documents': sorted(result.values(), key=lambda d: d['id']),
            'accounts': sorted(accounts, key=lambda a: a['user'])}


def latest_inventory(operations, context):
    inventories = [e for e in operations.values()
                   if e['operation']['kind'] == 'recovery_inventory']
    if (not inventories or inventories[-1]['operation']['context'] != context
            or inventories[-1].get('superseded')):
        raise AuthorityError('Current complete inventory for this destination required')
    inventory = inventories[-1]['operation']
    after = False
    for entry in operations.values():
        if entry['operation']['operation_id'] == inventory['operation_id']:
            after = True
        elif after and entry['operation']['kind'] not in RECOVERY_KINDS:
            raise AuthorityError('Source operation after inventory requires a new complete freeze review')
    validate_holds(inventory['holds'])
    return inventory


def check_current_holds(inventory, effect):
    from .lifecycle_holds import ActiveHoldError
    scopes = {('account', effect.user_id), ('owner', effect.owner_id)}
    scopes |= {('document', doc['id']) for doc in effect.plan['documents']}
    for item in inventory['holds'].values():
        hold = item['hold']
        if not item['release'] and (hold['scope_kind'], hold['scope_id']) in scopes:
            raise ActiveHoldError('Current independently confirmed hold blocks reconciliation')


def effect_environment(target, operations):
    settings = SimpleNamespace(storage_dir=target/'documents', lifecycle_durable_receipts_required=True,
        lifecycle_authentication_key_path=target/'application_keys/lifecycle_authentication_key_path')
    for name, attribute in snapshots.STORE_ATTRIBUTES.items():
        setattr(settings, attribute, target/'reconciliation'/'lifecycle-current'/name/(name+'.sqlite'))
    store = LocalOperations(target/'lite', 0)
    adapter = SimpleNamespace(store=store, control=target/'reconciliation',
                              _proof=lambda: (operations, 0))
    return settings, adapter


def synchronize_holds(target, inventory, settings):
    """Mirror an independently signed history into the existing authenticated hold stores."""
    from .lifecycle_durability import configured_coordinator
    from .lifecycle_registry import configured_registry
    from .lifecycle_holds import HoldStore
    for name, attribute in snapshots.STORE_ATTRIBUTES.items():
        path = Path(getattr(settings, attribute))
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not path.exists():
            with snapshots.sqlite_copy(target/f'lifecycle/{name}.sqlite', name=name) as copied:
                snapshots.write_blob(path, copied.read_bytes())
    coordinator = configured_coordinator(settings, configured_registry(settings))
    store = HoldStore(settings.lifecycle_holds_path, coordinator.authenticated)
    desired = inventory['holds']
    with store.store.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        previous = store._snapshots(connection)
        for key, old in previous.items():
            new = desired.get(key)
            if (not new or old['hold'] != new['hold'] or old['created'] != new['created']
                    or old['release'] and old['release'] != new['release']):
                raise AuthorityError('Hold mirror history cannot be removed or rewritten')
        # A previous interrupted import may have committed the HMAC before the
        # hold rows. Only the exact independently signed target can finish it.
        with coordinator.authenticated.store.connection() as authenticated:
            mirrors = coordinator.authenticated._hold_mirrors(authenticated)
        if (not set(previous) <= set(mirrors)
                or any(value not in (previous.get(key), desired.get(key)) for key, value in mirrors.items())):
            raise AuthorityError('Authenticated hold mirror contradicts current signed inventory')
        for key in sorted(desired):
            if mirrors.get(key) != desired[key]:
                coordinator.authenticated.update_hold(mirrors, desired[key])
                mirrors = {**mirrors, key: desired[key]}
        if mirrors != desired:
            raise AuthorityError('Authenticated hold inventory is incomplete')
        connection.execute('DELETE FROM hold_decisions_v2')
        connection.execute('DELETE FROM holds_v2')
        for key, item in sorted(desired.items()):
            hold = item['hold']
            connection.execute('INSERT INTO holds_v2 VALUES(?,?,?,?,?)',
                (key, hold['scope_kind'], hold['scope_id'], canonical(hold).decode(), int(item['release'] is not None)))
            for decision in [item['created']] + ([item['release']] if item['release'] else []):
                connection.execute(
                    'INSERT INTO hold_decisions_v2(hold_id,action,actor,at,decision_id,evidence_sha256) VALUES(?,?,?,?,?,?)',
                    (key, decision['action'], decision['actor'], decision['at'],
                     decision['decision_id'], decision['evidence_sha256']))
    with store.store.connection() as connection:
        coordinator.authenticated.verify_holds(store._snapshots(connection))


def check_restored_holds(target):
    """A hold in the old copy is cleared only by a matching current release history."""
    import sqlite3
    path = secure_path(target/'lifecycle/holds.sqlite', 0)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT id,content,released FROM holds_v2').fetchall()
    return rows


def check_hold_history(target, inventory):
    for identifier, content, released in check_restored_holds(target):
        prior = strict(content)
        current_hold = inventory['holds'].get(identifier)
        if not current_hold or current_hold['hold'] != prior or released and not current_hold['release']:
            raise AuthorityError('Current hold history omits or regresses a restored exception')


def restrictions(session, operations):
    """Quarantine already denies every session; also persist account closure before planning."""
    for entry in operations.values():
        op = entry['operation']
        if op['kind'] != 'account_closure_request':
            continue
        user = session.get(User, UUID(op['user_id']))
        if user is not None:
            if str(user.owner_id) != op['owner_id']:
                raise AuthorityError('Restored closure owner conflict')
            deletions.close_account(session, DeletionOperation(**op))


def reconcile_counter(session, operations, count):
    quota = session.get(PublicRegistrationQuota, 'public', with_for_update=True, populate_existing=True)
    if quota is None or not quota.closed or not 0 <= quota.issued_count <= 5:
        raise AuthorityError('Invalid restored quota')
    if quota.issued_count > count and not any(e['operation']['kind'] == 'admission'
            and e['phase'] == 'reserve' and e['counter'] == quota.issued_count for e in operations.values()):
        raise AuthorityError('Restored counter exceeds corroborated history')
    quota.issued_count = max(quota.issued_count, count)
    issued = quota.issued_count
    session.commit()
    return issued


def plan(target, snapshot, engine, envelope, origin_id, *, confirmation, export_key, offline_confirmed=False):
    target, context, manifest, control = destination(target, snapshot, engine)
    if not offline_confirmed or confirmation != origin_id:
        raise AuthorityError('Explicit offline original-operation confirmation required')
    with file_lock(control, 0):
        current_value, operations, count = current(envelope, context, manifest, control, consume=True)
        inventory = latest_inventory(operations, context)
        origin = operations.get(origin_id)
        if not origin or origin['operation']['kind'] not in DELETION_KINDS:
            raise AuthorityError('Signed original operation required')
        original = origin['operation']
        if original['kind'].endswith('_execution') and origin['phase'] != 'complete':
            raise AuthorityError('Historical execution is not confirmed complete')
        existing = [e['operation'] for e in operations.values()
                    if e['operation']['kind'] == 'recovery_reapplication'
                    and e['operation']['context'] == context and e['operation']['origin'] == origin_id
                    and e['operation']['inventory'] == inventory['operation_id']]
        if existing:
            return request(existing[-1], 'authorize', count, current_value['challenge'], export_key)
        with Session(engine) as session:
            reconcile_counter(session, operations, count)
            restrictions(session, operations)
            settings, adapter = effect_environment(target, operations)
            user = session.get(User, UUID(original['user_id']))
            if user is None or str(user.owner_id) != original['owner_id']:
                raise AuthorityError('Restored account absent or contradictory')
            docs = list(session.scalars(select(Document).where(Document.owner_id == user.owner_id)))
            if original['kind'].startswith('document_'):
                docs = [d for d in docs if str(d.id) == original['target_id']]
                if len(docs) != 1:
                    raise AuthorityError('Restored document absent or contradictory')
            closure = original['kind'] == 'account_closure_request'
            current_plan = deletions.plan_for(session, settings, user, [] if closure else docs,
                UUID(original['target_id']) if original['kind'].startswith('document_') else None, closure=closure)
            for doc in current_plan['documents']:
                logical = next((d for d in inventory['documents'] if d['id'] == doc['id']), None)
                if (logical is None or logical['state'] == 'active'
                        or any(logical[k] != doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256'))):
                    raise AuthorityError('Destination content not bound to current restricted/deleted identity')
                source_doc = next((d for d in original['plan']['documents'] if d['id'] == doc['id']), None)
                if source_doc is None or any(source_doc[k] != doc[k] for k in ('id', 'owner', 'name', 'size', 'sha256')):
                    raise AuthorityError('Original signed plan does not cover destination document')
            op_id = str(uuid4())
            effect = {**original, 'operation_id': op_id, 'plan': current_plan, 'requested_at': timestamp()}
            check_hold_history(target, inventory)
            check_current_holds(inventory, DeletionOperation(**effect))
            op = {'operation_id': op_id, 'kind': 'recovery_reapplication', 'context': context,
                  'inventory': inventory['operation_id'], 'origin': origin_id, 'effect': effect}
            validate_recovery_operation(op)
            write(control/('plan-'+op_id+'.json'), canonical(op), 0)
            return request(op, 'authorize', count, current_value['challenge'], export_key)


def execute(target, snapshot, engine, envelope, operation_id, *, confirmation, export_key,
            offline_confirmed=False):
    target, context, manifest, control = destination(target, snapshot, engine)
    if not offline_confirmed or confirmation != operation_id:
        raise AuthorityError('Explicit offline destination-operation confirmation required')
    with file_lock(control, 0):
        value, operations, count = current(envelope, context, manifest, control, consume=True)
        inventory = latest_inventory(operations, context)
        entry = operations.get(operation_id)
        if (not entry or entry['operation']['kind'] != 'recovery_reapplication'
                or entry['operation']['context'] != context
                or entry['operation']['inventory'] != inventory['operation_id']):
            raise AuthorityError('New independent destination authorization required')
        op = strict(read(control/('plan-'+operation_id+'.json'), 0))
        if op != entry['operation']:
            raise AuthorityError('Destination plan differs from signed authorization')
        effect = DeletionOperation(**op['effect'])
        check_hold_history(target, inventory)
        check_current_holds(inventory, effect)
        settings, adapter = effect_environment(target, operations)
        state = deletions.cursor(adapter, effect)
        try:
            synchronize_holds(target, inventory, settings)
            with Session(engine) as session:
                reconcile_counter(session, operations, count)
                restrictions(session, operations)
                with deletions.holds(settings, effect, adapter):
                    if entry['phase'] == 'complete':
                        verify_reapplication(session, settings, adapter, effect)
                    elif effect.kind == 'account_closure_request':
                        deletions.close_account(session, effect)
                    elif effect.kind != 'document_deletion_request':
                        deletions.erase(session, settings, adapter, effect, state)
                    verify_reapplication(session, settings, adapter, effect)
                    if effect.kind == 'account_purge_execution':
                        adapter.store.retire_user(effect.user_id)
                    state.update(effect_verified=True, failed=False)
                    deletions.save_cursor(adapter, effect, state)
            return request(op, 'complete', count, value['challenge'], export_key)
        except BaseException:
            state.update(effect_verified=False, failed=True)
            deletions.save_cursor(adapter, effect, state)
            emit('system.file_cleanup.failed', reason_code='cleanup_failed')
            raise


def verify_reapplication(session, settings, adapter, effect):
    if effect.kind == 'document_deletion_request':
        doc = session.get(Document, UUID(effect.target_id))
        if doc is None or str(doc.owner_id) != effect.owner_id:
            raise AuthorityError('Pending request identity changed')
        for item in effect.plan['documents']:
            deletions.verify_source(settings, item)
        return  # All documents remain inaccessible behind quarantine.
    deletions.verify_effect(session, settings, adapter, effect)


def diagnose(target, snapshot, engine, envelope, *, confirmation, offline_confirmed=False):
    target, context, manifest, control = destination(target, snapshot, engine)
    if not offline_confirmed or confirmation != context['destination']:
        raise AuthorityError('Explicit offline destination confirmation required')
    with file_lock(control, 0):
        value, operations, count = current(envelope, context, manifest, control, consume=True)
        inventory = latest_inventory(operations, context)
        check_hold_history(target, inventory)
        reasons = []
        with Session(engine) as session:
            issued = reconcile_counter(session, operations, count)
            restrictions(session, operations)
            users = {str(u.id): u for u in session.scalars(select(User))}
            for account in inventory['accounts']:
                user = users.get(account['user'])
                if account['state'] == 'active' and user is None:
                    reasons.append('active_account_not_reconstructible')
                if account['state'] == 'closed' and user is None:
                    reasons.append('closed_account_not_reconstructible')
                if account['state'] == 'active' and user and user.disabled_at is not None:
                    reasons.append('active_account_disabled')
                if user and str(user.owner_id) != account['owner']:
                    reasons.append('account_owner_conflict')
                if account['state'] == 'purged' and user:
                    reasons.append('purged_account_residue')
                if account['state'] == 'closed' and user and user.disabled_at is None:
                    reasons.append('closed_account_access_conflict')
            expected_users = {a['user'] for a in inventory['accounts']}
            if set(users) - expected_users:
                reasons.append('unknown_account')
            documents = {str(d.id): d for d in session.scalars(select(Document))}
            expected = {d['id']: d for d in inventory['documents']}
            for key, doc in documents.items():
                item = expected.get(key)
                if item is None:
                    reasons.append('unknown_document')
                    continue
                actual = deletions.source(SimpleNamespace(storage_dir=target/'documents'), doc)
                if any(actual[k] != item[k] for k in ('id', 'owner', 'name', 'size', 'sha256')):
                    reasons.append('document_identity_conflict')
                if item['state'] == 'deleted':
                    reasons.append('deleted_document_residue')
            for key, item in expected.items():
                if item['state'] in ('active', 'restricted') and key not in documents:
                    reasons.append('active_document_missing')
                if item['state'] == 'deleted' and os.path.lexists(target/'documents'/item['name']):
                    reasons.append('deleted_file_residue')
            actual_files = {p.name for p in (target/'documents').iterdir()}
            referenced = {d.storage_name for d in documents.values()}
            if actual_files - referenced:
                reasons.append('unattributed_file_residue')
            for entry in operations.values():
                op = entry['operation']
                if op['kind'] == 'admission' and entry['phase'] == 'reserve':
                    reasons.append('uncertain_reservation')
                if (op['kind'] == 'recovery_reapplication' and op['context'] == context
                        and entry['phase'] != 'complete' and not entry.get('resolved_by')):
                    reasons.append('reapplication_result_unconfirmed')
                if op['kind'] == 'recovery_reapplication' and op['context'] == context and entry['phase'] == 'complete':
                    saved = strict(read(control/('plan-'+op['operation_id']+'.json'), 0))
                    if saved != op:
                        raise AuthorityError('Completed plan changed')
                    effect = DeletionOperation(**op['effect'])
                    if (effect.kind == 'account_closure_request' and effect.user_id not in users
                            or effect.kind == 'document_deletion_request' and effect.target_id not in documents):
                        continue
                    settings, adapter = effect_environment(target, operations)
                    verify_reapplication(session, settings, adapter, effect)
        report = {'format': 1, 'context': context, 'inventory': inventory['operation_id'],
                  'authority_sequence': value['sequence'], 'authority_head': value['head'],
                  'issued_count': issued, 'independent_committed_count': count,
                  'status': 'blocked' if reasons else 'reconciled_quarantined',
                  'reasons': sorted(set(reasons)), 'opening_authorized': False,
                  'quarantine_release_authorized': False}
        write(control/'diagnostic.json', canonical(report), 0, replace=True)
        return report
