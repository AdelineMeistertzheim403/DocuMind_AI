"""V5.1 policy and complete local capture, with synthetic data and no Docker/network."""
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import tarfile
from uuid import UUID

import pytest

from tests.test_snapshot_backup_integrity import _capture_directory
from tests.test_lifecycle_lot29_bundle import laboratory
from tools import backup_local, validate_restore, verify_snapshot
from tools.lifecycle_key_policy import validate_key_permissions

MODES = [(0o400, True), (0o440, True), (0o600, True), (0o640, True),
         (0o444, False), (0o644, False), (0o660, False), (0o777, False)]
NAMES = backup_local.LIFECYCLE_KEY_PATHS


def archive_bytes(mode, uid=0, gid=1000, *, duplicate=False, link=False):
    stream = io.BytesIO()
    metadata = {}
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for index, name in enumerate(NAMES):
            payload = bytes([index + 1]) * 32
            member = tarfile.TarInfo(name)
            member.mode, member.uid, member.gid, member.size = mode, uid, gid, len(payload)
            if link and index == 0:
                member.type, member.linkname, member.size = tarfile.SYMTYPE, '/outside', 0
            archive.addfile(member, io.BytesIO(payload) if member.isfile() else None)
            if duplicate and index == 0:
                archive.addfile(member, io.BytesIO(payload))
            metadata[name] = {'mode': mode, 'uid': uid, 'gid': gid, 'size': len(payload),
                              'sha256': hashlib.sha256(payload).hexdigest()}
    return stream.getvalue(), metadata


@pytest.fixture
def capture_case(laboratory, monkeypatch, tmp_path):
    reference, manifest = _capture_directory(laboratory, monkeypatch, tmp_path)
    state = {'reference': reference, 'manifest': manifest, 'mode': 0o440, 'uid': 0,
             'gid': 1000, 'destination': tmp_path / 'captured', 'calls': []}
    monkeypatch.setattr(backup_local, 'uuid4', lambda: UUID(manifest['capture_id']))
    monkeypatch.setattr(backup_local, '_compose_config', lambda *_: {
        'services': {'api': {'environment': {'RECOVERY_STATE_PATH': '/run/documind/recovery-state.json'}}}})
    monkeypatch.setattr(backup_local, '_offline_api_compose', lambda c, e: nullcontext(c))
    def quiescence(*args):
        state['calls'].append('quiescence')
        if state.get('quiescence_fail') or (state.get('post_quiescence_fail') and state['calls'].count('quiescence') == 2):
            raise ValueError('Synthetic quiescence failure')
    monkeypatch.setattr(backup_local, '_assert_quiescent', quiescence)
    def clients(*args):
        state['calls'].append('clients')
        if state.get('clients_fail'):
            raise ValueError('Synthetic uncontrolled DB client')
    monkeypatch.setattr(backup_local, '_assert_no_database_clients', clients)

    def run(argv, **kwargs):
        if '--list' in argv:
            if state.get('pg_restore_fail'):
                raise subprocess.CalledProcessError(1, argv, stderr=b'synthetic invalid dump')
            return SimpleNamespace(returncode=0)
        if any('pg_dump' in part for part in argv):
            payload = b'synthetic dump'
        elif 'backend.lifecycle_snapshot' in argv:
            payload = (reference / 'lifecycle.sqlite.tar.gz').read_bytes()
            if any(state.get(k) for k in ('sqlite_incomplete', 'sqlite_bad_capture', 'sqlite_checksum')):
                output = io.BytesIO()
                with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as old:
                    with tarfile.open(fileobj=output, mode='w:gz') as new:
                        for member in old.getmembers():
                            if state.get('sqlite_incomplete') and member.name == 'stores/holds.sqlite':
                                continue
                            content = old.extractfile(member).read()
                            if member.name == 'metadata.json':
                                meta = json.loads(content)
                                if state.get('sqlite_bad_capture'):
                                    meta['capture_id'] = 'wrong'
                                if state.get('sqlite_checksum'):
                                    meta['stores']['registry']['sha256'] = '0' * 64
                                content = json.dumps(meta).encode()
                            member.size = len(content)
                            new.addfile(member, io.BytesIO(content))
                payload = output.getvalue()
        elif NAMES[-1] in argv:
            payload, _ = archive_bytes(state['mode'], state['uid'], state['gid'],
                                       duplicate=state.get('duplicate', False), link=state.get('link', False))
        elif 'cat' in argv:
            payload = b'invalid' if state.get('latch_fail') else (reference / 'recovery-state.json').read_bytes()
        else:
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                member = tarfile.TarInfo('documents')
                member.type = tarfile.DIRTYPE
                if state.get('documents_link'):
                    member.type, member.linkname = tarfile.SYMTYPE, '/outside'
                archive.addfile(member)
            payload = stream.getvalue()
        kwargs['stdout'].write(payload)
        return SimpleNamespace(returncode=0)

    def query(argv, **kwargs):
        if state.get('sql_fail'):
            raise ValueError('Synthetic SQL failure')
        sql = argv[-1]
        if 'pg_tables' in sql:
            optional = ['chunk_embeddings', 'index_jobs', 'rag_results', 'rag_documents',
                        'ai_operation_documents', 'long_summary_jobs', 'summary_steps', 'workspaces',
                        'workspace_memberships', 'account_tokens', 'account_deletion_requests',
                        'public_registration_quota']
            if state.get('quota_missing'):
                optional.remove('public_registration_quota')
            return '\n'.join(optional)
        if 'information_schema.columns' in sql:
            return 'id\nissued_count\nclosed' if 'public_registration_quota' in sql else 'id'
        if 'alembic_version' in sql:
            return '0007'
        if state.get('database_result_invalid'):
            return 'invalid'
        return '0|d41d8cd98f00b204e9800998ecf8427e'
    monkeypatch.setattr(backup_local.subprocess, 'run', run)
    monkeypatch.setattr(backup_local.subprocess, 'check_output', query)
    return state


