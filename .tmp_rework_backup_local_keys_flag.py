import re
from pathlib import Path

path = Path('tools/backup_local.py')
text = path.read_text(encoding='utf-8')
orig = text

# 1) Version constants
text, n = re.subn(r'^BACKUP_FORMAT_VERSION\s*=\s*5\s*$',
                  'BACKUP_FORMAT_VERSION = 4\nBACKUP_FORMAT_VERSION_WITH_KEYS = 5',
                  text, flags=re.M)
if n != 1:
    raise SystemExit(f'Expected to update BACKUP_FORMAT_VERSION once (updated {n})')

# 2) BACKUP_FILES -> v4 + v5 variant
pattern = re.compile(r"BACKUP_FILES = \(\n(?:    .*\n)+\)\n", re.M)
match = pattern.search(text)
if not match:
    raise SystemExit('BACKUP_FILES block not found')
block = match.group(0)
if 'LIFECYCLE_KEYS_ARCHIVE' not in block:
    raise SystemExit('BACKUP_FILES block does not include keys; unexpected state')
new_block = (
"BACKUP_FILES = (\n"
"    'database.dump',\n"
"    'documents.tar.gz',\n"
"    'lifecycle.sqlite.tar.gz',\n"
"    'recovery-state.json',\n"
"    'integrity.json',\n"
")\n\n\n"
"BACKUP_FILES_WITH_KEYS = BACKUP_FILES + (LIFECYCLE_KEYS_ARCHIVE,)\n"
)
text = text[:match.start()] + new_block + text[match.end():]

# 3) create_backup signature
text, n = re.subn(r'^def create_backup\(compose, destination, env=None\):\s*$',
                  'def create_backup(compose, destination, env=None, *, include_lifecycle_keys=False):',
                  text, flags=re.M)
if n != 1:
    raise SystemExit(f'Expected to update create_backup signature once (updated {n})')

# 4) Remove unconditional keys command entry
text, n = re.subn(
    r"\n\s*'lifecycle-keys\.tar\.gz': \['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n\s*'--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',\n\s*'-czf', '-', '--no-recursion', 'keys/authentication\.key', 'keys/admission\.key'\],\n",
    "\n",
    text,
    flags=re.M,
)
if n != 1:
    raise SystemExit(f'Expected to remove lifecycle-keys command once (removed {n})')

# 5) Insert conditional command addition before offline capture loop
anchor = "    }\n    with _offline_api_compose(compose, env) as offline:\n"
if anchor not in text:
    raise SystemExit('Commands close anchor not found')
text = text.replace(
    anchor,
    "    }\n"
    "    if include_lifecycle_keys:\n"
    "        commands[LIFECYCLE_KEYS_ARCHIVE] = ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
    "            '--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',\n"
    "            '-czf', '-', '--no-recursion', *LIFECYCLE_KEY_PATHS]\n"
    "    with _offline_api_compose(compose, env) as offline:\n",
)

# 6) Replace lifecycle keys validation region with conditional block.
start = text.find("\n    lifecycle_keys = {}\n    with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE")
if start < 0:
    raise SystemExit('Lifecycle key validation start not found')
end = text.find("\n    recovery_payload =", start)
if end < 0:
    raise SystemExit('Lifecycle key validation end anchor not found')

validation_inner = (
"        lifecycle_keys = {}\n"
"        with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n"
"            members = archive.getmembers()\n"
"            names = {member.name for member in members}\n"
"            if (names != set(LIFECYCLE_KEY_PATHS)\n"
"                    or any(not member.isfile() or member.issym() or member.islnk() for member in members)):\n"
"                raise ValueError('Lifecycle key archive must contain exactly the two key files')\n"
"            for member in members:\n"
"                path = PurePosixPath(member.name)\n"
"                if path.is_absolute() or '..' in path.parts or not path.parts:\n"
"                    raise ValueError('Unsafe lifecycle key archive member')\n"
"                mode = member.mode & 0o777\n"
"                if mode & 0o077 or not mode & 0o400:\n"
"                    raise ValueError('Lifecycle key permissions are not restrictive')\n"
"                source = archive.extractfile(member)\n"
"                if source is None:\n"
"                    raise ValueError('Lifecycle key archive entry is unreadable')\n"
"                payload = source.read()\n"
"                if len(payload) != member.size:\n"
"                    raise ValueError('Lifecycle key archive payload size mismatch')\n"
"                lifecycle_keys[member.name] = {\n"
"                    'size': int(member.size),\n"
"                    'mode': int(mode),\n"
"                    'sha256': hashlib.sha256(payload).hexdigest(),\n"
"                }\n\n"
)
replacement_region = (
"\n    lifecycle_keys = None\n"
"    if include_lifecycle_keys:\n" + validation_inner
)
text = text[:start] + replacement_region + text[end:]

# 7) Manifest updates
text, n = re.subn(r"'backup_format_version': BACKUP_FORMAT_VERSION,",
                  "'backup_format_version': (BACKUP_FORMAT_VERSION_WITH_KEYS if include_lifecycle_keys else BACKUP_FORMAT_VERSION),",
                  text)
if n != 1:
    raise SystemExit(f'Expected to patch manifest backup_format_version once (patched {n})')

text, n = re.subn(
    r"'capture_scope': \['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state'\],",
    "'capture_scope': (['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state']\n"
    "                         if include_lifecycle_keys\n"
    "                         else ['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state']),",
    text,
)
if n != 1:
    raise SystemExit(f'Expected to patch capture_scope once (patched {n})')

text, n = re.subn(r"'lifecycle_keys': lifecycle_keys,",
                  "**({'lifecycle_keys': lifecycle_keys} if include_lifecycle_keys else {}),",
                  text)
if n != 1:
    raise SystemExit(f'Expected to patch lifecycle_keys field once (patched {n})')

text, n = re.subn(r"'files': list\(BACKUP_FILES\),",
                  "'files': list(BACKUP_FILES_WITH_KEYS if include_lifecycle_keys else BACKUP_FILES),",
                  text)
if n != 1:
    raise SystemExit(f'Expected to patch files list once (patched {n})')

# 8) CLI arg insertion after --destination block
if '--include-lifecycle-keys' not in text:
    lines = text.splitlines(True)
    for i, line in enumerate(lines):
        if "parser.add_argument('--destination'" in line:
            # Insert after the following help line.
            if i + 1 >= len(lines):
                raise SystemExit('Destination arg block truncated')
            insert_at = i + 2
            lines.insert(insert_at,
                         "    parser.add_argument('--include-lifecycle-keys', action='store_true',\n"
                         "                        help='Capture lifecycle keys into lifecycle-keys.tar.gz (format v5)')\n")
            text = ''.join(lines)
            break
    else:
        raise SystemExit('Destination argument line not found for insertion')

# Patch create_backup call
after = "    create_backup(compose, destination)\n"
if after not in text:
    raise SystemExit('create_backup call not found')
text = text.replace(after, "    create_backup(compose, destination, include_lifecycle_keys=args.include_lifecycle_keys)\n")

if text == orig:
    raise SystemExit('No changes applied')

path.write_text(text, encoding='utf-8')
print('Reworked', path)