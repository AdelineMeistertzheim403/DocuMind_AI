import secrets

from fastapi import HTTPException, Request


def trusted_gateway(request):
    key = request.headers.get('x-api-key', '')
    settings = request.app.state.settings
    service = settings.bff_service_key.get_secret_value()
    candidates = [service] if service else list(settings.api_keys)
    return bool(key and any(secrets.compare_digest(key.encode(), candidate.encode()) for candidate in candidates))


def secure_gateway(request: Request):
    if request.headers.get('x-documind-secure') != '1' or not trusted_gateway(request):
        raise HTTPException(403, 'HTTPS via le BFF est obligatoire')


def client_ip(request):
    return request.headers.get('x-documind-client-ip', request.client.host) if trusted_gateway(request) else request.client.host
