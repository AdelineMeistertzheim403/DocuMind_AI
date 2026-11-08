"""Hash reviewable reports, harness and evidence; exclude private runtime assets."""
import ast
import hashlib
import json
from pathlib import Path

LAB=Path(__file__).resolve().parent
ROOT=LAB.parents[1]
reports=[ROOT/('DOCNELO_SIGNUP_E2E_LAB_'+name+'.md') for name in ['ARCHITECTURE','RUNBOOK','TEST_REPORT','SECURITY_REPORT']]
evidence=[LAB/name for name in ['archive-proof.json','test-results.json','smtp-proof.json',
    'restart-proof.json','post-restart-proof.json','loopback-proof.json','runtime-isolation-final.json',
    'safety-preflight-final.json','final-state.json','worktree-status.txt']]
scripts=sorted(LAB.glob('*.py'))
for file in scripts:ast.parse(file.read_text(encoding='utf-8'),filename=str(file))
proof=json.loads((LAB/'test-results.json').read_text())
assert len(proof['tests'])==26 and all(t['status']=='PASS' for t in proof['tests'])
assert json.loads((LAB/'final-state.json').read_text())['containers_stopped']
assert not (LAB/'worktree-status.txt').read_text().strip()
records=[]
for file in reports+evidence+scripts:
    records.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(ROOT).as_posix())
(LAB/'EVIDENCE_SHA256SUMS').write_text('\n'.join(records)+'\n',encoding='utf-8')
print(json.dumps(dict(reports_verified=len(reports),main_probe_checks=26,script_syntax_checked=len(scripts),
    verdict=proof['verdict'],evidence_files_hashed=len(records))))
