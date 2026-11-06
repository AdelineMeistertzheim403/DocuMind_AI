"""Explicit first-beta delivery policy. Standard library only, also shipped in flat bundles."""


class PublicBetaPolicyError(ValueError):
    pass


def validate_registration_config(environment, schema_revision, approved=False):
    """Validate only allowlisted fields; errors never contain environment values."""
    mode = environment.get('REGISTRATION_MODE', 'disabled')
    if mode in ('disabled', 'invite'):
        return mode
    if mode != 'public':
        raise PublicBetaPolicyError('Unsupported registration mode')
    if approved is not True:
        raise PublicBetaPolicyError('Public beta requires separate explicit approval')
    if schema_revision not in ('0007', '0008'):
        raise PublicBetaPolicyError('Public beta requires schema 0007 or 0008')
    limit = environment.get('PUBLIC_REGISTRATION_LIMIT')
    expected_limit = '10' if schema_revision == '0008' else '5'
    if isinstance(limit, bool) or str(limit) != expected_limit:
        raise PublicBetaPolicyError('Public beta requires the reviewed cumulative admission limit')
    if schema_revision == '0008':
        approval = environment.get('PUBLIC_REGISTRATION_REQUIRES_APPROVAL')
        receipts = environment.get('PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS')
        if approval is not True and str(approval).lower() not in ('true', '1'):
            raise PublicBetaPolicyError('Public beta requires explicit administrative account approval')
        if receipts is not False and str(receipts).lower() not in ('false', '0'):
            raise PublicBetaPolicyError('Ten-account beta requires the explicit PostgreSQL admission profile')
    for name in ('AI_ENABLED', 'OWNER_DEMO_ENABLED', 'LEGACY_API_ENABLED'):
        value = environment.get(name)
        if value is not False and (not isinstance(value, str) or value.lower() not in ('false', '0')):
            raise PublicBetaPolicyError('Public beta requires explicit disabled AI, owner demo and legacy API')
    return mode


# Executed in the reviewed API image: Settings validates SMTP/legal/BFF configuration.
# Only these non-secret, effective values are returned to the host, never model_dump().
SETTINGS_PROBE = (
    "import json; from backend.config import Settings; s=Settings(); "
    "assert not s.legacy_api_enabled; "
    "print(json.dumps({'REGISTRATION_MODE':s.registration_mode,"
    "'PUBLIC_REGISTRATION_LIMIT':s.public_registration_limit,'AI_ENABLED':s.ai_enabled,"
    "'OWNER_DEMO_ENABLED':s.owner_demo_enabled,'LEGACY_API_ENABLED':s.legacy_api_enabled,"
    "**({'PUBLIC_REGISTRATION_REQUIRES_APPROVAL':s.public_registration_requires_approval,"
    "'PUBLIC_REGISTRATION_USE_LIFECYCLE_RECEIPTS':s.public_registration_use_lifecycle_receipts}"
    " if s.public_registration_limit==10 else {})}))"
)
