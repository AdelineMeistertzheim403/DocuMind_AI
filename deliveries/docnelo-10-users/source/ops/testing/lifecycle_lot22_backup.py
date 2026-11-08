"""Persistent encrypted backup experiment for explicitly marked synthetic data."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.lifecycle_durability import _read_private_key, canonical, separate_directories
from backend.lifecycle_registry import Registry


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware synthetic clock required')
    return value.astimezone(timezone.utc)


def _private_directory(path):
    path = Path(path).absolute()
    info = path.stat()
    if (os.name != 'posix' or path.resolve() != path or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError('Private synthetic directory required')
    return path


class PersistentSyntheticBackups:
    """Caller-driven synthetic clocks and copies; no scheduler or deletion."""

    def __init__(self, registry, copies, alerts, keys, active_key, root):
        root = Path(root).absolute()
        marker = root / '.synthetic-only'
        if (os.environ.get('PHASE154L22_SYNTHETIC') != 'isolated' or root.resolve() != root
                or not marker.is_file() or marker.read_bytes() != b'documind-synthetic-only\n'):
            raise ValueError('Explicitly marked isolated synthetic root required')
        if not isinstance(registry, Registry) or not isinstance(keys, dict) or not keys:
            raise ValueError('Synthetic registry and keyring required')
        self.registry = registry
        self.copies, self.alerts = _private_directory(copies), _private_directory(alerts)
        self.keys = {name: Path(path).absolute() for name, path in keys.items()}
        paths = [registry.path, self.copies, self.alerts, *self.keys.values()]
        if any(not path.is_relative_to(root) for path in paths):
            raise ValueError('Synthetic paths must remain inside the marked root')
        if any(not isinstance(name, str) or not re.fullmatch(r'[a-z0-9-]{1,32}', name) for name in self.keys):
            raise ValueError('Invalid synthetic key version')
        separate_directories([registry.path.parent, self.copies, self.alerts,
                              *sorted({path.parent for path in self.keys.values()})])
        registry._check()
        self.rotate(active_key)

    def rotate(self, version):
        if version not in self.keys:
            raise ValueError('Synthetic key version unavailable')
        _read_private_key(self.keys[version])
        self.active_key = version

    def _alert(self, at, reason):
        path = self.alerts / 'alerts.jsonl'
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ValueError('Unsafe synthetic alert file')
            line = (canonical({'at': _time(at).isoformat(), 'reason': reason}) + '\n').encode()
            if os.write(descriptor, line) != len(line):
                raise OSError('Incomplete synthetic alert')
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _read(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > 64 * 1024 * 1024):
                raise ValueError('Unsafe synthetic archive')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def restore(self, path, *, _temporary=False):
        path = Path(path).absolute()
        if path.parent != self.copies:
            raise ValueError('Synthetic archive outside copy directory')
        if path.name.endswith('.part') and not _temporary:
            raise ValueError('Incomplete synthetic archive cannot be restored')
        content = self._read(path)
        envelope = json.loads(content)
        if (not isinstance(envelope, dict) or set(envelope) != {'metadata', 'nonce', 'ciphertext'}
                or canonical(envelope).encode() != content):
            raise ValueError('Invalid synthetic archive envelope')
        metadata = envelope['metadata']
        if (not isinstance(metadata, dict) or set(metadata) != {
                'id', 'at', 'reason', 'version', 'key_version', 'registry_sha256'}
                or metadata['version'] != 2 or metadata['reason'] not in ('daily', 'administrative_update')
                or not isinstance(metadata['id'], str) or not isinstance(metadata['at'], str)
                or not isinstance(metadata['key_version'], str) or not isinstance(metadata['registry_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', metadata['registry_sha256'])):
            raise ValueError('Invalid synthetic archive metadata')
        identifier = str(UUID(metadata['id']))
        if identifier != metadata['id'] or path.name not in (identifier + '.json', identifier + '.part'):
            raise ValueError('Invalid synthetic archive identity')
        _time(datetime.fromisoformat(metadata['at']))
        key_path = self.keys.get(metadata['key_version'])
        if key_path is None:
            raise ValueError('Synthetic recovery key unavailable')
        nonce = base64.b64decode(envelope['nonce'], validate=True)
        ciphertext = base64.b64decode(envelope['ciphertext'], validate=True)
        if len(nonce) != 12:
            raise ValueError('Invalid synthetic archive nonce')
        plaintext = AESGCM(_read_private_key(key_path)).decrypt(nonce, ciphertext, canonical(metadata).encode())
        if hashlib.sha256(plaintext).hexdigest() != metadata['registry_sha256']:
            raise ValueError('Synthetic archive fingerprint mismatch')
        with sqlite3.connect(':memory:') as db:
            db.deserialize(plaintext)
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Synthetic archive database corrupt')
        return metadata, plaintext

    def _archives(self):
        result = []
        for path in sorted(self.copies.iterdir()):
            if path.name.endswith('.part'):
                raise ValueError('Interrupted synthetic archive requires review')
            if not path.name.endswith('.json'):
                raise ValueError('Unknown synthetic archive entry')
            result.append(self.restore(path)[0])
        return result

    def snapshot(self, at, reason):
        current = _time(at)
        if reason not in ('daily', 'administrative_update'):
            raise ValueError('Invalid synthetic backup trigger')
        try:
            previous = self._archives()
            if previous and current < max(_time(datetime.fromisoformat(item['at'])) for item in previous):
                raise ValueError('Synthetic clock moved backwards')
            with self.registry.connection() as source, sqlite3.connect(':memory:') as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Synthetic registry integrity failed')
                plaintext = target.serialize()
            identifier = str(uuid4())
            metadata = {'id': identifier, 'at': current.isoformat(), 'reason': reason, 'version': 2,
                        'key_version': self.active_key, 'registry_sha256': hashlib.sha256(plaintext).hexdigest()}
            nonce = os.urandom(12)
            ciphertext = AESGCM(_read_private_key(self.keys[self.active_key])).encrypt(
                nonce, plaintext, canonical(metadata).encode())
            envelope = canonical({'metadata': metadata, 'nonce': base64.b64encode(nonce).decode(),
                                  'ciphertext': base64.b64encode(ciphertext).decode()}).encode()
            temporary, final = self.copies / (identifier + '.part'), self.copies / (identifier + '.json')
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(descriptor, 'wb', closefd=False) as stream:
                    stream.write(envelope)
                    stream.flush()
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.restore(temporary, _temporary=True)
            os.link(temporary, final)
            os.unlink(temporary)
            directory = os.open(self.copies, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.restore(final)
            return final
        except (OSError, sqlite3.Error, ValueError, InvalidTag):
            self._alert(current, 'snapshot_failed')
            raise

    def daily(self, at):
        current = _time(at)
        try:
            archives = self._archives()
            if archives and current < max(_time(datetime.fromisoformat(item['at'])) for item in archives):
                raise ValueError('Synthetic clock moved backwards')
            if any(item['reason'] == 'daily' and _time(datetime.fromisoformat(item['at'])).date() == current.date()
                   for item in archives):
                return None
        except (OSError, sqlite3.Error, ValueError, InvalidTag):
            self._alert(current, 'snapshot_failed')
            raise
        return self.snapshot(current, 'daily')

    def after_administrative_update(self, at):
        return self.snapshot(at, 'administrative_update')

    def retention_plan(self, at):
        current = _time(at)
        return [{'id': item['id'], 'due_at': (_time(datetime.fromisoformat(item['at'])) + timedelta(days=7)).isoformat(),
                 'target_at': (_time(datetime.fromisoformat(item['at'])) + timedelta(days=8)).isoformat(),
                 'eligible_simulated': current >= _time(datetime.fromisoformat(item['at'])) + timedelta(days=7)}
                for item in self._archives()]
