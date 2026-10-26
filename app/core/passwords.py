"""Password hashing.

Argon2 is CPU-heavy. Callers in async code should run these functions in a
worker thread. A corrupt stored hash is a failed check, not an exception
the client can distinguish from a wrong password.
"""

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bool(_hasher.verify(password, password_hash))
    except Exception:
        return False


def dummy_password_hash() -> str:
    """Hash used when no real hash exists, so the check takes similar time."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    return _dummy_hash
