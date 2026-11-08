"""Real restored PostgreSQL, originals and the single signed operator ledger."""
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update

from backend import lite_reconciliation as recovery
from backend.account_models import PublicRegistrationQuota
from backend.auth import User
from backend.lite_authority import AuthorityError, canonical, strict, operation_payload
from backend.lite_deletions import prepare_execution
from backend.models import Document, now
from backend.recovery_quarantine import read_recovery_state
from tests.test_lite_snapshot import (capture_env, deletions, domains, real_admissions, ledgers,
    take, restored, resume_source, enroll)
from tests.test_lite_deletions import document_request, execution, close, confirm, effect


@pytest.fixture
def laboratory(capture_env):
    return capture_env


def consult(lab, target, snapshot, engine):
    identity = strict((target/'destination.json').read_bytes())
    challenge = recovery.challenge(target, snapshot, engine, confirmation=identity['destination'])
    ledger = lab[0][2]['ledger']
    return ledger.refresh(challenge['challenge'], confirmation=challenge['challenge'])


def freeze(lab):
    app = lab[0][1]
    with app.state.sessions() as session:
        session.execute(update(PublicRegistrationQuota).values(closed=True)); session.commit()
    app.state.recovery_ready_at_start = False
    app.state.engine.dispose(); app.state.authentication_engine.dispose()


def inventory(lab, target, snapshot, engine):
    freeze(lab)
    env = lab[0]
    current = consult(lab, target, snapshot, engine)
    _, context, _, _ = recovery.destination(target, snapshot, engine)
    with env[1].state.sessions() as session:
        proposal = recovery.export_inventory(env[1].state.settings, env[2]['adapter'], session,
            context, current, export_key=env[2]['export'],
            confirmation=context['destination'], offline_confirmed=True)
    op = proposal['payload']['operation']
    env[2]['ledger'].approve(proposal, confirmation=op['operation_id'], reference='synthetic-current-completeness')
    return op


def planned(lab, target, snapshot, engine, origin, *, approve=True):
    current = consult(lab, target, snapshot, engine)
    proposal = recovery.plan(target, snapshot, engine, current, origin.operation_id,
        confirmation=origin.operation_id, export_key=lab[0][2]['export'], offline_confirmed=True)
    if approve:
        lab[0][2]['ledger'].approve(proposal,
            confirmation=proposal['payload']['operation']['operation_id'], reference='synthetic-destination-authorization')
    return proposal['payload']['operation']


def applied(lab, target, snapshot, engine, op, *, complete=True):
    current = consult(lab, target, snapshot, engine)
    proposal = recovery.execute(target, snapshot, engine, current, op['operation_id'],
        confirmation=op['operation_id'], export_key=lab[0][2]['export'], offline_confirmed=True)
    if complete:
        lab[0][2]['ledger'].approve(proposal,
            confirmation=op['operation_id'], reference='synthetic-destination-result')
    return proposal


def diagnosis(lab, target, snapshot, engine):
    current = consult(lab, target, snapshot, engine)
    return recovery.diagnose(target, snapshot, engine, current,
        confirmation=strict((target/'destination.json').read_bytes())['destination'], offline_confirmed=True)


def source_document_deleted(lab):
    env = lab[0]
    op = execution(env)
    confirm(env, op, 'authorize'); effect(env, op); confirm(env, op, 'complete')
    return op


def source_purged(lab):
    env = lab[0]
    parent = close(env)
    with env[1].state.sessions() as session:
        op = prepare_execution(session, env[1].state.settings, env[2]['adapter'],
                               parent.operation_id, 'account_purge_execution')
    confirm(env, op, 'authorize'); effect(env, op); confirm(env, op, 'complete')
    return parent, op


