"""Shared FastAPI dependencies."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import access
from .database import get_db
from .models import User
from .security import read_token
from .services.billing import is_member


def optional_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User | None:
    """Whoever is signed in, or None: for public routes that show more to an account."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    claims = read_token(token) if token else None
    user = db.get(User, claims[0]) if claims else None
    if user is not None and claims[1] != user.token_version:  # issued before the last password change
        user = None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def member_user(user: User = Depends(current_user)) -> User:
    """Admins, and members whose paid month (plus the grace days) hasn't run out."""
    if not is_member(user):
        raise HTTPException(status_code=403, detail="Members only")
    return user


def require(feature: str):
    """A dependency for one gated feature (see `access.FEATURES`): 401 for a visitor, 403 for an account that
    needs a membership."""
    def dep(user: User | None = Depends(optional_user)) -> User:
        if access.can(user, feature):
            return user
        if user is None:
            raise HTTPException(status_code=401, detail="Create a free account to see this")
        raise HTTPException(status_code=403, detail="Members only")
    return dep
