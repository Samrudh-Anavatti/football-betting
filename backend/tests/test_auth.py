"""Member accounts: sign-up, sign-in by email, password change and reset, deleting an account."""
import pytest

from app import config
from app.services import email

API = "/api/v1"


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(email, "send", lambda to, subject, text, html: sent.append((to, subject, text)))
    return sent


def signup(client, addr="fan@example.com", pw="password1"):
    r = client.post(f"{API}/auth/signup", json={"email": addr, "password": pw, "adult": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_signup_and_sign_in_by_email(client):
    h = signup(client, " Fan@Example.com ")
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["email"] == "fan@example.com" and me["is_admin"] is False and me["display_name"] == "fan"

    r = client.post(f"{API}/auth/login", json={"username": "FAN@example.com", "password": "password1"})
    assert r.status_code == 200 and r.json()["user"]["id"] == me["id"]
    assert client.post(f"{API}/auth/login", json={"username": "fan@example.com", "password": "nope"}).status_code == 401

    # Members aren't admins, and don't show up among the admins' accounts.
    assert client.get(f"{API}/admin/accounts", headers=h).status_code == 403


def test_signup_rules(client, auth):
    def post(**kw):
        return client.post(f"{API}/auth/signup", json={"email": "a@b.co", "password": "password1", "adult": True, **kw})

    assert post(adult=False).status_code == 422
    assert post(email="not-an-email").status_code == 422
    assert post(password="short").status_code == 422
    assert post().status_code == 201
    assert "already an account" in post(email="A@B.co").json()["detail"]
    names = [a["display_name"] for a in client.get(f"{API}/admin/accounts", headers=auth).json()["accounts"]]
    assert "a" not in names


def test_change_password_signs_out_other_devices(client):
    old = signup(client, "change2@example.com")
    r = client.put(f"{API}/auth/password", headers=old, json={"current_password": "wrong", "new_password": "newpass99"})
    assert r.status_code == 403
    r = client.put(f"{API}/auth/password", headers=old, json={"current_password": "password1", "new_password": "newpass99"})
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get(f"{API}/auth/me", headers=new).status_code == 200
    assert client.post(f"{API}/auth/login", json={"username": "change2@example.com", "password": "newpass99"}).status_code == 200


def test_password_reset(client, outbox):
    old = signup(client, "password3@example.com")
    r = client.post(f"{API}/auth/forgot", json={"email": "password3@example.com"})
    unknown = client.post(f"{API}/auth/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == unknown.status_code == 200 and r.json() == unknown.json()  # doesn't say who has an account
    assert len(outbox) == 1 and outbox[0][0] == "password3@example.com"
    link = next(w for w in outbox[0][2].split() if w.startswith(config.SITE_URL))
    token = link.split("#token=")[1]

    assert client.post(f"{API}/auth/reset", json={"token": "bogus", "password": "newpass99"}).status_code == 400
    r = client.post(f"{API}/auth/reset", json={"token": token, "password": "newpass99"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "password3@example.com"
    assert client.post(f"{API}/auth/reset", json={"token": token, "password": "another99"}).status_code == 400  # single use
    assert client.get(f"{API}/auth/me", headers=old).status_code == 401
    assert client.post(f"{API}/auth/login", json={"username": "password3@example.com", "password": "newpass99"}).status_code == 200


def test_reset_link_expires(client, outbox, monkeypatch):
    signup(client, "reset4@example.com")
    monkeypatch.setattr(config, "RESET_MINUTES", -1)
    client.post(f"{API}/auth/forgot", json={"email": "reset4@example.com"})
    token = outbox[0][2].split("#token=")[1].split()[0]
    assert client.post(f"{API}/auth/reset", json={"token": token, "password": "newpass99"}).status_code == 400


def test_forgot_is_rate_limited_per_email(client, outbox):
    signup(client, "forgot5@example.com")
    codes = [client.post(f"{API}/auth/forgot", json={"email": "forgot5@example.com"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429] and len(outbox) == 3


def test_failed_logins_are_rate_limited(client):
    for _ in range(10):
        assert client.post(f"{API}/auth/login", json={"username": "ivo", "password": "wrong"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"username": "ivo", "password": "pw"}).status_code == 429


def test_delete_account(client, auth):
    h = signup(client, "delete7@example.com")
    assert client.post(f"{API}/auth/delete-account", headers=h, json={"password": "wrong"}).status_code == 403
    assert client.post(f"{API}/auth/delete-account", headers=h, json={"password": "password1"}).status_code == 204
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/delete-account", headers=auth, json={"password": "pw"}).status_code == 409
