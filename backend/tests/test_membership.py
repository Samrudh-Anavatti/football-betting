"""Membership: joining through Stripe Checkout, the webhook keeping access in step, the grace days, refunds and
disputes, deleting an account with a live subscription, and the admins' view of payments by country."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from itertools import count

import pytest

from app import config
from app.database import SessionLocal
from app.models import Payment, User
from app.services import billing

from .test_auth import signup

API = "/api/v1"
SECRET = "whsec_test"
_ids = count(1)


@pytest.fixture()
def stripe_fake(monkeypatch):
    """Stripe switched on, with its outbound calls replaced; returns what they were asked to do."""
    calls = {"cancelled": []}
    monkeypatch.setattr(config, "STRIPE_API_KEY", "rk_test_x")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "STRIPE_PRICE_ID", "price_1")
    monkeypatch.setattr(billing, "price", lambda: {"amount": 399, "currency": "gbp", "interval": "month"})

    def create_checkout(u):
        u.stripe_customer_id = u.stripe_customer_id or f"cus_{u.id}"
        return "https://checkout.stripe.test/s"

    monkeypatch.setattr(billing, "create_checkout", create_checkout)
    monkeypatch.setattr(billing, "portal_url", lambda u: "https://billing.stripe.test/p")
    monkeypatch.setattr(billing, "card_country", lambda sub_id: "DE")
    monkeypatch.setattr(billing, "payment_method_country", lambda pm: "FR")
    monkeypatch.setattr(billing, "charge_customer", lambda charge: calls["charge_customer"])
    monkeypatch.setattr(billing, "cancel_now", lambda sub_id: calls["cancelled"].append(sub_id))
    return calls


def send(client, type_, obj, previous=None, event_id=None):
    data = {"object": obj, **({"previous_attributes": previous} if previous else {})}
    payload = json.dumps({"id": event_id or f"evt_{next(_ids)}", "type": type_, "data": data})
    t = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return client.post(f"{API}/membership/webhook", content=payload,
                       headers={"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"})


def invoice(customer, end, inv_id=None, country="DE"):
    start = end - timedelta(days=30)
    return {"id": inv_id or f"in_{next(_ids)}", "customer": customer, "amount_paid": 399, "currency": "gbp",
            "total_taxes": [], "customer_address": {"country": country},
            "status_transitions": {"paid_at": int(time.time())},
            "lines": {"data": [{"period": {"start": int(start.timestamp()), "end": int(end.timestamp())}}]}}


def me(client, h):
    return client.get(f"{API}/auth/me", headers=h).json()["membership"]


def join(client, h):
    r = client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": True})
    assert r.status_code == 200, r.text
    return f"cus_{client.get(f'{API}/auth/me', headers=h).json()['id']}"


def test_closed_until_stripe_is_set_up(client):
    h = signup(client, "early@example.com")
    assert client.get(f"{API}/membership").json()["open"] is False
    assert client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": True}).status_code == 503
    assert client.post(f"{API}/membership/webhook", content=b"{}").status_code == 503
    assert client.get(f"{API}/staking", headers=h).status_code == 403  # members only


def test_join_pay_renew_and_lapse(client, auth, stripe_fake):
    h = signup(client, "joiner@example.com")
    assert client.get(f"{API}/membership").json() == {
        "open": True, "price": {"amount": 399, "currency": "gbp", "interval": "month"}, "grace_days": 3}
    assert client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": False}).status_code == 422
    assert client.post(f"{API}/membership/checkout", headers=auth, json={"terms": True, "start_now": True}).status_code == 409
    cus = join(client, h)
    assert me(client, h)["member"] is False and me(client, h)["can_manage"] is True  # nothing paid yet

    # Only Stripe can call the webhook.
    bad = client.post(f"{API}/membership/webhook", content=b'{"id":"evt_x"}', headers={"stripe-signature": "t=1,v1=00"})
    assert bad.status_code == 400

    end = (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)
    assert send(client, "customer.subscription.created", {"id": "sub_1", "customer": cus, "status": "active"}).status_code == 200
    first = invoice(cus, end, "in_first")
    assert send(client, "invoice.paid", first, event_id="evt_paid").status_code == 200
    assert send(client, "invoice.paid", first, event_id="evt_paid").status_code == 200  # Stripe resends: no double count
    send(client, "checkout.session.completed", {
        "id": "cs_1", "mode": "subscription", "payment_status": "paid", "customer": cus, "subscription": "sub_1",
        "client_reference_id": "x", "customer_details": {"address": {"country": "DE"}}})
    m = me(client, h)
    assert m["member"] is True and m["status"] == "active" and m["paid_until"] == end.isoformat() + "Z"
    assert m["access_until"] == (end + timedelta(days=3)).isoformat() + "Z"
    assert client.get(f"{API}/staking", headers=h).status_code == 200
    assert client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": True}).status_code == 409
    assert client.post(f"{API}/membership/portal", headers=h).json() == {"url": "https://billing.stripe.test/p"}

    with SessionLocal() as db:
        u = db.get(User, client.get(f"{API}/auth/me", headers=h).json()["id"])
        assert (u.billing_country, u.card_country) == ("DE", "DE") and u.terms_accepted_at is not None
        assert db.query(Payment).filter(Payment.user_id == u.id).count() == 1
        # The grace days: still in 2 days after the paid month ends, out after 4.
        assert billing.is_member(u, end + timedelta(days=2)) and not billing.is_member(u, end + timedelta(days=4))

    # A failed renewal shows as past due; access carries on to the same date. Paid late, it extends.
    send(client, "invoice.payment_failed", {"id": "in_2", "customer": cus})
    assert me(client, h)["status"] == "past_due" and me(client, h)["paid_until"] == end.isoformat() + "Z"
    send(client, "invoice.paid", invoice(cus, end + timedelta(days=30)))
    assert me(client, h)["paid_until"] == (end + timedelta(days=30)).isoformat() + "Z"

    # Cancelling in the portal keeps access to the end of the month; a new card's country is picked up.
    send(client, "customer.subscription.updated", {"id": "sub_1", "customer": cus, "status": "active",
                                                   "cancel_at_period_end": True, "default_payment_method": "pm_2"},
         previous={"cancel_at_period_end": False, "default_payment_method": "pm_1"})
    m = me(client, h)
    assert m["cancelling"] is True and m["member"] is True
    send(client, "customer.subscription.deleted", {"id": "sub_1", "customer": cus, "status": "canceled"})
    m = me(client, h)
    assert m["status"] == "canceled" and m["cancelling"] is False and m["member"] is True  # paid to the end

    # Admins see members and where the money came from; the CSV is for the accountant.
    overview = client.get(f"{API}/admin/members", headers=auth).json()
    row = next(r for r in overview["members"] if r["email"] == "joiner@example.com")
    assert (row["billing_country"], row["card_country"]) == ("DE", "FR")
    assert {"country": "DE", "currency": "GBP", "payments": 2, "amount": 798, "tax": 0, "card_elsewhere": 0} in overview["by_country"]
    csv = client.get(f"{API}/admin/members/payments.csv", headers=auth)
    assert csv.status_code == 200 and "in_first,3.99,0.00,GBP,DE,DE" in csv.text
    assert client.get(f"{API}/admin/members", headers=h).status_code == 403


def test_refund_and_dispute_end_access(client, stripe_fake):
    h = signup(client, "refund@example.com")
    cus = join(client, h)
    send(client, "customer.subscription.created", {"id": "sub_r", "customer": cus, "status": "active"})
    send(client, "invoice.paid", invoice(cus, datetime.utcnow() + timedelta(days=30)))
    send(client, "charge.refunded", {"id": "ch_1", "customer": cus, "refunded": False})  # partial: no change
    assert me(client, h)["member"] is True
    send(client, "charge.refunded", {"id": "ch_1", "customer": cus, "refunded": True})
    assert me(client, h)["member"] is False and stripe_fake["cancelled"] == ["sub_r"]

    h2 = signup(client, "dispute@example.com")
    cus2 = join(client, h2)
    send(client, "customer.subscription.created", {"id": "sub_d", "customer": cus2, "status": "active"})
    send(client, "invoice.paid", invoice(cus2, datetime.utcnow() + timedelta(days=30)))
    stripe_fake["charge_customer"] = cus2
    send(client, "radar.early_fraud_warning.created", {"id": "issfr_1", "charge": "ch_2"})
    assert me(client, h2)["member"] is False and stripe_fake["cancelled"][-1] == "sub_d"


def test_delete_account_cancels_the_subscription(client, stripe_fake):
    h = signup(client, "leaver@example.com", "password1")
    cus = join(client, h)
    uid = client.get(f"{API}/auth/me", headers=h).json()["id"]
    send(client, "customer.subscription.created", {"id": "sub_l", "customer": cus, "status": "active"})
    send(client, "invoice.paid", invoice(cus, datetime.utcnow() + timedelta(days=30), "in_leaver"))
    r = client.post(f"{API}/auth/delete-account", headers=h, json={"password": "password1"})
    assert r.status_code == 204 and stripe_fake["cancelled"] == ["sub_l"]
    with SessionLocal() as db:
        assert db.get(User, uid) is None
        p = db.query(Payment).filter(Payment.invoice_id == "in_leaver").one()
        assert p.user_id is None and p.billing_country == "DE"  # the financial record stays, without the person
