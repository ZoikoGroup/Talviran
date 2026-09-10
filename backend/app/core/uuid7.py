"""Single centralized UUIDv7 generator.

Every module must import `new_uuid7` for generated primary keys rather than
reaching for `uuid.uuid4()` — DATA-001 requires opaque, time-ordered PKs, and
mixing generators silently breaks that property and bloats indexes.
"""

import uuid

import uuid_utils


def new_uuid7() -> uuid.UUID:
    """Returns a stdlib uuid.UUID (not uuid_utils.UUID) so it binds directly
    with SQLAlchemy's postgresql.UUID column type / asyncpg.
    """
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
