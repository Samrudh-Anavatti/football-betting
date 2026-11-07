"""Accounts: sign-in (admins by username, members by email), sign-up, password change and reset."""
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import AfterValidator, BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import current_user
from ..models import User
from ..ratelimit import check, client_ip, hit
from ..security import hash_password, hash_reset_token, make_token, new_reset_token, verify_password
from ..services import email

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HOUR = 3600
LOGIN_LIMIT = (10, 15 * 60)  # failed attempts per IP


def me_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email,
            "is_admin": u.is_admin}


def _signed_in(u: User) -> dict:
    return {"token": make_token(u.id, u.token_version), "user": me_dict(u)}


def _email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address")
    return v


def _password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Use at least 8 characters")
    if len(v.encode("utf-8")) > 72:  # bcrypt only reads the first 72 bytes
        raise ValueError("Use at most 72 characters")
    return v


Email = Annotated[str, AfterValidator(_email)]
Password = Annotated[str, AfterValidator(_password)]


def _set_password(u: User, pw: str) -> None:
    u.password_hash = hash_password(pw)
    u.token_version = u.token_version + 1
    u.reset_token_hash = u.reset_expires_at = None


class LoginIn(BaseModel):
    username: str  # a member's email or an admin's username
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    check("login", ip, *LOGIN_LIMIT)
    name = body.username.strip().lower()
    user = db.scalar(select(User).where(User.email == name if "@" in name else User.username == name))
    if user is None or not verify_password(body.password, user.password_hash):
        hit("login", ip, *LOGIN_LIMIT)
        raise HTTPException(401, "Wrong email or password")
    return _signed_in(user)


class SignupIn(BaseModel):
    email: Email
    password: Password
    adult: bool  # ticked "I'm 18 or over"


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    if not body.adult:
        raise HTTPException(422, "You need to be 18 or over to join")
    hit("signup", client_ip(request), 5, HOUR)
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "There's already an account with this email. Sign in, or reset your password.")
    user = User(username=f"m{secrets.token_hex(8)}", display_name=body.email.split("@")[0][:60], email=body.email,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return _signed_in(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return me_dict(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: Password


@router.put("/password")
def change_password(body: PasswordIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    ip = client_ip(request)
    check("login", ip, *LOGIN_LIMIT)
    user = db.get(User, user.id)
    if not verify_password(body.current_password, user.password_hash):
        hit("login", ip, *LOGIN_LIMIT)
        raise HTTPException(403, "Your current password is wrong")
    _set_password(user, body.new_password)
    db.commit()
    return _signed_in(user)  # this device stays signed in; every other one is signed out


class DeleteIn(BaseModel):
    password: str


@router.post("/delete-account", status_code=204)
def delete_account(body: DeleteIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    if user.is_admin:
        raise HTTPException(409, "Admin accounts are removed from the USERS setting, not here")
    ip = client_ip(request)
    check("login", ip, *LOGIN_LIMIT)
    if not verify_password(body.password, user.password_hash):
        hit("login", ip, *LOGIN_LIMIT)
        raise HTTPException(403, "Wrong password")
    db.delete(db.get(User, user.id))
    db.commit()


class ForgotIn(BaseModel):
    email: Email


def _send_reset(to: str, token: str) -> None:
    link = f"{config.SITE_URL}/reset#token={token}"  # a fragment, so the token never reaches a server or analytics
    mins = config.RESET_MINUTES
    intro = "Someone (hopefully you) asked to reset the password for your Football Predictions AI account."
    outro = (f"The link works once and expires in {mins} minutes. If you didn't ask for this, ignore this email: "
             "your password hasn't changed.")
    email.send(to, "Reset your password", f"{intro}\n\nChoose a new password here: {link}\n\n{outro}",
               f'<p>{intro}</p><p><a href="{link}">Choose a new password</a></p><p>{outro}</p>')


@router.post("/forgot")
def forgot(body: ForgotIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    hit("forgot", client_ip(request), 5, HOUR)
    hit("forgot-email", body.email, 3, HOUR)
    user = db.scalar(select(User).where(User.email == body.email))
    if user is not None:
        token, user.reset_token_hash = new_reset_token()
        user.reset_expires_at = datetime.utcnow() + timedelta(minutes=config.RESET_MINUTES)
        db.commit()
        tasks.add_task(_send_reset, user.email, token)  # after the response, so timing doesn't say who has an account
    return {"detail": "If there's an account with that email, we've sent it a link to reset the password."}


class ResetIn(BaseModel):
    token: str
    password: Password


@router.post("/reset")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    hit("reset", client_ip(request), 10, HOUR)
    user = db.scalar(select(User).where(User.reset_token_hash == hash_reset_token(body.token)))
    if user is None or user.reset_expires_at is None or user.reset_expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link has expired or was already used. Ask for a new one.")
    _set_password(user, body.password)
    db.commit()
    return _signed_in(user)
