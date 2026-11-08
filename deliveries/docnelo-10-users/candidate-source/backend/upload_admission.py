"""Body-free admission and bounded upload resource reservations (one API process)."""
import asyncio
import shutil
import tempfile
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .authentication import authenticate
from .gateway import client_ip
from .security_audit import mark


def is_upload(scope):
    return scope['method'] == 'POST' and scope['path'].rstrip('/') == '/api/v1/documents'


class UploadCapacity:
    def __init__(self):
        self.lock = threading.Lock()
        self.owners = {}
        self.active = self.reserved = 0

    def acquire(self, owner, settings):
        reservation = 3 * settings.max_upload_bytes + 2 * 65536
        with self.lock:
            # Conservatively count existing .part files too, including crash leftovers.
            # Never delete them as part of request admission.
            partial_bytes = 0
            for partial in settings.storage_dir.glob('*.part'):
                partial_bytes += partial.stat().st_size
                if partial_bytes + self.reserved + reservation > settings.upload_temp_budget_bytes:
                    raise HTTPException(503, 'Budget temporaire atteint')
            if (self.active >= settings.upload_max_concurrent or
                    self.owners.get(owner, 0) >= settings.upload_max_per_owner or
                    self.reserved + reservation > settings.upload_temp_budget_bytes):
                raise HTTPException(503, 'Capacité de réception atteinte', headers={'Retry-After': '1'})
            self.active += 1
            self.reserved += reservation
            self.owners[owner] = self.owners.get(owner, 0) + 1
        return reservation

    def release(self, owner, reservation):
        with self.lock:
            self.active -= 1
            self.reserved -= reservation
            self.owners[owner] -= 1
            if not self.owners[owner]:
                del self.owners[owner]


async def early_authenticate(request, *, charge=True):
    state = request.app.state
    if not state.authentication_slots.acquire(blocking=False):
        raise HTTPException(503, 'Capacité de vérification atteinte')
    task = asyncio.create_task(asyncio.to_thread(authenticate, request, charge=charge))

    def finished(completed):
        state.authentication_slots.release()
        if not completed.cancelled():
            completed.exception()  # Consume failures even if the client already timed out.

    task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), state.settings.upload_auth_timeout_seconds)
    except TimeoutError:
        raise HTTPException(503, 'Vérification temporairement indisponible') from None


class IPAdmission:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'] != '/api/v1/health':
            request = Request(scope)
            try:
                request.app.state.rate_limiter.check(f'ip:{client_ip(request)}', request.app.state.settings.requests_per_minute * 4)
            except HTTPException as exc:
                return await JSONResponse({'detail': exc.detail}, exc.status_code, headers=exc.headers)(scope, receive, send)
        return await self.app(scope, receive, send)


class UploadAdmission:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not is_upload(scope):
            return await self.app(scope, receive, send)
        request = Request(scope)
        state = request.app.state
        reservation = None
        owner = None
        try:
            # Preserve the policy of other private routes; upload admission only validates identity.
            owner = await early_authenticate(request)
            request.state.admitted_owner = owner
            state.rate_limiter.check(f'upload:{owner}', state.settings.uploads_per_minute)
            lengths = request.headers.getlist('content-length')
            if (len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit())) or
                    (lengths and request.headers.get('transfer-encoding'))):
                raise HTTPException(400, 'Encadrement HTTP invalide')
            if lengths and int(lengths[0]) > state.settings.max_upload_bytes + 65536:
                raise HTTPException(413, 'Requête trop volumineuse')
            if request.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise HTTPException(415, 'Corps compressé non accepté')
            reservation = state.upload_capacity.acquire(owner, state.settings)
            # Check both filesystems before creating a request spool or persistent .part.
            root = state.settings.storage_dir
            storage = root if root.exists() else root.parent
            for directory in (storage, tempfile.gettempdir()):
                if shutil.disk_usage(directory).free < state.settings.upload_min_free_bytes + state.upload_capacity.reserved:
                    raise HTTPException(503, 'Espace temporaire insuffisant')
            request.state.upload_started = time.monotonic()
        except HTTPException as exc:
            if reservation is not None:
                state.upload_capacity.release(owner, reservation)
            return await JSONResponse({'detail': exc.detail}, exc.status_code, headers=exc.headers)(scope, receive, send)
        except (SQLAlchemyError, OSError) as exc:
            if isinstance(exc, SQLAlchemyError):
                mark('system.database.unavailable', 'database')
            if reservation is not None:
                state.upload_capacity.release(owner, reservation)
            return await JSONResponse({'detail': 'Admission indisponible'}, 503)(scope, receive, send)
        try:
            return await self.app(scope, receive, send)
        finally:
            state.upload_capacity.release(owner, reservation)
