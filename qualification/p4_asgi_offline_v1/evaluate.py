"""Offline evidence evaluator. A case PASS is not a P4 or production authorization."""
import argparse
import calendar
import json
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_create import argv, inspect_created, validate_plan
from matrix import cases
from offline import digest, load, require, sha, write_new
from p4_control import KINDS


class Incomplete(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Incomplete(message)


def receipt(root, name, expected_argv=None):
    folder = root / name
    need((folder / 'receipt.json').is_file(), 'Missing capture: ' + name)
    item = load(folder / 'receipt.json')
    need(item['complete'] is True and type(item['returncode']) is int, 'Interrupted capture: ' + name)
    require(item['returncode'] == 0, 'Nonzero capture: ' + name)
    require(item['sha256'] == {n: digest(folder / n) for n in ('stdout', 'stderr')},
            'Capture changed: ' + name)
    require(item['end_ns'] >= item['start_ns'], 'Wall clock moved backwards')
    if expected_argv is not None:
        require(item['argv'] == expected_argv, 'Unexpected captured command: ' + name)
    return item, folder / 'stdout'


def event_check(plan, text, published, action_times=None):
    events, times = [], []
    for line in text.splitlines():
        match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\.(\d{1,9})Z RCD_EVENT (.+)', line)
        if match:
            stamp, fraction, value = match.groups()
            times.append(calendar.timegm(time.strptime(stamp, '%Y-%m-%dT%H:%M:%S')) * 10**9
                         + int(fraction.ljust(9, '0')))
            events.append(json.loads(value))
        else:
            require('RCD_EVENT ' not in line, 'Malformed/untimestamped RCD event')
    need(events and events[0]['event'] == 'startup', 'Startup event absent')
    startup = events[0]
    require(startup['ready_at_start'] is plan['initial_ready'], 'Startup state mismatch')
    require(type(startup['routes']) is int and startup['routes'] > 0
            and startup['path'] == '/run/documind-control/recovery-state.json', 'Startup route/path')
    workers = startup['workers']
    if not plan['initial_ready']:
        require(not any(workers.values()), 'Workers started while quarantined')
    else:
        require(workers == {'summary_recover': int(plan['profile'] == 'standard'),
                            'index_recover': int(plan['profile'] == 'standard'),
                            'summary_start': int(plan['profile'] == 'standard'),
                            'thread_start': 1, 'cleanup_schedule': 1}, 'Positive worker spies')
    need(len(events) >= 1 + len(plan['probes']), 'Missing probe events')
    require(len(events) == 1 + len(plan['probes']), 'Extra probe events')
    expected_initial, steps = cases()[plan['case']]
    require(plan['initial_ready'] is expected_initial
            and plan['probes'] == [s[2] for s in steps], 'Plan deviates from frozen matrix')
    need(len(published) == len(steps), 'Missing action receipts')
    if action_times is not None:
        require(len(action_times) == len(steps), 'Action times missing')
        for index, (start, end) in enumerate(action_times):
            require(times[index] < start <= end < times[index + 1],
                    'Required startup/previous probe -> commit -> next probe ordering not proved')
    for event, expected, publication, step in zip(events[1:], plan['probes'], published, steps):
        require(event['event'] == 'probe' and event['expected'] == expected
                and event['ready_at_start'] is plan['initial_ready'], 'Probe order/state mismatch')
        outcomes = event['outcomes']
        require(all(type(v) is int and v > 0 for v in outcomes.values()), 'HTTP outcome counts')
        if expected == 'sentinel':
            require(outcomes == {'500-synthetic-tripwire': 1} and event['downstream_delta'] == 1,
                    'Positive sentinel must be reached exactly once')
        else:
            keys = {'503'} if plan['profile'] == 'standard' else {'503', '403'}
            require(set(outcomes) == keys and sum(outcomes.values()) == 2 * startup['routes']
                    and event['downstream_delta'] == 0, '503/403 coverage or downstream mismatch')
        action, value, _ = step
        require(publication['scope'] == 'P4_SYNTHETIC_ONLY' and publication['action'] == action,
                'Wrong publication action')
        require(publication['record']['namespace'] == Path(plan['root']).name, 'Wrong synthetic namespace')
        require(publication['record']['uid'] == plan['uid']
                and publication['record']['primary_gid'] == plan['gid']
                and publication['record']['reader_gid'] == plan['reader_gid'], 'Publication identity')
        before, after = publication['before'], publication['after']
        require((before['control']['device'], before['control']['inode']) ==
                (after['control']['device'], after['control']['inode']), 'Control directory inode changed')
        require(publication['commit_return_ns'] >= publication['start_ns'], 'Commit timestamps')
        if action == 'publish':
            payload = (b'{"format":1,"state":"quarantined"}\n'
                       if value == 'quarantined' else KINDS[value])
            require(publication['kind'] == value and after['latch']['sha256'] == sha(payload),
                    'Published payload hash')
            require(before['latch']['inode'] != after['latch']['inode'], 'No atomic inode replacement')
            require(after['latch']['uid'] == 0 and after['latch']['gid'] == plan['reader_gid']
                    and after['latch']['mode'] == '0o440' and after['latch']['nlink'] == 1,
                    'Published latch metadata')
        elif action == 'remove':
            require(after['latch'] == {'exists': False}, 'Child not absent')
        elif action == 'symlink':
            require(after['latch']['type'] == 0o120000, 'Synthetic symlink not observed')
        elif action == 'mode':
            obj, mode = value.split(':')
            key = 'control' if obj == 'directory' else 'latch'
            require(publication['object'] == obj and publication['mode'] == mode
                    and after[key]['mode'] == oct(int(mode, 8))
                    and before[key]['inode'] == after[key]['inode'], 'Mode/inode change mismatch')
    return events


def evaluate(root):
    need((root / 'plan.json').is_file(), 'Missing plan')
    plan = load(root / 'plan.json')
    validate_plan(plan)
    need(plan['case'] in cases(), 'Case not in bounded P4 matrix')
    review_file = root / 'operator-review.json'
    need(review_file.is_file(), 'Missing independent operator review')
    review = load(review_file)
    required_checks = {'transfer_anchors', 'image_approval', 'daemon_local_rootful_no_remap',
                       'all_container_ids_accounted', 'no_submounts_or_shared_propagation',
                       'host_identity_before_after_create', 'startup_before_each_action',
                       'commit_before_each_probe', 'explicit_stop_sent', 'no_session_interruption',
                       'runtime_probe_identity_limits', 'candidate_unchanged'}
    need(set(review.get('checks', {})) == required_checks
         and all(value is True for value in review['checks'].values()), 'Operator checks incomplete')
    require(review.get('plan_sha256') == digest(root / 'plan.json'), 'Operator review binding')
    image_review = load(root / 'image-review.json')
    require(digest(root / 'image-review.json') == plan['image_review_sha256']
            and image_review['approved'] is True and image_review['image_id'] == plan['image']
            and image_review['native_closure_approved'] is True, 'Image review is missing/unapproved')
    inspection = load(root / 'created-inspection.json')
    require(inspection['verdict'] == 'PASS_CREATED_INSPECTION_ONLY'
            and inspection['inputs'] == {n: digest(root / n) for n in
                                        ('plan.json', 'created-inspect.json', 'image-inspect.json', 'others.json')},
            'Missing created-only inspection binding')
    rerun = inspect_created(plan, load(root / 'created-inspect.json')[0],
                            load(root / 'image-inspect.json')[0], load(root / 'others.json'))
    require(rerun['container_id'] == inspection['container_id'], 'Created inspection differs')
    docker = ['docker', '--host', 'unix:///var/run/docker.sock']
    cid = inspection['container_id']
    create_capture, create_stdout = receipt(root, 'create', argv(plan))
    require(create_stdout.read_text().strip() == cid, 'Create returned another container ID')
    created_capture, created_stdout = receipt(root, 'created-inspect',
                                             docker + ['container', 'inspect', cid])
    require(digest(created_stdout) == digest(root / 'created-inspect.json'), 'Created JSON copy changed')
    _, image_stdout = receipt(root, 'image-inspect', docker + ['image', 'inspect', plan['image']])
    require(digest(image_stdout) == digest(root / 'image-inspect.json'), 'Image JSON copy changed')
    session_receipt, _ = receipt(root, 'start-session')
    session_argv = session_receipt['argv']
    require(session_argv[0] == 'script' and session_argv.count('--command') == 1
            and session_argv[-2:] == ['--command', ' '.join(docker + ['start', '-ai', cid])]
            and all(flag in session_argv for flag in
                    ('--return', '--flush', '--log-in', '--log-out', '--log-timing')),
            'Start target/session differs')
    require(create_capture['end_ns'] <= created_capture['start_ns'] <=
            created_capture['end_ns'] <= session_receipt['start_ns'], 'Create/inspect/start order')
    _, log_path = receipt(root, 'logs', docker + ['logs', '--timestamps', cid])
    wait_receipt, wait_stdout = receipt(root, 'wait', docker + ['wait', cid])
    require(wait_stdout.read_text().strip() == '0', 'Docker wait exit status is not zero')
    _, final_stdout = receipt(root, 'final-inspect', docker + ['container', 'inspect', cid])
    final = load(final_stdout)
    require(len(final) == 1, 'Final container inspect')
    final = final[0]
    require(final['Id'] == inspection['container_id'] and final['Image'] == plan['image'],
            'Container changed')
    require(final['State']['Status'] == 'exited' and final['State']['ExitCode'] == 0
            and final['State']['OOMKilled'] is False and final['State']['Error'] == ''
            and final['State']['Dead'] is False, 'Failed, killed or running final process')
    require(final['Config'] == load(root / 'created-inspect.json')[0]['Config']
            and final['HostConfig'] == load(root / 'created-inspect.json')[0]['HostConfig'],
            'Container configuration changed after inspection')
    need((root / 'container-run' / 'result.json').is_file(), 'Missing launcher result')
    run_root = root / 'container-run'
    result = load(run_root / 'result.json')
    require(result['verdict'] == 'PASS_MOUNTED_ASGI_REQUIRE_ENGINE_EVIDENCE'
            and result['mounted_profile'] == plan['profile'] and result['uid'] == plan['uid']
            and result['gid'] == plan['gid'] and plan['reader_gid'] in result['groups']
            and result['collected'] == 1 and result['outcomes'] == {'passed': 1}
            and result['pytest_exit_code'] == 0 and not result['forbidden_io_events'],
            'Launcher result/identity/isolation')
    runtime = load(root / 'runtime-probe.json')
    receipt(root, 'runtime', docker + ['exec', cid, plan['python'], '-I', '-B',
                                      '/opt/p4-tools/runtime_probe.py', '--inventory',
                                      '/opt/p4-materials/DEPENDENCIES_OBSERVED.json',
                                      '--out', '/evidence/runtime-probe.json'])
    require(runtime['verdict'] == 'PASS_RUNTIME_OBSERVATION_ONLY_NOT_P4'
            and runtime['uid'] == plan['uid'] and runtime['gid'] == plan['gid']
            and plan['reader_gid'] in runtime['groups']
            and runtime['inventory_sha256'] == image_review['inventory_sha256']
            and runtime['probe_sha256'] == digest(Path(__file__).with_name('runtime_probe.py'))
            and runtime['helper_sha256'] == digest(Path(__file__).with_name('offline.py')),
            'Runtime probe absent/wrong identity or different materials/tools')
    from offline import manifest
    manifest(run_root)
    xml = ET.parse(run_root / 'junit.xml')
    tests = list(xml.getroot().iter('testcase'))
    require(len(tests) == 1 and not any(list(xml.getroot().iter(tag))
            for tag in ('failure', 'error', 'skipped')), 'JUnit outcome')
    published = []
    action_times = []
    for index in range(len(plan['probes'])):
        capture, output = receipt(root, f'action-{index + 1:02d}')
        publication = load(output)
        require(capture['start_ns'] <= publication['start_ns'] <=
                publication['commit_return_ns'] <= capture['end_ns'], 'Publication/capture times')
        published.append(publication)
        action_times.append((capture['start_ns'], capture['end_ns']))
    events = event_check(plan, log_path.read_text(encoding='utf-8'), published, action_times)
    require(all(session_receipt['start_ns'] <= start <= end <= session_receipt['end_ns']
                for start, end in action_times), 'Actions outside attached session')
    cases_report = load(run_root / 'cases.json')
    require(len(cases_report) == 1 and cases_report[0]['outcome'] == 'passed'
            and json.loads(cases_report[0]['properties']['mounted_observations']) == events[1:],
            'Launcher observations disagree with Engine logs')
    require(all(end <= wait_receipt['end_ns'] for _, end in action_times), 'Actions after wait')
    return {'verdict': 'PASS_CASE_ONLY', 'case': plan['case'], 'profile': plan['profile'],
            'p4_go': False, 'production_go': False, 'events': events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(args.evidence)
        code = 0
    except Incomplete as error:
        result, code = {'verdict': 'INCOMPLETE', 'reason': str(error), 'p4_go': False}, 2
    except FileNotFoundError as error:
        result, code = {'verdict': 'INCOMPLETE', 'reason': str(error), 'p4_go': False}, 2
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
        result, code = {'verdict': 'FAIL', 'reason': str(error), 'p4_go': False}, 1
    write_new(args.out, result)
    sys.exit(code)


if __name__ == '__main__':
    main()
