"""Password hashing + JWT encode/decode — zero-dependency except PyJWT.

Usage::

    from pptgenius.infrastructure.auth import hash_password, verify_password, create_token, decode_token

    pw_hash = hash_password("mysecret")
    assert verify_password("mysecret", pw_hash)

    token = create_token(user_id=1)
    payload = decode_token(token)  # {"user_id": 1, "exp": 1234567890}
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import jwt

from pptgenius.infrastructure.config import get_settings

_JWT_ALGO = "HS256"


def _secret_key() -> str:
    """Derive signing key from configured API key (stable across restarts)."""
    return get_settings().llm.api_key or "pptgenius-dev-secret"


# ── password ──────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """PBKDF2-SHA256 with 32-byte random salt. Returns ``salt$hash`` hex."""
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a ``salt$hash`` string."""
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────


def create_token(user_id: int, ttl_seconds: int = 86_400 * 7) -> str:
    """Create a signed JWT for the given user_id.  Default TTL: 7 days."""
    now = int(time.time())
    payload = {"user_id": user_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, _secret_key(), algorithm=_JWT_ALGO)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT.  Returns ``{"user_id": int, ...}`` or None."""
    try:
        return jwt.decode(token, _secret_key(), algorithms=[_JWT_ALGO])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
