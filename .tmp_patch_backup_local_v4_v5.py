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

# Version constants
replace_once('BACKUP_FORMAT_VERSION = 5\n', 'BACKUP_FORMAT_VERSION = 4\nBACKUP_FORMAT_VERSION_WITH_KEYS = 5\n')

# BACKUP_FILES tuple: restore v4 and introduce v5.
block_old = (
"BACKUP_FILES = (\n"
"    'database.dump',\n"
"    'documents.tar.gz',\n"
"    'lifecycle.sqlite.tar.gz',\n"
"    LIFECYCLE_KEYS_ARCHIVE,\n"
"    'recovery-state.json',\n"
"    'integrity.json',\n"
")\n"
)
block_new = (
"BACKUP_FILES = (\n"
"    'database.dump',\n"
"    'documents.tar.gz',\n"
"    'lifecycle.sqlite.tar.gz',\n"
"    'recovery-state.json',\n"
"    'integrity.json',\n"
")\n\n\n"
"BACKUP_FILES_WITH_KEYS = BACKUP_FILES + (LIFECYCLE_KEYS_ARCHIVE,)\n"
)
if block_old not in text:
    raise SystemExit('Expected BACKUP_FILES block not found')
text = text.replace(block_old, block_new)

# create_backup signature
replace_once('def create_backup(compose, destination, env=None):\n', 'def create_backup(compose, destination, env=None, *, include_lifecycle_keys=False):\n')

# Ensure destination list uses correct mode (unchanged)

# Commands dict: remove always-on keys command and add conditional insertion.
needle = (
"        'lifecycle.sqlite.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
"            '-e', 'LIFECYCLE_CAPTURE_ID=' + capture_id,\n"
"            '--entrypoint', 'python', 'api', '-m', 'backend.lifecycle_snapshot'],\n"
"        'lifecycle-keys.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
"            '--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',\n"
"            '-czf', '-', '--no-recursion', 'keys/authentication.key', 'keys/admission.key'],\n"
)
count = text.count(needle)
if count != 1:
    raise SystemExit(f'Expected combined lifecycle+keys command block not found uniquely (found {count})')
replacement = (
"        'lifecycle.sqlite.tar.gz': ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
"            '-e', 'LIFECYCLE_CAPTURE_ID=' + capture_id,\n"
"            '--entrypoint', 'python', 'api', '-m', 'backend.lifecycle_snapshot'],\n"
)
text = text.replace(needle, replacement)

# Insert conditional command after commands dict creation.
insert_anchor = "    commands = {\n"
if text.count(insert_anchor) != 1:
    raise SystemExit('Expected commands dict anchor not found uniquely')

# Add conditional insertion after the dict literal closes.
close_anchor = "    }\n    with _offline_api_compose(compose, env) as offline:\n"
if text.count(close_anchor) != 1:
    raise SystemExit('Expected commands dict close anchor not found uniquely')
text = text.replace(
    close_anchor,
    "    }\n    if include_lifecycle_keys:\n"
    "        commands[LIFECYCLE_KEYS_ARCHIVE] = ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',\n"
    "            '--entrypoint', 'tar', 'api', '-C', '/app/lifecycle',\n"
    "            '-czf', '-', '--no-recursion', *LIFECYCLE_KEY_PATHS]\n"
    + "    with _offline_api_compose(compose, env) as offline:\n",
)

# Lifecycle keys validation block: wrap it in if include_lifecycle_keys.
keys_block = "    lifecycle_keys = {}\n    with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n"
if keys_block not in text:
    raise SystemExit('Expected lifecycle_keys validation block not found')
text = text.replace(
    "\n    lifecycle_keys = {}\n    with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n",
    "\n    lifecycle_keys = None\n    if include_lifecycle_keys:\n        lifecycle_keys = {}\n        with tarfile.open(destination / LIFECYCLE_KEYS_ARCHIVE, 'r:gz') as archive:\n",
)

# Manifest capture_scope: make it conditional.
replace_once(
"        'capture_scope': ['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state'],\n",
"        'capture_scope': (['postgresql', 'documents', 'lifecycle_sqlite', 'lifecycle_keys', 'recovery_state']\n"
"                          if include_lifecycle_keys\n"
"                          else ['postgresql', 'documents', 'lifecycle_sqlite', 'recovery_state']),\n",
)

# Manifest backup_format_version and lifecycle_keys field.
replace_once("        'backup_format_version': BACKUP_FORMAT_VERSION,\n",
             "        'backup_format_version': (BACKUP_FORMAT_VERSION_WITH_KEYS if include_lifecycle_keys else BACKUP_FORMAT_VERSION),\n")

# lifecycle_keys: include only when enabled.
replace_once("        'lifecycle_keys': lifecycle_keys,\n",
             "        **({'lifecycle_keys': lifecycle_keys} if include_lifecycle_keys else {}),\n")

# files list: choose v4/v5 files.
replace_once("        'files': list(BACKUP_FILES),\n",
             "        'files': list(BACKUP_FILES_WITH_KEYS if include_lifecycle_keys else BACKUP_FILES),\n")

# Also ensure checksums include the keys archive only when created.
# checksums loop uses commands keys; ok.

# Update return value remains.

# Update main() to accept flag and pass through.
if '--include-lifecycle-keys' not in text:
    replace_once("    parser.add_argument('--destination', type=Path, default=None,\n                         help='Backup output directory (default var/backups/<timestamp>).')\n",
                 "    parser.add_argument('--destination', type=Path, default=None,\n                         help='Backup output directory (default var/backups/<timestamp>).')\n"
                 "    parser.add_argument('--include-lifecycle-keys', action='store_true',\n"
                 "                        help='Capture lifecycle keys into lifecycle-keys.tar.gz (format v5)')\n")

replace_once("    create_backup(compose, destination)\n",
             "    create_backup(compose, destination, include_lifecycle_keys=args.include_lifecycle_keys)\n")

if text == orig:
    raise SystemExit('No changes applied')

path.write_text(text, encoding='utf-8')
print('Patched', path)