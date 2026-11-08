"""Capture and verify the explicitly non-v3 PostgreSQL/documents transition archive."""
import hashlib
import json
import re
import tarfile
import types
from pathlib import Path, PurePosixPath


SOURCE_RELEASE_COMMIT = '9b26006a2f8cfa3185580de66c671d419ad24dd6'
SOURCE_HELPER_GIT_BLOB = '06e7275465da146ac1b032905d3f237f40af0d45'
SOURCE_HELPER_SHA256 = '0ae5025a1fb259e39ba0d3259e187ddfff92e54ecf2afd391b389664d35b4ad7'
SOURCE_COMPOSE_GIT_BLOB = 'ae264448cecfa39fa2acb62fe900955ceb6136ff'
SOURCE_COMPOSE_SHA256 = 'c754e2759b2d7a9d20653a79ede94884e59e70f3b6cdedfd8952746787be2bf5'
PAYLOAD_FILES = {'database.dump', 'documents.tar.gz', 'integrity.json', 'manifest.json'}
HISTORICAL_MANIFEST = 'historical_manifest.json'
HISTORICAL_HELPER_SOURCE = Path(__file__).with_name('historical_pre_v3_backup_source.txt')
QUOTA_COLUMNS = {'id', 'issued_count', 'closed'}
REQUIRED_TABLES = {'users', 'account_deletion_requests', 'public_registration_quota'}


def _sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _normalized_source(path):
    source = Path(path).read_bytes().replace(b'\r\n', b'\n')
    if b'\r' in source:
        raise ValueError('Historical source uses unsupported newline encoding')
    return source


def _require_regular_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Expected a regular, non-symlink file: {path.name}')


def _load_historical_helper(path):
    path = Path(path)
    _require_regular_file(path)
    source = _normalized_source(path)
    digest = hashlib.sha256(source).hexdigest()
    blob = hashlib.sha1(
        b'blob ' + str(len(source)).encode('ascii') + b'\0' + source
    ).hexdigest()
    if digest != SOURCE_HELPER_SHA256 or blob != SOURCE_HELPER_GIT_BLOB:
        raise ValueError('Historical backup helper provenance mismatch')
    module = types.ModuleType('documind_historical_backup_helper')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    if not callable(getattr(module, 'create_backup', None)):
        raise ValueError('Historical helper has no compatible create_backup function')
    return module


def _validate_compose_source(path, compose):
    path = Path(path)
    _require_regular_file(path)
    if hashlib.sha256(_normalized_source(path)).hexdigest() != SOURCE_COMPOSE_SHA256:
        raise ValueError('Historical Compose source provenance mismatch')
    arguments = list(compose)
    files = [Path(arguments[index + 1]) for index, value in enumerate(arguments[:-1])
             if value in ('-f', '--file')]
    if len(files) != 1 or files[0].resolve() != path.resolve():
        raise ValueError('Capture must use exactly the pinned historical Compose file')
    project_indices = [index for index, value in enumerate(arguments[:-1]) if value == '-p']
    if (len(project_indices) != 1 or arguments[project_indices[0] + 1] != 'documind-prod'
            or '--project-directory' not in arguments):
        raise ValueError('Capture must use the historical production Compose project')


def _validate_legacy_manifest(directory):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest.get('files')
    checksums = manifest.get('sha256')
    if (manifest.get('migration') != '0007'
            or manifest.get('database_major') != 17
            or manifest.get('integrity_version') != 2
            or not isinstance(files, list)
            or any(not isinstance(name, str) for name in files)
            or set(files) != {'database.dump', 'documents.tar.gz'}
            or not isinstance(checksums, dict)
            or set(checksums) != {'database.dump', 'documents.tar.gz'}):
        raise ValueError('Historical helper manifest is incomplete or not schema 0007')
    for name in ('database.dump', 'documents.tar.gz'):
        expected = checksums[name]
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError(f'Invalid historical helper checksum: {name}')
        if _sha256(directory / name) != expected:
            raise ValueError(f'Historical helper checksum mismatch: {name}')

    with (directory / 'database.dump').open('rb') as source:
        if source.read(5) != b'PGDMP':
            raise ValueError('Historical database dump is not a PostgreSQL custom archive')

    integrity = json.loads((directory / 'integrity.json').read_text(encoding='utf-8'))
    if not isinstance(integrity, dict) or not REQUIRED_TABLES.issubset(integrity):
        raise ValueError('Historical table inventory lacks required schema 0007 tables')
    for table, entry in integrity.items():
        if (not isinstance(entry, dict) or type(entry.get('count')) is not int
                or entry['count'] < 0
                or not isinstance(entry.get('digest'), str)
                or not re.fullmatch(r'[0-9a-f]{32}', entry['digest'])
                or not isinstance(entry.get('columns'), list)
                or not entry['columns']
                or any(not isinstance(column, str) for column in entry['columns'])
                or len(entry['columns']) != len(set(entry['columns']))):
            raise ValueError(f'Invalid historical integrity entry: {table}')
    if set(integrity['public_registration_quota']['columns']) != QUOTA_COLUMNS:
        raise ValueError('Historical public quota schema is incomplete')
    if 'registration_kind' not in integrity['users']['columns']:
        raise ValueError('Historical users table lacks the legacy/public discriminator')

    seen = set()
    with tarfile.open(directory / 'documents.tar.gz', 'r:gz') as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if (member.name in seen or path.is_absolute() or '..' in path.parts
                    or member.issym() or member.islnk()
                    or not (member.isfile() or member.isdir())):
                raise ValueError('Unsafe or ambiguous historical documents archive')
            seen.add(member.name)
    return manifest