def test_real_document_reapplication_new_identity_and_independent_result(laboratory):
    lab = laboratory
    snapshot, manifest, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        before = target/'documents'/lab[0][-1].name
        assert before.stat().st_ino != origin.plan['documents'][0]['inode']
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        assert op['effect']['plan']['documents'][0]['inode'] == before.stat().st_ino
        assert op['effect']['plan'] != origin.plan
        proposal = applied(lab, target, snapshot, engine, op)
        assert not before.exists()
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM documents')) == 0
            assert connection.scalar(text('SELECT count(*) FROM document_chunks')) == 0
            assert connection.scalar(text("SELECT issued_count FROM public_registration_quota WHERE id='public'")) == 1
        report = diagnosis(lab, target, snapshot, engine)
        assert report['status'] == 'reconciled_quarantined'
        assert report['quarantine_release_authorized'] is False
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
        # A newly read current view is required even for an idempotent retry.
        applied(lab, target, snapshot, engine, op)
        assert proposal['payload']['facts'] == 'recovery_effect_verified'
        Path('/results/reconciliation-real-evidence.json').write_bytes(canonical({
            'manifest': checksum, 'source_identity': origin.plan['documents'][0],
            'destination_identity': op['effect']['plan']['documents'][0],
            'result': report, 'original_plan_unchanged': all(
                e['request']['operation'] == operation_payload(origin)
                for e in lab[0][2]['ledger'].recover()['events']
                if e['request']['operation']['operation_id'] == origin.operation_id),
            'file_absent': not before.exists(), 'sql_document_and_chunks_absent': True}))
    finally:
        engine.dispose()


