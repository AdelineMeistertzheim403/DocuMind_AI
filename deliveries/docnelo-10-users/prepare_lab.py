"""Copy only canonical tracked R2 sources; preserve all existing worktrees."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LAB = Path(__file__).resolve().parent
BASE = ROOT / 'deliveries/docnelo-web-branding-r2/source'
TARGET = LAB / 'source'
assert not TARGET.exists(), 'Never overwrite an existing lab'
names = subprocess.check_output(['git', '-c', f'safe.directory={BASE.as_posix()}', '-C', str(BASE), 'ls-files', '-z']).decode().split('\0')
inventory = []
for name in filter(None, names):
    if name.startswith('.env') or '/.env' in name:
        continue
    origin = BASE / name
    if not origin.is_file() or origin.is_symlink():
        continue
    destination = TARGET / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin, destination)
    inventory.append({'path': name, 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest()})
(LAB / 'source-inventory.json').write_text(json.dumps({'source_commit': 'b046e5d8256d45b65bf575a8a006351616b69fc9', 'files': inventory}, indent=2), encoding='utf-8')
print(f'Copied {len(inventory)} tracked source files; no env files or worktree changes')
