"""Offline argv preparation and fail-closed Engine inspection. Never calls Docker."""
import argparse
from pathlib import Path, PurePosixPath
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline import candidate, digest, load, no_links, require, write_new
from matrix import cases

TMPFS = 'rw,noexec,nosuid,nodev,size=67108864,mode=1777'
MEMORY = 536870912
LABEL = 'org.docnelo.p4.synthetic'


def absolute(value):
    require(isinstance(value, str) and value.startswith('/') and value != '/'
            and str(PurePosixPath(value)) == value and '\\' not in value and ',' not in value
            and not any(part in ('', '.', '..') for part in value.split('/')[1:])
            and not any(ord(c) < 33 for c in value), 'Canonical Linux path required')
    return value


def overlap(a, b):
    a, b = PurePosixPath(a), PurePosixPath(b)
    return a == b or a in b.parents or b in a.parents


def validate_plan(plan):
    require(set(plan) == {'purpose', 'profile', 'case', 'name', 'image', 'python', 'uid', 'gid',
                          'reader_gid', 'candidate', 'root', 'image_env', 'image_review_sha256',
                          'initial_ready', 'probes'}, 'Exact plan schema required')
    require(plan['purpose'] == 'P4_ASGI_ONLY' and plan['profile'] in ('standard', 'beta_lite'),
            'P4 mounted profile only')
    require(re.fullmatch(r'D(?:0[3-9]|11|12|14)(?:-[a-z0-9-]+)?', str(plan['case'])), 'P4 case ID')
    require(re.fullmatch(r'docnelo-p4-[a-f0-9]{32}-[a-z0-9-]+', str(plan['name'])), 'P4 name')
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', str(plan['image'])), 'Immutable local image ID')
    require(re.fullmatch(r'[a-f0-9]{64}', str(plan['image_review_sha256'])), 'Image approval receipt')
    for key in ('uid', 'gid', 'reader_gid'):
        require(type(plan[key]) is int and 0 < plan[key] <= 2147483647, 'Non-root numeric identity')
    require(plan['gid'] != plan['reader_gid'], 'Separate explicit reader group')
    for key in ('candidate', 'root', 'python'):
        absolute(plan[key])
    require(re.fullmatch(r'/var/tmp/docnelo-p4-[a-f0-9]{32}', plan['root']), 'P4 namespace only')
    require(plan['name'].startswith(PurePosixPath(plan['root']).name + '-'), 'Name/root binding')
    require(not overlap(plan['candidate'], plan['root']), 'Candidate/namespace overlap')
    require(plan['python'] == '/opt/p4-venv/bin/python', 'Dedicated reviewed venv path')
    require(type(plan['initial_ready']) is bool and plan['probes']
            and len(plan['probes']) <= 63
            and all(p in ('closed', 'sentinel') for p in plan['probes']), 'Ordered probes required')
    require(plan['initial_ready'] or 'sentinel' not in plan['probes'], 'Closed startup cannot reopen')
    require(plan['case'] in cases() and
            (plan['initial_ready'], plan['probes']) ==
            (cases()[plan['case']][0], [step[2] for step in cases()[plan['case']][1]]),
            'Only the bounded reviewed matrix; no silent custom campaign')
    env = plan['image_env']
    require(isinstance(env, list) and all(isinstance(s, str) and '=' in s for s in env), 'Image environment')
    keys = [s.split('=', 1)[0] for s in env]
    require(len(keys) == len(set(keys)) and set(keys) <=
            {'PATH', 'LANG', 'LC_ALL', 'TZ', 'PYTHON_VERSION', 'PYTHON_SHA256'},
            'Unexpected/duplicate inherited environment; never secrets or Python options')


def mounts(plan):
    return [(plan['candidate'], '/candidate', True),
            (plan['root'] + '/control', '/run/documind-control', True),
            (plan['root'] + '/evidence', '/evidence', False)]


def cmd(plan):
    return ['-I', '-B', '/candidate/run_local.py', '--mounted-profile', plan['profile'],
            '--reader-gid', str(plan['reader_gid']), '--evidence', '/evidence/run',
            '--scratch', '/tmp/case']


