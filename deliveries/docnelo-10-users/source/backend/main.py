import asyncio
import tempfile
import threading
import queue
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from .api import router
from .config import Settings
from .db import make_engine, make_sessions, make_authentication_engine
from .ai.api import router as ai_router
from .auth import SessionVault
from .ai.settings_api import router as settings_router
from .rag.api import router as rag_router
from .ai.long_api import router as long_router
from .account_api import router as account_router
from .resource_limits import RateLimiter
from .upload_admission import IPAdmission, UploadAdmission, UploadCapacity, is_upload
from .audit_middleware import SecurityAudit
from .recovery_quarantine import RecoveryQuarantine, read_recovery_state
from .security_audit import emit, mark


class RequestSizeLimit:
    """Bound requests before multipart parsing, including chunked requests."""
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        with tempfile.SpooledTemporaryFile(max_size=256 * 1024) as body:
            size = 0
            while True:
                upload = is_upload(scope)
                try:
                    if upload:
                        settings = scope['app'].state.settings
                        left = settings.upload_read_timeout_seconds - (time.monotonic() - scope['state']['upload_started'])
                        if left <= 0:
                            raise TimeoutError
                        message = await asyncio.wait_for(receive(), min(left, settings.upload_idle_timeout_seconds))
                        authorization = dict(scope['headers']).get(b'authorization', b'').decode('latin-1')
                        if authorization.startswith('Bearer '):
                            scope['app'].state.session_vault.resolve(authorization[7:])
                    else:
                        message = await receive()
                except TimeoutError:
                    return await JSONResponse({'detail': 'Délai de réception dépassé'}, 408)(scope, receive, send)
                except HTTPException as exc:
                    return await JSONResponse({'detail': exc.detail}, exc.status_code)(scope, receive, send)
                if message["type"] == "http.disconnect":
                    return
                data = message.get("body", b"")
                size += len(data)
                maximum = scope['app'].state.settings.max_upload_bytes + 65536 if upload else self.maximum
                if size > maximum:
                    return await JSONResponse({"detail": "Requête trop volumineuse"}, status_code=413)(scope, receive, send)
                body.write(data)
                if not message.get("more_body", False):
                    break
            expected = dict(scope['headers']).get(b'content-length')
            if is_upload(scope) and expected is not None and size != int(expected):
                return await JSONResponse({'detail': 'Corps incomplet'}, 400)(scope, receive, send)
            body.seek(0)

            async def replay():
                data = body.read(64 * 1024)
                return {"type": "http.request", "body": data, "more_body": body.tell() < size}

            await self.app(scope, replay, send)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if not settings.api_keys and not settings.bff_service_key.get_secret_value():
            emit('system.security_config.invalid', reason_code='security_unavailable')
            raise RuntimeError("Configurez API_KEYS avant de démarrer le serveur")
        recovery_state = read_recovery_state(settings.recovery_state_path)
        app.state.recovery_ready_at_start = recovery_state == 'ready'
        if not app.state.recovery_ready_at_start:
            emit('system.recovery.quarantine', reason_code='recovery_quarantined')
        if app.state.recovery_ready_at_start and settings.extraction_mode == 'sandbox':
            from .services.extraction import check_available
            try:
                await asyncio.to_thread(check_available, settings)
            except Exception:
                emit('system.security_config.invalid', reason_code='security_unavailable')
                raise RuntimeError('Confinement requis indisponible') from None
        if app.state.recovery_ready_at_start:
            settings.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            from .rag.indexing import recover_jobs
            recover_jobs(app)
            from .ai.long_summary import recover
            recover(app)
            app.state.summary_worker.thread.start()

            def deliver_mail():
                from .account_api import send_reset,send_verification
                while not app.state.mail_stopping.is_set():
                    try:
                        item = app.state.mail_queue.get(timeout=.2)
                        email, token = item[:2]
                        verification = len(item)==3 and item[2]=='verify'
                    except queue.Empty:
                        continue
                    try:
                        sender = getattr(app.state,'mail_sender',None)
                        if sender:
                            sender(email,token)
                        else:
                            (send_verification if verification else send_reset)(settings,email,token)
                    except Exception:
                        emit('system.mail.failed', reason_code='mail_failed')
                    finally:
                        app.state.mail_queue.task_done()

            mail_thread = threading.Thread(target=deliver_mail,daemon=True)
            mail_thread.start()

            async def expire_sessions():
                while True:
                    await asyncio.sleep(15)
                    with app.state.session_vault.lock:
                        app.state.session_vault.purge()

            cleanup = asyncio.create_task(expire_sessions())
        else:
            mail_thread = None
            cleanup = None
        try:
            yield
        finally:
            if cleanup is not None:
                cleanup.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup
            if app.state.recovery_ready_at_start:
                await asyncio.to_thread(app.state.summary_worker.stop)
            if mail_thread is not None:
                app.state.mail_stopping.set()
                await asyncio.to_thread(mail_thread.join,12)
            app.state.session_vault.clear()
            app.state.authentication_engine.dispose()
            app.state.engine.dispose()

    app = FastAPI(title="DocuMind AI", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.recovery_ready_at_start = False
    app.state.engine = make_engine(settings.database_url)
    app.state.sessions = make_sessions(app.state.engine)
    app.state.authentication_engine = make_authentication_engine(settings.database_url, app.state.engine)
    app.state.authentication_sessions = make_sessions(app.state.authentication_engine)
    app.state.slots = threading.BoundedSemaphore(settings.max_concurrent_workers)
    app.state.ai_provider = None
    app.state.embedding_provider = None
    app.state.session_vault = SessionVault(settings.ai_session_ttl_seconds)
    from .public_registration import RegistrationChallenges
    app.state.registration_challenges = RegistrationChallenges()
    app.state.rate_limiter = RateLimiter()
    app.state.upload_capacity = UploadCapacity()
    app.state.authentication_slots = threading.BoundedSemaphore(settings.upload_max_preflights)
    app.state.mail_queue = queue.Queue(maxsize=100)
    app.state.mail_stopping = threading.Event()
    from .ai.long_summary import SummaryWorker
    app.state.summary_worker = SummaryWorker(app)
    app.add_middleware(RequestSizeLimit, maximum=settings.max_upload_bytes + 64 * 1024)
    app.add_middleware(UploadAdmission)
    app.add_middleware(IPAdmission)
    app.add_middleware(SecurityAudit)
    app.add_middleware(RecoveryQuarantine)
    app.include_router(router)
    app.include_router(ai_router)
    app.include_router(settings_router)
    app.include_router(rag_router)
    app.include_router(long_router)
    app.include_router(account_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default error payload can echo an invalid secret/password input.
        return JSONResponse({'detail': [{'loc': error['loc'], 'msg': error['msg'], 'type': error['type']} for error in exc.errors()]}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        mark('system.database.unavailable', 'database')
        return JSONResponse({"detail": "Base de données indisponible"}, status_code=503)

    return app


try:
    app = create_app()
except Exception:
    # Settings/engine exceptions may include a DSN or raw validation input.
    emit('system.security_config.invalid', reason_code='security_unavailable')
    raise RuntimeError('Configuration du service invalide') from None
