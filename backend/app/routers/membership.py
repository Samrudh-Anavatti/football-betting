"""Membership: the price, joining through Stripe Checkout, managing it in the Customer Portal, Stripe's webhook, and
the admins' view of members and payments (with where each payer is, for tax)."""
import csv
import io
import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import admin_user, current_user
from ..models import Payment, User
from ..ratelimit import client_ip, hit
from ..services import billing

router = APIRouter(tags=["membership"])
log = logging.getLogger(__name__)

UNAVAILABLE = "Payments aren't available right now. Try again in a few minutes."


@router.get("/membership")
def info():
    price = None
    if billing.ready():
        try:
            price = billing.price()
        except stripe.StripeError:
            log.exception("couldn't read the membership price")
    return {"open": billing.ready() and price is not None, "price": price, "grace_days": config.GRACE_DAYS}


class JoinIn(BaseModel):
    terms: bool  # agreed to the terms
    start_now: bool  # asked to start straight away, so the 14-day cancellation right ends once it starts


@router.post("/membership/checkout")
def checkout(body: JoinIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not billing.ready():
        raise HTTPException(503, "Membership isn't open yet")
    if user.is_admin:
        raise HTTPException(409, "Admins already see everything")
    if not (body.terms and body.start_now):
        raise HTTPException(422, "Tick both boxes to continue")
    if billing.has_subscription(user):
        raise HTTPException(409, "You're already a member. Manage it from your account page.")
    hit("checkout", client_ip(request), 10, 3600)
    user = db.get(User, user.id)
    user.terms_accepted_at = datetime.utcnow()
    try:
        url = billing.create_checkout(user)
    except stripe.StripeError:
        log.exception("checkout for user %s", user.id)
        raise HTTPException(502, UNAVAILABLE)
    db.commit()  # keeps the Stripe customer made for this checkout
    return {"url": url}


@router.post("/membership/portal")
def portal(user: User = Depends(current_user)):
    if not user.stripe_customer_id:
        raise HTTPException(404, "There's no membership on this account")
    try:
        return {"url": billing.portal_url(user)}
    except stripe.StripeError:
        log.exception("portal for user %s", user.id)
        raise HTTPException(502, UNAVAILABLE)


@router.post("/membership/webhook", include_in_schema=False)
async def webhook(request: Request):
    if not config.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Not configured")
    payload = await request.body()
    try:
        await run_in_threadpool(billing.handle_webhook, payload, request.headers.get("stripe-signature"))
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Bad signature")
    return {"received": True}


@router.get("/admin/members", dependencies=[Depends(admin_user)])
def members(db: Session = Depends(get_db)):
    return billing.members_overview(db)


@router.get("/admin/members/payments.csv", dependencies=[Depends(admin_user)])
def payments_csv(db: Session = Depends(get_db)):
    """Every payment, for the accountant: amounts in pounds/euros etc., with the billing and card countries."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["paid_at", "invoice_id", "amount", "tax", "currency", "billing_country", "card_country",
                "period_start", "period_end"])
    for p in db.scalars(select(Payment).order_by(Payment.paid_at)):
        w.writerow([p.paid_at.isoformat(timespec="seconds"), p.invoice_id, f"{p.amount / 100:.2f}", f"{p.tax / 100:.2f}",
                    p.currency, p.billing_country or "", p.card_country or "",
                    p.period_start.date().isoformat() if p.period_start else "",
                    p.period_end.date().isoformat() if p.period_end else ""])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="payments.csv"'})