def argv(plan):
    validate_plan(plan)
    result = ['docker', '--host', 'unix:///var/run/docker.sock', 'create',
              '--pull=never', '-i', '--name', plan['name'],
              '--label', LABEL + '=true', '--network', 'none',
              '--user', f"{plan['uid']}:{plan['gid']}", '--group-add', str(plan['reader_gid']),
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
              '--memory', str(MEMORY), '--memory-swap', str(MEMORY), '--cpus', '0.5',
              '--pids-limit', '64', '--ipc', 'none', '--cgroupns', 'private',
              '--restart', 'no', '--stop-timeout', '15', '--no-healthcheck',
              '--hostname', 'p4-synthetic', '--workdir', '/candidate',
              '--env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
              '--tmpfs', '/tmp:' + TMPFS,
              '--log-driver', 'json-file', '--log-opt', 'max-size=16m', '--log-opt', 'max-file=1',
              '--entrypoint', plan['python']]
    for source, target, readonly in mounts(plan):
        result += ['--mount', f'type=bind,src={source},dst={target},bind-propagation=rprivate'
                   + (',readonly' if readonly else '')]
    return result + [plan['image'], *cmd(plan)]


def inspect_created(plan, obj, image, others):
    validate_plan(plan)
    config, host, state = obj['Config'], obj['HostConfig'], obj['State']
    require(state['Status'] == 'created' and state['Running'] is False
            and state['StartedAt'].startswith('0001-01-01'), 'Container must never have started')
    require(obj['Image'] == image['Id'] == plan['image'] and config['Image'] == plan['image'],
            'Real image ID differs')
    require(obj['Name'] == '/' + plan['name'] and re.fullmatch('[a-f0-9]{64}', obj['Id']), 'Name/ID')
    require(config.get('Labels', {}).get(LABEL) == 'true', 'Synthetic label absent')
    require(config['Entrypoint'] == [plan['python']] and config['Cmd'] == cmd(plan),
            'Never the normal application entrypoint')
    require(config['User'] == f"{plan['uid']}:{plan['gid']}"
            and config['WorkingDir'] == '/candidate' and config['Hostname'] == 'p4-synthetic',
            'Container identity/workdir')
    require(config['OpenStdin'] is True and config['Tty'] is False, 'Non-TTY open stdin required')
    expected_env = plan['image_env'] + ['PYTEST_DISABLE_PLUGIN_AUTOLOAD=1']
    require(sorted(config['Env']) == sorted(expected_env), 'Exact synthetic environment required')
    require(image.get('Os') == 'linux' and image.get('Architecture') == 'amd64', 'Image platform')
    ic = image['Config']
    require(sorted(ic.get('Env') or []) == sorted(plan['image_env'])
            and not ic.get('Volumes') and not ic.get('OnBuild'), 'Unreviewed image configuration')
    require(not config.get('Volumes') and not config.get('ExposedPorts')
            and config.get('Healthcheck', {}).get('Test') == ['NONE'], 'No ports/volumes/healthcheck')
    require(host['NetworkMode'] == 'none' and not host.get('PortBindings')
            and host['PublishAllPorts'] is False, 'Network none, no published ports')
    require(not obj['NetworkSettings'].get('Ports')
            and set(obj['NetworkSettings'].get('Networks', {})) <= {'none'}, 'Unexpected network')
    require(host['ReadonlyRootfs'] is True and host['Privileged'] is False
            and host['CapDrop'] == ['ALL'] and not host.get('CapAdd')
            and host['SecurityOpt'] == ['no-new-privileges'], 'Confinement mismatch')
    require(host['GroupAdd'] == [str(plan['reader_gid'])], 'Explicit reader group')
    require(type(host['Memory']) is int and host['Memory'] == MEMORY
            and type(host['MemorySwap']) is int and host['MemorySwap'] == MEMORY
            and type(host['NanoCpus']) is int and host['NanoCpus'] == 500000000
            and type(host['PidsLimit']) is int and host['PidsLimit'] == 64, 'Resource limits')
    require(host['IpcMode'] == 'none' and host['CgroupnsMode'] == 'private'
            and host['PidMode'] == '' and host['UTSMode'] == '' and host['UsernsMode'] == '',
            'Unreviewed shared/remapped namespace')
    require(host['RestartPolicy'] == {'Name': 'no', 'MaximumRetryCount': 0}
            and host['AutoRemove'] is False and config['StopTimeout'] == 15, 'Stop/retention policy')
    require(host['Tmpfs'] == {'/tmp': TMPFS}, 'Only the declared /tmp tmpfs')
    require(host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '16m', 'max-file': '1'}},
            'Preserved local logs required')
    for field in ('Binds', 'VolumesFrom', 'Devices', 'DeviceRequests', 'DeviceCgroupRules',
                  'Links', 'ExtraHosts', 'Dns', 'DnsOptions', 'DnsSearch', 'Sysctls',
                  'StorageOpt', 'CgroupParent'):
        require(not host.get(field), 'Unexpected HostConfig.' + field)
    require(not host.get('OomKillDisable') and not host.get('Init'), 'Unexpected OOM/init policy')
    declared = host['Mounts']
    require(len(declared) == 3, 'Exactly three declared binds')
    for source, target, ro in mounts(plan):
        selected = [m for m in declared if m.get('Target') == target]
        require(len(selected) == 1, 'Missing/duplicate declared target')
        item = selected[0]
        require(item.get('Type') == 'bind' and item.get('Source') == source
                and item.get('ReadOnly', False) is ro
                and item.get('BindOptions') == {'Propagation': 'rprivate'}
                and not (set(item) - {'Type', 'Source', 'Target', 'ReadOnly', 'BindOptions'}),
                'Declared bind mismatch')
    actual = [m for m in obj['Mounts'] if m.get('Type') != 'tmpfs']
    require(len(actual) == 3, 'Anonymous, inherited or extra bind/volume')
    for source, target, ro in mounts(plan):
        selected = [m for m in actual if m.get('Destination') == target]
        require(len(selected) == 1 and selected[0].get('Type') == 'bind'
                and selected[0].get('Source') == source and selected[0].get('RW') is (not ro)
                and selected[0].get('Propagation') == 'rprivate', 'Actual mount mismatch')
    require(all(m.get('Destination') == '/tmp' for m in obj['Mounts'] if m.get('Type') == 'tmpfs'),
            'Unexpected tmpfs mount')
    seen = set()
    for other in others:
        require(other['Id'] not in seen and other['Id'] != obj['Id'], 'Other-container ID inventory')
        seen.add(other['Id'])
        for mount in other['Mounts']:
            source = mount.get('Source')
            if source and source.startswith('/'):
                require(not overlap(source, plan['root']),
                        'Other container aliases P4 control/evidence, including RO aliases')
                require(not overlap(source, plan['candidate']) or mount.get('RW') is False,
                        'Other container can write the frozen candidate')
    return {'verdict': 'PASS_CREATED_INSPECTION_ONLY', 'start_go': False,
            'container_id': obj['Id'], 'image_id': obj['Image'], 'others_reviewed': sorted(seen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--inspect', type=Path)
    parser.add_argument('--image-inspect', type=Path)
    parser.add_argument('--others', type=Path)
    args = parser.parse_args()
    plan = load(args.plan)
    validate_plan(plan)
    candidate(Path(plan['candidate']))
    for source, _, _ in mounts(plan):
        require(no_links(source).is_dir(), 'Pre-existing bind directory required')
    if args.inspect:
        require(args.image_inspect and args.others, 'All inspection inputs required')
        objects, images = load(args.inspect), load(args.image_inspect)
        require(len(objects) == len(images) == 1, 'Exactly one target container/image')
        result = inspect_created(plan, objects[0], images[0], load(args.others))
        result['inputs'] = {name: digest(path) for name, path in (
            ('plan.json', args.plan), ('created-inspect.json', args.inspect),
            ('image-inspect.json', args.image_inspect), ('others.json', args.others))}
    else:
        require(not args.image_inspect and not args.others, 'Partial inspection refused')
        result = {'status': 'REVIEW_ONLY_ARGV_NOT_EXECUTED', 'argv': argv(plan), 'create_go': False}
    write_new(args.out, result)


if __name__ == '__main__':
    main()
