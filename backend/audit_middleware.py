"""Correlation and single response event, before any receive/spool/multipart parsing."""
import asyncio
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .gateway import trusted_gateway
from .security_audit import AuditContext, REQUEST_ID, current, emit


def operation(path, method):
    fixed = {'/api/v1/auth/login': 'login', '/api/v1/auth/logout': 'logout',
        '/api/v1/auth/register': 'register', '/api/v1/auth/forgot-password': 'reset_request',
        '/api/v1/auth/reset-password': 'reset_complete', '/api/v1/account/password': 'password_change',
        '/api/v1/account/deletion-request': 'deletion_request',
        '/api/v1/internal/upload-admission': 'upload_preflight'}
    if path in fixed:
        return fixed[path]
    if path.rstrip('/') == '/api/v1/documents' and method == 'POST':
        return 'upload'
    if path.startswith('/api/v1/account/sessions/') and method == 'DELETE':
        return 'session_revoke'
    for prefix, name in [('/api/v1/documents', 'documents'), ('/api/v1/account', 'account'),
                         ('/api/v1/ai', 'ai'), ('/api/v1/search', 'ai')]:
        if path.startswith(prefix):
            return name
    return 'other'


def result(context, status, disconnected):
    if context.event:
        return context.event, context.reason_code
    if disconnected:
        return ('upload.aborted', 'disconnected') if context.operation == 'upload' else (None, None)
    success = {'login': 'auth.login.success', 'logout': 'auth.logout', 'register': 'account.created',
        'reset_request': 'auth.password_reset.requested', 'reset_complete': 'auth.password_reset.completed',
        'password_change': 'auth.password.changed', 'session_revoke': 'auth.session.revoked',
        'deletion_request': 'account.deletion.requested', 'upload': 'upload.completed'}
    if 200 <= status < 300:
        return success.get(context.operation), 'completed'
    if status == 429:
        return 'rate_limit.exceeded', 'rate_limit'
    if status == 402:
        return 'quota.exceeded', 'quota'
    if context.operation == 'upload_preflight' and status == 503:
        return 'upload.capacity.exceeded', 'capacity'
    if context.operation == 'upload':
        return {401: ('upload.admission.denied', 'authentication_required'),
                403: ('upload.admission.denied', 'denied'),
                400: ('upload.rejected', 'invalid_request'), 415: ('upload.rejected', 'invalid_request'),
                422: ('upload.rejected', 'invalid_request'),
                408: ('upload.timeout', 'timeout'), 413: ('upload.size.exceeded', 'size'),
                503: ('upload.capacity.exceeded', 'capacity')}.get(status, ('upload.admission.denied', 'denied'))
    if context.operation == 'login' and status in {400, 401, 422}:
        return 'auth.login.failure', 'invalid_identity'
    if context.operation in {'password_change', 'deletion_request'} and status == 401:
        return 'access.denied', 'invalid_identity'
    if status == 401:
        return 'auth.session.invalid', 'invalid_session'
    if status in {403, 404}:
        return 'access.denied', 'denied'
    return None, None


class SecurityAudit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        supplied = request.headers.getlist('x-request-id')
        request_id = (supplied[0] if len(supplied) == 1 and REQUEST_ID.fullmatch(supplied[0])
                      and trusted_gateway(request) else uuid4().hex)
        context = AuditContext(request_id, operation(scope['path'], scope['method']))
        token = current.set(context)
        status, started, disconnected = 500, False, False

        async def observed_receive():
            nonlocal disconnected
            message = await receive()
            disconnected |= message['type'] == 'http.disconnect'
            return message

        async def observed_send(message):
            nonlocal status, started
            if message['type'] == 'http.response.start':
                status, started = message['status'], True
                message = {**message, 'headers': [(k, v) for k, v in message.get('headers', [])
                    if k.lower() != b'x-request-id'] + [(b'x-request-id', request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, observed_receive, observed_send)
        except asyncio.CancelledError:
            disconnected = True
            raise
        except Exception:
            # Do not let Uvicorn serialize arbitrary exception messages/SQL/request data.
            context.event, context.reason_code = 'system.worker.failed', 'unexpected_error'
            if not started:
                try:
                    await JSONResponse({'detail': 'Erreur interne du service'}, 500)(scope, observed_receive, observed_send)
                except (Exception, asyncio.CancelledError):
                    # A failed error response must not expose the original exception chain.
                    disconnected = True
        finally:
            try:
                event, reason = result(context, status, disconnected)
                if event:
                    emit(event, reason_code=reason, http_status=499 if disconnected else status)
            finally:
                current.reset(token)
