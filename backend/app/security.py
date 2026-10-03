"""Password hashing (bcrypt) + signed login tokens (JWT)."""
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


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=config.TOKEN_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, config.JWT_SECRET, algorithm="HS256")


def read_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
