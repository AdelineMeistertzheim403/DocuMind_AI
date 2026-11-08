"""V5.1 archive policy; group access is scoped to the approved Public Beta identity.

Archive ownership is evidence, never an instruction to chown restored lab files.
"""
APPROVED_KEY_MODES = frozenset({0o400, 0o440, 0o600, 0o640})
PUBLIC_BETA_KEY_OWNER = (0, 1000)


def validate_key_permissions(mode, uid=None, gid=None):
    if type(mode) is not int or mode not in APPROVED_KEY_MODES:
        raise ValueError('Lifecycle key permissions are not restrictive')
    if mode & 0o040 and (
        type(uid) is not int or type(gid) is not int
        or (uid, gid) != PUBLIC_BETA_KEY_OWNER
    ):
        raise ValueError('Lifecycle key group ownership is not approved')


def validate_key_member(member, metadata=None):
    # Do not mask mode bits: setuid/setgid/sticky and execution must be refused.
    validate_key_permissions(member.mode, member.uid, member.gid)
    if metadata is not None:
        validate_key_permissions(metadata.get('mode'), metadata.get('uid'), metadata.get('gid'))
        if member.mode != metadata['mode']:
            raise ValueError('Lifecycle key mode mismatch')
        for field in ('uid', 'gid'):
            if field in metadata and (
                type(metadata[field]) is not int or getattr(member, field) != metadata[field]
            ):
                raise ValueError('Lifecycle key ownership metadata mismatch')
