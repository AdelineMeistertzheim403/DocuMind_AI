"""DEFERRED: genuine FastAPI against a host-controlled, RO-mounted synthetic latch."""
import json
import sys
from pathlib import Path

from tests.test_recovery_quarantine_inprocess import (
    harness, quarantine_route_cases, request, run,
)

# Only the standalone mounted profile adds the inventoried campaign tests directory.
from test_fastapi_directory_transitions import application, tripwire, WORKERS, lite_blocked


def test_host_controlled_mounted_latch(harness, pytestconfig, record_property):
    profile = pytestconfig._mounted_profile
    path = Path('/run/documind-control/recovery-state.json')
    h = harness
    app = application(h, path, profile)
    reached, observations = [], []
    tripwire(app, reached)
    cases = quarantine_route_cases(app)

    def emit(value):
        print('RCD_EVENT ' + json.dumps(value, sort_keys=True), file=sys.__stdout__, flush=True)

    async def scenario():
        async with app.router.lifespan_context(app):
            initial = app.state.recovery_ready_at_start
            workers = {key: h.effects[key] for key in WORKERS}
            if not initial:
                assert not any(workers.values())
            emit({'event': 'startup', 'ready_at_start': initial, 'path': str(path),
                  'workers': workers, 'routes': len(cases)})
            for _ in range(64):
                line = sys.__stdin__.readline()
                assert line, 'EOF without explicit stop: incomplete mounted campaign'
                command = json.loads(line)
                if command == {'action': 'stop'}:
                    assert observations, 'at least one post-publication probe required'
                    return
                assert command.get('action') == 'probe'
                assert command.get('expect') in ('closed', 'sentinel')
                before = len(reached)
                outcomes = {}
                if command['expect'] == 'sentinel':
                    assert initial
                    response, _ = await request(app, 'GET', '/api/v1/health', authenticated=True)
                    assert response.status_code == 500
                    assert len(reached) == before + 1
                    outcomes['500-synthetic-tripwire'] = 1
                else:
                    for authenticated in (False, True):
                        for method, route in cases:
                            response, consumed = await request(app, method, route, authenticated=authenticated)
                            expected = 403 if profile == 'beta_lite' and lite_blocked(route) else 503
                            assert response.status_code == expected
                            assert not consumed
                            outcomes[str(expected)] = outcomes.get(str(expected), 0) + 1
                    assert len(reached) == before
                assert workers == {key: h.effects[key] for key in WORKERS}
                observation = {'event': 'probe', 'expected': command['expect'], 'outcomes': outcomes,
                               'ready_at_start': initial, 'downstream_delta': len(reached) - before}
                observations.append(observation)
                emit(observation)
            raise AssertionError('missing stop within 64 commands')
    run(scenario())
    record_property('mounted_observations', json.dumps(observations))
