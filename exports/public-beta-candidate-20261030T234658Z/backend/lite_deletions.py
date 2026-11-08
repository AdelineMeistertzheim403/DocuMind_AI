"""Targeted Lite requests and administrative effects under the existing authority."""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select

from .account_models import AccountToken, DeletionRequest, PublicRegistrationQuota, Workspace, WorkspaceMembership
from .auth import User
from .db import Base
from .lite_authority import (AuthorityError, DeletionOperation, OperationalConfirmation,
                             canonical, digest, hex64, operation_payload, read, sign,
                             strict, timestamp, uuid, validate_operation, write)
from .models import Document, now
from .security_audit import emit
from .services.document_integrity import STORAGE_NAME, discard_session, durable_document_state


def validate_plan(op):
    plan = op['plan']
    if not isinstance(plan, dict) or set(plan) != {'documents', 'sql_sha256', 'result_ids', 'token_ids'}:
        raise AuthorityError('Invalid deletion plan')
    hex64(plan['sql_sha256'])
    if not isinstance(plan['documents'], list):
        raise AuthorityError('Invalid document inventory')
    for key in ('result_ids', 'token_ids'):
        values = plan[key]
        if (not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                or len(values) != len(set(values))):
            raise AuthorityError('Invalid dependency inventory')
        for value in values:
            uuid(value)
    seen = set()
    for doc in plan['documents']:
        if not isinstance(doc, dict) or set(doc) != {'id','owner','name','size','sha256','device','inode'}:
            raise AuthorityError('Invalid source identity')
        uuid(doc['id']); uuid(doc['owner']); hex64(doc['sha256'])
        if (doc['owner'] != op['owner_id'] or doc['id'] in seen
                or not isinstance(doc['name'], str) or not STORAGE_NAME.fullmatch(doc['name'])
                or any(type(doc[k]) is not int or doc[k] < 0 for k in ('size','device','inode'))):
            raise AuthorityError('Contradictory source scope')
        seen.add(doc['id'])
    if op['kind'].startswith('document_') and seen != {op['target_id']}:
        raise AuthorityError('Document target mismatch')
    if op['kind'] == 'account_closure_request' and seen:
        raise AuthorityError('Closure is not an erasure')


def require_profile(settings, adapter):
    from .recovery_quarantine import read_recovery_state
    state = read_recovery_state(settings.recovery_state_path)
    if state == 'serving_closed':
        from .lite_release import runtime_manifest
        runtime_manifest(settings, strict(read(settings.lite_authority_manifest, 0, private=False)))
    if (settings.application_profile != 'beta_lite'
            or not settings.lifecycle_durable_receipts_required
            or settings.lifecycle_synthetic_mutations_enabled
            or settings.ai_enabled or settings.registration_mode != 'invite'
            or settings.legacy_api_enabled or settings.owner_demo_enabled or settings.api_keys
            or settings.public_registration_limit != 5
            or not isinstance(adapter, OperationalConfirmation)
            or adapter.cohort_id != settings.lite_cohort_id
            or adapter.instance != str(settings.lite_instance_id)
            or state not in ('ready', 'serving_closed')):
        raise AuthorityError('Operational Lite deletion coordinator unavailable')
    adapter._proof()


def entry(adapter, op):
    operations, _ = adapter._proof()
    value = operations.get(op.operation_id)
    if value and value['operation'] != operation_payload(op):
        raise AuthorityError('Deletion confirmation mismatch')
    return value


def restricted_documents(adapter, owner_id):
    operations, _ = adapter._proof()
    return {UUID(e['operation']['target_id']) for e in operations.values()
            if e['operation']['kind'] == 'document_deletion_request'
            and e['operation']['owner_id'] == str(owner_id)}


def account_restricted(adapter, user_id):
    operations, _ = adapter._proof()
    return any(e['operation']['kind'] == 'account_closure_request'
               and e['operation']['user_id'] == str(user_id) for e in operations.values())


def check_document_access(session, document_id, owner_id):
    app = session.info.get('application')
    if app is None or app.state.settings.application_profile != 'beta_lite':
        return
    try:
        adapter = app.state.lite_confirmation
        require_profile(app.state.settings, adapter)
        if document_id in restricted_documents(adapter, owner_id):
            raise HTTPException(410, 'Accès retiré ; suppression administrative en attente.')
    except (ValueError, OSError):
        emit('system.security_config.invalid', reason_code='security_unavailable')
        raise HTTPException(503, 'Vérification administrative indisponible.') from None


