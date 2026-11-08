import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import check_create as checks
import evaluate
import offline
import p4_control
import preservation


def plan():
    return {'purpose': 'P4_ASGI_ONLY', 'profile': 'standard', 'case': 'D03',
            'name': 'docnelo-p4-' + 'a' * 32 + '-standard-d03', 'image': 'sha256:' + 'b' * 64,
            'python': '/opt/p4-venv/bin/python', 'uid': 21101, 'gid': 21102, 'reader_gid': 21103,
            'candidate': '/opt/p4/r3', 'root': '/var/tmp/docnelo-p4-' + 'a' * 32,
            'image_env': ['PATH=/usr/bin:/bin'], 'image_review_sha256': 'c' * 64,
            'initial_ready': True, 'probes': ['closed']}


def fixture():
    p = plan()
    declared = [{'Type': 'bind', 'Source': s, 'Target': t, 'ReadOnly': ro,
                 'BindOptions': {'Propagation': 'rprivate'}} for s, t, ro in checks.mounts(p)]
    obj = {
        'Id': 'd' * 64, 'Image': p['image'], 'Name': '/' + p['name'],
        'State': {'Status': 'created', 'Running': False, 'StartedAt': '0001-01-01T00:00:00Z'},
        'Config': {'Image': p['image'], 'Labels': {checks.LABEL: 'true'},
                   'Entrypoint': [p['python']], 'Cmd': checks.cmd(p), 'User': '21101:21102',
                   'WorkingDir': '/candidate', 'Hostname': 'p4-synthetic', 'OpenStdin': True,
                   'Tty': False, 'Env': p['image_env'] + ['PYTEST_DISABLE_PLUGIN_AUTOLOAD=1'],
                   'Healthcheck': {'Test': ['NONE']}, 'StopTimeout': 15},
        'HostConfig': {
            'NetworkMode': 'none', 'PublishAllPorts': False, 'ReadonlyRootfs': True,
            'Privileged': False, 'CapDrop': ['ALL'], 'CapAdd': None,
            'SecurityOpt': ['no-new-privileges'], 'GroupAdd': ['21103'],
            'Memory': checks.MEMORY, 'MemorySwap': checks.MEMORY, 'NanoCpus': 500000000,
            'PidsLimit': 64, 'IpcMode': 'none', 'CgroupnsMode': 'private',
            'PidMode': '', 'UTSMode': '', 'UsernsMode': '',
            'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'AutoRemove': False,
            'Tmpfs': {'/tmp': checks.TMPFS},
            'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '16m', 'max-file': '1'}},
            'Mounts': declared,
        },
        'Mounts': [{'Type': 'bind', 'Source': s, 'Destination': t, 'RW': not ro,
                    'Propagation': 'rprivate'} for s, t, ro in checks.mounts(p)],
        'NetworkSettings': {'Ports': {}, 'Networks': {}},
    }
    image = {'Id': p['image'], 'Os': 'linux', 'Architecture': 'amd64',
             'Config': {'Env': p['image_env']}}
    return p, obj, image


