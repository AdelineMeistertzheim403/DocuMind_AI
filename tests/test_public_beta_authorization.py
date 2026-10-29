"""Closed-by-default beta delivery, using only synthetic configuration and SQL state."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tools import deploy_production as deploy
from tools import prepare_production as prepare
from tests.test_deployment import release, simulation
from tests.test_public_beta import beta, enroll, signup_body, PASSWORD


PUBLIC = {'REGISTRATION_MODE': 'public', 'PUBLIC_REGISTRATION_LIMIT': '5',
          'AI_ENABLED': 'false', 'OWNER_DEMO_ENABLED': 'false', 'LEGACY_API_ENABLED': 'false'}
EFFECTIVE_PUBLIC = {'REGISTRATION_MODE': 'public', 'PUBLIC_REGISTRATION_LIMIT': 5,
                    'AI_ENABLED': False, 'OWNER_DEMO_ENABLED': False, 'LEGACY_API_ENABLED': False}


def configuration(environment, recovery_control_file=None):
    data = yaml.safe_load(Path('compose.production.yaml').read_text(encoding='utf-8'))
    for service, component in (('api', 'backend'), ('web', 'frontend'), ('db', 'postgres')):
        data['services'][service]['image'] = release('0007')['images'][component]
    data['services']['api']['environment'] = {
        **environment, 'ACCOUNT_BASE_URL': 'https://' + deploy.HOST}
    data['services']['api']['volumes'] = [
        {'type': 'volume', 'source': 'production_documents', 'target': '/app/var'},
        {'type': 'volume', 'source': 'production_lifecycle', 'target': '/app/lifecycle'},
        {'type': 'bind', 'source': str(recovery_control_file or Path('/synthetic/recovery-state.json')),
         'target': '/run/documind/recovery-state.json', 'read_only': True},
    ]
    data['volumes'] = {
        name: {'name': f'{deploy.PROJECT}_{name}'}
        for name in ('production_documents', 'production_lifecycle')
    }
    return data


def stack_for(environment):
    data = configuration(environment)
    return SimpleNamespace(release=release('0007'), call=lambda *args: json.dumps(data))


def test_public_configuration_requires_separate_approval():
    with pytest.raises(deploy.DeploymentError, match='approval'):
        deploy.check_config(stack_for(PUBLIC))


def test_explicit_approval_accepts_only_closed_preparation_profile():
    assert deploy.check_config(stack_for(PUBLIC), True)['services']['api']['environment']['PUBLIC_REGISTRATION_LIMIT'] == '5'


@pytest.mark.parametrize('key,value', [
    ('PUBLIC_REGISTRATION_LIMIT', '4'), ('PUBLIC_REGISTRATION_LIMIT', '6'),
    ('PUBLIC_REGISTRATION_LIMIT', None), ('AI_ENABLED', 'true'),
    ('OWNER_DEMO_ENABLED', 'true'), ('LEGACY_API_ENABLED', 'true'), ('AI_ENABLED', None),
])
def test_public_profile_rejects_unsafe_or_missing_values(key, value):
    with pytest.raises(deploy.DeploymentError):
        deploy.check_config(stack_for({**PUBLIC, key: value}), True)


@pytest.mark.parametrize('mode', ['disabled', 'invite'])
def test_ordinary_modes_do_not_need_public_approval(mode):
    assert deploy.check_config(stack_for({'REGISTRATION_MODE': mode}))


def test_public_profile_requires_schema_0007():
    stack = stack_for(PUBLIC)
    stack.release = release('0006')
    with pytest.raises(deploy.DeploymentError, match='0007'):
        deploy.check_config(stack, True)


@pytest.mark.parametrize('state', [None, {'closed': False, 'issued_count': 0},
    {'closed': True, 'issued_count': -1}, {'closed': True, 'issued_count': 6},
    {'closed': True, 'issued_count': True}, {'closed': 'true', 'issued_count': 1}])
def test_public_deployment_refuses_missing_open_or_ambiguous_quota(state):
    stack = SimpleNamespace(sql=lambda query: json.dumps(state))
    with pytest.raises(deploy.DeploymentError):
        deploy.check_public_quota(stack)


def test_quota_check_reads_only_and_preserves_lifetime_counter():
    queries = []
    def sql(query):
        queries.append(query)
        return json.dumps({'closed': True, 'issued_count': 4})
    assert deploy.check_public_quota(SimpleNamespace(sql=sql)) == {'closed': True, 'issued_count': 4}
    assert len(queries) == 1 and queries[0].startswith('SELECT ')
    assert 'UPDATE ' not in queries[0]


@pytest.mark.parametrize('allow_migration', [False, True])
def test_migration_approval_never_substitutes_for_beta_approval(simulation, monkeypatch, allow_migration):
    args, events, state, bundle = simulation
    args.allow_migration = allow_migration
    monkeypatch.setattr(deploy, 'check_config', lambda stack, approved=False:
                        deploy.registration_policy(PUBLIC, '0007', approved))
    with pytest.raises(deploy.DeploymentError, match='approval'):
        deploy.execute(args, {})
    assert not events


def public_simulation(simulation, monkeypatch, *, opened=False):
    args, events, state, bundle = simulation
    control_file = args.root.parent / 'recovery-state.json'
    control_file.write_text('{"format":1,"state":"ready"}\n', encoding='utf-8')
    args.approve_public_beta = True
    state['revision'] = '0007'
    (bundle / 'release.json').write_text(json.dumps(release('0007')))
    from tests.test_release_security import approved_bundle
    from tools import release_security
    trust={'format':1,'releases':{}}
    approved_bundle(bundle,release('0007'),trust)
    monkeypatch.setattr(release_security,'load_trust',lambda:trust)
    original_stack = deploy.Stack
    class PublicStack(original_stack):
        def call(self, *args):
            if args[0] == 'run' and args[-2] == '-c':
                events.append(('settings', ()))
                return json.dumps(EFFECTIVE_PUBLIC)
            return super().call(*args)
        def sql(self, query):
            if 'has_public_users' in query:
                return json.dumps({'has_public_users':True,'closed':not opened,'issued_count':3})
            if 'public_registration_quota' in query:
                events.append(('quota', (query,)))
                return json.dumps({'closed': not opened, 'issued_count': 3})
            return super().sql(query)
    monkeypatch.setattr(deploy, 'Stack', PublicStack)
    old = PublicStack(args.root, bundle.parent / 'prior', release('0007'))
    monkeypatch.setattr(deploy, 'current_stack', lambda *args: old)
    monkeypatch.setattr(deploy, 'check_config', lambda *args: configuration(PUBLIC, control_file))
    return args, events, state, bundle


def test_authorized_deployment_preserves_closed_quota_and_counter(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    report = {}
    deploy.execute(args, report)
    assert report['status'] == 'success'
    assert report['public_beta']['quota_before'] == report['public_beta']['quota_after'] == {'closed': True, 'issued_count': 3}
    assert len([event for event in events if event[0] == 'quota']) >= 3
    assert not any('UPDATE ' in str(event) for event in events)
    assert not any('reopen' in str(event) for event in events)


def test_open_quota_refuses_before_pull_backup_or_service_change(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch, opened=True)
    with pytest.raises(deploy.DeploymentError, match='closed'):
        deploy.execute(args, {})
    assert all(name == 'quota' for name, _ in events)


def test_public_first_installation_requires_separate_closed_schema_install(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    args.initialize = True
    monkeypatch.setattr(deploy, 'current_stack', lambda *args: None)
    with pytest.raises(deploy.DeploymentError, match='existing.*0007'):
        deploy.execute(args, {})
    assert not events


def test_public_mode_cannot_be_combined_with_a_schema_upgrade(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    args.allow_migration = True
    state['revision'] = '0006'
    with pytest.raises(deploy.DeploymentError, match='existing.*0007'):
        deploy.execute(args, {})
    assert not events


@pytest.mark.parametrize('approved,mode', [(False, 'disabled'), (False, 'invite'), (True, 'public')])
def test_preparer_uses_same_policy_without_changing_sql_or_environment(tmp_path, monkeypatch, approved, mode):
    manifest = tmp_path / 'release.json'
    manifest.write_text(json.dumps(release('0007')))
    environment = {**PUBLIC, 'REGISTRATION_MODE': mode, 'ACCOUNT_BASE_URL': 'https://' + deploy.HOST,
                   'POSTGRES_PASSWORD': 'fictitious-database-secret', 'BFF_SERVICE_KEY': 'fictitious-bff-secret',
                   'TRAEFIK_CONTAINER': 'fictitious-traefik'}
    original = dict(environment)
    monkeypatch.setattr(prepare, 'dotenv_values', lambda *args: environment)
    argv = ['prepare_production.py', '--release', str(manifest)] + (['--approve-public-beta'] if approved else [])
    monkeypatch.setattr('sys.argv', argv)
    prepare.main()
    assert environment == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ['images.env', 'release.json']
    assert 'secret' not in (tmp_path / 'images.env').read_text()


@pytest.mark.parametrize('change,approved', [({}, False), ({'PUBLIC_REGISTRATION_LIMIT': '6'}, True),
    ({'AI_ENABLED': 'true'}, True), ({'OWNER_DEMO_ENABLED': 'true'}, True),
    ({'LEGACY_API_ENABLED': 'true'}, True)])
def test_preparer_refuses_unsafe_public_profile_before_writing_pins(tmp_path, monkeypatch, change, approved, capsys):
    manifest = tmp_path / 'release.json'
    manifest.write_text(json.dumps(release('0007')))
    environment = {**PUBLIC, 'ACCOUNT_BASE_URL': 'https://' + deploy.HOST,
                   'POSTGRES_PASSWORD': 'fictitious-secret-must-not-leak', 'BFF_SERVICE_KEY': 'fictitious-bff-secret',
                   'TRAEFIK_CONTAINER': 'fictitious-traefik', **change}
    monkeypatch.setattr(prepare, 'dotenv_values', lambda *args: environment)
    monkeypatch.setattr('sys.argv', ['prepare', '--release', str(manifest)] + (['--approve-public-beta'] if approved else []))
    with pytest.raises(SystemExit) as caught:
        prepare.main()
    assert not (tmp_path / 'images.env').exists()
    assert 'fictitious-secret' not in str(caught.value) + str(capsys.readouterr())


def test_public_rollback_keeps_gate_closed_without_database_downgrade(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    args.rollback = True
    report = {}
    deploy.execute(args, report)
    assert report['status'] == 'success'
    assert report['public_beta']['quota_after'] == {'closed': True, 'issued_count': 3}
    assert not any('alembic' in arguments for _, arguments in events)


@pytest.mark.parametrize('change', [{'AI_ENABLED': True}, {'REGISTRATION_MODE': 'invite'}])
def test_effective_image_settings_are_validated_before_quiescing_services(simulation, monkeypatch, change):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    original = deploy.Stack.call
    def changed(self, *arguments):
        if arguments[0] == 'run' and arguments[-2] == '-c':
            return json.dumps({**EFFECTIVE_PUBLIC, **change})
        return original(self, *arguments)
    monkeypatch.setattr(deploy.Stack, 'call', changed)
    with pytest.raises(deploy.DeploymentError):
        deploy.execute(args, {})
    assert not any(arguments[:1] == ('stop',) or name == 'backup' for name, arguments in events)


def test_changed_quota_blocks_activation_without_resetting_it(simulation, monkeypatch):
    args, events, state, bundle = public_simulation(simulation, monkeypatch)
    quota = {'closed': True, 'issued_count': 3}
    original_backup=deploy.create_backup
    def changed_after_backup(*arguments,**kwargs):
        original_backup(*arguments,**kwargs)
        quota['issued_count']=4
    monkeypatch.setattr(deploy,'create_backup',changed_after_backup)
    monkeypatch.setattr(deploy, 'check_public_quota', lambda stack: dict(quota))
    with pytest.raises(deploy.DeploymentError, match='changed'):
        deploy.execute(args, {})
    assert not any(name == 'activate' or 'alembic' in arguments for name, arguments in events)


def test_workflow_approval_is_manual_false_and_distinct_from_migration():
    workflow = yaml.load(Path('.github/workflows/deploy.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch'}
    approval = workflow['on']['workflow_dispatch']['inputs']['approve_public_beta']
    assert approval['type'] == 'boolean' and approval['default'] == 'false'
    rollout = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('id') == 'rollout')
    assert rollout['env']['APPROVE_PUBLIC_BETA'] == '${{ inputs.approve_public_beta }}'
    assert 'if [ "$APPROVE_PUBLIC_BETA" = true ]; then FLAGS="$FLAGS --approve-public-beta"; fi' in rollout['run']
    assert 'reopen' not in rollout['run']
    ci = Path('.github/workflows/ci.yml').read_text()
    assert 'tools/public_beta_policy.py release-bundle/' in ci


def test_flat_bundle_scripts_import_without_application_or_secrets(tmp_path):
    import shutil
    import subprocess
    import sys
    for name in ('deploy_production.py', 'prepare_production.py', 'backup_local.py', 'backup_production.py',
                 'verify_snapshot.py','validate_restore.py','retention_production.py','monitor_production.py',
                 'gmail_monitor_alert.py','release_manifest.py','public_beta_policy.py','release_security.py'):
        shutil.copyfile(Path('tools') / name, tmp_path / name)
    for script in ('deploy_production.py','prepare_production.py','backup_production.py',
                   'verify_snapshot.py','validate_restore.py','retention_production.py','monitor_production.py'):
        result = subprocess.run([sys.executable, str(tmp_path / script), '--help'], cwd=tmp_path,
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        if script=='validate_restore.py':
            assert '--restore-root' in result.stdout
        elif script in ('deploy_production.py','prepare_production.py'):
            assert '--approve-public-beta' in result.stdout


def test_settings_probe_returns_only_allowlisted_non_secret_effective_fields():
    from tools.public_beta_policy import SETTINGS_PROBE
    from backend.config import Settings
    # Settings is constructed with explicit fixture-only overrides, without any .env.
    # Execute the actual code after substituting only its Settings constructor binding.
    safe = Settings(_env_file=None, legacy_api_enabled=False)
    import builtins
    captured = []
    def importer(name, *args, **kwargs):
        if name == 'backend.config':
            return SimpleNamespace(Settings=lambda: safe)
        return builtins.__import__(name, *args, **kwargs)
    exec(SETTINGS_PROBE, {'__builtins__': {**vars(builtins), '__import__': importer}, 'print': captured.append})
    assert set(json.loads(captured[0])) == set(PUBLIC)


def test_operator_close_is_verified_preserves_counter_and_existing_account(beta):
    from backend.account_admin import registration_control
    from backend.account_models import PublicRegistrationQuota
    client, app, sent = beta
    token = enroll(beta)
    with app.state.sessions() as session:
        result = registration_control(session, app.state.settings, 'close', True)
        assert result['before'] == {'closed': False, 'issued_count': 1}
        assert result['closed'] is True and result['issued_count'] == 1 and result['verified']
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'closed@example.test')).status_code == 202
    assert sent.empty()
    assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 200
    assert client.post('/api/v1/auth/login', json={'email': 'alice@example.test', 'password': PASSWORD}).status_code == 200
    with app.state.sessions() as session:
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1


@pytest.mark.parametrize('action', ['close', 'reopen'])
def test_operator_mutation_is_simulated_by_default(beta, action):
    from backend.account_admin import registration_control
    client, app, sent = beta
    with app.state.sessions() as session:
        result = registration_control(session, app.state.settings, action)
        assert result['simulation'] and result['closed'] is False and result['issued_count'] == 0


def test_reopen_requires_valid_public_profile_and_preserves_counter(beta):
    from backend.account_admin import registration_control
    from backend.account_models import PublicRegistrationQuota
    client, app, sent = beta
    token = enroll(beta)
    with app.state.sessions() as session:
        registration_control(session, app.state.settings, 'close', True)
        with pytest.raises(ValueError, match='public/5'):
            registration_control(session, app.state.settings, 'reopen', True)
        assert session.get(PublicRegistrationQuota, 'public').closed is True
        app.state.settings.public_registration_limit = 5
        result = registration_control(session, app.state.settings, 'reopen', True)
        assert result['before'] == {'closed': True, 'issued_count': 1}
        assert result['closed'] is False and result['issued_count'] == 1


def test_reopening_accepts_a_legitimate_admission_before_result_read(beta, monkeypatch):
    from backend.account_admin import registration_control
    client, app, sent = beta
    app.state.settings.public_registration_limit = 5
    enroll(beta)
    with app.state.sessions() as session:
        registration_control(session, app.state.settings, 'close', True)
        commit = session.commit
        def commit_then_admit():
            commit()
            enroll(beta, 'immediately-after-reopen@example.test')
        monkeypatch.setattr(session, 'commit', commit_then_admit)
        result = registration_control(session, app.state.settings, 'reopen', True)
        assert result['before']['issued_count'] == 1
        assert result['closed'] is False and result['issued_count'] == 2 and result['verified']


@pytest.mark.parametrize('key,value', [('registration_mode', 'disabled'), ('ai_enabled', True),
    ('owner_demo_enabled', True), ('legacy_api_enabled', True)])
def test_unsafe_reopening_refused_but_emergency_closure_remains_possible(beta, key, value):
    from backend.account_admin import registration_control
    client, app, sent = beta
    app.state.settings.public_registration_limit = 5
    setattr(app.state.settings, key, value)
    with app.state.sessions() as session:
        result = registration_control(session, app.state.settings, 'close', True)
        assert result['closed']
        with pytest.raises(ValueError):
            registration_control(session, app.state.settings, 'reopen', True)


def test_five_lifetime_admissions_sixth_refused_and_no_recycled_places(beta):
    from backend.account_admin import registration_control
    from backend.account_models import PublicRegistrationQuota
    from backend.auth import User
    from backend.models import now
    from sqlalchemy import select, func
    client, app, sent = beta
    app.state.settings.public_registration_limit = 5
    # Distinct fictitious client IPs keep quota verification separate from the 5/min challenge limiter.
    for index in range(5):
        client.headers['X-Documind-Client-IP'] = f'192.0.2.{index + 1}'
        enroll(beta, f'public-{index}@example.test')
    client.headers['X-Documind-Client-IP'] = '192.0.2.6'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'sixth@example.test')).status_code == 202
    assert sent.empty()
    with app.state.sessions() as session:
        quota = session.get(PublicRegistrationQuota, 'public')
        assert quota.issued_count == 5
        assert session.scalar(select(func.count()).select_from(User).where(User.registration_kind == 'public')) == 5
        users = session.scalars(select(User)).all()
        assert all(user.email_verified_at is None and user.disabled_at is None for user in users)
        users[0].disabled_at = now()
        session.delete(users[1])
        session.commit()
        registration_control(session, app.state.settings, 'close', True)
        with pytest.raises(ValueError, match='Aucune admission'):
            registration_control(session, app.state.settings, 'reopen', True)
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 5


def test_missing_sql_gate_refuses_operator_mutation(app):
    from backend.account_admin import registration_control
    from backend.account_models import PublicRegistrationQuota
    with app.state.sessions() as session:
        session.delete(session.get(PublicRegistrationQuota, 'public'))
        session.commit()
        with pytest.raises(ValueError, match='0007'):
            registration_control(session, app.state.settings, 'close', True)


def test_cli_close_output_contains_before_after_and_no_secret(app, monkeypatch, capsys):
    from backend import account_admin
    from backend.account_models import PublicRegistrationQuota
    with app.state.sessions() as session:
        quota = session.get(PublicRegistrationQuota, 'public')
        assert quota.closed is True
        quota.closed = False
        session.commit()
    monkeypatch.setattr(account_admin, 'Settings', lambda: app.state.settings)
    monkeypatch.setattr('sys.argv', ['account_admin', 'public-registration', 'close', '--execute'])
    account_admin.main()
    raw = capsys.readouterr().out
    result = json.loads(raw)
    assert result['action'] == 'close' and result['closed'] is True and result['before']['closed'] is False
    assert result['verified'] and result['timestamp'] and result['issued_count'] == 0
    assert result['before']['issued_count'] == result['issued_count']
    assert app.state.settings.bff_service_key.get_secret_value() not in raw


def test_postgresql_close_serializes_with_last_inflight_admission(app):
    from backend.account_admin import registration_control
    from backend.account_models import PublicRegistrationQuota
    from sqlalchemy import text, update
    from threading import Event, Thread
    import time
    if app.state.engine.dialect.name != 'postgresql':
        pytest.skip('Requires a dedicated disposable PostgreSQL test database')
    with app.state.sessions() as session:
        session.execute(update(PublicRegistrationQuota).values(issued_count=4, closed=False))
        session.commit()
    entered, release_admission, closing = Event(), Event(), Event()
    results, failures, pids = [], [], []
    def admit_last_slot():
        try:
            with app.state.sessions() as session:
                granted = session.execute(text("UPDATE public_registration_quota SET issued_count=issued_count+1 "
                    "WHERE id='public' AND closed=false AND issued_count<5 RETURNING issued_count")).scalar_one()
                assert granted == 5
                entered.set()
                assert release_admission.wait(15)
                session.commit()
        except Exception as error:
            failures.append(error)
    def close_gate():
        try:
            with app.state.sessions() as session:
                session.execute(text("SET LOCAL lock_timeout='10s'"))
                pids.append(session.scalar(text('SELECT pg_backend_pid()')))
                closing.set()
                results.append(registration_control(session, app.state.settings, 'close', True))
        except Exception as error:
            failures.append(error)
    admission = Thread(target=admit_last_slot, daemon=True)
    closure = Thread(target=close_gate, daemon=True)
    admission.start()
    try:
        assert entered.wait(5)
        closure.start()
        assert closing.wait(5)
        deadline = time.monotonic() + 5
        while True:
            with app.state.sessions() as session:
                waiting = session.scalar(text('SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid'), {'pid': pids[0]})
            if waiting == 'Lock':
                break
            assert time.monotonic() < deadline, 'Closure did not acquire the expected PostgreSQL lock wait'
            time.sleep(.01)
        assert not results
    finally:
        release_admission.set()
        admission.join(15)
        if closure.ident is not None:
            closure.join(15)
    assert not admission.is_alive() and not closure.is_alive()
    assert not failures, [type(error).__name__ for error in failures]
    assert results[0]['closed'] is True and results[0]['issued_count'] == 5
    with app.state.sessions() as session:
        assert session.execute(text("UPDATE public_registration_quota SET issued_count=issued_count+1 "
            "WHERE id='public' AND closed=false AND issued_count<5 RETURNING issued_count")).scalar_one_or_none() is None
