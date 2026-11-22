"""Membership through Whop: its hosted checkout to join, its billing page to manage or cancel, and a webhook that
keeps each member's access in step with Whop.

Access runs to `paid_until` (the end of the paid month, as Whop's membership has it) plus `GRACE_DAYS`, so a renewal
that fails still has a few days to be paid. A membership Whop reports as cancelled or expired ends access, and so does
a full refund or a dispute, which also cancel the membership. Each payment is kept in `payments` with the member's
billing country: VAT on digital services is owed where the customer is, and that's the evidence for it.

We tie a Whop membership to our account with `metadata.user_id`, which we put on the checkout and Whop copies to
the membership and its payments (the buyer's Whop email need not match ours).

The calls to Whop are small functions of their own so tests can replace them. API: https://docs.whop.com/api-reference
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import BillingEvent, Payment, User
from ..serialize import iso

log = logging.getLogger(__name__)

API_VERSION_DATE = "2026-11-20"  # the dated API version these calls and the webhook's payloads are written against
# A membership that still exists and could charge again.
LIVE_STATUSES = {"active", "trialing", "past_due", "unresolved"}
PAID_STATUSES = {"active", "trialing"}  # Whop: these grant access
PRICE_TTL = timedelta(hours=1)
_price_cache: dict = {"at": None, "value": None}


class WhopError(Exception):
    """Whop couldn't be reached or refused the call."""


class BadSignature(Exception):
    """A webhook delivery that Whop didn't sign."""


def ready() -> bool:
    return bool(config.WHOP_API_KEY and config.WHOP_WEBHOOK_SECRET and config.WHOP_PLAN_ID)


