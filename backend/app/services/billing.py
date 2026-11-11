"""Membership through Stripe: Checkout to join, the Customer Portal to manage or cancel, and a webhook that keeps
each member's access in step with Stripe.

Access runs to `paid_until` (the end of the last paid month, from `invoice.paid`) plus `GRACE_DAYS`, so a failed
renewal and a cancellation end it the same way, and a renewal that's paid late just extends it again. Only the
webhook moves `paid_until` forward; a refund, a dispute or a fraud warning ends access at once and cancels the
subscription. Each paid invoice is kept in `payments` with the member's billing and card countries: VAT on digital
services is owed where the customer is, and that's the evidence for it.

The Stripe calls are small functions of their own so tests can replace them.
"""
import json
import logging
from datetime import datetime, timedelta

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import Payment, StripeEvent, User
from ..serialize import iso

log = logging.getLogger(__name__)

INTEGRATION_ID = "membership-monthly-qhzvrkdm"  # tags our Checkout Sessions in the Dashboard
# A subscription that still exists and could charge again ("incomplete" was never paid and expires in a day).
LIVE_STATUSES = {"active", "trialing", "past_due", "unpaid", "paused"}
PRICE_TTL = timedelta(hours=1)
_price_cache: dict = {"at": None, "value": None}


def ready() -> bool:
    return bool(config.STRIPE_API_KEY and config.STRIPE_WEBHOOK_SECRET and config.STRIPE_PRICE_ID)


def _client() -> stripe.StripeClient:
    return stripe.StripeClient(config.STRIPE_API_KEY, max_network_retries=2)


def _ts(seconds: int | None) -> datetime | None:
    return datetime.utcfromtimestamp(seconds) if seconds else None


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
        "can_manage": u.stripe_customer_id is not None,
    }


# ── Calls to Stripe ──────────────────────────────────────────────────────────


def price() -> dict | None:
    """The monthly price as Stripe has it, so our page can't disagree with checkout. Cached for an hour."""
    now = datetime.utcnow()
    if _price_cache["at"] and now - _price_cache["at"] < PRICE_TTL:
        return _price_cache["value"]
    p = _client().v1.prices.retrieve(config.STRIPE_PRICE_ID)
    value = {"amount": p["unit_amount"], "currency": p["currency"], "interval": (p.get("recurring") or {}).get("interval")}
    _price_cache.update(at=now, value=value)
    return value


def create_checkout(u: User) -> str:
    """A Checkout Session for the monthly membership; makes the Stripe customer first if there isn't one."""
    client = _client()
    if u.stripe_customer_id is None:
        u.stripe_customer_id = client.v1.customers.create(params={"email": u.email, "metadata": {"user_id": str(u.id)}}).id
    params = {
        "mode": "subscription", "customer": u.stripe_customer_id, "client_reference_id": str(u.id),
        "line_items": [{"price": config.STRIPE_PRICE_ID, "quantity": 1}],
        # The billing address is our location evidence for tax, so ask for it; take a fresh one each time.
        "billing_address_collection": "required", "customer_update": {"address": "auto"},
        "success_url": f"{config.SITE_URL}/account?joined=1", "cancel_url": f"{config.SITE_URL}/membership",
        "integration_identifier": INTEGRATION_ID,
    }
    if config.STRIPE_AUTOMATIC_TAX:
        params["automatic_tax"] = {"enabled": True}
    return client.v1.checkout.sessions.create(params=params).url


def portal_url(u: User) -> str:
    return _client().v1.billing_portal.sessions.create(
        params={"customer": u.stripe_customer_id, "return_url": f"{config.SITE_URL}/account"}).url


def cancel_now(subscription_id: str) -> None:
    _client().v1.subscriptions.cancel(subscription_id)


def card_country(subscription_id: str) -> str | None:
    sub = _client().v1.subscriptions.retrieve(subscription_id, params={"expand": ["default_payment_method"]})
    pm = sub.get("default_payment_method")
    return ((pm or {}).get("card") or {}).get("country") if not isinstance(pm, str) else None


def payment_method_country(payment_method_id: str) -> str | None:
    pm = _client().v1.payment_methods.retrieve(payment_method_id)
    return (pm.get("card") or {}).get("country")


def charge_customer(charge_id: str) -> str | None:
    return _client().v1.charges.retrieve(charge_id).get("customer")


# ── Webhook ──────────────────────────────────────────────────────────────────


def handle_webhook(payload: bytes, signature: str | None) -> None:
    """Verify and apply one event. Raises stripe.SignatureVerificationError if it isn't from Stripe."""
    stripe.WebhookSignature.verify_header(payload, signature, config.STRIPE_WEBHOOK_SECRET, tolerance=300)
    event = json.loads(payload)
    with SessionLocal() as db:
        if db.get(StripeEvent, event["id"]):
            return  # Stripe sends some events more than once
        handler = HANDLERS.get(event["type"])
        if handler:
            handler(db, event["data"]["object"], event["data"].get("previous_attributes") or {})
        db.add(StripeEvent(id=event["id"], type=event["type"]))
        db.commit()


def _user(db: Session, customer_id: str | None) -> User | None:
    return db.scalar(select(User).where(User.stripe_customer_id == customer_id)) if customer_id else None


def _country(address: dict | None) -> str | None:
    return (address or {}).get("country")


