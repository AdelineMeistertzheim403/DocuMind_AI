"""Manual, signed Lite authority. No keys, provisioning or approval defaults.

Linux ownership is part of provisioning. cryptography is an explicit prerequisite;
missing crypto/authority/recovery fails closed. No dependency is fetched at runtime.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
from uuid import UUID

from .lite_admissions import AdmissionOperation


class AuthorityError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise AuthorityError('Duplicate evidence field')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (TypeError, UnicodeError, ValueError):
        raise AuthorityError('Invalid authority evidence') from None


def uuid(value):
    try:
        if str(UUID(str(value))) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise AuthorityError('Canonical identity required') from None
    return value


def hex64(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise AuthorityError('Invalid evidence fingerprint')
    return value


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def secure_path(path, uid, *, private=True, directory=False):
    """Reject links, writable ancestry, wrong owner, hard links and unsafe modes."""
    if os.name != 'posix': raise AuthorityError('POSIX authority provisioning required')
    path = Path(path)
    if not path.is_absolute(): raise AuthorityError('Absolute authority path required')
    for parent in reversed((path.parent, *path.parents)):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise AuthorityError('Unsafe authority ancestry')
        if info.st_uid not in (0,uid):raise AuthorityError('Untrusted owner in authority ancestry')
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise AuthorityError('Writable authority ancestry')
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != uid
            or info.st_mode & (0o077 if private else 0o022)
            or not directory and info.st_nlink != 1):
        raise AuthorityError('Unsafe authority ownership or permissions')
    return path


def read(path, uid, *, private=True):
    path = secure_path(path, uid, private=private)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        current = path.lstat()
        if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                or not stat.S_ISREG(info.st_mode) or info.st_uid!=uid
                or info.st_mode & (0o077 if private else 0o022)
                or info.st_nlink != 1 or info.st_size > 4*1024*1024):
            raise AuthorityError('Authority file identity changed')
        return stream.read(4*1024*1024+1)


def write(path, raw, uid, *, replace=False, public=False):
    path = Path(path)
    secure_path(path.parent, uid, private=not public, directory=True)
    if path.exists() or path.is_symlink():
        secure_path(path, uid, private=not public)
        if not replace: raise AuthorityError('Evidence already exists')
    temporary = path.parent / ('.write-'+secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644 if public else 0o600)
    os.fchmod(fd,0o644 if public else 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    if replace:
        os.replace(temporary, path)
    else:
        # link is no-overwrite, then remove only our temporary link.
        os.link(temporary, path); temporary.unlink()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(directory)
    finally: os.close(directory)
    if read(path, uid, private=not public) != raw:
        raise AuthorityError('Evidence readback failed')


@contextmanager
def file_lock(directory, uid, *, private=True):
    import fcntl
    directory = secure_path(directory, uid, private=private, directory=True)
    path = directory/'authority.lock'
    try:
        if not path.exists() and os.geteuid()!=uid: raise AuthorityError('Application must initialize its own lock')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    except FileExistsError:
        pass
    secure_path(path, uid)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def sign(payload, key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return {'payload': payload, 'signature': Ed25519PrivateKey.from_private_bytes(key).sign(canonical(payload)).hex()}


def verify(envelope, public_key):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        if set(envelope) != {'payload', 'signature'}: raise ValueError()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(envelope['signature']), canonical(envelope['payload']))
    except Exception:
        raise AuthorityError('Unauthorized or altered evidence') from None
    return envelope['payload']


def operation_payload(op):
    if isinstance(op, DeletionOperation):
        return {key: value for key, value in asdict(op).items() if key not in ('state', 'progress')}
    # Commit to requester + invitation + Argon2 verifier without exporting them.
    binding = digest([op.invitation_digest, op.email_digest, op.password_hash])
    return {'operation_id': str(op.id), 'kind': 'admission', 'user_id': str(op.user_id),
            'owner_id': str(op.owner_id), 'binding': binding, 'terms_version': op.terms_version,
            'terms_sha256': op.terms_sha256, 'adult_declared': op.adult_declared,
            'terms_accepted': op.terms_accepted, 'accepted_at': op.accepted_at}


DELETION_KINDS = ('document_deletion_request', 'document_deletion_execution',
                  'account_closure_request', 'account_purge_execution')
RECOVERY_KINDS = ('recovery_inventory', 'recovery_reapplication', 'recovery_release', 'recovery_resolution')


@dataclass
class DeletionOperation:
    operation_id: str
    kind: str
    user_id: str
    owner_id: str
    target_id: str
    parent_id: str | None
    plan: dict
    requested_at: str
    state: str = 'awaiting_confirmation'
    progress: dict = field(default_factory=dict)


def validate_operation(value):
    if isinstance(value, dict) and value.get('kind') in RECOVERY_KINDS:
        from .lite_reconciliation import validate_recovery_operation
        validate_recovery_operation(value)
        return
    if isinstance(value, dict) and value.get('kind') in DELETION_KINDS:
        if set(value) != {'operation_id','kind','user_id','owner_id','target_id','parent_id','plan','requested_at'}:
            raise AuthorityError('Invalid deletion proposal')
        for key in ('operation_id','user_id','owner_id','target_id'):
            uuid(value[key])
        execution = value['kind'].endswith('_execution')
        if execution:
            uuid(value['parent_id'])
        elif value['parent_id'] is not None:
            raise AuthorityError('Request cannot have a parent')
        if value['kind'].startswith('account_') and value['target_id'] != value['user_id']:
            raise AuthorityError('Account target mismatch')
        from .lite_deletions import validate_plan
        validate_plan(value)
        try:
            if datetime.fromisoformat(value['requested_at']).utcoffset() is None: raise ValueError()
        except (TypeError, ValueError):
            raise AuthorityError('Deletion date required') from None
        return
    expected = {'operation_id','kind','user_id','owner_id','binding','terms_version','terms_sha256',
                'adult_declared','terms_accepted','accepted_at'}
    if not isinstance(value, dict) or set(value) != expected or value['kind'] != 'admission':
        raise AuthorityError('Unsupported operation contract')
    for field in ('operation_id','user_id','owner_id'): uuid(value[field])
    for field in ('binding','terms_sha256'): hex64(value[field])
    if (value['adult_declared'] is not True or value['terms_accepted'] is not True
            or not isinstance(value['terms_version'], str) or not 1 <= len(value['terms_version']) <= 40):
        raise AuthorityError('Incomplete acceptance evidence')
    try:
        if datetime.fromisoformat(value['accepted_at']).utcoffset() is None: raise ValueError()
    except (TypeError, ValueError): raise AuthorityError('UTC evidence date required') from None


def project(events, instance, cohort):
    """Verify the single authority history, including non-recyclable admissions."""
    operations = {}; count = 0; previous = ''
    for number, event in enumerate(events, 1):
        if set(event) != {'version','instance','cohort','sequence','previous','at','reference','request'}:
            raise AuthorityError('Invalid event fields')
        if (event['version'] != 1 or event['instance'] != instance or event['cohort'] != cohort
                or type(event['sequence']) is not int or event['sequence'] != number
                or event['previous'] != previous):
            raise AuthorityError('Conflicting sequence or domain')
        request = event['request']; validate_request(request, instance, cohort)
        op = request['operation']; key = op['operation_id']; phase = request['phase']
        before = operations.get(key)
        if before and before['operation'] != op: raise AuthorityError('Conflicting operation')
        if op['kind'] in RECOVERY_KINDS:
            from .lite_reconciliation import project_recovery
            project_recovery(operations, op, phase, request['counter'], count, number-1, previous)
            previous = digest(event)
            continue
        # A transition of an already-known operation may occur after an inventory;
        # insertion order alone cannot detect that its result became stale.
        for projected in operations.values():
            if projected['operation']['kind'] == 'recovery_inventory':
                projected['superseded'] = True
        if op['kind'] in DELETION_KINDS:
            if request['counter'] != count:
                raise AuthorityError('Deletion cannot change admission counter')
            if phase == 'authorize':
                if before:
                    raise AuthorityError('Duplicate deletion intent')
                if op['parent_id']:
                    parent = operations.get(op['parent_id'])
                    required = ('document_deletion_request' if op['kind'].startswith('document_')
                                else 'account_closure_request')
                    if (not parent or parent['phase'] != 'complete'
                            or parent['operation']['kind'] != required
                            or any(parent['operation'][k] != op[k] for k in ('user_id','owner_id','target_id'))):
                        raise AuthorityError('Execution requires completed matching request')
                    if any(e['operation'].get('parent_id') == op['parent_id'] for e in operations.values()):
                        raise AuthorityError('Conflicting execution')
                elif any(e['operation']['kind'] == op['kind'] and e['operation'].get('target_id') == op['target_id']
                         for e in operations.values()):
                    raise AuthorityError('Conflicting deletion request')
                operations[key] = {'operation': op, 'phase': phase, 'counter': count}
            elif phase == 'complete' and before and before['phase'] == 'authorize':
                before['phase'] = 'complete'
            else:
                raise AuthorityError('Invalid deletion transition')
            previous = digest(event)
            continue
        pending = [o for o in operations.values() if o['phase'] == 'reserve']
        if phase == 'reserve':
            if before or pending or request['counter'] != count or count >= 5:
                raise AuthorityError('Reservation conflict or capacity exhausted')
            operations[key] = {'operation': op, 'phase': 'reserve', 'counter': count+1}
        elif phase == 'result':
            if not before or before['phase'] != 'reserve' or request['counter'] != before['counter']:
                raise AuthorityError('Result without matching reservation')
            if request['facts'] != 'sql_commit_verified': raise AuthorityError('Unverified SQL result')
            count += 1; before['phase'] = 'result'
        elif phase == 'cancel':
            if (not before or before['phase'] != 'reserve' or request['counter'] != count
                    or request['facts'] != 'sql_absence_fenced'):
                raise AuthorityError('Cancellation lacks corroboration')
            before['phase'] = 'cancel'
        previous = digest(event)
    return operations, count, previous


def validate_request(request, instance, cohort):
    if (not isinstance(request, dict) or set(request) != {'version','instance','cohort','challenge','operation','phase','counter','facts'}
            or request['version'] != 1 or request['instance'] != instance or request['cohort'] != cohort
            or request['phase'] not in ('reserve','result','cancel','authorize','complete')
            or type(request['counter']) is not int or not 0 <= request['counter'] <= 5):
        raise AuthorityError('Invalid administrative proposal')
    hex64(request['challenge']); validate_operation(request['operation'])
    if request['operation']['kind'] in RECOVERY_KINDS:
        facts = {'authorize': 'recovery_plan_verified', 'complete': 'recovery_effect_verified'}
        if request['operation']['kind'] == 'recovery_inventory':
            facts = {'complete': 'recovery_inventory_verified'}
        elif request['operation']['kind'] == 'recovery_release':
            facts = {'authorize': 'recovery_validation_verified'}
        elif request['operation']['kind'] == 'recovery_resolution':
            facts = {'complete': 'recovery_obsolete_plan_verified'}
        if request['facts'] != facts.get(request['phase']):
            raise AuthorityError('Wrong recovery evidence phase')
        return
    if request['operation']['kind'] in DELETION_KINDS:
        facts = {'authorize': 'deletion_plan_verified', 'complete': 'deletion_effect_verified'}
        if request['facts'] != facts.get(request['phase']):
            raise AuthorityError('Wrong deletion evidence phase')
        return
    facts = {'reserve': 'invitation_and_counter_verified', 'result': 'sql_commit_verified', 'cancel': 'sql_absence_fenced'}
    if request['facts'] != facts.get(request['phase']): raise AuthorityError('Wrong evidence phase')


class OperatorLedger:
    """Operator domain + distinct encrypted recovery domain; neither is application state."""
    def __init__(self, directory, recovery, signing_key, recovery_key, *, instance, cohort, export_public_key):
        self.uid = os.geteuid() if os.name == 'posix' else -1
        self.directory = secure_path(directory, self.uid, directory=True)
        self.recovery = secure_path(recovery, self.uid, directory=True)
        self.instance = uuid(instance); self.cohort = uuid(cohort)
        paths = [self.directory, self.recovery, Path(signing_key).parent, Path(recovery_key).parent]
        if any(a == b or a in b.parents or b in a.parents for i,a in enumerate(paths) for b in paths[i+1:]):
            raise AuthorityError('Separate authority, recovery and key domains required')
        self.key = read(signing_key, self.uid); self.recovery_key = read(recovery_key, self.uid)
        if len(self.key) != 32 or len(self.recovery_key) != 32: raise AuthorityError('Invalid key material')
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.public = Ed25519PrivateKey.from_private_bytes(self.key).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.export_public = hex64(export_public_key)
        if self.export_public==self.public:raise AuthorityError('Operator and application export keys must differ')

    def _events(self):
        events = []
        for path in sorted(self.directory.glob('event-*.json')):
            if path.name != f'event-{len(events)+1:08d}.json': raise AuthorityError('Event sequence gap')
            events.append(verify(strict(read(path, self.uid)), self.public))
        project(events, self.instance, self.cohort)
        return events

    def _backup(self, events):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        head = digest(events[-1]) if events else ''
        if (self.recovery/'current.json').exists():
            old=verify(strict(read(self.recovery/'current.json',self.uid)),self.public)
            number=old.get('sequence')
            if type(number) is not int or not 0<=number<=len(events):
                raise AuthorityError('Refusing rollback of independent completeness bound')
            self._current(events[:number])
        payload = {'version':1, 'instance':self.instance, 'cohort':self.cohort, 'events':events}
        aad = canonical([self.instance, self.cohort, len(events), head])
        name = f'checkpoint-{len(events):08d}-{head or "genesis"}.enc'
        destination = self.recovery/name
        if not destination.exists():
            nonce = secrets.token_bytes(12)
            write(destination, nonce+AESGCM(self.recovery_key).encrypt(nonce, canonical(payload), aad), self.uid)
        raw = read(destination, self.uid)
        try: recovered = strict(AESGCM(self.recovery_key).decrypt(raw[:12], raw[12:], aad))
        except Exception: raise AuthorityError('Independent recovery verification failed') from None
        if recovered != payload: raise AuthorityError('Independent recovery differs')
        pointer = sign({'instance':self.instance, 'cohort':self.cohort,'sequence':len(events),
                        'head':head,'file':name,'cipher_sha256':hashlib.sha256(raw).hexdigest()}, self.key)
        write(self.recovery/'current.json', canonical(pointer), self.uid, replace=True)

    def initialize(self):
        with file_lock(self.directory, self.uid):
            if self._events() or (self.recovery/'current.json').exists(): raise AuthorityError('Authority already initialized')
            self._backup([])

    def _current(self, events):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        pointer = verify(strict(read(self.recovery/'current.json', self.uid)), self.public)
        head = digest(events[-1]) if events else ''
        if (pointer['instance'] != self.instance or pointer['cohort'] != self.cohort
                or pointer['sequence'] != len(events) or pointer['head'] != head
                or Path(pointer['file']).name != pointer['file']):
            raise AuthorityError('Registry is not the independently anchored current history')
        raw = read(self.recovery/pointer['file'], self.uid)
        if hashlib.sha256(raw).hexdigest() != pointer['cipher_sha256']: raise AuthorityError('Recovery copy altered')
        try:
            payload = strict(AESGCM(self.recovery_key).decrypt(raw[:12], raw[12:],
                canonical([self.instance,self.cohort,len(events),head])))
        except Exception: raise AuthorityError('Recovery unavailable') from None
        if payload != {'version':1,'instance':self.instance,'cohort':self.cohort,'events':events}:
            raise AuthorityError('Recovery history differs')

    def approve(self, proposal, *, confirmation, reference):
        request = verify(proposal, self.export_public)
        validate_request(request, self.instance, self.cohort)
        if confirmation != request['operation']['operation_id'] or not reference or len(reference)>64:
            raise AuthorityError('Explicit operator confirmation and reference required')
        with file_lock(self.directory, self.uid):
            events = self._events()
            # Retry only the identical last transition after a failed recovery write.
            same = next((e for e in events if e['request']['operation']['operation_id']==confirmation
                         and e['request']['phase']==request['phase']), None)
            if same:
                old={k:v for k,v in same['request'].items() if k!='challenge'}
                new={k:v for k,v in request.items() if k!='challenge'}
                if old!=new: raise AuthorityError('Contradictory duplicate proposal')
                if same != events[-1]:
                    self._current(events)
                else:
                    self._backup(events)
            else:
                self._current(events)
                event = {'version':1,'instance':self.instance,'cohort':self.cohort,
                         'sequence':len(events)+1,'previous':digest(events[-1]) if events else '',
                         'at':timestamp(),'reference':reference,'request':request}
                project([*events,event],self.instance,self.cohort)
                write(self.directory/f'event-{len(events)+1:08d}.json',canonical(sign(event,self.key)),self.uid)
                events.append(event)
                self._backup(events)  # No receipt before independent decrypt/readback.
            self._current(events)
            return self._view(events, request['challenge'])

    def _view(self, events, challenge):
        hex64(challenge)
        return sign({'version':1,'instance':self.instance,'cohort':self.cohort,'challenge':challenge,
                     'sequence':len(events),'head':digest(events[-1]) if events else '',
                     'at':timestamp(),'events':events}, self.key)

    def refresh(self, challenge, *, confirmation):
        if confirmation != challenge: raise AuthorityError('Explicit current-history review required')
        with file_lock(self.directory,self.uid):
            events=self._events(); self._current(events)
            return self._view(events,challenge)

    def attest_domains(self, application_domain, operator_domain, recovery_domain, *, reference, scope, confirmation):
        """A signed HUMAN review, not automatic physical-topology discovery."""
        domains=[uuid(application_domain),uuid(operator_domain),uuid(recovery_domain)]
        if len(set(domains))!=3 or confirmation!=self.instance or scope not in ('laboratory','deployment'):
            raise AuthorityError('Explicit independent-domain review required')
        uuid(reference)
        with file_lock(self.directory,self.uid):
            self._current(self._events())
            return sign({'version':1,'instance':self.instance,'cohort':self.cohort,
                'application_domain':domains[0],'operator_domain':domains[1],'recovery_domain':domains[2],
                'review_reference':reference,'scope':scope,'at':timestamp()},self.key)

    def recover(self):
        """Read/decrypt recovery only; never overwrite an authority or activate a service."""
        pointer=verify(strict(read(self.recovery/'current.json',self.uid)),self.public)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if Path(pointer['file']).name != pointer['file']: raise AuthorityError('Invalid recovery identity')
        raw=read(self.recovery/pointer['file'],self.uid)
        if hashlib.sha256(raw).hexdigest()!=pointer['cipher_sha256']: raise AuthorityError('Recovery copy altered')
        try: value=strict(AESGCM(self.recovery_key).decrypt(raw[:12],raw[12:],
            canonical([self.instance,self.cohort,pointer['sequence'],pointer['head']])))
        except Exception: raise AuthorityError('Recovery decryption failed') from None
        operations,count,head=project(value['events'],self.instance,self.cohort)
        if head!=pointer['head'] or len(value['events'])!=pointer['sequence']: raise AuthorityError('Recovery bound differs')
        return value

    def restore_empty(self, *, confirmation):
        """Recover proof registry into an explicitly NEW domain, never application data."""
        if confirmation!=self.instance:raise AuthorityError('Explicit registry recovery confirmation required')
        with file_lock(self.directory,self.uid):
            if any(p.name!='authority.lock' for p in self.directory.iterdir()):
                raise AuthorityError('Registry recovery destination must be empty')
            payload=self.recover()
            for index,event in enumerate(payload['events'],1):
                write(self.directory/f'event-{index:08d}.json',canonical(sign(event,self.key)),self.uid)
            restored=self._events();self._current(restored)
            if restored!=payload['events']:raise AuthorityError('Recovered registry differs')
            return {'status':'registry_recovered','sequence':len(restored),'opening_authorized':False}


class LocalOperations:
    """Application-private proposals and verifiers; never an approval authority."""
    def __init__(self, directory, uid):
        self.directory=secure_path(directory,uid,directory=True); self.uid=uid; self.path=self.directory/'operations.sqlite'
        if not self.path.exists():
            if os.geteuid()!=uid:raise AuthorityError('Application must initialize its own store')
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
        if os.geteuid()==uid:
            with self.connection() as db:
                db.execute('CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, invitation TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY CHECK(id=1), challenge TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS deletions(id TEXT PRIMARY KEY, target TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS retired_admissions(id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            with file_lock(self.directory,uid):pass

    @contextmanager
    def connection(self):
        secure_path(self.path,self.uid)
        administrative=os.geteuid()!=self.uid
        target=f'{self.path.as_uri()}?mode=ro&immutable=1' if administrative else str(self.path)
        db=sqlite3.connect(target,timeout=5,uri=administrative)
        try:
            with db:
                db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL')
                if not administrative:db.execute('PRAGMA secure_delete=ON')
                yield db
        finally:db.close()

    def challenge(self, *, renew=False):
        with self.connection() as db:
            if renew: db.execute('INSERT OR REPLACE INTO metadata VALUES(1,?)',(secrets.token_hex(32),))
            row=db.execute('SELECT challenge FROM metadata WHERE id=1').fetchone()
            if not row: raise AuthorityError('Application boot challenge unavailable')
            return row[0]

    def save(self, op):
        if os.geteuid()!=self.uid:raise AuthorityError('Administrator must not write application SQLite')
        data=asdict(op)
        for key in ('id','cohort_id','user_id','owner_id'):data[key]=str(data[key])
        with self.connection() as db:
            row=db.execute('SELECT payload FROM operations WHERE id=?',(str(op.id),)).fetchone()
            if row:
                old=strict(row[0])
                if any(old[k]!=v for k,v in data.items() if k not in ('state','issued_count','reserved_count')):
                    raise AuthorityError('Contradictory local operation')
            db.execute('INSERT INTO operations VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (str(op.id),op.invitation_digest,canonical(data).decode()))

    def all(self):
        with self.connection() as db:rows=db.execute('SELECT payload FROM operations').fetchall()
        result=[]
        for row in rows:
            data=strict(row[0])
            for key in ('id','cohort_id','user_id','owner_id'):data[key]=UUID(data[key])
            result.append(AdmissionOperation(**data))
        return result

    def deletions(self):
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='deletions'").fetchone():
                return []
            return [DeletionOperation(**strict(row[0])) for row in db.execute('SELECT payload FROM deletions')]

    def save_deletion(self, op):
        if os.geteuid() != self.uid:
            raise AuthorityError('Administrator must not write application SQLite')
        validate_operation(operation_payload(op))
        with self.connection() as db:
            row = db.execute('SELECT payload FROM deletions WHERE id=?', (op.operation_id,)).fetchone()
            if row and operation_payload(DeletionOperation(**strict(row[0]))) != operation_payload(op):
                raise AuthorityError('Deletion proposal changed')
            db.execute('INSERT INTO deletions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (op.operation_id, op.kind+':'+op.target_id, canonical(asdict(op)).decode()))

    def payloads(self):
        with self.connection() as db:
            retired = ({row[0]: strict(row[1]) for row in db.execute('SELECT id,payload FROM retired_admissions')}
                       if db.execute("SELECT 1 FROM sqlite_master WHERE name='retired_admissions'").fetchone() else {})
        return {**retired, **{str(o.id): operation_payload(o) for o in self.all()},
                **{o.operation_id: operation_payload(o) for o in self.deletions()}}

    def retire_user(self, user_id):
        """Keep acceptance commitments, not credentials for an erased account."""
        if os.geteuid() != self.uid:
            raise AuthorityError('Only application identity writes its proposal cache')
        operations = [op for op in self.all() if str(op.user_id) == str(user_id)]
        with self.connection() as db:
            for op in operations:
                db.execute('INSERT INTO retired_admissions VALUES(?,?)',
                           (str(op.id), canonical(operation_payload(op)).decode()))
                db.execute('DELETE FROM operations WHERE id=?', (str(op.id),))


def view(envelope, public_key, instance, cohort, challenge):
    value=verify(envelope,public_key)
    if (set(value)!={'version','instance','cohort','challenge','sequence','head','at','events'}
            or value['version']!=1 or value['instance']!=instance or value['cohort']!=cohort
            or value['challenge']!=challenge or type(value['sequence']) is not int):
        raise AuthorityError('Stale challenge or wrong authority domain')
    operations,count,head=project(value['events'],instance,cohort)
    if value['sequence']!=len(value['events']) or value['head']!=head: raise AuthorityError('Invalid completeness bound')
    return value,operations,count


def import_view(envelope, *, control, store, instance, cohort, public_key):
    """Root-only import; API cannot sign or update this administrative checkpoint."""
    if os.name!='posix' or os.geteuid()!=0: raise AuthorityError('Administrative import requires root')
    secure_path(control,0,private=False,directory=True)
    with file_lock(control,0,private=False):
        value,_,_=view(envelope,public_key,instance,cohort,store.challenge())
        local=store.payloads()
        if any(local.get(e['request']['operation']['operation_id'])!=e['request']['operation']
               for e in value['events'] if e['request']['operation']['kind'] not in RECOVERY_KINDS):
            raise AuthorityError('Confirmation does not match local proposal')
        target=Path(control)/'accepted.json'
        if target.exists():
            old=verify(strict(read(target,0,private=False)),public_key)
            if (old['instance']!=instance or old['cohort']!=cohort or value['sequence']<old['sequence']
                    or value['events'][:len(old['events'])]!=old['events']
                    or value['sequence']==old['sequence'] and value['head']!=old['head']
                    or digest(envelope)==digest(strict(read(target,0,private=False)))):
                raise AuthorityError('Replayed, conflicting or regressing confirmation')
        write(target,canonical(envelope),0,replace=True,public=True)


class OperationalConfirmation:
    """Persistent adapter; provisioning factory enforces actual API/admin identities."""
    def __init__(self, *, store, control, instance, cohort, public_key, renew=True):
        self.store=store;self.control=Path(control);self.instance=uuid(instance)
        self.cohort_id=UUID(uuid(cohort));self.public_key=hex64(public_key)
        self.nonce=self.store.challenge(renew=renew)

    def exclusive(self):return file_lock(self.store.directory,self.store.uid)

    def _proof(self):
        value,operations,count=view(strict(read(self.control/'accepted.json',0,private=False)),
            self.public_key,self.instance,str(self.cohort_id),self.nonce)
        return operations,count

    def find(self, invitation_digest, email_digest):
        op=next((o for o in self.store.all() if o.invitation_digest==invitation_digest and o.email_digest==email_digest),None)
        if op and (self.control/f'fence-{op.id}.json').exists():
            fence=strict(read(self.control/f'fence-{op.id}.json',0,private=False))
            if fence!={'instance':self.instance,'cohort':str(self.cohort_id),'operation':operation_payload(op)}:
                raise AuthorityError('Invalid administrative fence')
            op.state='uncertain'
            entry=self._entry(op)
            if entry and entry['phase']=='cancel':self.reconcile(op,{})
        if op and op.state=='uncertain':
            entry=self._entry(op)
            if entry and entry['phase']=='result':self.reconcile(op,{})
        return op

    def for_user(self,user_id):
        op=next((o for o in self.store.all() if o.user_id==user_id),None)
        if op and op.state=='uncertain':
            entry=self._entry(op)
            if entry and entry['phase']=='result':self.reconcile(op,{})
        if op and self.result_verified(op):op.state='admitted'
        return op

    def prepare(self,op):
        if op.cohort_id!=self.cohort_id:raise AuthorityError('Wrong application cohort')
        existing=self.find(op.invitation_digest,op.email_digest)
        if existing:
            if operation_payload(existing)!=operation_payload(op):raise AuthorityError('Conflicting duplicate proposal')
            return existing
        self.store.save(op);return op

    def _entry(self,op):
        local=next((o for o in self.store.all() if o.id==op.id),None)
        if local is None or operation_payload(local)!=operation_payload(op):
            raise AuthorityError('Unknown or contradictory local operation')
        operations,_=self._proof();entry=operations.get(str(op.id))
        if entry and entry['operation']!=operation_payload(op):raise AuthorityError('Proposal changed after confirmation')
        return entry

    def reservation_verified(self,op,issued_count):
        entry=self._entry(op)
        if entry is None:
            op.reserved_count=issued_count+1;op.state='reservation_pending';self.store.save(op);return False
        if entry['phase']!='reserve' or entry['counter']!=issued_count+1:raise AuthorityError('Reservation not current')
        op.reserved_count=entry['counter'];op.state='reservation_confirmed';self.store.save(op);return True

    def committed(self,op,issued_count):
        entry=self._entry(op)
        if not entry or entry['phase'] not in ('reserve','result') or entry['counter']!=issued_count:
            raise AuthorityError('SQL result conflicts with reservation')
        if op.issued_count not in (None,issued_count):raise AuthorityError('Conflicting SQL result')
        op.issued_count=issued_count;op.reserved_count=issued_count;op.state='result_pending';self.store.save(op)

    def result_verified(self,op):
        entry=self._entry(op)
        result=bool(entry and entry['phase']=='result' and op.issued_count==entry['counter'])
        if result:op.state='admitted';self.store.save(op)
        return result

    def counter_verified(self,issued_count):
        operations,count=self._proof()
        pending=[e['counter'] for e in operations.values() if e['phase']=='reserve']
        return type(issued_count) is int and issued_count in [count,*pending] and 0<=issued_count<=5

    def ready(self):
        try:self._proof();return True
        except (ValueError,OSError,ImportError):return False

    def uncertain(self,op):op.state='uncertain';self.store.save(op)

    def reconcile(self,op,sql_evidence):
        # Caller-supplied booleans cannot cancel. Only independently signed cancellation.
        entry=self._entry(op)
        if entry and entry['phase']=='cancel' and op.issued_count is None:
            op.state='cancelled';self.store.save(op);return
        if entry and entry['phase']=='result':
            op.issued_count=entry['counter'];op.reserved_count=entry['counter'];op.state='admitted'
            self.store.save(op);return
        raise AuthorityError('Independent cancellation required')


def export_proposal(adapter, operation_id, phase, session, export_key):
    """Administrative SQL read, signed with a key inaccessible to the API account."""
    from sqlalchemy import select
    from .auth import User
    from .account_models import PublicRegistrationQuota,AccountToken,WorkspaceMembership
    from .models import now
    with adapter.exclusive():
        mutation = next((o for o in adapter.store.deletions() if o.operation_id == str(operation_id)), None)
        if mutation:
            from .lite_deletions import export_deletion
            return export_deletion(adapter, mutation, phase, session, export_key)
        op=next((o for o in adapter.store.all() if str(o.id)==str(operation_id)),None)
        if op is None:raise AuthorityError('Unknown operation')
        quota=session.get(PublicRegistrationQuota,'public'); user=session.get(User,op.user_id)
        token=session.scalar(select(AccountToken).where(AccountToken.digest==op.invitation_digest,AccountToken.kind=='invite'))
        if (quota is None or token is None or hashlib.sha256(token.email.encode()).hexdigest()!=op.email_digest):
            raise AuthorityError('Missing or contradictory SQL evidence')
        count=quota.issued_count
        if phase=='reserve':
            expires=token.expires_at.replace(tzinfo=timezone.utc) if token.expires_at.tzinfo is None else token.expires_at
            if user or token.used_at or expires<=now() or quota.closed or op.reserved_count!=count+1:
                raise AuthorityError('Reservation SQL evidence invalid')
            facts='invitation_and_counter_verified'
        elif phase=='result':
            membership=session.get(WorkspaceMembership,op.user_id)
            if (not user or user.owner_id!=op.owner_id or user.registration_kind!='invite'
                    or user.disabled_at is not None or user.password_hash!=op.password_hash
                    or user.terms_version!=op.terms_version or not token.used_at
                    or not membership or membership.owner_id!=op.owner_id or count!=op.reserved_count):
                raise AuthorityError('SQL commit is not established')
            facts='sql_commit_verified'
        elif phase=='cancel':
            if user or token.used_at or op.reserved_count is None or count!=op.reserved_count-1 or op.issued_count is not None:
                raise AuthorityError('SQL absence is not established')
            fence=adapter.control/f'fence-{op.id}.json'
            value=canonical({'instance':adapter.instance,'cohort':str(adapter.cohort_id),'operation':operation_payload(op)})
            if fence.exists():
                if read(fence,0,private=False)!=value:raise AuthorityError('Conflicting cancellation fence')
            else:write(fence,value,0,public=True)
            facts='sql_absence_fenced'
        else:raise AuthorityError('Unsupported admission phase')
        session.rollback()
        payload={'version':1,'instance':adapter.instance,'cohort':str(adapter.cohort_id),
                 'challenge':adapter.nonce,'operation':operation_payload(op),'phase':phase,
                 'counter':count,'facts':facts}
        validate_request(payload,adapter.instance,str(adapter.cohort_id))
        return sign(payload,export_key)


def load_provision(settings, *, administrative=False):
    """A root-owned manifest is a trust decision, never an app-owned approved flag."""
    path=getattr(settings,'lite_authority_manifest',None)
    if path is None:return None
    if os.name!='posix':raise AuthorityError('Linux provisioning required')
    manifest=strict(read(path,0,private=False))
    if manifest.get('purpose') == 'laboratory_recovery':
        from .lite_release import runtime_manifest
        return runtime_manifest(settings, manifest, administrative=administrative)
    fields={'version','instance','cohort','api_uid','store','control','authority_public_key','export_private_key','export_public_key','database_sha256','independence'}
    if (set(manifest)!=fields or manifest['version']!=1 or type(manifest['api_uid']) is not int
            or manifest['api_uid']<=0 or manifest['cohort']!=str(settings.lite_cohort_id)
            or manifest['instance']!=str(settings.lite_instance_id)
            or manifest['database_sha256']!=hashlib.sha256(settings.database_url.encode()).hexdigest()):
        raise AuthorityError('Incomplete or contradictory authority provisioning')
    if os.geteuid()!=(0 if administrative else manifest['api_uid']):raise AuthorityError('Wrong administrative/application identity')
    store=secure_path(manifest['store'],manifest['api_uid'],directory=True)
    control=secure_path(manifest['control'],0,private=False,directory=True)
    if store==control or store in control.parents or control in store.parents:raise AuthorityError('Separate rights required')
    key=Path(manifest['export_private_key'])
    if not key.is_absolute() or store in key.parents or control in key.parents:
        raise AuthorityError('Separate administrative export key required')
    hex64(manifest['authority_public_key'])
    hex64(manifest['export_public_key'])
    if manifest['authority_public_key']==manifest['export_public_key']:
        raise AuthorityError('Distinct authority and application export keys required')
    independence=verify(manifest['independence'],manifest['authority_public_key'])
    if (set(independence)!={'version','instance','cohort','application_domain','operator_domain','recovery_domain','review_reference','scope','at'}
            or independence['version']!=1 or independence['instance']!=manifest['instance']
            or independence['cohort']!=manifest['cohort'] or independence['scope']!='deployment'
            or len({uuid(independence[k]) for k in ('application_domain','operator_domain','recovery_domain')})!=3):
        raise AuthorityError('Independent deployment review missing or unsuitable')
    uuid(independence['review_reference'])
    if administrative:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        public=Ed25519PrivateKey.from_private_bytes(read(key,0)).public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()
        if public!=manifest['export_public_key']:raise AuthorityError('Administrative export key mismatch')
    return manifest


def provisioned_adapter(settings):
    manifest=load_provision(settings)
    if manifest is None:return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:raise AuthorityError('Pinned authority crypto prerequisite unavailable') from None
    adapter = OperationalConfirmation(store=LocalOperations(manifest['store'],manifest['api_uid']),
        control=manifest['control'],instance=manifest['instance'],cohort=manifest['cohort'],
        public_key=manifest['authority_public_key'], renew=manifest.get('purpose') != 'laboratory_recovery')
    if manifest.get('purpose') == 'laboratory_recovery':
        adapter.nonce = manifest['current']['payload']['challenge']
    return adapter