@contextmanager
def application_identity(adapter):
    previous = os.geteuid()
    if previous != adapter.store.uid:
        if previous != 0:
            raise AuthorityError('Wrong application identity')
        os.seteuid(adapter.store.uid)
    try:
        yield
    finally:
        if previous != adapter.store.uid:
            os.seteuid(previous)


@contextmanager
def holds(settings, op, adapter):
    from .lifecycle_durability import configured_coordinator
    from .lifecycle_holds import configured_hold_guard
    from .lifecycle_registry import configured_registry
    with ExitStack() as stack:
        with application_identity(adapter):
            coordinator = configured_coordinator(settings, configured_registry(settings))
            scopes = [('owner', op.owner_id), ('account', op.user_id)]
            scopes += [('document', d['id']) for d in op.plan['documents']]
            stack.enter_context(configured_hold_guard(settings, scopes, coordinator))
        yield


def source(settings, document):
    root = Path(settings.storage_dir).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise AuthorityError('Unsafe document root')
    if not STORAGE_NAME.fullmatch(document.storage_name):
        raise AuthorityError('Unsafe storage identity')
    path = root / document.storage_name
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid != os.geteuid() and os.geteuid() != 0
            or before.st_mode & 0o077):
        raise AuthorityError('Unsafe source permissions')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info = os.fstat(stream.fileno())
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if ((before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)
            or info.st_size != document.size_bytes or actual != document.sha256):
        raise AuthorityError('Source identity changed')
    return dict(id=str(document.id), owner=str(document.owner_id), name=document.storage_name,
                size=document.size_bytes, sha256=document.sha256, device=info.st_dev, inode=info.st_ino)


def verify_source(settings, item):
    document = Document(id=UUID(item['id']), owner_id=UUID(item['owner']), storage_name=item['name'],
                        size_bytes=item['size'], sha256=item['sha256'])
    if source(settings, document) != item:
        raise AuthorityError('Source replaced after authorization')


def sql_inventory(session, user_id, owner_id, document_id=None):
    """Hash actual related rows, not their sensitive contents in the authority."""
    from .rag.models import RAGDocument, OperationDocument
    from .ai.models import AIReservation
    from .ai.long_models import LongSummaryJob
    docs = select(Document.id).where(Document.owner_id == owner_id)
    if document_id is not None:
        docs = docs.where(Document.id == document_id)
    linked = select(RAGDocument.result_id).where(RAGDocument.document_id.in_(docs))
    reservations = select(OperationDocument.reservation_id).where(OperationDocument.document_id.in_(docs))
    if session.scalar(select(AIReservation.id).where(AIReservation.id.in_(reservations),
                                                    AIReservation.owner_id != owner_id).limit(1)):
        raise AuthorityError('Cross-owner reservation dependency')
    if session.scalar(select(RAGDocument.id).join(Document, Document.id == RAGDocument.document_id).where(
            RAGDocument.result_id.in_(linked), Document.owner_id != owner_id).limit(1)):
        raise AuthorityError('Cross-owner derived dependency')
    jobs = select(LongSummaryJob.id).where(LongSummaryJob.document_id.in_(docs))
    user = session.get(User, user_id)
    rows = {}
    for table in Base.metadata.sorted_tables:
        columns = table.c
        if table.name == 'documents':
            condition = columns.id.in_(docs)
        elif 'document_id' in columns:
            condition = columns.document_id.in_(docs)
            if document_id is None and 'owner_id' in columns:
                condition = condition | (columns.owner_id == owner_id)
        elif table.name == 'summary_steps':
            condition = columns.job_id.in_(jobs)
        elif table.name == 'rag_results':
            condition = columns.id.in_(linked)
            if document_id is None:
                condition = condition | (columns.owner_id == owner_id)
        elif document_id is None and table.name == 'users':
            condition = columns.id == user_id
        elif document_id is None and table.name in ('workspace_memberships','account_deletion_requests'):
            condition = columns.user_id == user_id
        elif document_id is None and table.name == 'account_tokens':
            if user is None:
                raise AuthorityError('Missing account inventory')
            condition = columns.email == user.email
        else:
            continue
        values = session.execute(select(table).where(condition)).mappings().all()
        if 'owner_id' in columns and any(row['owner_id'] != owner_id for row in values):
            raise AuthorityError('Cross-owner SQL dependency')
        rows[table.name] = sorted(digest({k: str(v) for k, v in row.items()}) for row in values)
    return digest(rows)


