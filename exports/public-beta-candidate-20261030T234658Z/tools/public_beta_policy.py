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
    if schema_revision != '0007':
        raise PublicBetaPolicyError('Public beta requires schema 0007')
    limit = environment.get('PUBLIC_REGISTRATION_LIMIT')
    if isinstance(limit, bool) or str(limit) != '5':
        raise PublicBetaPolicyError('Public beta requires exactly five cumulative admissions')
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
    "'OWNER_DEMO_ENABLED':s.owner_demo_enabled,'LEGACY_API_ENABLED':s.legacy_api_enabled}))"
)
