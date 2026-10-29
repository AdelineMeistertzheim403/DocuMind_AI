"""Fail closed until derived-data erasures have independent receipts."""
from fastapi import HTTPException


def require_derived_erasure_support(settings):
    if getattr(settings, 'lifecycle_durable_receipts_required', True):
        raise HTTPException(503, 'Suppression des données dérivées temporairement indisponible')