def _seal_capture(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Historical capture directory is not a real directory')
    names = {path.name for path in directory.iterdir()}
    if names != PAYLOAD_FILES:
        raise ValueError('Historical capture has missing or unrecognized files')
    for name in PAYLOAD_FILES:
        _require_regular_file(directory / name)
    legacy = _validate_legacy_manifest(directory)
    hashes = {name: _sha256(directory / name) for name in sorted(PAYLOAD_FILES)}
    manifest = {
        'format': 'documind-historical-pre-v3',
        'format_version': 1,
        'capture_kind': 'historical_pre_v3',
        'source_release_commit': SOURCE_RELEASE_COMMIT,
        'source_release_identification': 'reported reference; runtime image identity not independently attested',
        'source_helper_git_blob': SOURCE_HELPER_GIT_BLOB,
        'source_helper_sha256': SOURCE_HELPER_SHA256,
        'source_compose_git_blob': SOURCE_COMPOSE_GIT_BLOB,
        'source_compose_sha256': SOURCE_COMPOSE_SHA256,
        'source_schema_revision': legacy['migration'],
        'source_database_major': legacy['database_major'],
        'files': sorted(PAYLOAD_FILES),
        'sha256': hashes,
        'capture_scope': ['postgresql', 'documents'],
        'lifecycle_stores_included': False,
        'lifecycle_history_absence_proven': False,
        'database_content_integrity_verified': False,
        'v3_complete': False,
    }
    manifest_path = directory / HISTORICAL_MANIFEST
    with manifest_path.open('x', encoding='utf-8') as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write('\n')
    return manifest


def capture_historical_pre_v3(compose, compose_file, destination, env=None):
    """Run only the pinned legacy helper, then bind its four-file output to a non-v3 manifest."""
    compose_file = Path(compose_file)
    helper = _load_historical_helper(HISTORICAL_HELPER_SOURCE)
    _validate_compose_source(compose_file, compose)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Refusing to overwrite an existing historical capture')
    helper.create_backup(list(compose), destination, env)
    _seal_capture(destination)
    return destination


def verify_historical_pre_v3(directory):
    """Verify a historical archive's exact file set, provenance declarations and hashes."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Historical archive directory is not a real directory')
    expected_names = PAYLOAD_FILES | {HISTORICAL_MANIFEST}
    if {path.name for path in directory.iterdir()} != expected_names:
        raise ValueError('Historical archive has missing or unrecognized files')
    for name in expected_names:
        _require_regular_file(directory / name)
    manifest = json.loads((directory / HISTORICAL_MANIFEST).read_text(encoding='utf-8'))
    if (manifest.get('format') != 'documind-historical-pre-v3'
            or manifest.get('format_version') != 1
            or manifest.get('capture_kind') != 'historical_pre_v3'
            or manifest.get('source_release_commit') != SOURCE_RELEASE_COMMIT
            or manifest.get('source_helper_git_blob') != SOURCE_HELPER_GIT_BLOB
            or manifest.get('source_helper_sha256') != SOURCE_HELPER_SHA256
            or manifest.get('source_compose_git_blob') != SOURCE_COMPOSE_GIT_BLOB
            or manifest.get('source_compose_sha256') != SOURCE_COMPOSE_SHA256
            or manifest.get('source_schema_revision') != '0007'
            or manifest.get('source_database_major') != 17
            or manifest.get('files') != sorted(PAYLOAD_FILES)
            or manifest.get('capture_scope') != ['postgresql', 'documents']
            or manifest.get('lifecycle_stores_included') is not False
            or manifest.get('lifecycle_history_absence_proven') is not False
            or manifest.get('database_content_integrity_verified') is not False
            or manifest.get('v3_complete') is not False
            or not isinstance(manifest.get('sha256'), dict)
            or set(manifest['sha256']) != PAYLOAD_FILES):
        raise ValueError('Invalid historical_pre_v3 manifest or scope declaration')
    for name in PAYLOAD_FILES:
        digest = manifest['sha256'][name]
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError(f'Invalid historical archive checksum: {name}')
        if _sha256(directory / name) != digest:
            raise ValueError(f'Historical archive checksum mismatch: {name}')
    _validate_legacy_manifest(directory)
    return manifest
