"""Accounts come from env: USERS=sam,ivo and PASSWORD_<NAME>.

Passwords are reconciled on every startup, so rotating one = change the App
Service setting and restart.
"""
import os

from sqlalchemy import select

from .database import SessionLocal
from .models import User
from .security import hash_password, verify_password


def sync_users() -> None:
    names = [u.strip().lower() for u in os.getenv("USERS", "sam,ivo").split(",") if u.strip()]
    db = SessionLocal()
    try:
        for name in names:
            pw = os.getenv(f"PASSWORD_{name.upper()}", "changeme")
            user = db.scalar(select(User).where(User.username == name))
            if user is None:
                db.add(User(username=name, display_name=name.capitalize(), password_hash=hash_password(pw)))
            elif not verify_password(pw, user.password_hash):
                user.password_hash = hash_password(pw)
        db.commit()
    finally:
        db.close()
