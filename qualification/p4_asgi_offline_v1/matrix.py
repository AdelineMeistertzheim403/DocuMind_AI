"""The bounded P4 case matrix, without any execution."""


def cases():
    result = {
        'D03': (True, [('publish', 'quarantined', 'closed')]),
        'D04': (True, [('publish', 'quarantined', 'closed'), ('publish', 'ready', 'sentinel')]),
        'D05': (False, [('publish', 'ready', 'closed')]),
        'D06': (True, [('publish', 'ready', 'sentinel')]),
        'D07': (True, [('remove', None, 'closed')]),
        'D11-child': (True, [('remove', None, 'closed')]),
        'D12-symlink': (True, [('symlink', None, 'closed')]),
    }
    for kind in ('invalid-json', 'invalid-utf8', 'duplicate', 'boolean', 'unknown', 'extra', 'oversized'):
        result['D08-' + kind] = (True, [('publish', kind, 'closed')])
    for initial in (True, False):
        for obj, bad, good in (('latch', '000', '0440'), ('directory', '0700', '0750')):
            positive = 'sentinel' if initial else 'closed'
            result[f'D09-{obj}-{"ready" if initial else "quarantined"}'] = (
                initial, [('publish', 'ready', positive),
                          ('mode', obj + ':' + bad, 'closed'),
                          ('mode', obj + ':' + good, positive)])
    return result