def _checkout_completed(db: Session, session: dict, _prev: dict) -> None:
    if session.get("mode") != "subscription" or session.get("payment_status") not in ("paid", "no_payment_required"):
        return  # access comes from invoice.paid anyway; this adds where the member is
    u = _user(db, session.get("customer"))
    if u is None and str(session.get("client_reference_id") or "").isdigit():
        u = db.get(User, int(session["client_reference_id"]))
        if u is not None:
            u.stripe_customer_id = session.get("customer")
    if u is None:
        log.warning("checkout %s: no account for customer %s", session.get("id"), session.get("customer"))
        return
    u.subscription_id = session.get("subscription") or u.subscription_id
    u.billing_country = _country((session.get("customer_details") or {}).get("address")) or u.billing_country
    if u.subscription_id:
        try:
            u.card_country = card_country(u.subscription_id) or u.card_country
        except stripe.StripeError:
            log.exception("couldn't read the card country for %s", u.subscription_id)
    # The first invoice.paid often arrives before this event, so fill in where that payment came from.
    for p in db.scalars(select(Payment).where(Payment.stripe_customer_id == u.stripe_customer_id)):
        p.billing_country = p.billing_country or u.billing_country
        p.card_country = p.card_country or u.card_country


def _subscription_changed(db: Session, sub: dict, prev: dict) -> None:
    u = _user(db, sub.get("customer"))
    if u is None:
        return
    if (u.subscription_id and sub["id"] != u.subscription_id and has_subscription(u)
            and sub.get("status") not in LIVE_STATUSES):
        return  # an old subscription ending doesn't change the current one
    u.subscription_id, u.subscription_status = sub["id"], sub.get("status")
    u.cancel_at_period_end = bool(sub.get("cancel_at_period_end") or sub.get("cancel_at")) and sub.get("status") != "canceled"
    pm = sub.get("default_payment_method")
    if "default_payment_method" in prev and isinstance(pm, str):  # they changed card in the portal
        try:
            u.card_country = payment_method_country(pm) or u.card_country
        except stripe.StripeError:
            log.exception("couldn't read the card country for %s", pm)


def _invoice_paid(db: Session, inv: dict, _prev: dict) -> None:
    u = _user(db, inv.get("customer"))
    lines = (inv.get("lines") or {}).get("data") or []
    start = min((ln["period"]["start"] for ln in lines if ln.get("period")), default=None)
    end = max((ln["period"]["end"] for ln in lines if ln.get("period")), default=None)
    if db.scalar(select(Payment).where(Payment.invoice_id == inv["id"])) is None:
        db.add(Payment(
            invoice_id=inv["id"], user_id=u.id if u else None, stripe_customer_id=inv.get("customer"),
            amount=inv.get("amount_paid") or 0, tax=sum(t.get("amount", 0) for t in inv.get("total_taxes") or []),
            currency=(inv.get("currency") or "").upper(),
            billing_country=_country(inv.get("customer_address")) or (u.billing_country if u else None),
            card_country=u.card_country if u else None, period_start=_ts(start), period_end=_ts(end),
            paid_at=_ts((inv.get("status_transitions") or {}).get("paid_at")) or datetime.utcnow(),
        ))
    if u is None or end is None:
        return
    period_end = _ts(end)
    u.paid_until = max(u.paid_until, period_end) if u.paid_until else period_end
    u.member_since = u.member_since or datetime.utcnow()


def _payment_failed(db: Session, inv: dict, _prev: dict) -> None:
    # Stripe retries and emails the member; access carries on to the end of the paid month plus the grace days.
    if (u := _user(db, inv.get("customer"))) is not None and u.subscription_status == "active":
        u.subscription_status = "past_due"


def _customer_updated(db: Session, customer: dict, _prev: dict) -> None:
    if (u := _user(db, customer.get("id"))) is not None:
        u.billing_country = _country(customer.get("address")) or u.billing_country


def end_access(u: User) -> None:
    """Refund, dispute or fraud warning: no access from now, and no more charges."""
    if u.subscription_id and has_subscription(u):
        try:
            cancel_now(u.subscription_id)
        except stripe.StripeError:
            log.exception("couldn't cancel %s; cancel it in the Stripe Dashboard", u.subscription_id)
    u.paid_until = None
    u.cancel_at_period_end = False


def _charge_refunded(db: Session, charge: dict, _prev: dict) -> None:
    if charge.get("refunded") and (u := _user(db, charge.get("customer"))) is not None:  # fully refunded only
        end_access(u)


def _dispute_created(db: Session, dispute: dict, _prev: dict) -> None:
    charge = dispute.get("charge")
    try:
        customer = charge.get("customer") if isinstance(charge, dict) else charge_customer(charge)
    except stripe.StripeError:
        log.exception("dispute %s: couldn't read charge %s", dispute.get("id"), charge)
        return
    if (u := _user(db, customer)) is not None:
        end_access(u)


HANDLERS = {
    "checkout.session.completed": _checkout_completed,
    "checkout.session.async_payment_succeeded": _checkout_completed,
    "customer.subscription.created": _subscription_changed,
    "customer.subscription.updated": _subscription_changed,
    "customer.subscription.deleted": _subscription_changed,
    "invoice.paid": _invoice_paid,
    "invoice.payment_failed": _payment_failed,
    "customer.updated": _customer_updated,
    "charge.refunded": _charge_refunded,
    "charge.dispute.created": _dispute_created,
    "radar.early_fraud_warning.created": _dispute_created,  # has a `charge` too; acting first avoids a dispute
}
EVENTS = sorted(HANDLERS)  # what the Stripe webhook endpoint should send


# ── Admin ────────────────────────────────────────────────────────────────────


def members_overview(db: Session) -> dict:
    now = datetime.utcnow()
    members = list(db.scalars(select(User).where(User.is_admin.is_(False), User.stripe_customer_id.is_not(None))
                              .order_by(User.member_since.desc())))
    payments = list(db.scalars(select(Payment).order_by(Payment.paid_at.desc())))
    year_ago = now - timedelta(days=365)
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
