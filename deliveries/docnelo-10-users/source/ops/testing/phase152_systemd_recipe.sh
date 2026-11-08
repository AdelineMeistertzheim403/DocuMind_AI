#!/bin/bash
# Only the local Ubuntu WSL instance. No SSH, remote host or global journal policy.
set -euo pipefail
umask 077
test "$(cat /proc/1/comm)" = systemd
workspace=/mnt/c/Users/Adeline/Documents/DocuMind_AI
evidence="$workspace/var/phase15-2-validation"
namespace=phase152-$(date +%s)
printf '%s\n' "$namespace" > "$evidence/journal-namespace.txt"
fixture=/run/documind-phase152
rootfs="$fixture/rootfs"
test ! -e "$fixture"
mkdir -m 700 "$fixture"
mkdir "$fixture/rootfs"
tar -xf "$evidence/rootfs.tar" -C "$fixture/rootfs"
rootfs="$fixture/rootfs"
mkdir -p "$rootfs/fixture" "$rootfs/srv/documind-lifecycle/venv/bin"
chmod 755 "$rootfs" "$rootfs/fixture" "$rootfs/srv" "$rootfs/srv/documind-lifecycle" "$rootfs/srv/documind-lifecycle/venv" "$rootfs/srv/documind-lifecycle/venv/bin"
ln -s /app "$rootfs/srv/documind-lifecycle/source"
ln -s /usr/local/bin/python "$rootfs/srv/documind-lifecycle/venv/bin/python"
cp "$workspace/ops/testing/systemd_recipe_payload.py" "$rootfs/app/ops/testing/"
chmod 644 "$rootfs/app/ops/testing/systemd_recipe_payload.py"
chroot "$rootfs" /usr/local/bin/python /app/ops/testing/systemd_recipe_payload.py seed
sha256sum "$rootfs/fixture/inventory.db" > "$fixture/database-before.sha256"
cat > "$fixture/inventory.env" <<'EOF'
DATABASE_URL=sqlite:////fixture/inventory.db
PENDING_REVIEW_HOURS=168
REGISTRATION_MODE=disabled
AI_ENABLED=false
EOF
mkdir -p "/run/systemd/journald@$namespace.conf.d"
chroot "$rootfs" /usr/local/bin/python /app/tools/lifecycle_logs.py --retention-days 1 --max-use-mb 16 > "/run/systemd/journald@$namespace.conf.d/policy.conf"
# Accelerated synthetic trial only; the production policy is not modified.
cat >> "/run/systemd/journald@$namespace.conf.d/policy.conf" <<'EOF'
MaxRetentionSec=2s
MaxFileSec=1s
Compress=no
RateLimitIntervalSec=0
EOF
python3 - "$workspace" "$rootfs" "$fixture" "$namespace" <<'PY'
from pathlib import Path
import sys
workspace,rootfs,fixture=map(Path,sys.argv[1:4])
namespace=sys.argv[4]
text=(workspace/'ops/systemd/documind-pending-inventory.service.example').read_text()
text=text.replace('User=documind-lifecycle','User=1000').replace('Group=documind-lifecycle','Group=1000')
text=text.replace('/etc/documind-lifecycle/inventory.env',str(fixture/'inventory.env'))
text=text.replace('documind-lifecycle-alert.service','phase152-notification.service')
text=text.replace('LogNamespace=documind-lifecycle','LogNamespace='+namespace)
text+='\nRootDirectory='+str(rootfs)+'\nRestrictAddressFamilies=AF_UNIX\n'
Path('/run/systemd/system/phase152-inventory.service').write_text(text)
timer=(workspace/'ops/systemd/documind-pending-inventory.timer.example').read_text()
timer=timer.replace('Unit=documind-pending-inventory.service','Unit=phase152-inventory.service')
timer=timer.replace('OnCalendar=*-*-* 09:30:00 Europe/Paris','OnActiveSec=2s')
Path('/run/systemd/system/phase152-inventory.timer').write_text(timer)
for name,mode in [('phase152-notification','notify'),('phase152-notification-fail','notify-fail'),('phase152-emit','emit'),('phase152-bulk','bulk')]:
    unit=f'''[Unit]
Description=Synthetic phase 15.2 only
[Service]
Type=oneshot
User=1000
Group=1000
RootDirectory={rootfs}
WorkingDirectory=/app
ExecStart=/usr/local/bin/python /app/ops/testing/systemd_recipe_payload.py {mode}
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX
LogNamespace={namespace}
'''
    Path('/run/systemd/system/'+name+'.service').write_text(unit)
PY
# Host-side verify may flag chroot-only executables as absent. Preserve that
# diagnostic; actual service execution below remains mandatory and decisive.
systemd-analyze verify /run/systemd/system/phase152-*.service /run/systemd/system/phase152-inventory.timer > "$evidence/systemd-verify.log" 2>&1 || printf 'host_verify_exit=%s\n' "$?" >> "$evidence/systemd-verify.log"
systemctl daemon-reload
systemctl start phase152-inventory.service
journalctl --namespace="$namespace" -u phase152-inventory.service --no-pager -o cat > "$evidence/systemd-inventory-success.log"
grep -q '"eligible": 1' "$evidence/systemd-inventory-success.log"
sha256sum -c "$fixture/database-before.sha256"
# A real timer activation, not only syntax validation.
systemctl start phase152-inventory.timer
sleep 4
systemctl show phase152-inventory.timer -p LastTriggerUSec -p ActiveState > "$evidence/systemd-timer.log"
grep -q 'ActiveState=active' "$evidence/systemd-timer.log"
if systemctl show phase152-nonexistent.timer -p LoadState | grep -q 'LoadState=not-found'; then
    printf 'missing_timer_detected=true\n' >> "$evidence/systemd-timer.log"
