"""Allowlisted security events; bounded, best-effort local stdout, never request data."""
import contextvars
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

EVENTS = {
    'auth.login.success': 'INFO', 'auth.login.failure': 'WARNING', 'auth.logout': 'INFO',
    'auth.session.invalid': 'WARNING', 'auth.session.revoked': 'WARNING',
    'auth.password_reset.requested': 'INFO', 'auth.password_reset.completed': 'INFO',
    'auth.password.changed': 'INFO', 'access.denied': 'WARNING',
    'access.cross_owner.denied': 'WARNING', 'gateway.authentication.failed': 'WARNING',
    'rate_limit.exceeded': 'WARNING', 'quota.exceeded': 'WARNING',
    'upload.admission.denied': 'WARNING', 'upload.capacity.exceeded': 'WARNING',
    'upload.size.exceeded': 'WARNING', 'upload.timeout': 'WARNING',
    'upload.aborted': 'INFO', 'upload.completed': 'INFO', 'account.created': 'INFO',
    'upload.rejected': 'WARNING',
    'account.deletion.requested': 'INFO', 'account.deletion.completed': 'INFO',
    'account.sessions.revoked': 'INFO', 'system.database.unavailable': 'ERROR',
    'system.security_config.invalid': 'CRITICAL', 'system.worker.failed': 'ERROR',
    'system.file_cleanup.failed': 'ERROR', 'system.mail.failed': 'ERROR',
    'system.ai.settled': 'INFO', 'system.ai.output_rejected': 'WARNING',
    'system.audit.dropped': 'WARNING',
}
OPERATIONS = frozenset(('login', 'logout', 'register', 'reset_request', 'reset_complete',
    'password_change', 'session_revoke', 'deletion_request', 'upload', 'upload_preflight',
    'documents', 'account', 'ai', 'system', 'other'))
REASONS = frozenset(('invalid_service_credential', 'secure_transport_required', 'invalid_identity',
    'invalid_session', 'session_revoked', 'not_owner', 'not_found', 'rate_limit', 'quota',
    'authentication_required', 'capacity', 'size', 'timeout', 'disconnected', 'database',
    'unexpected_error', 'security_unavailable', 'cleanup_failed', 'mail_failed',
    'worker_failed', 'invalid_output', 'settled', 'completed', 'denied', 'dropped', 'invalid_request'))
REQUEST_ID = re.compile(r'^[0-9a-f]{32}$')


@dataclass
class AuditContext:
    request_id: str
    operation: str
    event: str | None = None
    reason_code: str | None = None


current = contextvars.ContextVar('security_audit', default=None)


class AuditWriter:
    """No I/O in submit. A full/stalled/failed output never blocks authentication."""
    def __init__(self, sink=None, capacity=1024, per_second=100):
        self.sink = sink or self.stdout
        self.queue = queue.Queue(maxsize=capacity)
        self.per_second = per_second
        self.lock = threading.Lock()
        self.thread = None
        self.window = self.count = self.dropped = self.failed = 0
        self.reported = self.last_report = 0

    @staticmethod
    def stdout(line):
        # Avoid Python buffered-stdio locks held by a daemon at interpreter shutdown.
        os.write(1, (line + '\n').encode('utf-8'))

    def submit(self, line):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            now = int(time.monotonic())
            if now != self.window:
                self.window, self.count = now, 0
            if self.count >= self.per_second:
                self.dropped += 1
                return False
            self.count += 1
            try:
                self.queue.put_nowait(line)
            except queue.Full:
                self.dropped += 1
                return False
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name='security-audit', daemon=True)
                self.thread.start()
            return True
        finally:
            self.lock.release()

    def run(self):
        while True:
            line = self.queue.get()
            try:
                self.sink(line)
                lost = self.dropped + self.failed
                if lost > self.reported and time.monotonic() - self.last_report >= 1:
                    self.sink(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                        'level': 'WARNING', 'service': 'documind-api', 'event': 'system.audit.dropped',
                        'operation': 'system', 'outcome': 'error', 'reason_code': 'dropped',
                        'dropped_count': min(lost - self.reported, 1000000000)}))
                    self.reported, self.last_report = lost, time.monotonic()
            except Exception:
                self.failed += 1
            finally:
                self.queue.task_done()

    def flush(self, timeout=1):
        # Test/administrative observation only; never called from the request path.
        with self.queue.all_tasks_done:
            return self.queue.all_tasks_done.wait_for(lambda: self.queue.unfinished_tasks == 0, timeout)


writer = AuditWriter()


def mark(event, reason_code):
    context = current.get()
    if context is not None and event in EVENTS and reason_code in REASONS:
        context.event, context.reason_code = event, reason_code


def emit(event, **fields):
    """Ignore every unapproved field/value, including exception strings and identifiers."""
    try:
        if event not in EVENTS:
            return False
        context = current.get()
        status = fields.get('http_status')
        reason = fields.get('reason_code')
        operation = fields.get('operation', context.operation if context else 'system')
        request_id = fields.get('request_id', context.request_id if context else None)
        record = {'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                  'level': EVENTS[event], 'service': 'documind-api', 'event': event,
                  'operation': operation if operation in OPERATIONS else 'other',
                  'outcome': 'error' if EVENTS[event] in {'ERROR', 'CRITICAL'} else
                             'aborted' if event == 'upload.aborted' else
                             'success' if type(status) is int and 200 <= status < 300 else
                             'denied' if EVENTS[event] == 'WARNING' else 'success'}
        if isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id):
            record['request_id'] = request_id
        if type(status) is int and 100 <= status <= 599:
            record['http_status'] = status
        if reason in REASONS:
            record['reason_code'] = reason
        return writer.submit(json.dumps(record, separators=(',', ':'), ensure_ascii=True))
    except Exception:
        return False
