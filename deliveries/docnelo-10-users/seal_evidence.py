"""Seal local diagnostic evidence; never create a deployment artifact or contact VPS."""
import ast
import hashlib
import json
from pathlib import Path

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
R2 = ROOT / 'deliveries/docnelo-web-branding-r2'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

source = json.loads((LAB / 'source-inventory.json').read_text())
for row in source['files']:
    assert sha(R2 / 'source' / row['path']) == row['sha256'], 'Existing R2 changed'
    assert sha(LAB / 'source' / row['path']) == row['sha256'], 'Lab application changed'
candidate = json.loads((LAB / 'candidate-api-inventory.json').read_text())
for row in candidate['files']:
    assert sha(ROOT / candidate['export'] / row['path']) == row['sha256'], 'Existing export changed'
    assert sha(LAB / 'candidate-source' / row['path']) == row['sha256'], 'Candidate application changed'
for line in (R2 / 'payload/SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert sha(R2 / 'payload' / name) == digest, 'Existing R2 delivery changed'
summary = {
    'verdict': 'NO-GO_OPENING', 'deployment_performed': False, 'vps_access_performed': False,
    'runtime_changes_applied': False, 'active_api_attested': False,
    'r2_source_files_unchanged': len(source['files']), 'candidate_source_files_unchanged': len(candidate['files']),
    'r2_payload_integrity_verified': True, 'strict_lifecycle_ten_qualified': False,
    'postgres_test_image': 'sha256:d2e0a72a9da278610fc926cc8d125827c0069f33feaafa011aae890572ec95c3',
    'tests_image': 'sha256:526917bd27ecc837a7b683c0ca396fcdf315dde81c879100bffda874a3abeb1d',
    'final_results': {
        'git_r2_api': {'passed':188, 'failed':0, 'errors':0, 'skipped':0},
        'candidate_api': {'passed_call_phases':188, 'failed_assertions':0, 'teardown_errors':10, 'exit_code':1},
        'new_process_restart_git_r2': {'passed':1, 'failed':0},
        'new_process_restart_candidate': {'passed':1, 'failed':0},
        'bff_r2': {'passed':50, 'failed':0, 'skipped':0},
    },
    'earlier_restart_harness_attempts': {'setup_error_fixed':1, 'masked_synthetic_key_failure_fixed':1},
    'safety': {'network':'new internal Docker networks', 'database':'fresh PostgreSQL 17 tmpfs',
               'real_data_used':False, 'existing_volumes_touched':False},
}
for name, status in [('result.json',0),('candidate-result.json',1),('restart-result.json',0),('candidate-restart-result.json',0)]:
    assert json.loads((LAB / name).read_text())['exit_code'] == status
assert '188 passed' in (LAB / 'pytest.log').read_text(encoding='utf-8')
assert '188 passed, 2 warnings, 10 errors' in (LAB / 'candidate-pytest.log').read_text(encoding='utf-8')
assert '# pass 50' in (LAB / 'bff-tests.log').read_text(encoding='utf-16')
(LAB / 'qualification-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
documents = sorted(ROOT.glob('DOCNELO_PUBLIC_BETA_10_USERS_*.md'))
assert len(documents) == 5
scripts = list(LAB.glob('*.py')) + list((LAB / 'source/tests').glob('test_ten_users*.py'))
for script in scripts:
    ast.parse(script.read_text(encoding='utf-8'), feature_version=(3,11))
for document in documents:
    text = document.read_text(encoding='utf-8')
    assert text.count('```') % 2 == 0
    assert 'NO-GO' in text
    assert not any(line.rstrip() != line for line in text.splitlines())
files = documents + scripts + list(LAB.glob('*.json')) + list(LAB.glob('*.log'))
lines = [f'{sha(path)}  {path.relative_to(ROOT).as_posix()}\n' for path in sorted(files)]
(LAB / 'SHA256SUMS').write_text(''.join(lines), encoding='ascii', newline='\n')
print(json.dumps({'reports':len(documents), 'evidence_files':len(files),
    'r2_source_files_preserved':len(source['files']), 'candidate_files_preserved':len(candidate['files']),
    'sha256sums':sha(LAB / 'SHA256SUMS'), 'verdict':'NO-GO_OPENING'}))
