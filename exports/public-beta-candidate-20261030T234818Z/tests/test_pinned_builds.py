"""Build-input boundaries; no external requests, Docker or production secrets."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.error import HTTPError

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tools.fetch_build_materials import acquire, download, manifest_materials, unique_object, verify_source


def manifest():
    return json.loads(Path('build-materials/pgvector.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('change', ['origin', 'credentials', 'query', 'path', 'hash', 'size', 'duplicate', 'target', 'commit'])
def test_build_manifest_rejects_unreviewed_inputs(change):
    data = manifest()
    row = data['apk'][0]
    if change == 'origin': row['url'] = row['url'].replace('dl-cdn.alpinelinux.org', 'example.test')
    elif change == 'credentials': row['url'] = row['url'].replace('https://', 'https://private:secret@')
    elif change == 'query': row['url'] += '?token=private'
    elif change == 'path': row['filename'] = '../outside.apk'
    elif change == 'hash': row['sha256'] = 'bad'
    elif change == 'size': row['size'] = True
    elif change == 'duplicate': data['apk'].append(copy.deepcopy(row))
    elif change == 'target': data['target'] = 'linux-arm64'
    elif change == 'commit': data['source']['commit'] = 'main'
    with pytest.raises(ValueError): manifest_materials(data)


def test_duplicate_json_fields_are_not_last_value_wins():
    with pytest.raises(ValueError, match='duplicate'):
        json.loads('{"format": "one", "format": "two"}', object_pairs_hook=unique_object)


@pytest.mark.parametrize('failure', ['hash', 'short', 'oversize', 'redirect'])
def test_failed_download_never_leaves_an_accepted_file_or_partial(tmp_path, failure):
    data = b'reviewed-build-material'
    row = {'url': 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/fake.apk',
           'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    class Opener:
        def open(self, *args, **kwargs):
            if failure == 'redirect':
                raise HTTPError(row['url'], 302, 'redirect', {}, None)
            return io.BytesIO(data[:-1] if failure == 'short' else data + b'x' if failure == 'oversize' else b'x' * len(data))
    with pytest.raises((ValueError, HTTPError)):
        download(row, tmp_path / 'material.apk', Opener())
    assert list(tmp_path.iterdir()) == []


def test_existing_output_is_not_overwritten(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    marker = output / 'keep'
    marker.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        acquire(Path('build-materials/pgvector.json'), output)
    assert marker.read_bytes() == b'preserve'


@pytest.mark.parametrize('kind', ['symlink', 'traversal', 'version'])
def test_source_archive_does_not_bypass_path_or_version_review(tmp_path, kind):
    source = manifest()['source']
    prefix = 'pgvector-' + source['commit']
    path = tmp_path / 'source.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        name = prefix + '/../outside' if kind == 'traversal' else prefix + '/link' if kind == 'symlink' else prefix + '/vector.control'
        info = tarfile.TarInfo(name)
        if kind == 'symlink':
            info.type = tarfile.SYMTYPE
            info.linkname = '/private'
            archive.addfile(info)
        else:
            content = b"default_version = '0.0.0'\n"
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with pytest.raises(ValueError): verify_source(path, source)


def hashed_lock(name):
    result = {}
    for line in Path(name).read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'): continue
        requirement, digest = line.split(' --hash=sha256:')
        parsed = Requirement(requirement)
        specs = list(parsed.specifier)
        assert len(specs) == 1 and specs[0].operator == '=='
        assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
        key = canonicalize_name(parsed.name)
        assert key not in result
        result[key] = specs[0].version
    return result


def test_image_closures_keep_functional_versions_and_separate_test_tools():
    runtime = hashed_lock('requirements.runtime.lock')
    extra = hashed_lock('requirements.test.lock')
    build = hashed_lock('requirements.build.lock')
    assert len(runtime) == 44
    assert set(extra) == {'cryptography', 'iniconfig', 'packaging', 'pluggy', 'pygments', 'pytest'}
    assert not runtime.keys() & extra.keys()
    assert set(build) == {'pip', 'setuptools', 'wheel', 'packaging'}
    pins = {}
    for line in Path('requirements.lock').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'): continue
        requirement = Requirement(line)
        if not requirement.marker or requirement.marker.evaluate({'sys_platform': 'linux'}):
            pins[canonicalize_name(requirement.name)] = list(requirement.specifier)[0].version
    assert all(pins[name] == version for name, version in (runtime | extra).items())
    assert 'pytest' not in runtime and 'setuptools' not in runtime


def test_compiler_manifest_is_complete_without_private_index_or_git():
    data = manifest()
    assert len(manifest_materials(data)) == 20
    assert len(data['apk']) == 19
    assert not any(p['filename'].startswith('git-') for p in data['apk'])
    dockerfile = Path('Dockerfile.db').read_text(encoding='utf-8')
    assert '--repositories-file /dev/null' in dockerfile
    assert 'apk --network=no verify' in dockerfile
    assert dockerfile.count('OPTFLAGS="" with_llvm=no') == 2
    assert 'git clone' not in dockerfile and '--allow-untrusted' not in dockerfile


def test_new_build_inputs_are_in_runner_material_inventory(capsys):
    from tools.build_materials import main
    assert main([]) == 0
    data = json.loads(capsys.readouterr().out)
    for name in ('requirements.runtime.lock', 'requirements.build.lock', 'requirements.test.lock',
                 'build-materials/pgvector.json', 'tools/fetch_build_materials.py'):
        assert data['source_sha256'][name] == hashlib.sha256(Path(name).read_bytes()).hexdigest()


def test_ci_waits_for_final_postgresql_tcp_server():
    import yaml
    workflow = yaml.load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    start = next(step['run'] for step in workflow['jobs']['python']['steps']
                 if 'pg_isready' in step.get('run', ''))
    assert 'pg_isready -h 127.0.0.1' in start
    assert 'seq 1 60' in start  # Preserve the existing bounded readiness wait.