def counter(session, adapter):
    quota = session.get(PublicRegistrationQuota, 'public', populate_existing=True)
    if quota is None or not adapter.counter_verified(quota.issued_count):
        raise AuthorityError('Uncorroborated cumulative counter')
    return quota.issued_count


def plan_for(session, settings, user, documents, document_id=None, *, closure=False):
    from .rag.models import RAGDocument, RAGResult
    results = select(RAGResult.id)
    if document_id is not None:
        results = results.where(RAGResult.id.in_(select(RAGDocument.result_id).where(
            RAGDocument.document_id == document_id)))
    else:
        results = results.where(RAGResult.owner_id == user.owner_id)
    return {'documents': [source(settings, doc) for doc in documents],
            'sql_sha256': sql_inventory(session, user.id, user.owner_id, document_id),
            'result_ids': [] if closure else sorted(str(i) for i in session.scalars(results)),
            'token_ids': [] if document_id else sorted(str(i) for i in session.scalars(
                select(AccountToken.id).where(AccountToken.email == user.email)))}


def prepare_request(session, settings, adapter, user, document=None):
    require_profile(settings, adapter)
    kind = 'document_deletion_request' if document is not None else 'account_closure_request'
    target = str(document.id if document is not None else user.id)
    with adapter.exclusive():
        existing = next((o for o in adapter.store.deletions() if o.kind == kind and o.target_id == target), None)
        if existing:
            if (existing.user_id, existing.owner_id) != (str(user.id), str(user.owner_id)):
                raise AuthorityError('Conflicting requester')
            return status(adapter, existing)
        if document is not None and document.owner_id != user.owner_id:
            raise AuthorityError('Wrong document owner')
        if account_restricted(adapter, user.id):
            raise AuthorityError('Account closure already confirmed')
        plan = plan_for(session, settings, user, [document] if document is not None else [],
                        document.id if document is not None else None, closure=document is None)
        op = DeletionOperation(str(uuid4()), kind, str(user.id), str(user.owner_id), target, None, plan, timestamp())
        with holds(settings, op, adapter):
            counter(session, adapter)
            session.rollback()
            adapter.store.save_deletion(op)
        return status(adapter, op)


def status(adapter, op):
    proof = entry(adapter, op)
    state = 'awaiting_confirmation'
    if proof:
        state = ('access_restricted' if op.kind.startswith('document_') else 'closure_confirmed')
        if op.kind.endswith('_execution'):
            state = 'processing'
        if proof['phase'] == 'complete':
            state = ('completed' if op.kind.endswith('_execution') else
                     'access_restricted' if op.kind.startswith('document_') else 'account_closed')
        elif cursor(adapter, op)['failed']:
            state = 'failed_recoverable'
    return {'operation_id': op.operation_id, 'state': state, 'completed': state == 'completed',
            'message': 'Traitement administratif manuel. Le statut ne vaut pas effacement des sauvegardes.'}


def prepare_execution(session, settings, adapter, parent_id, kind):
    require_profile(settings, adapter)
    if kind not in ('document_deletion_execution', 'account_purge_execution'):
        raise AuthorityError('Targeted execution type required')
    with adapter.exclusive():
        parent = next((o for o in adapter.store.deletions() if o.operation_id == str(parent_id)), None)
        expected = 'document_deletion_request' if kind.startswith('document_') else 'account_closure_request'
        if parent is None or parent.kind != expected:
            raise AuthorityError('Matching request required')
        proof = entry(adapter, parent)
        if not proof or proof['phase'] != 'complete':
            raise AuthorityError('Completed request confirmation required')
        existing = next((o for o in adapter.store.deletions() if o.kind == kind and o.parent_id == parent.operation_id), None)
        if existing:
            return existing
        user = session.get(User, UUID(parent.user_id))
        if not user or str(user.owner_id) != parent.owner_id:
            raise AuthorityError('Account identity changed')
        if kind == 'account_purge_execution' and (not user.disabled_at or not session.scalar(
                select(DeletionRequest.id).where(DeletionRequest.user_id == user.id))):
            raise AuthorityError('Closed account required')
        docs = session.scalars(select(Document).where(Document.owner_id == user.owner_id).order_by(Document.id)).all()
        if kind.startswith('document_'):
            docs = [d for d in docs if str(d.id) == parent.target_id]
            if len(docs) != 1 or source(settings, docs[0]) != parent.plan['documents'][0]:
                raise AuthorityError('Request source changed')
        plan = plan_for(session, settings, user, docs,
                        UUID(parent.target_id) if kind.startswith('document_') else None)
        op = DeletionOperation(str(uuid4()), kind, parent.user_id, parent.owner_id, parent.target_id,
                               parent.operation_id, plan, timestamp())
        with holds(settings, op, adapter):
            counter(session, adapter)
            session.rollback()
            adapter.store.save_deletion(op)
        return op


