"""Versioned, bounded JSON metadata plus raw bytes on stdin; JSON only on stdout."""
import json
import re

MAX_INPUT = 10 * 1024 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
MAX_HEADER = 1024
MAX_PAGES = 200
MAX_CHARS = 1_000_000
ERRORS = {'invalid_document', 'resource_limit', 'sandbox_unavailable'}


def decode(raw):
    if isinstance(raw, bytes): raw = raw.decode('utf-8', errors='strict')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate_field')
            result[key] = value
        return result
    def invalid(value): raise ValueError('invalid_json')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {'version', 'job_id', 'extension', 'size', 'max_pages', 'max_chars'}:
        raise ValueError('invalid_request')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('invalid_request')
    if not isinstance(value['job_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['job_id']):
        raise ValueError('invalid_request')
    if value['extension'] not in ('.pdf', '.txt'): raise ValueError('invalid_request')
    for name, maximum in [('size', MAX_INPUT), ('max_pages', MAX_PAGES), ('max_chars', MAX_CHARS)]:
        if type(value[name]) is not int or not 1 <= value[name] <= maximum: raise ValueError('invalid_request')
    return value


def validate_response(value, request):
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('job_id') != request['job_id']): raise ValueError('invalid_response')
    if 'error' in value:
        if set(value) != {'version', 'job_id', 'error'} or value['error'] not in ERRORS:
            raise ValueError('invalid_response')
        return value
    if set(value) != {'version', 'job_id', 'pages'}: raise ValueError('invalid_response')
    pages = value['pages']
    if (not isinstance(pages, list) or not 1 <= len(pages) <= request['max_pages']
            or not all(isinstance(page, str) for page in pages)
            or sum(map(len, pages)) > request['max_chars'] or not any(page.strip() for page in pages)):
        raise ValueError('invalid_response')
    for page in pages: page.encode('utf-8', errors='strict')
    return value
