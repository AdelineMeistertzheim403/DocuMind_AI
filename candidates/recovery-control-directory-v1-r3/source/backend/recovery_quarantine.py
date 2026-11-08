import json
import os
import stat
from pathlib import Path

from fastapi.responses import JSONResponse

from .security_audit import emit

MAX_LATCH_BYTES = 1024


def read_recovery_state(path):
    if path is None:
        return 'unconfigured'
    path = Path(path).absolute()
    try:
        if any(part.is_symlink() for part in (path, *path.parents)):
            return 'invalid'
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_LATCH_BYTES:
                return 'invalid'
            with os.fdopen(descriptor, 'rb', closefd=False) as latch:
                data = latch.read(MAX_LATCH_BYTES + 1)
        finally:
            os.close(descriptor)
    except OSError:
        return 'unavailable'
    if len(data) > MAX_LATCH_BYTES:
        return 'invalid'

    def unique_keys(pairs):
        state = {}
        for key, value in pairs:
            if key in state:
                raise ValueError('duplicate key')
            state[key] = value
        return state

    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique_keys)
    except (UnicodeDecodeError, ValueError):
        return 'invalid'
    if (not isinstance(value, dict) or set(value) != {'format', 'state'}
            or type(value['format']) is not int or value['format'] != 1
            or not isinstance(value['state'], str) or value['state'] not in {'ready', 'quarantined', 'serving_closed'}):
        return 'invalid'
    return value['state']


class RecoveryQuarantine:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        app = scope['app']
        state = read_recovery_state(app.state.settings.recovery_state_path)
        permitted = state == 'ready'
        if getattr(app.state, 'recovery_release', None):
            permitted = False
        if state == 'serving_closed':
            from .lite_release import serving_gate
            permitted = serving_gate(app)
        if not app.state.recovery_ready_at_start or not permitted:
            emit('system.recovery.quarantine', reason_code='recovery_quarantined', http_status=503)
            response = JSONResponse({'detail': 'Service en quarantaine de reprise'}, status_code=503)
            return await response(scope, receive, send)
        if state == 'serving_closed' and scope.get('path') == '/api/v1/auth/register':
            return await JSONResponse({'detail': 'Admissions fermees apres reprise'}, status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)
