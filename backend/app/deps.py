"""Shared FastAPI dependencies."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import read_token


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    user_id = read_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user