@pytest.mark.parametrize('mode', ['pending', 'closure', 'purge'])
def test_pending_closure_and_purge_stay_quarantined(laboratory, mode):
    lab = laboratory
    second = enroll(lab)
    raw = b'Synthetic other-owner data must survive.'
    path = lab[0][1].state.settings.storage_dir/(uuid4().hex+'.txt')
    path.write_bytes(raw); path.chmod(0o600)
    with lab[0][1].state.sessions() as session:
        other = Document(owner_id=second.owner_id, filename='other.txt', storage_name=path.name,
                         media_type='text/plain', size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        session.add(other); session.commit()
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    if mode == 'pending':
        origin = document_request(lab[0]); confirm(lab[0], origin, 'authorize')
    elif mode == 'closure':
        origin = close(lab[0])
    else:
        _, origin = source_purged(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        applied(lab, target, snapshot, engine, op)
        report = diagnosis(lab, target, snapshot, engine)
        assert report['status'] == 'reconciled_quarantined'
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM users WHERE id=:id'),
                                     {'id': second.user_id}) == 1
            assert connection.scalar(text("SELECT issued_count FROM public_registration_quota WHERE id='public'")) == 2
            if mode != 'pending':
                row = connection.execute(text('SELECT disabled_at FROM users WHERE id=:id'),
                                         {'id': lab[0][3].user_id}).first()
                assert row is None if mode == 'purge' else row.disabled_at is not None
                assert connection.scalar(text(
                    'SELECT count(*) FROM account_tokens WHERE email=(SELECT email FROM users WHERE id=:id)'),
                    {'id': lab[0][3].user_id}) == 0
        assert (target/'documents'/path.name).read_bytes() == raw
        if mode == 'purge':
            assert not (target/'documents'/lab[0][-1].name).exists()
            cache = recovery.LocalOperations(target/'lite', 0)
            assert lab[0][3].password_hash.encode() not in cache.path.read_bytes()
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    finally:
        engine.dispose()


def make_hold(lab):
    from backend.lifecycle_durability import configured_coordinator
    from backend.lifecycle_registry import configured_registry
    from backend.lifecycle_holds import HoldStore
    settings = lab[0][1].state.settings
    coordinator = configured_coordinator(settings, configured_registry(settings))
    store = HoldStore(settings.lifecycle_holds_path, coordinator.authenticated)
    at = now(); identifier = str(uuid4()); actor = str(uuid4())
    store.create(dict(id=identifier, responsible_id=actor, scope_kind='owner',
        scope_id=str(lab[0][3].owner_id), reason='legal_hold', reviewed_at=at,
        review_at=at+timedelta(days=1), ends_at=None, end_event='legal_hold_lifted'), at)
    return store, identifier, actor


def test_current_hold_after_snapshot_blocks_and_release_is_explicit(laboratory):
    from backend.lifecycle_holds import ActiveHoldError
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    store, identifier, actor = make_hold(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        first = inventory(lab, target, snapshot, engine)
        assert first['holds'][identifier]['release'] is None
        with pytest.raises(ActiveHoldError):
            planned(lab, target, snapshot, engine, origin)
        assert (target/'documents'/lab[0][-1].name).exists()
        store.release(identifier, actor, str(uuid4()), b'synthetic documented hold release', now())
        second = inventory(lab, target, snapshot, engine)
        assert second['holds'][identifier]['release'] is not None
        op = planned(lab, target, snapshot, engine, origin)
        applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()


@pytest.mark.parametrize('point', ['before_sql', 'commit_uncertain', 'between_sql_file', 'after_unlink', 'after_result'])
def test_crash_reconciliation_resumes_from_actual_effects(laboratory, monkeypatch, point):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        original_save = recovery.deletions.save_cursor
        original_unlink = Path.unlink
        file = target/'documents'/lab[0][-1].name
        def faulty_save(adapter, effect, state):
            if point == 'before_sql' and state['started'] and not state['sql_erased']:
                raise OSError('synthetic before SQL')
            if point == 'commit_uncertain' and state['sql_erased']:
                raise OSError('synthetic lost SQL acknowledgement')
            if point == 'after_unlink' and state['effect_verified']:
                raise OSError('synthetic after physical effect')
            return original_save(adapter, effect, state)
        def faulty_unlink(path, *args, **kwargs):
            if point == 'between_sql_file' and path == file:
                raise OSError('synthetic denied unlink')
            return original_unlink(path, *args, **kwargs)
        if point != 'after_result':
            with monkeypatch.context() as patch:
                patch.setattr(recovery.deletions, 'save_cursor', faulty_save)
                patch.setattr(Path, 'unlink', faulty_unlink)
                with pytest.raises(OSError):
                    applied(lab, target, snapshot, engine, op)
        else:
            applied(lab, target, snapshot, engine, op)
        # New objects/current consultation, persisted plan and cursor only.
        engine.dispose()
        applied(lab, target, snapshot, engine, strict((target/'reconciliation'/('plan-'+op['operation_id']+'.json')).read_bytes()))
        assert not file.exists()
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()


@pytest.mark.parametrize('bad', ['no_authorization', 'modified_plan', 'wrong_owner', 'changed_content',
                                 'old_view', 'missing_current', 'wrong_confirmation', 'wrong_cohort'])
def test_new_authorization_identity_and_freshness_required(laboratory, bad):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        if bad in ('wrong_owner', 'changed_content'):
            if bad == 'changed_content':
                (target/'documents'/lab[0][-1].name).write_bytes(b'changed synthetic file')
            else:
                with engine.begin() as connection:
                    connection.execute(text('UPDATE documents SET owner_id=:owner'), {'owner': uuid4()})
            with pytest.raises(AuthorityError):
                planned(lab, target, snapshot, engine, origin)
            return
        op = planned(lab, target, snapshot, engine, origin, approve=bad != 'no_authorization')
        current = consult(lab, target, snapshot, engine)
        if bad == 'modified_plan':
            path = target/'reconciliation'/('plan-'+op['operation_id']+'.json')
            changed = strict(path.read_bytes()); changed['effect']['plan']['sql_sha256'] = '0'*64
            path.write_bytes(canonical(changed))
        if bad == 'old_view':
            current = strict((target/'control/accepted.json').read_bytes())
        if bad == 'missing_current':
            current = {}
        if bad == 'wrong_cohort':
            current['payload']['cohort'] = str(uuid4())
        with pytest.raises((AuthorityError, KeyError)):
            recovery.execute(target, snapshot, engine, current, op['operation_id'],
                confirmation=str(uuid4()) if bad == 'wrong_confirmation' else op['operation_id'],
                export_key=lab[0][2]['export'], offline_confirmed=True)
        assert (target/'documents'/lab[0][-1].name).exists()
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    finally:
        engine.dispose()


def test_counter_three_to_five_never_recreates_missing_accounts(laboratory):
    lab = laboratory
    enroll(lab); enroll(lab)
    snapshot, _, checksum = take(lab)
    resume_source(lab); enroll(lab); enroll(lab)
    _, origin = source_purged(lab)
    from tests.test_lite_admissions import invitation, send
    assert send(lab[0][0], invitation(lab[0][1])).status_code != 201
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        applied(lab, target, snapshot, engine, op)
        report = diagnosis(lab, target, snapshot, engine)
        assert report['issued_count'] == 5
        assert 'active_account_not_reconstructible' in report['reasons']
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM users')) == 2
            assert connection.scalar(text("SELECT issued_count FROM public_registration_quota WHERE id='public'")) == 5
            assert connection.scalar(text("SELECT closed FROM public_registration_quota WHERE id='public'"))
    finally:
        engine.dispose()


def test_inventory_active_present_missing_unknown_and_changed_owner(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM documents'))
        assert 'active_document_missing' in diagnosis(lab, target, snapshot, engine)['reasons']
    finally:
        engine.dispose()


def test_incomplete_or_forged_inventory_not_authoritative(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        op = inventory(lab, target, snapshot, engine)
        changed = {**op, 'operation_id': str(uuid4()), 'accounts': []}
        current = consult(lab, target, snapshot, engine)
        changed['basis'] = {'sequence': current['payload']['sequence'], 'head': current['payload']['head']}
        proposal = recovery.request(changed, 'complete', 1, current['payload']['challenge'], lab[0][2]['export'])
        with pytest.raises(AuthorityError):
            lab[0][2]['ledger'].approve(proposal, confirmation=changed['operation_id'], reference='synthetic-incomplete')
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    finally:
        engine.dispose()


def test_old_hold_in_snapshot_with_current_documented_release(laboratory):
    lab = laboratory
    store, identifier, actor = make_hold(lab)
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    store.release(identifier, actor, str(uuid4()), b'synthetic release after snapshot', now())
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()


def test_current_active_document_created_after_snapshot_is_not_faked(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    raw = b'Post-snapshot active synthetic original.'
    path = lab[0][1].state.settings.storage_dir/(uuid4().hex+'.txt')
    path.write_bytes(raw); path.chmod(0o600)
    with lab[0][1].state.sessions() as session:
        session.add(Document(owner_id=lab[0][3].owner_id, filename='later.txt', storage_name=path.name,
                             media_type='text/plain', size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        session.commit()
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        report = diagnosis(lab, target, snapshot, engine)
        assert report['status'] == 'blocked' and 'active_document_missing' in report['reasons']
        assert not (target/'documents'/path.name).exists()
    finally:
        engine.dispose()


def test_freshness_is_single_use_and_plan_cannot_cross_destinations(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    other, other_engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        current = consult(lab, target, snapshot, engine)
        recovery.execute(target, snapshot, engine, current, op['operation_id'], confirmation=op['operation_id'],
                         export_key=lab[0][2]['export'], offline_confirmed=True)
        with pytest.raises(AuthorityError):
            recovery.execute(target, snapshot, engine, current, op['operation_id'], confirmation=op['operation_id'],
                             export_key=lab[0][2]['export'], offline_confirmed=True)
        consult(lab, other, snapshot, other_engine)
        with pytest.raises(AuthorityError):
            recovery.execute(other, snapshot, other_engine, current, op['operation_id'], confirmation=op['operation_id'],
                             export_key=lab[0][2]['export'], offline_confirmed=True)
        assert (other/'documents'/lab[0][-1].name).exists()
    finally:
        engine.dispose(); other_engine.dispose()


@pytest.mark.parametrize('bad', ['unknown', 'owner', 'hash', 'incomplete_inventory'])
def test_inventory_conflicts_remain_closed(laboratory, bad):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        op = inventory(lab, target, snapshot, engine)
        if bad == 'incomplete_inventory':
            current = consult(lab, target, snapshot, engine)
            changed = {**op, 'operation_id': str(uuid4()), 'documents': [],
                       'basis': {'sequence': current['payload']['sequence'], 'head': current['payload']['head']}}
            proposal = recovery.request(changed, 'complete', 1, current['payload']['challenge'], lab[0][2]['export'])
            lab[0][2]['ledger'].approve(proposal, confirmation=changed['operation_id'], reference='synthetic-incomplete-documents')
        elif bad == 'unknown':
            old = lab[0][-1]
            with engine.begin() as connection:
                connection.execute(text('DELETE FROM documents'))
            with recovery.Session(engine) as session:
                session.add(Document(owner_id=lab[0][3].owner_id, filename='unknown.txt', storage_name=old.name,
                    media_type='text/plain', size_bytes=len(old.read_bytes()), sha256=hashlib.sha256(old.read_bytes()).hexdigest()))
                session.commit()
        elif bad == 'owner':
            with engine.begin() as connection:
                connection.execute(text('UPDATE documents SET owner_id=:owner'), {'owner': uuid4()})
        else:
            (target/'documents'/lab[0][-1].name).write_bytes(b'changed original')
        if bad == 'hash':
            with pytest.raises(AuthorityError):
                diagnosis(lab, target, snapshot, engine)
        else:
            report = diagnosis(lab, target, snapshot, engine)
            assert report['status'] == 'blocked'
            assert ('document_identity_conflict' if bad == 'owner' else 'unknown_document') in report['reasons']
        assert read_recovery_state(target/'recovery-state.json') == 'quarantined'
    finally:
        engine.dispose()


def test_process_restart_uses_persistent_signed_plan_and_cli(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        current = consult(lab, target, snapshot, engine)
        inbox = target/'view.json'; inbox.write_bytes(canonical(current)); inbox.chmod(0o600)
        out = target/'result.json'
        env = os.environ.copy()
        env['DOCUMIND_RESTORE_DATABASE_URL'] = engine.url.render_as_string(hide_password=False)
        engine.dispose()
        result = subprocess.run([sys.executable, '-m', 'tools.lite_restore', 'reconcile-apply',
            '--snapshot', str(snapshot), '--target', str(target), '--authority-view', str(inbox),
            '--operation', op['operation_id'], '--confirm', op['operation_id'],
            '--offline-confirmed', '--export-key', str(lab[0][2]['dirs']['export_keys']/'signing'),
            '--out', str(out)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout+result.stderr
        proposal = strict(out.read_bytes())
        lab[0][2]['ledger'].approve(proposal, confirmation=op['operation_id'], reference='synthetic-new-process-result')
        assert not (target/'documents'/lab[0][-1].name).exists()
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()


def test_nonroot_cannot_reconcile_or_inspect_private_context(monkeypatch, capsys):
    from tools.lite_restore import main
    monkeypatch.setattr(os, 'geteuid', lambda: 10001, raising=False)
    with pytest.raises(AuthorityError):
        recovery.destination('/never-real', '/never-real', None)
    assert main(['reconcile-challenge', '--target', '/never-real', '--snapshot', '/never-real',
                 '--confirm', str(uuid4()), '--out', '/never-real']) == 1
    assert capsys.readouterr().out == '{"status":"blocked","opening_authorized":false}\n'


def test_pending_reservation_then_corroborated_cancellation_never_counts_as_commit(laboratory):
    from tests.test_lite_authority import prepare_http, confirm_phase
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    _, pending = prepare_http(lab[0][:3])
    confirm_phase(lab[0][:3], pending, 'reserve')
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        assert 'uncertain_reservation' in diagnosis(lab, target, snapshot, engine)['reasons']
        confirm_phase(lab[0][:3], pending, 'cancel')
        # A transition of an OLD operation invalidates the previously signed inventory.
        with pytest.raises(AuthorityError):
            diagnosis(lab, target, snapshot, engine)
        inventory(lab, target, snapshot, engine)
        report = diagnosis(lab, target, snapshot, engine)
        assert report['status'] == 'reconciled_quarantined' and report['issued_count'] == 1
    finally:
        engine.dispose()


def test_higher_uncorroborated_counter_is_never_lowered(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        with engine.begin() as connection:
            connection.execute(text("UPDATE public_registration_quota SET issued_count=2 WHERE id='public'"))
        with pytest.raises(AuthorityError):
            diagnosis(lab, target, snapshot, engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT issued_count FROM public_registration_quota WHERE id='public'")) == 2
    finally:
        engine.dispose()


def test_original_source_authorization_cannot_erase_restored_identity(laboratory):
    from backend.lite_deletions import apply
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        settings = lab[0][1].state.settings.model_copy(update={
            'storage_dir': target/'documents', 'recovery_state_path': target/'recovery-state.json'})
        with recovery.Session(engine) as session, pytest.raises(AuthorityError):
            apply(session, settings, lab[0][2]['adapter'], origin.operation_id,
                  confirmation=origin.operation_id, offline_confirmed=True)
        assert (target/'documents'/lab[0][-1].name).exists()
    finally:
        engine.dispose()


def test_unknown_current_holds_refuses_inventory_and_any_destructive_plan(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        # A store missing from the source is not an authoritative empty hold set.
        lab[0][1].state.settings.lifecycle_holds_path.unlink()
        with pytest.raises((ValueError, OSError)):
            inventory(lab, target, snapshot, engine)
        with pytest.raises(AuthorityError):
            planned(lab, target, snapshot, engine, origin)
        assert (target/'documents'/lab[0][-1].name).exists()
    finally:
        engine.dispose()


def test_hold_mirror_interrupted_between_authenticated_and_hold_stores(laboratory, monkeypatch):
    from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
    lab = laboratory
    store, identifier, actor = make_hold(lab)
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    store.release(identifier, actor, str(uuid4()), b'synthetic documented release', now())
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        original = AuthenticatedConfirmationStore.update_hold
        def interrupted(store, expected, snapshot):
            original(store, expected, snapshot)
            raise OSError('synthetic hold mirror acknowledgement lost')
        with monkeypatch.context() as patch:
            patch.setattr(AuthenticatedConfirmationStore, 'update_hold', interrupted)
            with pytest.raises(OSError):
                applied(lab, target, snapshot, engine, op)
        assert (target/'documents'/lab[0][-1].name).exists()
        applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()


def test_effect_without_result_confirmation_stays_blocked(laboratory):
    lab = laboratory
    snapshot, _, checksum = take(lab)
    resume_source(lab)
    origin = source_document_deleted(lab)
    target, engine, _ = restored(lab, snapshot, checksum)
    try:
        inventory(lab, target, snapshot, engine)
        op = planned(lab, target, snapshot, engine, origin)
        applied(lab, target, snapshot, engine, op, complete=False)
        assert not (target/'documents'/lab[0][-1].name).exists()
        report = diagnosis(lab, target, snapshot, engine)
        assert 'reapplication_result_unconfirmed' in report['reasons']
        applied(lab, target, snapshot, engine, op)
        assert diagnosis(lab, target, snapshot, engine)['status'] == 'reconciled_quarantined'
    finally:
        engine.dispose()
