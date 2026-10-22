"""Bounded in-process admission; production runs exactly one API process."""
import hashlib
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException
from sqlalchemy import select, text

from .account_models import Workspace
from .security_audit import mark


class RateLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.buckets = OrderedDict()

    def check(self, key, limit, window=60):
        key = hashlib.sha256(key.encode()).hexdigest()
        with self.lock:
            now = time.monotonic()
            values = [t for t in self.buckets.pop(key, []) if t > now-window]
            if len(values) >= limit:
                mark('rate_limit.exceeded', 'rate_limit')
                self.buckets[key] = values
                raise HTTPException(429, 'Limite de requêtes atteinte', headers={'Retry-After': str(window)})
            if len(self.buckets) >= 10000:
                # Never evict an active bucket to let a distributed flood bypass its limits.
                oldest, times = next(iter(self.buckets.items()))
                if times[-1] > now-3600:
                    mark('rate_limit.exceeded', 'rate_limit')
                    raise HTTPException(429, 'Capacité de limitation atteinte')
                self.buckets.pop(oldest)
            self.buckets[key] = [*values, now]


def lock_workspace(session, owner):
    # Global budget lock serializes creation/quota checks consistently with AI/deletions.
    if session.bind.dialect.name == 'sqlite':
        session.execute(text('UPDATE ai_budgets SET reserved_usd=reserved_usd WHERE id=\'development\''))
    else:
        session.execute(text("SELECT id FROM ai_budgets WHERE id='development' FOR UPDATE"))
    workspace = session.get(Workspace, owner)
    if workspace is None:
        workspace = Workspace(owner_id=owner)
        session.add(workspace)
        session.flush()
    session.scalar(select(Workspace).where(Workspace.owner_id == owner).with_for_update())
    return workspace
