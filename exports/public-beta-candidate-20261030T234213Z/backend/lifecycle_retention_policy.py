"""Non-destructive A09/A20 receipt expiry calculation; evidence is caller-attested."""
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from uuid import UUID


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')
    return value.astimezone(timezone.utc)


def _one_year(value):
    year = value.year + 1
    return value.replace(year=year, day=min(value.day, monthrange(year, value.month)[1]))


def receipt_expiry_plan(closed_at, at, neutralized_at, *, coverage_attested, exceptions_complete, holds):
    current, closed = _time(at), _time(closed_at)
    if closed > current:
        raise ValueError('Closure is in the future')
    if type(coverage_attested) is not bool or type(exceptions_complete) is not bool or not isinstance(holds, list):
        raise ValueError('Explicit evidence required')
    if not exceptions_complete:
        return {'simulation': True, 'eligible': False, 'reason': 'exceptions_incomplete'}
    for hold in holds:
        if not isinstance(hold, dict) or set(hold) != {'id', 'responsible_id', 'reason', 'scope_id',
                                                      'reviewed_at', 'review_at', 'ends_at', 'end_event'}:
            raise ValueError('Incomplete hold')
        for field in ('id', 'responsible_id', 'scope_id'):
            UUID(str(hold[field]))
        if hold['reason'] not in ('legal_hold', 'security', 'historical_review'):
            raise ValueError('Invalid hold reason')
        reviewed, review = _time(hold['reviewed_at']), _time(hold['review_at'])
        if reviewed > current or review <= reviewed or review > reviewed + timedelta(days=30) or review <= current:
            raise ValueError('Hold review required')
        if (hold['ends_at'] is None) == (hold['end_event'] is None):
            raise ValueError('Hold end required')
        if hold['ends_at'] is not None and _time(hold['ends_at']) <= current:
            raise ValueError('Expired hold requires decision')
        if hold['end_event'] is not None and hold['end_event'] not in ('legal_hold_lifted', 'incident_closed'):
            raise ValueError('Invalid hold end event')
    if holds:
        return {'simulation': True, 'eligible': False, 'reason': 'active_hold'}
    if not coverage_attested or neutralized_at is None:
        return {'simulation': True, 'eligible': False, 'reason': 'neutralization_evidence_required'}
    neutralized = _time(neutralized_at)
    if neutralized > current:
        raise ValueError('Neutralization is in the future')
    due = max(_one_year(closed), neutralized + timedelta(days=7))
    return {'simulation': True, 'eligible': current >= due, 'reason': 'eligible' if current >= due else 'not_due',
            'due_at': due.isoformat(), 'target_purge_at': (due + timedelta(days=7)).isoformat(),
            'coverage': 'operator_attested_not_provider_verified'}
