"""Operator-only stdin probe INSIDE reviewed API. No database, network or writes."""
import hashlib
import json
from pathlib import Path
import sys

FILES = ('config.py', 'account_api.py', 'account_admin.py', 'account_models.py',
         'public_registration.py', 'main.py', 'authentication.py', 'lifecycle_admissions.py',
         'lifecycle_durability.py', 'lifecycle_registry.py', 'lifecycle_authenticated.py',
         'lifecycle_holds.py', 'lite_admissions.py', 'lite_authority.py', 'recovery_quarantine.py')

try:
    import backend.config as config
    root = Path(config.__file__).resolve().parent
    settings = config.Settings(_env_file=None)
    names = ('registration_mode', 'public_registration_limit', 'public_registration_per_hour',
             'public_verification_ttl_seconds', 'reset_ttl_seconds', 'public_challenge_difficulty',
             'application_profile', 'public_legal_ready', 'public_terms_version',
             'ai_enabled', 'owner_demo_enabled', 'legacy_api_enabled',
             'lifecycle_durable_receipts_required', 'lifecycle_synthetic_mutations_enabled',
             'max_upload_bytes', 'max_documents_per_owner', 'max_storage_bytes_per_owner', 'max_storage_bytes_total')
    files = {}
    for name in FILES:
        path = root / name
        files['backend/' + name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    print(json.dumps({'status': 'read_only_observed', 'settings': {name: getattr(settings, name, None) for name in names},
                      'source_sha256': files}, sort_keys=True))
except Exception:
    print('{"status":"NO-GO","reason":"api_reference_or_settings_unconfirmed"}')
    sys.exit(2)
