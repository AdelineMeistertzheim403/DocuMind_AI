"""Audit the two local Desktop images; save the R1 image, never run a container."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
DOCKER = ['docker', '--context', 'desktop-linux']
BASE = 'sha256:f15855942fb4382375648841bbcdc486fd39d252e80e8fdf8eb42999d6590019'
NEW = 'documind-public-beta-web:docnelo-r1-22b6428-v2'


def run(*args):
    return subprocess.check_output([*DOCKER, *args], text=True)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


base = json.loads(run('image', 'inspect', BASE))[0]
new = json.loads(run('image', 'inspect', NEW))[0]
assert base['Id'] == BASE
assert new['Os'] == base['Os'] == 'linux'
assert new['Architecture'] == base['Architecture'] == 'amd64'
assert new['Config'] == base['Config'], 'Runtime image configuration changed'
assert not base['Config'].get('Volumes'), 'Unexpected declared volumes'
base_layers = base['RootFS']['Layers']
assert new['RootFS']['Layers'][:len(base_layers)] == base_layers
payload = ROOT / 'payload'
payload.mkdir(exist_ok=True)
reference = ROOT / 'reference-runtime'
if (reference / 'server').exists():
    raise RuntimeError('Reference extraction already exists; preserve this sealed delivery and use a fresh evidence directory')
archive_path = payload / 'web-image.tar'
subprocess.run([*DOCKER, 'save', '--output', str(archive_path), NEW], check=True)
checked = []
parent_metadata = []
with tarfile.open(archive_path, 'r') as archive:
    manifests = json.load(archive.extractfile('manifest.json'))
    assert len(manifests) == 1
    base_directories = {}
    for layer in manifests[0]['Layers'][:len(base_layers)]:
        with tarfile.open(fileobj=archive.extractfile(layer), mode='r|*') as stream:
            for member in stream:
                name = member.name.removeprefix('./').rstrip('/')
                if member.isdir() and name in {'app', 'etc'}:
                    base_directories[name] = {'mode':member.mode, 'uid':member.uid,
                                             'gid':member.gid, 'mtime':member.mtime}
    for layer in manifests[0]['Layers'][len(base_layers):]:
        with tarfile.open(fileobj=archive.extractfile(layer), mode='r|*') as stream:
            for member in stream:
                name = member.name.removeprefix('./').rstrip('/')
                assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
                if name in {'app', 'etc'} and member.isdir():
                    before = base_directories[name]
                    assert (member.mode, member.uid, member.gid) == (before['mode'], before['uid'], before['gid'])
                    parent_metadata.append({'path':name, 'mode_uid_gid_unchanged':True,
                                            'mtime_before':before['mtime'], 'mtime_after':member.mtime})
                else:
                    assert (name.startswith('app/dist/') or name in {'app/dist', 'app/.wh.dist'}
                            or name in {'', '.'} and member.isdir()), 'Unexpected changed path: ' + name
                checked.append(name)

reference.mkdir(exist_ok=True)
container = run('create', '--network', 'none', BASE).strip()
assert re.fullmatch('[a-f0-9]{64}', container)
try:
    run('cp', container + ':/app/server', str(reference / 'server'))
    run('cp', container + ':/app/package.json', str(reference / 'package.json'))
    run('cp', container + ':/app/package-lock.json', str(reference / 'package-lock.json'))
finally:
    run('rm', container)  # Only the just-created, never-started inspection container.
source = ROOT / 'source' / 'frontend'
matches = []
for path in sorted(reference.rglob('*')):
    if path.is_file():
        relative = path.relative_to(reference)
        assert path.read_bytes() == (source / relative).read_bytes(), str(relative)
        matches.append({'path':relative.as_posix(), 'sha256':digest(path)})
commit = subprocess.check_output(['git', '-c', 'safe.directory=' + (ROOT / 'source').as_posix(),
                                  '-C', str(ROOT / 'source'), 'rev-parse', 'HEAD'], text=True).strip()
report = {'status':'passed', 'source_commit':commit, 'reference_image_id':BASE,
          'new_image_id':new['Id'], 'new_image_tag':NEW, 'architecture':'linux/amd64',
          'runtime_config_identical':True, 'base_layers_preserved':len(base_layers),
          'additional_layers':len(new['RootFS']['Layers']) - len(base_layers),
          'changed_layer_paths':checked, 'runtime_source_files_identical':matches,
          'parent_directory_metadata':parent_metadata,
          'archive_sha256':digest(archive_path), 'archive_bytes':archive_path.stat().st_size,
          'active_vps_image_id':None}
(ROOT / 'image-proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','source_commit','new_image_id',
    'runtime_config_identical','base_layers_preserved','additional_layers','archive_bytes','archive_sha256')}))
