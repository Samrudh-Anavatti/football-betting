"""Membership: joining through Whop's checkout, the webhook keeping access in step, the grace days, refunds and
disputes, deleting an account with a live membership, and the admins' view of payments by country."""
import json
import time
from datetime import datetime, timedelta
from itertools import count

import pytest

from app import access, config
from app.database import SessionLocal
from app.models import Payment, User
from app.services import billing

from .test_auth import signup

API = "/api/v1"
SECRET = "ws_test_secret"
_ids = count(1)


@pytest.fixture(autouse=True)
def staking_for_members(monkeypatch):
    """These tests are about the paywall, so put the staking plan behind it (it's on free accounts until it opens)."""
    monkeypatch.setitem(access.FEATURES, "staking", "member")


@pytest.fixture()
def whop(monkeypatch):
    """Whop switched on, with its outbound calls replaced; holds the memberships Whop "has" and what was cancelled."""
    state = {"cancelled": [], "memberships": {}}
    monkeypatch.setattr(config, "WHOP_API_KEY", "apik_test")
    monkeypatch.setattr(config, "WHOP_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "WHOP_PLAN_ID", "plan_1")
    monkeypatch.setattr(billing, "price", lambda: {"amount": 399, "currency": "gbp", "interval": "month"})
    monkeypatch.setattr(billing, "create_checkout", lambda u: "https://whop.test/checkout/plan_1")
    monkeypatch.setattr(billing, "membership", lambda mem_id: state["memberships"][mem_id])
    monkeypatch.setattr(billing, "cancel_now", lambda mem_id: state["cancelled"].append(mem_id))
    return state


def send(client, type_, data, msg_id=None):
    payload = json.dumps({"id": "evt", "type": type_, "api_version": "v1", "data": data}).encode()
    msg_id, stamp = msg_id or f"msg_{next(_ids)}", str(int(time.time()))
    return client.post(f"{API}/membership/webhook", content=payload, headers={
        "webhook-id": msg_id, "webhook-timestamp": stamp, "content-type": "application/json",
        "webhook-signature": "v1," + billing.signature(SECRET, msg_id, stamp, payload)})


def z(t):
    return t.isoformat() + ".000Z"


def mem(mem_id, uid, end, status="active", cancelling=False):
    return {"id": mem_id, "status": status, "metadata": {"user_id": str(uid)}, "cancel_at_period_end": cancelling,
            "current_period_start": z(end - timedelta(days=30)), "current_period_end": z(end),
            "manage_url": f"https://whop.test/billing/manage/{mem_id}"}


def payment(pay_id, mem_id, uid, country="de"):
    return {"id": pay_id, "membership_id": mem_id, "metadata": {"user_id": str(uid)}, "currency": "gbp",
            "total": {"amount": "3.99", "currency": "gbp", "decimals": 2},
            "tax_amount": {"amount": "0.67", "currency": "gbp", "decimals": 2},
            "billing_address": {"country": country}, "paid_at": z(datetime.utcnow().replace(microsecond=0))}


def me(client, h):
    return client.get(f"{API}/auth/me", headers=h).json()["membership"]


def uid_of(client, h):
    return client.get(f"{API}/auth/me", headers=h).json()["id"]


def pay_in(client, whop, h, mem_id, pay_id, end=None):
    """A first payment landing: Whop holds the membership, and tells us about it and the payment."""
    uid = uid_of(client, h)
    end = end or (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)
    whop["memberships"][mem_id] = mem(mem_id, uid, end)
    assert send(client, "payment.succeeded", payment(pay_id, mem_id, uid)).status_code == 200
    return uid, end


def test_closed_until_whop_is_set_up(client):
    h = signup(client, "early@example.com")
    assert client.get(f"{API}/membership").json()["open"] is False
    assert client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": True}).status_code == 503
    assert client.post(f"{API}/membership/webhook", content=b"{}").status_code == 503
    assert client.get(f"{API}/staking", headers=h).status_code == 403  # members only


def test_join_pay_renew_and_lapse(client, auth, whop):
    h = signup(client, "joiner@example.com")
    assert client.get(f"{API}/membership").json() == {
        "open": True, "price": {"amount": 399, "currency": "gbp", "interval": "month"}, "grace_days": 3}
    join = {"terms": True, "start_now": True}
    assert client.post(f"{API}/membership/checkout", headers=h, json={"terms": True, "start_now": False}).status_code == 422
    assert client.post(f"{API}/membership/checkout", headers=auth, json=join).status_code == 409
    assert client.post(f"{API}/membership/checkout", headers=h, json=join).json() == {"url": "https://whop.test/checkout/plan_1"}
    assert me(client, h)["member"] is False and me(client, h)["can_manage"] is False  # nothing paid yet
    assert client.post(f"{API}/membership/portal", headers=h).status_code == 404

    # Only Whop can call the webhook: a wrong signature, a missing one and a stale one are all refused.
    stamp = str(int(time.time()))
    bad = {"webhook-id": "msg_x", "webhook-timestamp": stamp, "webhook-signature": "v1,AAAA"}
    assert client.post(f"{API}/membership/webhook", content=b'{"type":"x"}', headers=bad).status_code == 400
    assert client.post(f"{API}/membership/webhook", content=b'{"type":"x"}').status_code == 400
    old = str(int(time.time()) - 3600)
    stale = {"webhook-id": "msg_x", "webhook-timestamp": old,
             "webhook-signature": "v1," + billing.signature(SECRET, "msg_x", old, b"{}")}
    assert client.post(f"{API}/membership/webhook", content=b"{}", headers=stale).status_code == 400

    # The payment arrives first; Whop sends it twice; then the membership event.
    uid = uid_of(client, h)
    end = (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)
    whop["memberships"]["mem_1"] = mem("mem_1", uid, end)
    first = payment("pay_first", "mem_1", uid)
    assert send(client, "payment.succeeded", first, "msg_paid").status_code == 200
    assert send(client, "payment.succeeded", first, "msg_paid").status_code == 200  # a retry: no double count
    assert send(client, "membership.activated", mem("mem_1", uid, end)).status_code == 200
    m = me(client, h)
    assert m["member"] is True and m["status"] == "active" and m["paid_until"] == end.isoformat() + "Z"
    assert m["access_until"] == (end + timedelta(days=3)).isoformat() + "Z" and m["can_manage"] is True
    assert client.get(f"{API}/staking", headers=h).status_code == 200
    assert client.post(f"{API}/membership/checkout", headers=h, json=join).status_code == 409
    assert client.post(f"{API}/membership/portal", headers=h).json() == {"url": "https://whop.test/billing/manage/mem_1"}

    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.billing_country == "DE" and u.terms_accepted_at is not None
        p = db.query(Payment).filter(Payment.user_id == u.id).one()
        assert (p.amount, p.tax, p.currency, p.period_end) == (399, 67, "GBP", end)
        # The grace days: still in 2 days after the paid month ends, out after 4.
        assert billing.is_member(u, end + timedelta(days=2)) and not billing.is_member(u, end + timedelta(days=4))

    # A failed renewal shows as past due; access carries on to the same date. Paid late, it extends.
    send(client, "membership.updated", mem("mem_1", uid, end, status="past_due"))
    assert me(client, h)["status"] == "past_due" and me(client, h)["paid_until"] == end.isoformat() + "Z"
    later = end + timedelta(days=30)
    whop["memberships"]["mem_1"] = mem("mem_1", uid, later)
    send(client, "payment.succeeded", payment("pay_second", "mem_1", uid))
    assert me(client, h)["paid_until"] == later.isoformat() + "Z" and me(client, h)["status"] == "active"

    # Admins see members and where the money came from; the CSV is for the accountant.
    overview = client.get(f"{API}/admin/members", headers=auth).json()
    row = next(r for r in overview["members"] if r["email"] == "joiner@example.com")
    assert row["billing_country"] == "DE" and row["member"] is True
    # Every sign-up is listed, paying or not, with when they joined.
    joined = next(r for r in overview["signups"] if r["email"] == "joiner@example.com")
    assert joined["created_at"] and overview["signups_week"] >= 1 and all(r["email"] for r in overview["signups"])
    assert {"country": "DE", "currency": "GBP", "payments": 2, "amount": 798, "tax": 134, "card_elsewhere": 0} in overview["by_country"]
    csv = client.get(f"{API}/admin/members/payments.csv", headers=auth)
    assert csv.status_code == 200 and "pay_first,3.99,0.67,GBP,DE," in csv.text
    assert client.get(f"{API}/admin/members", headers=h).status_code == 403

    # Cancelling on Whop keeps access to the end of the month; then Whop ends the membership and access goes.
    send(client, "membership.updated", mem("mem_1", uid, later, cancelling=True))
    m = me(client, h)
    assert m["cancelling"] is True and m["member"] is True
    send(client, "membership.updated", mem("mem_1", uid, later, status="canceled", cancelling=True))
    m = me(client, h)
    assert m["status"] == "canceled" and m["cancelling"] is False and m["member"] is False
    assert client.get(f"{API}/staking", headers=h).status_code == 403


def test_refund_and_dispute_end_access(client, whop):
    h = signup(client, "refund@example.com")
    pay_in(client, whop, h, "mem_r", "pay_r")
    assert me(client, h)["member"] is True
    part = {"id": "rfnd_1", "amount": 1.0, "status": "succeeded", "payment": {"id": "pay_r", "total": 3.99}}
    send(client, "refund.created", part)  # a part refund: no change
    assert me(client, h)["member"] is True
    send(client, "refund.created", {**part, "id": "rfnd_2", "amount": 3.99})
    assert me(client, h)["member"] is False and whop["cancelled"] == ["mem_r"]

    h2 = signup(client, "dispute@example.com")
    pay_in(client, whop, h2, "mem_d", "pay_d")
    send(client, "dispute.created", {"id": "dspt_1", "payment": {"id": "pay_d"}})
    assert me(client, h2)["member"] is False and whop["cancelled"][-1] == "mem_d"


def test_delete_account_cancels_the_membership(client, whop):
    h = signup(client, "leaver@example.com", "password1")
    uid, _ = pay_in(client, whop, h, "mem_l", "pay_leaver")
    r = client.post(f"{API}/auth/delete-account", headers=h, json={"password": "password1"})
    assert r.status_code == 204 and whop["cancelled"] == ["mem_l"]
    with SessionLocal() as db:
        assert db.get(User, uid) is None
        p = db.query(Payment).filter(Payment.invoice_id == "pay_leaver").one()
        assert p.user_id is None and p.billing_country == "DE"  # the financial record stays, without the person


def test_whop_amounts_and_times():
    assert billing._minor({"amount": "3.99", "decimals": 2}) == 399 and billing._minor(3.99) == 399
    assert billing._minor(None) == 0 and billing._minor({"amount": "500", "decimals": 0}) == 500
    assert billing._time("2026-08-01T00:00:00.000Z") == datetime(2026, 8, 1)
    assert billing._time("2026-11-22T16:29:52+02:00") == datetime(2026, 11, 22, 14, 29, 52)


def test_sandbox_is_for_test_accounts_only(client, whop, monkeypatch):
    monkeypatch.setattr(config, "WHOP_SANDBOX", True)
    monkeypatch.setattr(config, "WHOP_TESTERS", {"tester@example.com"})
    join = {"terms": True, "start_now": True}
    visitor, tester = signup(client, "public@example.com"), signup(client, "tester@example.com")
    assert client.get(f"{API}/membership").json()["open"] is False
    assert client.get(f"{API}/membership", headers=visitor).json()["open"] is False
    assert client.post(f"{API}/membership/checkout", headers=visitor, json=join).status_code == 503
    assert client.get(f"{API}/membership", headers=tester).json()["open"] is True
    assert client.post(f"{API}/membership/checkout", headers=tester, json=join).status_code == 200
    # Live but not announced yet: the same list keeps it to the testers. Emptied, it is open to everyone.
    monkeypatch.setattr(config, "WHOP_SANDBOX", False)
    assert client.get(f"{API}/membership", headers=visitor).json()["open"] is False
    assert client.get(f"{API}/membership", headers=tester).json()["open"] is True
    monkeypatch.setattr(config, "WHOP_TESTERS", set())
    assert client.get(f"{API}/membership").json()["open"] is True


def test_bought_on_whop_directly_is_matched_by_email(client, whop):
    h = signup(client, "direct@example.com")
    end = (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)
    whop["memberships"]["mem_e"] = {**mem("mem_e", 0, end), "metadata": {}}
    send(client, "payment.succeeded", {**payment("pay_e", "mem_e", 0), "metadata": None, "customer_email": "Direct@example.com"})
    assert me(client, h)["member"] is True