class InspectTests(unittest.TestCase):
    def test_exact_created_configuration_and_explicit_entrypoint(self):
        p, obj, image = fixture()
        self.assertEqual(checks.inspect_created(p, obj, image, [])['container_id'], obj['Id'])
        args = checks.argv(p)
        self.assertEqual(args[2:4], ['unix:///var/run/docker.sock', 'create'])
        self.assertNotIn('start', args)
        self.assertNotIn('--publish', args)
        self.assertEqual(args[-len(checks.cmd(p)):], checks.cmd(p))

    def test_confinement_mutations_are_rejected(self):
        mutations = [
            ('State', 'Status', 'running'), ('State', 'StartedAt', '2026-11-03T08:00:00Z'),
            ('Config', 'User', '0:0'), ('Config', 'Entrypoint', ['/app/entrypoint']),
            ('Config', 'Cmd', ['-m', 'uvicorn']), ('Config', 'OpenStdin', False),
            ('Config', 'Env', ['PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', 'PYTHONPATH=/app']),
            ('Config', 'ExposedPorts', {'8000/tcp': {}}),
            ('HostConfig', 'GroupAdd', []), ('HostConfig', 'NetworkMode', 'bridge'),
            ('HostConfig', 'PortBindings', {'8000/tcp': [{'HostPort': '8000'}]}),
            ('HostConfig', 'CapDrop', []), ('HostConfig', 'Privileged', True),
            ('HostConfig', 'ReadonlyRootfs', False), ('HostConfig', 'SecurityOpt', []),
            ('HostConfig', 'Memory', 0), ('HostConfig', 'Memory', float(checks.MEMORY)),
            ('HostConfig', 'MemorySwap', -1), ('HostConfig', 'NanoCpus', 0),
            ('HostConfig', 'PidsLimit', -1), ('HostConfig', 'UsernsMode', 'host'),
            ('HostConfig', 'PidMode', 'host'), ('HostConfig', 'AutoRemove', True),
            ('HostConfig', 'VolumesFrom', ['historical']),
            ('HostConfig', 'Tmpfs', {'/tmp': checks.TMPFS, '/run': 'rw'}),
            ('HostConfig', 'Devices', [{'PathOnHost': '/dev/sda'}]),
        ]
        for area, key, value in mutations:
            with self.subTest(area=area, key=key, value=value):
                p, obj, image = fixture()
                obj[area][key] = value
                with self.assertRaises((ValueError, KeyError)):
                    checks.inspect_created(p, obj, image, [])

    def test_mount_alias_socket_and_rw_mutations(self):
        for kind in ('rw', 'wrong-source', 'socket', 'propagation', 'implicit-source', 'anonymous'):
            with self.subTest(kind=kind):
                p, obj, image = fixture()
                if kind == 'rw':
                    obj['Mounts'][1]['RW'] = True
                elif kind == 'wrong-source':
                    obj['Mounts'][1]['Source'] = '/var/tmp/historical-p3'
                elif kind == 'socket':
                    obj['Mounts'].append({'Type': 'bind', 'Source': '/var/run/docker.sock',
                                          'Destination': '/var/run/docker.sock', 'RW': True})
                elif kind == 'propagation':
                    obj['Mounts'][1]['Propagation'] = 'rshared'
                elif kind == 'implicit-source':
                    obj['HostConfig']['Mounts'][1]['BindOptions']['CreateMountpoint'] = True
                else:
                    obj['Mounts'].append({'Type': 'volume', 'Destination': '/data'})
                with self.assertRaises(ValueError):
                    checks.inspect_created(p, obj, image, [])

    def test_other_container_parent_alias_is_rejected_but_historical_namespace_is_not(self):
        p, obj, image = fixture()
        for source in (p['root'], p['root'] + '/control', '/var/tmp', '/opt/p4'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                checks.inspect_created(p, obj, image, [{'Id': 'e' * 64, 'Mounts': [{'Source': source}]}])
        checks.inspect_created(p, obj, image, [
            {'Id': 'e' * 64, 'Mounts': [{'Source': '/var/tmp/docnelo-rcd-' + 'f' * 32}]}])
        checks.inspect_created(p, obj, image, [
            {'Id': 'e' * 64, 'Mounts': [{'Source': p['candidate'] + '/lab/docker_reader.py', 'RW': False}]}])

    def test_pending_plan_and_unreviewed_image_refuse(self):
        with self.assertRaises(ValueError):
            checks.validate_plan(offline.load(ROOT / 'plan.pending.json'))
        for config in ({'Volumes': {'/app': {}}}, {'OnBuild': ['RUN curl remote']}):
            p, obj, image = fixture()
            image['Config'].update(config)
            with self.assertRaises(ValueError):
                checks.inspect_created(p, obj, image, [])


class InventoryTests(unittest.TestCase):
    def test_preservation_detects_changes_and_added_files(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = Path(folder)
            historical = repository / 'history'
            historical.mkdir()
            (historical / 'proof').write_bytes(b'frozen')
            baseline = {'scope': ['history'], 'files': {'history/proof': offline.digest(historical / 'proof')}}
            preservation.verify(repository, baseline)
            (historical / 'proof').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                preservation.verify(repository, baseline)
            (historical / 'proof').write_bytes(b'frozen')
            (historical / 'extra').write_bytes(b'extra')
            with self.assertRaises(ValueError):
                preservation.verify(repository, baseline)

    def test_exact_manifest_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            offline.write_new(root / 'one.json', {'one': 1})
            value = offline.digest(root / 'one.json')
            (root / 'SHA256SUMS').write_text(value + '  one.json\n', encoding='ascii')
            offline.manifest(root)
            with self.assertRaises(FileExistsError):
                offline.write_new(root / 'one.json', {})
            (root / 'extra').write_text('extra')
            with self.assertRaises(ValueError):
                offline.manifest(root)

    def test_path_traversal_and_duplicate_zip_members(self):
        for name in ('../escape', '/absolute', 'x\\y', 'x:y', 'a//b', './x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                offline.safe_name(name)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('../outside', b'x')
        with self.assertRaises(ValueError):
            offline.checked_zip(data.getvalue())

    def test_observed_closure_and_missing_dependency(self):
        records = offline.load(ROOT / 'DEPENDENCIES_OBSERVED.json')['distributions']
        self.assertEqual(offline.closure(records), [])
        incomplete = [r for r in records if offline.norm(r['distribution']) != 'pydantic-core']
        self.assertTrue(any('pydantic-core' in error for error in offline.closure(incomplete)))
        incompatible = copy.deepcopy(records)
        incompatible[0]['file'] = 'alembic-1.20.0-cp313-cp313-win_amd64.whl'
        self.assertTrue(any('Incompatible' in error for error in offline.closure(incompatible)))

    def test_even_filled_approval_cannot_unlock_this_proposal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'approval.json'
            inv = ROOT / 'DEPENDENCIES_OBSERVED.json'
            approval = {'inventory_sha256': offline.digest(inv), 'review_only': False,
                        'build_authorized': True}
            for key in ('base_archive', 'cpython', 'native_closure', 'wheel_provenance',
                        'bootstrap', 'recipe', 'independent_review'):
                approval[key] = {'approved': True, 'sha256': 'a' * 64}
            offline.write_new(path, approval)
            with self.assertRaisesRegex(ValueError, 'separately reviewed build revision'):
                offline.material_gate(inv, path)

    def test_historical_namespace_cannot_be_provisioned(self):
        # Prefix refusal is checked on Linux before any filesystem mutation.
        from unittest.mock import patch
        with patch.object(p4_control.sys, 'platform', 'linux'):
            with patch.object(p4_control.os, 'geteuid', return_value=0, create=True):
                for root in ('/var/tmp/docnelo-rcd-' + 'a' * 32, '/etc', '/var/tmp/docnelo-p4-../x'):
                    with self.subTest(root=root), self.assertRaises(ValueError):
                        p4_control.scope(Path(root))


def event_fixture():
    p = plan()
    startup = {'event': 'startup', 'ready_at_start': True, 'routes': 3,
               'path': '/run/documind-control/recovery-state.json',
               'workers': {'summary_recover': 1, 'index_recover': 1, 'summary_start': 1,
                           'thread_start': 1, 'cleanup_schedule': 1}}
    probe = {'event': 'probe', 'expected': 'closed', 'ready_at_start': True,
             'outcomes': {'503': 6}, 'downstream_delta': 0}
    publication = {'scope': 'P4_SYNTHETIC_ONLY', 'action': 'publish', 'kind': 'quarantined',
                   'record': {'namespace': Path(p['root']).name, 'uid': p['uid'],
                              'primary_gid': p['gid'], 'reader_gid': p['reader_gid']},
                   'before': {'control': {'device': 1, 'inode': 2}, 'latch': {'inode': 3}},
                   'after': {'control': {'device': 1, 'inode': 2},
                             'latch': {'inode': 4, 'sha256': offline.sha(b'{"format":1,"state":"quarantined"}\n'),
                                       'uid': 0, 'gid': p['reader_gid'], 'mode': '0o440', 'nlink': 1}},
                   'start_ns': 1, 'commit_return_ns': 2}
    return p, startup, probe, publication


def logs(startup, probe):
    return ('2026-11-03T08:00:00.000000001Z RCD_EVENT ' + json.dumps(startup) + '\n'
            '2026-11-03T08:00:01.000000001Z RCD_EVENT ' + json.dumps(probe) + '\n')


class EvidenceTests(unittest.TestCase):
    def test_all_standard_routes_and_valid_atomic_commit(self):
        p, startup, probe, publication = event_fixture()
        result = evaluate.event_check(p, logs(startup, probe), [publication])
        self.assertEqual(len(result), 2)

    def test_lite_403_cannot_replace_quarantine_503(self):
        p, startup, probe, publication = event_fixture()
        p['profile'] = 'beta_lite'
        startup['workers'].update(summary_recover=0, index_recover=0, summary_start=0)
        probe['outcomes'] = {'403': 2, '503': 4}
        evaluate.event_check(p, logs(startup, probe), [publication])
        probe['outcomes'] = {'403': 6}
        with self.assertRaises(ValueError):
            evaluate.event_check(p, logs(startup, probe), [publication])

    def test_bad_http_missing_probe_wrong_inode_and_false_initial_state(self):
        for kind in ('wrong-http', 'missing-probe', 'same-inode', 'startup', 'no-timestamp'):
            with self.subTest(kind=kind):
                p, startup, probe, publication = event_fixture()
                if kind == 'wrong-http':
                    probe['outcomes'] = {'403': 6}
                if kind == 'same-inode':
                    publication['after']['latch']['inode'] = 3
                if kind == 'startup':
                    startup['ready_at_start'] = False
                text = logs(startup, probe)
                if kind == 'missing-probe':
                    text = text.splitlines()[0]
                if kind == 'no-timestamp':
                    text = 'RCD_EVENT ' + json.dumps(startup)
                with self.assertRaises(ValueError):
                    evaluate.event_check(p, text, [publication])

    def test_probe_before_publication_and_missing_capture_are_not_pass(self):
        p, startup, probe, publication = event_fixture()
        before_startup = [(0, 1)]
        with self.assertRaises(ValueError):
            evaluate.event_check(p, logs(startup, probe), [publication], before_startup)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(evaluate.Incomplete):
                evaluate.receipt(Path(folder), 'wait')
            with self.assertRaises(evaluate.Incomplete):
                evaluate.evaluate(Path(folder))

    def test_interruption_and_nonzero_refusal_never_become_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture = root / 'capture'
            capture.mkdir()
            offline.write_new(capture / 'receipt.json', {'complete': False, 'returncode': None})
            with self.assertRaises(evaluate.Incomplete):
                evaluate.receipt(root, 'capture')
            (capture / 'receipt.json').unlink()
            offline.write_new(capture / 'receipt.json', {'complete': True, 'returncode': 1})
            with self.assertRaises(ValueError):
                evaluate.receipt(root, 'capture')

    def test_complete_synthetic_evidence_then_tampered_wait_command(self):
        # Fabricated fixtures test the evaluator, never constitute Docker evidence.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p, startup, probe, publication = event_fixture()
            _, obj, image = fixture()
            image_review = {'approved': True, 'native_closure_approved': True,
                            'image_id': p['image'], 'inventory_sha256': 'e' * 64}
            offline.write_new(root / 'image-review.json', image_review)
            p['image_review_sha256'] = offline.digest(root / 'image-review.json')
            for name, value in (('plan.json', p), ('created-inspect.json', [obj]),
                                ('image-inspect.json', [image]), ('others.json', [])):
                offline.write_new(root / name, value)
            inspection = checks.inspect_created(p, obj, image, [])
            inspection['inputs'] = {name: offline.digest(root / name) for name in
                                    ('plan.json', 'created-inspect.json', 'image-inspect.json', 'others.json')}
            offline.write_new(root / 'created-inspection.json', inspection)
            flags = ('transfer_anchors', 'image_approval', 'daemon_local_rootful_no_remap',
                     'all_container_ids_accounted', 'no_submounts_or_shared_propagation',
                     'host_identity_before_after_create', 'startup_before_each_action',
                     'commit_before_each_probe', 'explicit_stop_sent', 'no_session_interruption',
                     'runtime_probe_identity_limits', 'candidate_unchanged')
            offline.write_new(root / 'operator-review.json',
                              {'plan_sha256': offline.digest(root / 'plan.json'),
                               'checks': {key: True for key in flags}})
            runtime = {'verdict': 'PASS_RUNTIME_OBSERVATION_ONLY_NOT_P4', 'uid': p['uid'],
                       'gid': p['gid'], 'groups': [p['reader_gid']], 'inventory_sha256': 'e' * 64,
                       'probe_sha256': offline.digest(ROOT / 'runtime_probe.py'),
                       'helper_sha256': offline.digest(ROOT / 'offline.py')}
            offline.write_new(root / 'runtime-probe.json', runtime)
            run = root / 'container-run'
            run.mkdir()
            offline.write_new(run / 'result.json',
                              {'verdict': 'PASS_MOUNTED_ASGI_REQUIRE_ENGINE_EVIDENCE',
                               'mounted_profile': p['profile'], 'uid': p['uid'], 'gid': p['gid'],
                               'groups': [p['reader_gid']], 'collected': 1, 'outcomes': {'passed': 1},
                               'pytest_exit_code': 0, 'forbidden_io_events': []})
            offline.write_new(run / 'cases.json',
                              [{'outcome': 'passed', 'properties': {'mounted_observations': json.dumps([probe])}}])
            (run / 'junit.xml').write_text('<testsuites><testsuite><testcase/></testsuite></testsuites>')
            entries = offline.files(run)
            (run / 'SHA256SUMS').write_text(''.join(f'{v}  {n}\n' for n, v in entries.items()))
            epoch = 1793692800000000000  # 2026-11-03T08:00:00Z

            def capture(name, command, stdout, start, end):
                out = root / name
                out.mkdir()
                (out / 'stdout').write_bytes(stdout.encode('utf-8'))
                (out / 'stderr').write_bytes(b'')
                offline.write_new(out / 'receipt.json', {
                    'argv': command, 'complete': True, 'returncode': 0,
                    'start_ns': start, 'end_ns': end,
                    'sha256': {n: offline.digest(out / n) for n in ('stdout', 'stderr')}})

            docker, cid = ['docker', '--host', 'unix:///var/run/docker.sock'], obj['Id']
            capture('create', checks.argv(p), cid + '\n', epoch - 10, epoch - 9)
            capture('created-inspect', docker + ['container', 'inspect', cid],
                    (root / 'created-inspect.json').read_text(), epoch - 8, epoch - 7)
            capture('image-inspect', docker + ['image', 'inspect', p['image']],
                    (root / 'image-inspect.json').read_text(), epoch - 15, epoch - 14)
            session = ['script', '--return', '--flush', '--log-in', 'in', '--log-out', 'out',
                       '--log-timing', 'times', '--command', ' '.join(docker + ['start', '-ai', cid])]
            capture('start-session', session, '', epoch - 1, epoch + 2 * 10**9)
            capture('logs', docker + ['logs', '--timestamps', cid], logs(startup, probe),
                    epoch + 3 * 10**9, epoch + 4 * 10**9)
            capture('wait', docker + ['wait', cid], '0\n', epoch + 3 * 10**9, epoch + 4 * 10**9)
            final = copy.deepcopy(obj)
            final['State'] = {'Status': 'exited', 'ExitCode': 0, 'OOMKilled': False, 'Error': '', 'Dead': False}
            capture('final-inspect', docker + ['container', 'inspect', cid], json.dumps([final]),
                    epoch + 3 * 10**9, epoch + 4 * 10**9)
            runtime_cmd = docker + ['exec', cid, p['python'], '-I', '-B', '/opt/p4-tools/runtime_probe.py',
                                    '--inventory', '/opt/p4-materials/DEPENDENCIES_OBSERVED.json',
                                    '--out', '/evidence/runtime-probe.json']
            capture('runtime', runtime_cmd, '', epoch + 100, epoch + 200)
            publication.update(start_ns=epoch + 150000000, commit_return_ns=epoch + 200000000)
            capture('action-01', ['synthetic-action-fixture'], json.dumps(publication),
                    epoch + 100000000, epoch + 300000000)
            self.assertEqual(evaluate.evaluate(root)['verdict'], 'PASS_CASE_ONLY')
            receipt = root / 'wait' / 'receipt.json'
            changed = offline.load(receipt)
            changed['argv'] = ['echo', '0']
            receipt.unlink()
            offline.write_new(receipt, changed)
            with self.assertRaisesRegex(ValueError, 'Unexpected captured command'):
                evaluate.evaluate(root)


if __name__ == '__main__':
    unittest.main()
