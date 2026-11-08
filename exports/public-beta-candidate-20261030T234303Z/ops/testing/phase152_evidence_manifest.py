"""Index local synthetic evidence; never reads environment/secrets or a remote host."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'var/phase15-2-validation'


def docker(*args):
    return subprocess.check_output(['docker','--context','desktop-linux',*args],text=True).strip()


def main():
    cases={};runs=[]
    for name in ('linux-postgresql.xml','linux-packaging-retest.xml','linux-additional.xml','linux-sandbox.xml'):
        tree=ET.parse(EVIDENCE/name)
        totals={'passed':0,'failed':0,'skipped':0}
        for case in tree.iter('testcase'):
            status=('failed' if case.find('failure') is not None or case.find('error') is not None else
                    'skipped' if case.find('skipped') is not None else 'passed')
            cases[case.get('classname')+'::'+case.get('name')]=status
            totals[status]+=1
        runs.append({'file':name,**totals})
    assert set(cases.values())=={'passed'}
    replay=json.loads((EVIDENCE/'recovery-replayed.json').read_text())
    assert replay['real_database_restore'] and replay['registration_closed'] and replay['counter_after']==3
    assert 'native_systemd_recipe_passed=true' in (EVIDENCE/'systemd-result.log').read_text()
    assert 'accelerated_calendar_expiry=true' in (EVIDENCE/'journald-calendar.log').read_text()
    for path in EVIDENCE.glob('systemd-*.log'):
        data=path.read_text()
        for forbidden in ('systemd-private@example.test','synthetic-not-used-for-auth','SYNTHETIC_PRIVATE_NOTIFICATION_ERROR'):
            assert forbidden not in data,path.name
    files={}
    for path in sorted(EVIDENCE.iterdir()):
        if path.is_file() and path.name!='evidence-manifest.json':
            with path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            files[path.name]={'sha256':checksum,'bytes':path.stat().st_size}
    sources={}
    for folder in ('backend','tools'):
        for path in sorted((ROOT/folder).rglob('*.py')):
            sources[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    report={'synthetic_only':True,'test_runs':runs,'distinct_tests_after_retest':len(cases),
            'persistent_test_failures':0,'skipped_selected_tests':0,
            'proofs_image':docker('image','inspect','documind-phase152-proofs:local','--format','{{.Id}}'),
            'postgres_image':docker('image','inspect','documind-s14-8-postgres:local','--format','{{.Id}}'),
            'source_database_state':docker('exec','phase152-db','psql','-U','phase152','-d','documind_recovery_source','-At',
                '-c',"SELECT issued_count,closed FROM public_registration_quota WHERE id='public'"),
            'restored_database_state':docker('exec','phase152-db','psql','-U','phase152','-d','documind_restore_phase152','-At',
                '-c',"SELECT issued_count,closed FROM public_registration_quota WHERE id='public'"),
            'files':files,'application_source_sha256':sources}
    (EVIDENCE/'evidence-manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:report[key] for key in ('distinct_tests_after_retest','persistent_test_failures','skipped_selected_tests')},sort_keys=True))


if __name__=='__main__':main()
