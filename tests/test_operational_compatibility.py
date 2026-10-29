import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import deploy_production as deploy, retention_production as retention
from tests.test_retention import make_daily, NOW
from tests.test_retention import inventory
from tests.test_production_backups import run_backup


def mount_config(tmp_path):
    root = tmp_path / 'vps'; root.mkdir()
    latch = tmp_path / 'latch.json'; latch.write_text('{"format":1,"state":"quarantined"}')
    return SimpleNamespace(root=root), {'volumes': {
        'production_documents': {'name': 'documind-prod_production_documents'},
        'production_lifecycle': {'name': 'documind-prod_production_lifecycle'}}, 'services': {'api': {'volumes': [
        {'type':'volume','source':'production_documents','target':'/app/var'},
        {'type':'volume','source':'production_lifecycle','target':'/app/lifecycle'},
        {'type':'bind','source':str(latch),'target':'/run/documind/recovery-state.json','read_only':True}]}}}


def test_three_approved_compose_mounts_are_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy,'run',lambda *_:str(tmp_path/'docker-data'))
    stack, config = mount_config(tmp_path)
    deploy.validate_recovery_control_config(stack, config)
    assert stack.recovery_control_path == tmp_path / 'latch.json'


@pytest.mark.parametrize('change', ['latch_missing','latch_writable','lifecycle_missing','lifecycle_target',
    'documents_replaced','extra','latch_in_root','latch_in_volume','anonymous_lifecycle','lifecycle_bind'])
def test_invalid_mount_topology_fails_closed(tmp_path, monkeypatch, change):
    monkeypatch.setattr(deploy,'run',lambda *_:str(tmp_path/'docker-data'))
    stack, config = mount_config(tmp_path)
    mounts = config['services']['api']['volumes']
    if change == 'latch_missing': mounts.pop(2)
    elif change == 'latch_writable': mounts[2]['read_only'] = False
    elif change == 'lifecycle_missing': mounts.pop(1)
    elif change == 'lifecycle_target': mounts[1]['target'] = '/wrong'
    elif change == 'documents_replaced': mounts[0]['source'] = 'other'
    elif change == 'extra': mounts.append({'type':'volume','source':'extra','target':'/extra'})
    elif change == 'anonymous_lifecycle': mounts[1].pop('source')
    elif change == 'lifecycle_bind': mounts[1]['type'] = 'bind'
    elif change in ('latch_in_root','latch_in_volume'):
        base = stack.root if change == 'latch_in_root' else tmp_path / 'docker-volume'
        base.mkdir(exist_ok=True); latch = base / 'latch.json'; latch.write_text('{}')
        mounts[2]['source'] = str(latch)
        if change == 'latch_in_volume':
            monkeypatch.setattr(deploy, 'run', lambda *_: str(base))
    with pytest.raises(deploy.DeploymentError): deploy.validate_recovery_control_config(stack, config)


def test_complete_v3_archive_is_accepted(tmp_path):
    row, files = make_daily(0)
    directory = tmp_path / row['tags'][1]; directory.mkdir()
    for name, data in files.items(): (directory / name).write_bytes(data)
    result = retention.local_archive(directory, tmp_path, '0006', NOW)
    assert set(result['hashes']) == set(files)
    assert result['classification'] == 'v3-complete'
    from tools.verify_snapshot import verify_capture
    assert verify_capture(directory,json.loads(files['manifest.json']),require_s2=True) is True


@pytest.mark.parametrize('change', ['missing_lifecycle','hash','manifest','integrity_hash','store_set','unknown_version'])
def test_v3_tampering_is_refused(tmp_path, change):
    row, files = make_daily(0)
    manifest = json.loads(files['manifest.json'])
    if change == 'missing_lifecycle': del files['lifecycle.sqlite.tar.gz']
    elif change == 'hash': files['lifecycle.sqlite.tar.gz'] += b'changed'
    elif change == 'manifest': manifest['s2_recovery_authorized'] = True
    elif change == 'integrity_hash': files['integrity.json'] += b' '
    elif change == 'store_set': manifest['lifecycle_stores'].pop('holds')
    elif change == 'unknown_version': manifest['backup_format_version'] = 4
    files['manifest.json'] = json.dumps(manifest).encode()
    directory = tmp_path / row['tags'][1]; directory.mkdir()
    for name, data in files.items(): (directory / name).write_bytes(data)
    with pytest.raises(retention.RetentionError): retention.local_archive(directory,tmp_path,'0006',NOW)


@pytest.mark.parametrize('version', [1,2])
def test_legacy_archives_remain_legacy_and_bytes_unchanged(tmp_path, version):
    row, files = make_daily(0, version)
    directory = tmp_path / row['tags'][1]; directory.mkdir()
    for name, data in files.items(): (directory / name).write_bytes(data)
    result = retention.local_archive(directory,tmp_path,'0006',NOW)
    assert result['classification'] == 'legacy-preserved'
    assert {p.name:p.read_bytes() for p in directory.iterdir()} == files


def test_backup_measurements_use_verified_offline_compose(run_backup):
    from tools import backup_production as backup
    root,events,state=run_backup
    backup.execute(root,{})
    sizes=[event[1] for event in events if event[0]=='offline-size']
    assert len(sizes)==2
    assert {argv[-1] for argv in sizes}=={'/app/var/documents','/app/lifecycle'}
    assert all('--network' not in argv and 'synthetic-offline.yaml' in argv for argv in sizes)


def test_old_helper_cannot_fall_back_to_networked_measurement(run_backup,monkeypatch):
    from tools import backup_production as backup
    root,events,state=run_backup
    monkeypatch.setattr(backup,'load_helper',lambda *_:SimpleNamespace())
    with pytest.raises(AttributeError): backup.execute(root,{})
    assert ('restart',) in events
    assert not any(event[0] in ('offline-size','snapshot') for event in events)


@pytest.mark.parametrize('version', [1,2])
def test_mixed_inventory_never_proposes_legacy_archives(inventory,version):
    root,repo,rows,days=inventory
    row,files=make_daily(12,version); days[12]=(row,files)
    directory=root/'var/backups'/row['tags'][1]
    (directory/'lifecycle.sqlite.tar.gz').unlink()  # Only this test's synthetic fixture.
    for name,data in files.items():(directory/name).write_bytes(data)
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    plan=retention.build_plan(root,repo,'0006',NOW)
    assert plan['status']=='simulated'
    assert row['id'] not in {item['snapshot'] for item in plan['remote']['would_remove']}
    assert row['tags'][1] not in {item['name'] for item in plan['local']['would_remove']}
    assert any(item['reason']=='legacy-format-preserved' for item in plan['local']['excluded'])
    assert any(item['reasons']==['legacy-format-preserved'] for item in plan['remote']['keep'])
    assert before=={p.name:p.read_bytes() for p in directory.iterdir()}


def test_legacy_schema_is_review_required_not_corruption(tmp_path):
    row,files=make_daily(0,2)
    manifest=json.loads(files['manifest.json']); manifest['migration']='0005'
    with pytest.raises(retention.RetentionError,match='^historical_schema_review_required$'):
        retention.validate_metadata(manifest,json.loads(files['integrity.json']),'0006',NOW-3600,NOW)
