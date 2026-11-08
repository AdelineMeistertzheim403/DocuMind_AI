from pathlib import Path

path = Path('tools/verify_snapshot.py')
text = path.read_text(encoding='utf-8')
orig = text

def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one occurrence of {old!r} (found {count})")
    text = text.replace(old, new)

replace_once(
"V4_BACKUP_FILES = V3_BACKUP_FILES | {'recovery-state.json'}\n",
"V4_BACKUP_FILES = V3_BACKUP_FILES | {'recovery-state.json'}\nV5_BACKUP_FILES = V4_BACKUP_FILES | {'lifecycle-keys.tar.gz'}\n",
)

replace_once('if version not in {3, 4}:', 'if version not in {3, 4, 5}:')

replace_once(
"    expected_files = V4_BACKUP_FILES if version == 4 else V3_BACKUP_FILES\n",
"    expected_files = (V5_BACKUP_FILES if version == 5 else (V4_BACKUP_FILES if version == 4 else V3_BACKUP_FILES))\n",
)

replace_once(
"    expected_scope = (['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state']\n"
"                      if version == 4 else ['postgresql', 'documents', 'lifecycle_sqlite'])\n",
"    expected_scope = (\n"
"        ['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state'] if version == 5\n"
"        else (['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state'] if version == 4\n"
"              else ['postgresql', 'documents', 'lifecycle_sqlite'])\n"
"    )\n",
)

replace_once('    if version == 4:\n', '    if version in {4, 5}:\n')

# Insert lifecycle-keys verification before the verify_snapshot() definition.
anchor = '    return True\n'
# We need the *specific* return True that precedes def verify_snapshot.
needle = '    return True\ndef verify_snapshot'
count = text.count(needle)
if count != 1:
    raise SystemExit(f'Expected verify_capture terminal return anchor not found uniquely (found {count})')

insertion = (
"    if version == 5:\n"
"        expected_key_names = {'keys/authentication.key', 'keys/admission.key'}\n"
"        keys = manifest.get('lifecycle_keys')\n"
"        if (not isinstance(keys, dict) or set(keys) != expected_key_names):\n"
"            raise SystemExit('Lifecycle key inventory missing or invalid')\n"
"        for name, meta in keys.items():\n"
"            if (not isinstance(meta, dict)\n"
"                    or type(meta.get('size')) is not int or meta['size'] < 1\n"
"                    or type(meta.get('mode')) is not int\n"
"                    or meta['mode'] & 0o077 or not meta['mode'] & 0o400\n"
"                    or not isinstance(meta.get('sha256'), str)\n"
"                    or not re.fullmatch(r'[a-f0-9]{64}', meta['sha256'])):\n"
"                raise SystemExit('Lifecycle key inventory entry is invalid')\n"
"        with tarfile.open(snapshot / 'lifecycle-keys.tar.gz', 'r:gz') as archive:\n"
"            members = archive.getmembers()\n"
"            names = {member.name for member in members}\n"
"            if (names != expected_key_names\n"
"                    or any(not member.isfile() or member.issym() or member.islnk() for member in members)):\n"
"                raise SystemExit('Lifecycle key archive must contain exactly the two key files')\n"
"            for member in members:\n"
"                path = Path(member.name)\n"
"                if path.is_absolute() or '..' in path.parts:\n"
"                    raise SystemExit('Unsafe lifecycle key archive member')\n"
"                meta = keys[member.name]\n"
"                mode = member.mode & 0o777\n"
"                if member.size != meta['size'] or mode != meta['mode']:\n"
"                    raise SystemExit(f'Lifecycle key metadata mismatch: {member.name}')\n"
"                source = archive.extractfile(member)\n"
"                if source is None:\n"
"                    raise SystemExit(f'Lifecycle key missing: {member.name}')\n"
"                payload = source.read()\n"
"                if len(payload) != member.size or hashlib.sha256(payload).hexdigest() != meta['sha256']:\n"
"                    raise SystemExit(f'Lifecycle key checksum mismatch: {member.name}')\n"
"    return True\n\n"
)

text = text.replace(needle, insertion + 'def verify_snapshot')

if text == orig:
    raise SystemExit('No changes applied')

path.write_text(text, encoding='utf-8')
print('Patched', path)