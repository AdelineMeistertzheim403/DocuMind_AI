param(
  [string]$EnvFile = "ops/public_beta/lab/lab.env",
  [string]$ComposeFile = "compose.public-beta.vps.yaml"
)
$ErrorActionPreference = "Stop"

function Assert-Ok($msg) { if ($LASTEXITCODE -ne 0) { throw $msg } }

function Inspect-Lifecycle($volumeName, $label) {
  Write-Host "`n== Inspect $label ($volumeName) =="
  docker run --rm -v "$volumeName`:/mnt" --entrypoint sh documind-s14-6-api:local -lc "set -e; echo '--- find'; find /mnt -maxdepth 3 -print; echo '--- stat'; find /mnt -maxdepth 3 -exec stat -c '%a %u:%g %n' {} \; | sort"
  Assert-Ok "inspect failed"
}

function Hash-FileInVolume($volumeName, $pathInVolume) {
  docker run --rm -u 0:0 -v "$volumeName`:/mnt" --entrypoint sh documind-s14-6-api:local -lc "set -e; test -e /mnt/$pathInVolume; sha256sum /mnt/$pathInVolume"
  Assert-Ok "hash failed: $pathInVolume"
}

# Scenario A: fresh volume
$projA = "pubbeta-lab-fresh"
Write-Host "`n### Scenario A: fresh volume ($projA)"

$env:PUBLIC_BETA_ENV_FILE=$EnvFile; docker compose --env-file $EnvFile -p $projA -f $ComposeFile up -d db
Assert-Ok "compose up db failed"

$env:PUBLIC_BETA_ENV_FILE=$EnvFile; docker compose --env-file $EnvFile -p $projA -f $ComposeFile run --rm lifecycle-init
Assert-Ok "lifecycle-init failed"

$volA = "${projA}_public_beta_lifecycle"
Inspect-Lifecycle $volA "fresh-after"

# Scenario B: partial init reproducing VPS state
$projB = "pubbeta-lab-partial"
Write-Host "`n### Scenario B: partial init ($projB)"

$env:PUBLIC_BETA_ENV_FILE=$EnvFile; docker compose --env-file $EnvFile -p $projB -f $ComposeFile up -d db
Assert-Ok "compose up db failed"

$volB = "${projB}_public_beta_lifecycle"

# Create broken state matching VPS diagnosis:
# - /app/lifecycle owned by app (1000:1000)
# - legacy flat stores exist but owned by root (0:0)
# - lock exists but owned by root (0:0)
# - keys root:app 0440
# We create valid stores as app first, then chown them to root.

# Step 1: create stores + lock as app, with /app/lifecycle private and owned by app.
docker run --rm -u 1000:1000 -v "$volB`:/app/lifecycle" --entrypoint sh documind-s14-6-api:local -lc "set -e; python - <<'PY'
import os
from pathlib import Path
from backend.lifecycle_registry import Registry
from backend.lifecycle_durability import ConfirmationStore

root = Path('/app/lifecycle')
root.mkdir(parents=True, exist_ok=True)
os.chmod(root, 0o700)

registry = root/'registry.sqlite'
confirmation = root/'confirmation.sqlite'

if not registry.exists():
  Registry(registry).initialize()
if not confirmation.exists():
  ConfirmationStore(confirmation).initialize()

lock = root/'.backup.lock'
if not lock.exists():
  fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
  os.close(fd)
PY"
Assert-Ok "creating partial state (app phase) failed"

# Step 2: chown legacy stores + lock to root; ensure keys are root:app 0440.
docker run --rm -u 0:0 -v "$volB`:/app/lifecycle" --entrypoint sh documind-s14-6-api:local -lc "set -e; python - <<'PY'
import os, pwd
from pathlib import Path

app = pwd.getpwnam('app')
app_uid, app_gid = app.pw_uid, app.pw_gid

root = Path('/app/lifecycle')
root.mkdir(parents=True, exist_ok=True)

# Ensure directory matches VPS: owned by app and private.
os.chown(root, app_uid, app_gid)
os.chmod(root, 0o700)

for name in ('registry.sqlite','confirmation.sqlite','.backup.lock'):
  p = root/name
  if p.exists():
    os.chown(p, 0, 0)

# Create keys as root (root:app 0440)
keys = root/'keys'
keys.mkdir(exist_ok=True)
os.chown(keys, 0, app_gid)
os.chmod(keys, 0o750)
for name in ('authentication.key','admission.key'):
  p = keys/name
  if not p.exists():
    fd = os.open(p, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    os.write(fd, b'x'*32)
    os.close(fd)
  os.chown(p, 0, app_gid)
  os.chmod(p, 0o440)
PY"
Assert-Ok "creating partial state (root phase) failed"

Inspect-Lifecycle $volB "partial-before"

$beforeRegistry = Hash-FileInVolume $volB "registry.sqlite"
$beforeConfirmation = Hash-FileInVolume $volB "confirmation.sqlite"

$env:PUBLIC_BETA_ENV_FILE=$EnvFile; docker compose --env-file $EnvFile -p $projB -f $ComposeFile run --rm lifecycle-init
Assert-Ok "lifecycle-init failed"

Inspect-Lifecycle $volB "partial-after"

$afterRegistry = Hash-FileInVolume $volB "registry/registry.sqlite"
$afterConfirmation = Hash-FileInVolume $volB "confirmation/confirmation.sqlite"

Write-Host "`n== Hash compare (should match for migrated stores) =="
Write-Host "BEFORE registry:"; $beforeRegistry
Write-Host "AFTER  registry:";  $afterRegistry
Write-Host "BEFORE confirmation:"; $beforeConfirmation
Write-Host "AFTER  confirmation:";  $afterConfirmation

Write-Host "`nOK"