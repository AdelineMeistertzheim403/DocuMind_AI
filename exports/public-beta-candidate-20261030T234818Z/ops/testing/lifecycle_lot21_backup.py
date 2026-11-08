"""Clock-driven synthetic backup model, without a scheduler or deletion."""
from datetime import datetime, timedelta, timezone
import os
import re
import sqlite3
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.lifecycle_durability import canonical


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware test clock required')
    return value.astimezone(timezone.utc)


class SyntheticBackupSimulation:
    """Copies and alerts live only in this object; test keys remain separate."""

    def __init__(self, registry, keys, active_key):
        self.registry = registry
        self.keys = dict(keys)
        if any(not re.fullmatch(r'[a-z0-9-]{1,32}', name) or not isinstance(key, bytes) or len(key) != 32
               for name, key in self.keys.items()):
            raise ValueError('Invalid synthetic keyring')
        self.rotate(active_key)
        self.copies = []
        self.alerts = []
        self.daily_dates = set()

    def rotate(self, version):
        if version not in self.keys:
            raise ValueError('Synthetic key unavailable')
        self.active_key = version

    def snapshot(self, at, reason):
        current = _time(at)
        if reason not in ('daily', 'administrative_update'):
            raise ValueError('Invalid synthetic backup trigger')
        metadata = {'id': str(uuid4()), 'key_version': self.active_key,
                    'at': current.isoformat(), 'reason': reason, 'version': 1}
        try:
            with self.registry.connection() as source, sqlite3.connect(':memory:') as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Synthetic registry integrity failed')
                plaintext = target.serialize()
            nonce = os.urandom(12)
            ciphertext = AESGCM(self.keys[self.active_key]).encrypt(nonce, plaintext, canonical(metadata).encode())
            copy = {'metadata': metadata, 'nonce': nonce, 'ciphertext': ciphertext}
            self.restore(copy)
        except (OSError, sqlite3.Error, ValueError, InvalidTag):
            self.alerts.append({'reason': 'snapshot_failed', 'at': current.isoformat()})
            raise
        self.copies.append(copy)
        return copy

    def daily(self, at):
        current = _time(at)
        if current.date() in self.daily_dates:
            return None
        copy = self.snapshot(current, 'daily')
        self.daily_dates.add(current.date())
        return copy

    def after_administrative_update(self, at):
        return self.snapshot(at, 'administrative_update')

    def restore(self, copy):
        metadata = copy['metadata']
        version = metadata['key_version']
        if version not in self.keys:
            raise ValueError('Synthetic recovery key unavailable')
        plaintext = AESGCM(self.keys[version]).decrypt(copy['nonce'], copy['ciphertext'], canonical(metadata).encode())
        with sqlite3.connect(':memory:') as db:
            db.deserialize(plaintext)
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Synthetic copy integrity failed')
        return plaintext

    def retention_plan(self, at):
        current = _time(at)
        return [{'id': copy['metadata']['id'],
                 'due_at': (_time(datetime.fromisoformat(copy['metadata']['at'])) + timedelta(days=7)).isoformat(),
                 'target_at': (_time(datetime.fromisoformat(copy['metadata']['at'])) + timedelta(days=8)).isoformat(),
                 'eligible_simulated': current >= _time(datetime.fromisoformat(copy['metadata']['at'])) + timedelta(days=7)}
                for copy in self.copies]