def cursor_path(adapter, op):
    return adapter.control / ('effect-'+op.operation_id+'.json')


def cursor(adapter, op):
    path = cursor_path(adapter, op)
    if not path.exists():
        return {'proposal': digest(operation_payload(op)), 'started': False, 'sql_erased': False,
                'effect_verified': False, 'failed': False}
    value = strict(read(path, 0, private=False))
    if (set(value) != {'proposal','started','sql_erased','effect_verified','failed'}
            or value['proposal'] != digest(operation_payload(op))
            or any(type(value[k]) is not bool for k in ('started','sql_erased','effect_verified','failed'))):
        raise AuthorityError('Invalid administrative effect cursor')
    return value


def save_cursor(adapter, op, value):
    write(cursor_path(adapter, op), canonical(value), 0, replace=True, public=True)


def no_workers(session, owner_id):
    from .ai.models import AIReservation
    from .ai.long_models import LongSummaryJob
    from .rag.models import IndexJob
    for model, condition in (
        (AIReservation, AIReservation.status == 'reserved'),
        (LongSummaryJob, LongSummaryJob.status.not_in(['completed','cancelled'])),
        (IndexJob, IndexJob.status.in_(['queued','running']))):
        if session.scalar(select(model.id).where(model.owner_id == owner_id, condition).limit(1)):
            raise AuthorityError('Worker/reservation reconciliation required')


def verify_effect(session, settings, adapter, op):
    owner = UUID(op.owner_id)
    if op.kind == 'document_deletion_request':
        if UUID(op.target_id) not in restricted_documents(adapter, owner):
            raise AuthorityError('Access restriction not established')
        return
    if op.kind == 'account_closure_request':
        user = session.get(User, UUID(op.user_id), populate_existing=True)
        request = session.scalar(select(DeletionRequest).where(DeletionRequest.user_id == UUID(op.user_id)))
        if not user or str(user.owner_id) != op.owner_id or user.disabled_at is None or request is None:
            raise AuthorityError('Closure effect not established')
        if session.scalar(select(AccountToken.id).where(AccountToken.email == user.email).limit(1)):
            raise AuthorityError('Account tokens remain')
        return
    from .rag.models import RAGResult
    if session.scalar(select(RAGResult.id).where(RAGResult.id.in_([UUID(i) for i in op.plan['result_ids']])).limit(1)):
        raise AuthorityError('Derived result residue remains')
    doc_ids = [UUID(item['id']) for item in op.plan['documents']]
    for table in Base.metadata.sorted_tables:
        if 'document_id' in table.c and session.execute(select(table).where(table.c.document_id.in_(doc_ids)).limit(1)).first():
            raise AuthorityError('Document dependency residue remains')
    for item in op.plan['documents']:
        identity = (UUID(item['id']), owner, item['name'], item['size'], item['sha256'])
        if durable_document_state(session.get_bind(), identity) != 'absent':
            raise AuthorityError('SQL erasure is not established')
        if os.path.lexists(Path(settings.storage_dir) / item['name']):
            raise AuthorityError('Physical residue remains')
    if op.kind == 'account_purge_execution':
        if session.scalar(select(AccountToken.id).where(AccountToken.id.in_([UUID(i) for i in op.plan['token_ids']])).limit(1)):
            raise AuthorityError('Account token residue remains')
        if session.get(User, UUID(op.user_id), populate_existing=True) is not None:
            raise AuthorityError('Account purge not established')
        for table in Base.metadata.sorted_tables:
            if 'owner_id' in table.c and table.name != 'public_registration_quota':
                if session.execute(select(table).where(table.c.owner_id == owner).limit(1)).first():
                    raise AuthorityError('Account dependency residue remains')


