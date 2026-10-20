import asyncio
import logging
import tempfile
import threading
import queue
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from .api import router
from .config import Settings
from .db import make_engine, make_sessions
from .ai.api import router as ai_router
from .auth import SessionVault
from .ai.settings_api import router as settings_router
from .rag.api import router as rag_router
from .ai.long_api import router as long_router
from .account_api import router as account_router
from .resource_limits import RateLimiter


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
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data = message.get("body", b"")
                size += len(data)
                if size > self.maximum:
                    return await JSONResponse({"detail": "Requête trop volumineuse"}, status_code=413)(scope, receive, send)
                body.write(data)
                if not message.get("more_body", False):
                    break
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
            raise RuntimeError("Configurez API_KEYS avant de démarrer le serveur")
        if settings.extraction_mode == 'sandbox':
            from .services.extraction import check_available
            await asyncio.to_thread(check_available, settings)
        settings.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        from .rag.indexing import recover_jobs
        recover_jobs(app)
        from .ai.long_summary import recover
        recover(app)
        app.state.summary_worker.thread.start()

        def deliver_mail():
            from .account_api import send_reset
            while not app.state.mail_stopping.is_set():
                try:
                    email, token = app.state.mail_queue.get(timeout=.2)
                except queue.Empty:
                    continue
                try:
                    sender = getattr(app.state,'mail_sender',None)
                    if sender:
                        sender(email,token)
                    else:
                        send_reset(settings,email,token)
                except Exception:
                    logging.getLogger(__name__).warning('mail_delivery_failed')
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
        try:
            yield
        finally:
            cleanup.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup
            await asyncio.to_thread(app.state.summary_worker.stop)
            app.state.mail_stopping.set()
            await asyncio.to_thread(mail_thread.join,12)
            app.state.session_vault.clear()
            app.state.engine.dispose()

    app = FastAPI(title="DocuMind AI", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessions = make_sessions(app.state.engine)
    app.state.slots = threading.BoundedSemaphore(settings.max_concurrent_workers)
    app.state.ai_provider = None
    app.state.embedding_provider = None
    app.state.session_vault = SessionVault(settings.ai_session_ttl_seconds)
    app.state.rate_limiter = RateLimiter()
    app.state.mail_queue = queue.Queue(maxsize=100)
    app.state.mail_stopping = threading.Event()
    from .ai.long_summary import SummaryWorker
    app.state.summary_worker = SummaryWorker(app)
    app.add_middleware(RequestSizeLimit, maximum=settings.max_upload_bytes + 64 * 1024)
    app.include_router(router)
    app.include_router(ai_router)
    app.include_router(settings_router)
    app.include_router(rag_router)
    app.include_router(long_router)
    app.include_router(account_router)

    @app.middleware('http')
    async def ip_admission(request, call_next):
        if request.url.path != '/api/v1/health':
            from .gateway import client_ip
            from fastapi import HTTPException
            try:
                app.state.rate_limiter.check(f'ip:{client_ip(request)}', settings.requests_per_minute * 4)
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default error payload can echo an invalid secret/password input.
        return JSONResponse({'detail': [{'loc': error['loc'], 'msg': error['msg'], 'type': error['type']} for error in exc.errors()]}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logging.getLogger(__name__).error("database_error type=%s", type(exc).__name__)
        return JSONResponse({"detail": "Base de données indisponible"}, status_code=503)

    return app


app = create_app()
