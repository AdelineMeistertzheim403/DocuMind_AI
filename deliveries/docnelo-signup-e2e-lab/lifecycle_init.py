import os
import secrets
import pwd
from pathlib import Path

from backend.lifecycle_admissions import AdmissionAnchor
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry

app = pwd.getpwnam('app')
app_uid, app_gid = app.pw_uid, app.pw_gid

root = Path(os.environ['LIFECYCLE_DATA_ROOT'])
lock_path = Path(os.environ['LIFECYCLE_BACKUP_LOCK_PATH'])

registry = Path(os.environ['LIFECYCLE_REGISTRY_PATH'])
witness = Path(os.environ['LIFECYCLE_CONFIRMATION_PATH'])
auth_path = Path(os.environ['LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH'])
holds = Path(os.environ['LIFECYCLE_HOLDS_PATH'])
anchor = Path(os.environ['LIFECYCLE_ADMISSION_ANCHOR_PATH'])

store_paths = [registry, witness, auth_path, holds, anchor]

def chmod(path: Path, mode: int) -> None:
  os.chmod(path, mode, follow_symlinks=False)

def chown(path: Path, uid: int, gid: int) -> None:
  os.chown(path, uid, gid, follow_symlinks=False)

def stat_owner(path: Path):
  st = os.stat(path, follow_symlinks=False)
  return st.st_uid, st.st_gid, st.st_mode & 0o777

def ensure_dir(path: Path, *, uid: int, gid: int, mode: int) -> None:
  path.mkdir(parents=True, exist_ok=True)
  if path.is_symlink():
    raise ValueError(f"Unsafe lifecycle directory: {path}")
  current_uid, current_gid, _ = stat_owner(path)
  if (current_uid, current_gid) != (uid, gid):
    chown(path, uid, gid)
  chmod(path, mode)

def ensure_file_owner(path: Path, *, uid: int, gid: int, mode: int, allow_root_fixup: bool) -> None:
  if not path.exists():
    return
  if path.is_symlink():
    raise ValueError(f"Unsafe lifecycle file: {path}")
  current_uid, current_gid, _ = stat_owner(path)
  if (current_uid, current_gid) == (uid, gid):
    chmod(path, mode)
    return
  if allow_root_fixup and current_uid == 0:
    # Fix a partial provisioning that created stores as root.
    chown(path, uid, gid)
    chmod(path, mode)
    return
  raise ValueError(f"Owner mismatch for {path}: {current_uid}:{current_gid} (expected {uid}:{gid})")

print(f"[lifecycle-init] pre ids uid={os.getuid()} gid={os.getgid()}")

# Privileged step: create dirs and keys, and (idempotently) fix wrong root-owned stores/lock.
ensure_dir(root, uid=app_uid, gid=app_gid, mode=0o700)
# Migrate legacy store locations (flat files under /app/lifecycle) into separate directories.
# This preserves store bytes (rename) and enables backend.lifecycle_snapshot invariants.
legacy_map = {
  root/'registry.sqlite': registry,
  root/'confirmation.sqlite': witness,
  root/'authenticated-confirmation.sqlite': auth_path,
  root/'holds.sqlite': holds,
  root/'admission-anchor.sqlite': anchor,
}

for legacy, current in legacy_map.items():
  if legacy.exists() and not current.exists():
    ensure_dir(current.parent, uid=app_uid, gid=app_gid, mode=0o700)
    os.rename(legacy, current)

for p in store_paths:
  ensure_dir(p.parent, uid=app_uid, gid=app_gid, mode=0o700)
  ensure_file_owner(p, uid=app_uid, gid=app_gid, mode=0o600, allow_root_fixup=True)

ensure_dir(lock_path.parent, uid=app_uid, gid=app_gid, mode=0o700)
ensure_file_owner(lock_path, uid=app_uid, gid=app_gid, mode=0o600, allow_root_fixup=True)

keys_dir = Path(os.environ['LIFECYCLE_AUTHENTICATION_KEY_PATH']).parent
ensure_dir(keys_dir, uid=0, gid=app_gid, mode=0o750)

def ensure_key(path: Path) -> None:
  if path.exists():
    # Preserve existing keys; only enforce the expected perms.
    ensure_file_owner(path, uid=0, gid=app_gid, mode=0o440, allow_root_fixup=False)
    return
  fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
  try:
    os.write(fd, secrets.token_bytes(32))
  finally:
    os.close(fd)
  chown(path, 0, app_gid)
  chmod(path, 0o440)

ensure_key(Path(os.environ['LIFECYCLE_AUTHENTICATION_KEY_PATH']))
ensure_key(Path(os.environ['LIFECYCLE_ADMISSION_KEY_PATH']))

# Drop privileges: all SQLite stores MUST be created/initialized as `app`.
try:
  os.setgroups([app_gid])
except Exception:
  pass
os.setgid(app_gid)
os.setuid(app_uid)
os.umask(0o077)

print(f"[lifecycle-init] post ids uid={os.getuid()} gid={os.getgid()}")

# Idempotent initialization: never overwrite existing stores.
if not registry.exists():
  Registry(registry).initialize()
if not witness.exists():
  ConfirmationStore(witness).initialize()

auth = AuthenticatedConfirmationStore(
  auth_path,
  Path(os.environ['LIFECYCLE_AUTHENTICATION_KEY_PATH']).read_bytes(),
  os.environ.get('LIFECYCLE_AUTHENTICATED_NAMESPACE', 'documind-public-beta'),
)
if not auth_path.exists():
  auth.initialize()

if not holds.exists():
  HoldStore(holds, auth).initialize()

if not anchor.exists():
  AdmissionAnchor(anchor, Path(os.environ['LIFECYCLE_ADMISSION_KEY_PATH']).read_bytes()).initialize()

# Ensure lock exists and is owned by `app` (no chmod/chown possible after setuid).
if not lock_path.exists():
  fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
  os.close(fd)
current_uid, current_gid, _ = stat_owner(lock_path)
if (current_uid, current_gid) != (app_uid, app_gid):
  raise ValueError(f"Lock owner mismatch for {lock_path}: {current_uid}:{current_gid} (expected {app_uid}:{app_gid})")
chmod(lock_path, 0o600)

# Final verification: owners must match effective uid.
for p in store_paths:
  puid, pgid, pmode = stat_owner(p)
  duid, dgid, dmode = stat_owner(p.parent)
  print(f"[lifecycle-init] {p} file={puid}:{pgid} {oct(pmode)} dir={duid}:{dgid} {oct(dmode)}")
  if puid != app_uid or duid != app_uid:
    raise ValueError(f"Owner mismatch after init: {p}")