def _api(method: str, path: str, body: dict | None = None) -> dict:
    base = "https://sandbox-api.whop.com/api/v1" if config.WHOP_SANDBOX else "https://api.whop.com/api/v1"
    try:
        r = httpx.request(method, base + path, json=body, timeout=20, headers={
            "Authorization": f"Bearer {config.WHOP_API_KEY}", "Api-Version-Date": API_VERSION_DATE})
    except httpx.HTTPError as e:
        raise WhopError(f"{method} {path}: {e}") from e
    if r.status_code >= 400:
        raise WhopError(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r.json()


def _time(value: str | None) -> datetime | None:
    """Whop's ISO timestamps as naive UTC, like the rest of our dates."""
    if not value:
        return None
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (t - t.utcoffset()).replace(tzinfo=None) if t.utcoffset() is not None else t


def _minor(money) -> int:
    """Whop's amounts ({"amount": "3.99", "decimals": 2}, or a plain number on some objects) in pence."""
    if money is None:
        return 0
    if isinstance(money, dict):
        return int(Decimal(str(money.get("amount") or 0)).scaleb(int(money.get("decimals", 2))).to_integral_value())
    return int((Decimal(str(money)) * 100).to_integral_value())


# ── Access ───────────────────────────────────────────────────────────────────


def access_until(u: User) -> datetime | None:
    return u.paid_until + timedelta(days=config.GRACE_DAYS) if u.paid_until else None


def is_member(u: User, now: datetime | None = None) -> bool:
    return u.is_admin or (u.paid_until is not None and (now or datetime.utcnow()) <= access_until(u))


def has_subscription(u: User) -> bool:
    return u.subscription_status in LIVE_STATUSES


def membership_dict(u: User) -> dict:
    return {
        "member": is_member(u), "status": u.subscription_status, "cancelling": u.cancel_at_period_end,
        "paid_until": iso(u.paid_until), "access_until": iso(access_until(u)), "member_since": iso(u.member_since),
        "can_manage": u.subscription_id is not None,
    }


# ── Calls to Whop ────────────────────────────────────────────────────────────


def price() -> dict | None:
    """The monthly price as Whop has it, so our page can't disagree with checkout. Cached for an hour."""
    now = datetime.utcnow()
    if _price_cache["at"] and now - _price_cache["at"] < PRICE_TTL:
        return _price_cache["value"]
    plan = _api("GET", f"/plans/{config.WHOP_PLAN_ID}")
    money = plan.get("renewal_price")
    currency = money.get("currency") if isinstance(money, dict) else plan.get("currency")
    value = {"amount": _minor(money), "currency": (currency or "").lower(),
             "interval": "month" if plan.get("billing_period") == 30 else f"{plan.get('billing_period')} days"}
    _price_cache.update(at=now, value=value)
    return value


def create_checkout(u: User) -> str:
    """Whop's checkout page for the monthly plan, tagged with our account so the webhook knows whose it is."""
    return _api("POST", "/checkout_configurations", {
        "variant_id": config.WHOP_PLAN_ID, "metadata": {"user_id": str(u.id)},
        "redirect_url": f"{config.SITE_URL}/account?joined=1"})["purchase_url"]


def membership(membership_id: str) -> dict:
    return _api("GET", f"/memberships/{membership_id}")


def portal_url(u: User) -> str:
    """Whop's page where the member changes card or cancels."""
    url = membership(u.subscription_id).get("manage_url")
    if not url:
        raise WhopError(f"no manage_url on {u.subscription_id}")
    return url


def cancel_now(membership_id: str) -> None:
    _api("POST", f"/memberships/{membership_id}/cancel", {"cancel_at_period_end": False})


# ── Webhook ──────────────────────────────────────────────────────────────────


def signature(secret: str, msg_id: str, stamp: str, payload: bytes) -> str:
    """Standard Webhooks, as Whop signs them: HMAC-SHA256 of "id.timestamp.body" keyed with the secret's own bytes
    (prefix and all), in base64."""
    signed = f"{msg_id}.{stamp}.".encode() + payload
    return base64.b64encode(hmac.new(secret.encode(), signed, hashlib.sha256).digest()).decode()


def verify(payload: bytes, headers) -> None:
    """`webhook-signature` holds "v1,<signature>" (several, space-separated, while a secret is being rotated)."""
    msg_id, stamp, given = headers.get("webhook-id"), headers.get("webhook-timestamp"), headers.get("webhook-signature")
    if not (msg_id and stamp and given and stamp.isdigit()) or abs(time.time() - int(stamp)) > 300:
        raise BadSignature()
    want = signature(config.WHOP_WEBHOOK_SECRET, msg_id, stamp, payload)
    if not any(hmac.compare_digest(want, part.partition(",")[2]) for part in given.split() if part.startswith("v1,")):
        raise BadSignature()


def handle_webhook(payload: bytes, headers) -> None:
    """Verify and apply one event. Raises BadSignature if it isn't from Whop."""
    verify(payload, headers)
    event = json.loads(payload)
    with SessionLocal() as db:
        if db.get(BillingEvent, headers["webhook-id"]):
            return  # Whop retries, so the same delivery can arrive more than once
        handler = HANDLERS.get(event.get("type"))
        if handler:
            handler(db, event.get("data") or {})
        db.add(BillingEvent(id=headers["webhook-id"], type=str(event.get("type"))[:60]))
        db.commit()


def _user(db: Session, membership_id: str | None, metadata: dict | None, payment_id: str | None = None) -> User | None:
    """Whose membership or payment this is: the membership we already hold, else the account id we put on checkout,
    else the account an earlier payment was recorded for."""
    if membership_id and (u := db.scalar(select(User).where(User.subscription_id == membership_id))) is not None:
        return u
    user_id = str((metadata or {}).get("user_id") or "")
    if user_id.isdigit() and (u := db.get(User, int(user_id))) is not None:
        return u
    if payment_id and (p := db.scalar(select(Payment).where(Payment.invoice_id == payment_id))) is not None and p.user_id:
        return db.get(User, p.user_id)
    return None


def apply_membership(db: Session, m: dict) -> User | None:
    """Bring an account in step with its Whop membership."""
    u = _user(db, m.get("id"), m.get("metadata"))
    if u is None:
        log.warning("membership %s: no account (metadata %s)", m.get("id"), m.get("metadata"))
        return None
    status = m.get("status")
    if u.subscription_id and m["id"] != u.subscription_id and has_subscription(u) and status not in LIVE_STATUSES:
        return u  # an old membership ending doesn't change the current one
    u.subscription_id, u.subscription_status = m["id"], status
    u.cancel_at_period_end = bool(m.get("cancel_at_period_end")) and status in LIVE_STATUSES
    if status in PAID_STATUSES:
        u.paid_until = _time(m.get("current_period_end")) or u.paid_until
        u.member_since = u.member_since or datetime.utcnow()
    elif status in ("canceled", "expired"):
        u.paid_until = None  # Whop says access is over (the end of a cancelled month, or ended early)
    # past_due: paid_until stays, so the grace days run from the end of the paid month.
    return u


def _membership_changed(db: Session, m: dict) -> None:
    apply_membership(db, m)


def _payment_succeeded(db: Session, pay: dict) -> None:
    m = None
    if pay.get("membership_id"):
        try:  # the period this payment bought, and access even if the membership event is late
            m = membership(pay["membership_id"])
        except WhopError:
            log.exception("payment %s: couldn't read membership %s", pay.get("id"), pay["membership_id"])
    meta = (m or {}).get("metadata") or pay.get("metadata") or {}
    if _user(db, pay.get("membership_id"), meta) is None and pay.get("customer_email"):
        # Bought on Whop's own page rather than through our checkout: the email they paid with is all we have.
        by_email = db.scalar(select(User).where(User.email == pay["customer_email"].strip().lower()))
        meta = {"user_id": str(by_email.id)} if by_email is not None else meta
    u = apply_membership(db, {**m, "metadata": meta}) if m else None
    u = u or _user(db, pay.get("membership_id"), meta)
    country = ((pay.get("billing_address") or {}).get("country") or "").upper()[:2] or None
    if u is not None:
        u.billing_country = country or u.billing_country
    if db.scalar(select(Payment).where(Payment.invoice_id == pay["id"])) is None:
        db.add(Payment(
            invoice_id=pay["id"], user_id=u.id if u else None, amount=_minor(pay.get("total")),
            tax=_minor(pay.get("tax_amount")), currency=(pay.get("currency") or "").upper()[:3],
            billing_country=country or (u.billing_country if u else None),
            period_start=_time((m or {}).get("current_period_start")), period_end=_time((m or {}).get("current_period_end")),
            paid_at=_time(pay.get("paid_at")) or datetime.utcnow(),
        ))


def end_access(u: User) -> None:
    """Refund or dispute: no access from now, and no more charges."""
    if u.subscription_id and has_subscription(u):
        try:
            cancel_now(u.subscription_id)
        except WhopError:
            log.exception("couldn't cancel %s; cancel it in the Whop dashboard", u.subscription_id)
    u.paid_until = None
    u.cancel_at_period_end = False


def _refund_created(db: Session, refund: dict) -> None:
    pay = refund.get("payment") or {}
    if _minor(refund.get("amount")) < _minor(pay.get("total")) or refund.get("status") in ("failed", "canceled"):
        return  # a part refund changes nothing
    u = _user(db, (pay.get("membership") or {}).get("id"), pay.get("metadata"), pay.get("id"))
    if u is not None:
        end_access(u)


def _dispute_created(db: Session, dispute: dict) -> None:
    u = _user(db, None, None, (dispute.get("payment") or {}).get("id"))
    if u is not None:
        end_access(u)


HANDLERS = {
    "membership.activated": _membership_changed,
    "membership.updated": _membership_changed,
    "payment.succeeded": _payment_succeeded,
    "refund.created": _refund_created,
    "dispute.created": _dispute_created,
}
EVENTS = sorted(HANDLERS)  # what the Whop webhook should send


# ── Admin ────────────────────────────────────────────────────────────────────


def members_overview(db: Session) -> dict:
    now = datetime.utcnow()
    members = list(db.scalars(select(User).where(User.is_admin.is_(False), User.subscription_id.is_not(None))
                              .order_by(User.member_since.desc())))
    payments = list(db.scalars(select(Payment).order_by(Payment.paid_at.desc())))
    year_ago = now - timedelta(days=365)
    # Everyone who has signed up (an email and a password is all sign-up asks for), newest first.
    accounts = list(db.scalars(select(User).where(User.is_admin.is_(False), User.email.is_not(None))
                               .order_by(User.created_at.desc(), User.id.desc())))
    by_country: dict[tuple[str, str], dict] = {}
    for p in payments:
        if p.paid_at < year_ago:
            continue
        row = by_country.setdefault((p.billing_country or "??", p.currency), {
            "country": p.billing_country, "currency": p.currency, "payments": 0, "amount": 0, "tax": 0,
            "card_elsewhere": 0})
        row["payments"] += 1
        row["amount"] += p.amount
        row["tax"] += p.tax
        row["card_elsewhere"] += bool(p.card_country and p.billing_country and p.card_country != p.billing_country)
    return {
        "open": ready(),
        "signups": [{"id": u.id, "email": u.email, "created_at": iso(u.created_at), "member": is_member(u, now)}
                    for u in accounts],
        "signups_week": sum(bool(u.created_at and u.created_at >= now - timedelta(days=7)) for u in accounts),
        "active": sum(is_member(u, now) for u in members),
        "members": [{
            "id": u.id, "email": u.email, **membership_dict(u), "billing_country": u.billing_country,
            "card_country": u.card_country,
        } for u in members],
        "by_country": sorted(by_country.values(), key=lambda r: -r["amount"]),  # the last 12 months
        "payments": [payment_dict(p) for p in payments[:100]],
    }


def payment_dict(p: Payment) -> dict:
    return {
        "invoice_id": p.invoice_id, "user_id": p.user_id, "amount": p.amount, "tax": p.tax, "currency": p.currency,
        "billing_country": p.billing_country, "card_country": p.card_country, "period_start": iso(p.period_start),
        "period_end": iso(p.period_end), "paid_at": iso(p.paid_at),
    }
