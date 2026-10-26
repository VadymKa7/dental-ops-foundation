"""Caller identity passed into services.

Services do not read HTTP headers. A dependency builds this value after it
has loaded a live session.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID
    role: str
    session_id: uuid.UUID
