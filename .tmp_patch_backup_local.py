from pathlib import Path

path = Path('tools/backup_local.py')
text = path.read_text(encoding='utf-8')
orig = text

def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one occurrence of {old!r} (found {count})")
    text = text.replace(old, new)

replace_once('BACKUP_FORMAT_VERSION = 4', 'BACKUP_FORMAT_VERSION = 5')

marker = "RECOVERY_STATE_ALLOWED = {'ready', 'quarantined', 'serving_closed'}\n"
insert = marker + "\nLIFECYCLE_KEYS_ARCHIVE = 'lifecycle-keys.tar.gz'\nLIFECYCLE_KEY_PATHS = ('keys/authentication.key', 'keys/admission.key')\n"
replace_once(marker, insert)

replace_once("    'lifecycle.sqlite.tar.gz',\n", "    'lifecycle.sqlite.tar.gz',\n    LIFECYCLE_KEYS_ARCHIVE,\n")

needle = (
"        'lifecycle.sqlite.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
"            '-e', 'LIFECYCLE_CAPTURE_ID=' + capture_id,\n"
"            '--entrypoint', 'python', 'api', '-m', 'backend.lifecycle_snapshot'],\n"
)
count = text.count(needle)
if count != 1:
    raise SystemExit(f'Expected lifecycle sqlite command block not found uniquely (found {count})')
addition = needle + (
"        'lifecycle-keys.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
"            '--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',\n"
"            '-czf', '-', '--no-recursion', 'keys/authentication.key', 'keys/admission.key'],\n"
)
text = text.replace(needle, addition)

anchor = "        raise ValueError('Lifecycle capture identity or store inventory mismatch')\n\n"
count = text.count(anchor)
if count != 1:
    raise SystemExit(f'Expected lifecycle identity mismatch anchor not found uniquely (found {count})')
validation = anchor + (
"    lifecycle_keys = {}\n"
"    with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n"
"        members = archive.getmembers()\n"
"        names = {member.name for member in members}\n"
"        if (names != set(LIFECYCLE_KEY_PATHS)\n"
"                or any(not member.isfile() or member.issym() or member.islnk() for member in members)):\n"
"            raise ValueError('Lifecycle key archive must contain exactly the two key files')\n"
"        for member in members:\n"
"            path = PurePosixPath(member.name)\n"
"            if path.is_absolute() or '..' in path.parts or not path.parts:\n"
"                raise ValueError('Unsafe lifecycle key archive member')\n"
"            mode = member.mode & 0o777\n"
"            if mode & 0o077 or not mode & 0o400:\n"
"                raise ValueError('Lifecycle key permissions are not restrictive')\n"
"            source = archive.extractfile(member)\n"
"            if source is None:\n"
"                raise ValueError('Lifecycle key archive entry is unreadable')\n"
"            payload = source.read()\n"
"            if len(payload) != member.size:\n"
"                raise ValueError('Lifecycle key archive payload size mismatch')\n"
"            lifecycle_keys[member.name] = {\n"
"                'size': int(member.size),\n"
"                'mode': int(mode),\n"
"                'sha256': hashlib.sha256(payload).hexdigest(),\n"
"            }\n\n"
)
text = text.replace(anchor, validation)

replace_once(
"        'capture_scope': ['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state'],\n",
"        'capture_scope': ['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state'],\n",
)

manifest_anchor = "        'lifecycle_store_sha256': sqlite_metadata_hashes,\n"
count = text.count(manifest_anchor)
if count != 1:
    raise SystemExit(f'Expected lifecycle_store_sha256 manifest anchor not found uniquely (found {count})')
text = text.replace(manifest_anchor, manifest_anchor + "        'lifecycle_keys': lifecycle_keys,\n")

if text == orig:
    raise SystemExit('No changes applied')

path.write_text(text, encoding='utf-8')
print('Patched', path)