def capture(state):
    return backup_local.create_backup(['docker', 'compose'], state['destination'],
                                     env={}, include_lifecycle_keys=True)


@pytest.mark.parametrize('mode,accepted', MODES, ids=lambda value: oct(value) if type(value) is int else str(value))
def test_capture_permissions_and_manifest_creation(capture_case, mode, accepted):
    capture_case['mode'] = mode
    if not accepted:
        with pytest.raises(ValueError, match='permissions'):
            capture(capture_case)
        assert not (capture_case['destination'] / 'manifest.json').exists()
        assert not (capture_case['destination'] / 'integrity.json').exists()
        return
    snapshot = capture(capture_case)
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    assert len(json.loads((snapshot / 'integrity.json').read_text())) == 23
    assert manifest['backup_format_version'] == 5
    assert all(item['mode'] == mode and item['uid'] == 0 and item['gid'] == 1000
               for item in manifest['lifecycle_keys'].values())
    assert capture_case['calls'] == ['quiescence', 'clients', 'quiescence', 'clients']
    assert verify_snapshot.verify_capture(snapshot, manifest, require_s2=True)


@pytest.mark.parametrize('mode,accepted', MODES)
def test_verifier_permissions(capture_case, mode, accepted):
    snapshot = capture(capture_case)
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    payload, metadata = archive_bytes(mode)
    (snapshot / 'lifecycle-keys.tar.gz').write_bytes(payload)
    manifest['lifecycle_keys'] = metadata
    manifest['sha256']['lifecycle-keys.tar.gz'] = hashlib.sha256(payload).hexdigest()
    if accepted:
        assert verify_snapshot.verify_capture(snapshot, manifest, require_s2=True)
    else:
        with pytest.raises(SystemExit, match='Lifecycle key'):
            verify_snapshot.verify_capture(snapshot, manifest, require_s2=True)


@pytest.mark.parametrize('mode,accepted', MODES)
def test_restore_permissions_and_identity(tmp_path, mode, accepted):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    payload, metadata = archive_bytes(mode)
    (snapshot / 'lifecycle-keys.tar.gz').write_bytes(payload)
    lifecycle = tmp_path / 'lifecycle'
    lifecycle.mkdir()
    if not accepted:
        with pytest.raises(ValueError, match='permissions'):
            validate_restore._extract_lifecycle_keys(snapshot, {'lifecycle_keys': metadata}, lifecycle)
        assert not list((lifecycle / 'keys').iterdir())
        return
    validate_restore._extract_lifecycle_keys(snapshot, {'lifecycle_keys': metadata}, lifecycle)
    for index, name in enumerate(NAMES):
        path = lifecycle / name
        assert path.read_bytes() == bytes([index + 1]) * 32
        if os.name == 'posix':
            assert stat.S_IMODE(path.stat().st_mode) == 0o400
            assert path.stat().st_uid == os.geteuid()
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize('uid,gid', [(1000, 1000), (0, 0), (0, 999), (0, 1001)])
def test_group_read_requires_approved_owner(capture_case, uid, gid):
    capture_case.update(uid=uid, gid=gid)
    with pytest.raises(ValueError, match='ownership'):
        capture(capture_case)


@pytest.mark.parametrize('mode', [0o2400, 0o4440, 0o1400, 0o500, 0o460, -1, True])
def test_special_execute_or_noninteger_modes_are_never_masked(mode):
    with pytest.raises(ValueError):
        validate_key_permissions(mode, 0, 1000)


@pytest.mark.parametrize('failure', ['duplicate', 'link', 'latch_fail', 'sql_fail', 'quota_missing', 'quiescence_fail',
                                   'post_quiescence_fail', 'clients_fail', 'pg_restore_fail', 'documents_link',
                                   'sqlite_incomplete', 'sqlite_bad_capture', 'sqlite_checksum', 'database_result_invalid'])
def test_other_pre_manifest_blockers_preserve_failure(capture_case, failure):
    capture_case[failure] = True
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        capture(capture_case)
    assert not (capture_case['destination'] / 'manifest.json').exists()


def test_restore_rejects_existing_key_directory_alias(tmp_path):
    root = tmp_path / 'lifecycle'
    root.mkdir()
    (root / 'keys').mkdir()
    with pytest.raises(FileExistsError):
        validate_restore._extract_lifecycle_keys(tmp_path, {'lifecycle_keys': {n: {} for n in NAMES}}, root)


def test_posix_restore_seals_using_descriptor_and_effective_uid(monkeypatch):
    calls = []
    fake_os = SimpleNamespace(name='posix', geteuid=lambda: 1234,
        fchmod=lambda fd, mode: calls.append((fd, mode)),
        fstat=lambda fd: SimpleNamespace(st_mode=stat.S_IFREG | 0o400, st_uid=1234, st_nlink=1))
    monkeypatch.setattr(validate_restore, 'os', fake_os)
    validate_restore._seal_lab_key(42)
    assert calls == [(42, 0o400)]


def test_posix_restore_refuses_wrong_output_owner(monkeypatch):
    monkeypatch.setattr(validate_restore, 'os', SimpleNamespace(name='posix', geteuid=lambda: 1234,
        fchmod=lambda *args: None,
        fstat=lambda fd: SimpleNamespace(st_mode=stat.S_IFREG | 0o400, st_uid=0, st_nlink=1)))
    with pytest.raises(ValueError, match='Private restored'):
        validate_restore._seal_lab_key(42)
