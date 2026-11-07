"""Password hashing (bcrypt), signed login tokens (JWT) and password-reset tokens."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from . import config


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), pw_hash.encode("utf-8"))
    except ValueError:
        return False


def make_token(user_id: int, version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "v": version, "iat": now, "exp": now + timedelta(days=config.TOKEN_DAYS)},
                      config.JWT_SECRET, algorithm="HS256")


def read_token(token: str) -> tuple[int, int] | None:
    """(user id, token version), or None if the token is bad or expired. Tokens from before versions count as 0."""
    try:
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return int(claims["sub"]), int(claims.get("v", 0))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_reset_token() -> tuple[str, str]:
    """(token for the email link, SHA-256 hex to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_reset_token(token)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
