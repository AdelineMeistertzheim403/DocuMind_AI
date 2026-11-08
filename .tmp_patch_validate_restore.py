from pathlib import Path

path = Path('tools/validate_restore.py')
text = path.read_text(encoding='utf-8')
orig = text

def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one occurrence of {old!r} (found {count})")
    text = text.replace(old, new)

# Add lifecycle keys constants just after LAB_MARKER_CONTENT.
marker = 'LAB_MARKER_CONTENT = b"documind-isolated-restore-lab-v1\\n"\n\n\n'
if marker not in text:
    raise SystemExit('LAB_MARKER_CONTENT anchor not found')
if 'LIFECYCLE_KEYS_ARCHIVE' not in text:
    text = text.replace(
        marker,
        marker + 'LIFECYCLE_KEYS_ARCHIVE = "lifecycle-keys.tar.gz"\nLIFECYCLE_KEY_PATHS = ("keys/authentication.key", "keys/admission.key")\n\n\n'
    )

# Add extraction helper after _extract_archive.
anchor = 'def check_resurrection_denials'
if anchor not in text:
    raise SystemExit('check_resurrection_denials anchor not found')
if '_extract_lifecycle_keys' not in text:
    helper = (
"def _extract_lifecycle_keys(snapshot: Path, manifest: dict, lifecycle_root: Path) -> None:\n"
"    keys = manifest.get('lifecycle_keys')\n"
"    expected_names = set(LIFECYCLE_KEY_PATHS)\n"
"    if (not isinstance(keys, dict) or set(keys) != expected_names):\n"
"        raise ValueError('Lifecycle key inventory missing or invalid')\n"
"    keys_dir = lifecycle_root / 'keys'\n"
"    keys_dir.mkdir(parents=True, exist_ok=True, mode=0o700)\n"
"    with tarfile.open(snapshot / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n"
"        members = archive.getmembers()\n"
"        names = {member.name for member in members}\n"
"        if (names != expected_names\n"
"                or any(not member.isfile() or member.issym() or member.islnk() for member in members)):\n"
"            raise ValueError('Lifecycle key archive must contain exactly the two key files')\n"
"        for member in members:\n"
"            path = PurePosixPath(member.name)\n"
"            if path.is_absolute() or '..' in path.parts or not path.parts:\n"
"                raise ValueError('Unsafe lifecycle key archive member')\n"
"            expected = keys[member.name]\n"
"            if (not isinstance(expected, dict)\n"
"                    or type(expected.get('size')) is not int\n"
"                    or type(expected.get('mode')) is not int\n"
"                    or not isinstance(expected.get('sha256'), str)):\n"
"                raise ValueError('Lifecycle key inventory entry is invalid')\n"
"            mode = member.mode & 0o777\n"
"            if member.size != expected['size'] or mode != expected['mode']:\n"
"                raise ValueError('Lifecycle key metadata mismatch')\n"
"            source = archive.extractfile(member)\n"
"            if source is None:\n"
"                raise ValueError('Lifecycle key archive entry is unreadable')\n"
"            payload = source.read()\n"
"            if len(payload) != member.size or hashlib.sha256(payload).hexdigest() != expected['sha256']:\n"
"                raise ValueError('Lifecycle key checksum mismatch')\n"
"            target = keys_dir / Path(member.name).name\n"
"            with target.open('xb') as output:\n"
"                output.write(payload)\n"
"            if os.name == 'posix':\n"
"                target.chmod(mode)\n\n\n"
    )
    text = text.replace(anchor, helper + anchor)

# Call extraction helper in _restore.
call_anchor = "    lifecycle_root = target / \"lifecycle\"\n    _extract_archive(snapshot / \"lifecycle.sqlite.tar.gz\", lifecycle_root, documents=False)\n"
count = text.count(call_anchor)
if count != 1:
    raise SystemExit(f'Expected lifecycle archive extraction anchor not found uniquely (found {count})')
call = call_anchor + (
"\n    if int(manifest.get('backup_format_version', 0) or 0) >= 5:\n"
"        _extract_lifecycle_keys(snapshot, manifest, lifecycle_root)\n"
)
text = text.replace(call_anchor, call)

# Include keys restored count in quarantine report when available.
report_anchor = '            "lifecycle_stores_restored": 5,\n'
if report_anchor in text and 'lifecycle_keys_restored' not in text:
    text = text.replace(report_anchor, report_anchor + '            "lifecycle_keys_restored": 2 if int(manifest.get("backup_format_version", 0) or 0) >= 5 else 0,\n')

if text == orig:
    raise SystemExit('No changes applied')

path.write_text(text, encoding='utf-8')
print('Patched', path)