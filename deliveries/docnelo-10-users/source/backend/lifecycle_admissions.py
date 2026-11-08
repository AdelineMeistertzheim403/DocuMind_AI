"""Authenticated admission anchor; never opens or changes a quota."""
import hashlib
import hmac
import json
from pathlib import Path
from uuid import UUID

from .lifecycle_durability import ConfirmationStore, _read_private_key, canonical, separate_directories


def _validate(entries):
    if not isinstance(entries, list) or len(entries) > 5:
        raise ValueError('Invalid synthetic admission witness')
    users = []
    for sequence, entry in enumerate(entries, 1):
        if (not isinstance(entry, dict) or set(entry) != {'sequence', 'user_id'} or
                type(entry['sequence']) is not int or entry['sequence'] != sequence):
            raise ValueError('Incomplete admission sequence')
        user = str(UUID(entry['user_id']))
        if user != entry['user_id'] or user in users:
            raise ValueError('Contradictory admission witness')
        users.append(user)
    return entries


def synthetic_anchor(entries, key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('A separate synthetic anchor key is required')
    payload = {'version': 1, 'sequence': len(_validate(entries)),
               'witness_sha256': hashlib.sha256(canonical(entries).encode()).hexdigest()}
    return {'payload': payload,
            'tag': hmac.new(key, canonical(payload).encode(), hashlib.sha256).hexdigest()}


def inspect_witness(entries, anchor, key, database_count):
    if type(database_count) is not int or not 0 <= database_count <= 5:
        raise ValueError('Invalid restored counter')
    expected = synthetic_anchor(entries, key)
    if (not isinstance(anchor, dict) or set(anchor) != {'payload', 'tag'} or
            anchor['payload'] != expected['payload'] or
            not isinstance(anchor['tag'], str) or not hmac.compare_digest(anchor['tag'], expected['tag'])):
        raise ValueError('Admission anchor missing, stale or contradictory')
    count = len(entries)
    if count < database_count:
        raise ValueError('Witness older than database')
    return {'minimum_issued_count': max(count, database_count),
            'state': 'reconciliation_required' if count > database_count else 'observed_consistent',
            'keep_registration_closed': True, 'opening_authorized': False}


class AdmissionAnchor:
    def __init__(self, path, key):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError('Separate admission key required')
        self.store = ConfirmationStore(path)
        self.key = key

    def _payload(self, entries, state, user):
        entries = _validate(entries)
        if state not in ('settled', 'pending'):
            raise ValueError('Invalid admission state')
        if (not entries and (state != 'settled' or user is not None)
                or entries and user != entries[-1]['user_id']):
            raise ValueError('Invalid admission identity')
        return {'version': 2, 'domain': 'documind-admissions-v2', 'sequence': len(entries),
                'witness_sha256': hashlib.sha256(canonical(entries).encode()).hexdigest(),
                'state': state, 'user_id': user}

    def _tag(self, text):
        return hmac.new(self.key, text.encode(), hashlib.sha256).hexdigest()

    def initialize(self):
        self.store.initialize()
        payload = canonical(self._payload([], 'settled', None))
        with self.store.connection() as db:
            db.execute('CREATE TABLE admission_anchor (id INTEGER PRIMARY KEY CHECK(id=1), '
                       'payload TEXT NOT NULL, tag TEXT NOT NULL)')
            db.execute('INSERT INTO admission_anchor VALUES (1,?,?)', (payload, self._tag(payload)))
            db.execute('PRAGMA user_version=2')

    def _read(self, db, entries):
        if db.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('Admission anchor schema required')
        rows = db.execute('SELECT payload,tag FROM admission_anchor').fetchall()
        if len(rows) != 1:
            raise ValueError('Admission anchor missing')
        payload = json.loads(rows[0]['payload'])
        if (not isinstance(payload, dict) or set(payload) != {
                'version', 'domain', 'sequence', 'witness_sha256', 'state', 'user_id'}
                or canonical(payload) != rows[0]['payload']
                or not isinstance(rows[0]['tag'], str)
                or not hmac.compare_digest(rows[0]['tag'], self._tag(rows[0]['payload']))):
            raise ValueError('Admission anchor authentication failed')
        expected = self._payload(entries, payload['state'], payload['user_id'])
        if payload != expected:
            raise ValueError('Admission anchor stale or contradictory')
        return payload

    def check(self, entries):
        with self.store.connection() as db:
            return self._read(db, entries)

    def reserve(self, before, after):
        if (len(after) != len(before) + 1 or after[:-1] != before
                or not after or len(after) > 5):
            raise ValueError('Invalid admission transition')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._read(db, before)
            if current['state'] != 'settled':
                raise ValueError('Uncertain admission requires reconciliation')
            text = canonical(self._payload(after, 'pending', after[-1]['user_id']))
            db.execute('UPDATE admission_anchor SET payload=?,tag=? WHERE id=1', (text, self._tag(text)))
        if self.check(after)['state'] != 'pending':
            raise ValueError('Admission reservation not durable')

    def settle(self, entries, user):
        user = str(UUID(str(user)))
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._read(db, entries)
            if current['user_id'] != user or current['state'] not in ('pending', 'settled'):
                raise ValueError('Admission settlement conflicts with reservation')
            text = canonical(self._payload(entries, 'settled', user))
            db.execute('UPDATE admission_anchor SET payload=?,tag=? WHERE id=1', (text, self._tag(text)))
        if self.check(entries)['state'] != 'settled':
            raise ValueError('Admission settlement not durable')

    def inspect(self, entries, database_count):
        if type(database_count) is not int or not 0 <= database_count <= 5:
            raise ValueError('Invalid restored counter')
        anchor = self.check(entries)
        if len(entries) < database_count:
            raise ValueError('Witness older than database')
        return {'minimum_issued_count': max(len(entries), database_count),
                'state': ('reconciliation_required' if anchor['state'] == 'pending'
                          or len(entries) != database_count else 'observed_consistent'),
                'keep_registration_closed': True, 'opening_authorized': False}


class AdmissionCoordinator:
    def __init__(self, witness, anchor):
        self.witness = witness
        self.anchor = anchor

    def reserve(self, count, user):
        before = self.witness.admission_entries()
        current = self.anchor.check(before)
        if current['state'] != 'settled' or len(before) != count - 1:
            raise ValueError('Admission witness requires reconciliation')
        self.witness.reserve_admission(count, user)
        after = self.witness.admission_entries()
        if not after or after[-1] != {'sequence': count, 'user_id': str(UUID(str(user)))}:
            raise ValueError('Admission identity changed')
        self.anchor.reserve(before, after)

    def settle(self, count, user):
        entries = self.witness.admission_entries()
        if len(entries) != count:
            raise ValueError('Admission witness changed')
        self.anchor.settle(entries, user)

    def inspect(self, database_count):
        return self.anchor.inspect(self.witness.admission_entries(), database_count)


def configured_admissions(settings, coordinator):
    anchor_path = getattr(settings, 'lifecycle_admission_anchor_path', None)
    key_path = getattr(settings, 'lifecycle_admission_key_path', None)
    if not anchor_path or not key_path or not Path(anchor_path).is_absolute():
        raise ValueError('Separate admission anchor and key required')
    if getattr(settings, 'public_registration_limit', None) != 5:
        raise ValueError('Strict admission limit must be five')
    directories = [coordinator.registry.path.parent, coordinator.store.path.parent,
                   coordinator.authenticated.store.path.parent, Path(settings.lifecycle_authentication_key_path).parent,
                   Path(anchor_path).parent, Path(key_path).parent]
    hold_path = getattr(settings, 'lifecycle_holds_path', None)
    if hold_path:
        directories.append(Path(hold_path).parent)
    separate_directories([*directories, settings.storage_dir])
    return AdmissionCoordinator(coordinator.store, AdmissionAnchor(anchor_path, _read_private_key(key_path)))
