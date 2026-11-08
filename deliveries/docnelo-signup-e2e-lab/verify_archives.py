"""Read private Docker saves without extracting application files or changing tags."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
API = '4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d'
WEB = 'ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362'
records = []
for name, archive, expected, archive_expected in (
    ('api', ROOT/'deliveries/docnelo-10-users/api-active.tar', API, None),
    ('web', ROOT/'deliveries/docnelo-web-branding-r2/payload/web-r2.tar', WEB,
     'de8f742edd34bf0182e746916376599686fcd7d5a176e43cdf0979caa32fc54b'),
):
    with archive.open('rb') as stream:
        archive_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if archive_expected:
        assert archive_hash == archive_expected
    with tarfile.open(archive) as saved:
        manifest = json.load(saved.extractfile('manifest.json'))
        assert len(manifest) == 1
        entry = manifest[0]
        raw = saved.extractfile(entry['Config']).read()
        config = json.loads(raw)
        assert hashlib.sha256(raw).hexdigest() == expected
        assert config['os'] == 'linux' and config['architecture'] == 'amd64'
        layer_hashes = []
        for layer in entry['Layers']:
            layer_hashes.append('sha256:' + hashlib.file_digest(saved.extractfile(layer), 'sha256').hexdigest())
        assert layer_hashes == config['rootfs']['diff_ids']
        records.append(dict(image=name, archive=str(archive.relative_to(ROOT)),
            archive_sha256=archive_hash, archive_hash_prior_reference=archive_expected,
            image_id='sha256:'+expected, platform='linux/amd64', layers_verified=len(layer_hashes),
            provenance='local private archive; image ID supplied by user' if name=='api' else 'local R2 RELEASE.json',
            historical_build_commit_attested=False))
        if name == 'api':
            target = LAB/'api-untagged.tar'
            assert not target.exists(), 'Refuse to replace private derived archive'
            entry['RepoTags'] = []
            # Retain only the Docker save manifest/config/layers. No OCI tag metadata.
            selected = set(entry['Layers']) | {entry['Config']}
            with tarfile.open(target, 'w') as output:
                for member in saved.getmembers():
                    if member.name in selected:
                        output.addfile(member, saved.extractfile(member))
                raw_manifest = json.dumps(manifest).encode()
                info = tarfile.TarInfo('manifest.json'); info.size=len(raw_manifest)
                output.addfile(info, io.BytesIO(raw_manifest))
(LAB/'archive-proof.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')
print(json.dumps(records, indent=2))
