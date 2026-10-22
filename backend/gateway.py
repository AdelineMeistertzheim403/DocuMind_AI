import secrets

from fastapi import HTTPException, Request


def trusted_gateway(request):
    key = request.headers.get('x-api-key', '')
    settings = request.app.state.settings
    service = settings.bff_service_key.get_secret_value()
    return bool(
        key and service
        and secrets.compare_digest(key.encode(), service.encode())
    )


def secure_gateway(request: Request):
    if request.headers.get('x-documind-secure') != '1' or not trusted_gateway(request):
        from .security_audit import mark
        mark('gateway.authentication.failed', 'invalid_service_credential' if not trusted_gateway(request) else 'secure_transport_required')
        raise HTTPException(403, 'HTTPS via le BFF est obligatoire')


def client_ip(request):
    return request.headers.get('x-documind-client-ip', request.client.host) if trusted_gateway(request) else request.client.host
