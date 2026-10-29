"""Synthetic-only encrypted SQLite backup experiment. No scheduler or deletion."""
import os
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.lifecycle_registry import Registry

MAGIC = b'DOCUMIND-SYNTHETIC-REGISTRY-1'


def encrypted_snapshot(registry, key):
    if not isinstance(registry, Registry) or not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('Synthetic registry and 256-bit key required')
    with registry.connection() as source, sqlite3.connect(':memory:') as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Registry integrity failed')
        plaintext = target.serialize()
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def verify_snapshot(ciphertext, key):
    if not isinstance(key, bytes) or len(key) != 32 or not ciphertext.startswith(MAGIC):
        raise ValueError('Invalid synthetic backup')
    nonce = ciphertext[len(MAGIC):len(MAGIC) + 12]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext[len(MAGIC) + 12:], MAGIC)
    with sqlite3.connect(':memory:') as db:
        db.deserialize(plaintext)
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Registry integrity failed')
    return plaintext