def apply(session, settings, adapter, operation_id, *, confirmation, offline_confirmed=False):
    """Root-only, exact signed target; no generic resource deletion or auto-approval."""
    if os.name != 'posix' or os.geteuid() != 0 or not offline_confirmed or str(operation_id) != confirmation:
        raise AuthorityError('Explicit root/offline/operation confirmation required')
    require_profile(settings, adapter)
    with adapter.exclusive():
        op = next((o for o in adapter.store.deletions() if o.operation_id == str(operation_id)), None)
        if op is None:
            raise AuthorityError('Unknown deletion operation')
        proof = entry(adapter, op)
        if not proof:
            raise AuthorityError('Independent authorization required')
        before = counter(session, adapter)
        state = cursor(adapter, op)
        try:
            with holds(settings, op, adapter):
                if proof['phase'] == 'complete':
                    verify_effect(session, settings, adapter, op)
                    return status(adapter, op)
                if op.kind == 'document_deletion_request':
                    verify_effect(session, settings, adapter, op)
                elif op.kind == 'account_closure_request':
                    close_account(session, op)
                else:
                    erase(session, settings, adapter, op, state)
                verify_effect(session, settings, adapter, op)
                if counter(session, adapter) != before:
                    raise AuthorityError('Cumulative counter changed')
                if op.kind == 'account_purge_execution':
                    with application_identity(adapter):
                        adapter.store.retire_user(op.user_id)
                state['effect_verified'] = True
                state['failed'] = False
                save_cursor(adapter, op, state)
                return {'operation_id': op.operation_id, 'state': 'result_pending', 'completed': False}
        except BaseException:
            emit('system.file_cleanup.failed', reason_code='cleanup_failed')
            state['failed'] = True
            state['effect_verified'] = False
            save_cursor(adapter, op, state)
            raise


def close_account(session, op):
    from .resource_limits import lock_workspace
    lock_workspace(session, UUID(op.owner_id))
    user = session.get(User, UUID(op.user_id), populate_existing=True, with_for_update=True)
    if not user or str(user.owner_id) != op.owner_id:
        raise AuthorityError('Account identity changed')
    if user.disabled_at is None:
        user.disabled_at = now()
    if not session.scalar(select(DeletionRequest.id).where(DeletionRequest.user_id == user.id)):
        session.add(DeletionRequest(user_id=user.id, owner_id=user.owner_id))
    # In-memory sessions are rejected by the signed intent on every request.
    session.execute(delete(AccountToken).where(AccountToken.email == user.email))
    session.commit()


