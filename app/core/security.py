"""Password hashing and JWT issuance/verification.

Kept deliberately small and dependency-light: bcrypt via passlib for
password hashing, python-jose for signing short-lived access tokens with
the app's JWT secret. No plaintext password ever leaves this module.
"""
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


def _to_bcrypt_bytes(plain: str) -> bytes:
    # bcrypt hard-caps input at 72 bytes; encode then truncate defensively so
    # multibyte passwords never raise. Max length is also enforced at the
    # schema layer.
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    """Issue a signed JWT. `subject` is the user id (as a string).

    The role is embedded for convenience/logging, but authorization NEVER
    trusts the token's role blindly at a security boundary -- deps.py
    re-loads the user from the database and reads the role from there, so
    a disabled account or a role change takes effect immediately.
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "role": role, "exp": expire, "iat": datetime.now(UTC)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the token payload, or None if it's invalid/expired/tampered."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
