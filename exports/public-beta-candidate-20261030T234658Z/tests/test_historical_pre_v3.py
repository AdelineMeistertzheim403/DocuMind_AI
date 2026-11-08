import hashlib
import json
import tarfile

import pytest

from tools import historical_pre_v3 as historical


def _synthetic_legacy_capture(directory):
    directory.mkdir(mode=0o700)
    (directory / 'database.dump').write_bytes(b'PGDMP synthetic-only')
    with tarfile.open(directory / 'documents.tar.gz', 'w:gz') as archive:
        info = tarfile.TarInfo('documents/')
        info.type = tarfile.DIRTYPE
        archive.addfile(info)
    empty_digest = hashlib.md5(b'').hexdigest()
    integrity = {
        'users': {'count': 0, 'digest': empty_digest, 'columns': ['id', 'registration_kind']},
        'account_deletion_requests': {
            'count': 0, 'digest': empty_digest,
            'columns': ['id', 'user_id', 'owner_id', 'status', 'created_at'],
        },
        'public_registration_quota': {
            'count': 1, 'digest': empty_digest, 'columns': ['id', 'issued_count', 'closed'],
        },
    }
    (directory / 'integrity.json').write_text(json.dumps(integrity), encoding='utf-8')
    checksums = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in ('database.dump', 'documents.tar.gz')
    }
    (directory / 'manifest.json').write_text(json.dumps({
        'created_at': '2026-10-27T00:00:00+00:00',
        'database_major': 17,
        'migration': '0007',
        'integrity_version': 2,
        'files': ['database.dump', 'documents.tar.gz'],
        'sha256': checksums,
    }), encoding='utf-8')
    return directory


def test_historical_capture_is_verifiable_and_explicitly_not_v3(tmp_path):
    snapshot = tmp_path / 'historical'
    _synthetic_legacy_capture(snapshot)
    manifest = historical._seal_capture(snapshot)

    verified = historical.verify_historical_pre_v3(snapshot)

    assert verified == manifest
    assert verified['capture_kind'] == 'historical_pre_v3'
    assert verified['capture_scope'] == ['postgresql', 'documents']
    assert verified['lifecycle_stores_included'] is False
    assert verified['lifecycle_history_absence_proven'] is False
    assert verified['database_content_integrity_verified'] is False
    assert verified['v3_complete'] is False


def test_historical_capture_is_rejected_as_s2_and_on_tamper_or_extra_files(tmp_path):
    snapshot = tmp_path / 'historical'
    _synthetic_legacy_capture(snapshot)
    historical._seal_capture(snapshot)
    legacy = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
    from tools.verify_snapshot import verify_capture

    with pytest.raises(SystemExit, match='Legacy snapshot lacks'):
        verify_capture(snapshot, legacy, require_s2=True)

    (snapshot / 'database.dump').write_bytes(b'PGDMP modified')
    with pytest.raises(ValueError, match='checksum mismatch'):
        historical.verify_historical_pre_v3(snapshot)

    (snapshot / 'database.dump').write_bytes(b'PGDMP synthetic-only')
    (snapshot / 'unattested.sqlite').write_bytes(b'not lifecycle evidence')
    with pytest.raises(ValueError, match='unrecognized files'):
        historical.verify_historical_pre_v3(snapshot)


def test_historical_capture_refuses_missing_or_ambiguous_evidence(tmp_path):
    missing = tmp_path / 'missing'
    _synthetic_legacy_capture(missing)
    historical._seal_capture(missing)
    integrity_path = missing / 'integrity.json'
    integrity = json.loads(integrity_path.read_text(encoding='utf-8'))
    del integrity['account_deletion_requests']
    integrity_path.write_text(json.dumps(integrity), encoding='utf-8')
    outer_path = missing / 'historical_manifest.json'
    outer = json.loads(outer_path.read_text(encoding='utf-8'))
    outer['sha256']['integrity.json'] = hashlib.sha256(integrity_path.read_bytes()).hexdigest()
    outer_path.write_text(json.dumps(outer), encoding='utf-8')
    with pytest.raises(ValueError, match='lacks required'):
        historical.verify_historical_pre_v3(missing)

    contradictory = tmp_path / 'contradictory'
    _synthetic_legacy_capture(contradictory)
    historical._seal_capture(contradictory)
    manifest_path = contradictory / 'historical_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['v3_complete'] = True
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='manifest or scope'):
        historical.verify_historical_pre_v3(contradictory)


def test_historical_helper_copy_matches_pinned_git_provenance():
    module = historical._load_historical_helper(historical.HISTORICAL_HELPER_SOURCE)
    assert callable(module.create_backup)


def test_historical_compose_provenance_rejects_unpinned_source(tmp_path):

    compose_file = tmp_path / 'compose.production.yaml'
    compose_file.write_text('services: {}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Compose source provenance'):
        historical._validate_compose_source(compose_file, [
            'docker', 'compose', '--project-directory', str(tmp_path),
            '-p', 'documind-prod', '-f', str(compose_file),
        ])


def test_capture_uses_pinned_helper_and_refuses_to_overwrite(tmp_path, monkeypatch):
    class Helper:
        @staticmethod
        def create_backup(compose, destination, env):
            assert compose == ['synthetic-compose']
            assert env == {'SYNTHETIC_ONLY': '1'}
            _synthetic_legacy_capture(destination)

    monkeypatch.setattr(historical, '_load_historical_helper', lambda _: Helper)
    monkeypatch.setattr(historical, '_validate_compose_source', lambda *_: None)
    destination = tmp_path / 'capture'
    result = historical.capture_historical_pre_v3(
        ['synthetic-compose'], tmp_path / 'compose.yaml',
        destination, {'SYNTHETIC_ONLY': '1'},
    )
    assert result == destination
    assert historical.verify_historical_pre_v3(destination)['v3_complete'] is False
    with pytest.raises(ValueError, match='overwrite'):
        historical.capture_historical_pre_v3(
            ['synthetic-compose'], tmp_path / 'compose.yaml',
            destination, {'SYNTHETIC_ONLY': '1'},
        )