def erase(session, settings, adapter, op, state):
    from sqlalchemy import text
    from .rag.models import RAGDocument, RAGResult
    owner = UUID(op.owner_id)
    if session.get_bind().dialect.name == 'sqlite':
        session.execute(text("UPDATE ai_budgets SET reserved_usd=reserved_usd WHERE id='development'"))
    else:
        session.execute(text("SELECT id FROM ai_budgets WHERE id='development' FOR UPDATE"))
    session.scalar(select(Workspace).where(Workspace.owner_id == owner).with_for_update())
    no_workers(session, owner)
    if not state['started']:
        current = sql_inventory(session, UUID(op.user_id), owner,
                                UUID(op.target_id) if op.kind.startswith('document_') else None)
        if current != op.plan['sql_sha256']:
            raise AuthorityError('SQL plan changed')
        if op.kind == 'account_purge_execution':
            referenced = set(session.scalars(select(Document.storage_name)))
            known_residues = {item['name'] for o in adapter.store.deletions()
                              if o.kind.endswith('_execution') and entry(adapter, o)
                              for item in o.plan['documents']}
            if any(path.name not in referenced | known_residues for path in Path(settings.storage_dir).iterdir()):
                raise AuthorityError('Unattributed storage residue requires reconciliation')
            from .lifecycle_registry import configured_registry
            with application_identity(adapter):
                if configured_registry(settings).pending_document_files(owner):
                    raise AuthorityError('Historical document residues require reconciliation')
        for item in op.plan['documents']:
            verify_source(settings, item)
        state['started'] = True
        save_cursor(adapter, op, state)
    if not state['sql_erased']:
        # A previous uncertain COMMIT is inspected, never retried blindly.
        docs = [session.get(Document, UUID(d['id']), populate_existing=True) for d in op.plan['documents']]
        user = session.get(User, UUID(op.user_id), populate_existing=True)
        absent = all(d is None for d in docs) and (op.kind.startswith('document_') or user is None)
        if not absent:
            current = sql_inventory(session, UUID(op.user_id), owner,
                                    UUID(op.target_id) if op.kind.startswith('document_') else None)
            if current != op.plan['sql_sha256']:
                raise AuthorityError('Partial SQL state requires reconciliation')
            for item in op.plan['documents']:
                verify_source(settings, item)
            for doc in docs:
                if doc is None or doc.owner_id != owner:
                    raise AuthorityError('Document scope changed')
                linked = select(RAGDocument.result_id).where(RAGDocument.document_id == doc.id)
                session.execute(delete(RAGResult).where(RAGResult.id.in_(linked)))
                session.delete(doc)
            session.flush()
            if op.kind == 'account_purge_execution':
                purge_dependencies(session, user, owner)
            try:
                session.commit()
            except BaseException:
                discard_session(session)
                raise
        else:
            session.rollback()
        for item in op.plan['documents']:
            identity = (UUID(item['id']), owner, item['name'], item['size'], item['sha256'])
            if durable_document_state(session.get_bind(), identity) != 'absent':
                raise AuthorityError('SQL commit remains uncertain')
        if op.kind == 'account_purge_execution' and session.get(User, UUID(op.user_id), populate_existing=True):
            raise AuthorityError('Account commit remains uncertain')
        state['sql_erased'] = True
        save_cursor(adapter, op, state)
    else:
        session.rollback()
    for item in op.plan['documents']:
        identity = (UUID(item['id']), owner, item['name'], item['size'], item['sha256'])
        if durable_document_state(session.get_bind(), identity) != 'absent':
            raise AuthorityError('SQL identity reappeared')
        path = Path(settings.storage_dir) / item['name']
        if os.path.lexists(path):
            verify_source(settings, item)
            path.unlink()
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def purge_dependencies(session, user, owner):
    from .ai.models import AIReservation, AIUsage
    from .rag.models import RAGResult
    if user is None or user.disabled_at is None:
        raise AuthorityError('Closed account required')
    session.execute(delete(RAGResult).where(RAGResult.owner_id == owner))
    session.execute(delete(AIUsage).where(AIUsage.owner_id == owner))
    session.execute(delete(AIReservation).where(AIReservation.owner_id == owner))
    session.execute(delete(AccountToken).where(AccountToken.email == user.email))
    session.execute(delete(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id))
    session.execute(delete(Workspace).where(Workspace.owner_id == owner))
    session.delete(user)
    session.flush()


def export_deletion(adapter, op, phase, session, export_key):
    # Called by the administrative exporter, never by an HTTP approval route.
    settings = session.info.get('deletion_settings')
    if settings is None:
        raise AuthorityError('Administrative deletion settings required')
    require_profile(settings, adapter)
    count = counter(session, adapter)
    if phase == 'authorize':
        user = session.get(User, UUID(op.user_id))
        if user is None or str(user.owner_id) != op.owner_id:
            raise AuthorityError('Deletion target missing')
        current = sql_inventory(session, user.id, user.owner_id,
                                UUID(op.target_id) if op.kind.startswith('document_') else None)
        if current != op.plan['sql_sha256']:
            raise AuthorityError('Deletion SQL proposal changed')
        with holds(settings, op, adapter):
            for item in op.plan['documents']:
                verify_source(settings, item)
        facts = 'deletion_plan_verified'
    elif phase == 'complete':
        if not cursor(adapter, op)['effect_verified']:
            raise AuthorityError('Administrative effect inspection required')
        verify_effect(session, settings, adapter, op)
        facts = 'deletion_effect_verified'
    else:
        raise AuthorityError('Invalid deletion export phase')
    session.rollback()
    payload = {'version': 1, 'instance': adapter.instance, 'cohort': str(adapter.cohort_id),
               'challenge': adapter.nonce, 'operation': operation_payload(op), 'phase': phase,
               'counter': count, 'facts': facts}
    validate_operation(payload['operation'])
    return sign(payload, export_key)
