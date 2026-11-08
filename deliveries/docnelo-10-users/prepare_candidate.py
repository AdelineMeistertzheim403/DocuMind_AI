"""Separate local hypothesis for the named exported API release; not VPS attestation."""
import hashlib
import json
from pathlib import Path
import shutil

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
EXPORT = ROOT / 'exports/public-beta-candidate-20261030T234818Z'
DEST = LAB / 'candidate-source'
assert not DEST.exists()
shutil.copytree(LAB / 'source', DEST)
entries = []
for origin in sorted((EXPORT / 'backend').rglob('*.py')):
    assert not origin.is_symlink()
    relative = origin.relative_to(EXPORT)
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    shutil.copyfile(origin, target)
    digest = hashlib.sha256(origin.read_bytes()).hexdigest()
    entries.append({'path': relative.as_posix(), 'sha256': digest, 'r2_sha256': previous, 'different': digest != previous})
(LAB / 'candidate-api-inventory.json').write_text(json.dumps({'export': str(EXPORT.relative_to(ROOT)),
    'active_api_attested': False, 'files': entries}, indent=2), encoding='utf-8')
print(json.dumps({'api_files':len(entries), 'different_from_r2':sum(e['different'] for e in entries)}))