fi
systemctl stop phase152-inventory.timer
systemctl stop phase152-inventory.service
# Execution failure and the actual OnFailure dispatch to a local in-memory sink.
sed -i 's/PENDING_REVIEW_HOURS=168/PENDING_REVIEW_HOURS=24/' "$fixture/inventory.env"
if systemctl start phase152-inventory.service; then exit 30; fi
sleep 1
journalctl --namespace="$namespace" -u phase152-inventory.service -u phase152-notification.service --no-pager -o cat > "$evidence/systemd-failure-notification.log"
grep -q 'pending_inventory_failed' "$evidence/systemd-failure-notification.log"
grep -q 'synthetic_notification_sink' "$evidence/systemd-failure-notification.log"
# A separate DB availability fault, still without writing the inventory DB.
sed -i 's/PENDING_REVIEW_HOURS=24/PENDING_REVIEW_HOURS=168/;s@sqlite:////fixture/inventory.db@sqlite:////fixture/unavailable/missing.db@' "$fixture/inventory.env"
if systemctl start phase152-inventory.service; then exit 34; fi
journalctl --namespace="$namespace" -u phase152-inventory.service --no-pager -o cat > "$evidence/systemd-database-unavailable.log"
grep -q 'pending_inventory_failed' "$evidence/systemd-database-unavailable.log"
if systemctl start phase152-notification-fail.service; then exit 31; fi
journalctl --namespace="$namespace" -u phase152-notification-fail.service --no-pager -o cat > "$evidence/systemd-notification-failed.log"
grep -q notification_failed "$evidence/systemd-notification-failed.log"
if grep -E 'systemd-private@example.test|synthetic-not-used-for-auth|SYNTHETIC_PRIVATE_NOTIFICATION_ERROR' "$evidence"/systemd-*.log; then exit 32; fi
# Actual namespaced journal retention with wall-clock time (accelerated seconds).
systemctl start phase152-emit.service
sleep 1
journalctl --namespace="$namespace" -u phase152-emit.service -o cat --no-pager | grep -q PHASE152_TIME_MARKER
sleep 3
journalctl --namespace="$namespace" --rotate
if journalctl --namespace="$namespace" -u phase152-emit.service -o cat --no-pager | grep -q PHASE152_TIME_MARKER; then exit 33; fi
printf 'accelerated_calendar_expiry=true\n' > "$evidence/journald-calendar.log"
# Isolate capacity from time expiration: switch only this synthetic namespace
# back to the generated one-day retention before creating > 28 MB of log data.
sed -i 's/MaxRetentionSec=2s/MaxRetentionSec=1day/;s/MaxFileSec=1s/MaxFileSec=1day/' "/run/systemd/journald@$namespace.conf.d/policy.conf"
systemctl restart "systemd-journald@$namespace.service"
systemctl start phase152-bulk.service
journalctl --namespace="$namespace" --rotate
journalctl --namespace="$namespace" --disk-usage > "$evidence/journald-disk-usage.log"
python3 - "$namespace" "$evidence" <<'PY'
from pathlib import Path
import json,subprocess,sys
namespace,evidence=sys.argv[1],Path(sys.argv[2])
directory=Path('/var/log/journal')/(Path('/etc/machine-id').read_text().strip()+'.'+namespace)
files={p.name:p.stat().st_size for p in directory.glob('*.journal')}
active=sum(size for name,size in files.items() if '@' not in name)
archived=sum(size for name,size in files.items() if '@' in name)
lines=subprocess.check_output(['journalctl','--namespace='+namespace,'-u','phase152-bulk.service','-o','cat','--no-pager'],text=True).splitlines()
retained=sum(line.startswith('PHASE152_CAPACITY ') for line in lines)
assert 0<retained<28000,(retained,files)
assert archived<=16*1024*1024,(archived,files)
assert active+archived<=24*1024*1024,(active,archived,files)
report={'input_lines':28000,'retained_lines':retained,'active_bytes':active,'archived_bytes':archived,
        'configured_max_use_bytes':16*1024*1024,'active_segment_allowance_bytes':8*1024*1024,'files':files}
(evidence/'journald-capacity.json').write_text(json.dumps(report,indent=2,sort_keys=True))
PY
journalctl --namespace="$namespace" --verify > "$evidence/journald-verify.log" 2>&1
systemctl show "systemd-journald@$namespace.service" -p ActiveState -p FragmentPath > "$evidence/journald-service.log"
systemd-analyze cat-config "systemd/journald@$namespace.conf" > "$evidence/journald-effective-policy.log"
printf 'native_systemd_recipe_passed=true\n' > "$evidence/systemd-result.log"
# Stop our namespace only. Preserve evidence; do not vacuum any other journal.
systemctl stop phase152-inventory.timer "systemd-journald@$namespace.service" "systemd-journald@$namespace.socket"
